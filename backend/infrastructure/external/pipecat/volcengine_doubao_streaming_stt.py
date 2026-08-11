"""Pipecat streaming STT for Doubao through the authenticated NewAPI relay.

The TalkWise process deliberately speaks an OpenAI-style, provider-neutral
WebSocket protocol. NewAPI owns the Volcengine credentials, binary ASR V3
protocol, billing, and provider error translation.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import json
import logging
import uuid
from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import suppress
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from infrastructure.external.newapi_user_gateway import (
    authorization_headers,
    user_relay_realtime_url,
)
from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.services.settings import STTSettings
from pipecat.services.stt_service import WebsocketSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

logger = logging.getLogger(__name__)

VOLCENGINE_DOUBAO_STREAMING_PROVIDER = "volcengine.doubao"
DEFAULT_DOUBAO_STREAMING_STT_MODEL = "volc.bigasr.sauc.duration"
DEFAULT_DOUBAO_STREAMING_STT_SAMPLE_RATE = 16000

_TRANSCRIPT_DELTA_EVENTS = frozenset(
    {
        "conversation.item.input_audio_transcription.delta",
        "conversation.item.input.audio.transcription.delta",
        "input.audio.transcription.delta",
        "transcript.delta",
    }
)
_TRANSCRIPT_FINAL_EVENTS = frozenset(
    {
        "conversation.item.input_audio_transcription.completed",
        "conversation.item.input.audio.transcription.completed",
        "input.audio.transcription.completed",
        "transcript.completed",
        "transcript.done",
        "transcript.final",
    }
)
_SESSION_READY_EVENTS = frozenset(
    {
        "session.created",
        "session.ready",
        "session.updated",
    }
)

_WebsocketConnector = Callable[..., Any]
_FallbackFactory = Callable[[], Any]


class DoubaoStreamingSTTGatewayError(RuntimeError):
    """A secret-free, structured failure from the streaming gateway boundary."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        category: str,
        retryable: bool,
        fatal: bool,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.category = category
        self.retryable = retryable
        self.fatal = fatal

    def to_realtime_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": VOLCENGINE_DOUBAO_STREAMING_PROVIDER,
            "feature": "stt:volcengine.doubao.streaming",
            "errorCategory": self.category,
            "retryable": self.retryable,
            "fatal": self.fatal,
        }


def normalize_doubao_streaming_stt_url(
    gateway_ws_url: str | None,
    *,
    model: str,
) -> str:
    """Normalize a NewAPI relay URL and attach the routing model."""

    raw_url = str(gateway_ws_url or user_relay_realtime_url()).strip()
    if not raw_url:
        raise DoubaoStreamingSTTGatewayError(
            "Doubao streaming STT requires a NewAPI gateway WebSocket URL",
            code="DOUBAO_STREAMING_STT_GATEWAY_URL_MISSING",
            phase="configuration",
            category="configuration",
            retryable=False,
            fatal=True,
        )
    if not raw_url.startswith(("ws://", "wss://", "http://", "https://")):
        raw_url = f"wss://{raw_url}"
    parsed = urlparse(raw_url)
    scheme = "wss" if parsed.scheme == "https" else "ws" if parsed.scheme == "http" else parsed.scheme
    path = parsed.path.rstrip("/")
    if not path:
        path = "/pg/realtime"
    elif path.endswith(("/pg", "/v1")):
        path = f"{path}/realtime"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["model"] = model
    return urlunparse(parsed._replace(scheme=scheme, path=path, query=urlencode(query)))


def build_doubao_streaming_stt_session_event(
    *,
    model: str,
    language: str,
    sample_rate: int,
) -> dict[str, Any]:
    """Build the provider-neutral session contract understood by NewAPI."""

    return {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": model,
                "language": language,
            },
            "turn_detection": None,
            "metadata": {
                "sample_rate": sample_rate,
                "channels": 1,
            },
        },
    }


