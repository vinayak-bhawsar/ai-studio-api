from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import os
import re

import httpx

from app.core.config import settings
from app.utils.retry import RetryConfig, wait_before_retry


@dataclass(frozen=True)
class GeneratedImage:
    data: bytes
    mime_type: str


class ImageClient:
    """
    Image generation client supporting Cloudflare Workers AI text-to-image
    and Google GenAI as a fallback if configured with a Google Gemini API key.
    """

    def __init__(self, retry_config: RetryConfig | None = None) -> None:
        self.account_id = self._get_account_id()
        self.cloudflare_token = self._get_cloudflare_token()
        self.gemini_api_key = self._get_gemini_api_key()
        self.model = self._get_model()

        self.retry_config = retry_config or RetryConfig(
            max_attempts=3,
            initial_delay_seconds=0.5,
            max_delay_seconds=4.0,
            backoff_multiplier=2.0,
        )

    def _get_gemini_api_key(self) -> str | None:
        key = (
            getattr(self, "gemini_api_key", None)
            or getattr(settings, "GEMINI_API_KEY", None)
            or os.environ.get("GEMINI_API_KEY")
        )
        if not key or not str(key).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                raw_key = env_vals.get("GEMINI_API_KEY")
                if raw_key and str(raw_key).strip():
                    key = str(raw_key).strip()
                    self.gemini_api_key = key
                    try:
                        settings.GEMINI_API_KEY = key
                    except Exception:
                        pass
                    os.environ["GEMINI_API_KEY"] = key
            except Exception:
                pass
        return str(key).strip() if key else None

    def _get_model(self) -> str:
        model = (
            getattr(self, "model", None)
            or getattr(settings, "CLOUDFLARE_IMAGE_MODEL", None)
            or getattr(settings, "IMAGE_GENERATION_MODEL", None)
            or os.environ.get("CLOUDFLARE_IMAGE_MODEL")
            or os.environ.get("IMAGE_GENERATION_MODEL")
        )
        if not model or not str(model).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                raw_model = env_vals.get("CLOUDFLARE_IMAGE_MODEL") or env_vals.get("IMAGE_GENERATION_MODEL")
                if raw_model and str(raw_model).strip():
                    model = str(raw_model).strip()
            except Exception:
                pass
        return str(model).strip() if model else "alibaba/qwen-image-3.0-pro"

    def _get_account_id(self) -> str | None:
        acc = (
            getattr(settings, "CLOUDFLARE_IMAGE_ACCOUNT_ID", None)
            or os.environ.get("CLOUDFLARE_IMAGE_ACCOUNT_ID")
            or getattr(settings, "CLOUDFLARE_ACCOUNT_ID", None)
            or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        )
        if not acc or not str(acc).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                acc = env_vals.get("CLOUDFLARE_IMAGE_ACCOUNT_ID") or env_vals.get("CLOUDFLARE_ACCOUNT_ID")
            except Exception:
                pass
        return str(acc).strip() if acc else None

    def _get_cloudflare_token(self) -> str | None:
        token = (
            getattr(settings, "CLOUDFLARE_IMAGE_API_TOKEN", None)
            or os.environ.get("CLOUDFLARE_IMAGE_API_TOKEN")
            or getattr(settings, "CLOUDFLARE_API_TOKEN", None)
            or os.environ.get("CLOUDFLARE_API_TOKEN")
        )
        if not token or not str(token).strip():
            try:
                import dotenv
                env_vals = dotenv.dotenv_values(".env")
                token = env_vals.get("CLOUDFLARE_IMAGE_API_TOKEN") or env_vals.get("CLOUDFLARE_API_TOKEN")
            except Exception:
                pass
        return str(token).strip() if token else None

    def _is_cloudflare_model(self) -> bool:
        model_name = self._get_model()
        return (
            model_name.startswith("@cf/")
            or model_name.startswith("cloudflare/")
            or model_name.startswith("alibaba/")
            or ("nano-banana" not in model_name.lower() and "gemini" not in model_name.lower())
        )

    async def generate_image(
        self,
        prompt: str,
        reference_image_bytes: bytes | None = None,
        reference_image_mime: str | None = None,
        timeout: float = 60.0,
    ) -> GeneratedImage:
        """
        Generate an image from a prompt (and optional canonical reference image for conditioning).
        """
        if not prompt or not prompt.strip():
            raise ValueError("Image generation prompt cannot be empty.")

        if self._is_cloudflare_model():
            return await self._generate_cloudflare_image(
                prompt=prompt.strip(),
                reference_image_bytes=reference_image_bytes,
                reference_image_mime=reference_image_mime,
                timeout=timeout,
            )
        else:
            return await self._generate_google_image(
                prompt=prompt.strip(),
                reference_image_bytes=reference_image_bytes,
                reference_image_mime=reference_image_mime,
                timeout=timeout,
            )

    async def _generate_cloudflare_image(
        self,
        prompt: str,
        reference_image_bytes: bytes | None = None,
        reference_image_mime: str | None = None,
        timeout: float = 60.0,
    ) -> GeneratedImage:
        account_id = self._get_account_id()
        primary_token = self._get_cloudflare_token()
        model_name = self._get_model()

        if not account_id:
            raise RuntimeError(
                "CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_IMAGE_ACCOUNT_ID is required for Cloudflare image generation."
            )
        if not primary_token:
            raise RuntimeError(
                "CLOUDFLARE_API_TOKEN or CLOUDFLARE_IMAGE_API_TOKEN is required for Cloudflare image generation."
            )

        tokens_to_try = [primary_token]

        if model_name.startswith("@cf/"):
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}"
            payload: dict[str, Any] = {
                "prompt": prompt,
            }
        else:
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
            payload = {
                "model": model_name,
                "input": {
                    "prompt": prompt,
                },
            }

        # Safe diagnostic logging (no secret tokens logged)
        masked_acc = f"{account_id[:4]}...{account_id[-4:]}" if len(account_id) > 8 else "configured"
        print(f"[ImageClient] Provider: Cloudflare Workers AI | Model: {model_name} | Account: {masked_acc} | Token configured: True")
        if reference_image_bytes:
            print(f"[ImageClient] Conditioning: Applying canonical character reference anchor to prompt (Model '{model_name}' text-driven).")

        effective_timeout = max(float(timeout), 90.0)
        timeout_config = httpx.Timeout(
            connect=10.0,
            read=effective_timeout,
            write=30.0,
            pool=10.0,
        )

        last_error = None
        for attempt in range(self.retry_config.max_attempts):
            for token_idx, token in enumerate(tokens_to_try):
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                try:
                    async with httpx.AsyncClient(timeout=timeout_config) as client:
                        response = await client.post(url, headers=headers, json=payload)

                        # Parse errors if non-200
                        if response.status_code >= 400:
                            err_text = response.text[:500]
                            try:
                                err_json = response.json()
                                errors = err_json.get("errors") or err_json.get("messages")
                                if errors:
                                    err_text = " ".join(
                                        f"code: {e.get('code')} message: {e.get('message')}" if isinstance(e, dict) else str(e)
                                        for e in errors
                                    )
                            except Exception:
                                pass

                            # Diagnostic logging of failure
                            print(f"[ImageClient] API Response HTTP {response.status_code}: {err_text}")

                            # If authentication failure (401/403) and another token candidate exists, try it
                            if response.status_code in (401, 403):
                                if token_idx + 1 < len(tokens_to_try):
                                    continue
                                # Non-retryable auth error
                                raise RuntimeError(
                                    f"Cloudflare image generation failed (HTTP {response.status_code}): {err_text}"
                                )

                            # If model route not found (400 code 7000) or 404, fallback to active Cloudflare image model
                            if response.status_code == 404 or (response.status_code == 400 and "7000" in err_text):
                                fallback_model = "@cf/black-forest-labs/flux-1-schnell"
                                if model_name != fallback_model:
                                    print(f"[ImageClient] Model '{model_name}' has no active route (code 7000). Automatically falling back to active Cloudflare model '{fallback_model}'...")
                                    model_name = fallback_model
                                    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}"
                                    payload = {"prompt": prompt}
                                    continue
                                raise RuntimeError(
                                    f"Cloudflare image generation failed (HTTP {response.status_code}): Model '{model_name}' was not found or has no active route on Cloudflare Workers AI. ({err_text})"
                                )

                            raise RuntimeError(
                                f"Cloudflare image generation failed (HTTP {response.status_code}): {err_text}"
                            )

                        content_type = response.headers.get("content-type", "").lower()

                        # Raw binary image returned
                        if "image/" in content_type:
                            return GeneratedImage(
                                data=response.content,
                                mime_type=content_type.split(";")[0],
                            )

                        data = response.json()
                        result = data.get("result", {})
                        img_data_str = None
                        if isinstance(result, dict):
                            inner_res = result.get("result", {})
                            if isinstance(inner_res, dict) and inner_res.get("images"):
                                imgs = inner_res.get("images")
                                if isinstance(imgs, list) and imgs:
                                    img_data_str = imgs[0]
                            if not img_data_str and result.get("images"):
                                imgs = result.get("images")
                                if isinstance(imgs, list) and imgs:
                                    img_data_str = imgs[0]
                            if not img_data_str:
                                img_data_str = result.get("image") or result.get("b64")
                        elif isinstance(result, str):
                            img_data_str = result

                        if not img_data_str:
                            raise RuntimeError(f"Cloudflare AI returned response without image data: {data}")

                        # If returned a hosted URL (e.g. Alibaba OSS or Cloudflare R2)
                        if isinstance(img_data_str, str) and (img_data_str.startswith("http://") or img_data_str.startswith("https://")):
                            dl_resp = await client.get(img_data_str, timeout=30.0)
                            if dl_resp.status_code == 200:
                                dl_ctype = dl_resp.headers.get("content-type", "image/png").split(";")[0]
                                return GeneratedImage(
                                    data=dl_resp.content,
                                    mime_type=dl_ctype,
                                )
                            raise RuntimeError(f"Failed to download generated image from {img_data_str}: HTTP {dl_resp.status_code}")

                        image_bytes = base64.b64decode(img_data_str)
                        return GeneratedImage(
                            data=image_bytes,
                            mime_type="image/jpeg",
                        )

                except Exception as exc:
                    last_error = exc
                    # Do not retry non-retryable errors (401, 403, 404, model route not found)
                    err_str = str(exc)
                    if any(term in err_str for term in ("HTTP 401", "HTTP 403", "HTTP 404", "7000", "not found")):
                        raise exc

            if attempt + 1 < self.retry_config.max_attempts:
                await wait_before_retry(self.retry_config, attempt)
                continue
            if last_error is not None:
                raise last_error
            raise RuntimeError("Cloudflare image generation failed.")

        if last_error is not None:
            raise last_error
        raise RuntimeError("Cloudflare image generation failed after retries.")

    def _extract_image_from_response(self, resp) -> GeneratedImage | None:
        parts = getattr(resp, "parts", None) or []
        if not parts and getattr(resp, "candidates", None):
            for cand in resp.candidates:
                content = getattr(cand, "content", None)
                if content and getattr(content, "parts", None):
                    parts.extend(content.parts)
        for part in parts:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                raw_data = inline.data
                if isinstance(raw_data, str):
                    raw_data = base64.b64decode(raw_data)
                mime = getattr(inline, "mime_type", "image/png") or "image/png"
                return GeneratedImage(data=bytes(raw_data), mime_type=mime)
            if hasattr(part, "as_image"):
                try:
                    pil_img = part.as_image()
                    if pil_img is not None:
                        import io
                        buf = io.BytesIO()
                        pil_img.save(buf, format="PNG")
                        return GeneratedImage(data=buf.getvalue(), mime_type="image/png")
                except Exception:
                    pass
        return None

    async def _generate_google_image(
        self,
        prompt: str,
        reference_image_bytes: bytes | None = None,
        reference_image_mime: str | None = None,
        timeout: float = 60.0,
    ) -> GeneratedImage:
        api_key = self._get_gemini_api_key()
        model_name = self._get_model()
        if not api_key or not api_key.strip():
            raise RuntimeError(
                f"Image generation failed: Nano Banana 2 ('{model_name}') is a Google AI Studio model and requires a dedicated Google Gemini API key (starting with AIza...). "
                "GEMINI_API_KEY is not configured in your .env file. "
                "Cloudflare Workers AI does not host Nano Banana 2 in its catalog. "
                "Please configure a valid Google AI Studio API key in GEMINI_API_KEY in .env."
            )

        if api_key.startswith("cfut_"):
            raise RuntimeError(
                f"Image generation failed: Nano Banana 2 ('{model_name}') is a Google AI Studio model and requires a dedicated Google Gemini API key (starting with AIza...). "
                "The current GEMINI_API_KEY is populated with a Cloudflare token (cfut_...). "
                "Cloudflare Workers AI does not host Nano Banana 2 in its catalog. "
                "Please configure a valid Google AI Studio API key in GEMINI_API_KEY in your .env file."
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        contents_payload: Any = prompt
        if reference_image_bytes:
            mime = reference_image_mime or "image/jpeg"
            contents_payload = [
                types.Part.from_bytes(data=reference_image_bytes, mime_type=mime),
                prompt,
            ]

        last_error = None
        for attempt in range(2):
            try:
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=contents_payload,
                            config=config,
                        ),
                        timeout=timeout,
                    )
                    gen_img = self._extract_image_from_response(resp)
                    if gen_img:
                        return gen_img
                except Exception as config_err:
                    last_error = config_err
                    # Fallback without config
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=contents_payload,
                        ),
                        timeout=timeout,
                    )
                    gen_img = self._extract_image_from_response(resp)
                    if gen_img:
                        return gen_img

                raise RuntimeError(f"No image data returned from model '{model_name}'.")

            except Exception as exc:
                last_error = exc
                if attempt + 1 < 2:
                    await asyncio.sleep(1.0)
                    continue

        err_msg = f"{type(last_error).__name__}: {str(last_error) or repr(last_error)}" if last_error else "unknown error"
        raise RuntimeError(f"Google image generation failed for model '{model_name}': {err_msg}")