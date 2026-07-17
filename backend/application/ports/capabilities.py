# input: LLM registry descriptors plus optional agent/tool/MCP inventory descriptors
# output: public, secret-free runtime capability registry with readiness diagnostics
# owner: unknown
# pos: application port - capability inventory/readiness boundary for external chat-runtime MCP/agent migration
"""Provider-neutral capability registry for chat and training runtimes."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from application.ports.llm import LLMProviderMetadata, build_llm_model_specs

CapabilityKind = Literal["provider", "model", "agent", "tool", "mcp_server", "runtime"]
CapabilityStatus = Literal[
    "ready",
    "warning",
    "blocked",
    "missingDependency",
    "disabled",
    "unknown",
]

_REGISTRY_VERSION = 2
_SECRET_KEYS = {
    "access_token",
    "accesstoken",
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
    "cookie",
    "credential",
    "credentials",
    "default_headers",
    "id_token",
    "idtoken",
    "jwt",
    "openai_api_key",
    "openaiapikey",
    "password",
    "private_key",
    "privatekey",
    "proxy_authorization",
    "refresh_token",
    "refreshtoken",
    "secret",
    "session_token",
    "sessiontoken",
    "set_cookie",
    "setcookie",
    "token",
}
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(\bbearer\s+)[^\s,;}\]]+"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{3,}\b"),
    re.compile(
        r"(?i)\b(?:api[_-]?key|apikey|authorization|password|secret|token)"
        r"\s*[:=]\s*[^\s,;}\]]+"
    ),
)
_STATUS_ALIASES = {
    "available": "ready",
    "enabled": "ready",
    "unavailable": "blocked",
    "missing_dependency": "missingDependency",
    "missing-dependency": "missingDependency",
}
_VALID_STATUSES = {"ready", "warning", "blocked", "missingDependency", "disabled", "unknown"}
_TOOL_CAPABILITY_MARKERS = {
    "agent",
    "function",
    "function_calling",
    "functions",
    "tool",
    "tool_calling",
    "tools",
}
_MCP_CAPABILITY_MARKERS = {
    "mcp",
    "mcp_server",
    "mcp_servers",
    "mcp_tool",
    "mcp_tools",
}
_AGENT_CONFIG_COLLECTION_KEYS = ("agents", "agent_configs", "agentConfigs", "items", "list")
_TOOL_CONFIG_COLLECTION_KEYS = ("tools", "tool_configs", "toolConfigs", "items", "list")
_MCP_SERVER_COLLECTION_KEYS = ("mcp_servers", "mcpServers", "servers", "items", "list")
_DESCRIPTOR_KEYS = {
    "args",
    "available",
    "capabilities",
    "command",
    "configured",
    "dependencies",
    "dependency",
    "description",
    "enabled",
    "endpoint",
    "env",
    "id",
    "label",
    "metadata",
    "missingDependency",
    "missingDependencies",
    "missing_dependency",
    "missing_dependencies",
    "model",
    "model_spec_id",
    "modelSpecId",
    "name",
    "required_roles",
    "requires_mcp",
    "requiresMcp",
    "scopes",
    "source",
    "status",
    "tags",
    "tool",
    "tools",
    "transport",
    "type",
    "url",
}
_PUBLIC_DESCRIPTOR_EXCLUDE_KEYS = {
    "api_key",
    "apikey",
    "created_at",
    "enabled",
    "id",
    "metadata",
    "name",
    "password",
    "prompt",
    "secret",
    "system_prompt",
    "token",
    "updated_at",
}
_DEFAULT_AGENT_ROLES = ("admin", "leader", "staff")


@dataclass(frozen=True)
class RuntimeCapability:
    """Public descriptor for a runtime capability or adapter inventory item."""

    id: str
    kind: CapabilityKind
    name: str
    provider: str | None = None
    source: str | None = None
    status: CapabilityStatus = "ready"
    enabled: bool = True
    ready: bool | None = None
    configured: bool | None = None
    scopes: tuple[str, ...] = ()
    required_roles: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    blocking_reasons: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    warnings: Sequence[Mapping[str, object]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_text(self.id, "id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "name", _required_text(self.name, "name"))
        object.__setattr__(self, "provider", _optional_text(self.provider))
        object.__setattr__(self, "source", _optional_text(self.source))

        enabled = _safe_bool(self.enabled, default=True)
        status = _normalize_status(self.status, enabled=enabled)
        ready = _safe_bool(self.ready, default=status == "ready") if self.ready is not None else status == "ready"
        if status in {"blocked", "missingDependency", "disabled", "unknown", "warning"}:
            ready = False
        if not enabled and status == "ready":
            status = "disabled"
            ready = False

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "enabled", enabled)
        object.__setattr__(self, "ready", ready)
        if self.configured is not None:
            object.__setattr__(
                self,
                "configured",
                _safe_bool(self.configured, default=False),
            )
        object.__setattr__(self, "scopes", tuple(_string_list(self.scopes)))
        object.__setattr__(self, "required_roles", tuple(_string_list(self.required_roles)))
        object.__setattr__(self, "tags", tuple(_string_list(self.tags)))

        sanitized = sanitize_public_metadata(dict(self.metadata or {}))
        object.__setattr__(self, "metadata", sanitized if isinstance(sanitized, dict) else {})
        object.__setattr__(
            self,
            "blocking_reasons",
            tuple(_public_issue(issue) for issue in self.blocking_reasons or ()),
        )
        object.__setattr__(
            self,
            "warnings",
            tuple(_public_issue(issue) for issue in self.warnings or ()),
        )

    def to_dict(self) -> dict[str, object]:
        blocking_reasons = [dict(reason) for reason in self.blocking_reasons]
        warnings = [dict(warning) for warning in self.warnings]
        payload: dict[str, object] = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "enabled": self.enabled,
            "ready": bool(self.ready),
            "scopes": list(self.scopes),
            "required_roles": list(self.required_roles),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
            "readiness": {
                "ready": bool(self.ready),
                "status": self.status,
                "blockingReasons": blocking_reasons,
                "warnings": warnings,
            },
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
            "inventory": _inventory_payload(items),
            "readiness": _registry_readiness(items),
            "capabilities": items,
            "by_kind": by_kind,
        }


def build_text_runtime_capability_registry(
    registry: LLMProviderMetadata,
    *,
    model_specs: Iterable[Mapping[str, object]] | None = None,
    agent_configs: object | None = None,
    tool_configs: object | None = None,
    mcp_servers: object | None = None,
    include_agent_tool_placeholders: bool = True,
) -> RuntimeCapabilityRegistry:
    """Project text runtime inventory into a public capability catalog.

    This function intentionally only builds inventory/readiness descriptors. It does not start
    MCP servers, execute tools, or validate remote network reachability.
    """

    specs = list(model_specs) if model_specs is not None else build_llm_model_specs(registry)
    provider_caps = _provider_capabilities(registry)
    model_caps = _model_capabilities(registry, model_specs=specs)
    capabilities: list[RuntimeCapability] = [*provider_caps, *model_caps]

    if include_agent_tool_placeholders:
        model_summary = _model_inventory_summary(model_caps)
        mcp_caps = _mcp_server_capabilities(mcp_servers)
        tool_caps = _tool_capabilities(
            tool_configs,
            model_summary=model_summary,
            mcp_capabilities=mcp_caps,
        )
        agent_caps = _agent_capabilities(
            agent_configs,
            model_summary=model_summary,
        )
        capabilities.extend(agent_caps)
        capabilities.extend(tool_caps)
        capabilities.extend(mcp_caps)

    return RuntimeCapabilityRegistry(provider=registry.provider, capabilities=tuple(capabilities))


def sanitize_public_metadata(value: object) -> object:
    """Return a JSON-like metadata structure with secret-bearing keys/values removed."""

    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested_value in value.items():
            if _is_secret_key(raw_key):
                continue
            safe_value = sanitize_public_metadata(nested_value)
            if safe_value is not None:
                sanitized[str(raw_key)] = safe_value
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [sanitize_public_metadata(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    if isinstance(value, bytes | bytearray):
        return None
    return value


def _provider_capabilities(registry: LLMProviderMetadata) -> list[RuntimeCapability]:
    endpoints = registry.endpoints or [
        type(
            "EndpointView",
            (),
            {
                "provider": registry.provider,
                "endpoint": registry.endpoint,
                "wire_api": registry.wire_api,
                "default_model": registry.default_model,
                "models": registry.models,
                "extra": {},
            },
        )()
    ]

    capabilities: list[RuntimeCapability] = []
    for endpoint in endpoints:
        endpoint_key = _capability_key(
            "provider",
            endpoint.provider,
            endpoint.endpoint or "",
            endpoint.wire_api or "",
        )
        enabled = _enabled_from(endpoint.extra, default=True)
        configured_flag = _configured_flag(endpoint.extra, registry.extra)
        has_model = bool(endpoint.default_model or endpoint.models)
        configured = has_model if configured_flag is None else bool(configured_flag and has_model)
        status = "ready"
        reasons: list[dict[str, object]] = []
        if not enabled:
            status = "disabled"
        elif configured_flag is False:
            status = "blocked"
            reasons.append(
                _reason(
                    "LLM_PROVIDER_NOT_CONFIGURED",
                    "Configure an LLM provider API key or active client before using this endpoint.",
                    provider=endpoint.provider,
                    phase="configuration",
                )
            )
        elif not has_model:
            status = "blocked"
            reasons.append(
                _reason(
                    "MISSING_DEFAULT_MODEL",
                    "Register at least one model or default_model for this LLM endpoint.",
                    provider=endpoint.provider,
                    phase="configuration",
                )
            )
        capabilities.append(
            RuntimeCapability(
                id=endpoint_key,
                kind="provider",
                name=endpoint.provider,
                provider=endpoint.provider,
                source="llm_registry",
                status=status,
                enabled=enabled,
                configured=configured,
                scopes=("chat", "training"),
                tags=("text", "provider"),
                metadata={
                    "default_model": endpoint.default_model,
                    "endpoint": endpoint.endpoint,
                    "wire_api": endpoint.wire_api,
                    "models": [model.name for model in endpoint.models],
                    **dict(endpoint.extra),
                },
                blocking_reasons=tuple(reasons),
            )
        )
    return capabilities


def _model_capabilities(
    registry: LLMProviderMetadata,
    *,
    model_specs: Iterable[Mapping[str, object]] | None = None,
) -> list[RuntimeCapability]:
    specs = list(model_specs) if model_specs is not None else build_llm_model_specs(registry)
    registry_configured = _configured_flag(registry.extra)
    capabilities: list[RuntimeCapability] = []
    for spec in specs:
        spec_id = _required_text(
            spec.get("model_spec_id") or spec.get("id") or spec.get("name"),
            "model_spec_id",
        )
        enabled = _enabled_from(spec, default=True)
        selectable = _safe_bool(spec.get("selectable"), default=enabled)
        provider = _optional_text(spec.get("provider")) or registry.provider
        capability_labels = _string_list(spec.get("capabilities"))
        tags = _string_list(spec.get("tags")) or capability_labels
        status = "ready"
        reasons: list[dict[str, object]] = []
        if not enabled:
            status = "disabled"
        elif registry_configured is False:
            status = "blocked"
            reasons.append(
                _reason(
                    "LLM_PROVIDER_NOT_CONFIGURED",
                    "Configure the LLM provider before selecting this model.",
                    provider=provider,
                    phase="configuration",
                    metadata={"model_spec_id": spec_id},
                )
            )
        elif not selectable:
            status = "blocked"
            reasons.append(
                _reason(
                    "MODEL_NOT_SELECTABLE",
                    "This model is present in the registry but is not selectable for runtime use.",
                    provider=provider,
                    feature="model",
                    phase="configuration",
                    metadata={"model_spec_id": spec_id},
                )
            )
        capabilities.append(
            RuntimeCapability(
                id=f"model:{spec_id}",
                kind="model",
                name=_optional_text(spec.get("label")) or _optional_text(spec.get("model")) or spec_id,
                provider=provider,
                source="llm_registry",
                status=status,
                enabled=enabled,
                configured=enabled and selectable and registry_configured is not False,
                scopes=("chat", "training"),
                tags=tuple(tags),
                metadata={
                    "model": spec.get("model"),
                    "model_spec_id": spec_id,
                    "endpoint": spec.get("endpoint"),
                    "endpoint_key": spec.get("endpoint_key"),
                    "wire_api": spec.get("wire_api"),
                    "capabilities": capability_labels,
                    "selectable": selectable,
                    "default": _safe_bool(spec.get("default"), default=False),
                    "context_window": spec.get("context_window"),
                    "max_output_tokens": spec.get("max_output_tokens"),
                    "pricing": spec.get("pricing"),
                    "cost": spec.get("cost"),
                },
                blocking_reasons=tuple(reasons),
            )
        )
    return capabilities


def _agent_capabilities(
    agent_configs: object | None,
    *,
    model_summary: Mapping[str, object],
) -> list[RuntimeCapability]:
    descriptors = _descriptor_items(agent_configs, _AGENT_CONFIG_COLLECTION_KEYS)
    ready_model_count = int(model_summary.get("ready_model_count") or 0)
    available_model_keys = set(_string_list(model_summary.get("available_model_keys")))
    if not descriptors:
        status = "ready" if ready_model_count else "blocked"
        reasons: list[dict[str, object]] = []
        if not ready_model_count:
            reasons.append(
                _reason(
                    "NO_READY_TEXT_MODEL",
                    "At least one ready LLM model is required before the built-in conversation agent can run.",
                    phase="configuration",
                    feature="agent",
                )
            )
        return [
            RuntimeCapability(
                id="agent:talkwise_conversation_agent",
                kind="agent",
                name="TalkWise Conversation Agent",
                source="llm_registry",
                status=status,
                enabled=True,
                configured=bool(ready_model_count),
                scopes=("chat", "training"),
                required_roles=_DEFAULT_AGENT_ROLES,
                tags=("agent", "conversation", "training"),
                metadata={
                    "runtime": "conversation_message_tree",
                    "model_dependency": "llm_registry",
                    "migration_boundary": "future external chat-runtime agent adapter",
                    "ready_model_count": ready_model_count,
                    "tool_capable_model_count": model_summary.get("tool_capable_model_count", 0),
                    "mcp_capable_model_count": model_summary.get("mcp_capable_model_count", 0),
                },
                blocking_reasons=tuple(reasons),
            )
        ]

    capabilities: list[RuntimeCapability] = []
    for descriptor in descriptors:
        name = _descriptor_text(descriptor, ("name", "label", "id")) or "Agent Config"
        agent_id = _descriptor_text(descriptor, ("id", "name", "label")) or name
        model = _descriptor_text(descriptor, ("model", "model_spec_id", "modelSpecId"))
        enabled = _enabled_from(descriptor, default=True)
        status = "ready"
        reasons: list[dict[str, object]] = []
        if not enabled:
            status = "disabled"
        elif not ready_model_count:
            status = "blocked"
            reasons.append(
                _reason(
                    "NO_READY_TEXT_MODEL",
                    "At least one ready LLM model is required before this agent can run.",
                    phase="configuration",
                    feature="agent",
                    metadata={"agent": name},
                )
            )
        elif model and model not in available_model_keys:
            status = "blocked"
            reasons.append(
                _reason(
                    "AGENT_MODEL_NOT_READY",
                    f"Agent model '{model}' is not present as a ready model capability.",
                    phase="configuration",
                    feature="model",
                    metadata={"agent": name, "model": model},
                )
            )
        capabilities.append(
            RuntimeCapability(
                id=f"agent:{_slug(agent_id)}",
                kind="agent",
                name=name,
                source=_descriptor_text(descriptor, ("source",)) or "agent_config",
                status=status,
                enabled=enabled,
                configured=enabled and status == "ready",
                scopes=tuple(_string_list(_descriptor_value(descriptor, ("scopes",))) or ("chat", "training")),
                required_roles=tuple(
                    _string_list(_descriptor_value(descriptor, ("required_roles", "requiredRoles")))
                    or _DEFAULT_AGENT_ROLES
                ),
                tags=tuple(_string_list(_descriptor_value(descriptor, ("tags",))) or ("agent", "config")),
                metadata={
                    "model": model,
                    "ready_model_count": ready_model_count,
                    "config": _public_descriptor_metadata(descriptor),
                },
                blocking_reasons=tuple(reasons),
            )
        )
    return capabilities


def _tool_capabilities(
    tool_configs: object | None,
    *,
    model_summary: Mapping[str, object],
    mcp_capabilities: Sequence[RuntimeCapability],
) -> list[RuntimeCapability]:
    descriptors = _descriptor_items(tool_configs, _TOOL_CONFIG_COLLECTION_KEYS)
    tool_model_ids = _string_list(model_summary.get("tool_capable_model_ids"))
    ready_mcp_ids = {capability.id for capability in mcp_capabilities if capability.ready}
    has_ready_mcp = bool(ready_mcp_ids)
    capabilities: list[RuntimeCapability] = [
        _model_tool_capability(
            tool_model_ids=tool_model_ids,
            has_explicit_tools=bool(descriptors),
            has_ready_mcp=has_ready_mcp,
        )
    ]

    for descriptor in descriptors:
        name = _descriptor_text(descriptor, ("name", "label", "tool", "id")) or "Tool"
        tool_id = _descriptor_text(descriptor, ("id", "name", "tool", "label")) or name
        enabled = _enabled_from(descriptor, default=True)
        requires_mcp = _safe_bool(
            _descriptor_value(descriptor, ("requires_mcp", "requiresMcp")),
            default=bool(_descriptor_text(descriptor, ("mcp_server", "mcpServer", "server"))),
        )
        mcp_server = _descriptor_text(descriptor, ("mcp_server", "mcpServer", "server"))
        status = "ready"
        reasons: list[dict[str, object]] = []
        if not enabled:
            status = "disabled"
        elif not tool_model_ids:
            status = "blocked"
            reasons.append(
                _reason(
                    "NO_TOOL_CAPABLE_MODEL",
                    "Register at least one ready model with tool_calling/function_calling capability.",
                    phase="configuration",
                    feature="tool_calling",
                    metadata={"tool": name},
                )
            )
        elif requires_mcp and not has_ready_mcp:
            status = "missingDependency"
            reasons.append(
                _reason(
                    "MISSING_READY_MCP_SERVER",
                    "This tool requires an MCP server, but no ready MCP server is registered.",
                    phase="configuration",
                    feature="mcp_server",
                    dependency="mcp_server",
                    severity="warning",
                    metadata={"tool": name, "mcp_server": mcp_server},
                )
            )
        capabilities.append(
            RuntimeCapability(
                id=f"tool:{_slug(tool_id)}",
                kind="tool",
                name=name,
                source=_descriptor_text(descriptor, ("source",)) or "tool_config",
                status=status,
                enabled=enabled,
                configured=enabled and status == "ready",
                scopes=tuple(_string_list(_descriptor_value(descriptor, ("scopes",))) or ("agent", "mcp")),
                required_roles=tuple(
                    _string_list(_descriptor_value(descriptor, ("required_roles", "requiredRoles")))
                    or _DEFAULT_AGENT_ROLES
                ),
                tags=tuple(_string_list(_descriptor_value(descriptor, ("tags",))) or ("tool",)),
                metadata={
                    "mcp_server": mcp_server,
                    "tool_capable_model_ids": tool_model_ids,
                    "config": _public_descriptor_metadata(descriptor),
                },
                blocking_reasons=tuple(reasons),
            )
        )
    return capabilities


def _model_tool_capability(
    *,
    tool_model_ids: Sequence[str],
    has_explicit_tools: bool,
    has_ready_mcp: bool,
) -> RuntimeCapability:
    if not tool_model_ids:
        return RuntimeCapability(
            id="tool:llm_tool_calling",
            kind="tool",
            name="LLM Tool Calling",
            source="llm_registry",
            status="disabled",
            enabled=False,
            configured=False,
            scopes=("agent", "tool"),
            required_roles=_DEFAULT_AGENT_ROLES,
            tags=("tool", "llm"),
            metadata={
                "tool_capable_model_count": 0,
                "reason": "No ready model advertises tool_calling/function_calling capability.",
            },
        )

    warnings: list[dict[str, object]] = []
    status = "ready" if has_explicit_tools or has_ready_mcp else "warning"
    if status == "warning":
        warnings.append(
            _reason(
                "TOOL_RUNTIME_INVENTORY_PENDING",
                "Tool-capable model metadata is visible, but no concrete tool or MCP server inventory is registered yet.",
                phase="configuration",
                feature="tool_runtime",
                severity="warning",
            )
        )
    return RuntimeCapability(
        id="tool:llm_tool_calling",
        kind="tool",
        name="LLM Tool Calling",
        source="llm_registry",
        status=status,
        enabled=True,
        configured=True,
        scopes=("agent", "tool"),
        required_roles=_DEFAULT_AGENT_ROLES,
        tags=("tool", "llm", "tool_calling"),
        metadata={
            "tool_capable_model_count": len(tool_model_ids),
            "tool_capable_model_ids": list(tool_model_ids),
            "execution_boundary": "inventory_only_no_tool_executor_runtime",
        },
        warnings=tuple(warnings),
    )


def _mcp_server_capabilities(mcp_servers: object | None) -> list[RuntimeCapability]:
    descriptors = _descriptor_items(mcp_servers, _MCP_SERVER_COLLECTION_KEYS)
    if not descriptors:
        return [
            RuntimeCapability(
                id="mcp_server:mcp_server_registry",
                kind="mcp_server",
                name="MCP Server Registry",
                source="mcp_config",
                status="missingDependency",
                enabled=False,
                configured=False,
                scopes=("agent", "tool"),
                required_roles=_DEFAULT_AGENT_ROLES,
                tags=("mcp", "registry"),
                metadata={
                    "runtime_started": False,
                    "execution_boundary": "inventory_only_no_mcp_runtime",
                },
                blocking_reasons=(
                    _reason(
                        "MISSING_MCP_SERVER_CONFIG",
                        "No MCP server config is registered; add at least one MCP server before enabling MCP tools.",
                        phase="configuration",
                        feature="mcp_server",
                        dependency="mcp_server_config",
                        severity="warning",
                    ),
                ),
            )
        ]

    capabilities: list[RuntimeCapability] = []
    for descriptor in descriptors:
        name = _descriptor_text(descriptor, ("name", "label", "id")) or "MCP Server"
        server_id = _descriptor_text(descriptor, ("id", "name", "label")) or name
        enabled = _enabled_from(descriptor, default=True)
        missing_dependencies = _string_list(
            _descriptor_value(
                descriptor,
                (
                    "missing_dependency",
                    "missingDependency",
                    "missing_dependencies",
                    "missingDependencies",
                ),
            )
        )
        configured = bool(
            _descriptor_text(descriptor, ("command", "url", "endpoint", "server_url", "serverUrl"))
            or _descriptor_text(descriptor, ("transport",))
        )
        status = "ready"
        reasons: list[dict[str, object]] = []
        if not enabled:
            status = "disabled"
        elif missing_dependencies:
            status = "missingDependency"
            reasons.append(
                _reason(
                    "MCP_SERVER_MISSING_DEPENDENCY",
                    "MCP server config references dependencies that are not available.",
                    phase="configuration",
                    feature="mcp_server",
                    dependency=", ".join(missing_dependencies),
                    modules=missing_dependencies,
                    severity="blocking",
                    metadata={"server": name},
                )
            )
        elif _safe_bool(_descriptor_value(descriptor, ("available",)), default=True) is False:
            status = "missingDependency"
            reasons.append(
                _reason(
                    "MCP_SERVER_UNAVAILABLE",
                    "MCP server is configured but marked unavailable by inventory metadata.",
                    phase="configuration",
                    feature="mcp_server",
                    dependency="mcp_server",
                    metadata={"server": name},
                )
            )
        elif not configured:
            status = "blocked"
            reasons.append(
                _reason(
                    "MCP_SERVER_CONFIG_INCOMPLETE",
                    "MCP server config must include a command, URL, endpoint, or transport.",
                    phase="configuration",
                    feature="mcp_server",
                    metadata={"server": name},
                )
            )
        capabilities.append(
            RuntimeCapability(
                id=f"mcp_server:{_slug(server_id)}",
                kind="mcp_server",
                name=name,
                source=_descriptor_text(descriptor, ("source",)) or "mcp_config",
                status=status,
                enabled=enabled,
                configured=enabled and configured,
                scopes=tuple(_string_list(_descriptor_value(descriptor, ("scopes",))) or ("agent", "tool")),
                required_roles=tuple(
                    _string_list(_descriptor_value(descriptor, ("required_roles", "requiredRoles")))
                    or _DEFAULT_AGENT_ROLES
                ),
                tags=tuple(_string_list(_descriptor_value(descriptor, ("tags",))) or ("mcp", "server")),
                metadata={
                    "transport": _descriptor_text(descriptor, ("transport",)),
                    "command": _descriptor_text(descriptor, ("command",)),
                    "url": _descriptor_text(descriptor, ("url", "endpoint", "server_url", "serverUrl")),
                    "runtime_started": False,
                    "execution_boundary": "inventory_only_no_mcp_runtime",
                    "config": _public_descriptor_metadata(descriptor),
                },
                blocking_reasons=tuple(reasons),
            )
        )
    return capabilities


def _model_inventory_summary(model_capabilities: Sequence[RuntimeCapability]) -> dict[str, object]:
    ready_models = [capability for capability in model_capabilities if capability.ready]
    available_model_keys: list[str] = []
    tool_model_ids: list[str] = []
    mcp_model_ids: list[str] = []
    for capability in ready_models:
        metadata = capability.metadata
        model = _optional_text(metadata.get("model"))
        spec_id = _optional_text(metadata.get("model_spec_id"))
        for key in (model, spec_id, capability.id, capability.id.removeprefix("model:")):
            if key and key not in available_model_keys:
                available_model_keys.append(key)
        labels = _string_list(metadata.get("capabilities"))
        if _has_marker(labels, _TOOL_CAPABILITY_MARKERS):
            tool_model_ids.append(capability.id.removeprefix("model:"))
        if _has_marker(labels, _MCP_CAPABILITY_MARKERS):
            mcp_model_ids.append(capability.id.removeprefix("model:"))
    return {
        "ready_model_count": len(ready_models),
        "available_model_keys": available_model_keys,
        "tool_capable_model_count": len(tool_model_ids),
        "tool_capable_model_ids": tool_model_ids,
        "mcp_capable_model_count": len(mcp_model_ids),
        "mcp_capable_model_ids": mcp_model_ids,
    }


def _inventory_payload(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    by_kind: dict[str, dict[str, int]] = {}
    by_status: dict[str, int] = {}
    ready = 0
    for item in items:
        kind = str(item.get("kind") or "unknown")
        status = str(item.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        kind_counts = by_kind.setdefault(kind, {"total": 0, "ready": 0})
        kind_counts["total"] += 1
        kind_counts[status] = kind_counts.get(status, 0) + 1
        if item.get("ready") is True:
            ready += 1
            kind_counts["ready"] += 1
    return {
        "total": len(items),
        "ready": ready,
        "by_kind": by_kind,
        "by_status": by_status,
    }


def _registry_readiness(items: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ready_kinds = {str(item.get("kind")) for item in items if item.get("ready") is True}
    blockers: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    if "provider" not in ready_kinds:
        blockers.append(
            _reason(
                "NO_READY_PROVIDER",
                "No ready LLM provider capability is available.",
                phase="configuration",
                feature="provider",
            )
        )
    if "model" not in ready_kinds:
        blockers.append(
            _reason(
                "NO_READY_MODEL",
                "No ready LLM model capability is available.",
                phase="configuration",
                feature="model",
            )
        )
    if "agent" not in ready_kinds:
        blockers.append(
            _reason(
                "NO_READY_AGENT",
                "No ready agent capability is available.",
                phase="configuration",
                feature="agent",
            )
        )

    for item in items:
        kind = str(item.get("kind") or "")
        status = str(item.get("status") or "")
        readiness = item.get("readiness") if isinstance(item.get("readiness"), Mapping) else {}
        item_reasons = [
            dict(reason)
            for reason in readiness.get("blockingReasons", [])  # type: ignore[union-attr]
            if isinstance(reason, Mapping)
        ]
        item_warnings = [
            dict(warning)
            for warning in readiness.get("warnings", [])  # type: ignore[union-attr]
            if isinstance(warning, Mapping)
        ]
        if kind in {"provider", "model", "agent"} and status in {"blocked", "missingDependency"}:
            blockers.extend(item_reasons)
        elif status in {"warning", "missingDependency"}:
            for reason in item_reasons:
                if _optional_text(reason.get("severity")) == "blocking":
                    blockers.append(reason)
                else:
                    warnings.append(reason)
        warnings.extend(item_warnings)

    blockers = _dedupe_issues(blockers)
    warnings = _dedupe_issues(warnings)
    status = "blocked" if blockers else "warning" if warnings else "ready"
    return {
        "ready": status == "ready",
        "status": status,
        "blockingReasons": blockers,
        "warnings": warnings,
    }


def _capability_key(*parts: object) -> str:
    return ":".join(_required_text(part, "capability_key_part") for part in parts)


def _descriptor_items(value: object | None, collection_keys: Sequence[str]) -> list[dict[str, object]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        for key in collection_keys:
            if key not in value:
                continue
            nested = value[key]
            if isinstance(nested, Mapping):
                return _descriptor_items(nested, ())
            if isinstance(nested, Iterable) and not isinstance(nested, (str, bytes, bytearray)):
                return [_descriptor_mapping(item) for item in nested]
        if _looks_like_descriptor(value):
            return [_descriptor_mapping(value)]
        return [
            _descriptor_mapping({"id": key, **nested_value})
            if isinstance(nested_value, Mapping)
            else _descriptor_mapping({"id": key, "value": nested_value})
            for key, nested_value in value.items()
        ]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return [_descriptor_mapping(item) for item in value]
    return []


def _descriptor_mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): nested_value for key, nested_value in value.items()}
    result: dict[str, object] = {}
    for key in _DESCRIPTOR_KEYS | {"system_prompt", "created_at", "updated_at"}:
        if hasattr(value, key):
            result[key] = getattr(value, key)
    if not result and hasattr(value, "__dict__"):
        result = {str(key): nested_value for key, nested_value in vars(value).items()}
    return result


def _looks_like_descriptor(value: Mapping[str, object]) -> bool:
    keys = {str(key) for key in value}
    return bool(keys & _DESCRIPTOR_KEYS)


def _descriptor_value(descriptor: Mapping[str, object], keys: Sequence[str]) -> object | None:
    for key in keys:
        if key in descriptor:
            return descriptor[key]
    for nested_key in ("metadata", "extra", "extra_metadata", "config"):
        nested = descriptor.get(nested_key)
        if not isinstance(nested, Mapping):
            continue
        for key in keys:
            if key in nested:
                return nested[key]
    return None


def _descriptor_text(descriptor: Mapping[str, object], keys: Sequence[str]) -> str | None:
    return _optional_text(_descriptor_value(descriptor, keys))


def _public_descriptor_metadata(descriptor: Mapping[str, object]) -> dict[str, object]:
    public: dict[str, object] = {}
    for raw_key, value in descriptor.items():
        key = str(raw_key)
        if key in _PUBLIC_DESCRIPTOR_EXCLUDE_KEYS or _is_secret_key(key):
            continue
        public[key] = value
    nested_metadata = descriptor.get("metadata")
    if isinstance(nested_metadata, Mapping):
        public["metadata"] = dict(nested_metadata)
    sanitized = sanitize_public_metadata(public)
    return sanitized if isinstance(sanitized, dict) else {}


def _configured_flag(*sources: Mapping[str, object]) -> bool | None:
    keys = ("configured", "api_key_configured", "client_configured")
    for source in sources:
        for key in keys:
            if key in source:
                return _safe_bool(source.get(key), default=False)
    return None


def _enabled_from(source: Mapping[str, object], *, default: bool) -> bool:
    disabled = _safe_bool(source.get("disabled"), default=False)
    if disabled:
        return False
    return _safe_bool(source.get("enabled"), default=default)


def _has_marker(labels: Sequence[str], markers: set[str]) -> bool:
    normalized = {label.strip().lower().replace("-", "_").replace(".", "_") for label in labels}
    return bool(normalized & markers)


def _normalize_status(value: object, *, enabled: bool) -> str:
    text = _required_text(value, "status")
    normalized = _STATUS_ALIASES.get(text, _STATUS_ALIASES.get(text.lower(), text))
    if normalized not in _VALID_STATUSES:
        normalized = "unknown"
    if not enabled and normalized == "ready":
        return "disabled"
    return normalized


def _reason(
    code: str,
    message: str,
    *,
    phase: str,
    provider: str | None = None,
    feature: str | None = None,
    dependency: str | None = None,
    severity: str = "blocking",
    modules: Sequence[str] = (),
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "code": code,
        "message": message,
        "phase": phase,
        "severity": severity,
    }
    if provider is not None:
        payload["provider"] = provider
    if feature is not None:
        payload["feature"] = feature
    if dependency is not None:
        payload["dependency"] = dependency
    if modules:
        payload["modules"] = list(modules)
    if metadata:
        payload["metadata"] = dict(metadata)
    return _public_issue(payload)


def _public_issue(issue: Mapping[str, object]) -> dict[str, object]:
    sanitized = sanitize_public_metadata(dict(issue))
    return sanitized if isinstance(sanitized, dict) else {}


def _dedupe_issues(issues: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[str | None, str | None]] = set()
    for issue in issues:
        code = _optional_text(issue.get("code"))
        message = _optional_text(issue.get("message"))
        key = (code, message)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(issue))
    return result


def _is_secret_key(key: object) -> bool:
    lowered = str(key).lower()
    snake = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    compact = "".join(ch for ch in lowered if ch.isalnum())
    if snake in _SECRET_KEYS or compact in _SECRET_KEYS:
        return True
    return snake.endswith(("_api_key", "_authorization", "_password", "_secret", "_token")) or compact.endswith(
        ("apikey", "authorization", "password", "secret", "token")
    )


def _redact_secret_text(value: str) -> str:
    redacted = value
    redacted = _SECRET_TEXT_PATTERNS[0].sub(r"\1***", redacted)
    redacted = _SECRET_TEXT_PATTERNS[1].sub("sk-***", redacted)
    redacted = _SECRET_TEXT_PATTERNS[2].sub("[redacted]", redacted)
    return redacted


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
    if isinstance(value, str):
        parts = re.split(r"[,|/]", value)
        raw_items: Iterable[object] = parts if len(parts) > 1 else (value,)
    elif isinstance(value, Mapping):
        raw_items = [key for key, enabled in value.items() if enabled is True]
    elif isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        return []
    result: list[str] = []
    for item in raw_items:
        text = _optional_text(item)
        if text and text not in result:
            result.append(text)
    return result


def _safe_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "ready"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
    return default


def _slug(value: object) -> str:
    text = _required_text(value, "slug")
    lowered = text.strip().lower()
    slug = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    return slug or "unnamed"
