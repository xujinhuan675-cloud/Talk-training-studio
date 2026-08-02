from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from application.ports.llm import (
    LLMEndpointMetadata,
    LLMModelMetadata,
    LLMProviderMetadata,
    build_llm_registry_artifacts,
    build_llm_provider_registry,
)
from application.services.chat_service import _llm_provider_metadata, _run_request_metadata
from application.services.training_studio.session_service import TrainingSessionService
from application.services.training_studio.training_core import training_core_metadata_for_session
from infrastructure.external.llm.openai_provider import OpenAIProvider


def _anthropic_provider_class():
    if "anthropic" not in sys.modules and importlib.util.find_spec("anthropic") is None:
        anthropic_module = types.ModuleType("anthropic")

        class FakeAsyncAnthropic:
            def __init__(self, **kwargs) -> None:
                self.kwargs = kwargs

        anthropic_module.AsyncAnthropic = FakeAsyncAnthropic
        sys.modules["anthropic"] = anthropic_module

    from infrastructure.external.llm.anthropic_provider import AnthropicProvider

    return AnthropicProvider


def test_openai_provider_metadata_serializes_endpoint_model_catalog() -> None:
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://gateway.example",
        provider_name="vllm",
        wire_api="responses",
        default_model="llama-test",
        default_max_tokens=2048,
        max_retries=3,
    )

    payload = provider.provider_metadata.to_dict()

    assert payload["provider"] == "vllm"
    assert payload["default_model"] == "llama-test"
    assert payload["endpoint"] == "https://gateway.example/v1"
    assert payload["wire_api"] == "responses"
    assert payload["max_retries"] == 3
    assert payload["models"] == [
        {
            "name": "llama-test",
            "provider": "vllm",
            "endpoint": "https://gateway.example/v1",
            "is_default": True,
            "max_output_tokens": 2048,
        }
    ]
    assert payload["endpoints"] == [
        {
            "provider": "vllm",
            "endpoint": "https://gateway.example/v1",
            "wire_api": "responses",
            "default_model": "llama-test",
            "models": payload["models"],
        }
    ]
    json.dumps(payload)


def test_anthropic_provider_metadata_serializes_endpoint_model_catalog() -> None:
    AnthropicProvider = _anthropic_provider_class()
    provider = AnthropicProvider(
        api_key="test-key",
        base_url="https://anthropic.example",
        default_model="claude-test",
        default_max_tokens=3072,
    )

    payload = provider.provider_metadata.to_dict()

    assert payload["provider"] == "anthropic"
    assert payload["default_model"] == "claude-test"
    assert payload["endpoint"] == "https://anthropic.example"
    assert payload["wire_api"] == "messages"
    assert "max_retries" not in payload
    assert payload["models"] == [
        {
            "name": "claude-test",
            "provider": "anthropic",
            "endpoint": "https://anthropic.example",
            "is_default": True,
            "max_output_tokens": 3072,
        }
    ]
    assert payload["endpoints"] == [
        {
            "provider": "anthropic",
            "endpoint": "https://anthropic.example",
            "wire_api": "messages",
            "default_model": "claude-test",
            "models": payload["models"],
        }
    ]
    json.dumps(payload)


