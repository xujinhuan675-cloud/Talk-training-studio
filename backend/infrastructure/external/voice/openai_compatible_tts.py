# input: NewAPI OpenAI-compatible audio speech endpoint and request-scoped user bearer
# output: OpenAICompatibleTTSProvider implementing TTSPort with streamed audio bytes
# owner: TalkWise platform integration
# pos: infrastructure - gateway-only TTS protocol client
"""TTS client for NewAPI's OpenAI-compatible audio speech relay."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from application.ports.tts import TTSConfig
from infrastructure.external.newapi_user_gateway import authorization_headers

logger = logging.getLogger(__name__)

_SPEECH_PATH = "/audio/speech"
_DEFAULT_VOICE = "alloy"
_OPENAI_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
}


def _uses_native_openai_voices(model: str) -> bool:
    normalized = model.strip().lower()
    return "/" not in normalized and normalized.startswith(("tts-", "gpt-4o-mini-tts"))


class OpenAICompatibleTTSProvider:
    """Stream speech through the authenticated NewAPI user relay."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
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
        url = f"{self._base_url}{_SPEECH_PATH}"
        voice = config.voice_id or _DEFAULT_VOICE
        if voice in _OPENAI_VOICES and not _uses_native_openai_voices(self._model):
            voice = "en_paul_neutral"

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
                    "newapi_tts_error status=%s body=%s",
                    response.status_code,
                    body.decode("utf-8", errors="replace")[:500],
                )
                raise RuntimeError(
                    f"NewAPI TTS request failed with status {response.status_code}"
                )

            async for chunk in response.aiter_bytes(chunk_size=8192):
                if chunk:
                    yield chunk

    async def close(self) -> None:
        await self._client.aclose()