def build_doubao_streaming_stt_audio_event(audio: bytes) -> dict[str, Any]:
    """Encode one PCM chunk for the NewAPI realtime relay."""

    return {
        "type": "input_audio_buffer.append",
        "audio": base64.b64encode(audio).decode("ascii"),
    }


class VolcengineDoubaoStreamingSTTService(WebsocketSTTService):
    """Stream PCM audio to NewAPI and translate transcript events to Pipecat frames.

    ``app_key`` and ``resource_id`` are compatibility-only constructor slots.
    Provider credentials must stay in NewAPI and non-``None`` values are rejected.
    The optional fallback factory is exposed for pipeline-level failover policy;
    this service never switches to batch transcription on its own.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        gateway_ws_url: str | None = None,
        ws_url: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_DOUBAO_STREAMING_STT_MODEL,
        language: str = "zh",
        sample_rate: int = DEFAULT_DOUBAO_STREAMING_STT_SAMPLE_RATE,
        timeout: float = 10.0,
        websocket_connector: _WebsocketConnector | None = None,
        request_id_factory: Callable[[], str] | None = None,
        fallback_factory: _FallbackFactory | None = None,
        app_key: str | None = None,
        resource_id: str | None = None,
        ttfs_p99_latency: float | None = None,
        **kwargs: Any,
    ) -> None:
        if app_key is not None or resource_id is not None:
            raise DoubaoStreamingSTTGatewayError(
                "TalkWise must not receive raw Volcengine streaming credentials",
                code="DOUBAO_STREAMING_STT_DIRECT_CREDENTIAL_REJECTED",
                phase="configuration",
                category="security",
                retryable=False,
                fatal=True,
            )
        if sample_rate != DEFAULT_DOUBAO_STREAMING_STT_SAMPLE_RATE:
            raise DoubaoStreamingSTTGatewayError(
                f"Doubao streaming STT requires {DEFAULT_DOUBAO_STREAMING_STT_SAMPLE_RATE} Hz PCM",
                code="DOUBAO_STREAMING_STT_AUDIO_FORMAT_INVALID",
                phase="configuration",
                category="configuration",
                retryable=False,
                fatal=True,
            )
        normalized_model = str(model or "").strip()
        if not normalized_model:
            raise DoubaoStreamingSTTGatewayError(
                "Doubao streaming STT model is required",
                code="DOUBAO_STREAMING_STT_MODEL_MISSING",
                phase="configuration",
                category="configuration",
                retryable=False,
                fatal=True,
            )

        explicit_urls = [value for value in (gateway_ws_url, ws_url, base_url) if value]
        if len({str(value).strip() for value in explicit_urls}) > 1:
            raise DoubaoStreamingSTTGatewayError(
                "Conflicting NewAPI streaming gateway URLs were provided",
                code="DOUBAO_STREAMING_STT_GATEWAY_URL_CONFLICT",
                phase="configuration",
                category="configuration",
                retryable=False,
                fatal=True,
            )

        settings = STTSettings(model=normalized_model, language=language)
        super().__init__(
            sample_rate=sample_rate,
            settings=settings,
            ttfs_p99_latency=ttfs_p99_latency,
            **kwargs,
        )
        self._api_key = str(api_key or "").strip() or None
        self._gateway_ws_url = normalize_doubao_streaming_stt_url(
            gateway_ws_url or ws_url or base_url,
            model=normalized_model,
        )
        self._model = normalized_model
        self._language = str(language or "zh").strip() or "zh"
        self._timeout = max(0.1, float(timeout))
        self._websocket_connector = websocket_connector or _connect_newapi_streaming_websocket
        self._request_id_factory = request_id_factory or (lambda: str(uuid.uuid4()))
        self._fallback_factory = fallback_factory
        self._request_id = ""
        self._websocket_context: Any | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._session_ready = asyncio.Event()
        self._audio_since_commit = False
        self._interim_text = ""

    @property
    def gateway_ws_url(self) -> str:
        return self._gateway_ws_url

    @property
    def fallback_factory(self) -> _FallbackFactory | None:
        """Return the pipeline-owned fallback without instantiating it."""

        return self._fallback_factory

    def can_generate_metrics(self) -> bool:
        return True

    async def start(self, frame: StartFrame) -> None:
        await super().start(frame)
        await self._connect()

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
        """Send one raw PCM chunk; receive-loop callbacks publish transcripts."""

        if not audio:
            yield None
            return
        await self._send_gateway_event(build_doubao_streaming_stt_audio_event(audio))
        self._audio_since_commit = True
        yield None

    async def commit_audio(self) -> None:
        """Commit the current client-VAD turn without changing providers."""

        if not self._audio_since_commit:
            return
        await self._send_gateway_event({"type": "input_audio_buffer.commit"})
        self._audio_since_commit = False

    async def _handle_vad_user_stopped_speaking(self, frame: VADUserStoppedSpeakingFrame) -> None:
        await super()._handle_vad_user_stopped_speaking(frame)
        await self.commit_audio()

    async def _connect(self) -> None:
        await super()._connect()
        await self._connect_websocket()
        if self._websocket is not None and self._receive_task is None:
            receive_coroutine = self._receive_task_handler(self._report_error)
            try:
                self._receive_task = self.create_task(
                    receive_coroutine,
                    name="doubao_streaming_stt_receive",
                )
            except Exception as exc:
                if "TaskManager is not initialized" not in str(exc):
                    receive_coroutine.close()
                    raise
                self._receive_task = asyncio.create_task(receive_coroutine)

    async def _disconnect(self) -> None:
        await super()._disconnect()
        current_task = asyncio.current_task()
        if self._receive_task is not None and self._receive_task is not current_task:
            try:
                await self.cancel_task(self._receive_task)
            except Exception as exc:
                if "TaskManager is not initialized" not in str(exc):
                    raise
                self._receive_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._receive_task
        self._receive_task = None
        await self._disconnect_websocket()

    async def _connect_websocket(self) -> None:
        if _websocket_is_open(self._websocket):
            return
        self._session_ready.clear()
        self._request_id = self._request_id_factory()
        try:
            headers = authorization_headers(self._api_key)
        except Exception as exc:
            raise DoubaoStreamingSTTGatewayError(
                "NewAPI user authentication is unavailable for streaming STT",
                code="DOUBAO_STREAMING_STT_GATEWAY_AUTH_MISSING",
                phase="gateway_authentication",
                category="authentication",
                retryable=True,
                fatal=True,
            ) from exc
        if not headers:
            raise DoubaoStreamingSTTGatewayError(
                "NewAPI user authentication is required for streaming STT",
                code="DOUBAO_STREAMING_STT_GATEWAY_AUTH_MISSING",
                phase="gateway_authentication",
                category="authentication",
                retryable=True,
                fatal=True,
            )
        headers = {**headers, "X-Request-Id": self._request_id}
        try:
            context = self._websocket_connector(
                self._gateway_ws_url,
                headers=headers,
                timeout=self._timeout,
            )
            self._websocket_context = context
            self._websocket = await _enter_websocket(context)
            await self._send_gateway_event(
                build_doubao_streaming_stt_session_event(
                    model=self._model,
                    language=self._language,
                    sample_rate=self.sample_rate,
                )
            )
            await self._call_event_handler("on_connected")
        except DoubaoStreamingSTTGatewayError:
            await self._disconnect_websocket()
            raise
        except Exception as exc:
            await self._disconnect_websocket()
            raise DoubaoStreamingSTTGatewayError(
                "Unable to connect to the NewAPI streaming STT gateway",
                code="DOUBAO_STREAMING_STT_GATEWAY_CONNECT_FAILED",
                phase="gateway_connect",
                category="network",
                retryable=True,
                fatal=False,
            ) from exc

    async def _disconnect_websocket(self) -> None:
        websocket = self._websocket
        context = self._websocket_context
        self._websocket = None
        self._websocket_context = None
        self._session_ready.clear()
        self._audio_since_commit = False
        self._interim_text = ""
        if websocket is not None:
            close = getattr(websocket, "close", None)
            if callable(close):
                with suppress(Exception):
                    result = close()
                    if inspect.isawaitable(result):
                        await result
        if context is not None and context is not websocket and hasattr(context, "__aexit__"):
            with suppress(Exception):
                await context.__aexit__(None, None, None)
        await self._call_event_handler("on_disconnected")

    async def _receive_messages(self) -> None:
        websocket = self._websocket
        if websocket is None:
            raise DoubaoStreamingSTTGatewayError(
                "NewAPI streaming STT WebSocket is not connected",
                code="DOUBAO_STREAMING_STT_GATEWAY_NOT_CONNECTED",
                phase="gateway_receive",
                category="network",
                retryable=True,
                fatal=False,
            )
        async for raw_message in _iter_websocket_messages(websocket):
            event = _decode_gateway_event(raw_message)
            await self._handle_gateway_event(event)

    async def _handle_gateway_event(self, event: Mapping[str, Any]) -> None:
        event_type = _event_type(event)
        if event_type in _SESSION_READY_EVENTS:
            self._session_ready.set()
            return
        if event_type in _TRANSCRIPT_DELTA_EVENTS:
            delta = _event_text(event, "delta", "transcript", "text")
            if not delta:
                return
            if event_type.endswith(".delta"):
                self._interim_text += delta
            else:
                self._interim_text = delta
            await self.push_frame(
                InterimTranscriptionFrame(
                    text=self._interim_text,
                    user_id=self._user_id,
                    timestamp=time_now_iso8601(),
                    language=self._language_for_frame(),
                    result=dict(event),
                )
            )
            return
        if event_type in _TRANSCRIPT_FINAL_EVENTS:
            text = _event_text(event, "transcript", "text") or self._interim_text
            self._interim_text = ""
            if not text:
                return
            await self.push_frame(
                TranscriptionFrame(
                    text=text,
                    user_id=self._user_id,
                    timestamp=time_now_iso8601(),
                    language=self._language_for_frame(),
                    result=dict(event),
                    finalized=True,
                )
            )
            return
        if event_type == "error" or event_type.endswith(".error"):
            error = _gateway_error(event)
            await self.push_error(str(error), exception=error, fatal=error.fatal)

    async def _send_gateway_event(self, event: Mapping[str, Any]) -> None:
        websocket = self._websocket
        if not _websocket_is_open(websocket):
            raise DoubaoStreamingSTTGatewayError(
                "NewAPI streaming STT WebSocket is not connected",
                code="DOUBAO_STREAMING_STT_GATEWAY_NOT_CONNECTED",
                phase="gateway_send",
                category="network",
                retryable=True,
                fatal=False,
            )
        try:
            await websocket.send(json.dumps(dict(event), ensure_ascii=False))
        except Exception as exc:
            raise DoubaoStreamingSTTGatewayError(
                "Failed to send audio to the NewAPI streaming STT gateway",
                code="DOUBAO_STREAMING_STT_GATEWAY_SEND_FAILED",
                phase="gateway_send",
                category="network",
                retryable=True,
                fatal=False,
            ) from exc

    def _language_for_frame(self) -> Language | None:
        try:
            return Language(self._language)
        except ValueError:
            return None


def create_volcengine_doubao_streaming_stt_service(
    **kwargs: Any,
) -> VolcengineDoubaoStreamingSTTService:
    """Create the NewAPI-backed streaming STT service.

    This factory never selects a raw-provider or batch fallback. A caller may
    pass ``fallback_factory`` as policy metadata and compose failover outside
    the service after a structured capability or connection failure.
    """

    return VolcengineDoubaoStreamingSTTService(**kwargs)


def _connect_newapi_streaming_websocket(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - optional runtime dependency
        raise DoubaoStreamingSTTGatewayError(
            "Doubao streaming STT requires the websockets package",
            code="DOUBAO_STREAMING_STT_DEPENDENCY_MISSING",
            phase="runtime_import",
            category="dependency",
            retryable=False,
            fatal=True,
        ) from exc
    connect_kwargs: dict[str, Any] = {"open_timeout": timeout, "close_timeout": 5}
    with suppress(TypeError, ValueError):
        parameters = inspect.signature(websockets.connect).parameters
        header_name = "additional_headers" if "additional_headers" in parameters else "extra_headers"
        connect_kwargs[header_name] = dict(headers)
    if not any(key in connect_kwargs for key in ("additional_headers", "extra_headers")):
        connect_kwargs["additional_headers"] = dict(headers)
    return websockets.connect(url, **connect_kwargs)


async def _enter_websocket(context_or_websocket: Any) -> Any:
    value = context_or_websocket
    if inspect.isawaitable(value):
        value = await value
    if hasattr(value, "__aenter__"):
        return await value.__aenter__()
    return value


async def _iter_websocket_messages(websocket: Any):
    if hasattr(websocket, "__aiter__"):
        async for message in websocket:
            yield message
        return
    receive = getattr(websocket, "recv", None)
    if not callable(receive):
        raise TypeError("WebSocket object does not provide async iteration or recv()")
    while True:
        message = receive()
        if inspect.isawaitable(message):
            message = await message
        if message is None:
            return
        yield message


def _decode_gateway_event(raw_message: Any) -> Mapping[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    if isinstance(raw_message, str):
        value = json.loads(raw_message)
    else:
        value = raw_message
    if not isinstance(value, Mapping):
        raise ValueError("NewAPI streaming STT event must be a JSON object")
    return value


def _event_type(event: Mapping[str, Any]) -> str:
    value = event.get("type") or event.get("event") or event.get("event_type")
    return str(value or "").strip().lower().replace("_", ".")


def _event_text(event: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = event.get(key)
        if isinstance(value, str) and value:
            return value
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        return _event_text(payload, *keys)
    return ""


def _gateway_error(event: Mapping[str, Any]) -> DoubaoStreamingSTTGatewayError:
    details = event.get("error")
    if not isinstance(details, Mapping):
        details = event
    code = str(details.get("code") or "DOUBAO_STREAMING_STT_GATEWAY_ERROR")
    message = str(details.get("message") or "NewAPI streaming STT gateway failed")
    retryable = bool(details.get("retryable"))
    fatal = bool(details.get("fatal", not retryable))
    return DoubaoStreamingSTTGatewayError(
        message,
        code=code,
        phase="gateway_receive",
        category=str(details.get("errorCategory") or "provider_error"),
        retryable=retryable,
        fatal=fatal,
    )


def _websocket_is_open(websocket: Any | None) -> bool:
    if websocket is None:
        return False
    if bool(getattr(websocket, "closed", False)):
        return False
    state = getattr(websocket, "state", None)
    state_name = str(getattr(state, "name", state) or "").upper()
    return state_name != "CLOSED"


__all__ = [
    "DEFAULT_DOUBAO_STREAMING_STT_MODEL",
    "DEFAULT_DOUBAO_STREAMING_STT_SAMPLE_RATE",
    "DoubaoStreamingSTTGatewayError",
    "VOLCENGINE_DOUBAO_STREAMING_PROVIDER",
    "VolcengineDoubaoStreamingSTTService",
    "build_doubao_streaming_stt_audio_event",
    "build_doubao_streaming_stt_session_event",
    "create_volcengine_doubao_streaming_stt_service",
    "normalize_doubao_streaming_stt_url",
]
