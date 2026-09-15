from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    model: str
    input_tokens: int | None
    output_tokens: int | None


@dataclass(frozen=True)
class StructuredLLMResult(Generic[T]):
    parsed: T
    raw_text: str
    usage: LLMUsage


class LLMError(Exception):
    """Base error for LLM provider failures."""


class LLMRateLimitError(LLMError):
    """Raised when the provider returns a transient rate limit."""


class LLMUnavailableError(LLMError):
    """Raised on 503/500 responses or network timeouts that should be retried."""


class LLMBillingError(LLMError):
    """Raised when the provider rejects the request for billing or credit reasons."""


class LLMPermissionError(LLMError):
    """Raised on 401/403 or API-key permission failures that should fail fast."""


class LLMModelNotFoundError(LLMError):
    """Raised when the requested Gemini model returns 404 NOT_FOUND."""


class LLMInvalidOutputError(LLMError):
    """Raised when structured output is missing or fails schema validation."""


class LLMProvider(Protocol):
    async def generate_structured(
        self,
        prompt: str,
        response_schema: type[T],
        system_instruction: str | None = None,
    ) -> StructuredLLMResult[T]:
        """Generate a response that validates against a Pydantic schema."""
        ...
