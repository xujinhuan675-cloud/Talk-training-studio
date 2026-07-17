from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_stakeholder_llm_client
from api.routes.training_studio import router
from application.ports.llm import LLMEndpointMetadata, LLMModelMetadata, LLMProviderMetadata
from core.config import LLMSettings, settings


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


def _client(llm) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stakeholder_llm_client] = lambda: llm
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

    response = _client(_FakeLLM()).get("/api/v1/training-studio/llm-registry")

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
