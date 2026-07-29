import asyncio
import json
import logging
from collections.abc import AsyncIterator, Mapping
from typing import Any

import pytest

from application.ports.realtime import (
    REALTIME_RUNTIME_PIPECAT,
    PersistedRealtimeTranscript,
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    RealtimeTranscript,
    TrainingVoiceContext,
)
from application.services.training_studio.realtime_pipeline_runner import (
    RealtimePipelineStartError,
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
        runtime=REALTIME_RUNTIME_PIPECAT,
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

    with pytest.raises(RealtimePipelineStartError, match="Pipecat OpenAI STT") as exc_info:
        await runner.start(
            binding=_binding(),
            provider="pipecat",
            realtime_session_id="rt-1",
        )

    error = exc_info.value.to_realtime_error()
    assert error["code"] == "PIPECAT_FEATURE_UNAVAILABLE"
    assert error["phase"] == "pipeline_start"
    assert error["provider"] == "pipecat"
    assert error["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert error["feature"] == "stt:openai"
    assert error["trainingSessionId"] == "training-1"
    assert error["roomId"] == 42
    assert error["realtimeSessionId"] == "rt-1"
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
    await event_sink.wait_for_events()

    assert len(sink.persisted) == 1
    transcript = sink.persisted[0]
    assert transcript.text == "We can start with a pilot."
    assert transcript.binding == _binding()
    assert transcript.provider == "pipecat"
    assert transcript.runtime == REALTIME_RUNTIME_PIPECAT
    assert transcript.realtime_session_id == "rt-1"
    assert transcript.event_id == "evt-1"
    assert event_sink.events == [
        {
            "type": "training.live_guidance.triggered",
            "schemaVersion": 1,
            "source": "realtime_voice",
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "reason": "final_transcript",
            "provider": "pipecat",
            "trainingSessionId": "training-1",
            "roomId": 42,
            "realtimeSessionId": "rt-1",
            "transcript": {
                "text": "We can start with a pilot.",
                "role": "user",
                "eventType": "transcript.done",
                "runtime": REALTIME_RUNTIME_PIPECAT,
                "eventId": "evt-1",
            },
            "messageId": 1,
        }
    ]

    await runner.close()


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
async def test_runner_collects_provider_neutral_telemetry_summary_for_observable_events():
    event_sink = FakeRealtimeEventSink()
    runner, adapter, _sink = await _started_runner(event_sink=event_sink)

    await adapter.emit({"type": "user_turn.started", "payload": {"signal": "user_turn"}})
    await adapter.emit(
        {
            "type": "user_turn.stopped",
            "payload": {"signal": "vad", "silenceSeconds": 0.8},
        }
    )
    await adapter.emit(
        {
            "type": "audio.output",
            "audio": "base64-pcm-should-not-be-in-summary",
            "bytes": 4,
            "payload": {
                "bytes": 4,
                "metadata": {
                    "realtimeMetrics": {
                        "schemaVersion": 1,
                        "turnSequence": 1,
                        "latencyEndEvent": "audio.output",
                        "turnLatencyMs": 150,
                    }
                },
            },
        }
    )
    await adapter.emit({"type": "interrupted", "metadata": {"reason": "barge_in"}})
    await adapter.emit({"type": "silence_timeout", "payload": {"timeoutSeconds": 6.5}})
    await event_sink.wait_for_events(5)

    summary = runner.telemetry_summary
    assert summary["type"] == "realtime.telemetry.summary"
    assert summary["schemaVersion"] == 1
    assert summary["source"] == "realtime_pipeline_runner"
    assert summary["provider"] == "pipecat"
    assert summary["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert summary["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
    assert summary["trainingSessionId"] == "training-1"
    assert summary["roomId"] == 42
    assert summary["realtimeSessionId"] == "rt-1"
    assert summary["events"] == {
        "total": 5,
        "byCategory": {
            "audio_output": 1,
            "interruption": 1,
            "silence": 1,
            "turn": 2,
        },
    }
    assert summary["audioOutput"] == {"events": 1, "bytes": 4}
    assert summary["turns"] == {
        "started": 1,
        "completed": 1,
        "latencyMs": {"count": 1, "min": 150, "max": 150, "avg": 150},
    }
    assert summary["interruptions"] == {"events": 1}
    assert summary["silence"] == {"events": 1}
    assert summary["providerErrors"] == {
        "total": 0,
        "fatal": 0,
        "retryable": 0,
        "byCategory": {},
    }
    assert "base64-pcm-should-not-be-in-summary" not in json.dumps(summary)

    await runner.close()


@pytest.mark.asyncio
async def test_runner_collects_secret_safe_provider_error_telemetry_summary():
    runner, adapter, _sink = await _started_runner()

    await adapter.emit(
        {
            "type": "pipeline.error",
            "status": 401,
            "error": {
                "message": "invalid api key sk-secret-should-not-appear",
                "code": "unauthorized",
            },
            "metadata": {
                "apiKey": "sk-secret-should-not-appear",
                "Authorization": "Bearer secret-should-not-appear",
            },
        }
    )

    async def _wait_for_error() -> None:
        while runner.events_error is None:
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_error(), timeout=1)

    summary = runner.telemetry_summary
    assert summary["events"] == {"total": 1, "byCategory": {"provider_error": 1}}
    assert summary["providerErrors"] == {
        "total": 1,
        "fatal": 1,
        "retryable": 0,
        "byCategory": {"authentication": 1},
    }
    serialized = json.dumps(summary)
    assert "secret-should-not-appear" not in serialized
    assert "apiKey" not in serialized
    assert "Authorization" not in serialized

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
    ("provider_event", "expected_message", "expected_code", "expected_category"),
    [
        (
            {
                "type": "pipeline.error",
                "error": {"message": "provider websocket disconnected"},
            },
            "provider websocket disconnected",
            "REALTIME_PROVIDER_UNAVAILABLE",
            "provider_unavailable",
        ),
        (
            {
                "type": "error",
                "message": "provider rejected audio frame",
            },
            "provider rejected audio frame",
            "REALTIME_PROVIDER_ERROR",
            "provider_error",
        ),
        (
            {
                "type": "realtime.error",
                "detail": "provider realtime session expired",
            },
            "provider realtime session expired",
            "REALTIME_PROVIDER_ERROR",
            "provider_error",
        ),
        (
            {
                "type": "error",
                "payload": {
                    "message": "Volcengine request parameter is invalid",
                    "code": "InvalidParameter",
                    "status": 400,
                    "metadata": {"requestId": "req-volc-1"},
                },
            },
            "Volcengine request parameter is invalid",
            "REALTIME_PROVIDER_BAD_REQUEST",
            "bad_request",
        ),
    ],
)
@pytest.mark.asyncio
async def test_runner_surfaces_provider_error_events_to_later_commands(
    provider_event,
    expected_message,
    expected_code,
    expected_category,
):
    event_sink = FakeRealtimeEventSink()
    runner, adapter, _sink = await _started_runner(event_sink=event_sink)

    await adapter.emit(provider_event)

    async def _wait_for_error() -> None:
        while runner.events_error is None:
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_error(), timeout=1)

    with pytest.raises(RealtimePipelineRunnerStateError, match=expected_message) as exc_info:
        await runner.commit_audio()

    assert exc_info.value.code == expected_code
    assert exc_info.value.phase == "provider_event"
    assert exc_info.value.provider == "pipecat"
    assert exc_info.value.metadata["eventType"] == provider_event["type"]
    assert exc_info.value.metadata["errorCategory"] == expected_category
    assert exc_info.value.metadata["fatal"] is True
    assert exc_info.value.metadata["retryable"] is (expected_category == "provider_unavailable")
    if expected_category == "bad_request":
        assert exc_info.value.metadata["sourceCode"] == "InvalidParameter"
        assert exc_info.value.metadata["metadata"]["requestId"] == "req-volc-1"
        assert exc_info.value.metadata["metadata"]["statusCode"] == 400
    await runner.close()
    assert event_sink.events == []


