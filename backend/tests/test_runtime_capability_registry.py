from __future__ import annotations

import json

from application.ports.capabilities import (
    RuntimeCapability,
    RuntimeCapabilityRegistry,
    build_text_runtime_capability_registry,
)
from application.ports.llm import (
    LLMEndpointMetadata,
    LLMModelMetadata,
    LLMProviderMetadata,
    build_llm_registry_artifacts,
    build_llm_provider_registry,
)


def test_runtime_capability_registry_sanitizes_secret_metadata() -> None:
    registry = RuntimeCapabilityRegistry(
        capabilities=(
            RuntimeCapability(
                id="tool:secret-bearing",
                kind="tool",
                name="Secret Bearing Tool",
                metadata={
                    "api_key": "sk-secret-should-not-appear",
                    "headers": {
                        "Authorization": "Bearer secret-should-not-appear",
                        "X-Safe": "kept",
                    },
                    "note": "Bearer secret-should-not-appear",
                },
                blocking_reasons=(
                    {
                        "code": "SAFE_PUBLIC_ERROR",
                        "message": "Authorization: Bearer secret-should-not-appear",
                        "api_key": "sk-secret-should-not-appear",
                    },
                ),
            ),
        )
    )

    payload = registry.to_dict()
    serialized = json.dumps(payload, sort_keys=True).lower()

    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized
    assert payload["by_kind"]["tool"][0]["metadata"] == {
        "headers": {"X-Safe": "kept"},
        "note": "Bearer ***",
    }
    assert payload["by_kind"]["tool"][0]["readiness"]["blockingReasons"] == [
        {"code": "SAFE_PUBLIC_ERROR", "message": "[redacted] ***"}
    ]


def test_text_runtime_capability_registry_projects_descriptor_only_agent_tool_and_mcp_inventory() -> None:
    model = LLMModelMetadata(
        name="gpt-registry",
        provider="openai",
        endpoint="https://openai.example/v1",
        display_name="GPT Registry",
        is_default=True,
        extra={
            "capabilities": ["text", "streaming", "tool_calling"],
            "model_spec": {
                "routing": "primary",
                "apiKey": "sk-secret-should-not-appear",
            },
        },
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-registry",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-registry",
                        models=[model],
                        extra={
                            "endpoint_config": {
                                "headers": {
                                    "Authorization": "Bearer secret-should-not-appear",
                                    "X-Provider": "kept",
                                }
                            }
                        },
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True, "api_key_configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    capability_registry = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
        agent_configs=[
            {
                "id": "coach",
                "name": "Training Coach",
                "model": "gpt-registry",
                "tool_ids": ["crm.lookup"],
                "mcp_server_ids": ["crm"],
                "system_prompt": "not public inventory",
                "metadata": {
                    "scenario": "sales",
                    "apiKey": "sk-secret-should-not-appear",
                },
            }
        ],
        tool_configs=[
            {
                "id": "crm.lookup",
                "name": "CRM Lookup",
                "requires_mcp": True,
                "mcp_server": "crm",
                "metadata": {"token": "secret-should-not-appear", "owner": "training"},
            }
        ],
        mcp_servers={
            "crm": {
                "name": "CRM MCP",
                "transport": "stdio",
                "command": "npx",
                "args": ["crm-mcp"],
                "env": {"CRM_TOKEN": "secret-should-not-appear", "MODE": "test"},
                "headers": {
                    "Authorization": "Bearer secret-should-not-appear",
                    "X-Safe": "kept",
                },
            }
        },
    ).to_dict()

    serialized = json.dumps(capability_registry, sort_keys=True).lower()
    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized
    assert capability_registry["provider"] == "talkwise"
    assert capability_registry["version"] == 2
    assert capability_registry["readiness"]["status"] == "warning"
    assert capability_registry["inventory"]["by_status"]["ready"] == 2
    assert capability_registry["inventory"]["by_status"]["warning"] == 4
    assert set(capability_registry["by_kind"]) == {
        "provider",
        "model",
        "agent",
        "tool",
        "mcp_server",
    }

    model_capability = capability_registry["by_kind"]["model"][0]
    assert model_capability["id"] == (
        "model:openai::https://openai.example/v1::responses::gpt-registry"
    )
    assert model_capability["provider"] == "openai"
    assert model_capability["configured"] is True
    assert model_capability["status"] == "ready"
    assert model_capability["ready"] is True
    assert model_capability["metadata"]["capabilities"] == [
        "text",
        "streaming",
        "tool_calling",
    ]

    agent_capability = capability_registry["by_kind"]["agent"][0]
    assert agent_capability["id"] == "agent:coach"
    assert agent_capability["enabled"] is True
    assert agent_capability["configured"] is True
    assert agent_capability["ready"] is False
    assert agent_capability["status"] == "warning"
    assert agent_capability["required_roles"] == ["admin", "leader", "staff"]
    assert agent_capability["metadata"]["descriptor_only"] is True
    assert agent_capability["metadata"]["runtime_started"] is False
    assert agent_capability["metadata"]["dispatcher_boundary"] == "no_generic_agent_dispatcher"
    assert agent_capability["metadata"]["auth_required"] is True
    assert agent_capability["readiness"]["warnings"][0]["code"] == (
        "AGENT_DESCRIPTOR_ONLY_NO_DISPATCHER"
    )
    assert agent_capability["metadata"]["model"] == "gpt-registry"
    assert agent_capability["metadata"]["tool_ids"] == ["crm.lookup"]
    assert agent_capability["metadata"]["mcp_server_ids"] == ["crm"]
    assert agent_capability["metadata"]["config"]["metadata"] == {"scenario": "sales"}

    tool_capabilities = capability_registry["by_kind"]["tool"]
    assert [capability["status"] for capability in tool_capabilities] == ["warning", "warning"]
    assert tool_capabilities[0]["id"] == "tool:llm_tool_calling"
    assert tool_capabilities[0]["ready"] is False
    assert tool_capabilities[0]["metadata"]["descriptor_only"] is True
    assert tool_capabilities[0]["metadata"]["tool_consumer_gated"] is True
    assert tool_capabilities[0]["metadata"]["tool_capable_model_count"] == 1
    assert tool_capabilities[1]["id"] == "tool:crm_lookup"
    assert tool_capabilities[1]["configured"] is True
    assert tool_capabilities[1]["ready"] is False
    assert tool_capabilities[1]["readiness"]["warnings"][0]["code"] == (
        "TOOL_DESCRIPTOR_ONLY_CONSUMER_GATED"
    )
    assert tool_capabilities[1]["metadata"]["mcp_server"] == "crm"

    mcp_capability = capability_registry["by_kind"]["mcp_server"][0]
    assert mcp_capability["id"] == "mcp_server:crm"
    assert mcp_capability["status"] == "warning"
    assert mcp_capability["enabled"] is True
    assert mcp_capability["configured"] is True
    assert mcp_capability["ready"] is False
    assert mcp_capability["metadata"]["descriptor_only"] is True
    assert mcp_capability["metadata"]["runtime_started"] is False
    assert mcp_capability["metadata"]["execution_boundary"] == "descriptor_only_no_mcp_runtime"
    assert mcp_capability["readiness"]["warnings"][0]["code"] == "MCP_DESCRIPTOR_ONLY_NO_RUNTIME"
    assert mcp_capability["metadata"]["config"]["env"] == {"MODE": "test"}
    assert mcp_capability["metadata"]["config"]["headers"] == {"X-Safe": "kept"}


