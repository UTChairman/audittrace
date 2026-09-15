import logging
import re
from typing import Any, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.base import (
    LLMBillingError,
    LLMError,
    LLMInvalidOutputError,
    LLMModelNotFoundError,
    LLMPermissionError,
    LLMRateLimitError,
    LLMUnavailableError,
    LLMUsage,
    StructuredLLMResult,
)
from app.llm.retry import with_retry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

BILLING_MARKERS = (
    "prepayment credits",
    "credits are depleted",
    "credits depleted",
    "enable billing",
    "billing has not been enabled",
    "insufficient credits",
    "purchase additional credits",
)

PERMISSION_MARKERS = (
    "permission denied",
    "permission_denied",
    "unauthenticated",
    "api key not valid",
    "api_key_invalid",
    "api key invalid",
    "caller does not have permission",
    "forbidden",
)

TRANSIENT_STATUS_CODES = {500, 502, 503, 504}
PERMISSION_STATUS_CODES = {401, 403}

_API_KEY_VALUE = re.compile(r"AIza[0-9A-Za-z_-]{8,}")
_API_KEY_ASSIGNMENT = re.compile(
    r"(?i)((?:gemini_)?api[_-]?key)([\"'\s:=]+)([^\s\"'&,]+)"
)
_API_KEY_QUERY = re.compile(r"(?i)([?&]key=)[^&\s]+")


def sanitize_secret_text(text: str) -> str:
    """Strip API keys and similar secrets from text stored or returned as errors."""
    cleaned = _API_KEY_VALUE.sub("[REDACTED]", text)
    cleaned = _API_KEY_ASSIGNMENT.sub(r"\1\2[REDACTED]", cleaned)
    cleaned = _API_KEY_QUERY.sub(r"\1[REDACTED]", cleaned)
    return cleaned


def status_code_from_exception(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.isdigit():
        return int(code)
    match = re.search(r"\b(401|403|404|429|500|502|503|504)\b", str(exc))
    return int(match.group(1)) if match else None


def is_billing_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in BILLING_MARKERS)


def is_permission_error(exc: Exception) -> bool:
    """Fail-fast auth/permission failures, never retried."""
    if is_billing_error(exc):
        return False
    code = status_code_from_exception(exc)
    if code in PERMISSION_STATUS_CODES:
        return True
    status = str(getattr(exc, "status", "") or "").upper()
    if status in {"PERMISSION_DENIED", "UNAUTHENTICATED"}:
        return True
    text = str(exc).lower()
    return any(marker in text for marker in PERMISSION_MARKERS)


def is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return True
    text = str(exc).lower()
    return "timed out" in text or "timeout" in text


def is_network_error(exc: Exception) -> bool:
    if isinstance(exc, ConnectionError):
        return True
    name = type(exc).__name__.lower()
    return any(token in name for token in ("connecterror", "connectionerror", "networkerror"))


def is_model_not_found_error(exc: Exception) -> bool:
    """404 / NOT_FOUND, including models no longer available to new users."""
    if is_billing_error(exc) or is_permission_error(exc):
        return False
    code = status_code_from_exception(exc)
    if code == 404:
        return True
    status = str(getattr(exc, "status", "") or "").upper()
    if status == "NOT_FOUND":
        return True
    text = str(exc).lower()
    return "no longer available" in text


def fallback_model_not_found_message(model: str) -> str:
    return (
        f"Fallback Gemini model '{model}' is not available (404). "
        "Set GEMINI_FALLBACK_MODEL in .env to a current Flash or Flash Lite model."
    )


def is_unavailable_error(exc: Exception) -> bool:
    """503 UNAVAILABLE, 500 internal, and network timeouts — retryable."""
    if is_billing_error(exc) or is_permission_error(exc) or is_model_not_found_error(exc):
        return False
    if is_timeout_error(exc) or is_network_error(exc):
        return True
    code = status_code_from_exception(exc)
    if code in TRANSIENT_STATUS_CODES:
        return True
    status = str(getattr(exc, "status", "") or "").upper()
    if status in {"UNAVAILABLE", "INTERNAL", "DEADLINE_EXCEEDED"}:
        return True
    text = str(exc).lower()
    if "high demand" in text:
        return True
    if "unavailable" in text:
        return True
    return False


def is_rate_limit_error(exc: Exception) -> bool:
    """Retry only transient rate limits, never billing, permission, or 503s."""
    if is_billing_error(exc) or is_permission_error(exc) or is_unavailable_error(exc):
        return False
    text = str(exc).lower()
    if "please retry" in text or "retry in" in text or "rate limit" in text:
        return True
    code = status_code_from_exception(exc)
    if code == 429:
        return "resource_exhausted" in text or "too many requests" in text
    return False


def billing_error_message(exc: Exception) -> str:
    text = str(exc)
    lower = text.lower()
    if "prepayment credits" in lower or ("credits" in lower and "depleted" in lower):
        return (
            "Gemini billing error: prepayment credits are depleted. "
            "Add credits or switch API keys. This request will not be retried."
        )
    summary = sanitize_secret_text(" ".join(text.split()))
    if len(summary) > 280:
        summary = summary[:277] + "..."
    return f"Gemini billing error: {summary}. This request will not be retried."


def permission_error_message(exc: Exception) -> str:
    code = status_code_from_exception(exc) or 403
    return (
        f"Gemini permission error ({code}): access denied. "
        "Check GEMINI_API_KEY permissions. This request will not be retried."
    )


