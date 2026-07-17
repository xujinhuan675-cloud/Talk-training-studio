import asyncio
import base64
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from application.ports.realtime import (
    REALTIME_RUNTIME_PIPECAT,
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


@dataclass
class FakeOutputAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 404
    name: str = "FakeOutputAudioRawFrame"
    pts: int | None = None


@dataclass
class FakeTTSAudioRawFrame(FakeOutputAudioRawFrame):
    context_id: str | None = None
    name: str = "FakeTTSAudioRawFrame"


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
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

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
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeOpenAILLMService:
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeLLMContext:
    def __init__(self, messages=None, **kwargs):
        self.messages = messages or []
        self.kwargs = kwargs


class FakeLLMUserAggregatorParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeLLMAssistantAggregatorParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeLLMUserAggregator:
    def __init__(self, context, params):
        self.context = context
        self.params = params


class FakeLLMAssistantAggregator:
    def __init__(self, context, params):
        self.context = context
        self.params = params


class FakeLLMContextAggregatorPair:
    def __init__(
        self,
        context,
        *,
        user_params=None,
        assistant_params=None,
        realtime_service_mode=None,
    ):
        self.context = context
        self.user_params = user_params
        self.assistant_params = assistant_params
        self.realtime_service_mode = realtime_service_mode
        self.user_aggregator = FakeLLMUserAggregator(context, user_params)
        self.assistant_aggregator = FakeLLMAssistantAggregator(context, assistant_params)

    def __iter__(self):
        return iter((self.user_aggregator, self.assistant_aggregator))


class FakeUserTurnProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeUserTurnStrategies:
    pass


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
        TTSAudioRawFrame=FakeTTSAudioRawFrame,
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
        OpenAILLMService=FakeOpenAILLMService,
        LLMContext=FakeLLMContext,
        LLMContextAggregatorPair=FakeLLMContextAggregatorPair,
        LLMUserAggregatorParams=FakeLLMUserAggregatorParams,
        LLMAssistantAggregatorParams=FakeLLMAssistantAggregatorParams,
        UserTurnProcessor=FakeUserTurnProcessor,
        UserTurnStrategies=FakeUserTurnStrategies,
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
        "_missing_required_pipecat_entries",
        lambda require_websocket=False: (),
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


def test_pipecat_capability_uses_runtime_symbols_for_optional_voice_features(monkeypatch):
    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        pipecat_adapter,
        "_missing_required_pipecat_entries",
        lambda require_websocket=False: (),
    )
    runtime = pipecat_adapter.PipecatRuntime(
        **{
            **fake_runtime(websocket=True).__dict__,
            "VADProcessor": None,
            "OpenAIRealtimeSTTService": None,
            "UserTurnProcessor": None,
        }
    )
    monkeypatch.setattr(
        pipecat_adapter,
        "import_pipecat_runtime",
        lambda require_websocket=False: runtime,
    )

    capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)

    assert capability.available is True
    assert capability.core_available is True
    assert capability.websocket_available is True
    assert capability.vad_available is False
    assert capability.stt_available is False
    assert capability.tts_available is True
    assert capability.turn_detection_available is False
    assert (
        "pipecat.processors.audio.vad_processor.VADProcessor" in capability.optional_missing_modules
    )
    assert (
        "pipecat.services.openai.stt.OpenAIRealtimeSTTService"
        in capability.optional_missing_modules
    )
    assert (
        "pipecat.turns.user_turn_processor.UserTurnProcessor" in capability.optional_missing_modules
    )


def test_pipecat_capability_requires_service_settings_symbols(monkeypatch):
    class FakeOpenAIRealtimeSTTServiceWithoutSettings:
        pass

    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        pipecat_adapter,
        "_missing_required_pipecat_entries",
        lambda require_websocket=False: (),
    )
    runtime = pipecat_adapter.PipecatRuntime(
        **{
            **fake_runtime(websocket=True).__dict__,
            "OpenAIRealtimeSTTService": FakeOpenAIRealtimeSTTServiceWithoutSettings,
        }
    )
    monkeypatch.setattr(
        pipecat_adapter,
        "import_pipecat_runtime",
        lambda require_websocket=False: runtime,
    )

    capability = pipecat_adapter.get_pipecat_capability()

    assert capability.stt_available is False
    assert (
        "pipecat.services.openai.stt.OpenAIRealtimeSTTService.Settings"
        in capability.optional_missing_modules
    )


