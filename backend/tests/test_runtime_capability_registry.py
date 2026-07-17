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
                },
            ),
        )
    )

    payload = registry.to_dict()
    serialized = json.dumps(payload, sort_keys=True).lower()

    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized
    assert payload["by_kind"]["tool"][0]["metadata"] == {"headers": {"X-Safe": "kept"}}


def test_text_runtime_capability_registry_projects_model_agent_tool_and_mcp_slots() -> None:
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
    )
    artifacts = build_llm_registry_artifacts(llm_registry)

    capability_registry = build_text_runtime_capability_registry(
        llm_registry,
        model_specs=artifacts["model_specs"],
    ).to_dict()

    serialized = json.dumps(capability_registry, sort_keys=True).lower()
    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized
    assert capability_registry["provider"] == "talkwise"
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
    assert model_capability["metadata"]["capabilities"] == [
        "text",
        "streaming",
        "tool_calling",
    ]

    agent_capability = capability_registry["by_kind"]["agent"][0]
    assert agent_capability["enabled"] is True
    assert agent_capability["required_roles"] == ["admin", "leader", "staff"]
    assert agent_capability["metadata"]["migration_boundary"] == (
        "future external chat-runtime agent adapter"
    )

    tool_capability = capability_registry["by_kind"]["tool"][0]
    assert tool_capability["enabled"] is False
    assert tool_capability["configured"] is False

    mcp_capability = capability_registry["by_kind"]["mcp_server"][0]
    assert mcp_capability["enabled"] is False
    assert mcp_capability["metadata"]["dependency"] == "mcp>=1.0,<2"
