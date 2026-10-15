import asyncio
from datetime import datetime
from pathlib import Path
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings

from app.models.character import Character
from app.models.environment import Environment
from app.models.project import Project
from app.models.scene import Scene
from app.models.shot import Shot
from app.repository.character_repo import list_characters
from app.repository.environment_repo import list_environments
from app.repository.storyboard_repo import (
    get_scene_by_id,
    get_shot_by_id,
    list_shots_by_project,
)
from app.repository.style_book_repo import get_style_book_by_project
from app.schemas.storyboard import (
    BatchVideoGenerateRequest,
    ProductionSettingsUpdateRequest,
    VideoGenerateRequest,
)
from app.service.external.video_client import VideoClient
from app.utils.video_storage import save_generated_video


def _validate_project_access(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found.")
    if project.user_id != user_id:
        raise PermissionError("Access forbidden to this project.")
    return project


def _load_image_bytes(image_url: str) -> bytes | None:
    """Load local or remote image bytes for reference frame generation."""
    if not image_url or not image_url.strip():
        return None
    url = image_url.strip()

    # Direct file path
    direct_path = Path(url)
    if direct_path.is_file():
        return direct_path.read_bytes()

    # Strip leading slash/backslash
    cleaned = url.lstrip("/\\")
    rel_path = Path(cleaned)
    if rel_path.is_file():
        return rel_path.read_bytes()

    # Check against configured IMAGE_GENERATION_OUTPUT_DIR
    if cleaned.startswith("generated-images"):
        base_dir = getattr(settings, "IMAGE_GENERATION_OUTPUT_DIR", "generated-images")
        sub_path = cleaned[len("generated-images"):].lstrip("/\\")
        cand = Path(base_dir) / sub_path
        if cand.is_file():
            return cand.read_bytes()

    # Remote URL fallback (R2 public URL or external CDN)
    if url.startswith(("http://", "https://")):
        from app.utils.r2_storage import download_bytes_from_url_or_key
        return download_bytes_from_url_or_key(url)

    return None


def get_production_shot_config(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Retrieve production configuration, prerequisites, and status for a shot."""
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    scene = get_scene_by_id(db, shot.scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    env_data = None
    if scene.environment_id:
        env = db.query(Environment).filter(Environment.id == scene.environment_id).first()
        if env:
            env_data = {
                "id": str(env.id),
                "name": env.name,
                "environment_type": env.environment_type,
                "time_of_day": env.time_of_day,
                "reference_images": env.reference_images or [],
            }

    all_chars = list_characters(db, project_id)
    shot_cids = set(str(c) for c in (shot.cast_ids or []))
    cast_list = [
        {
            "id": str(c.id),
            "name": c.name,
            "role": c.role,
            "reference_images": c.reference_images or [],
        }
        for c in all_chars
        if str(c.id) in shot_cids
    ]

    default_settings = {
        "video_model": getattr(settings, "VIDEO_GENERATION_MODEL", "google/veo-3.1-fast"),
        "duration_seconds": 4,
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "fps": 24,
    }
    merged_settings = dict(default_settings)
    if shot.production_settings:
        merged_settings.update(shot.production_settings)

    return {
        "shot_id": str(shot.id),
        "project_id": str(shot.project_id),
        "scene_id": str(shot.scene_id),
        "shot_number": shot.shot_number,
        "start_frame_url": shot.start_frame_url,
        "end_frame_url": shot.end_frame_url,
        "video_url": shot.video_url,
        "video_status": shot.video_status or "pending",
        "production_settings": merged_settings,
        "has_start_frame": bool(shot.start_frame_url),
        "cast": cast_list,
        "environment": env_data,
    }


def update_production_shot_config(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProductionSettingsUpdateRequest,
) -> dict[str, Any]:
    """Update production shot settings such as resolution, duration, aspect ratio, motion."""
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    current_settings = dict(shot.production_settings or {})
    update_data = payload.model_dump(exclude_unset=True)

    # Validate model bounds
    if "duration_seconds" in update_data and update_data["duration_seconds"] is not None:
        dur = update_data["duration_seconds"]
        if dur not in (4, 5, 6, 8):
            raise ValueError(f"Unsupported duration {dur}s. Supported durations are 4, 5, 6, 8 seconds.")

    if "resolution" in update_data and update_data["resolution"] is not None:
        res = update_data["resolution"]
        if res != "720p":
            raise ValueError(f"Unsupported resolution '{res}'. Only '720p' is supported.")

    if "aspect_ratio" in update_data and update_data["aspect_ratio"] is not None:
        ar = update_data["aspect_ratio"]
        if ar not in ("16:9", "9:16", "1:1"):
            raise ValueError(f"Unsupported aspect ratio '{ar}'. Supported are '16:9', '9:16', '1:1'.")

    current_settings.update(update_data)
    shot.production_settings = current_settings
    db.commit()
    db.refresh(shot)

    return get_production_shot_config(db, project_id, shot_id, user_id)


def get_production_studio_status(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Return overview of project production studio video generations."""
    _validate_project_access(db, project_id, user_id)
    shots = list_shots_by_project(db, project_id)

    completed = sum(1 for s in shots if s.video_status == "completed")
    generating = sum(1 for s in shots if s.video_status == "generating")
    pending = sum(1 for s in shots if s.video_status in ("pending", None))
    failed = sum(1 for s in shots if s.video_status == "failed")

    shot_summaries = [
        {
            "shot_id": str(s.id),
            "scene_id": str(s.scene_id),
            "shot_number": s.shot_number,
            "description": s.description[:80],
            "start_frame_url": s.start_frame_url,
            "video_url": s.video_url,
            "video_status": s.video_status or "pending",
        }
        for s in shots
    ]

    from app.service.composition_service import get_project_composition_status
    comp_data = None
    try:
        comp_data = get_project_composition_status(db, project_id, user_id)
    except Exception:
        pass

    return {
        "project_id": str(project_id),
        "total_shots": len(shots),
        "completed_videos": completed,
        "generating_videos": generating,
        "pending_videos": pending,
        "failed_videos": failed,
        "shots": shot_summaries,
        "composition": comp_data,
    }


def build_video_prompt(
    shot: Shot,
    scene: Scene,
    environment: Environment | None = None,
    cast_characters: list[Character] | None = None,
    style_context: str = "",
    instructions: str | None = None,
    content_format: str | None = None,
    visual_context: Any = None,
) -> str:
    """Build a prompt for Veo video generation combining all story elements and matching content format."""
    parts = []

    # Check for prompt override in production settings
    settings_dict = shot.production_settings or {}
    override = settings_dict.get("prompt_override")
    if override and override.strip():
        return override.strip()

    # Determine format header (film, story, documentary, product, reel, etc.)
    fmt = (content_format or "").strip().lower()
    style_lower = (style_context or "").strip().lower()

    if "documentary" in fmt or "documentary" in style_lower:
        parts.append(f"Documentary footage, Scene Shot {shot.shot_number} of {scene.heading}.")
    elif "product" in fmt or "commercial" in fmt or "advertisement" in fmt:
        parts.append(f"Product showcase, Scene Shot {shot.shot_number} of {scene.heading}.")
    elif "reel" in fmt or "social" in fmt:
        parts.append(f"Vertical dynamic scene, Shot {shot.shot_number} of {scene.heading}.")
    else:
        parts.append(f"Scene: Shot {shot.shot_number} of {scene.heading}.")

    if scene.time_of_day:
        parts.append(f"Time of day: {scene.time_of_day}.")

    parts.append(f"Action: {shot.description}.")
    if shot.action:
        parts.append(f"Subject motion: {shot.action}.")

    framing_elements = []
    if shot.camera_framing:
        framing_elements.append(f"Framing: {shot.camera_framing}")
    if shot.camera_movement:
        framing_elements.append(f"Camera movement: {shot.camera_movement}")
    if shot.camera_angle:
        framing_elements.append(f"Camera angle: {shot.camera_angle}")
    if shot.composition:
        framing_elements.append(f"Composition: {shot.composition}")
    if framing_elements:
        parts.append(", ".join(framing_elements) + ".")

    if environment:
        parts.append(
            f"Environment location: {environment.name}. "
            f"Architecture: {environment.architecture}. "
            f"Lighting: {environment.lighting}. "
            f"Atmosphere: {environment.atmosphere}."
        )

    if cast_characters:
        from app.service.character_identity_service import build_consistent_character_prompt_block
        char_prompt, _ = build_consistent_character_prompt_block(
            characters=cast_characters,
            shot=shot,
            is_end_frame=False,
        )
        if char_prompt:
            parts.append(char_prompt)

    if visual_context:
        if getattr(visual_context, "cultural_or_regional_context", None):
            parts.append(f"Cultural/world setting: {visual_context.cultural_or_regional_context}.")
        if getattr(visual_context, "clothing_and_styling", None):
            parts.append(f"Wardrobe & styling: {visual_context.clothing_and_styling}.")
        if getattr(visual_context, "negative_constraints", None):
            parts.append(f"Avoid: {', '.join(visual_context.negative_constraints)}.")

    if style_context:
        parts.append(f"Visual aesthetic: {style_context}.")

    if instructions and instructions.strip():
        parts.append(f"Director notes: {instructions.strip()}.")

    # Adapt quality and motion tokens based on visual style rather than forcing film grain
    if any(k in style_lower for k in ["anime", "cartoon", "animation", "2d", "3d", "cel"]):
        parts.append(
            "Fluid animation, expressive character motion, vivid color palette, smooth clean rendering."
        )
    elif "documentary" in style_lower or "documentary" in fmt:
        parts.append(
            "Authentic high-definition footage, natural lighting, clear realistic details, smooth camera work."
        )
    elif "reel" in style_lower or "reel" in fmt:
        parts.append(
            "Vibrant modern high-definition video, crisp lighting, dynamic motion, clear focal subjects."
        )
    else:
        parts.append(
            "High quality video capture, natural physics and fluid motion, atmospheric lighting, professional color grading."
        )

    return " ".join(parts)


async def generate_shot_video(
    db: Session,
    project_id: uuid.UUID,
    shot_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: VideoGenerateRequest | None = None,
    video_client: VideoClient | None = None,
) -> dict[str, Any]:
    """
    Generate video for a shot using Google Veo VideoClient.
    Validates ownership, prerequisites, tracks status, saves asset, and updates database.
    """
    _validate_project_access(db, project_id, user_id)
    shot = get_shot_by_id(db, shot_id, project_id)
    if not shot:
        raise ValueError("Shot not found.")

    scene = get_scene_by_id(db, shot.scene_id, project_id)
    if not scene:
        raise ValueError("Scene not found.")

    req = payload or VideoGenerateRequest()

    # Load start frame bytes if available
    start_frame_bytes = None
    if shot.start_frame_url:
        start_frame_bytes = _load_image_bytes(shot.start_frame_url)

    # Validate start frame prerequisite if required
    if req.require_start_frame and not start_frame_bytes:
        raise ValueError(
            "Start frame is required before generating video for this shot. Generate a start frame first."
        )

    # Check duplicate generation
    if shot.video_status == "completed" and shot.video_url and not req.force_regenerate:
        dur = (shot.production_settings or {}).get("duration_seconds", 4)
        return {
            "shot_id": str(shot.id),
            "video_url": shot.video_url,
            "status": "skipped",
            "duration_seconds": dur,
            "message": "Video has already been generated. Use force_regenerate to overwrite.",
        }

    # In-flight duplicate prevention
    if shot.video_status == "generating" and not req.force_regenerate:
        raise ValueError("Video generation is currently in progress for this shot.")

    # Determine settings
    prod_settings = dict(shot.production_settings or {})
    duration = req.duration_seconds or prod_settings.get("duration_seconds", 4)
    resolution = req.resolution or prod_settings.get("resolution", "720p")
    if resolution != "720p":
        raise ValueError(f"Unsupported resolution '{resolution}'. Only '720p' is supported.")
    aspect_ratio = req.aspect_ratio or prod_settings.get("aspect_ratio", "16:9")

    # Gather environment and cast context
    environment = (
        db.query(Environment).filter(Environment.id == scene.environment_id).first()
        if scene.environment_id
        else None
    )

    all_chars = list_characters(db, project_id)
    from app.service.character_identity_service import resolve_shot_active_characters
    cast_characters = resolve_shot_active_characters(shot, scene, all_chars)
    if cast_characters:
        shot.cast_ids = [str(c.id) for c in cast_characters]

    style_book = get_style_book_by_project(db, project_id)
    style_context = ""
    if style_book and style_book.content:
        content = style_book.content
        if isinstance(content, dict):
            aesthetic = content.get("aesthetic", {})
            style_context = aesthetic.get("preset", "")

    from app.service.visual_context_service import resolve_project_visual_context
    visual_context = resolve_project_visual_context(db, project_id)

    prompt = build_video_prompt(
        shot=shot,
        scene=scene,
        environment=environment,
        cast_characters=cast_characters,
        style_context=style_context,
        instructions=req.instructions,
        visual_context=visual_context,
    )

    client = video_client or VideoClient()

    # Set status to generating
    shot.video_status = "generating"
    db.commit()

    try:
        generated_video = await client.generate_video(
            prompt=prompt,
            start_frame_bytes=start_frame_bytes,
            duration_seconds=duration,
            resolution=resolution,
            aspect_ratio=aspect_ratio,
        )

        saved_url = save_generated_video(
            project_id=project_id,
            shot_id=shot.id,
            video_bytes=generated_video.data,
            extension="mp4",
        )

        shot.video_url = saved_url
        shot.video_status = "completed"

        # Update metadata
        current_meta = dict(shot.asset_metadata or {})
        current_meta["video"] = {
            "url": saved_url,
            "model": client.model,
            "duration_seconds": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "prompt": prompt,
            "has_start_frame": bool(start_frame_bytes),
            "generated_at": datetime.utcnow().isoformat(),
        }
        shot.asset_metadata = current_meta
        db.commit()
        db.refresh(shot)

        return {
            "shot_id": str(shot.id),
            "video_url": saved_url,
            "status": "completed",
            "duration_seconds": duration,
            "message": "Video generated successfully.",
        }

    except Exception as exc:
        shot.video_status = "failed"
        db.commit()
        raise RuntimeError(f"Video generation failed: {exc}") from exc


async def generate_batch_videos(
    db: Session,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: BatchVideoGenerateRequest | None = None,
    video_client: VideoClient | None = None,
) -> dict[str, Any]:
    """Batch generate videos for storyboard shots with bounded concurrency."""
    _validate_project_access(db, project_id, user_id)
    req = payload or BatchVideoGenerateRequest()

    all_shots = (
        db.query(Shot)
        .filter(Shot.project_id == project_id)
        .order_by(Shot.scene_id.asc(), Shot.shot_number.asc())
        .all()
    )
    if not all_shots:
        raise ValueError("No shots found for this project. Generate storyboard first.")

    target_shots = all_shots
    if req.shot_ids:
        target_ids = {str(sid) for sid in req.shot_ids}
        target_shots = [s for s in all_shots if str(s.id) in target_ids]
        if not target_shots:
            raise ValueError("No matching shots found for the provided shot IDs.")

    semaphore = asyncio.Semaphore(2)

    async def _process_shot(sh: Shot):
        async with semaphore:
            single_req = VideoGenerateRequest(
                force_regenerate=req.force_regenerate,
                duration_seconds=req.duration_seconds,
                resolution=req.resolution,
                aspect_ratio=req.aspect_ratio,
                require_start_frame=req.require_start_frame,
            )
            try:
                return await generate_shot_video(
                    db=db,
                    project_id=project_id,
                    shot_id=sh.id,
                    user_id=user_id,
                    payload=single_req,
                    video_client=video_client,
                )
            except Exception as exc:
                return {
                    "shot_id": str(sh.id),
                    "video_url": None,
                    "status": "failed",
                    "duration_seconds": 4,
                    "message": str(exc),
                }

    tasks = [_process_shot(sh) for sh in target_shots]
    results = await asyncio.gather(*tasks)

    completed = sum(1 for r in results if r["status"] == "completed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "total": len(results),
        "completed": completed,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }
