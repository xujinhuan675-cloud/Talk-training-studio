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
