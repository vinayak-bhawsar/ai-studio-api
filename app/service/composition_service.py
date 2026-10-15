from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.service.production_service import _validate_project_access

logger = logging.getLogger(__name__)

# Active in-flight composition locks by project_id
_active_compositions: set[str] = set()


def get_ffmpeg_path() -> str:
    """
    Locate a working ffmpeg binary.
    Searches in local project bin, PATH, and standard Windows directories.
    """
    candidates = [
        Path("d:/AI-Video-Studio/bin/ffmpeg.exe"),
        Path(os.getcwd()) / "bin" / "ffmpeg.exe",
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/ProgramData/chocolatey/bin/ffmpeg.exe"),
        Path("C:/ProgramData/chocolatey/lib/ffmpeg/tools/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Users/Admin/AppData/Local/Programs/ffmpeg/bin/ffmpeg.exe"),
    ]

    for c in candidates:
        if c.is_file():
            return str(c.resolve())

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    try:
        import importlib
        imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    raise RuntimeError(
        "FFmpeg binary not found. Please ensure FFmpeg is installed or placed in the application bin directory."
    )


def resolve_video_path(video_url: str) -> Path:
    """
    Convert a video URL or relative path into an absolute local Path.
    If the URL is a remote R2 or HTTP URL, downloads to a local temporary file
    so FFmpeg operations (concatenation, audio mixing, probe) can run directly on it.
    Examples:
      'https://pub-...r2.dev/agenting-rag/videos/xxx.mp4' -> Path('.../temp_xxx.mp4')
      '/generated-videos/xxx/yyy.mp4' -> Path('d:/AI-Video-Studio/generated-videos/xxx/yyy.mp4')
      'generated-videos/xxx/yyy.mp4'  -> Path('d:/AI-Video-Studio/generated-videos/xxx/yyy.mp4')
    """
    if not video_url or not video_url.strip():
        raise ValueError("Cannot resolve empty video_url.")

    url_str = video_url.strip()
    if url_str.startswith(("http://", "https://")):
        from app.utils.r2_storage import download_to_temp_file
        return download_to_temp_file(url_str, suffix=".mp4")

    cleaned = url_str.lstrip("/").replace("\\", "/")
    # If starts with generated-videos
    base_dir = Path("d:/AI-Video-Studio").resolve()
    target_path = (base_dir / cleaned).resolve()

    if not target_path.is_file():
        # Try relative to current working directory
        cwd_target = (Path(os.getcwd()) / cleaned).resolve()
        if cwd_target.is_file():
            return cwd_target

    return target_path