def test_build_llm_provider_registry_combines_provider_endpoint_model_catalogs() -> None:
    AnthropicProvider = _anthropic_provider_class()
    openai_metadata = OpenAIProvider(
        api_key="test-key",
        base_url="https://openai.example",
        provider_name="openai",
        wire_api="chat_completions",
        default_model="gpt-registry",
    ).provider_metadata
    anthropic_metadata = AnthropicProvider(
        api_key="test-key",
        base_url="https://anthropic.example",
        default_model="claude-registry",
    ).provider_metadata

    registry = build_llm_provider_registry(
        [openai_metadata, anthropic_metadata],
        provider="talkwise",
    )
    payload = registry.to_dict()

    assert payload["provider"] == "talkwise"
    assert payload["default_model"] == "gpt-registry"
    assert [(model["provider"], model["name"]) for model in payload["models"]] == [
        ("openai", "gpt-registry"),
        ("anthropic", "claude-registry"),
    ]
    assert [endpoint["provider"] for endpoint in payload["endpoints"]] == [
        "openai",
        "anthropic",
    ]
    assert [endpoint["default_model"] for endpoint in payload["endpoints"]] == [
        "gpt-registry",
        "claude-registry",
    ]
    assert payload["endpoints"][0]["models"][0]["provider"] == "openai"
    assert payload["endpoints"][1]["models"][0]["provider"] == "anthropic"
    artifacts = build_llm_registry_artifacts(registry)
    assert [(spec["provider"], spec["model"]) for spec in artifacts["model_specs"]] == [
        ("openai", "gpt-registry"),
        ("anthropic", "claude-registry"),
    ]
    assert [config["provider"] for config in artifacts["endpoints_config"].values()] == [
        "openai",
        "anthropic",
    ]
    json.dumps(payload)


def test_build_llm_registry_artifacts_exposes_model_specs_and_endpoint_config() -> None:
    enabled_model = LLMModelMetadata(
        name="gpt-registry",
        provider="openai",
        endpoint="https://openai.example/v1",
        display_name="GPT Registry",
        is_default=True,
        context_window=128000,
        max_output_tokens=4096,
        extra={
            "description": "General training model",
            "capabilities": ["text", "streaming", "structured_output"],
            "tags": ["fast", "balanced"],
            "pricing": {"prompt": 2.5, "completion": 10, "api_key": "hidden"},
        },
    )
    disabled_model = LLMModelMetadata(
        name="gpt-disabled",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"enabled": False},
    )
    registry = LLMProviderMetadata(
        provider="talkwise",
        default_model="gpt-registry",
        models=[enabled_model, disabled_model],
        endpoints=[
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                default_model="gpt-registry",
                models=[enabled_model, disabled_model],
                extra={"modelDisplayLabel": "OpenAI Responses", "capabilities": ["text"]},
            )
        ],
    )

    artifacts = build_llm_registry_artifacts(registry)

    assert artifacts["model_specs"][0] == {
        "id": "openai::https://openai.example/v1::responses::gpt-registry",
        "model_spec_id": "openai::https://openai.example/v1::responses::gpt-registry",
        "model_spec_name": "openai::https://openai.example/v1::responses::gpt-registry",
        "name": "openai::https://openai.example/v1::responses::gpt-registry",
        "label": "GPT Registry",
        "display_label": "GPT Registry",
        "provider": "openai",
        "endpoint": "https://openai.example/v1",
        "endpoint_key": "openai::https://openai.example/v1::responses",
        "wire_api": "responses",
        "model": "gpt-registry",
        "group": "openai",
        "default": True,
        "is_default": True,
        "enabled": True,
        "selectable": True,
        "show_in_menu": True,
        "capabilities": ["text", "streaming", "structured_output"],
        "tags": ["fast", "balanced"],
        "description": "General training model",
        "context_window": 128000,
        "max_output_tokens": 4096,
        "pricing": {"prompt": 2.5, "completion": 10},
    }
    assert artifacts["model_specs"][1]["model"] == "gpt-disabled"
    assert artifacts["model_specs"][1]["enabled"] is False
    assert artifacts["model_specs"][1]["selectable"] is False
    assert artifacts["endpoints_config"] == {
        "openai::https://openai.example/v1::responses": {
            "key": "openai::https://openai.example/v1::responses",
            "order": 0,
            "provider": "openai",
            "label": "openai",
            "display_label": "openai",
            "endpoint": "https://openai.example/v1",
            "wire_api": "responses",
            "default_model": "gpt-registry",
            "enabled": True,
            "selectable": True,
            "model_display_label": "OpenAI Responses",
            "available_models": ["gpt-registry"],
            "models": ["gpt-registry"],
            "model_spec_ids": ["openai::https://openai.example/v1::responses::gpt-registry"],
            "capabilities": ["text"],
            "tags": [],
        }
    }
    json.dumps(artifacts)


