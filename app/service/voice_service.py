from __future__ import annotations

import base64
import logging
import os
import re
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.models.character import Character
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.repository.character_repo import (
    get_latest_screenplay_version_by_project,
    list_characters,
)
from app.schemas.dialogue import DialogueItem
from app.service.composition_service import get_ffmpeg_path
from app.service.production_service import _validate_project_access

logger = logging.getLogger(__name__)

# Available voice assignments for consistent character voices
FEMALE_VOICES = ["luna", "asteria", "stella", "athena"]
MALE_VOICES = ["zeus", "orion", "arcas", "perseus"]


def get_default_voice_for_character(character: Character | None) -> str:
    """
    Deterministically assign a consistent voice per character based on their metadata.
    """
    if not character:
        return "orion"

    name_lower = character.name.lower()
    role_lower = (character.role or "").lower()
    appearance_lower = (character.appearance or "").lower()

    # Determine female vs male cues
    is_female = any(
        k in name_lower or k in role_lower or k in appearance_lower
        for k in ["female", "woman", "girl", "mother", "sister", "queen", "actress", "sophia", "emily", "sarah", "maria", "priya"]
    )

    seed = sum(ord(c) for c in character.name)
    if is_female:
        return FEMALE_VOICES[seed % len(FEMALE_VOICES)]
    else:
        return MALE_VOICES[seed % len(MALE_VOICES)]


def detect_language(text: str) -> str:
    """
    Detect dialogue language based on script ranges and linguistic markers.
    Preserves non-English dialogues for appropriate multilingual TTS routing.
    """
    if not text:
        return "en"

    # 1. Devanagari Hindi: \u0900-\u097F
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"

    # 2. Japanese (Hiragana, Katakana): \u3040-\u30FF
    if re.search(r"[\u3040-\u309F\u30A0-\u30FF]", text):
        return "ja"

    # 3. Chinese (CJK Ideographs without Japanese kana): \u4E00-\u9FFF
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh"

    # 4. Cyrillic: \u0400-\u04FF
    if re.search(r"[\u0400-\u04FF]", text):
        return "ru"

    # 5. Arabic: \u0600-\u06FF
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"

    # 6. Spanish markers
    if re.search(r"[¿¡]|(\b(hola|gracias|por favor|adiós|amigo|señor|señora|buenos días)\b)", text, re.IGNORECASE):
        return "es"

    # 7. French markers
    if re.search(r"\b(bonjour|merci|s'il vous plaît|au revoir|oui|monsieur|madame)\b", text, re.IGNORECASE):
        return "fr"

    # 8. German markers
    if re.search(r"\b(hallo|danke|bitte|auf wiedersehen|guten tag|jawohl)\b", text, re.IGNORECASE):
        return "de"

    return "en"


