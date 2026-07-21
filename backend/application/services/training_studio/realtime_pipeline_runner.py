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
    classify_realtime_pipeline_start_error_message,
    normalize_realtime_runtime,
    redact_realtime_secret_text,
    sanitize_realtime_public_value,
)
from application.services.training_studio.realtime_pipeline import build_realtime_transcript

_EVENT_PUMP_CLOSE_TIMEOUT_SECONDS = 1.0
RealtimePipelineEventSink = Callable[[Mapping[str, Any]], Awaitable[None] | None]
logger = logging.getLogger(__name__)

REALTIME_PROVIDER_ERROR_TAXONOMY: tuple[dict[str, Any], ...] = (
    {
        "errorCategory": "authentication",
        "code": "REALTIME_PROVIDER_AUTHENTICATION",
        "retryable": False,
        "fatal": True,
    },
    {
        "errorCategory": "rate_limit",
        "code": "REALTIME_PROVIDER_RATE_LIMIT",
        "retryable": True,
        "fatal": False,
    },
    {
        "errorCategory": "provider_unavailable",
        "code": "REALTIME_PROVIDER_UNAVAILABLE",
        "retryable": True,
        "fatal": True,
    },
    {
        "errorCategory": "bad_request",
        "code": "REALTIME_PROVIDER_BAD_REQUEST",
        "retryable": False,
        "fatal": True,
    },
    {
        "errorCategory": "provider_error",
        "code": "REALTIME_PROVIDER_ERROR",
        "retryable": False,
        "fatal": True,
    },
)
_ERROR_TAXONOMY_BY_CATEGORY = {
    str(item["errorCategory"]): item for item in REALTIME_PROVIDER_ERROR_TAXONOMY
}


