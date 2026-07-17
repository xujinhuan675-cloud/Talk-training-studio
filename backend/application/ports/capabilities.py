# input: provider/model/agent/tool/MCP descriptors
# output: public, secret-free capability registry for runtime adapters
# owner: unknown
# pos: application port - capability registry boundary for future external chat-runtime auth/MCP/agent migration
"""Provider-neutral capability registry for chat and training runtimes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from application.ports.llm import LLMProviderMetadata, build_llm_model_specs

CapabilityKind = Literal["provider", "model", "agent", "tool", "mcp_server", "runtime"]
CapabilityStatus = Literal["available", "unavailable", "disabled", "unknown"]

_REGISTRY_VERSION = 1
_SECRET_KEYS = {
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


@dataclass(frozen=True)
class RuntimeCapability:
    """Public descriptor for a runtime capability or future adapter slot."""

    id: str
    kind: CapabilityKind
    name: str
    provider: str | None = None
    source: str | None = None
    status: CapabilityStatus = "available"
    enabled: bool = True
    configured: bool | None = None
    scopes: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "provider", _optional_text(self.provider))
        object.__setattr__(self, "source", _optional_text(self.source))
        object.__setattr__(self, "status", _required_text(self.status, "status"))
        object.__setattr__(self, "scopes", tuple(_string_list(self.scopes)))
        object.__setattr__(self, "required_roles", tuple(_string_list(self.required_roles)))
        object.__setattr__(self, "tags", tuple(_string_list(self.tags)))
        sanitized = sanitize_public_metadata(dict(self.metadata or {}))
        object.__setattr__(self, "metadata", sanitized if isinstance(sanitized, dict) else {})

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "enabled": self.enabled,
            "scopes": list(self.scopes),
            "required_roles": list(self.required_roles),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.source is not None:
            payload["source"] = self.source
        if self.configured is not None:
            payload["configured"] = self.configured
        return payload


@dataclass(frozen=True)
class RuntimeCapabilityRegistry:
    """Secret-free capability catalog exported to APIs and tests."""

    provider: str = "talkwise"
    version: int = _REGISTRY_VERSION
    capabilities: tuple[RuntimeCapability, ...] = ()

    def to_dict(self) -> dict[str, object]:
        items = [capability.to_dict() for capability in self.capabilities]
        by_kind: dict[str, list[dict[str, object]]] = {}
        for item in items:
            by_kind.setdefault(str(item["kind"]), []).append(item)
        return {
            "provider": self.provider,
            "version": self.version,
            "capabilities": items,
            "by_kind": by_kind,
        }


def build_text_runtime_capability_registry(
    registry: LLMProviderMetadata,
    *,
    model_specs: Iterable[Mapping[str, object]] | None = None,
    include_agent_tool_placeholders: bool = True,
) -> RuntimeCapabilityRegistry:
    """Project the text runtime registry into a future-proof capability catalog."""

    capabilities: list[RuntimeCapability] = []
    endpoint_caps = _provider_capabilities(registry)
    capabilities.extend(endpoint_caps)
    capabilities.extend(
        _model_capabilities(
            registry,
            model_specs=model_specs,
        )
    )
    if include_agent_tool_placeholders:
        capabilities.extend(_future_agent_tool_mcp_capabilities())
    return RuntimeCapabilityRegistry(provider=registry.provider, capabilities=tuple(capabilities))


def sanitize_public_metadata(value: object) -> object:
    """Return a JSON-like metadata structure with secret-bearing keys removed."""

    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested_value in value.items():
            if _is_secret_key(raw_key):
                continue
            sanitized[str(raw_key)] = sanitize_public_metadata(nested_value)
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_public_metadata(item) for item in value]
    return value


def _provider_capabilities(registry: LLMProviderMetadata) -> list[RuntimeCapability]:
    endpoints = registry.endpoints
    if not endpoints:
        return [
            RuntimeCapability(
                id=f"provider:{registry.provider}",
                kind="provider",
                name=registry.provider,
                provider=registry.provider,
                source="llm_registry",
                configured=bool(registry.default_model),
                scopes=("chat", "training"),
                tags=("text", "provider"),
                metadata={
                    "default_model": registry.default_model,
                    "endpoint": registry.endpoint,
                    "wire_api": registry.wire_api,
                },
            )
        ]

    capabilities: list[RuntimeCapability] = []
    for endpoint in endpoints:
        endpoint_key = _capability_key(
            "provider",
            endpoint.provider,
            endpoint.endpoint or "",
            endpoint.wire_api or "",
        )
        enabled = _safe_bool(endpoint.extra.get("enabled"), default=True)
        capabilities.append(
            RuntimeCapability(
                id=endpoint_key,
                kind="provider",
                name=endpoint.provider,
                provider=endpoint.provider,
                source="llm_registry",
                status="available" if enabled else "disabled",
                enabled=enabled,
                configured=bool(endpoint.default_model),
                scopes=("chat", "training"),
                tags=("text", "provider"),
                metadata={
                    "default_model": endpoint.default_model,
                    "endpoint": endpoint.endpoint,
                    "wire_api": endpoint.wire_api,
                    **dict(endpoint.extra),
                },
            )
        )
    return capabilities


def _model_capabilities(
    registry: LLMProviderMetadata,
    *,
    model_specs: Iterable[Mapping[str, object]] | None = None,
) -> list[RuntimeCapability]:
    specs = list(model_specs) if model_specs is not None else build_llm_model_specs(registry)
    capabilities: list[RuntimeCapability] = []
    for spec in specs:
        spec_id = _required_text(
            spec.get("model_spec_id") or spec.get("id") or spec.get("name"),
            "model_spec_id",
        )
        enabled = _safe_bool(spec.get("enabled"), default=True)
        selectable = _safe_bool(spec.get("selectable"), default=enabled)
        provider = _optional_text(spec.get("provider")) or registry.provider
        capabilities.append(
            RuntimeCapability(
                id=f"model:{spec_id}",
                kind="model",
                name=_optional_text(spec.get("label")) or _optional_text(spec.get("model")) or spec_id,
                provider=provider,
                source="llm_registry",
                status="available" if enabled else "disabled",
                enabled=enabled,
                configured=enabled and selectable,
                scopes=("chat", "training"),
                tags=tuple(_string_list(spec.get("tags") or spec.get("capabilities"))),
                metadata={
                    "model": spec.get("model"),
                    "model_spec_id": spec_id,
                    "endpoint": spec.get("endpoint"),
                    "endpoint_key": spec.get("endpoint_key"),
                    "wire_api": spec.get("wire_api"),
                    "capabilities": _string_list(spec.get("capabilities")),
                    "selectable": selectable,
                    "default": _safe_bool(spec.get("default"), default=False),
                    "context_window": spec.get("context_window"),
                    "max_output_tokens": spec.get("max_output_tokens"),
                    "pricing": spec.get("pricing"),
                    "cost": spec.get("cost"),
                },
            )
        )
    return capabilities


def _future_agent_tool_mcp_capabilities() -> list[RuntimeCapability]:
    roles = ("admin", "leader", "staff")
    return [
        RuntimeCapability(
            id="agent:conversation_agent_config",
            kind="agent",
            name="Conversation Agent Config",
            source="conversation_agent_config",
            configured=True,
            scopes=("chat", "training"),
            required_roles=roles,
            tags=("agent", "adapter"),
            metadata={
                "adapter": "ConversationApplicationService.agent_config",
                "migration_boundary": "future external chat-runtime agent adapter",
            },
        ),
        RuntimeCapability(
            id="tool:tool_executor_port",
            kind="tool",
            name="Tool Executor Port",
            source="application.ports.tool_executor",
            status="disabled",
            enabled=False,
            configured=False,
            scopes=("agent", "mcp"),
            required_roles=roles,
            tags=("tool", "port"),
            metadata={
                "port": "ToolExecutorPort",
                "reason": "No concrete tool executor adapter is registered yet",
            },
        ),
        RuntimeCapability(
            id="mcp:mcp_server_registry",
            kind="mcp_server",
            name="MCP Server Registry",
            source="mcp_dependency",
            status="disabled",
            enabled=False,
            configured=False,
            scopes=("agent", "tool"),
            required_roles=roles,
            tags=("mcp", "registry"),
            metadata={
                "dependency": "mcp>=1.0,<2",
                "reason": "MCP server adapters are not registered yet",
            },
        ),
    ]


def _capability_key(*parts: object) -> str:
    return ":".join(_required_text(part, "capability_key_part") for part in parts)


def _is_secret_key(key: object) -> bool:
    lowered = str(key).lower()
    snake = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    compact = "".join(ch for ch in lowered if ch.isalnum())
    if snake in _SECRET_KEYS or compact in _SECRET_KEYS:
        return True
    return snake.endswith(("_api_key", "_authorization", "_password", "_secret", "_token"))


def _required_text(value: object, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text and text not in result:
            result.append(text)
    return result


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