def _get_metadata_path(project_id: uuid.UUID) -> Path:
    target_dir = Path("d:/AI-Video-Studio/generated-videos") / str(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / "composition_metadata.json"


def _read_composition_metadata(project_id: uuid.UUID) -> dict[str, Any] | None:
    meta_path = _get_metadata_path(project_id)
    if not meta_path.is_file():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not read composition metadata for %s: %s", project_id, exc)
        return None


def _write_composition_metadata(project_id: uuid.UUID, data: dict[str, Any]) -> None:
    meta_path = _get_metadata_path(project_id)
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        logger.error("Could not write composition metadata for %s: %s", project_id, exc)


def get_project_composition_status(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """
    Retrieve current video composition status, final video URL, and shot summaries.
    """
    _validate_project_access(db, project_id, user_id)

    # Collect project shots strictly ordered by Scene and Shot sequence
    shots = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Shot.project_id == project_id)
        .order_by(Scene.scene_number.asc(), Shot.shot_number.asc())
        .all()
    )

    shot_summaries = []
    completed_count = 0
    total_duration = 0.0

    for s in shots:
        dur = (s.production_settings or {}).get("duration_seconds", 4)
        is_completed = s.video_status == "completed" and bool(s.video_url)
        if is_completed:
            completed_count += 1
            total_duration += float(dur)

        shot_summaries.append(
            {
                "shot_id": str(s.id),
                "scene_number": s.scene.scene_number,
                "shot_number": s.shot_number,
                "video_url": s.video_url,
                "video_status": s.video_status or "pending",
                "duration_seconds": float(dur),
            }
        )

    # Check active lock
    pid_str = str(project_id)
    if pid_str in _active_compositions:
        return {
            "project_id": pid_str,
            "status": "processing",
            "video_url": None,
            "total_shots": len(shots),
            "composed_shots": completed_count,
            "duration_seconds": total_duration,
            "resolution": "720p",
            "message": "Video composition is currently processing.",
            "shots": shot_summaries,
        }

    # Check persisted metadata
    meta = _read_composition_metadata(project_id)
    if meta:
        video_url = meta.get("video_url")
        # Verify file exists if status is completed
        if meta.get("status") == "completed" and video_url:
            resolved_file = resolve_video_path(video_url)
            if resolved_file.is_file():
                return {
                    "project_id": pid_str,
                    "status": "completed",
                    "video_url": video_url,
                    "total_shots": len(shots),
                    "composed_shots": meta.get("composed_shots", completed_count),
                    "duration_seconds": meta.get("duration_seconds", total_duration),
                    "resolution": meta.get("resolution", "720p"),
                    "message": meta.get("message", "Video composition completed."),
                    "shots": shot_summaries,
                }

        if meta.get("status") == "failed":
            return {
                "project_id": pid_str,
                "status": "failed",
                "video_url": None,
                "total_shots": len(shots),
                "composed_shots": 0,
                "duration_seconds": 0.0,
                "resolution": "720p",
                "message": meta.get("error", "Video composition failed."),
                "shots": shot_summaries,
            }

    # Default initial state
    return {
        "project_id": pid_str,
        "status": "pending",
        "video_url": None,
        "total_shots": len(shots),
        "composed_shots": 0,
        "duration_seconds": 0.0,
        "resolution": "720p",
        "message": "Video composition has not been started.",
        "shots": shot_summaries,
    }