class _RealtimePipelineTelemetry:
    def __init__(self) -> None:
        self.total_events = 0
        self.event_categories: dict[str, int] = {}
        self.audio_output_events = 0
        self.audio_output_bytes = 0
        self.turn_started = 0
        self.turn_completed = 0
        self.interruption_events = 0
        self.silence_events = 0
        self.provider_error_events = 0
        self.provider_error_fatal = 0
        self.provider_error_retryable = 0
        self.provider_error_categories: dict[str, int] = {}
        self._active_turn_started_at_ms: dict[str, float] = {}
        self._recorded_latency_turn_keys: set[str] = set()
        self._turn_latency_count = 0
        self._turn_latency_total_ms = 0.0
        self._turn_latency_min_ms: float | None = None
        self._turn_latency_max_ms: float | None = None

    def record_event(
        self,
        payload: Mapping[str, Any],
        *,
        provider_error: RealtimePipelineProviderError | None = None,
    ) -> None:
        category = _telemetry_event_category(payload)
        self.total_events += 1
        _increment_count(self.event_categories, category)

        if _is_audio_output_event(payload):
            self.audio_output_events += 1
            self.audio_output_bytes += _extract_audio_output_bytes(payload)

        if _is_turn_event(payload):
            self._record_turn_event(payload)
        else:
            latency_ms = _extract_turn_latency_ms(payload)
            if latency_ms is not None:
                self._record_turn_latency(payload, latency_ms)

        if _is_interruption_event(payload):
            self.interruption_events += 1
        if _is_silence_event(payload):
            self.silence_events += 1
        if provider_error is not None:
            self._record_provider_error(provider_error)

    def to_summary(self) -> dict[str, Any]:
        return {
            "events": {
                "total": self.total_events,
                "byCategory": dict(sorted(self.event_categories.items())),
            },
            "audioOutput": {
                "events": self.audio_output_events,
                "bytes": self.audio_output_bytes,
            },
            "turns": {
                "started": self.turn_started,
                "completed": self.turn_completed,
                "latencyMs": self._latency_summary(),
            },
            "interruptions": {"events": self.interruption_events},
            "silence": {"events": self.silence_events},
            "providerErrors": {
                "total": self.provider_error_events,
                "fatal": self.provider_error_fatal,
                "retryable": self.provider_error_retryable,
                "byCategory": dict(sorted(self.provider_error_categories.items())),
            },
        }

    def _record_turn_event(self, payload: Mapping[str, Any]) -> None:
        turn_key = _turn_identity(payload) or "_current"
        timestamp_ms = _extract_event_timestamp_ms(payload)
        latency_ms = _extract_turn_latency_ms(payload)

        if _is_turn_started_event(payload):
            self.turn_started += 1
            if timestamp_ms is not None:
                self._active_turn_started_at_ms[turn_key] = timestamp_ms

        if _is_turn_completed_event(payload):
            self.turn_completed += 1
            if latency_ms is None and timestamp_ms is not None:
                started_at_ms = self._active_turn_started_at_ms.pop(turn_key, None)
                if started_at_ms is not None and timestamp_ms >= started_at_ms:
                    latency_ms = timestamp_ms - started_at_ms

        if latency_ms is not None:
            self._record_turn_latency(payload, latency_ms)

    def _record_turn_latency(self, payload: Mapping[str, Any], latency_ms: float) -> None:
        turn_key = _turn_identity(payload)
        if turn_key is not None:
            if turn_key in self._recorded_latency_turn_keys:
                return
            self._recorded_latency_turn_keys.add(turn_key)

        self._turn_latency_count += 1
        self._turn_latency_total_ms += latency_ms
        self._turn_latency_min_ms = (
            latency_ms
            if self._turn_latency_min_ms is None
            else min(self._turn_latency_min_ms, latency_ms)
        )
        self._turn_latency_max_ms = (
            latency_ms
            if self._turn_latency_max_ms is None
            else max(self._turn_latency_max_ms, latency_ms)
        )

    def _record_provider_error(self, error: RealtimePipelineProviderError) -> None:
        self.provider_error_events += 1
        _increment_count(self.provider_error_categories, error.error_category)
        if error.fatal:
            self.provider_error_fatal += 1
        if error.retryable:
            self.provider_error_retryable += 1

    def _latency_summary(self) -> dict[str, Any]:
        if self._turn_latency_count == 0:
            return {"count": 0}
        return {
            "count": self._turn_latency_count,
            "min": _public_millis(self._turn_latency_min_ms or 0.0),
            "max": _public_millis(self._turn_latency_max_ms or 0.0),
            "avg": _public_millis(self._turn_latency_total_ms / self._turn_latency_count),
        }


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
        super().__init__(redact_realtime_secret_text(message))
        self.code = code
        self.phase = phase
        self.provider = provider
        safe_metadata = sanitize_realtime_public_value(dict(metadata or {}))
        self.metadata = dict(safe_metadata) if isinstance(safe_metadata, Mapping) else {}

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
        super().__init__(redact_realtime_secret_text(message))
        self.code = code
        self.phase = phase
        self.provider = provider
        safe_metadata = sanitize_realtime_public_value(dict(metadata or {}))
        self.metadata = dict(safe_metadata) if isinstance(safe_metadata, Mapping) else {}

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
        safe_payload = sanitize_realtime_public_value(dict(payload))
        self.payload = dict(safe_payload) if isinstance(safe_payload, Mapping) else {}
        self.provider = provider
        message = _provider_error_message(self.payload)
        super().__init__(message)
        self.error_category = _provider_error_category(self.payload)
        self.code = _provider_error_public_code(self.error_category)
        self.retryable = _provider_error_retryable(self.error_category)
        self.fatal = _provider_error_fatal(self.error_category, self.payload)
        self.phase = "provider_event"
        self.event_type = str(self.payload.get("type") or "")
        self.processor = _provider_error_processor(self.payload)

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": self.provider,
            "eventType": self.event_type,
            "errorCategory": self.error_category,
            "retryable": self.retryable,
            "fatal": self.fatal,
        }
        source_code = _provider_error_source_code(self.payload)
        if source_code is not None:
            payload["sourceCode"] = source_code
        if self.processor is not None:
            payload["processor"] = self.processor
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
        self._telemetry = _RealtimePipelineTelemetry()
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

    @property
    def telemetry_summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "realtime.telemetry.summary",
            "schemaVersion": 1,
            "source": "realtime_pipeline_runner",
            **self._telemetry.to_summary(),
        }
        if self._config is not None:
            runtime = normalize_realtime_runtime(self._config.runtime, provider=self._config.provider)
            payload["provider"] = _safe_telemetry_text(self._config.provider)
            payload["runtime"] = _safe_telemetry_text(runtime)
            payload["realtimeRuntime"] = _safe_telemetry_text(runtime)
        if self._context is not None:
            payload["trainingSessionId"] = _safe_telemetry_text(
                self._context.binding.training_session_id
            )
            payload["roomId"] = self._context.binding.room_id
        if self._realtime_session_id is not None:
            payload["realtimeSessionId"] = _safe_telemetry_text(self._realtime_session_id)
        return payload

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
        runtime: str | None = None,
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
            runtime=normalize_realtime_runtime(runtime, provider=provider),
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
        self._telemetry = _RealtimePipelineTelemetry()
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
                    provider_error = RealtimePipelineProviderError(
                        payload,
                        provider=config.provider,
                    )
                    self._telemetry.record_event(payload, provider_error=provider_error)
                    if not provider_error.fatal:
                        await self._forward_event(
                            _provider_error_event(
                                provider_error,
                                context=context,
                                config=config,
                                realtime_session_id=realtime_session_id,
                            )
                        )
                        continue
                    raise provider_error
                self._telemetry.record_event(payload)
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
            runtime=config.runtime,
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
    return event_type in {"error", "pipeline.error", "realtime.error"} or event_type.endswith(
        ".error"
    )


