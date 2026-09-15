import pytest
from pydantic import BaseModel

from app.llm.base import (
    LLMBillingError,
    LLMInvalidOutputError,
    LLMPermissionError,
    LLMRateLimitError,
    LLMUnavailableError,
)
from app.llm.gemini import (
    GeminiProvider,
    billing_error_message,
    is_billing_error,
    is_permission_error,
    is_rate_limit_error,
    is_unavailable_error,
    public_error_message,
    wrap_gemini_exception,
)
from app.llm.retry import transient_exhausted_message, with_retry


class _FakeServerError(Exception):
    def __init__(self, code: int, status: str, message: str) -> None:
        self.code = code
        self.status = status
        super().__init__(f"{code} {status}. {message}")


class _Ping(BaseModel):
    ok: bool


class _FakeResponse:
    def __init__(self, parsed: _Ping) -> None:
        self.parsed = parsed
        self.text = parsed.model_dump_json()
        self.usage_metadata = None


class _FakeModels:
    def __init__(self, impl) -> None:
        self._impl = impl

    async def generate_content(self, **kwargs):
        return await self._impl(**kwargs)


class _FakeAio:
    def __init__(self, impl) -> None:
        self.models = _FakeModels(impl)


class _FakeClient:
    def __init__(self, impl) -> None:
        self.aio = _FakeAio(impl)


@pytest.mark.asyncio
async def test_retries_rate_limit_then_succeeds() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise LLMRateLimitError("Gemini rate limited (429). The request will be retried.")
        return "ok"

    result = await with_retry(
        operation, initial_delay_seconds=0.01, max_delay_seconds=0.02, jitter=False
    )
    assert result == "ok"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_retries_503_then_succeeds() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise LLMUnavailableError(
                "Gemini temporarily unavailable (503). The request will be retried."
            )
        return "ok"

    result = await with_retry(
        operation, initial_delay_seconds=0.01, max_delay_seconds=0.02, jitter=False
    )
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

    result = await with_retry(operation, initial_delay_seconds=0.01, jitter=False)
    assert result == "ok"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_invalid_output_fails_after_one_retry() -> None:
    async def operation() -> str:
        raise LLMInvalidOutputError("bad json")

    with pytest.raises(LLMInvalidOutputError):
        await with_retry(operation, initial_delay_seconds=0.01, jitter=False)


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
        await with_retry(operation, initial_delay_seconds=0.01, jitter=False)
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_permission_error_fails_fast_without_retry() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        raise LLMPermissionError(
            "Gemini permission error (403): access denied. "
            "Check GEMINI_API_KEY permissions. This request will not be retried."
        )

    with pytest.raises(LLMPermissionError, match="permission error \\(403\\)"):
        await with_retry(operation, initial_delay_seconds=0.01, jitter=False)
    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_503_exhausted_message_includes_retry_count() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        raise LLMUnavailableError(
            "Gemini temporarily unavailable (503). The request will be retried."
        )

    with pytest.raises(
        LLMUnavailableError,
        match=r"Gemini temporarily unavailable \(503\) after 3 retries, try again later",
    ):
        await with_retry(
            operation,
            max_transient_attempts=3,
            initial_delay_seconds=0.01,
            max_delay_seconds=0.02,
            jitter=False,
        )
    assert attempts["count"] == 3


def test_prepayment_credits_are_billing_not_rate_limit() -> None:
    exc = Exception(
        "429 You exceeded your current quota. Your prepayment credits are depleted."
    )
    assert is_billing_error(exc) is True
    assert is_rate_limit_error(exc) is False
    assert is_unavailable_error(exc) is False
    assert "prepayment credits are depleted" in billing_error_message(exc)
    assert "will not be retried" in billing_error_message(exc)


def test_retry_in_message_is_rate_limit() -> None:
    exc = Exception("429 RESOURCE_EXHAUSTED. Please retry in 47.7s.")
    assert is_billing_error(exc) is False
    assert is_unavailable_error(exc) is False
    assert is_rate_limit_error(exc) is True


