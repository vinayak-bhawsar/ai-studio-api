from __future__ import annotations

import logging
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.character import Character
from app.models.scene import Scene
from app.models.shot import Shot
from app.repository.character_repo import list_characters

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalCharacterIdentity:
    character_id: str
    name: str
    role: str
    age: str
    appearance: str
    canonical_reference_url: str | None
    face_structure: str
    eyes: str
    hair: str
    skin_tone: str
    facial_hair: str
    wardrobe: str
    visual_style: str
    identity_anchor: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_trait(text: str, keywords: list[str], default: str) -> str:
    """Extract a descriptive phrase matching keywords or fallback to default."""
    if not text:
        return default
    text_lower = text.lower()
    for kw in keywords:
        if kw in text_lower:
            return text.strip()
    return default


def build_canonical_character_identity(character: Character) -> CanonicalCharacterIdentity:
    """
    Establish a structured, stable canonical identity representation for a character.
    Extracts stable facial features, age appearance, hair, skin tone, and authentic styling,
    separating immutable identity traits from transient shot-specific expressions/poses.
    """
    char_id_str = str(character.id)
    canonical_url = character.reference_images[0] if (character.reference_images and len(character.reference_images) > 0) else None

    appearance = character.appearance or ""
    role = character.role or "character"
    age = character.age or "adult"
    wardrobe = character.wardrobe or ""
    visual_style = character.visual_style or ""

    # Synthesize stable facial features
    app_lower = appearance.lower()
    
    # Hair analysis
    hair_desc = "neatly styled natural hair"
    if "dark hair" in app_lower or "black hair" in app_lower:
        hair_desc = "dark black hair, neatly styled"
    elif "blonde" in app_lower or "blond" in app_lower:
        hair_desc = "golden blonde hair"
    elif "brown hair" in app_lower:
        hair_desc = "rich brown hair"
    elif "grey" in app_lower or "gray" in app_lower:
        hair_desc = "distinguished silver-grey hair"
    elif "long" in app_lower:
        hair_desc = "long, well-groomed dark hair"
    elif "short" in app_lower:
        hair_desc = "short, well-groomed dark hair"

    # Eyes analysis
    eyes_desc = "expressive eyes"
    if "brown eyes" in app_lower:
        eyes_desc = "piercing deep brown eyes"
    elif "dark eyes" in app_lower:
        eyes_desc = "striking dark eyes"
    elif "hazel" in app_lower:
        eyes_desc = "warm hazel eyes"
    elif "blue" in app_lower:
        eyes_desc = "clear blue eyes"
    elif "green" in app_lower:
        eyes_desc = "vivid green eyes"

    # Face & Skin tone
    face_desc = "defined facial structure"
    if "chiseled" in app_lower or "strong jawline" in app_lower:
        face_desc = "strong defined jawline, chiseled cheekbones"
    elif "kind face" in app_lower or "gentle" in app_lower:
        face_desc = "elegant gentle facial features, graceful jawline"
    elif "commanding" in app_lower or "dignified" in app_lower:
        face_desc = "dignified regal countenance, mature defined facial structure"

    skin_desc = "natural skin tone"
    if "olive" in app_lower:
        skin_desc = "warm olive skin tone"
    elif "fair" in app_lower:
        skin_desc = "fair radiant complexion"
    elif "tan" in app_lower or "golden" in app_lower:
        skin_desc = "warm golden skin tone"
    elif "deep" in app_lower or "dark" in app_lower:
        skin_desc = "rich deep skin tone"

    # Facial hair
    facial_hair_desc = "clean-shaven"
    if "mustache" in app_lower and "beard" in app_lower:
        facial_hair_desc = "neatly trimmed black mustache and beard"
    elif "beard" in app_lower:
        facial_hair_desc = "groomed black beard"
    elif "mustache" in app_lower:
        facial_hair_desc = "groomed dark mustache"
    elif any(k in character.name.lower() or k in role.lower() for k in ["queen", "princess", "rajkumari", "maharani", "woman", "girl", "female"]):
        facial_hair_desc = "smooth radiant skin"

    # Assemble stable identity anchor string
    anchor_parts = [
        f"Consistent character likeness of {character.name}",
        f"Role: {role}",
        f"Age appearance: {age}",
        f"Face: {face_desc}, {eyes_desc}, {hair_desc}, {skin_desc}",
    ]
    if facial_hair_desc and facial_hair_desc != "clean-shaven":
        anchor_parts.append(f"Facial hair: {facial_hair_desc}")
    if wardrobe:
        anchor_parts.append(f"Authentic wardrobe: {wardrobe}")
    if visual_style:
        anchor_parts.append(f"Styling aesthetic: {visual_style}")

    anchor_str = ". ".join(anchor_parts) + "."

    return CanonicalCharacterIdentity(
        character_id=char_id_str,
        name=character.name,
        role=role,
        age=age,
        appearance=appearance,
        canonical_reference_url=canonical_url,
        face_structure=face_desc,
        eyes=eyes_desc,
        hair=hair_desc,
        skin_tone=skin_desc,
        facial_hair=facial_hair_desc,
        wardrobe=wardrobe,
        visual_style=visual_style,
        identity_anchor=anchor_str,
    )


