# input: Volcengine Doubao Speech ASR/TTS APIs
# output: VolcengineSTTProvider and VolcengineTTSProvider implementing STTPort/TTSPort
# owner: wanhua.gu
# pos: infrastructure layer - Volcengine/Doubao voice providers
"""Volcengine/Doubao voice providers.

The current TalkWise voice ports are turn-based:

* STT receives one audio blob and returns text.
* TTS receives one text string and streams audio bytes.

Volcengine's Doubao Speech APIs are provider-native protocols, not
OpenAI-compatible audio endpoints. This module keeps that protocol handling at
the infrastructure edge so the application layer can continue using STTPort and
TTSPort.
"""

from __future__ import annotations

import base64
import gzip
import inspect
import json
import logging
import uuid
from typing import Any, AsyncIterator, Callable, Iterator, Mapping
from urllib.parse import urlparse, urlunparse

import httpx

from application.ports.stt import TranscriptionResult
from application.ports.tts import TTSConfig

logger = logging.getLogger(__name__)

_DEFAULT_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
_DEFAULT_TTS_MODEL = "seed-tts-2.0"
_DEFAULT_TTS_VOICE = "zh_female_vv_uranus_bigtts"
_DEFAULT_ASR_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
_DEFAULT_ASR_MODEL = "volc.bigasr.sauc.duration"
_DEFAULT_ASR_SAMPLE_RATE = 16000
_DEFAULT_ASR_CHUNK_SIZE = 3200

_MESSAGE_TYPE_FULL_CLIENT_REQUEST = 0b0001
_MESSAGE_TYPE_AUDIO_ONLY_REQUEST = 0b0010
_MESSAGE_TYPE_FULL_SERVER_RESPONSE = 0b1001
_MESSAGE_TYPE_ERROR = 0b1111
_FLAG_POS_SEQUENCE = 0b0001
_FLAG_NEG_SEQUENCE = 0b0011
_SERIALIZATION_NONE = 0b0000
_SERIALIZATION_JSON = 0b0001
_COMPRESSION_GZIP = 0b0001


class VolcengineTTSProvider:
    """Volcengine Doubao TTS provider using HTTP chunked streaming."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = _DEFAULT_TTS_MODEL,
        base_url: str = _DEFAULT_TTS_URL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_TTS_MODEL
        self._url = normalize_volcengine_tts_url(base_url)
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0))

    async def synthesize_stream(
        self,
        text: str,
        config: TTSConfig,
    ) -> AsyncIterator[bytes]:
        """Stream mp3 audio chunks from Volcengine Doubao TTS."""

        payload = build_volcengine_tts_payload(text, config)
        headers = {
            "X-Api-Key": self._api_key,
            "X-Api-Resource-Id": self._model,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "keep-alive",
        }

        async with self._client.stream(
            "POST",
            self._url,
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                logger.error(
                    "volcengine_tts_error status=%s body=%s",
                    response.status_code,
                    body.decode("utf-8", errors="replace")[:500],
                )
                raise RuntimeError(
                    f"Volcengine TTS request failed with status {response.status_code}"
                )

            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = _parse_volcengine_tts_line(line)
                if chunk:
                    yield chunk

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


class VolcengineSTTProvider:
    """Volcengine Doubao ASR provider using the WebSocket binary protocol."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = _DEFAULT_ASR_MODEL,
        base_url: str = _DEFAULT_ASR_URL,
        timeout: float = 30.0,
        chunk_size: int = _DEFAULT_ASR_CHUNK_SIZE,
        websocket_connector: Callable[..., Any] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model or _DEFAULT_ASR_MODEL
        self._url = normalize_volcengine_asr_url(base_url)
        self._timeout = timeout
        self._chunk_size = chunk_size if chunk_size > 0 else _DEFAULT_ASR_CHUNK_SIZE
        self._websocket_connector = websocket_connector
        self._request_id_factory = request_id_factory or (lambda: str(uuid.uuid4()))

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh",
        audio_format: str = "webm",
    ) -> TranscriptionResult:
        """Transcribe one audio blob through Volcengine's streaming ASR API."""

        request_id = self._request_id_factory()
        headers = build_volcengine_asr_headers(
            api_key=self._api_key,
            model=self._model,
            request_id=request_id,
        )
        request_payload = build_volcengine_asr_request_payload(
            request_id=request_id,
            language=language,
            audio_format=audio_format,
        )

        final_text = ""
        duration_seconds: float | None = None
        connector = self._websocket_connector or _connect_volcengine_websocket
        async with connector(self._url, headers=headers, timeout=self._timeout) as websocket:
            await websocket.send(encode_volcengine_asr_json_request(request_payload))
            for index, chunk in enumerate(_iter_audio_chunks(audio, self._chunk_size), start=1):
                final = index * self._chunk_size >= len(audio)
                sequence = -index if final else index
                await websocket.send(encode_volcengine_asr_audio_request(chunk, sequence=sequence))

                response = await websocket.recv()
                parsed = parse_volcengine_asr_response(response)
                text = _extract_volcengine_asr_text(parsed)
                if text:
                    final_text = text
                duration_seconds = _extract_volcengine_asr_duration(parsed) or duration_seconds
                if final:
                    break

        return TranscriptionResult(
            text=final_text.strip(),
            language=language,
            duration_seconds=duration_seconds,
        )

    async def close(self) -> None:
        """No persistent client to close for WebSocket STT."""
        return None


