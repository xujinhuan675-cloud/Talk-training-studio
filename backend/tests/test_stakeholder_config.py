"""Stakeholder and gateway model configuration tests."""

from __future__ import annotations

import pytest

from core.config import Settings


def test_stakeholder_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    settings = Settings(_env_file=None)

    assert settings.stakeholder.max_group_rounds == 20
    assert settings.stakeholder.persona_dir == "data/personas"


def test_stakeholder_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("STAKEHOLDER__MAX_GROUP_ROUNDS", "10")
    monkeypatch.setenv("STAKEHOLDER__PERSONA_DIR", "/custom/personas")

    settings = Settings(_env_file=None)

    assert settings.stakeholder.max_group_rounds == 10
    assert settings.stakeholder.persona_dir == "/custom/personas"


def test_openai_compatible_aliases_populate_llm_model_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.delenv("LLM__DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("LLM__WIRE_API", raising=False)
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "gpt-compatible")
    monkeypatch.setenv("OPENAI_COMPATIBLE_WIRE_API", "responses")

    settings = Settings(_env_file=None)

    assert settings.llm.default_model == "gpt-compatible"
    assert settings.llm.wire_api == "responses"


def test_voice_models_default_to_newapi_channel_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    settings = Settings(_env_file=None)

    assert settings.voice.stt_model == "gpt-4o-mini-transcribe"
    assert settings.voice.tts_model == "tts-1"


def test_voice_models_can_be_selected_from_newapi_channel_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("VOICE__STT_MODEL", "whisper-1")
    monkeypatch.setenv("VOICE__TTS_MODEL", "gpt-4o-mini-tts")

    settings = Settings(_env_file=None)

    assert settings.voice.stt_model == "whisper-1"
    assert settings.voice.tts_model == "gpt-4o-mini-tts"
