"""Pipecat service adapter for Volcengine Doubao speech-to-speech."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Callable

from application.audio_format import is_pcm_audio_mime_type, sniff_audio_mime_type
from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    TrainingVoiceContext,
)
from infrastructure.external.voice.volcengine_realtime import (
    VolcengineDoubaoRealtimeAdapter,
    create_volcengine_doubao_realtime_adapter,
)


def create_volcengine_realtime_service(
    runtime: Any,
    *,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    adapter_factory: Callable[..., VolcengineDoubaoRealtimeAdapter] | None = None,
) -> Any:
    """Wrap the provider transport as a Pipecat frame processor."""

    create_adapter = adapter_factory or create_volcengine_doubao_realtime_adapter

    class VolcengineRealtimeService(runtime.FrameProcessor):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__(name="VolcengineDoubaoRealtimeService")
            self._adapter = create_adapter()
            self._events_task: asyncio.Task[None] | None = None
            self._ready = asyncio.Event()
            self._start_error: BaseException | None = None
            self._started = False
            self._assistant_speaking = False
            self._drop_assistant_tail = False
            self._interruption_active = False

        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)
            if _is_frame(frame, runtime.StartFrame):
                await self._start_provider()
            elif isinstance(frame, runtime.InputAudioRawFrame):
                await self._adapter.append_audio(
                    RealtimeAudioChunk(
                        data=frame.audio,
                        mime_type="audio/pcm",
                        metadata={
                            "sampleRate": frame.sample_rate,
                            "channels": frame.num_channels,
                        },
                    )
                )
            elif _is_frame(frame, runtime.InterruptionFrame):
                self._drop_assistant_tail = True
                await self._adapter.cancel_response("pipecat_interruption")
            elif _is_frame(frame, runtime.EndFrame) or _is_frame(frame, runtime.CancelFrame):
                await self._stop_provider("pipeline_closed")
            await self.push_frame(frame, direction)

        async def cleanup(self) -> None:
            await self._stop_provider("pipeline_cleanup")
            await super().cleanup()

        async def wait_until_ready(self) -> None:
            await self._ready.wait()
            if self._start_error is not None:
                raise self._start_error

        async def commit_audio(self) -> None:
            await self._adapter.commit_audio()

        async def _start_provider(self) -> None:
            if self._started:
                return
            try:
                await self._adapter.start(context, config)
                self._started = True
                self._events_task = asyncio.create_task(
                    self._pump_provider_events(),
                    name="pipecat-volcengine-realtime-events",
                )
            except BaseException as exc:
                self._start_error = exc
                raise
            finally:
                self._ready.set()

        async def _stop_provider(self, reason: str) -> None:
            if not self._started and self._events_task is None:
                return
            self._started = False
            if self._events_task is not None and self._events_task is not asyncio.current_task():
                self._events_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._events_task
            self._events_task = None
            await self._adapter.close(reason)

        async def _pump_provider_events(self) -> None:
            try:
                async for event in self._adapter.events():
                    await self._handle_provider_event(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._forward_provider_error(str(exc), exception=exc, fatal=True)

        async def _handle_provider_event(self, event: Mapping[str, Any]) -> None:
            event_type = _event_type(event)
            if event_type in {"session.ready", "session.configured", "audio.input.committed"}:
                return
            if event_type == "user.turn.started":
                if runtime.UserStartedSpeakingFrame is not None:
                    await self.broadcast_frame(runtime.UserStartedSpeakingFrame)
                if self._assistant_speaking:
                    self._drop_assistant_tail = True
                    await self._broadcast_interruption_once()
                return
            if event_type == "user.turn.stopped":
                if runtime.UserStoppedSpeakingFrame is not None:
                    await self.broadcast_frame(runtime.UserStoppedSpeakingFrame)
                return
            if event_type == "interrupted":
                self._drop_assistant_tail = True
                await self._broadcast_interruption_once()
                return
            if event_type == "interruption.ended":
                await self._stop_assistant_speaking()
                return
            if event_type == "transcript.delta":
                text = _event_text(event)
                if text and runtime.InterimTranscriptionFrame is not None:
                    await self.push_frame(
                        runtime.InterimTranscriptionFrame(text, "browser", _timestamp(event))
                    )
                return
            if event_type == "transcript.done":
                text = _event_text(event)
                if text:
                    if self._drop_assistant_tail:
                        await self._stop_assistant_speaking()
                    self._drop_assistant_tail = False
                    await self.push_frame(
                        runtime.TranscriptionFrame(
                            text, "browser", _timestamp(event), finalized=True
                        )
                    )
                return
            if event_type == "assistant.speaking.started":
                await self._start_assistant_speaking()
                return
            if event_type == "assistant.speaking.stopped":
                await self._stop_assistant_speaking()
                return
            if event_type == "audio.output":
                if self._drop_assistant_tail:
                    return
                audio = _event_audio(event)
                if not audio:
                    return
                declared_mime_type = _event_text_value(
                    event,
                    "mimeType",
                    "mime_type",
                    "audioFormat",
                    "audio_format",
                )
                detected_mime_type = sniff_audio_mime_type(audio, declared_mime_type)
                if _is_non_pcm_audio_format(
                    detected_mime_type,
                    declared_mime_type=declared_mime_type,
                ):
                    await self._forward_provider_error(
                        "Volcengine Doubao realtime returned non-PCM audio for a PCM contract",
                        fatal=True,
                    )
                    return
                await self._start_assistant_speaking()
                audio_frame = runtime.TTSAudioRawFrame(
                    audio=audio,
                    sample_rate=_event_int(event, "sampleRate", "sample_rate") or 24000,
                    num_channels=_event_int(event, "channels", "numChannels") or 1,
                    context_id=_event_text_value(
                        event,
                        "contextId",
                        "context_id",
                        "responseId",
                        "response_id",
                        "providerResponseId",
                        "provider_response_id",
                    ),
                )
                _attach_frame_metadata(audio_frame, _response_identity_metadata(event))
                await self.push_frame(audio_frame)
                return
            if event_type == "response.audio_transcript.done":
                if self._drop_assistant_tail:
                    return
                text = _event_text(event)
                if text:
                    assistant_frame = runtime.LLMContextAssistantTurnFrame(text, _timestamp(event))
                    _attach_frame_metadata(
                        assistant_frame,
                        _response_identity_metadata(event),
                    )
                    await self.push_frame(assistant_frame)
                return
            if event_type == "error":
                await self._forward_provider_error(
                    _event_error_message(event),
                    fatal=_event_fatal(event),
                    event=event,
                )

        async def _start_assistant_speaking(self) -> None:
            if self._assistant_speaking:
                return
            self._assistant_speaking = True
            self._interruption_active = False
            if runtime.BotStartedSpeakingFrame is not None:
                await self.push_frame(runtime.BotStartedSpeakingFrame())

        async def _stop_assistant_speaking(self) -> None:
            if not self._assistant_speaking:
                return
            self._assistant_speaking = False
            if runtime.BotStoppedSpeakingFrame is not None:
                await self.push_frame(runtime.BotStoppedSpeakingFrame())

        async def _broadcast_interruption_once(self) -> None:
            if self._interruption_active:
                return
            self._interruption_active = True
            await self.broadcast_interruption()

        async def _forward_provider_error(
            self,
            message: str,
            *,
            exception: Exception | None = None,
            fatal: bool,
            event: Mapping[str, Any] | None = None,
        ) -> None:
            if runtime.ErrorFrame is None:
                await self.push_error(message, exception=exception, fatal=fatal)
                return
            error_frame = runtime.ErrorFrame(
                error=message,
                fatal=fatal,
                processor=self,
                exception=exception,
            )
            if event is not None:
                _attach_frame_metadata(
                    error_frame,
                    {"providerError": _provider_error_frame_metadata(event)},
                )
            await self.push_frame(error_frame)

    return VolcengineRealtimeService()


def _is_frame(frame: Any, frame_type: type | None) -> bool:
    return frame_type is not None and isinstance(frame, frame_type)


def _event_type(event: Mapping[str, Any]) -> str:
    return str(event.get("type") or "").strip().lower()


def _event_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, Mapping) else event


def _event_text_value(event: Mapping[str, Any], *keys: str) -> str | None:
    payload = _event_payload(event)
    metadata = event.get("metadata")
    sources = (event, payload, metadata if isinstance(metadata, Mapping) else {})
    for source in sources:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _response_identity_metadata(event: Mapping[str, Any]) -> dict[str, str]:
    response_id = _event_text_value(
        event,
        "responseId",
        "response_id",
        "providerResponseId",
        "provider_response_id",
        "reply_id",
        "replyId",
        "contextId",
        "context_id",
    )
    provider_response_id = (
        _event_text_value(
            event,
            "providerResponseId",
            "provider_response_id",
            "reply_id",
            "replyId",
        )
        or response_id
    )
    provider_question_id = _event_text_value(
        event,
        "providerQuestionId",
        "provider_question_id",
        "question_id",
        "questionId",
    )
    return {
        key: value
        for key, value in {
            "responseId": response_id,
            "providerResponseId": provider_response_id,
            "providerQuestionId": provider_question_id,
        }.items()
        if value is not None
    }


def _provider_error_frame_metadata(event: Mapping[str, Any]) -> dict[str, Any]:
    payload = _event_payload(event)
    error = payload.get("error")
    sources = (event, payload, error if isinstance(error, Mapping) else {})
    metadata: dict[str, Any] = {}
    for key in (
        "code",
        "sourceCode",
        "errorCategory",
        "retryable",
        "fatal",
        "statusCode",
        "phase",
    ):
        for source in sources:
            value = source.get(key)
            if isinstance(value, str | int | float | bool):
                metadata[key] = value
                break
    return metadata


def _attach_frame_metadata(frame: Any, metadata: Mapping[str, Any]) -> None:
    if not metadata:
        return
    existing = getattr(frame, "metadata", None)
    merged = dict(existing) if isinstance(existing, Mapping) else {}
    merged.update(metadata)
    setattr(frame, "metadata", merged)


def _event_text(event: Mapping[str, Any]) -> str | None:
    return _event_text_value(event, "text", "transcript", "delta")


def _event_int(event: Mapping[str, Any], *keys: str) -> int | None:
    payload = _event_payload(event)
    for source in (event, payload):
        for key in keys:
            value = source.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
    return None


def _event_audio(event: Mapping[str, Any]) -> bytes:
    value = _event_text_value(event, "audio", "delta", "data")
    if not value:
        return b""
    try:
        return base64.b64decode(value, validate=True)
    except ValueError:
        return b""


def _is_non_pcm_audio_format(
    detected_mime_type: str,
    *,
    declared_mime_type: str | None,
) -> bool:
    normalized = (detected_mime_type or "").strip().lower().replace("-", "_")
    if is_pcm_audio_mime_type(detected_mime_type) or normalized in {
        "pcm",
        "pcm16",
        "pcm_s16le",
        "s16le",
    }:
        return False
    return detected_mime_type != "application/octet-stream" or bool(declared_mime_type)


def _timestamp(event: Mapping[str, Any]) -> str:
    return _event_text_value(event, "timestamp") or datetime.now(UTC).isoformat()


def _event_error_message(event: Mapping[str, Any]) -> str:
    payload = _event_payload(event)
    error = payload.get("error")
    if isinstance(error, Mapping):
        value = error.get("message")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _event_text_value(event, "message", "detail") or "Volcengine realtime provider error"


def _event_fatal(event: Mapping[str, Any]) -> bool:
    value = _event_payload(event).get("fatal")
    return value is not False


__all__ = ["create_volcengine_realtime_service"]