@pytest.mark.asyncio
async def test_runner_logs_provider_event_pump_failure_with_structured_details(caplog):
    caplog.set_level(
        logging.WARNING,
        logger="application.services.training_studio.realtime_pipeline_runner",
    )
    runner, adapter, _sink = await _started_runner()

    await adapter.emit(
        {
            "type": "error",
            "payload": {
                "message": "Volcengine request parameter is invalid",
                "code": "InvalidParameter",
                "status": 400,
                "metadata": {"requestId": "req-invalid-1"},
            },
        }
    )

    async def _wait_for_error() -> None:
        while runner.events_error is None:
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_error(), timeout=1)

    record = next(
        item for item in caplog.records if item.message == "Realtime pipeline event pump failed"
    )
    error = record.realtime_error
    assert error["message"] == "Volcengine request parameter is invalid"
    assert error["code"] == "REALTIME_PROVIDER_BAD_REQUEST"
    assert error["errorCategory"] == "bad_request"
    assert error["metadata"]["requestId"] == "req-invalid-1"
    assert error["metadata"]["statusCode"] == 400
    assert error["trainingSessionId"] == "training-1"
    assert error["roomId"] == 42
    await runner.close()


@pytest.mark.asyncio
async def test_runner_sanitizes_provider_error_events_before_rethrowing():
    runner, adapter, _sink = await _started_runner()

    await adapter.emit(
        {
            "type": "pipeline.error",
            "error": {
                "message": "provider failed with invalid request sk-secret-should-not-appear",
                "code": "bad_request",
            },
            "metadata": {
                "apiKey": "sk-secret-should-not-appear",
                "Authorization": "Bearer secret-should-not-appear",
                "safe": "kept",
            },
        }
    )

    async def _wait_for_error() -> None:
        while runner.events_error is None:
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait_for_error(), timeout=1)

    with pytest.raises(RealtimePipelineRunnerStateError) as exc_info:
        await runner.commit_audio()

    error = exc_info.value.to_realtime_error()
    assert error["code"] == "REALTIME_PROVIDER_BAD_REQUEST"
    assert error["phase"] == "provider_event"
    assert error["eventType"] == "pipeline.error"
    assert error["errorCategory"] == "bad_request"
    assert error["retryable"] is False
    assert error["fatal"] is True
    assert error["sourceCode"] == "bad_request"
    assert error["metadata"] == {"safe": "kept"}
    serialized = json.dumps(error)
    assert "secret-should-not-appear" not in serialized
    assert "apiKey" not in serialized
    assert "Authorization" not in serialized
    await runner.close()
