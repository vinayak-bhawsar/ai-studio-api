from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.utils.retry import RetryConfig, wait_before_retry


@dataclass(frozen=True)
class GeneratedVideo:
    data: bytes
    mime_type: str = "video/mp4"
    duration_seconds: int = 4


class VideoClient:
    """
    Video generation client supporting Cloudflare Workers AI (google/veo-3.1-fast)
    and Google GenAI as a fallback if configured.
    """

    def __init__(self, retry_config: RetryConfig | None = None) -> None:
        self.account_id = self._get_account_id()
        self.cloudflare_token = self._get_cloudflare_token()

        model_name = getattr(
            settings,
            "VIDEO_GENERATION_MODEL",
            "google/veo-3.1-fast",
        )
        if model_name in ("veo-3.1-fast-generate-preview", "veo-3.1-lite-generate-preview"):
            model_name = "google/veo-3.1-fast"

        self.model = model_name
        self.gemini_api_key = getattr(settings, "GEMINI_API_KEY", None)

        self.retry_config = retry_config or RetryConfig(
            max_attempts=3,
            initial_delay_seconds=1.0,
            max_delay_seconds=6.0,
            backoff_multiplier=2.0,
        )

    def _get_account_id(self) -> str | None:
        acc = (
            getattr(settings, "CLOUDFLARE_VIDEO_ACCOUNT_ID", None)
            or os.environ.get("CLOUDFLARE_VIDEO_ACCOUNT_ID")
            or getattr(settings, "CLOUDFLARE_IMAGE_ACCOUNT_ID", None)
            or os.environ.get("CLOUDFLARE_IMAGE_ACCOUNT_ID")
            or getattr(settings, "CLOUDFLARE_ACCOUNT_ID", None)
            or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        )
        if not acc or not str(acc).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                acc = (
                    env_vals.get("CLOUDFLARE_VIDEO_ACCOUNT_ID")
                    or env_vals.get("CLOUDFLARE_IMAGE_ACCOUNT_ID")
                    or env_vals.get("CLOUDFLARE_ACCOUNT_ID")
                )
            except Exception:
                pass
        return str(acc).strip() if acc else None

    def _get_cloudflare_token(self) -> str | None:
        token = (
            getattr(settings, "CLOUDFLARE_VIDEO_API_TOKEN", None)
            or os.environ.get("CLOUDFLARE_VIDEO_API_TOKEN")
            or getattr(settings, "CLOUDFLARE_API_TOKEN", None)
            or os.environ.get("CLOUDFLARE_API_TOKEN")
        )
        if not token or not str(token).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                token = env_vals.get("CLOUDFLARE_VIDEO_API_TOKEN") or env_vals.get("CLOUDFLARE_API_TOKEN")
            except Exception:
                pass
        return str(token).strip() if token else None

    def _is_cloudflare_provider(self) -> bool:
        if self.model.startswith("google/") or self.model.startswith("@cf/"):
            return True
        tok = self._get_cloudflare_token()
        if tok and tok.startswith("cfut_"):
            return True
        provider = getattr(settings, "LLM_PROVIDER", "").lower()
        return provider == "cloudflare"

    async def generate_video(
        self,
        prompt: str,
        start_frame_bytes: bytes | None = None,
        duration_seconds: int = 4,
        resolution: str = "720p",
        aspect_ratio: str = "16:9",
        timeout: float = 300.0,
        poll_interval: float = 5.0,
    ) -> GeneratedVideo:
        """
        Generate a video from a prompt (and optional start frame image).
        Restricted to 720p resolution.
        """
        if not prompt or not prompt.strip():
            raise ValueError("Video generation prompt cannot be empty.")

        if duration_seconds not in (4, 5, 6, 8):
            duration_seconds = 4

        if resolution != "720p":
            raise ValueError(f"Unsupported resolution '{resolution}'. Only '720p' is supported.")

        if aspect_ratio not in ("16:9", "9:16", "1:1"):
            aspect_ratio = "16:9"

        if self._is_cloudflare_provider():
            return await self._generate_cloudflare_video(
                prompt=prompt.strip(),
                start_frame_bytes=start_frame_bytes,
                duration_seconds=duration_seconds,
                resolution="720p",
                aspect_ratio=aspect_ratio,
                timeout=timeout,
                poll_interval=poll_interval,
            )
        else:
            return await self._generate_google_video(
                prompt=prompt.strip(),
                start_frame_bytes=start_frame_bytes,
                duration_seconds=duration_seconds,
                resolution="720p",
                aspect_ratio=aspect_ratio,
                timeout=timeout,
                poll_interval=poll_interval,
            )

    async def _generate_cloudflare_video(
        self,
        prompt: str,
        start_frame_bytes: bytes | None,
        duration_seconds: int,
        resolution: str,
        aspect_ratio: str,
        timeout: float,
        poll_interval: float,
    ) -> GeneratedVideo:
        account_id = self._get_account_id()
        token = self._get_cloudflare_token()

        if not account_id:
            raise RuntimeError(
                "CLOUDFLARE_VIDEO_ACCOUNT_ID or CLOUDFLARE_ACCOUNT_ID is required for Cloudflare Workers AI video generation."
            )
        if not token:
            raise RuntimeError(
                "CLOUDFLARE_VIDEO_API_TOKEN or CLOUDFLARE_API_TOKEN is required for Cloudflare Workers AI video generation."
            )

        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Safe diagnostic logging (no secrets logged)
        masked_acc = f"{account_id[:4]}...{account_id[-4:]}" if len(account_id) > 8 else "configured"
        print(f"[VideoClient] Provider: Cloudflare Workers AI | Model: {self.model} | Account: {masked_acc} | Token configured: True")

        dur_str = f"{duration_seconds}s" if not str(duration_seconds).endswith("s") else str(duration_seconds)
        input_data: dict[str, Any] = {
            "prompt": prompt,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration": dur_str,
            "generate_audio": True,
        }

        if start_frame_bytes:
            input_data["image_input"] = base64.b64encode(start_frame_bytes).decode("utf-8")

        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_data,
        }

        start_time = time.time()
        effective_timeout = max(float(timeout), 180.0)
        timeout_config = httpx.Timeout(
            connect=15.0,
            read=effective_timeout,
            write=60.0,
            pool=15.0,
        )

        async with httpx.AsyncClient(timeout=timeout_config) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code >= 400:
                err_text = response.text[:1000]
                try:
                    err_json = response.json()
                    errors = err_json.get("errors") or err_json.get("messages")
                    if errors:
                        err_text = str(errors)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Cloudflare video generation failed (HTTP {response.status_code}): {err_text}"
                )

            content_type = response.headers.get("content-type", "").lower()
            if "video/mp4" in content_type:
                return GeneratedVideo(
                    data=response.content,
                    mime_type="video/mp4",
                    duration_seconds=duration_seconds,
                )

            try:
                data = response.json()
            except Exception as exc:
                raise RuntimeError("Cloudflare AI returned a non-JSON and non-video response.") from exc

            result = data.get("result", {})
            video_url = None
            if isinstance(result, dict):
                inner_res = result.get("result", {})
                if isinstance(inner_res, dict):
                    video_url = inner_res.get("video")
                if not video_url:
                    video_url = result.get("video")
            elif isinstance(result, str):
                video_url = result

            task_id = data.get("task_id") or (result.get("task_id") if isinstance(result, dict) else None)
            if not video_url and task_id:
                status_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/tasks/{task_id}"
                while not video_url:
                    elapsed = time.time() - start_time
                    if elapsed > timeout:
                        raise TimeoutError(f"Cloudflare video generation timed out after {int(elapsed)} seconds.")
                    await asyncio.sleep(poll_interval)
                    status_resp = await client.get(status_url, headers=headers)
                    if status_resp.status_code == 200:
                        s_data = status_resp.json()
                        s_result = s_data.get("result", {})
                        if isinstance(s_result, dict) and s_result.get("video"):
                            video_url = s_result.get("video")
                            break
                        if s_data.get("state") == "Failed":
                            raise RuntimeError(f"Cloudflare video generation task failed: {s_data.get('error')}")

            if not video_url:
                raise RuntimeError(f"Cloudflare video generation completed without video output: {data}")

            # If video_url is a hosted URL (e.g. R2 storage link)
            if video_url.startswith("http://") or video_url.startswith("https://"):
                dl_error = None
                video_bytes = b""
                for attempt in range(self.retry_config.max_attempts):
                    try:
                        dl_resp = await client.get(video_url)
                        dl_resp.raise_for_status()
                        video_bytes = dl_resp.content
                        if video_bytes:
                            dl_error = None
                            break
                    except Exception as dl_exc:
                        dl_error = dl_exc
                        if attempt + 1 < self.retry_config.max_attempts:
                            await wait_before_retry(self.retry_config, attempt)
                        else:
                            raise
                if dl_error:
                    raise dl_error

                return GeneratedVideo(
                    data=video_bytes,
                    mime_type="video/mp4",
                    duration_seconds=duration_seconds,
                )

            # If video_url is base64
            try:
                video_bytes = base64.b64decode(video_url)
                return GeneratedVideo(
                    data=video_bytes,
                    mime_type="video/mp4",
                    duration_seconds=duration_seconds,
                )
            except Exception as exc:
                raise RuntimeError("Failed to decode video payload from Cloudflare response.") from exc

    async def _generate_google_video(
        self,
        prompt: str,
        start_frame_bytes: bytes | None,
        duration_seconds: int,
        resolution: str,
        aspect_ratio: str,
        timeout: float,
        poll_interval: float,
    ) -> GeneratedVideo:
        api_key = self.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not configured.")
        if api_key.startswith("cfut_"):
            raise RuntimeError(
                "A Cloudflare API token (cfut_...) is configured for Google GenAI. "
                "Cloudflare Workers AI model 'google/veo-3.1-fast' must be used with Cloudflare, "
                "or a valid Google Gemini API key (AIza...) must be provided."
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.GenerateVideosConfig(
            number_of_videos=1,
            duration_seconds=str(duration_seconds),
            resolution="720p",
            aspect_ratio=aspect_ratio,
        )

        image_obj = None
        if start_frame_bytes:
            mime_type = "image/jpeg"
            if start_frame_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                mime_type = "image/png"
            elif start_frame_bytes.startswith(b"RIFF") and b"WEBP" in start_frame_bytes[:16]:
                mime_type = "image/webp"
            image_obj = types.Image(image_bytes=start_frame_bytes, mime_type=mime_type)

        start_time = time.time()

        def _start_op():
            return client.models.generate_videos(
                model=self.model,
                prompt=prompt.strip(),
                image=image_obj,
                config=config,
            )

        operation = await asyncio.to_thread(_start_op)
        if not operation:
            raise RuntimeError("Video generation failed to initialize operation.")

        while not operation.done:
            elapsed = time.time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Video generation timed out after {int(elapsed)} seconds.")

            await asyncio.sleep(poll_interval)
            try:
                def _get_op():
                    return client.operations.get(operation)

                operation = await asyncio.to_thread(_get_op)
            except Exception as poll_exc:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise TimeoutError(f"Video generation timed out after {int(elapsed)} seconds.") from poll_exc
                continue

        if getattr(operation, "error", None):
            err_msg = getattr(operation.error, "message", str(operation.error))
            raise RuntimeError(f"Video generation operation failed: {err_msg}")

        if operation.response is None or not operation.response.generated_videos:
            raise RuntimeError("Video generation completed without returned video.")

        first_video = operation.response.generated_videos[0]
        if first_video.video is None:
            raise RuntimeError("Generated video payload is empty.")

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            def _download():
                client.files.download(file=first_video.video, destination=str(tmp_path))

            await asyncio.to_thread(_download)
            video_bytes = tmp_path.read_bytes()
            return GeneratedVideo(
                data=video_bytes,
                mime_type="video/mp4",
                duration_seconds=duration_seconds,
            )
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