def test_pipecat_capability_preserves_core_when_websocket_extra_import_fails(monkeypatch):
    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        pipecat_adapter,
        "_missing_required_pipecat_entries",
        lambda require_websocket=False: (),
    )

    def import_runtime(*, require_websocket: bool = False):
        raise ImportError("Pipecat websocket transport is unavailable; install websocket extras")

    monkeypatch.setattr(pipecat_adapter, "import_pipecat_runtime", import_runtime)

    capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)

    assert capability.available is False
    assert capability.core_available is True
    assert capability.websocket_available is False
    assert capability.missing_modules == (pipecat_adapter.WEBSOCKET_PIPECAT_MODULE,)


def test_pipecat_capability_reports_missing_core_symbol(monkeypatch):
    modules = {
        "pipecat.pipeline.pipeline": SimpleNamespace(Pipeline=object),
        "pipecat.pipeline.worker": SimpleNamespace(PipelineParams=object),
        "pipecat.workers.base_worker": SimpleNamespace(WorkerParams=object),
        "pipecat.workers.runner": SimpleNamespace(WorkerRunner=object),
        "pipecat.frames.frames": SimpleNamespace(
            InputAudioRawFrame=object,
            EndFrame=object,
            TextFrame=object,
            TranscriptionFrame=object,
            LLMContextAssistantTurnFrame=object,
        ),
        "pipecat.processors.frame_processor": SimpleNamespace(
            FrameProcessor=object,
            FrameDirection=object,
        ),
    }

    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(
        pipecat_adapter.importlib,
        "import_module",
        lambda name: modules[name],
    )

    capability = pipecat_adapter.get_pipecat_capability()

    assert capability.available is False
    assert capability.core_available is False
    assert capability.websocket_available is True
    assert capability.missing_modules == (
        "pipecat.pipeline.worker.PipelineWorker",
        "pipecat.frames.frames.TTSAudioRawFrame",
    )
    assert "Missing Pipecat runtime symbol" in capability.error


def test_pipecat_capability_reports_core_symbol_import_exception(monkeypatch):
    def import_module(name):
        if name == "pipecat.frames.frames":
            raise RuntimeError("bad pipecat frame import")
        return SimpleNamespace(
            **{symbol: object for symbol in pipecat_adapter.CORE_PIPECAT_SYMBOLS[name]}
        )

    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(pipecat_adapter.importlib, "import_module", import_module)

    capability = pipecat_adapter.get_pipecat_capability()

    assert capability.available is False
    assert capability.core_available is False
    assert capability.websocket_available is False
    assert capability.missing_modules == ()
    assert "Pipecat module import failed while checking pipecat.frames.frames" in capability.error
    assert "bad pipecat frame import" in capability.error


def test_pipecat_realtime_readiness_reports_structured_blockers_without_secrets():
    capability = pipecat_adapter.PipecatCapability(
        available=True,
        core_available=True,
        websocket_available=True,
        stt_available=False,
        tts_available=True,
        llm_available=False,
        vad_available=False,
        turn_detection_available=False,
        optional_missing_modules=(
            pipecat_adapter.OPENAI_STT_PIPECAT_MODULE,
            pipecat_adapter.OPENAI_LLM_PIPECAT_MODULE,
            pipecat_adapter.SILERO_VAD_PIPECAT_MODULE,
            pipecat_adapter.VAD_PROCESSOR_PIPECAT_MODULE,
            pipecat_adapter.USER_TURN_PROCESSOR_PIPECAT_MODULE,
            "openaiApiKey=sk-secret-should-not-appear",
        ),
        error="Pipecat saw api_key=sk-secret-should-not-appear",
    )

    readiness = pipecat_adapter.pipecat_realtime_readiness(
        capability,
        openai_api_key_available=False,
    ).to_dict()

    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert readiness["required"]["features"] == {
        "stt": "openai",
        "tts": "openai",
        "llm": "openai",
        "vad": "silero",
        "turnDetection": "pipecat",
    }
    errors = readiness["blockingReasons"]
    assert [error["code"] for error in errors] == [
        "PIPECAT_FEATURE_UNAVAILABLE",
        "PIPECAT_FEATURE_UNAVAILABLE",
        "PIPECAT_FEATURE_UNAVAILABLE",
        "PIPECAT_FEATURE_UNAVAILABLE",
        "MISSING_OPENAI_API_KEY",
    ]
    by_feature = {error.get("feature"): error for error in errors}
    assert by_feature["stt:openai"]["modules"] == [
        pipecat_adapter.OPENAI_STT_PIPECAT_MODULE
    ]
    assert by_feature["llm:openai"]["modules"] == [
        pipecat_adapter.OPENAI_LLM_PIPECAT_MODULE
    ]
    assert by_feature["vad:silero"]["modules"] == [
        pipecat_adapter.SILERO_VAD_PIPECAT_MODULE,
        pipecat_adapter.VAD_PROCESSOR_PIPECAT_MODULE,
    ]
    assert by_feature["turnDetection:pipecat"]["modules"] == [
        pipecat_adapter.USER_TURN_PROCESSOR_PIPECAT_MODULE
    ]
    assert errors[-1]["missingEnv"] == [
        "REALTIME_OPENAI_API_KEY",
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    ]
    assert "secret-should-not-appear" not in json.dumps(readiness)


