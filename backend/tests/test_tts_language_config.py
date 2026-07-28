from __future__ import annotations

import httpx
import pytest

from application.ports.tts import TTSConfig
from infrastructure.external.voice.elevenlabs_tts import ElevenLabsTTSProvider
from infrastructure.external.voice.minimax_tts import MinimaxTTSProvider


class _FakeStream:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def __aenter__(self) -> httpx.Response:
        return self.response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeAsyncClient:
    def __init__(self, response_content: bytes) -> None:
        self.response_content = response_content
        self.captured: dict[str, object] = {}

    def stream(self, method: str, url: str, *, json=None, headers=None, **_kwargs):
        self.captured = {
            "method": method,
            "url": url,
            "json": json,
            "headers": dict(headers or {}),
        }
        response = httpx.Response(
            200,
            content=self.response_content,
            request=httpx.Request(method, url),
        )
        return _FakeStream(response)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_minimax_tts_sets_language_boost_from_config_language(monkeypatch) -> None:
    fake_client = _FakeAsyncClient(response_content=b"")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: fake_client)

    provider = MinimaxTTSProvider(api_key="test-key", model="speech-2.8-hd")
    chunks = [
        chunk
        async for chunk in provider.synthesize_stream(
            "Please renew the contract.",
            TTSConfig(voice_id="male-qn-qingse", language="zh-CN"),
        )
    ]

    assert chunks == []
    assert fake_client.captured["json"]["language_boost"] == "Chinese"


@pytest.mark.asyncio
async def test_elevenlabs_tts_sets_language_code_from_config_language(monkeypatch) -> None:
    fake_client = _FakeAsyncClient(response_content=b"mp3-audio")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: fake_client)

    provider = ElevenLabsTTSProvider(api_key="test-key", model="eleven_multilingual_v2")
    chunks = [
        chunk
        async for chunk in provider.synthesize_stream(
            "Please renew the contract.",
            TTSConfig(voice_id="voice-test", language="zh-CN"),
        )
    ]

    assert chunks == [b"mp3-audio"]
    assert fake_client.captured["json"]["language_code"] == "zh"