def test_503_unavailable_is_transient_not_billing() -> None:
    exc = _FakeServerError(
        503,
        "UNAVAILABLE",
        "The model is currently experiencing high demand. Wait a bit and try again.",
    )
    assert is_billing_error(exc) is False
    assert is_permission_error(exc) is False
    assert is_unavailable_error(exc) is True
    assert is_rate_limit_error(exc) is False
    wrapped = wrap_gemini_exception(exc)
    assert isinstance(wrapped, LLMUnavailableError)
    assert "503" in str(wrapped)
    assert "AIza" not in str(wrapped)


def test_500_internal_is_transient() -> None:
    exc = _FakeServerError(500, "INTERNAL", "Internal error encountered.")
    assert is_unavailable_error(exc) is True
    assert "500" in public_error_message(exc)


def test_timeout_is_transient() -> None:
    exc = TimeoutError("The read operation timed out")
    assert is_unavailable_error(exc) is True
    assert "timed out" in public_error_message(exc).lower()


def test_permission_403_is_not_retried() -> None:
    exc = _FakeServerError(403, "PERMISSION_DENIED", "The caller does not have permission.")
    assert is_permission_error(exc) is True
    assert is_unavailable_error(exc) is False
    assert is_rate_limit_error(exc) is False
    message = public_error_message(exc)
    assert "403" in message
    assert "will not be retried" in message


def test_public_error_message_is_specific_and_redacts_keys() -> None:
    exc = _FakeServerError(
        503,
        "UNAVAILABLE",
        "high demand api_key=AIzaSyDummySecretValue012345 key=AIzaSyDummySecretValue012345",
    )
    message = public_error_message(exc)
    assert message == "Gemini temporarily unavailable (503). The request will be retried."
    assert "Unexpected error during extraction" not in message
    assert "AIza" not in message
    assert "DummySecret" not in message


def test_exhausted_message_format() -> None:
    exc = LLMUnavailableError(
        "Gemini temporarily unavailable (503). The request will be retried."
    )
    assert (
        transient_exhausted_message(exc, 5)
        == "Gemini temporarily unavailable (503) after 5 retries, try again later"
    )


@pytest.mark.asyncio
async def test_fallback_model_used_after_primary_unavailable() -> None:
    calls: list[str] = []

    async def generate_content(*, model: str, contents: str, config) -> _FakeResponse:
        calls.append(model)
        if model == "primary-model":
            raise _FakeServerError(
                503,
                "UNAVAILABLE",
                "The model is currently experiencing high demand.",
            )
        return _FakeResponse(_Ping(ok=True))

    provider = GeminiProvider(
        client=_FakeClient(generate_content),
        model="primary-model",
        fallback_model="fallback-model",
        max_transient_attempts=2,
        retry_initial_delay_seconds=0.01,
        retry_max_delay_seconds=0.02,
    )
    result = await provider.generate_structured("extract", _Ping)
    assert result.parsed.ok is True
    assert result.usage.model == "fallback-model"
    assert calls == ["primary-model", "primary-model", "fallback-model"]


@pytest.mark.asyncio
async def test_fallback_failure_keeps_clear_503_message() -> None:
    async def generate_content(*, model: str, contents: str, config) -> _FakeResponse:
        raise _FakeServerError(503, "UNAVAILABLE", "high demand")

    provider = GeminiProvider(
        client=_FakeClient(generate_content),
        model="primary-model",
        fallback_model="fallback-model",
        max_transient_attempts=2,
        retry_initial_delay_seconds=0.01,
        retry_max_delay_seconds=0.02,
    )
    with pytest.raises(LLMUnavailableError) as raised:
        await provider.generate_structured("extract", _Ping)
    message = str(raised.value)
    assert "Gemini temporarily unavailable (503) after 2 retries, try again later" in message
    assert "fallback-model" in message
    assert "Unexpected error" not in message
    assert "AIza" not in message
