from __future__ import annotations

import importlib.util
import json
import sys
import types

from application.ports.llm import build_llm_provider_registry
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
