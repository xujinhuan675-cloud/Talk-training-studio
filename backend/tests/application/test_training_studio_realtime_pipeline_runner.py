import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from application.ports.realtime import (
    PersistedRealtimeTranscript,
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    RealtimeTranscript,
    TrainingVoiceContext,
)
from application.services.training_studio.realtime_pipeline_runner import (
    RealtimePipelineRunnerStateError,
    RealtimePipelineSessionRunner,
)


class FakeRealtimePipelineAdapter:
    def __init__(self) -> None:
        self.started_context: TrainingVoiceContext | None = None
        self.started_config: RealtimePipelineConfig | None = None
        self.appended_chunks: list[RealtimeAudioChunk] = []
        self.commit_count = 0
        self.close_count = 0
        self.start_error: Exception | None = None
        self._events: asyncio.Queue[Mapping[str, Any] | None] = asyncio.Queue()

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        self.started_context = context
        self.started_config = config
        if self.start_error is not None:
            raise self.start_error

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self.appended_chunks.append(chunk)

    async def commit_audio(self) -> None:
        self.commit_count += 1

    async def events(self) -> AsyncIterator[Mapping[str, Any]]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        self.close_count += 1
        await self._events.put(None)

    async def emit(self, event: Mapping[str, Any]) -> None:
        await self._events.put(event)


class FakeTrainingTranscriptSink:
    def __init__(self) -> None:
        self.persisted: list[RealtimeTranscript] = []
        self._persisted_event = asyncio.Event()

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
        self.persisted.append(transcript)
        self._persisted_event.set()
        return PersistedRealtimeTranscript(transcript=transcript, message_id=len(self.persisted))

    async def wait_for_persisted(self, count: int = 1) -> None:
        async def _wait() -> None:
            while len(self.persisted) < count:
                self._persisted_event.clear()
                await self._persisted_event.wait()

        await asyncio.wait_for(_wait(), timeout=1)


class FakeRealtimeEventSink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._forwarded_event = asyncio.Event()

    async def __call__(self, event: Mapping[str, Any]) -> None:
        self.events.append(dict(event))
        self._forwarded_event.set()

    async def wait_for_events(self, count: int = 1) -> None:
        async def _wait() -> None:
            while len(self.events) < count:
                self._forwarded_event.clear()
                await self._forwarded_event.wait()

        await asyncio.wait_for(_wait(), timeout=1)


def _binding() -> RealtimeSessionBinding:
    return RealtimeSessionBinding(training_session_id="training-1", room_id=42)


async def _started_runner(
    *,
    adapter: FakeRealtimePipelineAdapter | None = None,
    sink: FakeTrainingTranscriptSink | None = None,
    event_sink: FakeRealtimeEventSink | None = None,
) -> tuple[RealtimePipelineSessionRunner, FakeRealtimePipelineAdapter, FakeTrainingTranscriptSink]:
    fake_adapter = adapter or FakeRealtimePipelineAdapter()
    fake_sink = sink or FakeTrainingTranscriptSink()
    runner = RealtimePipelineSessionRunner(
        adapter=fake_adapter,
        transcript_sink=fake_sink,
        event_sink=event_sink,
    )
    await runner.start(
        binding=_binding(),
        provider="pipecat",
        realtime_session_id="rt-1",
        task_goal="Practice discovery",
        rubric={"clarity": 0.6},
        recent_turns=[{"speaker": "user", "text": "What is the priority?"}],
        context_metadata={"scenario": "sales"},
        model="test-model",
        voice="alloy",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        instructions="Keep responses concise.",
        config_metadata={"sampleRate": 24000},
    )
    return runner, fake_adapter, fake_sink


@pytest.mark.asyncio
async def test_runner_start_builds_context_and_config_for_adapter():
    runner, adapter, _sink = await _started_runner()

    assert adapter.started_context == TrainingVoiceContext(
        binding=_binding(),
        task_goal="Practice discovery",
        rubric={"clarity": 0.6},
        recent_turns=({"speaker": "user", "text": "What is the priority?"},),
        metadata={"scenario": "sales"},
    )
    assert adapter.started_config == RealtimePipelineConfig(
        provider="pipecat",
        model="test-model",
        voice="alloy",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        instructions="Keep responses concise.",
        metadata={"sampleRate": 24000},
    )
    assert runner.context == adapter.started_context
    assert runner.config == adapter.started_config
    assert runner.realtime_session_id == "rt-1"

    await runner.close()


@pytest.mark.asyncio
async def test_runner_closes_adapter_when_start_fails():
    adapter = FakeRealtimePipelineAdapter()
    adapter.start_error = RuntimeError("Pipecat OpenAI STT is unavailable")
    runner = RealtimePipelineSessionRunner(
        adapter=adapter,
        transcript_sink=FakeTrainingTranscriptSink(),
    )

    with pytest.raises(RuntimeError, match="Pipecat OpenAI STT"):
        await runner.start(
            binding=_binding(),
            provider="pipecat",
            realtime_session_id="rt-1",
        )

    assert adapter.close_count == 1


