"""Application-layer runner for provider-neutral realtime voice pipelines."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from typing import Any
from uuid import uuid4

from application.ports.realtime import (
    PersistedRealtimeTranscript,
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingTranscriptSink,
    TrainingVoiceContext,
)
from application.services.training_studio.realtime_pipeline import build_realtime_transcript

_EVENT_PUMP_CLOSE_TIMEOUT_SECONDS = 1.0
RealtimePipelineEventSink = Callable[[Mapping[str, Any]], Awaitable[None] | None]
logger = logging.getLogger(__name__)


class RealtimePipelineRunnerStateError(ValueError):
    """Raised when a runner command is called before the pipeline is ready."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "REALTIME_PIPELINE_STATE_ERROR",
        phase: str = "runner_state",
        provider: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.provider = provider
        self.metadata = dict(metadata or {})

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        payload.update(self.metadata)
        return payload


class RealtimePipelineStartError(RuntimeError):
    """Raised when a realtime pipeline adapter fails before it is ready."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "REALTIME_PIPELINE_START_FAILED",
        phase: str = "pipeline_start",
        provider: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase
        self.provider = provider
        self.metadata = dict(metadata or {})

    def to_realtime_error(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": self.provider,
            **self.metadata,
        }


class RealtimePipelineProviderError(RuntimeError):
    """Raised when a provider event reports a realtime pipeline error."""

    def __init__(self, payload: Mapping[str, Any], *, provider: str) -> None:
        self.payload = dict(payload)
        self.provider = provider
        message = _provider_error_message(self.payload)
        super().__init__(message)
        self.code = _provider_error_code(self.payload)
        self.phase = "provider_event"
        self.event_type = str(self.payload.get("type") or "")

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": self.provider,
            "eventType": self.event_type,
        }
        source_code = _provider_error_source_code(self.payload)
        if source_code is not None:
            payload["sourceCode"] = source_code
        metadata = _provider_error_metadata(self.payload)
        if metadata:
            payload["metadata"] = metadata
        return payload


class RealtimePipelineSessionRunner:
    """Bridge realtime pipeline adapter events into Training Studio persistence."""

    def __init__(
        self,
        *,
        adapter: RealtimePipelineAdapter,
        transcript_sink: TrainingTranscriptSink,
        event_sink: RealtimePipelineEventSink | None = None,
    ) -> None:
        self._adapter = adapter
        self._transcript_sink = transcript_sink
        self._event_sink = event_sink
        self._context: TrainingVoiceContext | None = None
        self._config: RealtimePipelineConfig | None = None
        self._realtime_session_id: str | None = None
        self._events_task: asyncio.Task[None] | None = None
        self._events_error: BaseException | None = None
        self._closed = True

    @property
    def context(self) -> TrainingVoiceContext | None:
        return self._context

    @property
    def config(self) -> RealtimePipelineConfig | None:
        return self._config

    @property
    def realtime_session_id(self) -> str | None:
        return self._realtime_session_id

    @property
    def events_error(self) -> BaseException | None:
        return self._events_error

    async def start(
        self,
        *,
        binding: RealtimeSessionBinding,
        provider: str,
        realtime_session_id: str | None = None,
        task_goal: str | None = None,
        rubric: Mapping[str, object] | None = None,
        recent_turns: Sequence[Mapping[str, object]] = (),
        context_metadata: Mapping[str, object] | None = None,
        model: str | None = None,
        voice: str | None = None,
        input_audio_format: str | None = None,
        output_audio_format: str | None = None,
        instructions: str | None = None,
        config_metadata: Mapping[str, object] | None = None,
    ) -> None:
        """Start the adapter and begin pumping provider events in the background."""

        if self._events_task is not None and not self._events_task.done():
            raise RealtimePipelineRunnerStateError("Realtime pipeline runner is already started")

        context = TrainingVoiceContext(
            binding=binding,
            task_goal=task_goal,
            rubric=dict(rubric or {}),
            recent_turns=tuple(dict(turn) for turn in recent_turns),
            metadata=dict(context_metadata or {}),
        )
        config = RealtimePipelineConfig(
            provider=provider,
            model=model,
            voice=voice,
            input_audio_format=input_audio_format,
            output_audio_format=output_audio_format,
            instructions=instructions,
            metadata=dict(config_metadata or {}),
        )

        self._context = context
        self._config = config
        self._realtime_session_id = realtime_session_id or str(uuid4())
        self._events_error = None
        try:
            await self._adapter.start(context, config)
        except Exception as exc:
            with suppress(Exception):
                await self._adapter.close()
            error = _pipeline_start_error(
                exc,
                provider=provider,
                realtime_session_id=self._realtime_session_id,
                binding=binding,
            )
            logger.warning(
                "Realtime pipeline adapter start failed",
                extra={"realtime_error": error.to_realtime_error()},
                exc_info=True,
            )
            raise error from exc
        self._closed = False
        self._events_task = asyncio.create_task(
            self._pump_events(),
            name=f"training-studio-realtime-events-{self._realtime_session_id}",
        )

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self._require_open()
        await self._adapter.append_audio(chunk)

    async def commit(self) -> None:
        self._require_open()
        await self._adapter.commit_audio()

    async def commit_audio(self) -> None:
        await self.commit()

    def raise_if_failed(self) -> None:
        self._raise_events_error()

    async def close(self) -> None:
        if self._closed and self._events_task is None:
            return
        self._closed = True
        try:
            await self._adapter.close()
        finally:
            await self._stop_events_task()

    async def _pump_events(self) -> None:
        context = self._context
        config = self._config
        realtime_session_id = self._realtime_session_id
        if context is None or config is None or realtime_session_id is None:
            raise RealtimePipelineRunnerStateError("Realtime pipeline runner is not started")

        try:
            async for event in self._adapter.events():
                payload = dict(event)
                if _is_provider_error(payload):
                    raise RealtimePipelineProviderError(payload, provider=config.provider)
                persisted = await self._persist_final_transcript(
                    payload,
                    context,
                    config,
                    realtime_session_id,
                )
                if persisted is not None:
                    await self._forward_event(
                        _live_guidance_trigger_event(
                            persisted,
                            context=context,
                            config=config,
                            realtime_session_id=realtime_session_id,
                        )
                    )
                    continue
                if not _is_transcript_event(payload):
                    await self._forward_event(payload)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._events_error = exc
            raise

    async def _persist_final_transcript(
        self,
        payload: dict[str, Any],
        context: TrainingVoiceContext,
        config: RealtimePipelineConfig,
        realtime_session_id: str,
    ) -> PersistedRealtimeTranscript | None:
        transcript = build_realtime_transcript(
            payload,
            binding=context.binding,
            provider=config.provider,
            realtime_session_id=realtime_session_id,
        )
        if transcript is None:
            return None
        return await self._transcript_sink.persist(transcript)

    async def _forward_event(self, payload: Mapping[str, Any]) -> None:
        if self._event_sink is None:
            return
        maybe_awaitable = self._event_sink(dict(payload))
        if maybe_awaitable is not None:
            await maybe_awaitable

    async def _stop_events_task(self) -> None:
        task = self._events_task
        if task is None:
            return
        try:
            if not task.done():
                try:
                    await asyncio.wait_for(
                        asyncio.shield(task), timeout=_EVENT_PUMP_CLOSE_TIMEOUT_SECONDS
                    )
                except TimeoutError:
                    task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                if self._events_error is None:
                    self._events_error = exc
        finally:
            self._events_task = None

    def _require_started(self) -> None:
        if self._context is None or self._config is None or self._realtime_session_id is None:
            raise RealtimePipelineRunnerStateError("Realtime pipeline runner is not started")

    def _require_open(self) -> None:
        self._require_started()
        if self._closed:
            raise RealtimePipelineRunnerStateError("Realtime pipeline runner is closed")
        self._raise_events_error()

    def _raise_events_error(self) -> None:
        if self._events_error is not None:
            structured = _realtime_error_from_exception(self._events_error)
            raise RealtimePipelineRunnerStateError(
                f"Realtime pipeline event pump failed: {structured['message']}",
                code=str(structured["code"]),
                phase=str(structured["phase"]),
                provider=str(structured["provider"]) if structured.get("provider") else None,
                metadata={
                    key: value
                    for key, value in structured.items()
                    if key not in {"code", "message", "phase", "provider"}
                },
            ) from self._events_error


def _is_provider_error(payload: Mapping[str, object]) -> bool:
    event_type = str(payload.get("type") or "").lower()
    return event_type in {"error", "pipeline.error", "realtime.error"}


def _live_guidance_trigger_event(
    persisted: PersistedRealtimeTranscript,
    *,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    realtime_session_id: str,
) -> dict[str, Any]:
    transcript = persisted.transcript
    transcript_payload: dict[str, Any] = {
        "text": transcript.text,
        "role": transcript.role,
        "eventType": transcript.event_type,
    }
    for output_key, value in {
        "eventId": transcript.event_id,
        "itemId": transcript.item_id,
        "responseId": transcript.response_id,
    }.items():
        if value is not None:
            transcript_payload[output_key] = value

    event: dict[str, Any] = {
        "type": "training.live_guidance.triggered",
        "schemaVersion": 1,
        "source": "realtime_voice",
        "reason": "final_transcript",
        "provider": config.provider,
        "trainingSessionId": context.binding.training_session_id,
        "roomId": context.binding.room_id,
        "realtimeSessionId": realtime_session_id,
        "transcript": transcript_payload,
    }
    if persisted.message_id is not None:
        event["messageId"] = persisted.message_id
    return event


def _is_transcript_event(payload: Mapping[str, object]) -> bool:
    event_type = str(payload.get("type") or "").lower()
    return "transcript" in event_type or "transcription" in event_type


def _provider_error_message(payload: Mapping[str, object]) -> str:
    for key in ("message", "detail", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            nested = value.get("message") or value.get("detail")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return "Realtime pipeline provider error"


def _provider_error_code(payload: Mapping[str, object]) -> str:
    for key in ("code", "error_code", "errorCode"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    error = payload.get("error")
    if isinstance(error, Mapping):
        for key in ("code", "type"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "PIPECAT_PROVIDER_ERROR"


def _provider_error_source_code(payload: Mapping[str, object]) -> str | None:
    code = _provider_error_code(payload)
    if code == "PIPECAT_PROVIDER_ERROR":
        return None
    return code


def _provider_error_metadata(payload: Mapping[str, object]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("request_id", "requestId", "trace_id", "traceId"):
        value = payload.get(key)
        if isinstance(value, str | int | float | bool):
            metadata[key] = value
    nested_metadata = payload.get("metadata")
    if isinstance(nested_metadata, Mapping):
        for key, value in nested_metadata.items():
            if isinstance(value, str | int | float | bool) or value is None:
                metadata[str(key)] = value
    return metadata


def _pipeline_start_error(
    exc: BaseException,
    *,
    provider: str,
    realtime_session_id: str | None,
    binding: RealtimeSessionBinding,
) -> RealtimePipelineStartError:
    structured = _realtime_error_from_exception(exc)
    message = str(structured.get("message") or exc)
    code = str(structured.get("code") or "REALTIME_PIPELINE_START_FAILED")
    phase = str(structured.get("phase") or "pipeline_start")
    metadata = {
        key: value
        for key, value in structured.items()
        if key not in {"code", "message", "phase", "provider"}
    }
    metadata.setdefault("trainingSessionId", binding.training_session_id)
    metadata.setdefault("roomId", binding.room_id)
    if realtime_session_id is not None:
        metadata.setdefault("realtimeSessionId", realtime_session_id)

    if code == "REALTIME_PIPELINE_START_FAILED":
        fallback = _classify_start_error_message(message)
        if fallback:
            code = str(fallback.pop("code"))
            phase = str(fallback.pop("phase", phase))
            metadata.update(fallback)

    return RealtimePipelineStartError(
        message,
        code=code,
        phase=phase,
        provider=provider,
        metadata=metadata,
    )


def _realtime_error_from_exception(exc: BaseException) -> dict[str, Any]:
    for method_name in ("to_realtime_error", "to_dict"):
        method = getattr(exc, method_name, None)
        if callable(method):
            with suppress(Exception):
                value = method()
                if isinstance(value, Mapping):
                    return {str(key): item for key, item in value.items()}

    data: dict[str, Any] = {"message": str(exc)}
    for attr_name, output_key in {
        "code": "code",
        "phase": "phase",
        "provider": "provider",
        "feature": "feature",
        "missing_env": "missingEnv",
        "missing_modules": "modules",
        "event_type": "eventType",
        "source_code": "sourceCode",
        "metadata": "metadata",
    }.items():
        if hasattr(exc, attr_name):
            value = getattr(exc, attr_name)
            if value is not None:
                data[output_key] = value
    return data


def _classify_start_error_message(message: str) -> dict[str, Any]:
    text = message.lower()
    if "api key is required" in text or "openai api key" in text:
        return {
            "code": "MISSING_OPENAI_API_KEY",
            "phase": "configuration",
            "missingEnv": ("REALTIME_OPENAI_API_KEY", "LLM__API_KEY", "OPENAI_API_KEY"),
            "feature": _feature_from_error_text(text),
        }
    if "stt" in text and "unavailable" in text:
        return {
            "code": "PIPECAT_FEATURE_UNAVAILABLE",
            "phase": "pipeline_start",
            "feature": "stt:openai",
        }
    if "tts" in text and "unavailable" in text:
        return {
            "code": "PIPECAT_FEATURE_UNAVAILABLE",
            "phase": "pipeline_start",
            "feature": "tts:openai",
        }
    if ("llm" in text or "aggregator" in text) and "unavailable" in text:
        return {
            "code": "PIPECAT_FEATURE_UNAVAILABLE",
            "phase": "pipeline_start",
            "feature": "llm:openai",
        }
    if "vad" in text and "unavailable" in text:
        return {
            "code": "PIPECAT_FEATURE_UNAVAILABLE",
            "phase": "pipeline_start",
            "feature": "vad:silero",
        }
    if "user turn" in text and "unavailable" in text:
        return {
            "code": "PIPECAT_FEATURE_UNAVAILABLE",
            "phase": "pipeline_start",
            "feature": "turnDetection:pipecat",
        }
    if "not importable" in text or ("module" in text and "missing" in text):
        return {"code": "PIPECAT_MODULE_UNAVAILABLE", "phase": "runtime_import"}
    return {}


def _feature_from_error_text(text: str) -> str | None:
    if "stt" in text:
        return "stt:openai"
    if "tts" in text:
        return "tts:openai"
    if "llm" in text:
        return "llm:openai"
    return None


__all__ = [
    "RealtimePipelineEventSink",
    "RealtimePipelineProviderError",
    "RealtimePipelineStartError",
    "RealtimePipelineRunnerStateError",
    "RealtimePipelineSessionRunner",
]
