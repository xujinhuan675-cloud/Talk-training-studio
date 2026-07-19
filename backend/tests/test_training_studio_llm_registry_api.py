from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_conversation_service, get_stakeholder_llm_client
from api.routes.training_studio import router
from application.dto import AgentConfigDTO
from application.ports.llm import LLMEndpointMetadata, LLMModelMetadata, LLMProviderMetadata
from core.config import LLMSettings, settings


def _as_mapping(value: object | None) -> dict:
    return value if isinstance(value, dict) else {}


def _metadata_text(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _owned_user_id(metadata: dict) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "userId", "user_id") or _metadata_text(
        metadata,
        "ownerUserId",
        "owner_user_id",
        "createdByUserId",
        "created_by_user_id",
    )


def _owned_team_id(metadata: dict) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "teamId", "team_id") or _metadata_text(
        metadata,
        "teamId",
        "team_id",
        "ownerTeamId",
        "owner_team_id",
    )


def _matches_metadata_scope(metadata: dict, scope) -> bool:
    metadata = _as_mapping(metadata)
    owner_user_id = _owned_user_id(metadata)
    owner_team_id = _owned_team_id(metadata)
    team_id = getattr(scope, "team_id", None)
    if not owner_user_id and not owner_team_id:
        return bool(getattr(scope, "allow_unscoped", False))
    if owner_user_id and owner_user_id == getattr(scope, "user_id", None):
        return True
    if getattr(scope, "include_team_scope", False) and owner_team_id and owner_team_id == team_id:
        return True
    if not owner_user_id and owner_team_id and owner_team_id == team_id:
        return True
    return False


class _FakeLLM:
    @property
    def provider_metadata(self) -> LLMProviderMetadata:
        model = LLMModelMetadata(
            name="claude-sonnet-test",
            provider="anthropic",
            endpoint="https://anthropic.example",
            display_name="Claude Sonnet Test",
            is_default=True,
            context_window=200000,
            max_output_tokens=4096,
        )
        return LLMProviderMetadata(
            provider="anthropic",
            default_model="claude-sonnet-test",
            endpoint="https://anthropic.example",
            wire_api="messages",
            models=[model],
            endpoints=[
                LLMEndpointMetadata(
                    provider="anthropic",
                    endpoint="https://anthropic.example",
                    wire_api="messages",
                    default_model="claude-sonnet-test",
                    models=[model],
                )
            ],
        )


class _SecretBearingLLM:
    @property
    def provider_metadata(self) -> LLMProviderMetadata:
        model = LLMModelMetadata(
            name="gpt-secret-test",
            provider="openai",
            endpoint="https://openai.example/v1",
            is_default=True,
            extra={
                "model_spec": {
                    "routing": "primary",
                    "api_key": "sk-secret-should-not-appear",
                    "headers": {
                        "Authorization": "Bearer secret-should-not-appear",
                        "X-Safe": "kept",
                    },
                }
            },
        )
        return LLMProviderMetadata(
            provider="openai",
            default_model="gpt-secret-test",
            endpoint="https://openai.example/v1",
            wire_api="responses",
            models=[model],
            endpoints=[
                LLMEndpointMetadata(
                    provider="openai",
                    endpoint="https://openai.example/v1",
                    wire_api="responses",
                    default_model="gpt-secret-test",
                    models=[model],
                    extra={
                        "endpoint_config": {
                            "timeout_ms": 5000,
                            "headers": {
                                "Authorization": "Bearer secret-should-not-appear",
                                "X-Safe": "kept",
                            },
                        }
                    },
                )
            ],
        )


