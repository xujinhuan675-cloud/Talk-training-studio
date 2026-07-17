from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from application.ports.llm import build_llm_provider_registry
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
    json.dumps(payload)


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
    registry = build_llm_provider_registry(
        [
            OpenAIProvider(
                api_key="test-key",
                base_url="https://openai.example",
                provider_name="openai",
                default_model="gpt-registry",
            ).provider_metadata
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
        repo_root / "backend" / "application" / "ports" / "llm.py",
        repo_root / "backend" / "application" / "services" / "chat_service.py",
        repo_root
        / "backend"
        / "application"
        / "services"
        / "training_studio"
        / "training_core.py",
        repo_root / "frontend" / "src" / "services" / "trainingConversation.ts",
    ]

    for path in source_paths:
        text = path.read_text(encoding="utf-8").lower()
        assert "librechat" not in text
        assert "mongoose" not in text
        assert "mongodb" not in text
        assert re.search(r"\bexpress\b", text) is None