def resolve_shot_active_characters(
    shot: Shot,
    scene: Scene,
    all_characters: list[Character],
) -> list[Character]:
    """
    Intelligently determine which characters are actually active/focal in this specific shot.
    Prevents 'cast pollution' where all scene characters are dumped into a single-person close-up.
    Considers:
    1. Dialogue speaker(s) in this shot.
    2. Character names mentioned in shot.description or shot.action.
    3. Camera framing constraints (Close-Up vs Two-Shot vs Wide Shot).
    4. Fallback to shot.cast_ids or scene primary characters.
    """
    char_by_name = {c.name.strip().lower(): c for c in all_characters}
    char_by_id = {str(c.id): c for c in all_characters}

    # 1. Dialogue speakers in this shot
    shot_meta = shot.asset_metadata or {}
    diags = shot_meta.get("dialogues", [])
    speaker_names = [d.get("character_name", "").strip().lower() for d in diags if d.get("character_name")]

    active_chars: list[Character] = []
    for sname in speaker_names:
        c = char_by_name.get(sname)
        if c and c not in active_chars:
            active_chars.append(c)

    # 2. Character names mentioned in description or action
    full_text = f"{shot.description or ''} {shot.action or ''}".lower()
    for cname, c in char_by_name.items():
        # Match whole word
        pattern = r"\b" + re.escape(cname) + r"\b"
        if re.search(pattern, full_text):
            if c not in active_chars:
                active_chars.append(c)

    # 3. Framing-based filtering
    framing = (shot.camera_framing or "").lower()
    desc_lower = (shot.description or "").lower()
    is_closeup = any(k in framing for k in ["close-up", "extreme close-up", "macro", "single"]) or "close-up" in desc_lower
    is_two_shot = "two-shot" in framing or "two-shot" in desc_lower or "2-shot" in framing or "over-the-shoulder" in framing or "over-the-shoulder" in desc_lower

    if is_closeup and active_chars:
        # For a close-up, retain only the primary focal character (the speaker or first mentioned)
        return active_chars[:1]

    if is_two_shot and len(active_chars) > 2:
        return active_chars[:2]

    # If active characters were found via dialogue/text, return them
    if active_chars:
        if is_two_shot and len(active_chars) < 2 and shot.cast_ids:
            # Try to add second cast member for two-shot
            for cid in shot.cast_ids:
                c = char_by_id.get(str(cid))
                if c and c not in active_chars:
                    active_chars.append(c)
                    if len(active_chars) >= 2:
                        break
        return active_chars

    # 4. Fallback: Check shot.cast_ids if explicitly assigned
    if shot.cast_ids:
        shot_cids = [str(cid) for cid in shot.cast_ids]
        matching = [char_by_id[cid] for cid in shot_cids if cid in char_by_id]
        if matching:
            if is_closeup:
                return matching[:1]
            if is_two_shot:
                return matching[:2]
            return matching

    # 5. Fallback: Check scene.cast_ids
    if scene.cast_ids:
        scene_cids = [str(cid) for cid in scene.cast_ids]
        matching = [char_by_id[cid] for cid in scene_cids if cid in char_by_id]
        if matching:
            if is_closeup:
                return matching[:1]
            if is_two_shot:
                return matching[:2]
            return matching

    return all_characters[:1] if all_characters else []


