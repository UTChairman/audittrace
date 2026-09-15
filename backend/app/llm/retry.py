import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.llm.base import LLMInvalidOutputError, LLMRateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_rate_limit_attempts: int = 5,
    invalid_output_retries: int = 1,
    initial_delay_seconds: float = 2.0,
    max_delay_seconds: float = 32.0,
) -> T:
    """Retry rate limits with exponential backoff; retry invalid output once."""
    delay = initial_delay_seconds
    rate_limit_attempt = 0
    invalid_output_attempt = 0

    while True:
        try:
            return await operation()
        except LLMRateLimitError:
            rate_limit_attempt += 1
            if rate_limit_attempt >= max_rate_limit_attempts:
                raise
            logger.warning(
                "LLM rate limit; retrying in %.1fs (attempt %s/%s)",
                delay,
                rate_limit_attempt + 1,
                max_rate_limit_attempts,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay_seconds)
        except LLMInvalidOutputError:
            invalid_output_attempt += 1
            if invalid_output_attempt > invalid_output_retries:
                raise
            logger.warning("Invalid LLM output; retrying once")
