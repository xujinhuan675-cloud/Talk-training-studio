from __future__ import annotations

import httpx
import pytest

from application.ports.tts import TTSConfig
from core.config import VoiceSettings, settings
import infrastructure.external.voice as voice_lifecycle
from infrastructure.external.newapi_user_gateway import (
    bind_user_access_token,
    reset_user_access_token,
)
from infrastructure.external.voice.openai_compatible_stt import (
    OpenAICompatibleSTTProvider,
    normalize_transcriptions_url,
)
from infrastructure.external.voice.openai_compatible_tts import (
    OpenAICompatibleTTSProvider,
)


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, response: httpx.Response | None = None, **_kwargs) -> None:
        self.response = response
        self.captured: dict[str, object] = {}

    def stream(self, method: str, url: str, *, json=None, headers=None, **_kwargs):
        self.captured = {
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
        }
        response = self.response or httpx.Response(
            200,
            content=b"mp3-audio",
            request=httpx.Request(method, url),
        )
        return _FakeStream(response)

    async def aclose(self) -> None:
        return None


class _FakeGatewayProvider:
    instances: list["_FakeGatewayProvider"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.instances.append(self)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (
            "https://gateway.example.com/pg",
            "https://gateway.example.com/pg/audio/transcriptions",
        ),
        (
            "https://gateway.example.com/v1/audio/speech",
            "https://gateway.example.com/v1/audio/transcriptions",
        ),
        (
            "https://gateway.example.com/v1/audio/transcriptions",
            "https://gateway.example.com/v1/audio/transcriptions",
        ),
    ],
)
def test_normalize_transcriptions_url(base_url: str, expected: str) -> None:
    assert normalize_transcriptions_url(base_url) == expected


@pytest.mark.asyncio
async def test_stt_posts_to_newapi_with_current_user_token(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    context_token = bind_user_access_token("dashboard-user-token")
    seen: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"text": "hello", "duration": 1.25})

    provider = OpenAICompatibleSTTProvider(
        api_key="newapi-user-session",
        base_url="https://gateway.example.com/pg",
        model="gpt-4o-mini-transcribe",
    )
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        result = await provider.transcribe(b"audio", language="en")
    finally:
        await provider.close()
        reset_user_access_token(context_token)

    assert seen == {
        "url": "https://gateway.example.com/pg/audio/transcriptions",
        "authorization": "Bearer dashboard-user-token",
    }
    assert result.text == "hello"
    assert result.duration_seconds == 1.25


@pytest.mark.asyncio
async def test_tts_posts_to_newapi_with_native_openai_voice(monkeypatch) -> None:
    fake_client = _FakeAsyncClient()
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: fake_client)
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    context_token = bind_user_access_token("dashboard-user-token")
    provider = OpenAICompatibleTTSProvider(
        api_key="newapi-user-session",
        model="tts-1",
        base_url="https://gateway.example.com/pg",
    )
    try:
        chunks = [
            chunk
            async for chunk in provider.synthesize_stream(
                "Hello.",
                TTSConfig(voice_id="alloy"),
            )
        ]
    finally:
        await provider.close()
        reset_user_access_token(context_token)

    assert chunks == [b"mp3-audio"]
    assert fake_client.captured["url"] == "https://gateway.example.com/pg/audio/speech"
    assert fake_client.captured["headers"]["Authorization"] == "Bearer dashboard-user-token"
    assert fake_client.captured["json"]["voice"] == "alloy"


@pytest.mark.asyncio
async def test_voice_lifecycle_only_initializes_gateway_clients(monkeypatch) -> None:
    original_voice = settings.voice
    voice_lifecycle._tts_client = None
    voice_lifecycle._stt_client = None
    _FakeGatewayProvider.instances = []
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    monkeypatch.setattr(settings, "NEWAPI_USER_RELAY_BASE_URL", "https://gateway.example.com/pg")
    monkeypatch.setattr(
        "infrastructure.external.voice.openai_compatible_tts.OpenAICompatibleTTSProvider",
        _FakeGatewayProvider,
    )
    monkeypatch.setattr(
        "infrastructure.external.voice.openai_compatible_stt.OpenAICompatibleSTTProvider",
        _FakeGatewayProvider,
    )
    settings.voice = VoiceSettings(
        tts_model="tts-1",
        stt_model="gpt-4o-mini-transcribe",
    )

    try:
        await voice_lifecycle.init_tts_client()
        await voice_lifecycle.init_stt_client()

        assert [provider.kwargs for provider in _FakeGatewayProvider.instances] == [
            {
                "api_key": "newapi-user-session",
                "model": "tts-1",
                "base_url": "https://gateway.example.com/pg",
            },
            {
                "api_key": "newapi-user-session",
                "base_url": "https://gateway.example.com/pg",
                "model": "gpt-4o-mini-transcribe",
            },
        ]
    finally:
        await voice_lifecycle.shutdown_stt_client()
        await voice_lifecycle.shutdown_tts_client()
        settings.voice = original_voice


@pytest.mark.asyncio
async def test_voice_lifecycle_has_no_direct_provider_fallback(monkeypatch) -> None:
    voice_lifecycle._tts_client = None
    voice_lifecycle._stt_client = None
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", False)

    await voice_lifecycle.init_tts_client()
    await voice_lifecycle.init_stt_client()

    assert voice_lifecycle.get_tts_client() is None
    assert voice_lifecycle.get_stt_client() is None