def _agent_config(
    config_id: int,
    *,
    metadata: dict | None = None,
    tool_ids: list[str] | None = None,
    mcp_server_ids: list[str] | None = None,
) -> AgentConfigDTO:
    now = datetime.now(timezone.utc)
    return AgentConfigDTO(
        id=config_id,
        name=f"agent-{config_id}",
        system_prompt=None,
        model="claude-sonnet-test",
        temperature=None,
        max_tokens=None,
        tool_ids=tool_ids or [],
        mcp_server_ids=mcp_server_ids or [],
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


class _FakeConversationService:
    def __init__(self, agent_configs: list[AgentConfigDTO] | None = None) -> None:
        self.agent_configs = agent_configs or []

    async def list_agent_configs(self, **kwargs):
        items = list(self.agent_configs)
        metadata_scope = kwargs.get("metadata_scope")
        if metadata_scope is not None:
            items = [item for item in items if _matches_metadata_scope(item.metadata, metadata_scope)]
        total = len(items)
        skip = kwargs.get("skip", 0)
        limit = kwargs.get("limit", 20)
        return items[skip:skip + limit], total


def _client(llm, *, agent_configs: list[AgentConfigDTO] | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stakeholder_llm_client] = lambda: llm
    app.dependency_overrides[get_conversation_service] = lambda: _FakeConversationService(agent_configs)
    return TestClient(app)


def test_llm_registry_uses_active_client_provider_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        LLMSettings(
            provider="openai",
            api_key="sk-active-secret",
            base_url="https://openai.example/v1",
            wire_api="chat_completions",
            default_model="gpt-settings",
        ),
    )

    response = _client(
        _FakeLLM(),
        agent_configs=[
            _agent_config(
                12,
                tool_ids=["crm.lookup"],
                mcp_server_ids=["crm"],
                metadata={
                    "ownerUserId": "user-admin-001",
                    "teamId": "team-platform",
                    "tool": "secret-safe-branch-review",
                },
            )
        ],
    ).get("/api/v1/training-studio/llm-registry")

    assert response.status_code == 200
    assert "sk-active-secret" not in response.text
    data = response.json()["data"]
    assert data["provider"] == "talkwise"
    assert data["default_model"] == "claude-sonnet-test"
    assert data["configured"] is True
    assert data["client_configured"] is True
    assert data["api_key_configured"] is True
    assert data["source"] == "active_client"
    assert data["models"] == [
        {
            "name": "claude-sonnet-test",
            "provider": "anthropic",
            "endpoint": "https://anthropic.example",
            "display_name": "Claude Sonnet Test",
            "is_default": True,
            "context_window": 200000,
            "max_output_tokens": 4096,
        }
    ]
    assert data["endpoints"] == [
        {
            "provider": "anthropic",
            "endpoint": "https://anthropic.example",
            "wire_api": "messages",
            "default_model": "claude-sonnet-test",
            "models": data["models"],
        }
    ]
    assert data["model_specs"] == [
        {
            "id": "anthropic::https://anthropic.example::messages::claude-sonnet-test",
            "model_spec_id": "anthropic::https://anthropic.example::messages::claude-sonnet-test",
            "model_spec_name": "anthropic::https://anthropic.example::messages::claude-sonnet-test",
            "name": "anthropic::https://anthropic.example::messages::claude-sonnet-test",
            "label": "Claude Sonnet Test",
            "display_label": "Claude Sonnet Test",
            "provider": "anthropic",
            "endpoint": "https://anthropic.example",
            "endpoint_key": "anthropic::https://anthropic.example::messages",
            "wire_api": "messages",
            "model": "claude-sonnet-test",
            "group": "anthropic",
            "default": True,
            "is_default": True,
            "enabled": True,
            "selectable": True,
            "show_in_menu": True,
            "capabilities": ["text", "streaming"],
            "tags": ["text", "streaming"],
            "context_window": 200000,
            "max_output_tokens": 4096,
        }
    ]
    assert data["endpoints_config"] == {
        "anthropic::https://anthropic.example::messages": {
            "key": "anthropic::https://anthropic.example::messages",
            "order": 0,
            "provider": "anthropic",
            "label": "anthropic",
            "display_label": "anthropic",
            "endpoint": "https://anthropic.example",
            "wire_api": "messages",
            "default_model": "claude-sonnet-test",
            "enabled": True,
            "selectable": True,
            "model_display_label": "anthropic",
            "available_models": ["claude-sonnet-test"],
            "models": ["claude-sonnet-test"],
            "model_spec_ids": ["anthropic::https://anthropic.example::messages::claude-sonnet-test"],
            "capabilities": ["text", "streaming"],
            "tags": [],
        }
    }
    capability_registry = data["capability_registry"]
    assert capability_registry["provider"] == "talkwise"
    assert set(capability_registry["by_kind"]) == {
        "provider",
        "model",
        "agent",
        "tool",
        "mcp_server",
    }
    assert capability_registry["by_kind"]["model"][0]["provider"] == "anthropic"
    assert capability_registry["by_kind"]["model"][0]["configured"] is True
    assert capability_registry["by_kind"]["agent"][0]["enabled"] is True
    assert capability_registry["by_kind"]["agent"][0]["source"] == "agent_config"
    assert capability_registry["by_kind"]["agent"][0]["name"] == "agent-12"
    assert capability_registry["by_kind"]["agent"][0]["status"] == "missingDependency"
    assert capability_registry["by_kind"]["agent"][0]["ready"] is False
    assert capability_registry["by_kind"]["agent"][0]["metadata"]["tool_ids"] == ["crm.lookup"]
    assert capability_registry["by_kind"]["agent"][0]["metadata"]["mcp_server_ids"] == ["crm"]
    assert capability_registry["by_kind"]["tool"][0]["enabled"] is False
    assert capability_registry["by_kind"]["mcp_server"][0]["enabled"] is False


