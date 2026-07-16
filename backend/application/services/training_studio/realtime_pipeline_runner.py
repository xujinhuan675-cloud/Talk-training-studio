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

    @property
    def context(self) -> TrainingVoiceContext | None:
        return self._context

    @property
    def config(self) -> RealtimePipelineConfig | None:
        return self._config

    @property
    def realtime_session_id(self) -> str | None:
        return self._realtime_session_id

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
        await self._adapter.start(context, config)
        self._events_task = asyncio.create_task(
            self._pump_events(),
            name=f"training-studio-realtime-events-{self._realtime_session_id}",
        )

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self._require_started()
        await self._adapter.append_audio(chunk)

    async def commit(self) -> None:
        self._require_started()
        await self._adapter.commit_audio()

    async def commit_audio(self) -> None:
        await self.commit()

    async def close(self) -> None:
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

        async for event in self._adapter.events():
            await self._persist_final_transcript(dict(event), context, config, realtime_session_id)

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
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        self._events_task = None

    def _require_started(self) -> None:
        if self._context is None or self._config is None or self._realtime_session_id is None:
            raise RealtimePipelineRunnerStateError("Realtime pipeline runner is not started")


__all__ = [
    "RealtimePipelineRunnerStateError",
    "RealtimePipelineSessionRunner",
]
