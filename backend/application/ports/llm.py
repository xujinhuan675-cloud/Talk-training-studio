# input: LLM provider SDKs (OpenAI, Azure, Anthropic, vLLM)
# output: LLMPort Protocol, LLMProviderMetadata, LLMMessage, LLMResponse, LLMChunk data types
# owner: unknown
# pos: application port - provider-neutral LLM invocation boundary; update this header and folder docs when changed
"""Application-owned LLM port abstraction (hexagonal architecture).

Defines the minimal protocol needed by application use cases so that
the application layer does not depend on specific LLM provider details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


@dataclass
class LLMModelMetadata:
    """Provider-neutral model descriptor for endpoint/model registries."""

    name: str
    provider: Optional[str] = None
    endpoint: Optional[str] = None
    display_name: Optional[str] = None
    is_default: bool = False
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class LLMEndpointMetadata:
    """Provider-neutral endpoint descriptor with its available models."""

    provider: str
    endpoint: Optional[str] = None
    wire_api: Optional[str] = None
    default_model: Optional[str] = None
    models: list[LLMModelMetadata] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class LLMProviderMetadata:
    """Stable provider identity exposed by an LLM adapter."""

    provider: str
    default_model: Optional[str] = None
    endpoint: Optional[str] = None
    wire_api: Optional[str] = None
    max_retries: Optional[int] = None
    models: list[LLMModelMetadata] = field(default_factory=list)
    endpoints: list[LLMEndpointMetadata] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)


@dataclass
class LLMMessage:
    """A single message in a conversation sent to the LLM."""

    role: str  # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    """Non-streaming LLM response."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: Optional[str] = None


@dataclass
class LLMChunk:
    """A single chunk from a streaming LLM response."""

    content: str = ""
    model: str = ""
    finish_reason: Optional[str] = None
    # Token usage is typically available only in the final chunk.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@runtime_checkable
class LLMPort(Protocol):
    """Port for interacting with a Large Language Model."""

    @property
    def provider_metadata(self) -> LLMProviderMetadata: ...

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse: ...

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        *,
        schema: dict,
        schema_name: str = "output",
        schema_description: str = "",
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Generate a response that conforms to the given JSON schema.

        Uses provider-native structured output (e.g. Anthropic tool_choice,
        OpenAI function calling) so the result is guaranteed to be valid.

        Args:
            messages: Conversation messages.
            schema: JSON Schema dict describing the desired output shape.
            schema_name: Tool/function name used internally by the provider.
            schema_description: Human-readable description of the output.

        Returns:
            A dict matching the provided schema.
        """
        ...

    async def stream(
        self,
        messages: list[LLMMessage],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[LLMChunk]: ...