def compose_project_video(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    allow_partial: bool = False,
    force_recompose: bool = False,
) -> dict[str, Any]:
    """
    Concatenate completed shot video clips into one final composed video.
    Clips are strictly ordered by Scene.scene_number and Shot.shot_number.
    """
    _validate_project_access(db, project_id, user_id)
    pid_str = str(project_id)

    # In-flight duplicate prevention
    if pid_str in _active_compositions:
        raise ValueError("Video composition is already in progress for this project.")

    # Collect project shots strictly ordered by Scene and Shot sequence
    shots = (
        db.query(Shot)
        .join(Scene, Shot.scene_id == Scene.id)
        .filter(Shot.project_id == project_id)
        .order_by(Scene.scene_number.asc(), Shot.shot_number.asc())
        .all()
    )

    if not shots:
        raise ValueError("Project has no storyboard scenes or shots to compose.")

    # Separate completed and incomplete shots
    completed_shots = [s for s in shots if s.video_status == "completed" and s.video_url]
    incomplete_shots = [s for s in shots if s.video_status != "completed" or not s.video_url]

    if not allow_partial and incomplete_shots:
        missing_desc = [f"Scene {s.scene.scene_number} Shot {s.shot_number} ({s.video_status})" for s in incomplete_shots[:3]]
        raise ValueError(
            f"Cannot compose full video: {len(incomplete_shots)} of {len(shots)} shots are not completed yet "
            f"({', '.join(missing_desc)}{'...' if len(incomplete_shots) > 3 else ''}). "
            "Please generate all shot videos first, or set allow_partial=True to compose currently available clips."
        )

    if not completed_shots:
        raise ValueError("Cannot compose video: no completed video clips are available for this project.")

    # Check cached composition
    existing_meta = _read_composition_metadata(project_id)
    if existing_meta and existing_meta.get("status") == "completed" and not force_recompose:
        cached_url = existing_meta.get("video_url")
        if cached_url and resolve_video_path(cached_url).is_file():
            # If shot count matches
            if existing_meta.get("composed_shots") == len(completed_shots):
                logger.info("Returning existing completed video composition for %s", project_id)
                return get_project_composition_status(db, project_id, user_id)

    # Validate physical files exist on disk for each clip
    clip_paths: list[Path] = []
    for s in completed_shots:
        assert s.video_url is not None
        clip_path = resolve_video_path(s.video_url)
        if not clip_path.is_file():
            raise ValueError(
                f"Video clip for Scene {s.scene.scene_number} Shot {s.shot_number} was not found on disk at: {clip_path}"
            )
        clip_paths.append(clip_path)

    ffmpeg_exe = get_ffmpeg_path()

    # Mark active in-flight
    _active_compositions.add(pid_str)
    _write_composition_metadata(
        project_id,
        {
            "project_id": pid_str,
            "status": "processing",
            "started_at": datetime.utcnow().isoformat(),
            "total_shots": len(shots),
            "composed_shots": len(completed_shots),
        },
    )

    output_dir = Path("d:/AI-Video-Studio/generated-videos") / pid_str
    output_dir.mkdir(parents=True, exist_ok=True)
    composition_id = uuid.uuid4().hex[:8]
    output_filename = f"composition_{composition_id}.mp4"
    output_path = output_dir / output_filename
    concat_list_path = output_dir / f"concat_list_{composition_id}.txt"

    try:
        # Write concat list with escaped forward slashes
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for p in clip_paths:
                normalized = str(p.resolve()).replace("\\", "/")
                f.write(f"file '{normalized}'\n")

        # Attempt 1: Direct stream copy (fast, zero quality loss, preserves audio)
        copy_cmd = [
            ffmpeg_exe,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list_path),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        logger.info("Executing FFmpeg composition (stream-copy): %s", " ".join(copy_cmd))
        proc = subprocess.run(
            copy_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )

        # Fallback to re-encoding if stream copy fails (e.g. non-matching bitstreams or timestamps)
        if proc.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            logger.warning(
                "Stream-copy concatenation failed (exit code %d), falling back to re-encode. Stderr: %s",
                proc.returncode,
                proc.stderr[:400],
            )
            reencode_cmd = [
                ffmpeg_exe,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list_path),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
            logger.info("Executing FFmpeg composition (re-encode): %s", " ".join(reencode_cmd))
            proc_reencode = subprocess.run(
                reencode_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300,
            )
            if proc_reencode.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
                raise RuntimeError(
                    f"FFmpeg composition failed with exit code {proc_reencode.returncode}: {proc_reencode.stderr[:500]}"
                )

        # Clean up temporary concat list
        if concat_list_path.is_file():
            concat_list_path.unlink()

        output_size = output_path.stat().st_size
        final_url = f"/generated-videos/{pid_str}/{output_filename}"

        from app.utils.r2_storage import is_r2_configured, upload_file
        if is_r2_configured():
            try:
                r2_key = f"videos/{pid_str}/{output_filename}"
                final_url = upload_file(output_path, key=r2_key, content_type="video/mp4")
                try:
                    output_path.unlink()
                except Exception:
                    pass
            except Exception as r2_exc:
                logger.warning("Failed to upload composed video to R2, keeping local fallback: %s", r2_exc)

        total_duration = sum(
            float((s.production_settings or {}).get("duration_seconds", 4))
            for s in completed_shots
        )

        metadata = {
            "project_id": pid_str,
            "status": "completed",
            "video_url": final_url,
            "total_shots": len(shots),
            "composed_shots": len(completed_shots),
            "duration_seconds": total_duration,
            "resolution": "720p",
            "composed_at": datetime.utcnow().isoformat(),
            "output_size_bytes": output_size,
            "allow_partial": allow_partial,
            "message": f"Successfully composed {len(completed_shots)} video clips into full video.",
        }
        _write_composition_metadata(project_id, metadata)
        logger.info("Video composition completed successfully for project %s -> %s", project_id, final_url)
        _active_compositions.discard(pid_str)

        return get_project_composition_status(db, project_id, user_id)

    except Exception as exc:
        logger.error("Video composition error for project %s: %s", project_id, exc)
        _write_composition_metadata(
            project_id,
            {
                "project_id": pid_str,
                "status": "failed",
                "error": str(exc),
                "failed_at": datetime.utcnow().isoformat(),
            },
        )
        raise RuntimeError(f"Video composition failed: {exc}") from exc

    finally:
        _active_compositions.discard(pid_str)
        if concat_list_path.is_file():
            try:
                concat_list_path.unlink()
            except Exception:
                pass