def test_llm_registry_artifacts_endpoint_selectable_false_makes_models_unselectable() -> None:
    model = LLMModelMetadata(
        name="gpt-hidden-endpoint",
        provider="openai",
        endpoint="https://openai.example/v1",
    )
    registry = LLMProviderMetadata(
        provider="talkwise",
        endpoints=[
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                default_model="gpt-hidden-endpoint",
                models=[model],
                extra={"selectable": False},
            )
        ],
    )

    artifacts = build_llm_registry_artifacts(registry)

    assert artifacts["endpoints_config"]["openai::https://openai.example/v1::responses"][
        "selectable"
    ] is False
    assert artifacts["model_specs"][0]["enabled"] is True
    assert artifacts["model_specs"][0]["selectable"] is False


def test_llm_registry_artifacts_keep_wire_api_variants_distinct() -> None:
    model = LLMModelMetadata(
        name="gpt-same",
        provider="openai",
        endpoint="https://openai.example/v1",
    )
    registry = LLMProviderMetadata(
        provider="talkwise",
        endpoints=[
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://openai.example/v1",
                wire_api="chat_completions",
                default_model="gpt-same",
                models=[model],
            ),
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                default_model="gpt-same",
                models=[model],
            ),
        ],
    )

    artifacts = build_llm_registry_artifacts(registry)

    assert [spec["id"] for spec in artifacts["model_specs"]] == [
        "openai::https://openai.example/v1::chat_completions::gpt-same",
        "openai::https://openai.example/v1::responses::gpt-same",
    ]
    assert artifacts["endpoints_config"][
        "openai::https://openai.example/v1::chat_completions"
    ]["model_spec_ids"] == [
        "openai::https://openai.example/v1::chat_completions::gpt-same"
    ]
    assert artifacts["endpoints_config"]["openai::https://openai.example/v1::responses"][
        "model_spec_ids"
    ] == ["openai::https://openai.example/v1::responses::gpt-same"]


def test_llm_registry_artifacts_hide_models_marked_out_of_menu() -> None:
    visible_model = LLMModelMetadata(
        name="gpt-visible",
        provider="openai",
        endpoint="https://openai.example/v1",
    )
    hidden_model = LLMModelMetadata(
        name="gpt-hidden",
        provider="openai",
        endpoint="https://openai.example/v1",
        extra={"showInMenu": False},
    )
    registry = LLMProviderMetadata(
        provider="talkwise",
        endpoints=[
            LLMEndpointMetadata(
                provider="openai",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[visible_model, hidden_model],
            )
        ],
    )

    artifacts = build_llm_registry_artifacts(registry)

    assert [spec["model"] for spec in artifacts["model_specs"]] == ["gpt-visible"]
    assert artifacts["endpoints_config"]["openai::https://openai.example/v1::responses"][
        "models"
    ] == ["gpt-visible"]


