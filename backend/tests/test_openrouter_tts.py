from __future__ import annotations

import httpx
import pytest

from application.ports.tts import TTSConfig
from core.config import LLMSettings, VoiceSettings, settings
import infrastructure.external.voice as voice_lifecycle
from infrastructure.external.voice.openrouter_tts import OpenRouterTTSProvider


class _FakeOpenRouterStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeOpenRouterAsyncClient:
    captured: dict[str, object] = {}

    def __init__(self, **_kwargs) -> None:
        pass

    def stream(self, method: str, url: str, *, json=None, headers=None, **_kwargs):
        self.captured = {
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
        }
        response = httpx.Response(
            200,
            content=b"mp3-audio-bytes",
            request=httpx.Request(method, url),
        )
        return _FakeOpenRouterStream(response)

    async def aclose(self) -> None:
        return None


class _FakeOpenRouterErrorAsyncClient(_FakeOpenRouterAsyncClient):
    def stream(self, method: str, url: str, *, json=None, headers=None, **_kwargs):
        self.captured = {
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
        }
        response = httpx.Response(
            401,
            content=b'{"error":"invalid key"}',
            request=httpx.Request(method, url),
        )
        return _FakeOpenRouterStream(response)


class _FakeOpenRouterTTSProvider:
    instances: list["_FakeOpenRouterTTSProvider"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_openrouter_tts_streams_mp3_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeOpenRouterAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake_client)

    provider = OpenRouterTTSProvider(
        api_key="test-openrouter-key",
        model="openai/gpt-4o-mini-tts-2025-12-15",
    )
    chunks = [
        chunk
        async for chunk in provider.synthesize_stream(
            "Hello from Talk Training Studio.",
            TTSConfig(
                voice_id="en_paul_neutral",
                speed=1.1,
                style_instruction="Speak clearly.",
            ),
        )
    ]

    assert chunks == [b"mp3-audio-bytes"]
    assert fake_client.captured["method"] == "POST"
    assert fake_client.captured["url"] == "https://openrouter.ai/api/v1/audio/speech"
    assert fake_client.captured["headers"]["Authorization"] == "Bearer test-openrouter-key"
    assert fake_client.captured["headers"]["Accept"] == "audio/mpeg"
    assert fake_client.captured["json"] == {
        "model": "openai/gpt-4o-mini-tts-2025-12-15",
        "input": "Hello from Talk Training Studio.",
        "voice": "en_paul_neutral",
        "response_format": "mp3",
        "speed": 1.1,
        "instructions": "Speak clearly.",
    }


@pytest.mark.asyncio
async def test_openrouter_tts_raises_on_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: _FakeOpenRouterErrorAsyncClient())

    provider = OpenRouterTTSProvider(
        api_key="bad-key",
        model="openai/gpt-4o-mini-tts-2025-12-15",
    )

    with pytest.raises(RuntimeError, match="OpenRouter TTS request failed with status 401"):
        async for _chunk in provider.synthesize_stream(
            "Hello.",
            TTSConfig(voice_id="en_paul_neutral"),
        ):
            pass


@pytest.mark.asyncio
async def test_openrouter_tts_falls_back_from_openai_voice_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeOpenRouterAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake_client)

    provider = OpenRouterTTSProvider(
        api_key="test-openrouter-key",
        model="mistralai/voxtral-mini-tts-2603",
    )
    chunks = [
        chunk
        async for chunk in provider.synthesize_stream(
            "Hello.",
            TTSConfig(voice_id="alloy"),
        )
    ]

    assert chunks == [b"mp3-audio-bytes"]
    assert fake_client.captured["json"]["voice"] == "en_paul_neutral"


@pytest.mark.asyncio
async def test_openrouter_tts_lifecycle_reuses_openrouter_llm_key(monkeypatch) -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    voice_lifecycle._tts_client = None
    _FakeOpenRouterTTSProvider.instances = []
    monkeypatch.setattr(
        "infrastructure.external.voice.openrouter_tts.OpenRouterTTSProvider",
        _FakeOpenRouterTTSProvider,
    )
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-openrouter-llm",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="openrouter",
        tts_api_key=None,
        tts_base_url=None,
        tts_model="mistralai/voxtral-mini-tts-2603",
    )

    try:
        await voice_lifecycle.init_tts_client()

        provider = voice_lifecycle.get_tts_client()
        assert isinstance(provider, _FakeOpenRouterTTSProvider)
        assert provider.kwargs == {
            "api_key": "sk-openrouter-llm",
            "model": "mistralai/voxtral-mini-tts-2603",
            "base_url": "https://openrouter.ai/api/v1",
        }
    finally:
        await voice_lifecycle.shutdown_tts_client()
        settings.llm = original_llm
        settings.voice = original_voice


@pytest.mark.asyncio
async def test_openrouter_tts_lifecycle_does_not_reuse_non_openrouter_llm_key(
    monkeypatch,
) -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    voice_lifecycle._tts_client = None
    _FakeOpenRouterTTSProvider.instances = []
    monkeypatch.setattr(
        "infrastructure.external.voice.openrouter_tts.OpenRouterTTSProvider",
        _FakeOpenRouterTTSProvider,
    )
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-flowguide-llm",
        base_url="https://ai.flowguide.cc/v1",
        default_model="gpt-5.5",
    )
    settings.voice = VoiceSettings(
        tts_provider="openrouter",
        tts_api_key=None,
        tts_base_url="https://openrouter.ai/api/v1",
        tts_model="mistralai/voxtral-mini-tts-2603",
    )

    try:
        await voice_lifecycle.init_tts_client()

        assert voice_lifecycle.get_tts_client() is None
        assert _FakeOpenRouterTTSProvider.instances == []
    finally:
        await voice_lifecycle.shutdown_tts_client()
        settings.llm = original_llm
        settings.voice = original_voice