def test_pipecat_realtime_readiness_reports_missing_openai_runtime_settings():
    capability = pipecat_adapter.PipecatCapability(
        available=True,
        core_available=True,
        websocket_available=True,
        vad_available=True,
        stt_available=True,
        tts_available=True,
        llm_available=True,
        turn_detection_available=True,
    )

    readiness = pipecat_adapter.pipecat_realtime_readiness(
        capability,
        openai_api_key_available=True,
        openai_model=None,
        openai_voice=None,
        input_audio_format=None,
    ).to_dict()

    assert readiness["ready"] is False
    assert readiness["status"] == "blocked"
    assert readiness["required"]["env"] == [
        "REALTIME_OPENAI_API_KEY",
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    ]
    assert [error["code"] for error in readiness["blockingReasons"]] == [
        "MISSING_OPENAI_REALTIME_MODEL",
        "MISSING_OPENAI_REALTIME_VOICE",
        "MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
    ]
    assert [error["missingEnv"] for error in readiness["blockingReasons"]] == [
        ["REALTIME_OPENAI_MODEL"],
        ["REALTIME_OPENAI_VOICE"],
        ["REALTIME_OPENAI_INPUT_AUDIO_FORMAT"],
    ]


def test_pipecat_realtime_capability_response_is_public_safe(monkeypatch):
    capability = pipecat_adapter.PipecatCapability(
        available=True,
        core_available=True,
        websocket_available=True,
        vad_available=True,
        stt_available=True,
        tts_available=True,
        llm_available=True,
        turn_detection_available=True,
    )
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: capability,
    )
    monkeypatch.setattr(
        pipecat_adapter,
        "pipecat_source_snapshot",
        lambda: {
            "checkedAt": "test",
            "coreEntrypoints": ("pipecat.pipeline.pipeline.Pipeline",),
            "apiKey": "sk-secret-should-not-appear",
            "nested": {
                "Authorization": "Bearer secret-should-not-appear",
                "label": "safe",
            },
        },
    )

    response = pipecat_adapter.pipecat_realtime_capability_response(
        openai_api_key_available=True,
    )

    assert response["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert response["provider"] == "pipecat"
    assert response["readyForCall"] is True
    assert response["readiness"]["status"] == "ready"
    assert response["errors"] == []
    assert response["sourceSnapshot"]["coreEntrypoints"] == [
        "pipecat.pipeline.pipeline.Pipeline"
    ]
    assert response["sourceSnapshot"]["nested"] == {"label": "safe"}
    serialized = json.dumps(response)
    assert "secret-should-not-appear" not in serialized
    assert "apiKey" not in serialized


def test_pipecat_capability_preserves_core_when_websocket_symbol_import_fails(monkeypatch):
    def import_module(name):
        if name == pipecat_adapter.WEBSOCKET_PIPECAT_MODULE:
            raise ImportError("websocket dependency failed")
        return SimpleNamespace(
            **{symbol: object for symbol in pipecat_adapter.CORE_PIPECAT_SYMBOLS[name]}
        )

    monkeypatch.setattr(pipecat_adapter.importlib.util, "find_spec", lambda name: object())
    monkeypatch.setattr(pipecat_adapter.importlib, "import_module", import_module)

    capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)

    assert capability.available is False
    assert capability.core_available is True
    assert capability.websocket_available is False
    assert capability.missing_modules == (pipecat_adapter.WEBSOCKET_PIPECAT_MODULE,)
    assert "Missing Pipecat runtime symbol" in capability.error


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
    context = TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-1", room_id=7),
        task_goal="Practice a discovery call",
        rubric={"clarity": 1},
        recent_turns=(
            {
                "speaker": "user",
                "text": "Can we discuss renewal risk?",
                "metadata": {"message_id": 1},
            },
        ),
        metadata={
            "personaIds": ["buyer"],
            "scenarioId": 9,
            "scenarioTemplateId": "enterprise-renewal",
            "category": "sales",
            "liveGuidance": {"enabled": True},
        },
    )
    config = RealtimePipelineConfig(
        provider="pipecat",
        metadata={"inputSampleRate": 16000, "outputSampleRate": 24000},
    )

    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=runtime,
        context=context,
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
    start_metadata = handle.worker.kwargs["params"].kwargs["start_metadata"]
    assert start_metadata["provider"] == "pipecat"
    assert start_metadata["personaIds"] == ["buyer"]
    assert start_metadata["scenarioId"] == 9
    assert start_metadata["scenarioTemplateId"] == "enterprise-renewal"
    assert start_metadata["category"] == "sales"
    assert start_metadata["liveGuidance"] == {"enabled": True}
    assert start_metadata["recentTurns"] == [
        {
            "speaker": "user",
            "text": "Can we discuss renewal risk?",
            "metadata": {"message_id": 1},
        }
    ]


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
    assert processors[1].kwargs["api_key"] == "sk-test"
    assert processors[1].kwargs["base_url"] == "wss://api.openai.com/v1/realtime"
    assert processors[1].kwargs["turn_detection"] is False
    assert processors[1].kwargs["should_interrupt"] is True
    assert processors[1].kwargs["settings"].kwargs == {"model": "gpt-realtime-whisper"}
    assert processors[3].kwargs["api_key"] == "sk-test"
    assert processors[3].kwargs["base_url"] is None
    assert processors[3].kwargs["sample_rate"] == 24000
    assert processors[3].kwargs["settings"].kwargs == {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "instructions": "Speak concisely.",
    }


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
    assert processors[1].kwargs["base_url"] == "wss://example.test/realtime"
    assert processors[1].kwargs["turn_detection"] is False
    assert processors[1].kwargs["should_interrupt"] is False
    assert processors[1].kwargs["settings"].kwargs == {
        "model": "gpt-4o-mini-transcribe",
        "language": "zh",
        "prompt": "Sales coaching vocabulary.",
        "noise_reduction": "near_field",
    }
    assert processors[2].kwargs == {
        "user_turn_stop_timeout": 3.0,
        "user_idle_timeout": 10.0,
    }
    assert processors[3].kwargs["sample_rate"] == 24000
    assert processors[3].kwargs["settings"].kwargs == {
        "model": "gpt-4o-mini-tts",
        "voice": "fallback",
        "instructions": "Warm and concise.",
        "speed": 1.2,
    }


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

    with pytest.raises(ValueError, match="Unsupported Pipecat llm provider"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(provider="pipecat", metadata={"llm": "homegrown"})
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

    with pytest.raises(ValueError, match="OpenAI realtime STT noise reduction"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"stt": {"provider": "openai", "noiseReduction": "studio"}},
            )
        )

    with pytest.raises(ValueError, match="OpenAI LLM temperature"):
        pipecat_adapter.validate_pipecat_voice_config(
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"llm": {"provider": "openai", "temperature": 3}},
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

    with pytest.raises(
        pipecat_adapter.PipecatRealtimePipelineError,
        match="OpenAI realtime STT",
    ) as exc_info:
        pipecat_adapter.build_pipecat_voice_processors(
            runtime,
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"stt": "openai", "openaiApiKey": "sk-test"},
            ),
        )

    error = exc_info.value.to_realtime_error()
    assert error["code"] == "PIPECAT_FEATURE_UNAVAILABLE"
    assert error["phase"] == "voice_processor_config"
    assert error["feature"] == "stt:openai"
    assert error["modules"] == (pipecat_adapter.OPENAI_STT_PIPECAT_MODULE,)


