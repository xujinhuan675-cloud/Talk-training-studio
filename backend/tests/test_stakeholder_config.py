# input: core.config.Settings, infrastructure.external.llm.anthropic_provider
# output: StakeholderSettings 配置测试, AnthropicProvider mock 测试
# owner: wanhua.gu
# pos: 测试层 - Story 1.1 配置与 Provider 验收测试；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Tests for Story 1.1: StakeholderSettings + AnthropicProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.config import Settings


def test_stakeholder_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC1: StakeholderSettings has correct default values."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    s = Settings(_env_file=None)

    assert s.stakeholder.model == "claude-opus-4-0-20250514"
    assert s.stakeholder.max_group_rounds == 20
    assert s.stakeholder.persona_dir == "data/personas"
    assert s.stakeholder.anthropic_api_key is None
    assert s.stakeholder.anthropic_base_url is None


def test_stakeholder_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2: Environment variables correctly inject into StakeholderSettings."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("STAKEHOLDER__ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("STAKEHOLDER__ANTHROPIC_BASE_URL", "https://custom.api.com")
    monkeypatch.setenv("STAKEHOLDER__MODEL", "claude-sonnet-4-20250514")
    monkeypatch.setenv("STAKEHOLDER__MAX_GROUP_ROUNDS", "10")
    monkeypatch.setenv("STAKEHOLDER__PERSONA_DIR", "/custom/personas")

    s = Settings(_env_file=None)

    assert s.stakeholder.anthropic_api_key == "sk-ant-test-key"
    assert s.stakeholder.anthropic_base_url == "https://custom.api.com"
    assert s.stakeholder.model == "claude-sonnet-4-20250514"
    assert s.stakeholder.max_group_rounds == 10
    assert s.stakeholder.persona_dir == "/custom/personas"


def test_app_starts_without_stakeholder_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC5: App starts normally when STAKEHOLDER__ANTHROPIC_API_KEY is not set."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    # Explicitly ensure no stakeholder env vars
    monkeypatch.delenv("STAKEHOLDER__ANTHROPIC_API_KEY", raising=False)

    s = Settings(_env_file=None)

    # Settings created successfully
    assert s.stakeholder.anthropic_api_key is None
    # Other settings still functional
    assert s.SECRET_KEY == "test-secret"


def test_openai_compatible_aliases_populate_llm_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Common OpenAI-compatible env names can configure the project LLM."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("LLM__API_KEY", raising=False)
    monkeypatch.delenv("LLM__BASE_URL", raising=False)
    monkeypatch.delenv("LLM__DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LLM__WIRE_API", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-compatible-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "gpt-compatible")
    monkeypatch.setenv("OPENAI_COMPATIBLE_WIRE_API", "responses")

    s = Settings(_env_file=None)

    assert s.llm.api_key == "sk-compatible-test"
    assert s.llm.base_url == "https://gateway.example.com/v1"
    assert s.llm.default_model == "gpt-compatible"
    assert s.llm.wire_api == "responses"


def test_voice_stt_falls_back_to_llm_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """STT can reuse the OpenAI-compatible LLM gateway when no voice key is set."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("VOICE__STT_API_KEY", raising=False)
    monkeypatch.delenv("VOICE__STT_BASE_URL", raising=False)
    monkeypatch.setenv("LLM__API_KEY", "sk-llm-test")
    monkeypatch.setenv("LLM__BASE_URL", "https://gateway.example.com/v1")

    s = Settings(_env_file=None)

    assert s.voice.stt_api_key == "sk-llm-test"
    assert s.voice.stt_base_url == "https://gateway.example.com/v1"


def test_voice_stt_explicit_settings_override_llm_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dedicated STT credentials stay authoritative when configured."""
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("LLM__API_KEY", "sk-llm-test")
    monkeypatch.setenv("LLM__BASE_URL", "https://gateway.example.com/v1")
    monkeypatch.setenv("VOICE__STT_API_KEY", "sk-stt-test")
    monkeypatch.setenv("VOICE__STT_BASE_URL", "https://stt.example.com/v1")

    s = Settings(_env_file=None)

    assert s.voice.stt_api_key == "sk-stt-test"
    assert s.voice.stt_base_url == "https://stt.example.com/v1"


@pytest.mark.asyncio
async def test_anthropic_provider_generate_mock() -> None:
    """AC3: AnthropicProvider.generate() calls Anthropic SDK and returns LLMResponse."""
    from application.ports.llm import LLMMessage, LLMResponse
    from infrastructure.external.llm.anthropic_provider import AnthropicProvider

    # Create provider with mock client
    provider = AnthropicProvider(
        api_key="sk-ant-test",
        default_model="claude-opus-4-0-20250514",
    )

    # Mock the internal Anthropic client
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello from Claude")]
    mock_response.model = "claude-opus-4-0-20250514"
    mock_response.usage = MagicMock(
        input_tokens=10,
        output_tokens=20,
    )
    mock_response.stop_reason = "end_turn"

    provider._client = AsyncMock()
    provider._client.messages.create = AsyncMock(return_value=mock_response)

    messages = [
        LLMMessage(role="system", content="You are a helpful assistant"),
        LLMMessage(role="user", content="Hello"),
    ]

    result = await provider.generate(messages)

    assert isinstance(result, LLMResponse)
    assert result.content == "Hello from Claude"
    assert result.model == "claude-opus-4-0-20250514"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.total_tokens == 30
    assert result.finish_reason == "end_turn"

    # Verify SDK was called with correct params
    provider._client.messages.create.assert_called_once()
    call_kwargs = provider._client.messages.create.call_args
    assert call_kwargs.kwargs["model"] == "claude-opus-4-0-20250514"