def normalize_volcengine_tts_url(base_url: str | None = None) -> str:
    """Normalize user input to the Volcengine unidirectional TTS HTTP endpoint."""

    return _normalize_url(
        base_url,
        default_url=_DEFAULT_TTS_URL,
        default_scheme="https",
        default_path="/api/v3/tts/unidirectional",
    )


def normalize_volcengine_asr_url(base_url: str | None = None) -> str:
    """Normalize user input to the Volcengine bigmodel ASR WebSocket endpoint."""

    return _normalize_url(
        base_url,
        default_url=_DEFAULT_ASR_URL,
        default_scheme="wss",
        default_path="/api/v3/sauc/bigmodel",
    )


def build_volcengine_tts_payload(text: str, config: TTSConfig) -> dict[str, Any]:
    """Build the provider-native TTS request body."""

    req_params: dict[str, Any] = {
        "text": text,
        "speaker": config.voice_id or _DEFAULT_TTS_VOICE,
        "audio_params": {
            "format": "mp3",
            "sample_rate": 24000,
        },
    }
    if config.speed and config.speed != 1.0:
        req_params["speed"] = config.speed
    if config.volume and config.volume != 1.0:
        req_params["volume"] = config.volume
    if config.pitch:
        req_params["pitch"] = int(config.pitch)
    if config.language:
        req_params["explicit_language"] = _normalize_language(config.language)
    if config.style_instruction:
        req_params["additions"] = json.dumps(
            {"context_texts": [config.style_instruction]},
            ensure_ascii=False,
        )

    return {"req_params": req_params}


def build_volcengine_asr_headers(
    *,
    api_key: str,
    model: str,
    request_id: str,
) -> dict[str, str]:
    """Build ASR request headers for the newer console API key flow."""

    return {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": model,
        "X-Api-Request-Id": request_id,
        "X-Api-Sequence": "-1",
    }


def build_volcengine_asr_request_payload(
    *,
    request_id: str,
    language: str,
    audio_format: str,
) -> dict[str, Any]:
    """Build the ASR full-client request payload."""

    normalized_format = _normalize_audio_format(audio_format)
    audio_config: dict[str, Any] = {
        "format": normalized_format,
        "codec": "opus" if normalized_format == "ogg" else "raw",
        "rate": _DEFAULT_ASR_SAMPLE_RATE,
        "bits": 16,
        "channel": 1,
    }
    normalized_language = _normalize_asr_language(language)
    if normalized_language:
        audio_config["language"] = normalized_language

    return {
        "user": {"uid": "talkwise"},
        "audio": audio_config,
        "request": {
            "reqid": request_id,
            "model_name": "bigmodel",
            "enable_punc": True,
            "enable_itn": True,
            "enable_ddc": False,
        },
    }


def encode_volcengine_asr_json_request(payload: Mapping[str, Any]) -> bytes:
    """Encode an ASR full-client JSON request frame."""

    data = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return _encode_volcengine_frame(
        message_type=_MESSAGE_TYPE_FULL_CLIENT_REQUEST,
        flags=_FLAG_POS_SEQUENCE,
        serialization=_SERIALIZATION_JSON,
        compression=_COMPRESSION_GZIP,
        payload=data,
        sequence=1,
    )


def encode_volcengine_asr_audio_request(audio: bytes, *, sequence: int) -> bytes:
    """Encode an ASR audio-only request frame."""

    data = gzip.compress(audio)
    return _encode_volcengine_frame(
        message_type=_MESSAGE_TYPE_AUDIO_ONLY_REQUEST,
        flags=_FLAG_NEG_SEQUENCE if sequence < 0 else _FLAG_POS_SEQUENCE,
        serialization=_SERIALIZATION_NONE,
        compression=_COMPRESSION_GZIP,
        payload=data,
        sequence=sequence,
    )


def parse_volcengine_asr_response(raw: bytes | str) -> dict[str, Any]:
    """Parse a Volcengine ASR binary response into a JSON mapping."""

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Volcengine ASR returned non-JSON text response") from exc
    if len(raw) < 8:
        raise RuntimeError("Volcengine ASR response frame is too short")

    first, second, third = raw[0], raw[1], raw[2]
    header_size = (first & 0x0F) * 4
    message_type = second >> 4
    flags = second & 0x0F
    serialization = third >> 4
    compression = third & 0x0F
    offset = header_size
    if flags in {_FLAG_POS_SEQUENCE, _FLAG_NEG_SEQUENCE}:
        if len(raw) < offset + 4:
            raise RuntimeError("Volcengine ASR response sequence is missing")
        offset += 4
    if message_type == _MESSAGE_TYPE_ERROR:
        if len(raw) < offset + 8:
            raise RuntimeError("Volcengine ASR error frame is too short")
        code = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
        size = int.from_bytes(raw[offset + 4 : offset + 8], "big", signed=False)
        message = raw[offset + 8 : offset + 8 + size].decode("utf-8", errors="replace")
        raise RuntimeError(f"Volcengine ASR error {code}: {message}")

    if message_type != _MESSAGE_TYPE_FULL_SERVER_RESPONSE:
        return {}

    if len(raw) < offset + 4:
        raise RuntimeError("Volcengine ASR response payload size is missing")
    payload_size = int.from_bytes(raw[offset : offset + 4], "big", signed=False)
    payload = raw[offset + 4 : offset + 4 + payload_size]
    if compression == _COMPRESSION_GZIP:
        payload = gzip.decompress(payload)
    if serialization == _SERIALIZATION_JSON:
        return json.loads(payload.decode("utf-8"))
    return {}


