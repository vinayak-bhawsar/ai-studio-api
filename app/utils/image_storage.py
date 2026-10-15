import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.utils.r2_storage import is_r2_configured, upload_bytes

logger = logging.getLogger(__name__)


def save_generated_image(
    project_id: uuid.UUID | str,
    resource_type: str,
    resource_id: uuid.UUID | str,
    image_bytes: bytes,
    extension: str = "jpg",
) -> str:
    """
    Saves generated image bytes to Cloudflare R2 bucket without local storage.
    If R2 is not configured, falls back to the configured local output directory.
    Returns the public web-accessible URL.
    """
    ext = extension.lstrip(".").lower()
    content_type = "image/png" if ext == "png" else "image/jpeg"
    filename = f"{str(resource_id)}_{uuid.uuid4().hex[:8]}.{ext}"

    if is_r2_configured():
        # Store in R2 under images/{resource_type}/{project_id}/{filename}
        r2_key = f"images/{resource_type}/{str(project_id)}/{filename}"
        public_url = upload_bytes(
            data=image_bytes,
            key=r2_key,
            content_type=content_type,
            metadata={
                "project_id": str(project_id),
                "resource_type": resource_type,
                "resource_id": str(resource_id),
            },
        )
        logger.info("Saved image to R2: %s", public_url)
        return public_url

    # Fallback to local storage only if R2 is not configured
    base_dir = getattr(settings, "IMAGE_GENERATION_OUTPUT_DIR", "generated-images")
    output_dir = Path(base_dir) / resource_type / str(project_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    file_path = output_dir / filename
    file_path.write_bytes(image_bytes)

    return f"/generated-images/{resource_type}/{project_id}/{filename}"