def unavailable_error_message(exc: Exception) -> str:
    if is_timeout_error(exc) and status_code_from_exception(exc) not in TRANSIENT_STATUS_CODES:
        return "Gemini request timed out. The request will be retried."
    if is_network_error(exc) and status_code_from_exception(exc) not in TRANSIENT_STATUS_CODES:
        return "Gemini network error. The request will be retried."
    code = status_code_from_exception(exc)
    if code == 500:
        return "Gemini internal error (500). The request will be retried."
    if code in {502, 504}:
        return f"Gemini temporarily unavailable ({code}). The request will be retried."
    return "Gemini temporarily unavailable (503). The request will be retried."


def rate_limit_error_message() -> str:
    return "Gemini rate limited (429). The request will be retried."


def wrap_gemini_exception(exc: Exception) -> LLMError:
    """Map provider exceptions to typed LLM errors with user-safe messages."""
    if isinstance(exc, LLMError):
        return exc
    if is_billing_error(exc):
        return LLMBillingError(billing_error_message(exc))
    if is_permission_error(exc):
        return LLMPermissionError(permission_error_message(exc))
    if is_model_not_found_error(exc):
        return LLMModelNotFoundError("Gemini model is not available (404).")
    if is_unavailable_error(exc):
        return LLMUnavailableError(unavailable_error_message(exc))
    if is_rate_limit_error(exc):
        return LLMRateLimitError(rate_limit_error_message())
    code = status_code_from_exception(exc)
    if code is not None:
        return LLMError(f"Gemini request failed ({code}).")
    return LLMError("Gemini request failed.")


def public_error_message(exc: Exception) -> str:
    """Message stored on the document. Never generic, never includes API keys."""
    wrapped = wrap_gemini_exception(exc)
    return sanitize_secret_text(str(wrapped))


class GeminiProvider:
    """Google Gemini implementation of the swappable LLM provider interface."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
        max_transient_attempts: int | None = None,
        retry_initial_delay_seconds: float = 2.0,
        retry_max_delay_seconds: float = 32.0,
    ) -> None:
        settings = get_settings()
        self._model = model or settings.gemini_model
        configured_fallback = (
            fallback_model if fallback_model is not None else settings.gemini_fallback_model
        )
        self._fallback_model = (configured_fallback or "").strip()
        if self._fallback_model == self._model:
            self._fallback_model = ""
        self._max_transient_attempts = (
            max_transient_attempts
            if max_transient_attempts is not None
            else settings.gemini_max_transient_attempts
        )
        self._retry_initial_delay_seconds = retry_initial_delay_seconds
        self._retry_max_delay_seconds = retry_max_delay_seconds
        if client is not None:
            self._client = client
            return
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured")
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> StructuredLLMResult[T]:
        async def _call_primary() -> StructuredLLMResult[T]:
            return await self._generate_once(
                self._model, prompt, response_schema, system_instruction
            )

        try:
            return await with_retry(
                _call_primary,
                max_transient_attempts=self._max_transient_attempts,
                initial_delay_seconds=self._retry_initial_delay_seconds,
                max_delay_seconds=self._retry_max_delay_seconds,
            )
        except (LLMUnavailableError, LLMRateLimitError) as exc:
            if not self._fallback_model:
                raise
            logger.warning(
                "Primary Gemini model %s unavailable after retries; trying fallback %s once",
                self._model,
                self._fallback_model,
            )
            try:
                return await self._generate_once(
                    self._fallback_model, prompt, response_schema, system_instruction
                )
            except LLMModelNotFoundError as fallback_exc:
                logger.warning(
                    "Fallback Gemini model %s returned 404 and is not available to this API key. "
                    "Set GEMINI_FALLBACK_MODEL in .env to a current Flash or Flash Lite model.",
                    self._fallback_model,
                )
                raise LLMError(
                    fallback_model_not_found_message(self._fallback_model)
                ) from fallback_exc
            except (LLMUnavailableError, LLMRateLimitError) as fallback_exc:
                raise LLMUnavailableError(
                    f"{exc} Fallback model {self._fallback_model} also failed."
                ) from fallback_exc

    async def _generate_once(
        self,
        model: str,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None,
    ) -> StructuredLLMResult[T]:
        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
        except Exception as exc:
            wrapped = wrap_gemini_exception(exc)
            if isinstance(wrapped, LLMModelNotFoundError):
                raise LLMModelNotFoundError(
                    f"Gemini model '{model}' is not available (404)."
                ) from exc
            raise wrapped from exc

        usage_metadata = getattr(response, "usage_metadata", None)
        usage = LLMUsage(
            model=model,
            input_tokens=getattr(usage_metadata, "prompt_token_count", None),
            output_tokens=getattr(usage_metadata, "candidates_token_count", None),
        )
        raw_text = response.text or ""
        parsed = response.parsed
        if parsed is None:
            if not raw_text:
                raise LLMInvalidOutputError("Gemini returned empty structured output")
            try:
                parsed = response_schema.model_validate_json(raw_text)
            except ValidationError as exc:
                raise LLMInvalidOutputError(
                    "Gemini output did not match the response schema"
                ) from exc
        elif isinstance(parsed, dict):
            try:
                parsed = response_schema.model_validate(parsed)
            except ValidationError as exc:
                raise LLMInvalidOutputError(
                    "Gemini output did not match the response schema"
                ) from exc
        elif not isinstance(parsed, response_schema):
            try:
                parsed = response_schema.model_validate(parsed)
            except ValidationError as exc:
                raise LLMInvalidOutputError(
                    "Gemini output did not match the response schema"
                ) from exc

        return StructuredLLMResult(parsed=parsed, raw_text=raw_text, usage=usage)


def get_llm_provider() -> GeminiProvider:
    return GeminiProvider()
