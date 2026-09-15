import pytest

from app.llm.base import LLMBillingError, LLMInvalidOutputError, LLMRateLimitError
from app.llm.gemini import billing_error_message, is_billing_error, is_rate_limit_error
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


@pytest.mark.asyncio
async def test_billing_error_fails_fast_without_retry() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        raise LLMBillingError(
            "Gemini billing error: prepayment credits are depleted. "
            "Add credits or switch API keys. This request will not be retried."
        )

    with pytest.raises(LLMBillingError, match="prepayment credits are depleted"):
        await with_retry(operation, initial_delay_seconds=0.01)
    assert attempts["count"] == 1


def test_prepayment_credits_are_billing_not_rate_limit() -> None:
    exc = Exception(
        "429 You exceeded your current quota. Your prepayment credits are depleted."
    )
    assert is_billing_error(exc) is True
    assert is_rate_limit_error(exc) is False
    assert "prepayment credits are depleted" in billing_error_message(exc)
    assert "will not be retried" in billing_error_message(exc)


def test_retry_in_message_is_rate_limit() -> None:
    exc = Exception(
        "429 RESOURCE_EXHAUSTED. Please retry in 47.7s."
    )
    assert is_billing_error(exc) is False
    assert is_rate_limit_error(exc) is True