def _telemetry_event_category(payload: Mapping[str, Any]) -> str:
    if _is_provider_error(payload):
        return "provider_error"
    if _is_audio_output_event(payload):
        return "audio_output"
    if _is_interruption_event(payload):
        return "interruption"
    if _is_silence_event(payload):
        return "silence"
    if _is_turn_event(payload):
        return "turn"
    if _is_transcript_event(payload):
        return "transcript"
    return "other"


def _is_audio_output_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    return event_type == "audio.output" or event_type.endswith(".audio.output")


def _is_turn_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    if "turn" in event_type:
        return True
    if _extract_realtime_metrics(payload):
        return True
    signal = _public_text_field(payload, ("signal",))
    return signal is not None and "turn" in signal.lower()


def _is_turn_started_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    return "turn" in event_type and (
        event_type.endswith(".started")
        or event_type.endswith("_started")
        or event_type.endswith(".start")
        or event_type.endswith("_start")
    )


def _is_turn_completed_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    return "turn" in event_type and any(
        event_type.endswith(suffix)
        for suffix in (
            ".stopped",
            "_stopped",
            ".completed",
            "_completed",
            ".complete",
            "_complete",
            ".ended",
            "_ended",
            ".done",
            "_done",
        )
    )


def _is_interruption_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    return any(token in event_type for token in ("interrupt", "interrupted", "interruption"))


def _is_silence_event(payload: Mapping[str, Any]) -> bool:
    event_type = _event_type(payload)
    signal = _public_text_field(payload, ("signal",))
    return "silence" in event_type or (signal is not None and "silence" in signal.lower())


def _extract_audio_output_bytes(payload: Mapping[str, Any]) -> int:
    value = _numeric_telemetry_value(
        payload,
        ("bytes", "byteLength", "byte_length", "audioBytes", "audio_bytes"),
    )
    if value is None:
        return 0
    return max(0, int(value))


def _extract_turn_latency_ms(payload: Mapping[str, Any]) -> float | None:
    return _numeric_telemetry_value(
        payload,
        ("turnLatencyMs", "turn_latency_ms", "latencyMs", "latency_ms"),
    )


def _extract_event_timestamp_ms(payload: Mapping[str, Any]) -> float | None:
    milliseconds = _numeric_telemetry_value(
        payload,
        ("timestampMs", "timestamp_ms", "timeMs", "time_ms", "createdAtMs", "created_at_ms"),
    )
    if milliseconds is not None:
        return milliseconds
    seconds = _numeric_telemetry_value(payload, ("timestampSeconds", "timestamp_seconds", "timestamp"))
    if seconds is None:
        return None
    return seconds * 1000


