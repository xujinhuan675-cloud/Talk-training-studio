# input: NewAPI OpenAI-compatible transcription relay and request-scoped user bearer
# output: OpenAICompatibleSTTProvider implementing STTPort
# owner: TalkWise platform integration
# pos: infrastructure - gateway-only STT protocol client
"""STT client for NewAPI's OpenAI-compatible transcription relay."""

from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse

import httpx

from application.ports.stt import TranscriptionResult
from infrastructure.external.newapi_user_gateway import authorization_headers

logger = logging.getLogger(__name__)

_TRANSCRIPTIONS_PATH = "/audio/transcriptions"


def normalize_transcriptions_url(base_url: str) -> str:
    """Normalize a gateway URL to its OpenAI-compatible transcription endpoint."""
    raw_url = base_url.strip()
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
    elif lower_path.endswith(("/v1", "/pg")):
        normalized_path = f"{path}{_TRANSCRIPTIONS_PATH}"
    else:
        normalized_path = f"{path}/v1{_TRANSCRIPTIONS_PATH}" if path else f"/v1{_TRANSCRIPTIONS_PATH}"

    return urlunparse(parsed._replace(path=normalized_path))


class OpenAICompatibleSTTProvider:
    """Transcribe audio through the authenticated NewAPI user relay."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
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
        response = await self._client.post(
            self._transcriptions_url,
            files={"file": (f"audio.{audio_format}", audio, f"audio/{audio_format}")},
            data={
                "model": self._model,
                "language": language,
                "response_format": "json",
            },
            headers=authorization_headers(self._api_key),
        )

        if response.status_code != 200:
            logger.error(
                "newapi_stt_error status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(
                f"NewAPI STT request failed with status {response.status_code}: "
                f"{response.text[:200]}"
            )

        result = response.json()
        return TranscriptionResult(
            text=result.get("text", "").strip(),
            language=language,
            duration_seconds=result.get("duration"),
        )

    async def close(self) -> None:
        await self._client.aclose()
