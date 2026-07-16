from __future__ import annotations

import httpx
import pytest

from infrastructure.external.voice.minimax_stt import (
    MinimaxSTTProvider,
    normalize_transcriptions_url,
)


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (None, "https://api.openai.com/v1/audio/transcriptions"),
        ("ai.flowguide.cc", "https://ai.flowguide.cc/v1/audio/transcriptions"),
        ("https://ai.flowguide.cc", "https://ai.flowguide.cc/v1/audio/transcriptions"),
        ("https://api.openai.com/v1", "https://api.openai.com/v1/audio/transcriptions"),
        (
            "https://gateway.example.com/v1/chat/completions",
            "https://gateway.example.com/v1/audio/transcriptions",
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
def test_normalize_transcriptions_url(base_url: str | None, expected: str) -> None:
    assert normalize_transcriptions_url(base_url) == expected


async def test_transcribe_posts_to_normalized_transcriptions_url() -> None:
    seen_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(200, json={"text": "hello from voice", "duration": 1.25})

    provider = MinimaxSTTProvider(
        api_key="sk-test",
        base_url="https://ai.flowguide.cc",
        model="whisper-1",
    )
    await provider._client.aclose()
    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        result = await provider.transcribe(b"audio-bytes", language="en", audio_format="webm")
    finally:
        await provider.close()

    assert seen_urls == ["https://ai.flowguide.cc/v1/audio/transcriptions"]
    assert result.text == "hello from voice"
    assert result.language == "en"
    assert result.duration_seconds == 1.25