def test_llm_provider_registry_keeps_model_specs_public_and_secret_free() -> None:
    model = LLMModelMetadata(
        name="gpt-spec",
        provider="openai",
        endpoint="https://openai.example/v1",
        is_default=True,
        extra={
            "model_spec": {
                "latency_tier": "fast",
                "capabilities": {"reasoning": True},
                "api_key": "sk-secret-should-not-appear",
                "headers": {
                    "Authorization": "Bearer secret-should-not-appear",
                    "X-Safe": "kept",
                },
            },
            "endpoint_config": {
                "timeout_ms": 30_000,
                "fallbacks": [
                    {
                        "name": "backup",
                        "apiKey": "sk-secret-should-not-appear",
                        "enabled": True,
                    }
                ],
            },
        },
    )
    endpoint = LLMEndpointMetadata(
        provider="openai",
        endpoint="https://openai.example/v1",
        wire_api="responses",
        default_model="gpt-spec",
        models=[model],
        extra={
            "endpoint_config": {
                "base_path": "/v1",
                "headers": {
                    "Authorization": "Bearer secret-should-not-appear",
                    "X-Provider": "kept",
                },
            },
            "client_secret": "secret-should-not-appear",
        },
    )
    registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-spec",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model],
                endpoints=[endpoint],
            )
        ],
        provider="talkwise",
        extra={
            "configured": True,
            "api_key_configured": True,
            "credentials": {"api_key": "sk-secret-should-not-appear"},
        },
    ).to_dict()
    serialized = json.dumps(registry, sort_keys=True).lower()

    assert "secret-should-not-appear" not in serialized
    assert "authorization" not in serialized
    assert registry["configured"] is True
    assert registry["api_key_configured"] is True

    model_payload = registry["models"][0]
    assert model_payload["model_spec"] == {
        "latency_tier": "fast",
        "capabilities": {"reasoning": True},
        "headers": {"X-Safe": "kept"},
    }
    assert model_payload["endpoint_config"] == {
        "timeout_ms": 30_000,
        "fallbacks": [{"name": "backup", "enabled": True}],
    }
    assert registry["endpoints"][0]["endpoint_config"] == {
        "base_path": "/v1",
        "headers": {"X-Provider": "kept"},
    }


@pytest.mark.asyncio
async def test_llm_registry_selection_metadata_stays_out_of_training_semantics() -> None:
    session_service = TrainingSessionService(id_factory=lambda: "training-registry-1")
    session = await session_service.create_session(
        {
            "role": "Product Manager",
            "level": "Senior",
            "tech_stack": ["Roadmap"],
            "question_type_ratios": {"craft": 1},
            "question_count": 3,
            "category": "sales",
            "scenario_template_id": "enterprise-renewal",
            "metadata": {
                "persona_ids": ["buyer", "cfo"],
                "scenario_id": 9,
                "dispatcher": {"policy": "stakeholder_turns"},
                "evaluation": {"rubric_id": "sales-v1"},
                "growth_report": {"report_id": "growth-1"},
                "live_guidance": {"enabled": True},
            },
        }
    )
    model_spec = LLMModelMetadata(
        name="gpt-registry",
        provider="openai",
        endpoint="https://openai.example/v1",
        is_default=True,
        extra={
            "personaIds": ["model-spec-shadow"],
            "scenarioId": 404,
            "dispatcher": {"policy": "model-spec-shadow"},
            "evaluation": {"rubric_id": "model-spec-shadow"},
            "growthReport": {"report_id": "model-spec-shadow"},
            "report": {"report_id": "model-spec-shadow"},
        },
    )
    registry = build_llm_provider_registry(
        [
            LLMProviderMetadata(
                provider="openai",
                default_model="gpt-registry",
                endpoint="https://openai.example/v1",
                wire_api="responses",
                models=[model_spec],
                endpoints=[
                    LLMEndpointMetadata(
                        provider="openai",
                        endpoint="https://openai.example/v1",
                        wire_api="responses",
                        default_model="gpt-registry",
                        models=[model_spec],
                    )
                ],
            )
        ],
        provider="talkwise",
    ).to_dict()

    metadata = training_core_metadata_for_session(
        session,
        runtime="conversation_message_tree",
        extra={
            "provider": "openai",
            "model": "gpt-selected",
            "providerMetadata": registry,
            "personaIds": ["registry-shadow"],
            "scenarioId": 404,
            "dispatcher": {"policy": "registry-shadow"},
            "evaluation": {"rubric_id": "registry-shadow"},
            "growthReport": {"report_id": "registry-shadow"},
            "liveGuidance": {"enabled": False},
        },
    )

    assert metadata["runtime"] == "conversation_message_tree"
    assert metadata["trainingSessionId"] == "training-registry-1"
    assert metadata["scenarioTemplateId"] == "enterprise-renewal"
    assert metadata["personaIds"] == ["buyer", "cfo"]
    assert metadata["scenarioId"] == 9
    assert metadata["dispatcher"] == {"policy": "stakeholder_turns"}
    assert metadata["evaluation"] == {"rubric_id": "sales-v1"}
    assert metadata["growthReport"] == {"report_id": "growth-1"}
    assert metadata["liveGuidance"] == {"enabled": True}
    assert metadata["provider"] == "openai"
    assert metadata["model"] == "gpt-selected"
    assert metadata["providerMetadata"]["provider"] == "talkwise"
    assert metadata["providerMetadata"]["models"][0]["name"] == "gpt-registry"
    assert metadata["providerMetadata"]["models"][0]["personaIds"] == ["model-spec-shadow"]
    assert metadata["providerMetadata"]["models"][0]["scenarioId"] == 404
    assert metadata["providerMetadata"]["models"][0]["dispatcher"] == {
        "policy": "model-spec-shadow"
    }
    assert metadata["providerMetadata"]["models"][0]["evaluation"] == {
        "rubric_id": "model-spec-shadow"
    }
    assert metadata["providerMetadata"]["models"][0]["growthReport"] == {
        "report_id": "model-spec-shadow"
    }
    assert metadata["providerMetadata"]["models"][0]["report"] == {
        "report_id": "model-spec-shadow"
    }

    metadata["providerMetadata"]["models"][0]["name"] = "mutated"
    metadata["dispatcher"]["policy"] = "mutated"
    assert registry["models"][0]["name"] == "gpt-registry"
    assert session.task_config.metadata["dispatcher"] == {"policy": "stakeholder_turns"}