def test_llm_registry_agent_configs_are_scoped_before_inventory_pagination(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        LLMSettings(
            provider="anthropic",
            api_key="sk-active-secret",
            base_url="https://anthropic.example",
            wire_api="messages",
            default_model="claude-sonnet-test",
        ),
    )

    response = _client(
        _FakeLLM(),
        agent_configs=[
            _agent_config(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            ),
            _agent_config(
                8,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
        ],
    ).get("/api/v1/training-studio/llm-registry", headers={"X-Mock-User": "sales"})

    assert response.status_code == 200
    agents = response.json()["data"]["capability_registry"]["by_kind"]["agent"]
    assert [agent["name"] for agent in agents] == ["agent-8"]


def test_llm_registry_response_strips_secrets_from_model_specs(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        LLMSettings(
            provider="openai",
            api_key="sk-settings-secret-should-not-appear",
            base_url="https://openai.example/v1",
            wire_api="responses",
            default_model="gpt-settings",
        ),
    )

    response = _client(_SecretBearingLLM()).get("/api/v1/training-studio/llm-registry")

    assert response.status_code == 200
    serialized = response.text.lower()
    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized

    data = response.json()["data"]
    assert data["api_key_configured"] is True
    assert data["models"][0]["model_spec"] == {
        "routing": "primary",
        "headers": {"X-Safe": "kept"},
    }
    assert data["endpoints"][0]["endpoint_config"] == {
        "timeout_ms": 5000,
        "headers": {"X-Safe": "kept"},
    }
    assert data["capability_registry"]["by_kind"]["model"][0]["metadata"]["capabilities"] == [
        "text",
        "streaming",
    ]


def test_llm_registry_falls_back_to_settings_without_active_client(monkeypatch) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        LLMSettings(
            provider="openrouter",
            api_key=None,
            base_url="https://openrouter.ai/api/v1",
            wire_api="responses",
            default_model="openai/gpt-4o-mini",
            max_tokens=2048,
            max_retries=5,
        ),
    )

    response = _client(None).get("/api/v1/training-studio/llm-registry")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "talkwise"
    assert data["default_model"] == "openai/gpt-4o-mini"
    assert data["configured"] is False
    assert data["client_configured"] is False
    assert data["api_key_configured"] is False
    assert data["source"] == "settings"
    assert data["models"] == [
        {
            "name": "openai/gpt-4o-mini",
            "provider": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "is_default": True,
            "max_output_tokens": 2048,
        }
    ]
    assert data["endpoints"] == [
        {
            "provider": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "wire_api": "responses",
            "default_model": "openai/gpt-4o-mini",
            "models": data["models"],
        }
    ]
    assert data["model_specs"] == [
        {
            "id": "openrouter::https://openrouter.ai/api/v1::responses::openai/gpt-4o-mini",
            "model_spec_id": "openrouter::https://openrouter.ai/api/v1::responses::openai/gpt-4o-mini",
            "model_spec_name": "openrouter::https://openrouter.ai/api/v1::responses::openai/gpt-4o-mini",
            "name": "openrouter::https://openrouter.ai/api/v1::responses::openai/gpt-4o-mini",
            "label": "openai/gpt-4o-mini",
            "display_label": "openai/gpt-4o-mini",
            "provider": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "endpoint_key": "openrouter::https://openrouter.ai/api/v1::responses",
            "wire_api": "responses",
            "model": "openai/gpt-4o-mini",
            "group": "openrouter",
            "default": True,
            "is_default": True,
            "enabled": True,
            "selectable": True,
            "show_in_menu": True,
            "capabilities": ["text", "streaming"],
            "tags": ["text", "streaming"],
            "max_output_tokens": 2048,
        }
    ]
    assert data["endpoints_config"] == {
        "openrouter::https://openrouter.ai/api/v1::responses": {
            "key": "openrouter::https://openrouter.ai/api/v1::responses",
            "order": 0,
            "provider": "openrouter",
            "label": "openrouter",
            "display_label": "openrouter",
            "endpoint": "https://openrouter.ai/api/v1",
            "wire_api": "responses",
            "default_model": "openai/gpt-4o-mini",
            "enabled": True,
            "selectable": True,
            "model_display_label": "openrouter",
            "available_models": ["openai/gpt-4o-mini"],
            "models": ["openai/gpt-4o-mini"],
            "model_spec_ids": [
                "openrouter::https://openrouter.ai/api/v1::responses::openai/gpt-4o-mini"
            ],
            "capabilities": ["text", "streaming"],
            "tags": [],
        }
    }