def test_build_pipecat_voice_processors_reports_missing_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.delenv("REALTIME_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(
        pipecat_adapter.PipecatRealtimePipelineError,
        match="OpenAI API key is required",
    ) as exc_info:
        pipecat_adapter.build_pipecat_voice_processors(
            fake_runtime(False),
            RealtimePipelineConfig(
                provider="pipecat",
                metadata={"stt": {"provider": "openai", "turnDetection": "disabled"}},
            ),
        )

    error = exc_info.value.to_realtime_error()
    assert error["code"] == "MISSING_OPENAI_API_KEY"
    assert error["phase"] == "configuration"
    assert error["feature"] == "stt:openai"
    assert error["missingEnv"] == (
        "REALTIME_OPENAI_API_KEY",
        "LLM__API_KEY",
        "OPENAI_API_KEY",
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


def test_build_pipecat_voice_processors_adds_native_llm_context_chain():
    context = TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-1", room_id=7),
        task_goal="Practice enterprise renewal discovery.",
        rubric={"clarity": 1, "brevity": 2},
        recent_turns=(
            {"speaker": "user", "text": "Can we discuss renewal risk?"},
            {"speaker": "assistant", "text": "Yes, what risk is most urgent?"},
        ),
        metadata={
            "personaIds": ["buyer"],
            "scenarioId": "renewal-1",
            "scenarioTemplateId": "enterprise-renewal",
            "category": "sales",
            "dispatcher": {"selectedPersonaId": "buyer"},
            "liveGuidance": {"enabled": True},
            "growthReport": {"internal": "not prompt material"},
        },
    )
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="fallback-realtime-model",
        voice="alloy",
        instructions="Stay in role as the counterpart.",
        metadata={
            "stt": {"provider": "openai", "turnDetection": "disabled"},
            "llm": {
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "baseUrl": "https://llm.example.test/v1",
                "temperature": 0.2,
                "maxCompletionTokens": 120,
            },
            "tts": "openai",
            "vad": "silero",
            "turnDetection": {
                "provider": "pipecat",
                "userTurnStopTimeout": 2.5,
                "userIdleTimeout": 8.0,
                "filterIncompleteUserTurns": True,
            },
            "context": {"provider": "pipecat", "realtimeServiceMode": False},
            "openaiApiKey": "sk-test",
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(
        fake_runtime(False),
        config,
        context=context,
    )

    assert [type(processor) for processor in processors] == [
        FakeVADProcessor,
        FakeOpenAIRealtimeSTTService,
        FakeLLMUserAggregator,
        FakeOpenAILLMService,
        FakeOpenAITTSService,
        FakeLLMAssistantAggregator,
    ]
    assert not any(isinstance(processor, FakeUserTurnProcessor) for processor in processors)
    user_aggregator = processors[2]
    assert user_aggregator.params.kwargs["user_turn_stop_timeout"] == 2.5
    assert user_aggregator.params.kwargs["user_idle_timeout"] == 8.0
    assert user_aggregator.params.kwargs["filter_incomplete_user_turns"] is True
    assert user_aggregator.context.messages == [
        {"role": "user", "content": "Can we discuss renewal risk?"},
        {"role": "assistant", "content": "Yes, what risk is most urgent?"},
    ]

    llm = processors[3]
    assert llm.kwargs["api_key"] == "sk-test"
    assert llm.kwargs["base_url"] == "https://llm.example.test/v1"
    llm_settings = llm.kwargs["settings"].kwargs
    assert llm_settings["model"] == "gpt-4.1-mini"
    assert llm_settings["temperature"] == 0.2
    assert llm_settings["max_completion_tokens"] == 120
    assert "Stay in role as the counterpart." in llm_settings["system_instruction"]
    assert "Practice enterprise renewal discovery." in llm_settings["system_instruction"]
    assert "Persona IDs" in llm_settings["system_instruction"]
    assert "Scenario ID" in llm_settings["system_instruction"]
    assert "Scenario template ID" in llm_settings["system_instruction"]
    assert "Scenario category" in llm_settings["system_instruction"]
    assert "Live guidance" in llm_settings["system_instruction"]
    assert "not prompt material" not in llm_settings["system_instruction"]


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
            llm_available=True,
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
            model="gpt-realtime",
            voice="marin",
            input_audio_format="pcm16",
            metadata={
                "stt": "openai",
                "tts": "openai",
                "vad": "silero",
                "turnDetection": "pipecat",
                "openaiApiKey": "sk-secret-should-not-appear",
            },
        ),
    )

    assert capability.provider == "pipecat"
    assert capability.runtime == REALTIME_RUNTIME_PIPECAT
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
    assert capability.metadata["llmAvailable"] is True
    assert capability.metadata["vadAvailable"] is False
    assert capability.metadata["turnDetectionAvailable"] is True
    assert capability.metadata["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert capability.metadata["requestedFeatures"] == {
        "stt": "openai",
        "tts": "openai",
        "llm": None,
        "vad": "silero",
        "turnDetection": "pipecat",
    }
    assert capability.ready_for_call is False
    assert capability.readiness_payload()["status"] == "blocked"
    assert capability.readiness_payload()["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert [error["feature"] for error in capability.errors] == [
        "tts:openai",
        "vad:silero",
    ]
    assert "secret-should-not-appear" not in json.dumps(
        {
            "errors": capability.errors,
            "readiness": capability.readiness_payload(),
            "metadata": capability.metadata,
        },
        default=str,
    )


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
    assert event["runtime"] == REALTIME_RUNTIME_PIPECAT
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
    assert event["runtime"] == REALTIME_RUNTIME_PIPECAT
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
async def test_talkwise_event_processor_strips_secret_frame_metadata():
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
                    "apiKey": "sk-secret-should-not-appear",
                    "safe": "kept",
                }
            },
        ),
    )

    await processor.process_frame(
        FakeTranscriptionFrame(
            text="final user turn",
            user_id="user",
            timestamp="2026-07-16T00:00:00Z",
            metadata={
                "openaiApiKey": "sk-secret-should-not-appear",
                "safe": "kept",
                "nested": {
                    "Authorization": "Bearer secret-should-not-appear",
                    "label": "safe",
                },
            },
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()

    assert event["metadata"]["safe"] == "kept"
    assert event["metadata"]["nested"] == {"label": "safe"}
    assert event["metadata"]["talkwise"] == {
        "trainingSessionId": "training-1",
        "safe": "kept",
    }
    serialized = json.dumps(event)
    assert "secret-should-not-appear" not in serialized
    assert "openaiApiKey" not in serialized
    assert "Authorization" not in serialized


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
    assert event["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert event["text"] == "assistant final turn"
    assert event["metadata"]["responseId"] == "response-pipecat-1"
    assert event["metadata"]["pipecatFrame"]["frameName"] == "FakeLLMContextAssistantTurnFrame"


@pytest.mark.asyncio
async def test_talkwise_event_processor_maps_tts_audio_frame_to_audio_output_event():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=RealtimePipelineConfig(
            provider="pipecat",
            output_audio_format="pcm16",
            metadata={"talkwise": {"trainingSessionId": "training-1", "roomId": 7}},
        ),
    )
    audio = b"\x01\x02\x03\x04"

    await processor.process_frame(
        FakeTTSAudioRawFrame(
            audio=audio,
            sample_rate=24000,
            num_channels=1,
            context_id="tts-context-1",
            pts=1234,
            metadata={"voice": "alloy", "unsafe": object()},
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    payload = event["payload"]
    encoded = base64.b64encode(audio).decode("ascii")
    assert event["type"] == "audio.output"
    assert event["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert event["source"] == "pipecat"
    assert event["audio"] == encoded
    assert event["mimeType"] == "audio/pcm"
    assert event["sampleRate"] == 24000
    assert event["channels"] == 1
    assert event["sequence"] == 1
    assert event["bytes"] == len(audio)
    assert event["contextId"] == "tts-context-1"
    assert payload["audio"] == encoded
    assert payload["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert payload["provider"] == "pipecat"
    assert payload["encoding"] == "base64"
    assert payload["mimeType"] == "audio/pcm"
    assert payload["sampleRate"] == 24000
    assert payload["channels"] == 1
    assert payload["sequence"] == 1
    assert payload["bytes"] == len(audio)
    assert payload["contextId"] == "tts-context-1"
    assert payload["metadata"]["voice"] == "alloy"
    assert payload["metadata"]["talkwise"] == {"trainingSessionId": "training-1", "roomId": 7}
    assert payload["metadata"]["pipecatFrame"] == {
        "frameId": 404,
        "frameName": "FakeTTSAudioRawFrame",
        "pts": 1234,
    }
    assert "unsafe" not in payload["metadata"]
    assert processor.pushed[0][0].audio == audio


@pytest.mark.asyncio
async def test_talkwise_event_processor_uses_frame_audio_sequence_when_present():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeTTSAudioRawFrame(
            audio=b"pcm",
            sample_rate=16000,
            num_channels=2,
            metadata={"sequence": 42, "mimeType": "audio/l16"},
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["sequence"] == 42
    assert event["payload"]["sequence"] == 42
    assert event["payload"]["channels"] == 2
    assert event["payload"]["mimeType"] == "audio/l16"


@pytest.mark.asyncio
async def test_talkwise_event_processor_does_not_mirror_generic_output_audio_frame():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeOutputAudioRawFrame(audio=b"pcm", sample_rate=16000, num_channels=1),
        FakeFrameDirection.DOWNSTREAM,
    )

    assert queue.empty()
    assert processor.pushed[0][0].audio == b"pcm"


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

    assert snapshot["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert "pipecat.pipeline.pipeline.Pipeline" in snapshot["coreEntrypoints"]
    assert "pipecat.pipeline.worker.PipelineParams" in snapshot["coreEntrypoints"]
    assert "pipecat.workers.base_worker.WorkerParams" in snapshot["coreEntrypoints"]
    assert "pipecat.processors.frame_processor.FrameProcessor" in snapshot["coreEntrypoints"]
    assert (
        "pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport"
        == snapshot["websocketEntrypoint"]
    )
    assert (
        "RealtimeAudioChunk to InputAudioRawFrame adaptation"
        in snapshot["talkwiseResponsibilities"]
    )
    assert "interim transcript frame mirroring" in snapshot["talkwiseResponsibilities"]
    assert (
        "TrainingVoiceContext to LLMContext seed adaptation" in snapshot["talkwiseResponsibilities"]
    )
    assert (
        "Pipecat runtime to provider-neutral readiness adaptation"
        in snapshot["talkwiseResponsibilities"]
    )
    assert (
        "optional import and Pipecat symbol capability detection"
        in snapshot["talkwiseResponsibilities"]
    )
    assert "pipecat.frames.frames.InterimTranscriptionFrame" in snapshot["frameEntrypoints"]
    assert "pipecat.frames.frames.TTSAudioRawFrame" in snapshot["frameEntrypoints"]
    assert snapshot["audioFrameFields"]["pipecat.frames.frames.OutputAudioRawFrame"] == (
        "audio",
        "sample_rate",
        "num_channels",
        "num_frames",
    )
    assert snapshot["audioFrameFields"]["pipecat.frames.frames.TTSAudioRawFrame"] == (
        "context_id",
    )
    assert (
        "TTSAudioRawFrame to provider-neutral audio.output event mirroring"
        in snapshot["talkwiseResponsibilities"]
    )
    assert "pipecat.audio.vad.silero.SileroVADAnalyzer" == snapshot["vadEntrypoint"]
    assert (
        "pipecat.processors.audio.vad_processor.VADProcessor" == snapshot["vadProcessorEntrypoint"]
    )
    assert "pipecat.services.openai.stt.OpenAIRealtimeSTTService" == snapshot["sttEntrypoint"]
    assert (
        "pipecat.services.openai.stt.OpenAIRealtimeSTTService.Settings"
        == snapshot["sttSettingsEntrypoint"]
    )
    assert "pipecat.services.openai.tts.OpenAITTSService" == snapshot["ttsEntrypoint"]
    assert (
        "pipecat.services.openai.tts.OpenAITTSService.Settings"
        == snapshot["ttsSettingsEntrypoint"]
    )
    assert "pipecat.services.openai.llm.OpenAILLMService" == snapshot["llmEntrypoint"]
    assert (
        "pipecat.services.openai.llm.OpenAILLMService.Settings"
        == snapshot["llmSettingsEntrypoint"]
    )
    assert (
        "pipecat.processors.aggregators.llm_response_universal.LLMContextAggregatorPair"
        in snapshot["llmContextEntrypoints"]
    )
    assert (
        "pipecat.processors.aggregators.llm_response_universal.LLMUserAggregatorParams"
        in snapshot["llmContextEntrypoints"]
    )
    assert (
        "pipecat.turns.user_turn_strategies.ExternalUserTurnStrategies"
        in snapshot["turnStrategyEntrypoints"]
    )
    assert (
        "pipecat.turns.user_turn_completion_mixin.UserTurnCompletionConfig"
        in snapshot["turnStrategyEntrypoints"]
    )
