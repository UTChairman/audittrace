import pytest

from app.llm.base import LLMInvalidOutputError, LLMRateLimitError
from app.llm.retry import with_retry


@pytest.mark.asyncio
async def test_retries_rate_limit_then_succeeds() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise LLMRateLimitError("429")
        return "ok"

    result = await with_retry(operation, initial_delay_seconds=0.01, max_delay_seconds=0.02)
    assert result == "ok"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_retries_invalid_output_once() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise LLMInvalidOutputError("bad json")
        return "ok"

    result = await with_retry(operation, initial_delay_seconds=0.01)
    assert result == "ok"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_invalid_output_fails_after_one_retry() -> None:
    async def operation() -> str:
        raise LLMInvalidOutputError("bad json")

    with pytest.raises(LLMInvalidOutputError):
        await with_retry(operation, initial_delay_seconds=0.01)
