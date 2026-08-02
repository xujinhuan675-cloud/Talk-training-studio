# input: OpenRouter Audio Speech API (/api/v1/audio/speech)
# output: OpenRouterTTSProvider implements TTSPort with streamed mp3 audio bytes
# owner: wanhua.gu
# pos: infrastructure layer - OpenRouter TTS provider; update this header and folder docs when changed
"""OpenRouter TTS provider using the OpenAI-compatible audio speech endpoint."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from application.ports.tts import TTSConfig
from infrastructure.external.newapi_user_gateway import authorization_headers

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_SPEECH_PATH = "/audio/speech"
_DEFAULT_VOICE = "en_paul_neutral"


class OpenRouterTTSProvider:
    """OpenRouter TTS provider with raw audio streaming support."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
            follow_redirects=True,
        )

    async def synthesize_stream(
        self,
        text: str,
        config: TTSConfig,
    ) -> AsyncIterator[bytes]:
        """Stream mp3 audio chunks from OpenRouter TTS."""
        url = f"{self._base_url}{_SPEECH_PATH}"
        voice = config.voice_id or _DEFAULT_VOICE
        if voice in {"alloy", "ash", "ballad", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}:
            voice = _DEFAULT_VOICE

        payload: dict[str, object] = {
            "model": self._model,
            "input": text,
            "voice": voice,
            "response_format": "mp3",
            "speed": config.speed,
        }
        if config.style_instruction:
            payload["instructions"] = config.style_instruction

        headers = {
            **authorization_headers(self._api_key),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }

        async with self._client.stream(
            "POST",
            url,
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                logger.error(
                    "openrouter_tts_error status=%s body=%s",
                    response.status_code,
                    body.decode("utf-8", errors="replace")[:500],
                )
                raise RuntimeError(
                    f"OpenRouter TTS request failed with status {response.status_code}"
                )

            async for chunk in response.aiter_bytes(chunk_size=8192):
                if chunk:
                    yield chunk

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
