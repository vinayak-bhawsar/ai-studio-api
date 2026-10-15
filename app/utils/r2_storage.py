import logging
import mimetypes
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from app.core.config import settings

logger = logging.getLogger(__name__)

_s3_client = None


def is_r2_configured() -> bool:
    """Check if Cloudflare R2 credentials and bucket are configured."""
    return bool(
        getattr(settings, "R2_ACCESS_KEY_ID", None)
        and getattr(settings, "R2_SECRET_ACCESS_KEY", None)
        and getattr(settings, "R2_ENDPOINT", None)
        and getattr(settings, "R2_BUCKET", None)
    )


def get_r2_client():
    """Returns a singleton boto3 S3 client configured for Cloudflare R2."""
    global _s3_client
    if _s3_client is None:
        if not is_r2_configured():
            raise RuntimeError(
                "Cloudflare R2 is not configured. Please set R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, R2_ENDPOINT, and R2_BUCKET in your environment."
            )
        _s3_client = boto3.client(
            service_name="s3",
            endpoint_url=settings.R2_ENDPOINT,
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
    return _s3_client


def _build_full_key(key: str) -> str:
    """Prepend R2_PREFIX if configured and not already included."""
    clean_key = key.lstrip("/")
    prefix = getattr(settings, "R2_PREFIX", "").strip("/")
    if prefix and not clean_key.startswith(f"{prefix}/"):
        return f"{prefix}/{clean_key}"
    return clean_key


def _build_public_url(full_key: str) -> str:
    """Build the public CDN/R2 URL for a given storage key."""
    public_base = getattr(settings, "R2_PUBLIC_URL", "").rstrip("/")
    if public_base:
        return f"{public_base}/{full_key}"
    # Fallback if no public URL domain configured
    endpoint = settings.R2_ENDPOINT.rstrip("/")
    bucket = settings.R2_BUCKET
    return f"{endpoint}/{bucket}/{full_key}"


def upload_bytes(
    data: bytes,
    key: str,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """
    Upload raw bytes directly to Cloudflare R2 bucket.
    Returns the public web-accessible URL.
    """
    client = get_r2_client()
    full_key = _build_full_key(key)

    if not content_type:
        content_type, _ = mimetypes.guess_type(full_key)
        if not content_type:
            if full_key.endswith(".jpg") or full_key.endswith(".jpeg"):
                content_type = "image/jpeg"
            elif full_key.endswith(".png"):
                content_type = "image/png"
            elif full_key.endswith(".mp4"):
                content_type = "video/mp4"
            elif full_key.endswith(".mp3"):
                content_type = "audio/mpeg"
            elif full_key.endswith(".wav"):
                content_type = "audio/wav"
            else:
                content_type = "application/octet-stream"

    extra_args: dict[str, Any] = {
        "ContentType": content_type,
    }
    if metadata:
        extra_args["Metadata"] = metadata

    try:
        client.put_object(
            Bucket=settings.R2_BUCKET,
            Key=full_key,
            Body=data,
            **extra_args,
        )
        public_url = _build_public_url(full_key)
        logger.info("Uploaded %d bytes to R2: %s -> %s", len(data), full_key, public_url)
        return public_url
    except Exception as exc:
        logger.error("Failed to upload bytes to R2 (%s): %s", full_key, exc)
        raise RuntimeError(f"Cloudflare R2 upload error for key '{full_key}': {exc}") from exc


def upload_file(
    file_path: Path | str,
    key: str,
    content_type: str | None = None,
) -> str:
    """
    Upload a local file directly to Cloudflare R2 bucket.
    Returns the public web-accessible URL.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"File to upload to R2 not found: {path}")

    data = path.read_bytes()
    return upload_bytes(data=data, key=key, content_type=content_type)


def download_bytes_from_url_or_key(url_or_key: str) -> bytes | None:
    """
    Download raw bytes given an R2 public URL, http URL, or object key.
    """
    if not url_or_key or not url_or_key.strip():
        return None

    target = url_or_key.strip()

    # If it's a full HTTP/HTTPS URL
    if target.startswith(("http://", "https://")):
        try:
            import httpx
            with httpx.Client(timeout=30.0, follow_redirects=True) as http_client:
                resp = http_client.get(target)
                if resp.status_code == 200:
                    return resp.content
                logger.warning("HTTP fetch returned %d for %s", resp.status_code, target)
        except Exception as exc:
            logger.warning("HTTP download error for %s: %s", target, exc)

        # Fallback to S3 get_object by extracting key if belongs to public domain
        public_base = getattr(settings, "R2_PUBLIC_URL", "").rstrip("/")
        if public_base and target.startswith(public_base):
            key = target[len(public_base):].lstrip("/")
            return download_bytes_by_key(key)

        return None

    # Treat as direct storage key
    return download_bytes_by_key(target)


def download_bytes_by_key(key: str) -> bytes | None:
    """Download object bytes directly from R2 using S3 API."""
    try:
        client = get_r2_client()
        full_key = _build_full_key(key)
        resp = client.get_object(Bucket=settings.R2_BUCKET, Key=full_key)
        return resp["Body"].read()
    except Exception as exc:
        logger.warning("R2 direct key download error for %s: %s", key, exc)
        return None


def download_to_temp_file(url_or_key: str, suffix: str | None = None) -> Path:
    """
    Download remote R2 file to a temporary file on disk (useful for FFmpeg processing).
    Returns the Path to the temporary file. Caller is responsible for cleanup when done.
    """
    data = download_bytes_from_url_or_key(url_or_key)
    if not data:
        raise ValueError(f"Could not download content for media URL/key: {url_or_key}")

    if not suffix:
        parsed = urllib.parse.urlparse(url_or_key)
        suffix = Path(parsed.path).suffix or ".tmp"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        temp_file.write(data)
        temp_file.flush()
    finally:
        temp_file.close()

    return Path(temp_file.name)
