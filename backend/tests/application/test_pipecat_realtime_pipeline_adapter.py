import asyncio
from dataclasses import dataclass, field

import pytest

from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)
from core.config import settings
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
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 101
    name: str = "FakeTranscriptionFrame"
    pts: int | None = None


@dataclass
class FakeInterimTranscriptionFrame:
    text: str
    user_id: str
    timestamp: str
    language: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 303
    name: str = "FakeInterimTranscriptionFrame"
    pts: int | None = None


@dataclass
class FakeLLMContextAssistantTurnFrame:
    text: str
    timestamp: str
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 202
    name: str = "FakeLLMContextAssistantTurnFrame"
    pts: int | None = None


@dataclass
class FakeTextFrame:
    text: str


class FakeOpenAIRealtimeSTTService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeSileroVADAnalyzer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeVADParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeVADProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeOpenAITTSService:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeUserTurnProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeExternalUserTurnStrategies:
    pass


class FakeFilterIncompleteUserTurnStrategies:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeUserTurnCompletionConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


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
        InterimTranscriptionFrame=FakeInterimTranscriptionFrame,
        FastAPIWebsocketParams=FakeFastAPIWebsocketParams if websocket else None,
        FastAPIWebsocketTransport=FakeFastAPIWebsocketTransport if websocket else None,
        SileroVADAnalyzer=FakeSileroVADAnalyzer,
        VADParams=FakeVADParams,
        VADProcessor=FakeVADProcessor,
        OpenAIRealtimeSTTService=FakeOpenAIRealtimeSTTService,
        OpenAITTSService=FakeOpenAITTSService,
        UserTurnProcessor=FakeUserTurnProcessor,
        ExternalUserTurnStrategies=FakeExternalUserTurnStrategies,
        FilterIncompleteUserTurnStrategies=FakeFilterIncompleteUserTurnStrategies,
        UserTurnCompletionConfig=FakeUserTurnCompletionConfig,
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


def test_pipecat_capability_reports_optional_voice_feature_modules(monkeypatch):
    present_modules = {
        *pipecat_adapter.CORE_PIPECAT_MODULES,
        pipecat_adapter.WEBSOCKET_PIPECAT_MODULE,
        pipecat_adapter.OPENAI_STT_PIPECAT_MODULE,
        "websockets",
    }
    monkeypatch.setattr(
        pipecat_adapter.importlib.util,
        "find_spec",
        lambda name: object() if name in present_modules else None,
    )
    monkeypatch.setattr(
        pipecat_adapter,
        "import_pipecat_runtime",
        lambda require_websocket=False: fake_runtime(websocket=require_websocket),
    )

    capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)

    assert capability.available is True
    assert capability.core_available is True
    assert capability.websocket_available is True
    assert capability.stt_available is True
    assert capability.vad_available is False
    assert capability.tts_available is False
    assert pipecat_adapter.SILERO_VAD_PIPECAT_MODULE in capability.optional_missing_modules
    assert "onnxruntime" in capability.optional_missing_modules
    assert "openai" in capability.optional_missing_modules


def test_pipecat_capability_preserves_core_when_websocket_extra_import_fails(monkeypatch):
    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())

    def import_runtime(*, require_websocket: bool = False):
        raise ImportError("Pipecat websocket transport is unavailable; install websocket extras")

    monkeypatch.setattr(pipecat_adapter, "import_pipecat_runtime", import_runtime)

    capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)

    assert capability.available is False
    assert capability.core_available is True
    assert capability.websocket_available is False
    assert capability.missing_modules == (pipecat_adapter.WEBSOCKET_PIPECAT_MODULE,)


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


@pytest.mark.asyncio
async def test_adapter_rejects_append_after_close_and_close_is_idempotent():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=fake_runtime(websocket=False))

    await adapter.start(voice_context(), realtime_config())
    assert adapter.handle is not None

    await adapter.close()
    await adapter.close()

    queued_frames = adapter.handle.worker.queued_frames
    assert sum(isinstance(frame, FakeEndFrame) for frame in queued_frames) == 1
    with pytest.raises(RuntimeError, match="closed"):
        await adapter.append_audio(RealtimeAudioChunk(data=b"late-pcm"))

    events = adapter.events()
    with pytest.raises(StopAsyncIteration):
        await events.__anext__()


