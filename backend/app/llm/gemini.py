import logging
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.base import (
    LLMError,
    LLMInvalidOutputError,
    LLMRateLimitError,
    LLMUsage,
    StructuredLLMResult,
)
from app.llm.retry import with_retry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _is_rate_limit(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if code == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "rate limit" in text


class GeminiProvider:
    """Google Gemini implementation of the swappable LLM provider interface."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured")
        self._model = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> StructuredLLMResult[T]:
        async def _call() -> StructuredLLMResult[T]:
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        response_schema=response_schema,
                    ),
                )
            except Exception as exc:
                if _is_rate_limit(exc):
                    raise LLMRateLimitError(str(exc)) from exc
                if isinstance(exc, genai_errors.ClientError):
                    raise LLMError(f"Gemini request failed: {exc}") from exc
                raise

            usage_metadata = getattr(response, "usage_metadata", None)
            usage = LLMUsage(
                model=self._model,
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

        return await with_retry(_call)


def get_llm_provider() -> GeminiProvider:
    return GeminiProvider()
