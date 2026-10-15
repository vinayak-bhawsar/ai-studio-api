
import json
import time
from collections.abc import AsyncIterator
from enum import StrEnum

import httpx

from app.core.config import settings
from app.utils.retry import (
    RetryConfig,
    wait_before_retry,
    wait_before_retry_sync,
)


class LLMRole(StrEnum):
    """Logical roles for LLM usage."""

    CREATIVE = "creative"
    REASONING = "reasoning"


class LLMClient:
    """
    Generic OpenAI-compatible LLM client.

    Responsibilities:
    - Provider communication
    - Model selection by logical role
    - Normal generation
    - Streaming
    - Structured output
    - Retry handling
    - Provider response parsing
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.provider = (
            provider or settings.LLM_PROVIDER
        ).strip().lower()

        self.api_key = (
            api_key or settings.LLM_API_KEY
        )

        self.base_url = (
            base_url or settings.LLM_BASE_URL
        ).rstrip("/")

        self.retry_config = (
            retry_config or RetryConfig()
        )

        # Increase output-token budget for large structured payloads.
        self.max_tokens = 8192
        self.reasoning_effort = "low"

    # =========================================================
    # MODEL RESOLUTION
    # =========================================================

    @staticmethod
    def _get_model(role: LLMRole) -> str:
        if role == LLMRole.CREATIVE:
            return settings.CREATIVE_LLM_MODEL

        if role == LLMRole.REASONING:
            return settings.REASONING_LLM_MODEL

        raise ValueError(
            f"Unsupported LLM role: {role}"
        )

    # =========================================================
    # HEADERS
    # =========================================================

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # =========================================================
    # NORMAL GENERATION
    # =========================================================

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        role: LLMRole = LLMRole.CREATIVE,
        temperature: float = 0.7,
        timeout: float = 120.0,
    ) -> str:
        model = self._get_model(role)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
        }

        response = await self._request(
            payload=payload,
            timeout=timeout,
        )

        return self._extract_text(response)

    # =========================================================
    # NORMAL STREAMING
    # =========================================================

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        role: LLMRole = LLMRole.CREATIVE,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        model = self._get_model(role)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
            "stream": True,
        }

        async for chunk in self._stream_request(
            payload=payload,
        ):
            yield chunk

    # =========================================================
    # STRUCTURED GENERATION
    # =========================================================

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict,
        schema_name: str,
        role: LLMRole = LLMRole.CREATIVE,
        temperature: float = 0.4,
        max_tokens: int | None = 8192,
        timeout: float = 120.0,
    ) -> dict:
        model = self._get_model(role)

        payload = self._build_structured_payload(
            model=model,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            temperature=temperature,
            stream=False,
            max_tokens=max_tokens,
        )

        response = await self._request(
            payload=payload,
            timeout=timeout,
        )

        content = self._extract_text(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM provider returned invalid JSON "
                "for structured output."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "LLM provider returned invalid "
                "structured output."
            )

        return result

    def generate_structured_sync(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict,
        schema_name: str,
        role: LLMRole = LLMRole.CREATIVE,
        temperature: float = 0.4,
        max_tokens: int | None = 8192,
        timeout: float = 120.0,
    ) -> dict:
        model = self._get_model(role)

        payload = self._build_structured_payload(
            model=model,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            temperature=temperature,
            stream=False,
            max_tokens=max_tokens,
        )

        response = self._request_sync(
            payload=payload,
            timeout=timeout,
        )

        content = self._extract_text(response)

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "LLM provider returned invalid JSON "
                "for structured output."
            ) from exc

        if not isinstance(result, dict):
            raise RuntimeError(
                "LLM provider returned invalid "
                "structured output."
            )

        return result

    # =========================================================
    # STRUCTURED STREAMING
    # =========================================================

    async def stream_structured(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict,
        schema_name: str,
        role: LLMRole = LLMRole.CREATIVE,
        temperature: float = 0.4,
        max_tokens: int | None = 8192,
    ) -> AsyncIterator[str]:
        model = self._get_model(role)

        payload = self._build_structured_payload(
            model=model,
            messages=messages,
            schema=schema,
            schema_name=schema_name,
            temperature=temperature,
            stream=True,
            max_tokens=max_tokens,
        )

        async for chunk in self._stream_request(
            payload=payload,
        ):
            yield chunk

    @staticmethod
    def _dereference_schema(schema: dict) -> dict:
        """
        Recursively expand $defs / $ref in Pydantic generated JSON Schemas
        because Cloudflare AI & open models do not support $ref pointers.
        """
        import copy

        if not isinstance(schema, dict):
            return schema

        schema_copy = copy.deepcopy(schema)
        defs = schema_copy.pop("$defs", {}) or schema_copy.pop("definitions", {})

        if not defs:
            return schema_copy

        def resolve(node):
            if isinstance(node, dict):
                if "$ref" in node:
                    ref_str = str(node["$ref"])
                    ref_key = ref_str.split("/")[-1]
                    if ref_key in defs:
                        target = copy.deepcopy(defs[ref_key])
                        for k, v in node.items():
                            if k != "$ref":
                                target[k] = v
                        return resolve(target)
                return {k: resolve(v) for k, v in node.items()}
            elif isinstance(node, list):
                return [resolve(item) for item in node]
            return node

        return resolve(schema_copy)

    # =========================================================
    # STRUCTURED PAYLOAD
    # =========================================================

    def _build_structured_payload(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        schema: dict,
        schema_name: str,
        temperature: float,
        stream: bool,
        max_tokens: int | None = None,
    ) -> dict:
        # Retain schema_name for compatibility with existing callers.
        # Cloudflare expects the JSON Schema directly in json_schema.
        _ = schema_name

        clean_schema = self._dereference_schema(schema)

        return {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": (
                max_tokens if max_tokens is not None else self.max_tokens
            ),
            "stream": stream,
            "response_format": {
                "type": "json_schema",
                "json_schema": clean_schema,
            },
        }

    # =========================================================
    # HTTP REQUEST
    # =========================================================

    async def _request(
        self,
        *,
        payload: dict,
        timeout: float = 120.0,
    ) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"

        last_error: Exception | None = None

        if isinstance(timeout, (int, float)):
            timeout_config = httpx.Timeout(
                connect=10.0,
                read=float(timeout),
                write=30.0,
                pool=10.0,
            )
        else:
            timeout_config = timeout

        for attempt in range(self.retry_config.max_attempts):
            started = time.monotonic()
            print(f"[LLM CLIENT] Request started (model={payload.get('model')}, attempt={attempt + 1})")
            try:
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    response = await client.post(
                        url,
                        headers=self._get_headers(),
                        json=payload,
                    )

                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Response received: "
                    f"status={response.status_code}, "
                    f"elapsed={elapsed:.2f}s"
                )

                if self._is_retryable(response.status_code):
                    if self._can_retry(attempt):
                        await wait_before_retry(self.retry_config, attempt)
                        continue

                    raise RuntimeError(self._provider_error(response))

                if response.status_code >= 400:
                    print(
                        f"[LLM CLIENT] HTTP error: "
                        f"status={response.status_code}, "
                        f"body={response.text[:1000]}"
                    )
                    raise RuntimeError(self._provider_error(response))

                return response

            except httpx.TimeoutException as exc:
                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Cloudflare timed out after "
                    f"{elapsed:.2f}s: {type(exc).__name__}"
                )
                last_error = exc
                if self._can_retry(attempt):
                    await wait_before_retry(self.retry_config, attempt)
                    continue
                raise RuntimeError("Unable to connect to LLM provider (timeout).") from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Network error after {elapsed:.2f}s: "
                    f"{type(exc).__name__}: {exc}"
                )
                last_error = exc
                if self._can_retry(attempt):
                    await wait_before_retry(self.retry_config, attempt)
                    continue

                raise RuntimeError("Unable to connect to LLM provider.") from exc

        raise RuntimeError("LLM request failed after retries.") from last_error

    def _request_sync(
        self,
        *,
        payload: dict,
        timeout: float = 120.0,
    ) -> httpx.Response:
        url = f"{self.base_url}/chat/completions"

        last_error: Exception | None = None

        if isinstance(timeout, (int, float)):
            timeout_config = httpx.Timeout(
                connect=10.0,
                read=float(timeout),
                write=30.0,
                pool=10.0,
            )
        else:
            timeout_config = timeout

        for attempt in range(self.retry_config.max_attempts):
            started = time.monotonic()
            print(f"[LLM CLIENT] Request started (model={payload.get('model')}, attempt={attempt + 1})")
            try:
                with httpx.Client(timeout=timeout_config) as client:
                    response = client.post(
                        url,
                        headers=self._get_headers(),
                        json=payload,
                    )

                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Response received: "
                    f"status={response.status_code}, "
                    f"elapsed={elapsed:.2f}s"
                )

                if self._is_retryable(response.status_code):
                    if self._can_retry(attempt):
                        wait_before_retry_sync(self.retry_config, attempt)
                        continue

                    raise RuntimeError(self._provider_error(response))

                if response.status_code >= 400:
                    print(
                        f"[LLM CLIENT] HTTP error: "
                        f"status={response.status_code}, "
                        f"body={response.text[:1000]}"
                    )
                    raise RuntimeError(self._provider_error(response))

                return response

            except httpx.TimeoutException as exc:
                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Cloudflare timed out after "
                    f"{elapsed:.2f}s: {type(exc).__name__}"
                )
                last_error = exc
                if self._can_retry(attempt):
                    wait_before_retry_sync(self.retry_config, attempt)
                    continue
                raise RuntimeError("Unable to connect to LLM provider (timeout).") from exc

            except httpx.RequestError as exc:
                elapsed = time.monotonic() - started
                print(
                    f"[LLM CLIENT] Network error after {elapsed:.2f}s: "
                    f"{type(exc).__name__}: {exc}"
                )
                last_error = exc

                if self._can_retry(attempt):
                    wait_before_retry_sync(self.retry_config, attempt)
                    continue

                raise RuntimeError("Unable to connect to LLM provider.") from exc

        raise RuntimeError("LLM request failed after retries.") from last_error

    # =========================================================
    # STREAM REQUEST
    # =========================================================

    async def _stream_request(
        self,
        *,
        payload: dict,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"

        for attempt in range(
            self.retry_config.max_attempts
        ):
            try:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=60.0,
                        write=30.0,
                        pool=10.0,
                    )
                ) as client:
                    async with client.stream(
                        "POST",
                        url,
                        headers=self._get_headers(),
                        json=payload,
                    ) as response:
                        if self._is_retryable(
                            response.status_code
                        ):
                            await response.aread()

                            if self._can_retry(attempt):
                                await wait_before_retry(
                                    self.retry_config,
                                    attempt,
                                )
                                continue

                            raise RuntimeError(
                                self._provider_error(response)
                            )

                        if response.status_code >= 400:
                            await response.aread()

                            raise RuntimeError(
                                self._provider_error(response)
                            )

                        async for chunk in self._read_stream(
                            response
                        ):
                            yield chunk

                        return

            except httpx.RequestError as exc:
                if self._can_retry(attempt):
                    await wait_before_retry(
                        self.retry_config,
                        attempt,
                    )
                    continue

                raise RuntimeError(
                    "Unable to connect to LLM provider."
                ) from exc

        raise RuntimeError(
            "LLM streaming failed after retries."
        )

    # =========================================================
    # SSE STREAM PARSER
    # =========================================================

    async def _read_stream(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[str]:
        async for line in response.aiter_lines():
            if not line or not line.startswith("data:"):
                continue

            data = line[5:].strip()

            if data == "[DONE]":
                return

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            if not isinstance(chunk, dict):
                continue

            choices = chunk.get("choices", [])

            if not isinstance(choices, list) or not choices:
                continue

            choice = choices[0]

            if not isinstance(choice, dict):
                continue

            delta = choice.get("delta", {})

            if not isinstance(delta, dict):
                continue

            content = delta.get("content")

            if isinstance(content, str) and content:
                yield content

            elif isinstance(content, list):
                # Handle text content parts when the provider
                # returns content as an array.
                for part in content:
                    if not isinstance(part, dict):
                        continue

                    part_text = part.get("text")

                    if isinstance(part_text, str) and part_text:
                        yield part_text

    # =========================================================
    # RESPONSE EXTRACTION
    # =========================================================

    @staticmethod
    def _extract_text(
        response: httpx.Response,
    ) -> str:
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(
                "LLM provider returned a non-JSON response."
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                "LLM provider returned an invalid response object."
            )

        choices = data.get("choices")

        if not isinstance(choices, list) or not choices:
            raise RuntimeError(
                "LLM provider response contained no choices."
            )

        choice = choices[0]

        if not isinstance(choice, dict):
            raise RuntimeError(
                "LLM provider returned an invalid choice."
            )

        message = choice.get("message")

        if not isinstance(message, dict):
            raise RuntimeError(
                "LLM provider returned an invalid message."
            )

        content = message.get("content")

        # Some providers return structured content parts.
        if isinstance(content, list):
            parts = [
                part["text"]
                for part in content
                if isinstance(part, dict)
                and isinstance(part.get("text"), str)
            ]
            content = "".join(parts)

        if isinstance(content, str) and content.strip():
            return content.strip()

        # Do not use reasoning_content as the final answer.
        # It may contain internal reasoning rather than the
        # requested assistant response or structured JSON.
        finish_reason = choice.get("finish_reason")
        usage = data.get("usage", {})
        completion_tokens = (
            usage.get("completion_tokens")
            if isinstance(usage, dict)
            else None
        )

        if finish_reason == "length":
            raise RuntimeError(
                "LLM response was truncated because the output-token "
                f"limit was reached. completion_tokens={completion_tokens}. "
                "Increase max_tokens or reduce the requested output."
            )

        if message.get("refusal"):
            raise RuntimeError(
                "LLM provider refused to generate the requested response."
            )

        raise RuntimeError(
            "LLM provider returned no assistant content. "
            f"finish_reason={finish_reason!r}, "
            f"completion_tokens={completion_tokens!r}."
        )

    # =========================================================
    # RETRY
    # =========================================================

    def _is_retryable(
        self,
        status_code: int,
    ) -> bool:
        return (
            status_code
            in self.retry_config.retryable_status_codes
        )

    def _can_retry(
        self,
        attempt: int,
    ) -> bool:
        return (
            attempt + 1
            < self.retry_config.max_attempts
        )

    # =========================================================
    # PROVIDER ERROR
    # =========================================================

    @staticmethod
    def _provider_error(
        response: httpx.Response,
    ) -> str:
        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError):
            body = response.text[:1000].strip()

            return (
                f"LLM provider returned HTTP "
                f"{response.status_code}."
                + (f" Response: {body}" if body else "")
            )

        if isinstance(data, dict):
            error = data.get("error")

            if isinstance(error, dict):
                message = error.get("message")

                if isinstance(message, str) and message:
                    return (
                        f"LLM provider returned HTTP "
                        f"{response.status_code}: {message}"
                    )

        # Do not include reasoning_content in provider errors.
        return (
            f"LLM provider returned HTTP {response.status_code}."
        )


async def debug_cloudflare_request(
    url: str,
    headers: dict,
    payload: dict,
) -> dict:
    started = time.monotonic()

    timeout = httpx.Timeout(
        connect=10.0,
        read=90.0,
        write=30.0,
        pool=10.0,
    )

    print("[LLM CLIENT] Request started")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

        elapsed = time.monotonic() - started

        print(
            f"[LLM CLIENT] Response received: "
            f"status={response.status_code}, "
            f"elapsed={elapsed:.2f}s"
        )

        response.raise_for_status()
        return response.json()

    except httpx.TimeoutException as exc:
        print(
            f"[LLM CLIENT] Cloudflare timed out after "
            f"{time.monotonic() - started:.2f}s: "
            f"{type(exc).__name__}"
        )
        raise

    except httpx.HTTPStatusError as exc:
        print(
            f"[LLM CLIENT] HTTP error: "
            f"status={exc.response.status_code}, "
            f"body={exc.response.text[:1000]}"
        )
        raise

    except httpx.RequestError as exc:
        print(
            f"[LLM CLIENT] Network error: "
            f"{type(exc).__name__}: {exc}"
        )
        raise