@pytest.mark.asyncio
async def test_adapter_rejects_double_start_until_closed():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=fake_runtime(websocket=False))

    await adapter.start(voice_context(), realtime_config())
    with pytest.raises(RuntimeError, match="already started"):
        await adapter.start(voice_context(), realtime_config())

    await adapter.close()
    await adapter.start(voice_context(), realtime_config())
    assert adapter.handle is not None


def test_pipeline_handle_uses_pipecat_websocket_transport_as_pipeline_boundary():
    runtime = fake_runtime(websocket=True)
    custom_processor = object()
    websocket = object()
    config = RealtimePipelineConfig(
        provider="pipecat",
        metadata={"inputSampleRate": 16000, "outputSampleRate": 24000},
    )

    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=runtime,
        context=voice_context(),
        config=config,
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
    assert handle.worker.kwargs["params"].kwargs["audio_in_sample_rate"] == 16000
    assert handle.worker.kwargs["params"].kwargs["audio_out_sample_rate"] == 24000
    assert handle.worker.kwargs["params"].kwargs["start_metadata"]["provider"] == "pipecat"


@pytest.mark.asyncio
async def test_adapter_uses_configured_input_sample_rate_when_chunk_omits_it():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=fake_runtime(websocket=False))

    await adapter.start(
        voice_context(),
        RealtimePipelineConfig(provider="pipecat", metadata={"inputSampleRate": 24000}),
    )
    await asyncio.sleep(0)
    await adapter.append_audio(RealtimeAudioChunk(data=b"pcm"))

    assert adapter.handle is not None
    frame = adapter.handle.worker.queued_frames[0]
    assert frame.sample_rate == 24000

    await adapter.close()