def test_text_runtime_capability_registry_reports_missing_mcp_server_as_tool_only_warning() -> None:
    model = LLMModelMetadata(
        name="claude-tooling",
        provider="anthropic",
        endpoint="https://anthropic.example",
        is_default=True,
        extra={"capabilities": ["text", "tool_calling"]},
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="anthropic",
                default_model="claude-tooling",
                endpoint="https://anthropic.example",
                wire_api="messages",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="anthropic",
                        endpoint="https://anthropic.example",
                        wire_api="messages",
                        default_model="claude-tooling",
                        models=[model],
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    payload = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
    ).to_dict()

    assert payload["readiness"]["status"] == "warning"
    assert payload["readiness"]["ready"] is False
    assert [warning["code"] for warning in payload["readiness"]["warnings"]] == [
        "TOOL_RUNTIME_INVENTORY_PENDING",
        "TOOL_DESCRIPTOR_ONLY_CONSUMER_GATED",
        "MISSING_MCP_SERVER_CONFIG",
    ]

    tool_capability = payload["by_kind"]["tool"][0]
    assert tool_capability["status"] == "warning"
    assert tool_capability["enabled"] is True
    assert tool_capability["ready"] is False
    assert tool_capability["readiness"]["warnings"][0]["message"].startswith(
        "Tool-capable model metadata is visible"
    )

    mcp_capability = payload["by_kind"]["mcp_server"][0]
    assert mcp_capability["status"] == "missingDependency"
    assert mcp_capability["enabled"] is False
    assert mcp_capability["configured"] is False
    assert mcp_capability["readiness"]["blockingReasons"][0]["message"].startswith(
        "No MCP server config is registered"
    )