def test_fallback_llm_provider_metadata_does_not_expose_client_secrets() -> None:
    class LegacyLLM:
        provider = "legacy-openai"
        _default_model = "legacy-model"
        api_key = "sk-secret-should-not-appear"
        _api_key = "sk-secret-should-not-appear"
        token = "bearer-secret-should-not-appear"
        default_headers = {"Authorization": "Bearer bearer-secret-should-not-appear"}

    provider_metadata = _llm_provider_metadata(LegacyLLM())
    request_metadata = _run_request_metadata(
        provider=provider_metadata.provider,
        model=provider_metadata.default_model,
        provider_metadata=provider_metadata,
    )
    serialized = json.dumps(
        {
            "registry": provider_metadata.to_dict(),
            "request": request_metadata,
        },
        sort_keys=True,
    ).lower()

    assert "secret-should-not-appear" not in serialized
    assert "api_key" not in serialized
    assert "authorization" not in serialized
    assert request_metadata["provider_metadata"] == {
        "provider": "legacy-openai",
        "default_model": "legacy-model",
        "endpoint": None,
        "wire_api": None,
        "max_retries": None,
    }


def test_registry_integration_sources_do_not_port_librechat_mongo_or_express() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source_paths = [
        repo_root / "backend" / "api" / "routes" / "training_studio.py",
        repo_root / "backend" / "application" / "ports" / "llm.py",
        repo_root / "backend" / "application" / "services" / "chat_service.py",
        repo_root
        / "backend"
        / "application"
        / "services"
        / "training_studio"
        / "training_core.py",
        repo_root
        / "outside-project"
        / "new-api-main"
        / "web"
        / "src"
        / "features"
        / "training"
        / "studio"
        / "api.ts",
        repo_root
        / "outside-project"
        / "new-api-main"
        / "web"
        / "src"
        / "features"
        / "training"
        / "conversations"
        / "api.ts",
    ]

    for path in source_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "librechat" not in text
        assert "mongoose" not in text
        assert "mongodb" not in text
        assert re.search(r"\bexpress\b", text) is None