def _turn_identity(payload: Mapping[str, Any]) -> str | None:
    for item in _iter_telemetry_mappings(payload):
        for key in ("turnId", "turn_id", "turnSequence", "turn_sequence"):
            value = item.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int | float):
                return str(value)
    return None


def _extract_realtime_metrics(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for item in _iter_telemetry_mappings(payload):
        value = item.get("realtimeMetrics")
        if isinstance(value, Mapping):
            return value
    return None


def _numeric_telemetry_value(payload: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for item in _iter_telemetry_mappings(payload):
        for key in keys:
            value = _coerce_non_negative_float(item.get(key))
            if value is not None:
                return value
    return None


def _coerce_non_negative_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if value >= 0 else None
    if isinstance(value, str) and value.strip():
        with suppress(ValueError):
            parsed = float(value.strip())
            return parsed if parsed >= 0 else None
    return None


def _public_text_field(payload: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for item in _iter_telemetry_mappings(payload):
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _iter_telemetry_mappings(payload: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = [payload]
    nested_payload = payload.get("payload")
    if isinstance(nested_payload, Mapping):
        items.append(nested_payload)
    for item in tuple(items):
        metadata = item.get("metadata")
        if isinstance(metadata, Mapping):
            items.append(metadata)
            metrics = metadata.get("realtimeMetrics")
            if isinstance(metrics, Mapping):
                items.append(metrics)
    return items


def _event_type(payload: Mapping[str, Any]) -> str:
    return str(payload.get("type") or "").lower()


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _public_millis(value: float) -> int | float:
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _safe_telemetry_text(value: object) -> str:
    return redact_realtime_secret_text(str(value))


def _provider_error_event(
    error: RealtimePipelineProviderError,
    *,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    realtime_session_id: str,
) -> dict[str, Any]:
    payload = error.to_realtime_error()
    runtime = normalize_realtime_runtime(config.runtime, provider=config.provider)
    payload.setdefault("runtime", runtime)
    payload.setdefault("realtimeRuntime", runtime)
    payload.setdefault("trainingSessionId", context.binding.training_session_id)
    payload.setdefault("roomId", context.binding.room_id)
    payload.setdefault("realtimeSessionId", realtime_session_id)
    return {
        "type": "error",
        "schemaVersion": 1,
        "source": "realtime_pipeline",
        **payload,
    }


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
        "runtime": normalize_realtime_runtime(transcript.runtime, provider=config.provider),
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
        "runtime": normalize_realtime_runtime(config.runtime, provider=config.provider),
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
            return redact_realtime_secret_text(value.strip())
        if isinstance(value, Mapping):
            nested = value.get("message") or value.get("detail")
            if isinstance(nested, str) and nested.strip():
                return redact_realtime_secret_text(nested.strip())
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
    if code in {
        "PIPECAT_PROVIDER_ERROR",
        _provider_error_public_code(_provider_error_category(payload)),
    }:
        return None
    return code


def _provider_error_public_code(category: str) -> str:
    item = _ERROR_TAXONOMY_BY_CATEGORY.get(category) or _ERROR_TAXONOMY_BY_CATEGORY[
        "provider_error"
    ]
    return str(item["code"])


def _provider_error_retryable(category: str) -> bool:
    item = _ERROR_TAXONOMY_BY_CATEGORY.get(category) or _ERROR_TAXONOMY_BY_CATEGORY[
        "provider_error"
    ]
    return bool(item["retryable"])


def _provider_error_fatal(category: str, payload: Mapping[str, object]) -> bool:
    value = payload.get("fatal")
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    error = payload.get("error")
    if isinstance(error, Mapping):
        for key in ("fatal", "isFatal"):
            nested = error.get(key)
            if isinstance(nested, bool):
                return nested
    item = _ERROR_TAXONOMY_BY_CATEGORY.get(category) or _ERROR_TAXONOMY_BY_CATEGORY[
        "provider_error"
    ]
    return bool(item["fatal"])


def _provider_error_processor(payload: Mapping[str, object]) -> str | None:
    for key in ("processor", "service", "sourceProcessor", "source_processor"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    error = payload.get("error")
    if isinstance(error, Mapping):
        for key in ("processor", "service", "sourceProcessor", "source_processor"):
            value = error.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _provider_error_category(payload: Mapping[str, object]) -> str:
    source_code = _provider_error_code(payload).lower()
    status_code = _provider_error_status_code(payload)
    message = _provider_error_message(payload).lower()
    haystack = " ".join(part for part in (source_code, message) if part)

    if status_code in {401, 403} or any(
        token in haystack
        for token in (
            "api key",
            "api_key",
            "auth",
            "authentication",
            "forbidden",
            "unauthorized",
        )
    ):
        return "authentication"
    if status_code == 429 or any(
        token in haystack for token in ("quota", "rate limit", "rate_limit", "too many")
    ):
        return "rate_limit"
    if status_code in {408, 409} or status_code >= 500 or any(
        token in haystack
        for token in (
            "connection",
            "connect",
            "disconnect",
            "overload",
            "overloaded",
            "temporarily",
            "timeout",
            "unavailable",
        )
    ):
        return "provider_unavailable"
    if 400 <= status_code < 500 or any(
        token in haystack for token in ("bad request", "bad_request", "invalid_request")
    ):
        return "bad_request"
    return "provider_error"


def _provider_error_status_code(payload: Mapping[str, object]) -> int:
    for key in ("status", "statusCode", "status_code"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    error = payload.get("error")
    if isinstance(error, Mapping):
        return _provider_error_status_code(error)
    return 0


def _provider_error_metadata(payload: Mapping[str, object]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("request_id", "requestId", "trace_id", "traceId"):
        value = payload.get(key)
        if isinstance(value, str | int | float | bool):
            metadata[key] = value
    status_code = _provider_error_status_code(payload)
    if status_code:
        metadata["statusCode"] = status_code
    nested_metadata = payload.get("metadata")
    if isinstance(nested_metadata, Mapping):
        for key, value in nested_metadata.items():
            safe_item = sanitize_realtime_public_value({key: value})
            if isinstance(safe_item, Mapping):
                metadata.update(dict(safe_item))
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
    metadata.setdefault("runtime", normalize_realtime_runtime(None, provider=provider))
    metadata.setdefault("trainingSessionId", binding.training_session_id)
    metadata.setdefault("roomId", binding.room_id)
    if realtime_session_id is not None:
        metadata.setdefault("realtimeSessionId", realtime_session_id)

    if code == "REALTIME_PIPELINE_START_FAILED":
        fallback = classify_realtime_pipeline_start_error_message(message)
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
                    safe_value = sanitize_realtime_public_value(value)
                    if isinstance(safe_value, Mapping):
                        return {str(key): item for key, item in safe_value.items()}

    data: dict[str, Any] = {"message": redact_realtime_secret_text(str(exc))}
    for attr_name, output_key in {
        "code": "code",
        "phase": "phase",
        "provider": "provider",
        "feature": "feature",
        "missing_env": "missingEnv",
        "missing_modules": "modules",
        "event_type": "eventType",
        "source_code": "sourceCode",
        "runtime": "runtime",
        "metadata": "metadata",
    }.items():
        if hasattr(exc, attr_name):
            value = getattr(exc, attr_name)
            if value is not None:
                data[output_key] = value
    safe_data = sanitize_realtime_public_value(data)
    return dict(safe_data) if isinstance(safe_data, Mapping) else {"message": data["message"]}


__all__ = [
    "REALTIME_PROVIDER_ERROR_TAXONOMY",
    "RealtimePipelineEventSink",
    "RealtimePipelineProviderError",
    "RealtimePipelineStartError",
    "RealtimePipelineRunnerStateError",
    "RealtimePipelineSessionRunner",
]