def test_text_runtime_capability_registry_requires_specific_mcp_server_match_for_tools() -> None:
    model = LLMModelMetadata(
        name="gpt-tooling",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"capabilities": ["text", "tool_calling"]},
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-tooling",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-tooling",
                        models=[model],
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    payload = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
        tool_configs=[
            {
                "id": "crm.lookup",
                "name": "CRM Lookup",
                "requires_mcp": True,
                "mcp_server": "crm",
            }
        ],
        mcp_servers=[
            {"id": "calendar", "name": "Calendar MCP", "transport": "stdio"},
            {
                "id": "crm",
                "name": "CRM MCP",
                "transport": "stdio",
                "enabled": False,
            },
        ],
    ).to_dict()

    assert payload["readiness"]["status"] == "warning"
    tool_capabilities = payload["by_kind"]["tool"]
    assert [capability["status"] for capability in tool_capabilities] == [
        "warning",
        "missingDependency",
    ]
    assert tool_capabilities[1]["metadata"]["mcp_server"] == "crm"
    assert tool_capabilities[1]["readiness"]["blockingReasons"][0]["code"] == (
        "MISSING_READY_MCP_SERVER"
    )
    assert [capability["status"] for capability in payload["by_kind"]["mcp_server"]] == [
        "warning",
        "disabled",
    ]


def test_text_runtime_capability_registry_marks_agent_bound_dependencies_not_ready() -> None:
    model = LLMModelMetadata(
        name="gpt-tooling",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"capabilities": ["text", "tool_calling"]},
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-tooling",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-tooling",
                        models=[model],
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    payload = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
        agent_configs=[
            {
                "id": "coach",
                "name": "Training Coach",
                "model": "gpt-tooling",
                "tool_ids": ["crm.lookup"],
                "mcp_server_ids": ["crm"],
            }
        ],
        tool_configs=[
            {
                "id": "crm.lookup",
                "name": "CRM Lookup",
                "requires_mcp": True,
                "mcp_server": "crm",
            }
        ],
        mcp_servers=[
            {"id": "crm", "name": "CRM MCP", "transport": "stdio", "enabled": False},
        ],
    ).to_dict()

    agent_capability = payload["by_kind"]["agent"][0]
    assert agent_capability["status"] == "missingDependency"
    assert agent_capability["ready"] is False
    assert [reason["code"] for reason in agent_capability["readiness"]["blockingReasons"]] == [
        "AGENT_BOUND_TOOL_NOT_READY",
        "AGENT_BOUND_MCP_SERVER_NOT_READY",
    ]


def test_text_runtime_capability_registry_ignores_agent_binding_metadata_for_readiness() -> None:
    model = LLMModelMetadata(
        name="gpt-text",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"capabilities": ["text"]},
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-text",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-text",
                        models=[model],
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    payload = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
        agent_configs=[
            {
                "id": "coach",
                "name": "Training Coach",
                "model": "gpt-text",
                "metadata": {
                    "tool_ids": ["legacy.crm.lookup"],
                    "mcp_server_ids": ["legacy-crm"],
                },
            }
        ],
    ).to_dict()

    agent_capability = payload["by_kind"]["agent"][0]
    assert agent_capability["status"] == "warning"
    assert agent_capability["ready"] is False
    assert agent_capability["metadata"]["descriptor_only"] is True
    assert agent_capability["metadata"]["dispatcher_boundary"] == "no_generic_agent_dispatcher"
    assert agent_capability["metadata"]["tool_ids"] == []
    assert agent_capability["metadata"]["mcp_server_ids"] == []
    assert agent_capability["metadata"]["config"]["metadata"]["tool_ids"] == [
        "legacy.crm.lookup"
    ]


def test_text_runtime_capability_registry_marks_disabled_and_missing_dependency_states() -> None:
    model = LLMModelMetadata(
        name="gpt-tooling",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"capabilities": ["text", "tool_calling"]},
    )
    llm_registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-tooling",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-tooling",
                        models=[model],
                    )
                ],
            )
        ],
        provider="talkwise",
        extra={"configured": True},
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    payload = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
        mcp_servers=[
            {"id": "disabled-mcp", "name": "Disabled MCP", "enabled": False, "transport": "stdio"},
            {
                "id": "missing-dep-mcp",
                "name": "Missing Dep MCP",
                "transport": "stdio",
                "missingDependencies": ["mcp-python"],
            },
        ],
    ).to_dict()

    assert payload["by_kind"]["model"][0]["status"] == "ready"
    assert payload["by_kind"]["agent"][0]["status"] == "ready"
    assert [capability["status"] for capability in payload["by_kind"]["mcp_server"]] == [
        "disabled",
        "missingDependency",
    ]
    assert payload["readiness"]["status"] == "blocked"
    assert payload["readiness"]["blockingReasons"][0]["code"] == "MCP_SERVER_MISSING_DEPENDENCY"
