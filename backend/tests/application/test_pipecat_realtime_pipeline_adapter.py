import asyncio
from dataclasses import dataclass

import pytest

from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)
from infrastructure.external.pipecat import realtime_pipeline as pipecat_adapter


class FakeFrameProcessor:
    def __init__(self, name=None):
        self.name = name
        self.pushed = []

    async def process_frame(self, frame, direction):
        return None

    async def push_frame(self, frame, direction=None):
        self.pushed.append((frame, direction))


class FakeFrameDirection:
    DOWNSTREAM = "downstream"
    UPSTREAM = "upstream"


@dataclass
class FakeInputAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int


class FakeEndFrame:
    pass


@dataclass
class FakeTranscriptionFrame:
    text: str
    user_id: str
    timestamp: str
    finalized: bool = False
    language: str | None = None


@dataclass
class FakeLLMContextAssistantTurnFrame:
    text: str
    timestamp: str


@dataclass
class FakeTextFrame:
    text: str


class FakePipeline:
    def __init__(self, processors):
        self.processors = processors


class FakePipelineParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakePipelineWorker:
    def __init__(self, pipeline, **kwargs):
        self.pipeline = pipeline
        self.kwargs = kwargs
        self.queued_frames = []
        self.flushed = False

    async def queue_frame(self, frame):
        self.queued_frames.append(frame)

    async def flush_pipeline(self):
        self.flushed = True


class FakeWorkerRunner:
    def __init__(self):
        self.workers = []
        self.ran = False

    async def add_workers(self, worker):
        self.workers.append(worker)

    async def run(self):
        self.ran = True


class FakeFastAPIWebsocketParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeFastAPIWebsocketTransport:
    def __init__(self, websocket, params):
        self.websocket = websocket
        self.params = params
        self.input_processor = object()
        self.output_processor = object()

    def input(self):
        return self.input_processor

    def output(self):
        return self.output_processor


def fake_runtime(websocket=True):
    return pipecat_adapter.PipecatRuntime(
        Pipeline=FakePipeline,
        PipelineParams=FakePipelineParams,
        PipelineWorker=FakePipelineWorker,
        WorkerParams=object,
        WorkerRunner=FakeWorkerRunner,
        InputAudioRawFrame=FakeInputAudioRawFrame,
        EndFrame=FakeEndFrame,
        TextFrame=FakeTextFrame,
        TranscriptionFrame=FakeTranscriptionFrame,
        LLMContextAssistantTurnFrame=FakeLLMContextAssistantTurnFrame,
        FrameProcessor=FakeFrameProcessor,
        FrameDirection=FakeFrameDirection,
        FastAPIWebsocketParams=FakeFastAPIWebsocketParams if websocket else None,
        FastAPIWebsocketTransport=FakeFastAPIWebsocketTransport if websocket else None,
    )


def voice_context():
    return TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-1", room_id=7),
        task_goal="Practice a discovery call",
        rubric={"clarity": 1},
        metadata={"scenario": "sales"},
    )


def realtime_config():
    return RealtimePipelineConfig(
        provider="pipecat",
        model="test-model",
        metadata={"sampleRate": 24000, "channels": 1},
    )


def test_pipecat_capability_reports_missing_core_without_importing(monkeypatch):
    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: None)

    capability = pipecat_adapter.get_pipecat_capability()

    assert capability.available is False
    assert capability.core_available is False
    assert "pipecat.pipeline.pipeline" in capability.missing_modules
    assert pipecat_adapter.is_pipecat_available() is False


def test_factory_returns_none_when_optional_pipecat_dependency_is_missing(monkeypatch):
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: pipecat_adapter.PipecatCapability(
            available=False,
            core_available=False,
            websocket_available=False,
            error="not installed",
        ),
    )

    assert pipecat_adapter.create_pipecat_realtime_pipeline() is None


@pytest.mark.asyncio
async def test_adapter_queues_pipecat_audio_frames_instead_of_owning_media_lifecycle():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=fake_runtime(websocket=False))

    await adapter.start(voice_context(), realtime_config())
    await asyncio.sleep(0)
    await adapter.append_audio(
        RealtimeAudioChunk(
            data=b"pcm",
            metadata={"sample_rate": 16000, "num_channels": 1},
        )
    )
    await adapter.commit_audio()

    assert adapter.handle is not None
    assert adapter.handle.runner.workers == [adapter.handle.worker]
    assert adapter.handle.runner.ran is True
    assert not hasattr(adapter, "audio_chunks")
    frame = adapter.handle.worker.queued_frames[0]
    assert isinstance(frame, FakeInputAudioRawFrame)
    assert frame.audio == b"pcm"
    assert frame.sample_rate == 16000
    assert frame.num_channels == 1
    assert adapter.handle.worker.flushed is True


def test_pipeline_handle_uses_pipecat_websocket_transport_as_pipeline_boundary():
    runtime = fake_runtime(websocket=True)
    custom_processor = object()
    websocket = object()

    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=runtime,
        context=voice_context(),
        config=realtime_config(),
        websocket=websocket,
        processors=[custom_processor],
        serializer=object(),
        transport_params={"allowed_origins": []},
    )

    assert isinstance(handle.transport, FakeFastAPIWebsocketTransport)
    assert handle.transport.websocket is websocket
    assert handle.pipeline.processors[0] is handle.transport.input_processor
    assert handle.pipeline.processors[1] is custom_processor
    assert handle.pipeline.processors[-2] is handle.event_processor
    assert handle.pipeline.processors[-1] is handle.transport.output_processor


@pytest.mark.asyncio
async def test_talkwise_event_processor_mirrors_pipecat_transcription_frames():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeTranscriptionFrame(
            text="final user turn",
            user_id="user",
            timestamp="2026-07-16T00:00:00Z",
            finalized=False,
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["type"] == "transcript.done"
    assert event["text"] == "final user turn"
    assert event["source"] == "pipecat"
    assert processor.pushed[0][0].text == "final user turn"


def test_source_snapshot_documents_pipecat_first_boundaries():
    snapshot = pipecat_adapter.pipecat_source_snapshot()

    assert "pipecat.pipeline.pipeline.Pipeline" in snapshot["coreEntrypoints"]
    assert (
        "pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport"
        == snapshot["websocketEntrypoint"]
    )
    assert (
        "RealtimeAudioChunk to InputAudioRawFrame adaptation"
        in snapshot["talkwiseResponsibilities"]
    )