def build_consistent_character_prompt_block(
    characters: list[Character],
    shot: Shot,
    is_end_frame: bool = False,
    start_frame_url: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Format a clear, consistent prompt block describing the characters in this shot.
    Ensures identical facial structure descriptors are reused across all shots.
    If 2+ characters are present, explicitly establishes spatial separation to avoid
    facial feature mingling or attribute swapping.
    """
    if not characters:
        return "", []

    identities = [build_canonical_character_identity(c) for c in characters]
    identity_dicts = [i.to_dict() for i in identities]

    if len(identities) == 1:
        ident = identities[0]
        prompt = (
            f"Focal Subject: {ident.name} ({ident.role}). "
            f"Distinctive appearance: {ident.appearance}. "
            f"Exact facial appearance: {ident.face_structure}, {ident.eyes}, {ident.hair}, {ident.skin_tone}. "
            f"Facial hair: {ident.facial_hair}. "
            f"Age: {ident.age}. "
            f"Wardrobe: {ident.wardrobe}. "
            f"Visual style: {ident.visual_style}. "
            f"Identity requirement: Precise recognizable character likeness matching canonical portrait, natural expressive facial features."
        )
        if is_end_frame and start_frame_url:
            prompt += f" Continuous shot: Identical face, hair, and wardrobe matching shot {shot.shot_number} start frame."
        return prompt, identity_dicts

    # Multiple characters: establish clear spatial framing
    parts = [f"Scene features {len(identities)} distinct characters:"]
    positions = ["on the left", "on the right", "in the center", "in the foreground"]
    
    for idx, ident in enumerate(identities):
        pos = positions[idx % len(positions)]
        parts.append(
            f"Character {idx + 1} ({pos}): {ident.name} ({ident.role}) - "
            f"Appearance: {ident.appearance}. "
            f"Face: {ident.face_structure}, {ident.eyes}, {ident.hair}, {ident.skin_tone}. "
            f"Wardrobe: {ident.wardrobe}."
        )

    parts.append(
        "Strict identity requirement: Completely distinct individual faces and character identities. "
        "Do NOT blend, combine, or swap facial features or clothing between characters."
    )

    if is_end_frame and start_frame_url:
        parts.append(f"Continuous shot: Identical character likenesses and costumes matching shot {shot.shot_number} start frame.")

    return " ".join(parts), identity_dicts


def load_canonical_reference_bytes(
    character: Character,
    project_id: uuid.UUID,
) -> tuple[bytes | None, str | None]:
    """
    Load the binary data and MIME type of the character's approved canonical portrait image.
    Supports both remote R2/HTTP URLs and local relative paths.
    """
    if not character.reference_images:
        return None, None

    primary_url = character.reference_images[0]
    if not primary_url:
        return None, None

    clean_url = primary_url.strip()

    # Remote URL (Cloudflare R2 or external CDN)
    if clean_url.startswith(("http://", "https://")):
        from app.utils.r2_storage import download_bytes_from_url_or_key
        data = download_bytes_from_url_or_key(clean_url)
        if data:
            mime = "image/png" if clean_url.lower().endswith(".png") else "image/jpeg"
            return data, mime

    # Handle local relative URL: /generated-images/characters/{project_id}/{filename}
    clean_path = clean_url.lstrip("/")
    local_path = Path(clean_path)
    if not local_path.exists():
        # Try relative to storage root
        from app.core.config import settings
        storage_root = Path(getattr(settings, "IMAGE_GENERATION_OUTPUT_DIR", "generated-images"))
        candidate = storage_root / "characters" / str(project_id) / Path(clean_path).name
        if candidate.exists():
            local_path = candidate

    if local_path.exists() and local_path.is_file():
        try:
            data = local_path.read_bytes()
            mime = "image/png" if local_path.suffix.lower() == ".png" else "image/jpeg"
            return data, mime
        except Exception as exc:
            logger.warning("Could not read canonical reference file %s: %s", local_path, exc)

    return None, None