def get_audio_duration(audio_path: Path) -> float:
    """Extract audio duration in seconds using FFmpeg."""
    try:
        ffmpeg_exe = get_ffmpeg_path()
        res = subprocess.run(
            [ffmpeg_exe, "-i", str(audio_path), "-f", "null", "-"],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        # Match 'Duration: 00:00:04.50'
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
        if m:
            hours, mins, secs = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return hours * 3600 + mins * 60 + secs
    except Exception as exc:
        logger.warning("Could not probe audio duration with ffmpeg: %s", exc)

    # Fallback approximation for MP3 ~ 16KB/s (128kbps) or file size
    size = audio_path.stat().st_size
    return max(1.0, round(size / 16000.0, 2))


class VoiceService:
    """
    Character dialogue voice synthesis service powered by Cloudflare Workers AI TTS.
    Supports English (Deepgram Aura-2) and Hindi / Multilingual (MeloTTS).
    """

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.account_id = (
            account_id
            or getattr(settings, "CLOUDFLARE_VIDEO_ACCOUNT_ID", "")
            or getattr(settings, "CLOUDFLARE_ACCOUNT_ID", "")
        )
        self.api_token = (
            api_token
            or getattr(settings, "CLOUDFLARE_VIDEO_API_TOKEN", "")
            or getattr(settings, "CLOUDFLARE_API_TOKEN", "")
        )

    async def generate_speech(
        self,
        text: str,
        speaker: str | None = None,
        language: str = "en",
        timeout: float = 30.0,
    ) -> bytes:
        """
        Synthesize speech from dialogue text.
        Returns raw audio bytes (MP3 or WAV).
        """
        if not self.account_id or not self.api_token:
            raise ValueError("Cloudflare credentials not configured for VoiceService.")

        lang = (language or "").strip().lower()
        detected = detect_language(text)
        effective_lang = detected if detected != "en" else (lang or "en")

        if effective_lang in ["hi", "ja", "zh", "ru", "ar", "es", "fr", "de"] or any(effective_lang.startswith(k) for k in ["hi", "ja", "zh", "ru", "ar", "es", "fr", "de"]):
            # Use MeloTTS for multilingual speech synthesis
            model = "@cf/myshell-ai/melotts"
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{model}"
            payload = {"prompt": text}
        else:
            # Use Deepgram Aura-2 for English
            model = "@cf/deepgram/aura-2-en"
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{model}"
            payload = {"text": text}
            if speaker:
                payload["speaker"] = speaker.lower()

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Cloudflare TTS failed ({resp.status_code}): {resp.text[:300]}"
                )

            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                # MeloTTS returns JSON with base64 audio
                data = resp.json()
                if not data.get("success", False) and "result" not in data:
                    err = data.get("errors", [{}])[0].get("message", "Unknown TTS error")
                    raise RuntimeError(f"MeloTTS error: {err}")
                audio_b64 = data.get("result", {}).get("audio")
                if not audio_b64:
                    raise RuntimeError("No audio data returned in MeloTTS response.")
                return base64.b64decode(audio_b64)
            else:
                # Direct audio binary (e.g. MP3)
                return resp.content


# Singleton instance
voice_service = VoiceService()


