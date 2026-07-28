from __future__ import annotations

from api import dependencies as deps
from core.config import LLMSettings, VoiceSettings, settings


def test_turn_based_openai_tts_key_availability_does_not_reuse_openrouter_key() -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    original_realtime_key = settings.REALTIME_OPENAI_API_KEY
    original_openai_key = settings.OPENAI_API_KEY
    try:
        settings.REALTIME_OPENAI_API_KEY = None
        settings.OPENAI_API_KEY = None
        settings.llm = LLMSettings(
            provider="openrouter",
            api_key="sk-openrouter",
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
        )
        settings.voice = VoiceSettings(
            tts_provider="openai",
            tts_api_key=None,
            tts_model="gpt-4o-mini-tts",
        )
        assert deps._turn_based_openai_tts_key_available() is False

        settings.voice = VoiceSettings(
            tts_provider="openai",
            tts_api_key="sk-voice",
            tts_model="gpt-4o-mini-tts",
        )
        assert deps._turn_based_openai_tts_key_available() is True

        settings.voice = VoiceSettings(
            tts_provider="openai",
            tts_api_key=None,
            tts_model="gpt-4o-mini-tts",
        )
        settings.REALTIME_OPENAI_API_KEY = "sk-realtime"
        assert deps._turn_based_openai_tts_key_available() is True
    finally:
        settings.llm = original_llm
        settings.voice = original_voice
        settings.REALTIME_OPENAI_API_KEY = original_realtime_key
        settings.OPENAI_API_KEY = original_openai_key
