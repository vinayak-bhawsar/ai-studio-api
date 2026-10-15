import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.utils.r2_storage import is_r2_configured, upload_bytes

logger = logging.getLogger(__name__)


def save_generated_video(
    project_id: uuid.UUID | str,
    shot_id: uuid.UUID | str,
    video_bytes: bytes,
    extension: str = "mp4",
) -> str:
    """
    Saves generated video bytes directly to Cloudflare R2 bucket without local storage.
    If R2 is not configured, falls back to the configured local output directory.
    Returns the public web-accessible URL.
    """
    ext = extension.lstrip(".").lower()
    content_type = "video/mp4" if ext == "mp4" else "application/octet-stream"
    filename = f"{str(shot_id)}_{uuid.uuid4().hex[:8]}.{ext}"

    if is_r2_configured():
        # Store in R2 under videos/{project_id}/{filename}
        r2_key = f"videos/{str(project_id)}/{filename}"
        public_url = upload_bytes(
            data=video_bytes,
            key=r2_key,
            content_type=content_type,
            metadata={
                "project_id": str(project_id),
                "shot_id": str(shot_id),
            },
        )
        logger.info("Saved video scene to R2: %s", public_url)
        return public_url

    # Fallback to local storage only if R2 is not configured
    base_dir = getattr(settings, "VIDEO_GENERATION_OUTPUT_DIR", "generated-videos")
    output_dir = Path(base_dir) / str(project_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / filename
    file_path.write_bytes(video_bytes)

    return f"/generated-videos/{project_id}/{filename}"
