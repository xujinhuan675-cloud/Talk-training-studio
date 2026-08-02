"""Tests for OpenAIProvider wire API variants."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.ports.llm import LLMMessage
from core.config import settings
from infrastructure.external.llm.openai_provider import OpenAIProvider
from infrastructure.external.newapi_user_gateway import bind_user_access_token


@pytest.mark.asyncio
async def test_responses_generate_preserves_message_roles() -> None:
    provider = OpenAIProvider(api_key="test-key", wire_api="responses", default_model="gpt-test")
    response = SimpleNamespace(
        output_text="hello",
        model="gpt-test",
        usage=SimpleNamespace(input_tokens=3, output_tokens=4, total_tokens=7),
        status="completed",
    )
    provider._client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response))
    )

    result = await provider.generate(
        [
            LLMMessage(role="system", content="system prompt"),
            LLMMessage(role="user", content="hello"),
        ],
        temperature=0.1,
        max_tokens=50,
    )

    assert result.content == "hello"
    assert result.prompt_tokens == 3
    assert result.completion_tokens == 4
    assert result.total_tokens == 7

    call_kwargs = provider._client.responses.create.call_args.kwargs
    assert call_kwargs["input"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
    ]
    assert call_kwargs["max_output_tokens"] == 50


@pytest.mark.asyncio
async def test_responses_generate_structured_uses_json_schema_format() -> None:
    provider = OpenAIProvider(api_key="test-key", wire_api="responses", default_model="gpt-test")
    response = SimpleNamespace(
        output_text='{"answer":"ok"}',
        model="gpt-test",
        usage=None,
        status="completed",
    )
    provider._client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=response))
    )
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    parsed = await provider.generate_structured(
        [LLMMessage(role="user", content="Return JSON")],
        schema=schema,
        schema_name="test_schema",
        schema_description="Test schema",
    )

    assert parsed == {"answer": "ok"}
    assert "additionalProperties" not in schema

    response_format = provider._client.responses.create.call_args.kwargs["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["name"] == "test_schema"
    assert response_format["description"] == "Test schema"
    assert response_format["strict"] is False
    assert response_format["schema"]["additionalProperties"] is False


def test_openai_provider_adds_v1_to_bare_compatible_base_url() -> None:
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://gateway.example.com",
        default_model="gpt-test",
    )

    assert str(provider._client.base_url) == "https://gateway.example.com/v1/"


def test_openai_provider_preserves_explicit_compatible_base_url_path() -> None:
    provider = OpenAIProvider(
        api_key="test-key",
        base_url="https://gateway.example.com/openai/v1",
        default_model="gpt-test",
    )

    assert str(provider._client.base_url) == "https://gateway.example.com/openai/v1/"


def test_openai_provider_uses_project_user_agent() -> None:
    provider = OpenAIProvider(api_key="test-key", user_agent="TestApp/1.0")

    assert provider._client.default_headers["User-Agent"] == "TestApp/1.0"


@pytest.mark.asyncio
async def test_openai_provider_overrides_static_key_with_current_newapi_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    bind_user_access_token("dashboard-user-token")
    provider = OpenAIProvider(api_key="newapi-user-session", default_model="gpt-test")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="hello"),
                finish_reason="stop",
            )
        ],
        usage=None,
        model="gpt-test",
    )
    create = AsyncMock(return_value=response)
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    await provider.generate([LLMMessage(role="user", content="hello")])

    assert create.call_args.kwargs["extra_headers"] == {
        "Authorization": "Bearer dashboard-user-token"
    }
