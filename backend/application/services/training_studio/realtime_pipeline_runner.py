"""Application-layer runner for provider-neutral realtime voice pipelines."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any
from uuid import uuid4

from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingTranscriptSink,
    TrainingVoiceContext,
)
from application.services.training_studio.realtime_pipeline import build_realtime_transcript

_EVENT_PUMP_CLOSE_TIMEOUT_SECONDS = 1.0


class RealtimePipelineRunnerStateError(ValueError):
    """Raised when a runner command is called before the pipeline is ready."""


class RealtimePipelineSessionRunner:
    """Bridge realtime pipeline adapter events into Training Studio persistence."""

    def __init__(
        self,
        *,
        adapter: RealtimePipelineAdapter,
        transcript_sink: TrainingTranscriptSink,
    ) -> None:
        self._adapter = adapter
        self._transcript_sink = transcript_sink
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
        except Exception:
            with suppress(Exception):
                await self._adapter.close()
            raise
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
                    raise RuntimeError(_provider_error_message(payload))
                await self._persist_final_transcript(payload, context, config, realtime_session_id)
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
    ) -> None:
        transcript = build_realtime_transcript(
            payload,
            binding=context.binding,
            provider=config.provider,
            realtime_session_id=realtime_session_id,
        )
        if transcript is None:
            return
        await self._transcript_sink.persist(transcript)

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
            raise RealtimePipelineRunnerStateError(
                f"Realtime pipeline event pump failed: {self._events_error}"
            ) from self._events_error


def _is_provider_error(payload: Mapping[str, object]) -> bool:
    event_type = str(payload.get("type") or "").lower()
    return event_type in {"error", "pipeline.error", "realtime.error"}


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


__all__ = [
    "RealtimePipelineRunnerStateError",
    "RealtimePipelineSessionRunner",
]
