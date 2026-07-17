# input: LLM provider SDKs (OpenAI, Azure, Anthropic, vLLM)
# output: LLMPort Protocol, LLM provider metadata registry/serialization, message/response types
# owner: unknown
# pos: application port - provider-neutral LLM invocation boundary; update this header and folder docs when changed
"""Application-owned LLM port abstraction (hexagonal architecture).

Defines the minimal protocol needed by application use cases so that
the application layer does not depend on specific LLM provider details.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


def _metadata_payload(
    fields: dict[str, object | None],
    extra: dict[str, object],
    *,
    include_none: bool,
) -> dict[str, object]:
    payload = {key: value for key, value in fields.items() if value is not None or include_none}
    for key, value in extra.items():
        payload.setdefault(key, value)
    return payload


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

    def to_dict(self, *, include_none: bool = False) -> dict[str, object]:
        """Serialize this model descriptor for API/storage metadata payloads."""
        return _metadata_payload(
            {
                "name": self.name,
                "provider": self.provider,
                "endpoint": self.endpoint,
                "display_name": self.display_name,
                "is_default": self.is_default,
                "context_window": self.context_window,
                "max_output_tokens": self.max_output_tokens,
            },
            self.extra,
            include_none=include_none,
        )


@dataclass
class LLMEndpointMetadata:
    """Provider-neutral endpoint descriptor with its available models."""

    provider: str
    endpoint: Optional[str] = None
    wire_api: Optional[str] = None
    default_model: Optional[str] = None
    models: list[LLMModelMetadata] = field(default_factory=list)
    extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self, *, include_none: bool = False) -> dict[str, object]:
        """Serialize this endpoint and its model catalog."""
        payload = _metadata_payload(
            {
                "provider": self.provider,
                "endpoint": self.endpoint,
                "wire_api": self.wire_api,
                "default_model": self.default_model,
            },
            self.extra,
            include_none=include_none,
        )
        payload["models"] = [model.to_dict(include_none=include_none) for model in self.models]
        return payload


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

    def to_dict(self, *, include_none: bool = False) -> dict[str, object]:
        """Serialize this provider or registry catalog into a stable nested payload."""
        payload = _metadata_payload(
            {
                "provider": self.provider,
                "default_model": self.default_model,
                "endpoint": self.endpoint,
                "wire_api": self.wire_api,
                "max_retries": self.max_retries,
            },
            self.extra,
            include_none=include_none,
        )
        payload["models"] = [model.to_dict(include_none=include_none) for model in self.models]
        payload["endpoints"] = [
            endpoint.to_dict(include_none=include_none) for endpoint in self.endpoints
        ]
        return payload


def build_llm_provider_registry(
    provider_metadata: Iterable[LLMProviderMetadata],
    *,
    provider: str = "talkwise",
    default_model: Optional[str] = None,
    extra: Optional[dict[str, object]] = None,
) -> LLMProviderMetadata:
    """Combine provider descriptors into a TalkWise-level endpoint/model catalog."""
    metadata_items = list(provider_metadata)
    registry_models: list[LLMModelMetadata] = []
    registry_endpoints: list[LLMEndpointMetadata] = []
    endpoint_by_key: dict[tuple[str, Optional[str], Optional[str]], LLMEndpointMetadata] = {}
    model_keys: set[tuple[Optional[str], Optional[str], str]] = set()

    def append_registry_model(model: LLMModelMetadata) -> None:
        key = (model.provider, model.endpoint, model.name)
        if key in model_keys:
            return
        model_keys.add(key)
        registry_models.append(model)

    for metadata in metadata_items:
        base_models = [
            _normalize_model_metadata(
                model,
                provider=metadata.provider,
                endpoint=metadata.endpoint,
                default_model=metadata.default_model,
            )
            for model in metadata.models
        ]
        if not base_models and metadata.default_model:
            base_models = [
                LLMModelMetadata(
                    name=metadata.default_model,
                    provider=metadata.provider,
                    endpoint=metadata.endpoint,
                    is_default=True,
                )
            ]

        for model in base_models:
            append_registry_model(model)

        source_endpoints = metadata.endpoints or [
            LLMEndpointMetadata(
                provider=metadata.provider,
                endpoint=metadata.endpoint,
                wire_api=metadata.wire_api,
                default_model=metadata.default_model,
                models=base_models,
            )
        ]

        for endpoint in source_endpoints:
            endpoint_default_model = endpoint.default_model or metadata.default_model
            endpoint_models = endpoint.models or base_models
            endpoint_key = (endpoint.provider, endpoint.endpoint, endpoint.wire_api)
            normalized_endpoint = endpoint_by_key.get(endpoint_key)
            if normalized_endpoint is None:
                normalized_endpoint = LLMEndpointMetadata(
                    provider=endpoint.provider,
                    endpoint=endpoint.endpoint,
                    wire_api=endpoint.wire_api,
                    default_model=endpoint_default_model,
                    models=[],
                    extra=dict(endpoint.extra),
                )
                endpoint_by_key[endpoint_key] = normalized_endpoint
                registry_endpoints.append(normalized_endpoint)
            elif normalized_endpoint.default_model is None:
                normalized_endpoint.default_model = endpoint_default_model

            endpoint_model_keys = {
                (model.provider, model.endpoint, model.name) for model in normalized_endpoint.models
            }
            for model in endpoint_models:
                normalized_model = _normalize_model_metadata(
                    model,
                    provider=endpoint.provider,
                    endpoint=endpoint.endpoint,
                    default_model=endpoint_default_model,
                )
                endpoint_model_key = (
                    normalized_model.provider,
                    normalized_model.endpoint,
                    normalized_model.name,
                )
                if endpoint_model_key not in endpoint_model_keys:
                    endpoint_model_keys.add(endpoint_model_key)
                    normalized_endpoint.models.append(normalized_model)
                append_registry_model(normalized_model)

    resolved_default_model = default_model or next(
        (metadata.default_model for metadata in metadata_items if metadata.default_model),
        None,
    )
    return LLMProviderMetadata(
        provider=provider,
        default_model=resolved_default_model,
        models=registry_models,
        endpoints=registry_endpoints,
        extra=dict(extra or {}),
    )


def _normalize_model_metadata(
    model: LLMModelMetadata,
    *,
    provider: str,
    endpoint: Optional[str],
    default_model: Optional[str],
) -> LLMModelMetadata:
    return replace(
        model,
        provider=model.provider or provider,
        endpoint=model.endpoint if model.endpoint is not None else endpoint,
        is_default=model.is_default or bool(default_model and model.name == default_model),
    )


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