def test_build_pipecat_voice_processors_uses_pipecat_stt_tts_and_turn_processors():
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="gpt-realtime-whisper",
        voice="alloy",
        instructions="Speak concisely.",
        metadata={
            "stt": {"provider": "openai"},
            "tts": "openai",
            "vad": "silero",
            "turnDetection": "pipecat",
            "openaiApiKey": "sk-test",
            "sttTurnDetection": "local",
            "ttsModel": "gpt-4o-mini-tts",
            "outputSampleRate": 24000,
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(fake_runtime(False), config)

    assert [type(processor) for processor in processors] == [
        FakeVADProcessor,
        FakeOpenAIRealtimeSTTService,
        FakeUserTurnProcessor,
        FakeOpenAITTSService,
    ]
    assert isinstance(processors[0].kwargs["vad_analyzer"], FakeSileroVADAnalyzer)
    assert processors[0].kwargs["vad_analyzer"].kwargs == {"sample_rate": None}
    assert processors[1].kwargs == {
        "api_key": "sk-test",
        "model": "gpt-realtime-whisper",
        "base_url": "wss://api.openai.com/v1/realtime",
        "language": None,
        "prompt": None,
        "turn_detection": False,
        "noise_reduction": None,
        "should_interrupt": True,
    }
    assert processors[3].kwargs["api_key"] == "sk-test"
    assert processors[3].kwargs["base_url"] is None
    assert processors[3].kwargs["model"] == "gpt-4o-mini-tts"
    assert processors[3].kwargs["voice"] == "alloy"
    assert processors[3].kwargs["instructions"] == "Speak concisely."
    assert processors[3].kwargs["sample_rate"] == 24000
    assert processors[3].kwargs["speed"] is None


def test_build_pipecat_voice_processors_supports_nested_feature_config():
    config = RealtimePipelineConfig(
        provider="pipecat",
        voice="fallback",
        metadata={
            "stt": {
                "provider": "openai",
                "model": "gpt-4o-mini-transcribe",
                "baseUrl": "wss://example.test/realtime",
                "language": "zh",
                "prompt": "Sales coaching vocabulary.",
                "turnDetection": "disabled",
                "noiseReduction": "near_field",
                "shouldInterrupt": False,
            },
            "tts": {
                "provider": "openai",
                "model": "gpt-4o-mini-tts",
                "voice": "verse",
                "instructions": "Warm and concise.",
                "sampleRate": 24000,
                "speed": 1.2,
            },
            "vad": {
                "provider": "silero",
                "sampleRate": 16000,
                "confidence": 0.75,
                "startSecs": 0.15,
                "stopSecs": 0.45,
                "minVolume": 0.2,
                "speechActivityPeriod": 0.1,
                "audioIdleTimeout": 0.8,
            },
            "turnDetection": {
                "provider": "pipecat",
                "userTurnStopTimeout": 3.0,
                "userIdleTimeout": 10.0,
            },
            "openaiApiKey": "sk-test",
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(fake_runtime(False), config)

    assert [type(processor) for processor in processors] == [
        FakeVADProcessor,
        FakeOpenAIRealtimeSTTService,
        FakeUserTurnProcessor,
        FakeOpenAITTSService,
    ]
    assert processors[0].kwargs["vad_analyzer"].kwargs["sample_rate"] == 16000
    assert isinstance(processors[0].kwargs["vad_analyzer"].kwargs["params"], FakeVADParams)
    assert processors[0].kwargs["vad_analyzer"].kwargs["params"].kwargs == {
        "confidence": 0.75,
        "start_secs": 0.15,
        "stop_secs": 0.45,
        "min_volume": 0.2,
    }
    assert processors[0].kwargs["speech_activity_period"] == 0.1
    assert processors[0].kwargs["audio_idle_timeout"] == 0.8
    assert processors[1].kwargs["model"] == "gpt-4o-mini-transcribe"
    assert processors[1].kwargs["base_url"] == "wss://example.test/realtime"
    assert processors[1].kwargs["language"] == "zh"
    assert processors[1].kwargs["prompt"] == "Sales coaching vocabulary."
    assert processors[1].kwargs["turn_detection"] is False
    assert processors[1].kwargs["noise_reduction"] == "near_field"
    assert processors[1].kwargs["should_interrupt"] is False
    assert processors[2].kwargs == {
        "user_turn_stop_timeout": 3.0,
        "user_idle_timeout": 10.0,
    }
    assert processors[3].kwargs["model"] == "gpt-4o-mini-tts"
    assert processors[3].kwargs["voice"] == "fallback"
    assert processors[3].kwargs["instructions"] == "Warm and concise."
    assert processors[3].kwargs["sample_rate"] == 24000
    assert processors[3].kwargs["speed"] == 1.2


def test_build_pipecat_voice_processors_supports_external_user_turn_strategy_metadata():
    config = RealtimePipelineConfig(
        provider="pipecat",
        metadata={
            "turnDetection": {
                "provider": "pipecat",
                "strategy": "external",
                "userTurnStopTimeout": 2.5,
                "userIdleTimeout": 8.0,
            },
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(fake_runtime(False), config)

    assert [type(processor) for processor in processors] == [FakeUserTurnProcessor]
    assert processors[0].kwargs["user_turn_stop_timeout"] == 2.5
    assert processors[0].kwargs["user_idle_timeout"] == 8.0
    assert isinstance(processors[0].kwargs["user_turn_strategies"], FakeExternalUserTurnStrategies)


def test_build_pipecat_voice_processors_supports_filter_incomplete_strategy_metadata():
    config = RealtimePipelineConfig(
        provider="pipecat",
        metadata={
            "turnDetection": {
                "provider": "pipecat",
                "userTurnStrategies": "filterIncomplete",
                "userTurnCompletionConfig": {
                    "instructions": "Decide whether the trainee finished.",
                    "incompleteShortTimeout": 1.5,
                    "incompleteLongTimeout": 9.0,
                    "incompleteShortPrompt": "Please continue.",
                    "incompleteLongPrompt": "Take your time.",
                },
            },
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(fake_runtime(False), config)

    strategies = processors[0].kwargs["user_turn_strategies"]
    assert isinstance(strategies, FakeFilterIncompleteUserTurnStrategies)
    completion_config = strategies.kwargs["config"]
    assert isinstance(completion_config, FakeUserTurnCompletionConfig)
    assert completion_config.kwargs == {
        "instructions": "Decide whether the trainee finished.",
        "incomplete_short_timeout": 1.5,
        "incomplete_long_timeout": 9.0,
        "incomplete_short_prompt": "Please continue.",
        "incomplete_long_prompt": "Take your time.",
    }


def test_build_pipecat_voice_processors_rejects_local_and_server_vad_mix():
    with pytest.raises(ValueError, match="server-side turn detection"):
        pipecat_adapter.build_pipecat_voice_processors(
            fake_runtime(False),
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={
                    "stt": "openai",
                    "vad": "silero",
                    "sttTurnDetection": "server_vad",
                    "openaiApiKey": "sk-test",
                },
            ),
        )


def test_build_pipecat_voice_processors_validates_supported_options():
    with pytest.raises(ValueError, match="Unsupported Pipecat stt provider"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(provider="pipecat", metadata={"stt": "homegrown"})
        )

    with pytest.raises(ValueError, match="Silero VAD sample rate"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"vad": {"provider": "silero", "sampleRate": 44100}},
            )
        )

    with pytest.raises(ValueError, match="OpenAI TTS speed"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"tts": {"provider": "openai", "speed": 5.0}},
            )
        )

    with pytest.raises(ValueError, match="Unsupported Pipecat user turn strategy"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"turnDetection": {"provider": "pipecat", "strategy": "homegrown"}},
            )
        )


