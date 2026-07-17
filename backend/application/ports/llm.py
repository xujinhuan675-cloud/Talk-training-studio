# input: LLM provider SDKs (OpenAI, Azure, Anthropic, vLLM)
# output: LLMPort Protocol, LLM provider metadata registry/serialization, message/response types
# owner: unknown
# pos: application port - provider-neutral LLM invocation boundary; update this header and folder docs when changed
"""Application-owned LLM port abstraction (hexagonal architecture).

Defines the minimal protocol needed by application use cases so that
the application layer does not depend on specific LLM provider details.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


_SENSITIVE_METADATA_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "auth_header",
    "authtoken",
    "auth_token",
    "bearer_token",
    "bearertoken",
    "client_secret",
    "clientsecret",
    "credential",
    "credentials",
    "default_headers",
    "password",
    "private_key",
    "privatekey",
    "proxy_authorization",
    "refresh_token",
    "refreshtoken",
    "secret",
    "token",
}


def _metadata_key_forms(key: object) -> tuple[str, str]:
    lowered = str(key).lower()
    snake = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    compact = "".join(ch for ch in lowered if ch.isalnum())
    return snake, compact


def _is_sensitive_metadata_key(key: object) -> bool:
    snake, compact = _metadata_key_forms(key)
    if snake in _SENSITIVE_METADATA_KEYS or compact in _SENSITIVE_METADATA_KEYS:
        return True
    return snake.endswith(("_api_key", "_authorization", "_password", "_secret", "_token"))


def _sanitize_metadata_extra(value: object) -> object:
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested_value in value.items():
            if _is_sensitive_metadata_key(raw_key):
                continue
            sanitized[str(raw_key)] = _sanitize_metadata_extra(nested_value)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_metadata_extra(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_metadata_extra(item) for item in value]
    return value


def _metadata_payload(
    fields: dict[str, object | None],
    extra: dict[str, object],
    *,
    include_none: bool,
) -> dict[str, object]:
    payload = {key: value for key, value in fields.items() if value is not None or include_none}
    for key, value in extra.items():
        if _is_sensitive_metadata_key(key):
            continue
        payload.setdefault(key, _sanitize_metadata_extra(value))
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


def build_llm_model_specs(registry: LLMProviderMetadata) -> list[dict[str, object]]:
    """Build TalkWise model specs from a provider registry.

    Each spec is a stable, UI-ready model selection profile.
    """
    specs: list[dict[str, object]] = []
    seen: set[str] = set()
    endpoint_model_keys: set[tuple[str, Optional[str], str]] = set()

    def append_model(model: LLMModelMetadata, endpoint: LLMEndpointMetadata | None = None) -> None:
        provider = (model.provider or endpoint.provider) if endpoint else model.provider
        provider = provider or registry.provider
        endpoint_url = model.endpoint if model.endpoint is not None else (
            endpoint.endpoint if endpoint else registry.endpoint
        )
        wire_api = endpoint.wire_api if endpoint else registry.wire_api
        endpoint_model_key = (provider, endpoint_url, model.name)
        if endpoint is None and endpoint_model_key in endpoint_model_keys:
            return
        if endpoint is not None:
            endpoint_model_keys.add(endpoint_model_key)
        endpoint_default = endpoint.default_model if endpoint else registry.default_model
        capabilities = _safe_string_list(
            model.extra.get("capabilities")
            or (endpoint.extra.get("capabilities") if endpoint else None)
            or ["text", "streaming"]
        )
        tags = _safe_string_list(model.extra.get("tags") or capabilities)
        endpoint_enabled = _safe_bool(endpoint.extra.get("enabled"), default=True) if endpoint else True
        endpoint_selectable = (
            _safe_bool(endpoint.extra.get("selectable"), default=endpoint_enabled)
            if endpoint
            else endpoint_enabled
        )
        enabled = endpoint_enabled and _safe_bool(model.extra.get("enabled"), default=True)
        selectable = _safe_bool(model.extra.get("selectable"), default=enabled)
        show_in_menu = _safe_bool(
            model.extra.get("show_in_menu", model.extra.get("showInMenu")),
            default=True,
        )
        if not show_in_menu:
            return
        endpoint_key = _llm_endpoint_config_key(provider, endpoint_url, wire_api)
        spec_name = _llm_model_spec_name(provider, endpoint_url, wire_api, model.name)
        if spec_name in seen:
            return
        seen.add(spec_name)

        label = _safe_text(model.display_name) or _safe_text(model.extra.get("label")) or model.name
        is_default = bool(model.is_default or (endpoint_default and model.name == endpoint_default))
        spec: dict[str, object] = {
            "id": spec_name,
            "model_spec_id": spec_name,
            "model_spec_name": spec_name,
            "name": spec_name,
            "label": label,
            "display_label": label,
            "provider": provider,
            "endpoint": endpoint_url,
            "endpoint_key": endpoint_key,
            "wire_api": wire_api,
            "model": model.name,
            "group": provider,
            "default": is_default,
            "is_default": is_default,
            "enabled": enabled,
            "selectable": enabled and endpoint_selectable and selectable and show_in_menu,
            "show_in_menu": show_in_menu,
            "capabilities": capabilities,
            "tags": tags,
        }
        description = _safe_text(model.extra.get("description"))
        if description:
            spec["description"] = description
        if model.context_window is not None:
            spec["context_window"] = model.context_window
        if model.max_output_tokens is not None:
            spec["max_output_tokens"] = model.max_output_tokens
        pricing = _safe_mapping(model.extra.get("pricing") or model.extra.get("tokenomics"))
        if pricing:
            spec["pricing"] = pricing
        cost = _safe_mapping(model.extra.get("cost"))
        if cost:
            spec["cost"] = cost
        for cost_key in (
            "input_cost_per_token",
            "output_cost_per_token",
            "prompt_cost_per_token",
            "completion_cost_per_token",
            "input_cost_per_1m_tokens",
            "output_cost_per_1m_tokens",
        ):
            if cost_key in model.extra:
                spec[cost_key] = _sanitize_metadata_extra(model.extra[cost_key])
        specs.append(spec)

    for endpoint in registry.endpoints:
        for model in endpoint.models:
            append_model(model, endpoint)
    for model in registry.models:
        append_model(model)
    return specs


def build_llm_endpoints_config(registry: LLMProviderMetadata) -> dict[str, dict[str, object]]:
    """Build endpoint config descriptors keyed by provider/endpoint/wire API."""
    config: dict[str, dict[str, object]] = {}
    endpoints = registry.endpoints or [
        LLMEndpointMetadata(
            provider=registry.provider,
            endpoint=registry.endpoint,
            wire_api=registry.wire_api,
            default_model=registry.default_model,
            models=registry.models,
        )
    ]
    for order, endpoint in enumerate(endpoints):
        key = _llm_endpoint_config_key(endpoint.provider, endpoint.endpoint, endpoint.wire_api)
        endpoint_enabled = _safe_bool(endpoint.extra.get("enabled"), default=True)
        endpoint_selectable = _safe_bool(endpoint.extra.get("selectable"), default=endpoint_enabled)
        model_names: list[str] = []
        model_spec_ids: list[str] = []
        for model in endpoint.models:
            if not _safe_bool(model.extra.get("enabled"), default=True):
                continue
            if not _safe_bool(
                model.extra.get("show_in_menu", model.extra.get("showInMenu")),
                default=True,
            ):
                continue
            model_names.append(model.name)
            model_spec_ids.append(
                _llm_model_spec_name(
                    model.provider or endpoint.provider,
                    model.endpoint if model.endpoint is not None else endpoint.endpoint,
                    endpoint.wire_api,
                    model.name,
                )
            )
        model_display_label = _safe_text(endpoint.extra.get("model_display_label")) or _safe_text(
            endpoint.extra.get("modelDisplayLabel")
        )
        label = _safe_text(endpoint.extra.get("label")) or endpoint.provider
        config[key] = {
            "key": key,
            "order": order,
            "provider": endpoint.provider,
            "label": label,
            "display_label": label,
            "endpoint": endpoint.endpoint,
            "wire_api": endpoint.wire_api,
            "default_model": endpoint.default_model,
            "enabled": endpoint_enabled,
            "selectable": endpoint_enabled and endpoint_selectable,
            "model_display_label": model_display_label or endpoint.provider,
            "available_models": model_names,
            "models": model_names,
            "model_spec_ids": model_spec_ids,
            "capabilities": _safe_string_list(endpoint.extra.get("capabilities") or ["text", "streaming"]),
            "tags": _safe_string_list(endpoint.extra.get("tags")),
        }
        pricing = _safe_mapping(endpoint.extra.get("pricing") or endpoint.extra.get("tokenomics"))
        if pricing:
            config[key]["pricing"] = pricing
        cost = _safe_mapping(endpoint.extra.get("cost"))
        if cost:
            config[key]["cost"] = cost
    return config


def build_llm_registry_artifacts(registry: LLMProviderMetadata) -> dict[str, object]:
    """Return model specs and endpoint configs for registry API payloads."""
    return {
        "model_specs": build_llm_model_specs(registry),
        "endpoints_config": build_llm_endpoints_config(registry),
    }


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


def _safe_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _safe_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _safe_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    sanitized = _sanitize_metadata_extra(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _llm_endpoint_config_key(
    provider: str,
    endpoint: Optional[str],
    wire_api: Optional[str],
) -> str:
    return "::".join([provider, endpoint or "", wire_api or ""])


def _llm_model_spec_name(
    provider: str,
    endpoint: Optional[str],
    wire_api: Optional[str],
    model: str,
) -> str:
    return "::".join([provider, endpoint or "", wire_api or "", model])


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