def _parse_volcengine_tts_line(line: str) -> bytes | None:
    text = line.strip()
    if text.startswith("data:"):
        text = text[5:].strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.debug("volcengine_tts_non_json_line")
        return None

    code = payload.get("code")
    if code not in {0, 20000000, None}:
        raise RuntimeError(
            f"Volcengine TTS stream failed with code {code}: {payload.get('message', '')}"
        )
    audio = payload.get("data")
    if not audio:
        return None
    try:
        return base64.b64decode(audio)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Volcengine TTS returned invalid base64 audio data") from exc


def _connect_volcengine_websocket(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - depends on optional runtime env
        raise RuntimeError(
            "Volcengine STT requires the 'websockets' package. "
            "Install backend voice dependencies before using this provider."
        ) from exc

    connect_kwargs: dict[str, Any] = {
        "open_timeout": timeout,
        "close_timeout": 5,
    }
    try:
        parameters = inspect.signature(websockets.connect).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive for exotic callables
        parameters = {}
    header_kwarg = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    connect_kwargs[header_kwarg] = dict(headers)
    return websockets.connect(url, **connect_kwargs)


def _encode_volcengine_frame(
    *,
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
    payload: bytes,
    sequence: int,
) -> bytes:
    header = bytes(
        [
            0x11,
            ((message_type & 0x0F) << 4) | (flags & 0x0F),
            ((serialization & 0x0F) << 4) | (compression & 0x0F),
            0x00,
        ]
    )
    return (
        header
        + int(sequence).to_bytes(4, "big", signed=True)
        + len(payload).to_bytes(4, "big", signed=False)
        + payload
    )


def _normalize_url(
    base_url: str | None,
    *,
    default_url: str,
    default_scheme: str,
    default_path: str,
) -> str:
    raw_url = (base_url or default_url).strip() or default_url
    if not raw_url.startswith(("http://", "https://", "ws://", "wss://")):
        raw_url = f"{default_scheme}://{raw_url}"

    parsed = urlparse(raw_url)
    if parsed.path and parsed.path != "/":
        return urlunparse(parsed)
    return urlunparse(parsed._replace(path=default_path))


def _normalize_language(language: str) -> str:
    return language.strip().split("-", 1)[0].lower() or "zh"


def _normalize_asr_language(language: str) -> str | None:
    text = (language or "").strip()
    if not text:
        return None
    aliases = {
        "zh": "zh-CN",
        "zh_cn": "zh-CN",
        "zh-cn": "zh-CN",
        "en": "en-US",
        "en_us": "en-US",
        "en-us": "en-US",
    }
    return aliases.get(text.lower().replace("_", "-"), text)


def _normalize_audio_format(audio_format: str) -> str:
    text = (audio_format or "wav").strip().lower()
    if text in {"pcm16", "raw"}:
        return "pcm"
    if text in {"opus", "ogg_opus", "ogg-opus"}:
        return "ogg"
    if text in {"wav", "mp3", "ogg", "pcm"}:
        return text
    if text == "webm":
        raise ValueError(
            "Volcengine ASR supports pcm, wav, ogg/opus, or mp3 audio; "
            "browser WebM audio must be converted before transcription."
        )
    raise ValueError(f"Unsupported Volcengine ASR audio format: {audio_format}")


def _iter_audio_chunks(audio: bytes, chunk_size: int) -> Iterator[bytes]:
    if not audio:
        yield b""
        return
    for offset in range(0, len(audio), chunk_size):
        yield audio[offset : offset + chunk_size]


def _extract_volcengine_asr_text(payload: Mapping[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, Mapping):
            text = first.get("text")
            if isinstance(text, str):
                return text
    if isinstance(result, Mapping):
        text = result.get("text")
        if isinstance(text, str):
            return text
    text = payload.get("text")
    return text if isinstance(text, str) else ""


def _extract_volcengine_asr_duration(payload: Mapping[str, Any]) -> float | None:
    addition = payload.get("addition")
    raw_duration: Any = None
    if isinstance(addition, Mapping):
        raw_duration = addition.get("duration")
    if raw_duration is None:
        result = payload.get("result")
        if isinstance(result, Mapping):
            raw_duration = result.get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        return None
    return duration / 1000 if duration > 100 else duration
