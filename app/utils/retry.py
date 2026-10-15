import asyncio
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryConfig:
    """
    Configuration for retrying transient LLM requests.
    """

    max_attempts: int = 3

    initial_delay_seconds: float = 1.0

    max_delay_seconds: float = 8.0

    backoff_multiplier: float = 2.0

    retryable_status_codes: frozenset[int] = frozenset(
        {
            408,
            429,
            500,
            502,
            503,
            504,
        }
    )


async def wait_before_retry(
    config: RetryConfig,
    attempt: int,
) -> None:
    """
    Wait using exponential backoff.

    Example:

    attempt 0 -> 1 second
    attempt 1 -> 2 seconds
    attempt 2 -> 4 seconds
    """

    delay = min(
        config.initial_delay_seconds
        * (
            config.backoff_multiplier
            ** attempt
        ),
        config.max_delay_seconds,
    )

    await asyncio.sleep(delay)


def wait_before_retry_sync(
    config: RetryConfig,
    attempt: int,
) -> None:
    """
    Synchronous wait using exponential backoff.
    """

    delay = min(
        config.initial_delay_seconds
        * (
            config.backoff_multiplier
            ** attempt
        ),
        config.max_delay_seconds,
    )

    time.sleep(delay)