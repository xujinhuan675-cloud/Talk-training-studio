# input: OpenAI Whisper-compatible API base URL or transcription endpoint
# output: MinimaxSTTProvider implements STTPort using OpenAI Whisper-compatible multipart transcription
# owner: wanhua.gu
# pos: infrastructure - STT provider implementation; update this header and folder docs when changed
"""STT provider using OpenAI Whisper-compatible API.

Note: MiniMax does not offer a standalone STT API. This provider uses
the OpenAI Whisper API format which is supported by OpenAI, Azure,
and many compatible gateways.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

import httpx

from application.ports.stt import TranscriptionResult

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TRANSCRIPTIONS_PATH = "/audio/transcriptions"


def normalize_transcriptions_url(base_url: str | None = None) -> str:
    """Normalize a gateway URL to the OpenAI-compatible transcriptions endpoint."""
    raw_url = (base_url or _DEFAULT_BASE_URL).strip() or _DEFAULT_BASE_URL
    if not raw_url.startswith(("http://", "https://")):
        raw_url = f"https://{raw_url}"

    parsed = urlparse(raw_url)
    path = parsed.path.rstrip("/")
    lower_path = path.lower()

    if lower_path.endswith(_TRANSCRIPTIONS_PATH):
        normalized_path = path
    elif lower_path.endswith("/audio/speech"):
        normalized_path = f"{path[: -len('/audio/speech')]}{_TRANSCRIPTIONS_PATH}"
    elif lower_path.endswith("/chat/completions"):
        normalized_path = f"{path[: -len('/chat/completions')]}{_TRANSCRIPTIONS_PATH}"
    elif lower_path.endswith("/v1"):
        normalized_path = f"{path}{_TRANSCRIPTIONS_PATH}"
    else:
        normalized_path = f"{path}/v1{_TRANSCRIPTIONS_PATH}" if path else f"/v1{_TRANSCRIPTIONS_PATH}"

    return urlunparse(parsed._replace(path=normalized_path))


class MinimaxSTTProvider:
    """STT provider using OpenAI Whisper-compatible transcription API.

    Despite the name, this uses OpenAI Whisper format since MiniMax
    lacks a standalone STT endpoint. The base_url is configurable
    to support any Whisper-compatible gateway.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = "whisper-1",
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._transcriptions_url = normalize_transcriptions_url(base_url)
        self._model = model
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh",
        audio_format: str = "webm",
    ) -> TranscriptionResult:
        """Transcribe audio using Whisper-compatible API.

        Args:
            audio: Raw audio bytes.
            language: Language hint (e.g., "zh", "en").
            audio_format: Audio format for the file extension hint.

        Returns:
            TranscriptionResult with transcribed text.
        """
        # Whisper API expects multipart form data.
        files = {
            "file": (f"audio.{audio_format}", audio, f"audio/{audio_format}"),
        }
        data = {
            "model": self._model,
            "language": language,
            "response_format": "json",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        response = await self._client.post(
            self._transcriptions_url,
            files=files,
            data=data,
            headers=headers,
        )

        if response.status_code != 200:
            logger.error(
                "stt_transcribe_error",
                status=response.status_code,
                body=response.text[:500],
            )
            raise RuntimeError(
                f"STT transcription failed with status {response.status_code}: "
                f"{response.text[:200]}"
            )

        result = response.json()
        text = result.get("text", "").strip()

        return TranscriptionResult(
            text=text,
            language=language,
            duration_seconds=result.get("duration"),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
