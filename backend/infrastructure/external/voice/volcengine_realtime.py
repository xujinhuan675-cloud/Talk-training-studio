"""Volcengine/Doubao realtime voice runtime adapter.

The repository currently has only turn-based Volcengine STT/TTS code and no
checked-in official Doubao Realtime wire protocol. This module therefore keeps
the provider protocol isolated behind encode/parse helpers while exposing the
same provider-neutral realtime pipeline shape used by Training Studio.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
import logging
import uuid
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlparse, urlunparse

from application.ports.realtime import (
    REALTIME_EVENT_SCHEMA_VERSION,
    REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    RealtimeAudioChunk,
    RealtimeOutputAudio,
    RealtimePipelineConfig,
    TrainingVoiceContext,
    redact_realtime_secret_text,
    sanitize_realtime_public_value,
)

logger = logging.getLogger(__name__)

VOLCENGINE_DOUBAO_REALTIME_PROVIDER = "volcengine.doubao_realtime"
DEFAULT_VOLCENGINE_REALTIME_URL = (
    "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
)
DEFAULT_VOLCENGINE_REALTIME_MODEL = "1.2.6.0"
DEFAULT_VOLCENGINE_REALTIME_VOICE = "zh_female_vv_uranus_bigtts"
DEFAULT_INPUT_AUDIO_FORMAT = "pcm16"
DEFAULT_OUTPUT_AUDIO_FORMAT = "pcm16"
DEFAULT_INPUT_SAMPLE_RATE = 16000
DEFAULT_OUTPUT_SAMPLE_RATE = 24000
_VOLCENGINE_EVENT_SESSION_CREATE = "session.create"
_VOLCENGINE_EVENT_SESSION_UPDATE = "session.update"
_VOLCENGINE_EVENT_AUDIO_APPEND = "input_audio_buffer.append"
_VOLCENGINE_EVENT_AUDIO_COMMIT = "input_audio_buffer.commit"
_VOLCENGINE_EVENT_RESPONSE_CANCEL = "response.cancel"
_VOLCENGINE_EVENT_SESSION_CLOSE = "session.close"
_VOLCENGINE_REALTIME_PLACEHOLDER_VOICES = {
    "marin",
    "your-voice",
    "your-doubao-voice",
    "your-volcengine-voice",
    "your-volcengine-realtime-voice",
}
_CLOSED = object()


class VolcengineRealtimeError(RuntimeError):
    """Public-safe structured error raised by the Volcengine realtime adapter."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        provider: str = VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
        error_category: str = "provider_error",
        retryable: bool = False,
        fatal: bool = True,
        source_code: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(redact_realtime_secret_text(message))
        self.code = code
        self.phase = phase
        self.provider = provider
        self.runtime = REALTIME_RUNTIME_VOLCENGINE_DOUBAO
        self.error_category = error_category
        self.retryable = retryable
        self.fatal = fatal
        self.source_code = source_code
        safe_metadata = sanitize_realtime_public_value(dict(metadata or {}))
        self.metadata = dict(safe_metadata) if isinstance(safe_metadata, Mapping) else {}

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": self.provider,
            "runtime": self.runtime,
            "realtimeRuntime": self.runtime,
            "errorCategory": self.error_category,
            "retryable": self.retryable,
            "fatal": self.fatal,
        }
        if self.source_code is not None:
            payload["sourceCode"] = self.source_code
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