@pytest.mark.asyncio
async def test_runner_append_audio_passes_chunk_through_to_adapter():
    runner, adapter, _sink = await _started_runner()
    chunk = RealtimeAudioChunk(
        data=b"pcm",
        mime_type="audio/pcm",
        sequence=3,
        metadata={"sample_rate": 16000},
    )

    await runner.append_audio(chunk)

    assert adapter.appended_chunks == [chunk]

    await runner.close()


@pytest.mark.asyncio
async def test_runner_commit_flushes_adapter_audio():
    runner, adapter, _sink = await _started_runner()

    await runner.commit()

    assert adapter.commit_count == 1

    await runner.close()


@pytest.mark.asyncio
async def test_runner_persists_final_transcripts_from_adapter_events():
    event_sink = FakeRealtimeEventSink()
    runner, adapter, sink = await _started_runner(event_sink=event_sink)

    await adapter.emit(
        {
            "type": "transcript.done",
            "event_id": "evt-1",
            "text": "  We can start with a pilot.  ",
        }
    )
    await sink.wait_for_persisted()

    assert len(sink.persisted) == 1
    transcript = sink.persisted[0]
    assert transcript.text == "We can start with a pilot."
    assert transcript.binding == _binding()
    assert transcript.provider == "pipecat"
    assert transcript.realtime_session_id == "rt-1"
    assert transcript.event_id == "evt-1"

    await runner.close()
    assert event_sink.events == []


@pytest.mark.asyncio
async def test_runner_forwards_non_transcript_adapter_events_to_event_sink():
    event_sink = FakeRealtimeEventSink()
    runner, adapter, sink = await _started_runner(event_sink=event_sink)

    await adapter.emit(
        {
            "type": "audio.output",
            "event_id": "evt-audio-1",
            "audio": "base64-pcm",
            "mime_type": "audio/pcm",
            "sequence": 2,
        }
    )
    await event_sink.wait_for_events()

    assert event_sink.events == [
        {
            "type": "audio.output",
            "event_id": "evt-audio-1",
            "audio": "base64-pcm",
            "mime_type": "audio/pcm",
            "sequence": 2,
        }
    ]
    assert sink.persisted == []

    await runner.close()


@pytest.mark.asyncio
async def test_runner_does_not_forward_non_final_transcript_events_to_event_sink():
    event_sink = FakeRealtimeEventSink()
    runner, adapter, sink = await _started_runner(event_sink=event_sink)

    await adapter.emit({"type": "transcript.delta", "text": "draft"})
    await runner.close()

    assert event_sink.events == []
    assert sink.persisted == []


@pytest.mark.asyncio
async def test_runner_ignores_non_final_transcript_events():
    runner, adapter, sink = await _started_runner()

    await adapter.emit({"type": "response.created", "text": "draft"})
    await adapter.emit({"type": "response.audio_transcript.done", "text": "final response"})
    await sink.wait_for_persisted()

    assert len(sink.persisted) == 1
    assert sink.persisted[0].text == "final response"

    await runner.close()


@pytest.mark.asyncio
async def test_runner_close_closes_adapter():
    runner, adapter, _sink = await _started_runner()

    await runner.close()

    assert adapter.close_count == 1


@pytest.mark.asyncio
async def test_runner_close_drains_queued_final_transcripts_before_stopping_pump():
    runner, adapter, sink = await _started_runner()

    await adapter.emit(
        {
            "type": "transcript.done",
            "event_id": "evt-close",
            "text": "Persist this queued turn before closing.",
        }
    )
    await runner.close()

    assert len(sink.persisted) == 1
    assert sink.persisted[0].event_id == "evt-close"
    assert sink.persisted[0].text == "Persist this queued turn before closing."


@pytest.mark.asyncio
async def test_runner_rejects_audio_commands_after_close():
    runner, _adapter, _sink = await _started_runner()

    await runner.close()
    await runner.close()

    with pytest.raises(RealtimePipelineRunnerStateError, match="closed"):
        await runner.append_audio(RealtimeAudioChunk(data=b"late-pcm"))
    with pytest.raises(RealtimePipelineRunnerStateError, match="closed"):
        await runner.commit_audio()


@pytest.mark.parametrize(
    ("provider_event", "expected_message"),
    [
        (
            {
                "type": "pipeline.error",
                "error": {"message": "provider websocket disconnected"},
            },
            "provider websocket disconnected",
        ),
        (
            {
                "type": "error",
                "message": "provider rejected audio frame",
            },
            "provider rejected audio frame",
        ),
        (
            {
                "type": "realtime.error",
                "detail": "provider realtime session expired",
            },
            "provider realtime session expired",
        ),
    ],
)
@pytest.mark.asyncio
async def test_runner_surfaces_provider_error_events_to_later_commands(
    provider_event,
    expected_message,
):
    event_sink = FakeRealtimeEventSink()
    runner, adapter, _sink = await _started_runner(event_sink=event_sink)

    await adapter.emit(provider_event)

    async def _wait_for_error() -> None:
        while runner.events_error is None:
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_error(), timeout=1)

    with pytest.raises(RealtimePipelineRunnerStateError, match=expected_message):
        await runner.commit_audio()

    await runner.close()
    assert event_sink.events == []
