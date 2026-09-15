import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.llm.base import LLMInvalidOutputError, LLMRateLimitError, LLMUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_ERRORS = (LLMRateLimitError, LLMUnavailableError)


def transient_exhausted_message(exc: Exception, attempts: int) -> str:
    """Clear stored message after the retry cap is hit. Never includes secrets."""
    text = str(exc).strip()
    text = text.replace(" The request will be retried.", "")
    text = text.rstrip(".")
    if not text:
        text = "Gemini temporarily unavailable"
    return f"{text} after {attempts} retries, try again later"


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    max_transient_attempts: int = 5,
    invalid_output_retries: int = 1,
    initial_delay_seconds: float = 2.0,
    max_delay_seconds: float = 32.0,
    jitter: bool = True,
) -> T:
    """Retry transient LLM failures with exponential backoff and jitter.

    Rate limits, 503/500, and timeouts share the same cap so a job cannot hang.
    Invalid structured output is retried once. Billing and permission errors are
    not caught here and fail immediately.
    """
    delay = initial_delay_seconds
    transient_attempt = 0
    invalid_output_attempt = 0

    while True:
        try:
            return await operation()
        except TRANSIENT_ERRORS as exc:
            transient_attempt += 1
            if transient_attempt >= max_transient_attempts:
                message = transient_exhausted_message(exc, transient_attempt)
                raise type(exc)(message) from exc
            sleep_for = delay
            if jitter:
                sleep_for = delay + random.uniform(0, delay * 0.3)
            logger.warning(
                "Transient LLM error (%s); retrying in %.1fs (attempt %s/%s)",
                type(exc).__name__,
                sleep_for,
                transient_attempt + 1,
                max_transient_attempts,
            )
            await asyncio.sleep(sleep_for)
            delay = min(delay * 2, max_delay_seconds)
        except LLMInvalidOutputError:
            invalid_output_attempt += 1
            if invalid_output_attempt > invalid_output_retries:
                raise
            logger.warning("Invalid LLM output; retrying once")