def test_build_pipecat_voice_processors_reports_missing_optional_service():
    runtime = fake_runtime(False)
    runtime = pipecat_adapter.PipecatRuntime(
        **{**runtime.__dict__, "OpenAIRealtimeSTTService": None}
    )

    with pytest.raises(RuntimeError, match="OpenAI realtime STT"):
        pipecat_adapter.build_pipecat_voice_processors(
            runtime,
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"stt": "openai", "openaiApiKey": "sk-test"},
            ),
        )


def test_build_pipecat_voice_processors_uses_settings_key_without_metadata(monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", "sk-settings-realtime")

    processors = pipecat_adapter.build_pipecat_voice_processors(
        fake_runtime(False),
        RealtimePipelineConfig(
            provider="pipecat",
            metadata={
                "stt": {"provider": "openai", "turnDetection": "disabled"},
                "tts": {"provider": "openai"},
            },
        ),
    )

    assert processors[0].kwargs["api_key"] == "sk-settings-realtime"
    assert processors[1].kwargs["api_key"] == "sk-settings-realtime"


def test_pipecat_pipeline_capability_declares_voice_boundary(monkeypatch):
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: pipecat_adapter.PipecatCapability(
            available=True,
            core_available=True,
            websocket_available=require_websocket,
            stt_available=True,
            tts_available=False,
            vad_available=False,
            turn_detection_available=True,
            optional_missing_modules=("pipecat.services.openai.tts",),
        ),
    )

    capability = pipecat_adapter.pipecat_pipeline_capability(
        runtime=fake_runtime(False),
        websocket=object(),
        config=RealtimePipelineConfig(
            provider="pipecat",
            metadata={
                "stt": "openai",
                "tts": "openai",
                "vad": "silero",
                "turnDetection": "pipecat",
            },
        ),
    )

    assert capability.provider == "pipecat"
    assert capability.media_transport == "pipecat.websocket"
    assert capability.stt == "openai"
    assert capability.tts == "openai"
    assert capability.vad == "silero"
    assert capability.turn_detection == "pipecat"
    assert capability.missing_features == ("tts:openai", "vad:silero")
    assert capability.metadata["coreAvailable"] is True
    assert capability.metadata["websocketAvailable"] is True
    assert capability.metadata["sttAvailable"] is True
    assert capability.metadata["ttsAvailable"] is False
    assert capability.metadata["vadAvailable"] is False
    assert capability.metadata["turnDetectionAvailable"] is True
    assert capability.metadata["requestedFeatures"] == {
        "stt": "openai",
        "tts": "openai",
        "vad": "silero",
        "turnDetection": "pipecat",
    }


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
    assert event["sender_id"] == "user"
    assert processor.pushed[0][0].text == "final user turn"