class VolcengineDoubaoRealtimeAdapter:
    """Provider-neutral realtime pipeline adapter for Doubao Realtime."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        timeout: float = 30.0,
        websocket_connector: Callable[..., Any] | None = None,
        request_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._api_key = _clean_text(api_key)
        self._base_url = normalize_volcengine_realtime_url(base_url)
        self._model = _clean_text(model)
        self._voice = _clean_volcengine_realtime_voice(voice)
        self._timeout = timeout
        self._websocket_connector = websocket_connector or _connect_volcengine_realtime_websocket
        self._request_id_factory = request_id_factory or (lambda: str(uuid.uuid4()))
        self._events: asyncio.Queue[Mapping[str, Any] | object] = asyncio.Queue()
        self._context: TrainingVoiceContext | None = None
        self._config: RealtimePipelineConfig | None = None
        self._request_id: str | None = None
        self._websocket: Any | None = None
        self._websocket_context: Any | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._audio_sequence = 0
        self._closed = True

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        if self._websocket is not None and not self._closed:
            raise VolcengineRealtimeError(
                "Volcengine Doubao realtime session is already started",
                code="VOLCENGINE_REALTIME_ALREADY_STARTED",
                phase="session_start",
                provider=config.provider,
            )

        self._context = context
        self._config = _volcengine_config(config)
        self._request_id = self._request_id_factory()
        self._audio_sequence = 0
        self._closed = False

        api_key = _config_api_key(self._config, fallback=self._api_key)
        if not api_key:
            raise VolcengineRealtimeError(
                "Volcengine Doubao realtime API key is required",
                code="MISSING_VOLCENGINE_REALTIME_API_KEY",
                phase="configuration",
                provider=self._config.provider,
                error_category="authentication",
                metadata={"missingEnv": ("REALTIME_API_KEY",)},
            )

        url = normalize_volcengine_realtime_url(
            _metadata_text(self._config.metadata, "baseUrl", "base_url")
            or self._base_url
        )
        model = _config_model(self._config, fallback=self._model)
        voice = _config_voice(self._config, fallback=self._voice) or DEFAULT_VOLCENGINE_REALTIME_VOICE
        headers = build_volcengine_realtime_headers(
            api_key=api_key,
            request_id=self._request_id,
            resource_id=_config_resource_id(self._config),
        )

        try:
            self._websocket_context = self._websocket_connector(
                url,
                headers=headers,
                timeout=self._timeout,
            )
            self._websocket = await _enter_websocket(self._websocket_context)
            await self._send_provider_event(
                _VOLCENGINE_EVENT_SESSION_CREATE,
                build_volcengine_realtime_session_payload(
                    context,
                    self._config,
                    request_id=self._request_id,
                    model=model,
                    voice=voice,
                ),
            )
            await self._queue_event(
                _base_event(
                    "session.ready",
                    self._config,
                    payload={
                        "requestId": self._request_id,
                        "providerSessionId": self._request_id,
                        "transport": "websocket",
                    },
                    context=context,
                )
            )
            await self._queue_event(
                _base_event(
                    "session.configured",
                    self._config,
                    payload={
                        "requestId": self._request_id,
                        "providerSessionId": self._request_id,
                        "model": model,
                        "voice": voice,
                    },
                    context=context,
                )
            )
            self._receive_task = asyncio.create_task(
                self._receive_loop(),
                name=f"volcengine-doubao-realtime-{self._request_id}",
            )
        except VolcengineRealtimeError:
            await self._cleanup_after_start_failure()
            raise
        except Exception as exc:
            await self._cleanup_after_start_failure()
            error = _connection_error(exc, provider=self._config.provider)
            logger.warning(
                "volcengine_realtime_start_failed",
                extra={"realtime_error": error.to_realtime_error()},
                exc_info=True,
            )
            raise error from exc

    async def configure(self, payload: Mapping[str, Any] | None = None) -> None:
        self._require_open()
        assert self._config is not None
        assert self._context is not None
        configure_payload = dict(payload or {})
        if self._request_id is not None:
            configure_payload.setdefault("requestId", self._request_id)
        merged_payload = build_volcengine_realtime_configure_payload(
            self._context,
            self._config,
            configure_payload,
        )
        await self._send_provider_event(_VOLCENGINE_EVENT_SESSION_UPDATE, merged_payload)

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self._require_open()
        self._audio_sequence = (
            int(chunk.sequence) if isinstance(chunk.sequence, int) else self._audio_sequence + 1
        )
        payload = build_volcengine_realtime_audio_input_payload(
            chunk,
            sequence=self._audio_sequence,
            config=self._require_config(),
        )
        await self._send_provider_event(_VOLCENGINE_EVENT_AUDIO_APPEND, payload)

    async def commit_audio(self) -> None:
        self._require_open()
        await self._send_provider_event(_VOLCENGINE_EVENT_AUDIO_COMMIT, {})

    async def cancel_response(self, reason: str | None = None) -> None:
        self._require_open()
        await self._send_provider_event(_VOLCENGINE_EVENT_RESPONSE_CANCEL, {})

    async def handle_client_event(self, payload: Mapping[str, Any]) -> None:
        event_type = _event_type(payload)
        if event_type in {"session.configure", "session.update"}:
            await self.configure(payload)
            return
        if event_type in {"audio.input", "input.audio.buffer.append"}:
            audio = _decode_audio_payload(payload)
            await self.append_audio(
                RealtimeAudioChunk(
                    data=audio,
                    mime_type=_metadata_text(payload, "mimeType", "mime_type"),
                    sequence=_metadata_int(payload, "sequence"),
                    metadata={
                        key: value
                        for key, value in payload.items()
                        if key
                        not in {
                            "type",
                            "audio",
                            "audioData",
                            "data",
                            "chunk",
                            "base64",
                        }
                    },
                )
            )
            return
        if event_type in {"audio.commit", "input.audio.buffer.commit"}:
            await self.commit_audio()
            return
        if event_type == "response.cancel":
            await self.cancel_response(_metadata_text(payload, "reason"))
            return
        if event_type == "session.close":
            await self.close(reason=_metadata_text(payload, "reason"))
            return
        raise VolcengineRealtimeError(
            f"Unsupported Volcengine realtime client event: {event_type or '<empty>'}",
            code="UNSUPPORTED_VOLCENGINE_REALTIME_EVENT",
            phase="client_event",
            provider=self._require_config().provider,
            error_category="bad_request",
            metadata={"eventType": event_type},
        )

    async def events(self) -> AsyncIterator[Mapping[str, Any]]:
        while True:
            event = await self._events.get()
            if event is _CLOSED:
                break
            if isinstance(event, Mapping):
                yield event

    async def close(self, reason: str | None = None) -> None:
        if self._websocket is None and self._closed:
            return
        config = self._config
        context = self._context
        if not self._closed and self._websocket is not None:
            with suppress(Exception):
                await self._send_provider_event(
                    _VOLCENGINE_EVENT_SESSION_CLOSE,
                    {},
                )
        self._closed = True
        if self._receive_task is not None and not self._receive_task.done():
            self._receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._receive_task
        if self._websocket is not None:
            close = getattr(self._websocket, "close", None)
            if callable(close):
                with suppress(Exception):
                    maybe_awaitable = close()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
        if self._websocket_context is not None and hasattr(self._websocket_context, "__aexit__"):
            with suppress(Exception):
                await self._websocket_context.__aexit__(None, None, None)
        self._websocket = None
        self._websocket_context = None
        self._receive_task = None
        if config is not None:
            await self._queue_event(
                _base_event(
                    "session.closed",
                    config,
                    payload={"reason": reason or "client_closed"},
                    context=context,
                )
            )
        await self._events.put(_CLOSED)

    async def _send_provider_event(self, event_type: str, payload: Mapping[str, Any]) -> None:
        self._require_open()
        assert self._websocket is not None
        frame = encode_volcengine_realtime_event(event_type, payload, event_id=str(uuid.uuid4()))
        await self._websocket.send(frame)

    async def _receive_loop(self) -> None:
        assert self._websocket is not None
        config = self._require_config()
        context = self._context
        try:
            while not self._closed:
                raw = await self._websocket.recv()
                for provider_event in iter_volcengine_realtime_events(raw):
                    for event in map_volcengine_realtime_event(
                        provider_event,
                        config=config,
                        context=context,
                    ):
                        await self._queue_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._closed:
                return
            error = _provider_exception_event(exc, config=config, context=context)
            await self._queue_event(error)
            await self._queue_event(
                _base_event(
                    "session.closed",
                    config,
                    payload={"reason": "provider_disconnected"},
                    context=context,
                )
            )
            await self._events.put(_CLOSED)

    async def _queue_event(self, event: Mapping[str, Any]) -> None:
        safe_event = sanitize_realtime_public_value(dict(event))
        if isinstance(safe_event, Mapping):
            await self._events.put(dict(safe_event))

    async def _cleanup_after_start_failure(self) -> None:
        self._closed = True
        if self._websocket is not None:
            close = getattr(self._websocket, "close", None)
            if callable(close):
                with suppress(Exception):
                    maybe_awaitable = close()
                    if inspect.isawaitable(maybe_awaitable):
                        await maybe_awaitable
        if self._websocket_context is not None and hasattr(self._websocket_context, "__aexit__"):
            with suppress(Exception):
                await self._websocket_context.__aexit__(None, None, None)
        self._websocket = None
        self._websocket_context = None

    def _require_open(self) -> None:
        if self._closed or self._websocket is None:
            provider = self._config.provider if self._config is not None else (
                VOLCENGINE_DOUBAO_REALTIME_PROVIDER
            )
            raise VolcengineRealtimeError(
                "Volcengine Doubao realtime session is not open",
                code="VOLCENGINE_REALTIME_NOT_OPEN",
                phase="session_state",
                provider=provider,
            )

    def _require_config(self) -> RealtimePipelineConfig:
        if self._config is None:
            raise VolcengineRealtimeError(
                "Volcengine Doubao realtime session is not configured",
                code="VOLCENGINE_REALTIME_NOT_CONFIGURED",
                phase="session_state",
            )
        return self._config


def normalize_volcengine_realtime_url(base_url: str | None = None) -> str:
    raw_url = (base_url or DEFAULT_VOLCENGINE_REALTIME_URL).strip()
    if not raw_url:
        raw_url = DEFAULT_VOLCENGINE_REALTIME_URL
    if not raw_url.startswith(("ws://", "wss://", "http://", "https://")):
        raw_url = f"wss://{raw_url}"
    parsed = urlparse(raw_url)
    scheme = "wss" if parsed.scheme == "https" else "ws" if parsed.scheme == "http" else parsed.scheme
    path = parsed.path if parsed.path and parsed.path != "/" else "/api/v3/duplex/realtime/dialogue"
    return urlunparse(parsed._replace(scheme=scheme, path=path))


def build_volcengine_realtime_headers(
    *,
    api_key: str,
    request_id: str,
    resource_id: str | None = None,
    model: str | None = None,
) -> dict[str, str]:
    headers = {
        "X-Api-Key": api_key,
        "X-Api-Request-Id": request_id,
    }
    if resource_id:
        headers["X-Api-Resource-Id"] = resource_id
    return headers


def build_volcengine_realtime_session_payload(
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    *,
    request_id: str,
    model: str,
    voice: str | None,
) -> dict[str, Any]:
    resolved_voice = voice or DEFAULT_VOLCENGINE_REALTIME_VOICE
    payload: dict[str, Any] = {
        "session": {
            "model": model,
            "instructions": _volcengine_realtime_instructions(context, config),
            "audio": {
                "input": {
                    "format": {
                        "type": _volcengine_input_audio_format(config.input_audio_format),
                        "sample_rate": DEFAULT_INPUT_SAMPLE_RATE,
                    },
                },
                "output": {
                    "format": {
                        "type": _volcengine_output_audio_format(config.output_audio_format),
                        "sample_rate": DEFAULT_OUTPUT_SAMPLE_RATE,
                    },
                    "voice": resolved_voice,
                },
            },
        }
    }
    safe_payload = sanitize_realtime_public_value(payload)
    return dict(safe_payload) if isinstance(safe_payload, Mapping) else {}


def build_volcengine_realtime_configure_payload(
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_volcengine_realtime_session_payload(
        context,
        config,
        request_id=str(_metadata_text(overrides or {}, "requestId", "request_id") or ""),
        model=_config_model(config),
        voice=_config_voice(config) or DEFAULT_VOLCENGINE_REALTIME_VOICE,
    )
    if overrides:
        safe_overrides = sanitize_realtime_public_value(dict(overrides))
        if isinstance(safe_overrides, Mapping):
            session_overrides = safe_overrides.get("session")
            if isinstance(session_overrides, Mapping):
                payload["session"] = _merge_public_mappings(
                    dict(payload.get("session") or {}),
                    session_overrides,
                )
            instructions = _clean_text(safe_overrides.get("instructions"))
            if instructions and isinstance(payload.get("session"), Mapping):
                payload["session"]["instructions"] = instructions
            model = _clean_text(safe_overrides.get("model"))
            if model and isinstance(payload.get("session"), Mapping):
                payload["session"]["model"] = model
            voice = _clean_volcengine_realtime_voice(safe_overrides.get("voice"))
            if voice and isinstance(payload.get("session"), Mapping):
                audio = payload["session"].setdefault("audio", {})
                if isinstance(audio, dict):
                    output = audio.setdefault("output", {})
                    if isinstance(output, dict):
                        output["voice"] = voice
    return payload


def build_volcengine_realtime_audio_input_payload(
    chunk: RealtimeAudioChunk,
    *,
    sequence: int,
    config: RealtimePipelineConfig,
) -> dict[str, Any]:
    return {"audio": base64.b64encode(chunk.data).decode("ascii")}


def encode_volcengine_realtime_event(
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    *,
    event_id: str | None = None,
) -> str:
    envelope: dict[str, Any] = {
        "type": event_type,
        "event_id": event_id or str(uuid.uuid4()),
    }
    safe_payload = sanitize_realtime_public_value(dict(payload or {}))
    if isinstance(safe_payload, Mapping):
        for key, value in safe_payload.items():
            if key not in {"type", "event_id"}:
                envelope[str(key)] = value
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def parse_volcengine_realtime_frame(raw: bytes | bytearray | str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, bytes | bytearray):
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VolcengineRealtimeError(
                "Volcengine realtime returned a non-JSON binary frame; official binary parser is not wired",
                code="VOLCENGINE_REALTIME_PROTOCOL_UNSUPPORTED",
                phase="provider_receive",
                error_category="bad_request",
            ) from exc
    else:
        text = str(raw)
    text = text.strip()
    if text.startswith("data:"):
        text = text[5:].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VolcengineRealtimeError(
            "Volcengine realtime returned an invalid JSON frame",
            code="VOLCENGINE_REALTIME_PROTOCOL_ERROR",
            phase="provider_receive",
            error_category="bad_request",
            metadata={"rawPrefix": text[:80]},
        ) from exc
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, list):
        return {"type": "batch", "events": value}
    raise VolcengineRealtimeError(
        "Volcengine realtime returned an unsupported frame shape",
        code="VOLCENGINE_REALTIME_PROTOCOL_ERROR",
        phase="provider_receive",
        error_category="bad_request",
    )


def iter_volcengine_realtime_events(
    raw: bytes | bytearray | str | Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    frame = parse_volcengine_realtime_frame(raw)
    if isinstance(frame.get("events"), Sequence) and not isinstance(frame.get("events"), str):
        events = [item for item in frame["events"] if isinstance(item, Mapping)]
        return tuple(dict(item) for item in events)
    payload = frame.get("payload")
    if isinstance(payload, Mapping) and isinstance(payload.get("events"), Sequence):
        events = [item for item in payload["events"] if isinstance(item, Mapping)]
        return tuple(dict(item) for item in events)
    return (frame,)


def map_volcengine_realtime_event(
    provider_event: Mapping[str, Any],
    *,
    config: RealtimePipelineConfig,
    context: TrainingVoiceContext | None = None,
) -> tuple[dict[str, Any], ...]:
    event_type = _normalized_provider_event_type(provider_event)
    if event_type in {"session.ready", "session.started", "connection.ready"}:
        return (_base_event("session.ready", config, payload=provider_event, context=context),)
    if event_type in {"session.configured", "session.updated", "session.configure.done"}:
        return (_base_event("session.configured", config, payload=provider_event, context=context),)
    if event_type in {"session.closed", "connection.closed"}:
        return (_base_event("session.closed", config, payload=provider_event, context=context),)
    if event_type in {"input.audio.buffer.committed", "audio.input.committed"}:
        return (
            _base_event(
                "audio.input.committed",
                config,
                payload=provider_event,
                context=context,
            ),
        )
    if _is_audio_output_provider_event(event_type, provider_event):
        audio = _extract_audio_bytes(provider_event)
        if not audio:
            return ()
        event = RealtimeOutputAudio(
            data=audio,
            provider=config.provider,
            runtime=REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
            mime_type=_metadata_text(provider_event, "mimeType", "mime_type", "audio_format")
            or _audio_mime_type(config.output_audio_format),
            sequence=_metadata_int(provider_event, "sequence", "audioSequence", "audio_sequence"),
            sample_rate=_metadata_int(provider_event, "sampleRate", "sample_rate")
            or _metadata_int(config.metadata, "outputSampleRate")
            or DEFAULT_OUTPUT_SAMPLE_RATE,
            channels=_metadata_int(provider_event, "channels", "numChannels") or 1,
            context_id=_metadata_text(provider_event, "responseId", "response_id", "itemId"),
            metadata=_event_metadata(provider_event, context=context),
        ).to_event()
        event["runtime"] = REALTIME_RUNTIME_VOLCENGINE_DOUBAO
        event["source"] = "volcengine"
        event["payload"]["source"] = "volcengine"
        return (event,)
    if _is_transcript_delta_event(event_type):
        text = _event_text(provider_event)
        if not text:
            return ()
        output_type = (
            "response.audio_transcript.delta"
            if _event_role(provider_event, event_type) == "assistant"
            else "transcript.delta"
        )
        return (
            _transcript_event(
                output_type,
                text,
                config,
                provider_event=provider_event,
                context=context,
                final=False,
            ),
        )
    if _is_transcript_done_event(event_type):
        text = _event_text(provider_event)
        if not text:
            return ()
        output_type = (
            "response.audio_transcript.done"
            if _event_role(provider_event, event_type) == "assistant"
            else "transcript.done"
        )
        return (
            _transcript_event(
                output_type,
                text,
                config,
                provider_event=provider_event,
                context=context,
                final=True,
            ),
        )
    if _is_turn_started_provider_event(event_type):
        return (
            _turn_event(
                _turn_contract_event_type(provider_event, "started"),
                "started",
                config,
                provider_event=provider_event,
                context=context,
            ),
        )
    if _is_turn_ended_provider_event(event_type):
        return (
            _turn_event(
                _turn_contract_event_type(provider_event, "stopped"),
                "stopped",
                config,
                provider_event=provider_event,
                context=context,
            ),
        )
    if _is_interruption_started_provider_event(event_type):
        return (
            _interruption_event(
                "interrupted",
                "started",
                config,
                provider_event=provider_event,
                context=context,
            ),
        )
    if _is_interruption_ended_provider_event(event_type):
        return (
            _interruption_event(
                "interrupted",
                "ended",
                config,
                provider_event=provider_event,
                context=context,
            ),
        )
    if _is_error_provider_event(event_type, provider_event):
        return (_provider_error_event(provider_event, config=config, context=context),)
    return ()


def classify_volcengine_realtime_error(payload: Mapping[str, Any] | BaseException) -> dict[str, Any]:
    if isinstance(payload, BaseException):
        message = str(payload)
        source_code = payload.__class__.__name__
        status_code = 0
    else:
        message = _provider_error_message(payload)
        source_code = _provider_error_code(payload)
        status_code = _provider_error_status_code(payload)
    haystack = f"{source_code} {message}".lower()
    if status_code in {401, 403} or any(
        token in haystack
        for token in ("api key", "api_key", "auth", "forbidden", "unauthorized")
    ):
        return _error_taxonomy("authentication", source_code=source_code, status_code=status_code)
    if status_code == 429 or any(token in haystack for token in ("quota", "rate limit", "rate_limit")):
        return _error_taxonomy("rate_limit", source_code=source_code, status_code=status_code)
    if status_code >= 500 or any(
        token in haystack
        for token in ("connection", "connect", "disconnect", "overload", "timeout", "unavailable")
    ):
        return _error_taxonomy(
            "provider_unavailable",
            source_code=source_code,
            status_code=status_code,
        )
    if 400 <= status_code < 500 or any(
        token in haystack for token in ("bad request", "bad_request", "invalid", "unsupported")
    ):
        return _error_taxonomy("bad_request", source_code=source_code, status_code=status_code)
    return _error_taxonomy("provider_error", source_code=source_code, status_code=status_code)


def create_volcengine_doubao_realtime_adapter(**kwargs: Any) -> VolcengineDoubaoRealtimeAdapter:
    return VolcengineDoubaoRealtimeAdapter(**kwargs)


def _connect_volcengine_realtime_websocket(
    url: str,
    *,
    headers: Mapping[str, str],
    timeout: float,
) -> Any:
    try:
        import websockets
    except ImportError as exc:  # pragma: no cover - depends on optional runtime env
        raise VolcengineRealtimeError(
            "Volcengine Doubao realtime requires the 'websockets' package",
            code="VOLCENGINE_REALTIME_DEPENDENCY_MISSING",
            phase="runtime_import",
            metadata={"modules": ("websockets",)},
        ) from exc

    connect_kwargs: dict[str, Any] = {"open_timeout": timeout, "close_timeout": 5}
    try:
        parameters = inspect.signature(websockets.connect).parameters
    except (TypeError, ValueError):  # pragma: no cover
        parameters = {}
    header_kwarg = "additional_headers" if "additional_headers" in parameters else "extra_headers"
    connect_kwargs[header_kwarg] = dict(headers)
    return websockets.connect(url, **connect_kwargs)


async def _enter_websocket(context_or_websocket: Any) -> Any:
    if inspect.isawaitable(context_or_websocket):
        context_or_websocket = await context_or_websocket
    if hasattr(context_or_websocket, "__aenter__"):
        return await context_or_websocket.__aenter__()
    return context_or_websocket


def _volcengine_config(config: RealtimePipelineConfig) -> RealtimePipelineConfig:
    runtime = config.runtime or REALTIME_RUNTIME_VOLCENGINE_DOUBAO
    provider = config.provider or VOLCENGINE_DOUBAO_REALTIME_PROVIDER
    return RealtimePipelineConfig(
        provider=provider,
        runtime=runtime,
        model=config.model,
        voice=config.voice,
        input_audio_format=config.input_audio_format or DEFAULT_INPUT_AUDIO_FORMAT,
        output_audio_format=config.output_audio_format or DEFAULT_OUTPUT_AUDIO_FORMAT,
        instructions=config.instructions,
        metadata=dict(config.metadata),
    )


def _config_api_key(config: RealtimePipelineConfig, *, fallback: str | None = None) -> str | None:
    return _metadata_text(
        config.metadata,
        "apiKey",
        "api_key",
        "realtimeApiKey",
        "realtime_api_key",
    ) or fallback


def _config_model(
    config: RealtimePipelineConfig,
    *,
    fallback: str | None = None,
) -> str:
    return (
        _clean_text(config.model)
        or _metadata_text(config.metadata, "model")
        or fallback
        or DEFAULT_VOLCENGINE_REALTIME_MODEL
    )


def _config_resource_id(config: RealtimePipelineConfig) -> str | None:
    return _metadata_text(
        config.metadata,
        "apiResourceId",
        "api_resource_id",
        "resourceId",
        "resource_id",
    )


def _config_voice(
    config: RealtimePipelineConfig,
    *,
    fallback: str | None = None,
) -> str | None:
    return (
        _clean_volcengine_realtime_voice(config.voice)
        or _clean_volcengine_realtime_voice(_metadata_text(config.metadata, "voice", "voiceId"))
        or _clean_volcengine_realtime_voice(fallback)
    )


def _volcengine_realtime_instructions(
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
) -> str:
    parts: list[str] = []
    instructions = _clean_text(config.instructions)
    if instructions:
        parts.append(instructions)
    task_goal = _clean_text(context.task_goal)
    if task_goal:
        parts.append(f"Training goal: {task_goal}")
    rubric = _public_json(context.rubric)
    if rubric:
        parts.append(f"Rubric: {rubric}")
    recent_turns = _public_json([dict(turn) for turn in context.recent_turns])
    if recent_turns:
        parts.append(f"Recent turns: {recent_turns}")
    scenario = _metadata_text(context.metadata, "scenario", "scenarioName", "scenario_name")
    if scenario:
        parts.append(f"Scenario: {scenario}")
    return "\n\n".join(parts) or "You are a realtime role-play training agent."


def _public_json(value: object) -> str | None:
    safe = sanitize_realtime_public_value(value)
    if safe is None:
        return None
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))


def _volcengine_input_audio_format(value: str | None) -> str:
    normalized = _normalized_audio_format(value)
    if "opus" in normalized:
        return "speech_opus"
    return "pcm"


def _volcengine_output_audio_format(value: str | None) -> str:
    normalized = _normalized_audio_format(value)
    if "opus" in normalized or "ogg" in normalized:
        return "ogg_opus"
    return "pcm_s16le"


def _normalized_audio_format(value: str | None) -> str:
    return (value or "").strip().lower().replace("-", "_").replace("/", "_")


def _merge_public_mappings(
    base: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(base)
    for key, value in updates.items():
        existing = merged.get(str(key))
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[str(key)] = _merge_public_mappings(existing, value)
        else:
            merged[str(key)] = value
    return merged


def _base_event(
    event_type: str,
    config: RealtimePipelineConfig,
    *,
    payload: Mapping[str, Any] | None = None,
    context: TrainingVoiceContext | None = None,
) -> dict[str, Any]:
    event_payload = dict(sanitize_realtime_public_value(dict(payload or {})) or {})
    event_payload.setdefault("schemaVersion", REALTIME_EVENT_SCHEMA_VERSION)
    event_payload.setdefault("runtime", REALTIME_RUNTIME_VOLCENGINE_DOUBAO)
    event_payload.setdefault("provider", config.provider)
    event_payload.setdefault("source", "volcengine")
    if context is not None:
        event_payload.setdefault("trainingSessionId", context.binding.training_session_id)
        event_payload.setdefault("roomId", context.binding.room_id)
    return {
        "type": event_type,
        "schemaVersion": REALTIME_EVENT_SCHEMA_VERSION,
        "runtime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
        "provider": config.provider,
        "source": "volcengine",
        "payload": event_payload,
    }


def _transcript_event(
    event_type: str,
    text: str,
    config: RealtimePipelineConfig,
    *,
    provider_event: Mapping[str, Any],
    context: TrainingVoiceContext | None,
    final: bool,
) -> dict[str, Any]:
    event = _base_event(
        event_type,
        config,
        payload={
            **dict(provider_event),
            "text": text,
            "transcript": text,
            "isFinal": final,
            "role": _event_role(provider_event, event_type),
        },
        context=context,
    )
    event.update(
        {
            "text": text,
            "transcript": text,
            "delta": None if final else text,
            "isFinal": final,
            "role": _event_role(provider_event, event_type),
        }
    )
    for output_key, input_keys in {
        "event_id": ("event_id", "eventId"),
        "item_id": ("item_id", "itemId", "item"),
        "response_id": ("response_id", "responseId", "response"),
        "language": ("language", "lang"),
        "confidence": ("confidence",),
        "sender_id": ("sender_id", "senderId", "user_id", "userId"),
    }.items():
        value = _metadata_value(provider_event, *input_keys)
        safe_value = sanitize_realtime_public_value(value)
        if safe_value is not None:
            event[output_key] = safe_value
    metadata = _event_metadata(provider_event, context=context)
    if metadata:
        event["metadata"] = metadata
    return event


def _turn_event(
    event_type: str,
    state: str,
    config: RealtimePipelineConfig,
    *,
    provider_event: Mapping[str, Any],
    context: TrainingVoiceContext | None,
) -> dict[str, Any]:
    participant = _metadata_text(provider_event, "participant", "role", "speaker") or "user"
    event = _base_event(
        event_type,
        config,
        payload={
            **dict(provider_event),
            "participant": participant,
            "state": state,
            "signal": "turn",
        },
        context=context,
    )
    event.update({"participant": participant, "state": state, "signal": "turn"})
    metadata = _event_metadata(provider_event, context=context)
    if metadata:
        event["metadata"] = metadata
    return event


def _turn_contract_event_type(provider_event: Mapping[str, Any], state: str) -> str:
    participant = (
        _metadata_text(provider_event, "participant", "role", "speaker") or "user"
    ).lower()
    suffix = "started" if state == "started" else "stopped"
    if participant in {"assistant", "agent", "ai", "bot"}:
        return f"assistant_speaking.{suffix}"
    return f"user_turn.{suffix}"


def _interruption_event(
    event_type: str,
    state: str,
    config: RealtimePipelineConfig,
    *,
    provider_event: Mapping[str, Any],
    context: TrainingVoiceContext | None,
) -> dict[str, Any]:
    event = _base_event(
        event_type,
        config,
        payload={**dict(provider_event), "state": state, "signal": "interruption"},
        context=context,
    )
    event.update({"state": state, "signal": "interruption"})
    metadata = _event_metadata(provider_event, context=context)
    if metadata:
        event["metadata"] = metadata
    return event


def _provider_exception_event(
    exc: BaseException,
    *,
    config: RealtimePipelineConfig,
    context: TrainingVoiceContext | None,
) -> dict[str, Any]:
    if isinstance(exc, VolcengineRealtimeError):
        payload = exc.to_realtime_error()
    else:
        classification = classify_volcengine_realtime_error(exc)
        payload = {
            "message": redact_realtime_secret_text(str(exc)),
            "phase": "provider_receive",
            **classification,
        }
    return _base_event("error", config, payload=payload, context=context)


def _provider_error_event(
    provider_event: Mapping[str, Any],
    *,
    config: RealtimePipelineConfig,
    context: TrainingVoiceContext | None,
) -> dict[str, Any]:
    classification = classify_volcengine_realtime_error(provider_event)
    payload = {
        **dict(provider_event),
        **classification,
        "message": _provider_error_message(provider_event),
        "phase": "provider_event",
    }
    return _base_event("error", config, payload=payload, context=context)


def _connection_error(exc: BaseException, *, provider: str) -> VolcengineRealtimeError:
    classified = classify_volcengine_realtime_error(exc)
    return VolcengineRealtimeError(
        f"Volcengine Doubao realtime connection failed: {exc}",
        code=str(classified["code"]),
        phase="provider_connect",
        provider=provider,
        error_category=str(classified["errorCategory"]),
        retryable=bool(classified["retryable"]),
        fatal=bool(classified["fatal"]),
        source_code=str(classified.get("sourceCode") or exc.__class__.__name__),
        metadata={"exceptionType": exc.__class__.__name__},
    )


def _error_taxonomy(
    category: str,
    *,
    source_code: str | None,
    status_code: int,
) -> dict[str, Any]:
    mapping = {
        "authentication": ("REALTIME_PROVIDER_AUTHENTICATION", False, True),
        "rate_limit": ("REALTIME_PROVIDER_RATE_LIMIT", True, False),
        "provider_unavailable": ("REALTIME_PROVIDER_UNAVAILABLE", True, True),
        "bad_request": ("REALTIME_PROVIDER_BAD_REQUEST", False, True),
        "provider_error": ("REALTIME_PROVIDER_ERROR", False, True),
    }
    code, retryable, fatal = mapping.get(category, mapping["provider_error"])
    payload: dict[str, Any] = {
        "errorCategory": category,
        "code": code,
        "retryable": retryable,
        "fatal": fatal,
    }
    if source_code:
        payload["sourceCode"] = redact_realtime_secret_text(source_code)
    if status_code:
        payload["statusCode"] = status_code
    return payload


def _normalized_provider_event_type(event: Mapping[str, Any]) -> str:
    value = _event_type(event)
    aliases = {
        "session.created": "session.ready",
        "session.started": "session.ready",
        "ready": "session.ready",
        "configured": "session.configured",
        "session.update": "session.configured",
        "session.updated": "session.configured",
        "input.audio.buffer.speech.started": "user.turn.started",
        "input.audio.buffer.speech.stopped": "user.turn.stopped",
        "user.turn.started": "user.turn.started",
        "user.turn.stopped": "user.turn.stopped",
        "user.turn.ended": "user.turn.stopped",
        "assistant.speaking.started": "assistant.speaking.started",
        "assistant.speaking.stopped": "assistant.speaking.stopped",
        "response.interrupted": "interrupted",
        "interrupted": "interrupted",
        "response.cancelled": "interrupted",
        "response.cancel.done": "interruption.ended",
        "input.audio.buffer.committed": "input.audio.buffer.committed",
        "input.audio.transcription.delta": "transcript.delta",
        "input.audio.transcription.completed": "transcript.done",
        "conversation.item.input.audio.transcription.delta": "transcript.delta",
        "conversation.item.input.audio.transcription.completed": "transcript.done",
        "response.audio_transcript.delta": "response.audio_transcript.delta",
        "response.audio_transcript.done": "response.audio_transcript.done",
        "response.output.text.delta": "response.audio_transcript.delta",
        "response.output.text.done": "response.audio_transcript.done",
        "response.output.audio.delta": "audio.output",
        "response.audio.delta": "audio.output",
        "response.audio.done": "audio.output",
    }
    return aliases.get(value, value)


def _event_type(event: Mapping[str, Any]) -> str:
    for key in ("type", "event", "eventType", "event_type", "name"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower().replace("_", ".")
    payload = event.get("payload")
    if isinstance(payload, Mapping):
        return _event_type(payload)
    return ""


def _is_audio_output_provider_event(event_type: str, event: Mapping[str, Any]) -> bool:
    return event_type == "audio.output" or bool(
        "audio" in event_type and "output" in event_type and _extract_audio_bytes(event)
    )


def _is_transcript_delta_event(event_type: str) -> bool:
    return "transcript" in event_type and event_type.endswith(".delta")


def _is_transcript_done_event(event_type: str) -> bool:
    return "transcript" in event_type and event_type.endswith((".done", ".completed", ".final"))


def _is_turn_started_provider_event(event_type: str) -> bool:
    return event_type in {
        "turn.started",
        "turn.start",
        "user.turn.started",
        "assistant.speaking.started",
    } or event_type.endswith(".speech.started")


def _is_turn_ended_provider_event(event_type: str) -> bool:
    return event_type in {
        "turn.ended",
        "turn.end",
        "turn.stopped",
        "user.turn.stopped",
        "user.turn.ended",
        "assistant.speaking.stopped",
        "assistant.speaking.ended",
    } or event_type.endswith(".speech.stopped")


def _is_interruption_started_provider_event(event_type: str) -> bool:
    return event_type in {"interruption.started", "interruption.start"} or (
        "interrupt" in event_type and not event_type.endswith((".ended", ".end", ".done"))
    )


def _is_interruption_ended_provider_event(event_type: str) -> bool:
    return event_type in {"interruption.ended", "interruption.end"} or (
        "interrupt" in event_type and event_type.endswith((".ended", ".end", ".done"))
    )


def _is_error_provider_event(event_type: str, event: Mapping[str, Any]) -> bool:
    return event_type in {"error", "realtime.error", "pipeline.error"} or event_type.endswith(
        ".error"
    ) or isinstance(event.get("error"), Mapping)


def _extract_audio_bytes(event: Mapping[str, Any]) -> bytes:
    value = _metadata_value(event, "audio", "audioData", "data", "chunk", "base64", "delta")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        if all(isinstance(item, int) for item in value):
            with suppress(ValueError):
                return bytes(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return b""
        if text.lower().startswith("data:") and "," in text:
            text = text.split(",", 1)[1].strip()
        try:
            return base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            return b""
    return b""


def _decode_audio_payload(payload: Mapping[str, Any]) -> bytes:
    audio = _extract_audio_bytes(payload)
    if audio:
        return audio
    value = _metadata_value(payload, "audio", "audioData", "data", "chunk", "base64")
    if value in (None, ""):
        return b""
    raise VolcengineRealtimeError(
        "Invalid base64 audio frame for Volcengine realtime",
        code="INVALID_VOLCENGINE_REALTIME_AUDIO",
        phase="audio_input",
        error_category="bad_request",
    )


def _event_text(event: Mapping[str, Any]) -> str | None:
    value = _metadata_value(
        event,
        "text",
        "transcript",
        "delta",
        "content",
        "sentence",
        "utterance",
    )
    if isinstance(value, str) and value.strip():
        return value.strip()
    result = _metadata_value(event, "result")
    if isinstance(result, Mapping):
        return _event_text(result)
    if isinstance(result, Sequence) and not isinstance(result, str):
        for item in result:
            if isinstance(item, Mapping):
                text = _event_text(item)
                if text:
                    return text
    return None


def _event_role(event: Mapping[str, Any], event_type: str) -> str:
    role = _metadata_text(event, "role", "speaker", "participant")
    if role:
        normalized = role.lower()
        if normalized in {"assistant", "bot", "agent", "ai"}:
            return "assistant"
        if normalized in {"system"}:
            return "system"
    if event_type.startswith("response."):
        return "assistant"
    return "user"


def _event_metadata(
    event: Mapping[str, Any],
    *,
    context: TrainingVoiceContext | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "sourceEvent": _event_type(event),
        "runtime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    }
    source_metadata = event.get("metadata")
    if isinstance(source_metadata, Mapping):
        safe_metadata = sanitize_realtime_public_value(dict(source_metadata))
        if isinstance(safe_metadata, Mapping):
            metadata.update(dict(safe_metadata))
    for key in ("request_id", "requestId", "trace_id", "traceId", "event_id", "eventId"):
        value = event.get(key)
        if isinstance(value, str | int | float | bool):
            metadata[key] = value
    if context is not None:
        metadata["talkwise"] = {
            "trainingSessionId": context.binding.training_session_id,
            "roomId": context.binding.room_id,
        }
    safe = sanitize_realtime_public_value(metadata)
    return dict(safe) if isinstance(safe, Mapping) else {}


def _metadata_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    nested = payload.get("payload")
    if isinstance(nested, Mapping):
        for key in keys:
            if key in nested and nested[key] is not None:
                return nested[key]
    nested = payload.get("data")
    if isinstance(nested, Mapping):
        for key in keys:
            if key in nested and nested[key] is not None:
                return nested[key]
    return None


def _metadata_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    value = _metadata_value(payload, *keys)
    return _clean_text(value)


def _metadata_int(payload: Mapping[str, Any], *keys: str) -> int | None:
    value = _metadata_value(payload, *keys)
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_volcengine_realtime_voice(value: object | None) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    normalized = text.lower().replace("_", "-").replace(" ", "-")
    if normalized in _VOLCENGINE_REALTIME_PLACEHOLDER_VOICES:
        return None
    return text


def _audio_mime_type(value: str | None) -> str:
    text = (value or DEFAULT_INPUT_AUDIO_FORMAT).strip().lower()
    if "/" in text:
        return text
    aliases = {
        "pcm": "audio/pcm",
        "pcm16": "audio/pcm",
        "s16le": "audio/pcm",
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "opus": "audio/opus",
        "ogg": "audio/ogg",
    }
    return aliases.get(text, f"audio/{text}")


def _provider_error_message(payload: Mapping[str, Any]) -> str:
    for key in ("message", "detail", "msg"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return redact_realtime_secret_text(value.strip())
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _provider_error_message(error)
    if isinstance(error, str) and error.strip():
        return redact_realtime_secret_text(error.strip())
    return "Volcengine Doubao realtime provider error"


def _provider_error_code(payload: Mapping[str, Any]) -> str | None:
    for key in ("code", "error_code", "errorCode", "type"):
        value = payload.get(key)
        if isinstance(value, str | int) and str(value).strip():
            return str(value).strip()
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _provider_error_code(error)
    return None


def _provider_error_status_code(payload: Mapping[str, Any]) -> int:
    for key in ("status", "statusCode", "status_code", "httpStatus"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _provider_error_status_code(error)
    return 0


__all__ = [
    "DEFAULT_VOLCENGINE_REALTIME_MODEL",
    "DEFAULT_VOLCENGINE_REALTIME_URL",
    "DEFAULT_VOLCENGINE_REALTIME_VOICE",
    "REALTIME_RUNTIME_VOLCENGINE_DOUBAO",
    "VOLCENGINE_DOUBAO_REALTIME_PROVIDER",
    "VolcengineDoubaoRealtimeAdapter",
    "VolcengineRealtimeError",
    "build_volcengine_realtime_audio_input_payload",
    "build_volcengine_realtime_configure_payload",
    "build_volcengine_realtime_headers",
    "build_volcengine_realtime_session_payload",
    "classify_volcengine_realtime_error",
    "create_volcengine_doubao_realtime_adapter",
    "encode_volcengine_realtime_event",
    "iter_volcengine_realtime_events",
    "map_volcengine_realtime_event",
    "normalize_volcengine_realtime_url",
    "parse_volcengine_realtime_frame",
]