def get_shot_dialogues(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Retrieve structured dialogue list for a shot."""
    _validate_project_access(db, project_id, user_id)
    shot = db.query(Shot).filter(Shot.id == shot_id, Shot.project_id == project_id).first()
    if not shot:
        raise ValueError("Shot not found.")

    meta = shot.asset_metadata or {}
    return meta.get("dialogues", [])


def update_shot_dialogues(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    dialogues: list[DialogueItem],
) -> list[dict[str, Any]]:
    """Save structured dialogues for a shot without requiring database migrations."""
    _validate_project_access(db, project_id, user_id)
    shot = db.query(Shot).filter(Shot.id == shot_id, Shot.project_id == project_id).first()
    if not shot:
        raise ValueError("Shot not found.")

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    name_map = {c.name.lower(): c for c in characters}

    cleaned = []
    for d in dialogues:
        d_dict = d.model_dump()
        d_dict["shot_id"] = str(shot_id)
        d_dict["scene_id"] = str(shot.scene_id)

        # Match character if missing
        matched_char = None
        if d.character_id and str(d.character_id) in char_map:
            matched_char = char_map[str(d.character_id)]
        elif d.character_name and d.character_name.lower() in name_map:
            matched_char = name_map[d.character_name.lower()]
            d_dict["character_id"] = str(matched_char.id)

        # Ensure consistent default voice if not set
        if not d_dict.get("voice_id"):
            d_dict["voice_id"] = get_default_voice_for_character(matched_char)

        if not d_dict.get("language"):
            d_dict["language"] = detect_language(d.text)

        cleaned.append(d_dict)

    current_meta = dict(shot.asset_metadata or {})
    current_meta["dialogues"] = cleaned
    shot.asset_metadata = current_meta

    db.commit()
    db.refresh(shot)
    return cleaned


async def generate_shot_dialogue_voice(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    dialogue_id: str | None = None,
    force_regenerate: bool = False,
    override_voice_id: str | None = None,
    override_language: str | None = None,
) -> dict[str, Any]:
    """
    Generate dialogue audio for one or all dialogues in a shot.
    Saves audio to generated-audio/{project_id}/ and updates metadata.
    """
    _validate_project_access(db, project_id, user_id)
    shot = db.query(Shot).filter(Shot.id == shot_id, Shot.project_id == project_id).first()
    if not shot:
        raise ValueError("Shot not found.")

    current_meta = dict(shot.asset_metadata or {})
    dialogues: list[dict[str, Any]] = list(current_meta.get("dialogues", []))

    if not dialogues:
        raise ValueError("No dialogues defined for this shot. Add a dialogue entry first.")

    audio_dir = Path("d:/AI-Video-Studio/generated-audio") / str(project_id)
    audio_dir.mkdir(parents=True, exist_ok=True)

    characters = list_characters(db, project_id)
    char_map = {str(c.id): c for c in characters}
    name_map = {c.name.lower(): c for c in characters}

    total = len(dialogues)
    completed = 0
    failed = 0

    for idx, d in enumerate(dialogues):
        curr_id = d.get("id")
        if dialogue_id and curr_id != dialogue_id:
            if d.get("status") == "completed":
                completed += 1
            continue

        text = (d.get("text") or "").strip()
        if not text:
            d["status"] = "failed"
            d["error"] = "Empty dialogue text."
            failed += 1
            continue

        # Check existing audio
        existing_url = d.get("audio_url")
        if existing_url and not force_regenerate:
            # Check file on disk
            rel_path = existing_url.lstrip("/")
            file_on_disk = Path("d:/AI-Video-Studio") / rel_path
            if file_on_disk.is_file():
                d["status"] = "completed"
                completed += 1
                continue

        # Determine voice and language
        lang = override_language or d.get("language") or detect_language(text)
        speaker = override_voice_id or d.get("voice_id")
        if not speaker:
            char_obj = char_map.get(str(d.get("character_id"))) or name_map.get((d.get("character_name") or "").lower())
            speaker = get_default_voice_for_character(char_obj)
            d["voice_id"] = speaker

        d["language"] = lang
        d["status"] = "generating"

        try:
            audio_bytes = await voice_service.generate_speech(
                text=text,
                speaker=speaker,
                language=lang,
            )

            # Determine extension (mp3 or wav)
            ext = "wav" if audio_bytes.startswith(b"RIFF") else "mp3"
            filename = f"{shot_id}_{curr_id}.{ext}"
            filepath = audio_dir / filename

            with open(filepath, "wb") as f:
                f.write(audio_bytes)

            dur = get_audio_duration(filepath)
            final_url = f"/generated-audio/{project_id}/{filename}"

            d["audio_url"] = final_url
            d["duration_seconds"] = dur
            d["status"] = "completed"
            d["error"] = None
            d["generated_at"] = datetime.utcnow().isoformat()
            completed += 1

        except Exception as exc:
            logger.error("TTS generation failed for dialogue %s: %s", curr_id, exc)
            d["status"] = "failed"
            d["error"] = str(exc)
            failed += 1

    current_meta["dialogues"] = dialogues
    shot.asset_metadata = current_meta
    db.commit()
    db.refresh(shot)

    return {
        "shot_id": str(shot_id),
        "total_dialogues": total,
        "completed_dialogues": completed,
        "failed_dialogues": failed,
        "dialogues": dialogues,
        "message": f"Generated audio for {completed} of {total} dialogues.",
    }


def populate_dialogues_from_screenplay(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Automatically populate structured dialogues on storyboard shots
    from the project's approved screenplay scenes.
    Preserves existing dialogues and character voice assignments.
    """
    _validate_project_access(db, project_id, user_id)
    characters = list_characters(db, project_id)
    name_to_char = {c.name.strip().lower(): c for c in characters}
    latest_screenplay_version = get_latest_screenplay_version_by_project(db, project_id)

    scenes = (
        db.query(Scene)
        .filter(Scene.project_id == project_id)
        .order_by(Scene.scene_number.asc())
        .all()
    )

    populated_count = 0
    shots_updated = 0

    for sc in scenes:
        shots = (
            db.query(Shot)
            .filter(Shot.scene_id == sc.id)
            .order_by(Shot.shot_number.asc())
            .all()
        )
        if not shots:
            continue

        # Retrieve screenplay version content from scene relation or fallback to latest project screenplay
        screenplay_dialogues: list[dict[str, str]] = []
        sp_version = getattr(sc, "screenplay_version", None) or latest_screenplay_version
        if sp_version and sp_version.content:
            content = sp_version.content or {}
            for sc_item in content.get("scenes", []):
                if sc_item.get("scene_number") == sc.scene_number:
                    screenplay_dialogues = sc_item.get("dialogue", [])
                    break

        if not screenplay_dialogues:
            continue

        # Map dialogue lines to shots (typically Shot 2 or Shot 3 onwards)
        # Distribute dialogues across scene shots
        for idx, diag in enumerate(screenplay_dialogues):
            if isinstance(diag, dict):
                char_name = str(diag.get("character") or "Narrator").strip()
                line_text = str(diag.get("line") or "").strip()
            else:
                char_name = "Narrator"
                line_text = str(diag or "").strip()

            if not line_text:
                continue

            target_shot_idx = min(idx + 1, len(shots) - 1)
            target_shot = shots[target_shot_idx]

            meta = dict(target_shot.asset_metadata or {})
            existing_dialogues = list(meta.get("dialogues", []))

            # Check if this exact text already exists
            if any(ed.get("text") == line_text for ed in existing_dialogues):
                continue

            char_obj = name_to_char.get(char_name.lower())
            voice_id = get_default_voice_for_character(char_obj)
            lang = detect_language(line_text)

            new_item = {
                "id": uuid.uuid4().hex[:12],
                "scene_id": str(sc.id),
                "shot_id": str(target_shot.id),
                "character_id": str(char_obj.id) if char_obj else None,
                "character_name": char_name,
                "text": line_text,
                "language": lang,
                "voice_id": voice_id,
                "emotion_tone": "natural",
                "start_time": 0.5,
                "duration_seconds": None,
                "audio_url": None,
                "status": "pending",
            }
            existing_dialogues.append(new_item)
            meta["dialogues"] = existing_dialogues
            target_shot.asset_metadata = meta
            flag_modified(target_shot, "asset_metadata")
            populated_count += 1
            shots_updated += 1

    db.commit()
    return {
        "project_id": str(project_id),
        "populated_dialogues": populated_count,
        "shots_updated": shots_updated,
        "message": f"Successfully mapped {populated_count} dialogue lines into storyboard shots.",
    }


def _has_audio_stream(video_path: Path) -> bool:
    """Check if video file has an audio track."""
    try:
        ffmpeg_exe = get_ffmpeg_path()
        res = subprocess.run(
            [ffmpeg_exe, "-i", str(video_path)],
            stderr=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
        return "Audio:" in res.stderr
    except Exception:
        return False


def mix_dialogue_into_shot_video(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    duck_ambient: bool = True,
    ambient_volume: float = 0.25,
    speech_volume: float = 1.0,
    force_remix: bool = False,
) -> dict[str, Any]:
    """
    Mix character dialogue audio into the generated shot video.
    Ducks ambient room tone while preserving existing video frames, clothing, and environment.
    """
    _validate_project_access(db, project_id, user_id)
    shot = db.query(Shot).filter(Shot.id == shot_id, Shot.project_id == project_id).first()
    if not shot:
        raise ValueError("Shot not found.")

    if not shot.video_url:
        raise ValueError("Cannot mix dialogue: shot video has not been generated yet.")

    from app.service.composition_service import resolve_video_path

    video_path = resolve_video_path(shot.video_url)
    if not video_path.is_file():
        raise ValueError(f"Shot video file not found at: {video_path}")

    current_meta = dict(shot.asset_metadata or {})
    dialogues = [d for d in current_meta.get("dialogues", []) if d.get("status") == "completed" and d.get("audio_url")]

    if not dialogues:
        return {
            "shot_id": str(shot_id),
            "video_url": shot.video_url,
            "has_dialogue": False,
            "ambient_preserved": True,
            "status": "skipped",
            "message": "No completed dialogue audio to mix into this shot.",
        }

    # If already mixed and not forcing remix
    if current_meta.get("dialogue_mixed") and not force_remix:
        return {
            "shot_id": str(shot_id),
            "video_url": shot.video_url,
            "has_dialogue": True,
            "ambient_preserved": True,
            "status": "completed",
            "message": "Dialogue audio is already mixed into this shot.",
        }

    # Collect audio paths and start offsets
    audio_inputs: list[Path] = []
    for d in dialogues:
        rel = d["audio_url"].lstrip("/")
        p = (Path("d:/AI-Video-Studio") / rel).resolve()
        if p.is_file():
            audio_inputs.append(p)

    if not audio_inputs:
        raise ValueError("Dialogue audio files missing on disk.")

    ffmpeg_exe = get_ffmpeg_path()
    output_dir = Path("d:/AI-Video-Studio/generated-videos") / str(project_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    dubbed_id = uuid.uuid4().hex[:8]
    output_filename = f"{shot_id}_dubbed_{dubbed_id}.mp4"
    output_path = output_dir / output_filename

    has_ambient = _has_audio_stream(video_path)

    # Build FFmpeg command
    cmd = [ffmpeg_exe, "-y", "-i", str(video_path)]
    for ap in audio_inputs:
        cmd.extend(["-i", str(ap)])

    if has_ambient and duck_ambient:
        # Mix ambient ducked with speech inputs
        # If single dialogue:
        if len(audio_inputs) == 1:
            filter_str = (
                f"[0:a]volume={ambient_volume}[amb];"
                f"[1:a]volume={speech_volume}[speech];"
                f"[amb][speech]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        else:
            # Multi-dialogue inputs
            inputs_str = "".join(f"[{i+1}:a]" for i in range(len(audio_inputs)))
            filter_str = (
                f"[0:a]volume={ambient_volume}[amb];"
                f"{inputs_str}amix=inputs={len(audio_inputs)}:dropout_transition=2[speech_all];"
                f"[speech_all]volume={speech_volume}[speech_vol];"
                f"[amb][speech_vol]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )

        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-movflags", "+faststart",
            str(output_path),
        ])
    else:
        # Video without ambient or ducking disabled
        if len(audio_inputs) == 1:
            cmd.extend([
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output_path),
            ])
        else:
            inputs_str = "".join(f"[{i+1}:a]" for i in range(len(audio_inputs)))
            filter_str = f"{inputs_str}amix=inputs={len(audio_inputs)}:dropout_transition=2[aout]"
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-movflags", "+faststart",
                str(output_path),
            ])

    logger.info("Mixing dialogue audio into shot %s with FFmpeg: %s", shot_id, " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)

    if proc.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg audio mixing failed ({proc.returncode}): {proc.stderr[:400]}")

    new_url = f"/generated-videos/{project_id}/{output_filename}"

    from app.utils.r2_storage import is_r2_configured, upload_file
    if is_r2_configured():
        try:
            r2_key = f"videos/{project_id}/{output_filename}"
            new_url = upload_file(output_path, key=r2_key, content_type="video/mp4")
            try:
                output_path.unlink()
            except Exception:
                pass
        except Exception as r2_exc:
            logger.warning("Failed to upload dubbed video to R2, keeping local fallback: %s", r2_exc)

    # Preserve original video URL if first dubbing
    if "original_video_url" not in current_meta:
        current_meta["original_video_url"] = shot.video_url

    current_meta["dialogue_mixed"] = True
    current_meta["dubbed_video_url"] = new_url
    current_meta["mixed_at"] = datetime.utcnow().isoformat()
    shot.video_url = new_url
    shot.asset_metadata = current_meta

    db.commit()
    db.refresh(shot)

    return {
        "shot_id": str(shot_id),
        "video_url": new_url,
        "has_dialogue": True,
        "ambient_preserved": has_ambient,
        "status": "completed",
        "message": f"Successfully mixed {len(audio_inputs)} dialogue audio tracks with ambient sound.",
    }