@pytest.mark.asyncio
async def test_talkwise_event_processor_maps_interim_transcription_to_delta_event():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeInterimTranscriptionFrame(
            text="partial user turn",
            user_id="user",
            timestamp="2026-07-16T00:00:00Z",
            language="en",
            pts=42,
            metadata={"sequence": 1},
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["type"] == "transcript.delta"
    assert event["text"] == "partial user turn"
    assert event["delta"] == "partial user turn"
    assert event["source"] == "pipecat"
    assert event["sender_id"] == "user"
    assert event["language"] == "en"
    assert event["metadata"]["sequence"] == 1
    assert event["metadata"]["pipecatFrame"] == {
        "frameId": 303,
        "frameName": "FakeInterimTranscriptionFrame",
        "pts": 42,
    }
    assert processor.pushed[0][0].text == "partial user turn"


@pytest.mark.asyncio
async def test_talkwise_event_processor_preserves_safe_frame_metadata():
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
            language="en",
            pts=123456,
            metadata={
                "trainingProfile": "live_coach",
                "translation": {"source": "zh-CN", "target": "en-US"},
                "sequence": 3,
                "unsupported": object(),
            },
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["language"] == "en"
    assert event["metadata"]["trainingProfile"] == "live_coach"
    assert event["metadata"]["translation"] == {"source": "zh-CN", "target": "en-US"}
    assert event["metadata"]["sequence"] == 3
    assert "unsupported" not in event["metadata"]
    assert event["metadata"]["pipecatFrame"] == {
        "frameId": 101,
        "frameName": "FakeTranscriptionFrame",
        "pts": 123456,
    }


@pytest.mark.asyncio
async def test_talkwise_event_processor_preserves_assistant_frame_metadata():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeLLMContextAssistantTurnFrame(
            text="assistant final turn",
            timestamp="2026-07-16T00:00:01Z",
            metadata={"responseId": "response-pipecat-1"},
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["type"] == "response.audio_transcript.done"
    assert event["text"] == "assistant final turn"
    assert event["metadata"]["responseId"] == "response-pipecat-1"
    assert event["metadata"]["pipecatFrame"]["frameName"] == "FakeLLMContextAssistantTurnFrame"


@pytest.mark.asyncio
async def test_talkwise_event_processor_preserves_config_talkwise_metadata():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=RealtimePipelineConfig(
            provider="pipecat",
            metadata={
                "talkwise": {
                    "trainingSessionId": "training-1",
                    "roomId": 7,
                    "unsafe": object(),
                }
            },
        ),
    )

    await processor.process_frame(
        FakeTranscriptionFrame(
            text="final user turn",
            user_id="user",
            timestamp="2026-07-16T00:00:00Z",
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["metadata"]["talkwise"] == {
        "trainingSessionId": "training-1",
        "roomId": 7,
    }


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
    assert "interim transcript frame mirroring" in snapshot["talkwiseResponsibilities"]
    assert "pipecat.frames.frames.InterimTranscriptionFrame" in snapshot["frameEntrypoints"]
    assert "pipecat.audio.vad.silero.SileroVADAnalyzer" == snapshot["vadEntrypoint"]
    assert (
        "pipecat.processors.audio.vad_processor.VADProcessor"
        == snapshot["vadProcessorEntrypoint"]
    )
    assert "pipecat.services.openai.stt.OpenAIRealtimeSTTService" == snapshot["sttEntrypoint"]
    assert "pipecat.services.openai.tts.OpenAITTSService" == snapshot["ttsEntrypoint"]
    assert (
        "pipecat.turns.user_turn_strategies.ExternalUserTurnStrategies"
        in snapshot["turnStrategyEntrypoints"]
    )
