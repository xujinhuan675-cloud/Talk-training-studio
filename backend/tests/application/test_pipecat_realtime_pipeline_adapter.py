import asyncio
import base64
import json
from contextlib import suppress
from dataclasses import dataclass, field, replace
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
from infrastructure.external.pipecat.volcengine_doubao_services import (
    VolcengineDoubaoSTTService,
    VolcengineDoubaoTTSService,
)


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
class FakePipelineFlushFrame:
    event: asyncio.Event | None = None


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
class FakeInterruptionFrame:
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 501
    name: str = "FakeInterruptionFrame"
    pts: int | None = None


@dataclass
class FakeErrorFrame:
    error: str
    fatal: bool = False
    exception: Exception | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 509
    name: str = "FakeErrorFrame"
    pts: int | None = None


@dataclass
class FakeUserStartedSpeakingFrame:
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 502
    name: str = "FakeUserStartedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeUserStoppedSpeakingFrame:
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 503
    name: str = "FakeUserStoppedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeVADUserStartedSpeakingFrame:
    start_secs: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 504
    name: str = "FakeVADUserStartedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeVADUserStoppedSpeakingFrame:
    stop_secs: float = 0.0
    timestamp: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 505
    name: str = "FakeVADUserStoppedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeBotStartedSpeakingFrame:
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 506
    name: str = "FakeBotStartedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeBotStoppedSpeakingFrame:
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 507
    name: str = "FakeBotStoppedSpeakingFrame"
    pts: int | None = None


@dataclass
class FakeUserIdleTimeoutUpdateFrame:
    timeout: float
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 508
    name: str = "FakeUserIdleTimeoutUpdateFrame"
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


class FakeOpenAIRealtimeLLMService:
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeRealtimeConfigValue:
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
        self.event_handlers = {}

    def add_event_handler(self, event_name, handler):
        self.event_handlers.setdefault(event_name, []).append(handler)

    async def emit_event(self, event_name, *args):
        for handler in self.event_handlers.get(event_name, []):
            await handler(self, *args)


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


class FakeSpeechTimeoutUserTurnStopStrategy:
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
        self.flush_count = 0

    async def queue_frame(self, frame):
        self.queued_frames.append(frame)
        if isinstance(frame, FakePipelineFlushFrame):
            self.flushed = True
            self.flush_count += 1
            if frame.event is not None:
                frame.event.set()

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
        PipelineFlushFrame=FakePipelineFlushFrame,
        TextFrame=FakeTextFrame,
        TranscriptionFrame=FakeTranscriptionFrame,
        LLMContextAssistantTurnFrame=FakeLLMContextAssistantTurnFrame,
        TTSAudioRawFrame=FakeTTSAudioRawFrame,
        FrameProcessor=FakeFrameProcessor,
        FrameDirection=FakeFrameDirection,
        InterimTranscriptionFrame=FakeInterimTranscriptionFrame,
        InterruptionFrame=FakeInterruptionFrame,
        ErrorFrame=FakeErrorFrame,
        UserStartedSpeakingFrame=FakeUserStartedSpeakingFrame,
        UserStoppedSpeakingFrame=FakeUserStoppedSpeakingFrame,
        VADUserStartedSpeakingFrame=FakeVADUserStartedSpeakingFrame,
        VADUserStoppedSpeakingFrame=FakeVADUserStoppedSpeakingFrame,
        BotStartedSpeakingFrame=FakeBotStartedSpeakingFrame,
        BotStoppedSpeakingFrame=FakeBotStoppedSpeakingFrame,
        UserIdleTimeoutUpdateFrame=FakeUserIdleTimeoutUpdateFrame,
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
        SpeechTimeoutUserTurnStopStrategy=FakeSpeechTimeoutUserTurnStopStrategy,
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
        "MISSING_OPENAI_REALTIME_MODEL",
        "MISSING_OPENAI_REALTIME_VOICE",
        "MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
    ]
    by_feature = {error.get("feature"): error for error in errors}
    assert by_feature["stt:openai"]["modules"] == [pipecat_adapter.OPENAI_STT_PIPECAT_MODULE]
    assert by_feature["llm:openai"]["modules"] == [pipecat_adapter.OPENAI_LLM_PIPECAT_MODULE]
    assert by_feature["vad:silero"]["modules"] == [
        pipecat_adapter.SILERO_VAD_PIPECAT_MODULE,
        pipecat_adapter.VAD_PROCESSOR_PIPECAT_MODULE,
    ]
    assert by_feature["turnDetection:pipecat"]["modules"] == [
        pipecat_adapter.USER_TURN_PROCESSOR_PIPECAT_MODULE
    ]
    assert errors[4]["missingEnv"] == [
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    ]
    assert all("missingEnv" not in error for error in errors[5:])
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
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    ]
    assert [error["code"] for error in readiness["blockingReasons"]] == [
        "MISSING_OPENAI_REALTIME_MODEL",
        "MISSING_OPENAI_REALTIME_VOICE",
        "MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
    ]
    assert [error.get("missingEnv") for error in readiness["blockingReasons"]] == [
        None,
        None,
        None,
    ]


def test_pipecat_realtime_smoke_contract_blocks_production_until_browser_e2e():
    smoke = pipecat_adapter.pipecat_realtime_smoke_contract(
        ready_for_call=True,
        require_websocket=True,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
    )

    assert smoke["localRuntimeReady"] is True
    assert smoke["browserE2EVerified"] is False
    assert smoke["productionReady"] is False
    assert smoke["productionReadiness"] == {
        "readyForProduction": False,
        "status": "browser_e2e_verification_required",
        "localRuntimeReady": True,
        "browserAudioE2EVerified": False,
        "requiredVerifications": ["browser_audio_e2e"],
        "blockingReasons": [
            {
                "code": "BROWSER_AUDIO_E2E_NOT_VERIFIED",
                "message": (
                    "Browser microphone capture, websocket transport, audio output playback, "
                    "turn events, metrics, and provider errors need E2E verification before "
                    "production readiness"
                ),
                "phase": "browser_audio_e2e",
                "provider": "pipecat",
                "runtime": REALTIME_RUNTIME_PIPECAT,
                "requiredSignals": [
                    "microphone_permission_and_capture",
                    "websocket_audio_input",
                    "provider_neutral_audio_output_playback",
                    "turn_interruption_silence_events",
                    "realtime_metrics_and_error_taxonomy",
                ],
            }
        ],
    }
    assert smoke["readinessAssertions"]["readyForCallImpliesProductionReady"] is False
    assert smoke["eventOrder"]["assistantAudioThenTranscript"] == [
        "audio.output",
        "transcript.done",
        "transcript.persisted",
    ]
    coverage = smoke["contractCoverage"]
    assert coverage["browserAudioE2E"]["verified"] is False
    assert coverage["browserAudioE2E"]["requiredForProduction"] is True
    assert coverage["providerNeutralAudioOutput"]["eventType"] == "audio.output"
    assert coverage["metrics"]["metadataKey"] == "realtimeMetrics"
    assert coverage["turnInterruptionSilence"]["eventTypes"] == [
        "user_turn.started",
        "user_turn.stopped",
        "assistant_speaking.started",
        "assistant_speaking.stopped",
        "interrupted",
        "silence_timeout",
    ]
    assert smoke["errorTaxonomy"][0] == {
        "errorCategory": "authentication",
        "code": "REALTIME_PROVIDER_AUTHENTICATION",
        "retryable": False,
        "fatal": True,
    }


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
        openai_model="gpt-realtime",
        openai_voice="marin",
        input_audio_format="pcm16",
    )

    assert response["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert response["provider"] == "pipecat"
    assert response["readyForCall"] is True
    assert response["readiness"]["status"] == "ready"
    assert response["productionReady"] is False
    assert response["productionReadiness"]["status"] == "browser_e2e_verification_required"
    assert response["productionReadiness"]["blockingReasons"][0]["code"] == (
        "BROWSER_AUDIO_E2E_NOT_VERIFIED"
    )
    assert response["smoke"]["productionReady"] is False
    assert response["smoke"]["contractCoverage"]["browserAudioE2E"]["verified"] is False
    assert (
        response["smoke"]["contractCoverage"]["providerNeutralAudioOutput"]["eventType"]
        == "audio.output"
    )
    assert response["errors"] == []
    assert response["sourceSnapshot"]["coreEntrypoints"] == ["pipecat.pipeline.pipeline.Pipeline"]
    assert response["sourceSnapshot"]["nested"] == {"label": "safe"}
    serialized = json.dumps(response)
    assert "secret-should-not-appear" not in serialized
    assert "apiKey" not in serialized


def test_pipecat_realtime_capability_response_omits_snapshot_when_snapshot_fails(monkeypatch):
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

    def _raise_snapshot_failure():
        raise RuntimeError("Pipecat source snapshot failed")

    monkeypatch.setattr(pipecat_adapter, "pipecat_source_snapshot", _raise_snapshot_failure)

    response = pipecat_adapter.pipecat_realtime_capability_response(
        openai_api_key_available=True,
        openai_model="gpt-realtime",
        openai_voice="marin",
        input_audio_format="pcm16",
    )

    assert response["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert response["readyForCall"] is True
    assert response["errors"] == []
    assert "sourceSnapshot" not in response


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


def test_speech_to_speech_builder_selects_volcengine_pipecat_service(monkeypatch):
    from infrastructure.external.pipecat import volcengine_realtime_service

    sentinel = object()
    captured = {}

    def create_service(runtime, *, context, config):
        captured.update(runtime=runtime, context=context, config=config)
        return sentinel

    monkeypatch.setattr(
        volcengine_realtime_service,
        "create_volcengine_realtime_service",
        create_service,
    )
    runtime = fake_runtime(websocket=False)
    context = voice_context()
    config = RealtimePipelineConfig(
        provider="volcengine.doubao_realtime",
        runtime=REALTIME_RUNTIME_PIPECAT,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        metadata={
            "profile": "speech_to_speech",
            "realtimeLlm": {"provider": "volcengine.doubao_realtime"},
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(
        runtime,
        config,
        context=context,
    )

    assert processors == (sentinel,)
    assert captured == {"runtime": runtime, "context": context, "config": config}


@pytest.mark.asyncio
async def test_openai_speech_to_speech_observes_finalized_user_turn_without_reordering(
    monkeypatch,
):
    monkeypatch.setattr(pipecat_adapter, "user_billing_enabled", lambda: False)
    runtime = replace(
        fake_runtime(websocket=False),
        OpenAIRealtimeLLMService=FakeOpenAIRealtimeLLMService,
        SessionProperties=FakeRealtimeConfigValue,
        AudioConfiguration=FakeRealtimeConfigValue,
        AudioInput=FakeRealtimeConfigValue,
        AudioOutput=FakeRealtimeConfigValue,
        InputAudioTranscription=FakeRealtimeConfigValue,
        InputAudioNoiseReduction=FakeRealtimeConfigValue,
        SemanticTurnDetection=FakeRealtimeConfigValue,
        TurnDetection=FakeRealtimeConfigValue,
        PCMAudioFormat=FakeRealtimeConfigValue,
        PCMUAudioFormat=FakeRealtimeConfigValue,
        PCMAAudioFormat=FakeRealtimeConfigValue,
    )
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="gpt-realtime",
        voice="marin",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        metadata={
            "profile": "speech_to_speech",
            "realtimeLlm": {"provider": "openai"},
            "openaiApiKey": "test-key",
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(
        runtime,
        config,
        context=voice_context(),
    )
    observer, user_aggregator, llm, assistant_aggregator = processors
    assert isinstance(observer, pipecat_adapter._TalkWiseUserTurnObserverSpec)
    assert observer.aggregator is user_aggregator
    assert observer.event_name == "on_user_turn_message_added"

    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=runtime,
        context=voice_context(),
        config=config,
        processors=processors,
    )
    assert handle.pipeline.processors == [
        user_aggregator,
        llm,
        assistant_aggregator,
        handle.event_processor,
    ]

    await user_aggregator.emit_event(
        "on_user_turn_message_added",
        SimpleNamespace(
            content="finalized realtime turn",
            user_id="browser",
            timestamp="2026-08-10T00:00:00Z",
        ),
    )
    event = await handle.event_queue.get()
    assert event["type"] == "transcript.done"
    assert event["text"] == "finalized realtime turn"
    assert handle.event_queue.empty()


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
    assert adapter.handle.worker.flush_count == 2


@pytest.mark.asyncio
async def test_adapter_surfaces_an_unexpected_pipecat_worker_failure():
    class FailingWorkerRunner(FakeWorkerRunner):
        async def run(self):
            raise RuntimeError("worker boom")

    runtime = pipecat_adapter.PipecatRuntime(
        **{
            **fake_runtime(websocket=False).__dict__,
            "WorkerRunner": FailingWorkerRunner,
        }
    )
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=runtime)

    await adapter.start(voice_context(), realtime_config())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="pipeline worker failed"):
        await adapter.events().__anext__()


@pytest.mark.asyncio
async def test_adapter_queues_native_pipecat_interruption_frame():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(runtime=fake_runtime(websocket=False))

    await adapter.start(voice_context(), realtime_config())
    await adapter.cancel_response("barge_in")

    assert adapter.handle is not None
    assert isinstance(adapter.handle.worker.queued_frames[-1], FakeInterruptionFrame)

    await adapter.close()


@pytest.mark.asyncio
async def test_adapter_waits_for_and_commits_provider_processor_lifecycle():
    class ProviderProcessor:
        def __init__(self):
            self.ready_waits = 0
            self.commits = 0

        async def wait_until_ready(self):
            self.ready_waits += 1

        async def commit_audio(self):
            self.commits += 1

    processor = ProviderProcessor()
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(
        runtime=fake_runtime(websocket=False),
        processors=(processor,),
    )

    await adapter.start(voice_context(), realtime_config())
    await adapter.commit_audio()

    assert processor.ready_waits == 1
    assert processor.commits == 1

    await adapter.close()


@pytest.mark.asyncio
async def test_adapter_commit_settlement_waits_for_prior_events_to_be_consumed():
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(
        runtime=fake_runtime(websocket=False)
    )
    await adapter.start(voice_context(), realtime_config())
    assert adapter.handle is not None

    event_received = asyncio.Event()
    release_consumer = asyncio.Event()
    consumed: list[dict[str, object]] = []

    async def consume_events() -> None:
        async for event in adapter.events():
            consumed.append(dict(event))
            event_received.set()
            await release_consumer.wait()

    consumer_task = asyncio.create_task(consume_events())
    await adapter.handle.event_queue.put(
        {"type": "transcript.done", "text": "committed turn"}
    )
    await event_received.wait()
    await adapter.commit_audio()

    settlement_task = asyncio.create_task(adapter.wait_for_commit_settled())
    await asyncio.sleep(0)
    assert settlement_task.done() is False

    release_consumer.set()
    await settlement_task
    assert consumed == [{"type": "transcript.done", "text": "committed turn"}]

    consumer_task.cancel()
    with suppress(asyncio.CancelledError, RuntimeError):
        await consumer_task
    await adapter.close()


@pytest.mark.asyncio
async def test_real_pipecat_pipeline_surfaces_doubao_empty_transcript_before_commit_settles():
    async def transcribe(_audio: bytes, _model: str, _language: str) -> str:
        return ""

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(
        runtime=pipecat_adapter.import_pipecat_runtime(),
        processors=(service, pipecat_adapter._TalkWiseSTTInputBoundarySpec()),
    )
    await adapter.start(
        voice_context(),
        RealtimePipelineConfig(
            provider="pipecat",
            input_audio_format="pcm16",
            metadata={"inputSampleRate": 16000},
        ),
    )

    events: list[dict[str, object]] = []

    async def consume_events() -> None:
        async for event in adapter.events():
            events.append(dict(event))

    consumer_task = asyncio.create_task(consume_events())
    await adapter.append_audio(
        RealtimeAudioChunk(
            data=b"\x01\x00" * 8000,
            mime_type="audio/pcm",
            metadata={"sampleRate": 16000, "channels": 1},
        )
    )
    await adapter.commit_audio()
    await adapter.wait_for_commit_settled()
    try:
        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["error"] == {
            "message": (
                "No clear speech was recognized. Move closer to the microphone and try again."
            ),
            "fatal": False,
            "code": "DOUBAO_VOICE_TRANSCRIPT_EMPTY",
            "phase": "provider_response",
            "errorCategory": "input_audio",
            "retryable": True,
        }
    finally:
        await adapter.close()
        await consumer_task


@pytest.mark.asyncio
async def test_real_pipecat_pipeline_surfaces_doubao_transcript_before_commit_settles():
    async def transcribe(_audio: bytes, _model: str, _language: str) -> str:
        return "我们先从一个小范围试点开始。"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(
        runtime=pipecat_adapter.import_pipecat_runtime(),
        processors=(service, pipecat_adapter._TalkWiseSTTInputBoundarySpec()),
    )
    await adapter.start(
        voice_context(),
        RealtimePipelineConfig(
            provider="pipecat",
            input_audio_format="pcm16",
            metadata={"inputSampleRate": 16000},
        ),
    )

    events: list[dict[str, object]] = []

    async def consume_events() -> None:
        async for event in adapter.events():
            events.append(dict(event))

    consumer_task = asyncio.create_task(consume_events())
    await adapter.append_audio(
        RealtimeAudioChunk(
            data=b"\x01\x00" * 8000,
            mime_type="audio/pcm",
            metadata={"sampleRate": 16000, "channels": 1},
        )
    )
    await adapter.commit_audio()
    await adapter.wait_for_commit_settled()
    try:
        transcripts = [event for event in events if event["type"] == "transcript.done"]
        assert len(transcripts) == 1
        assert transcripts[0]["text"] == "我们先从一个小范围试点开始。"
    finally:
        await adapter.close()
        await consumer_task


@pytest.mark.asyncio
async def test_stt_boundary_commit_does_not_wait_for_blocking_downstream_llm():
    from pipecat.frames.frames import LLMContextFrame

    async def transcribe(_audio: bytes, _model: str, _language: str) -> str:
        return "boundary transcript"

    runtime = pipecat_adapter.import_pipecat_runtime()
    downstream_release = asyncio.Event()
    downstream_blocked = asyncio.Event()

    class UserAggregator(runtime.FrameProcessor):  # type: ignore[misc, valid-type]
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, runtime.TranscriptionFrame):
                context = runtime.LLMContext(
                    messages=[{"role": "user", "content": frame.text}]
                )
                await self.push_frame(LLMContextFrame(context=context), direction)
                return
            await self.push_frame(frame, direction)

    class BlockingLLM(runtime.FrameProcessor):  # type: ignore[misc, valid-type]
        async def process_frame(self, frame, direction):
            await super().process_frame(frame, direction)
            if isinstance(frame, LLMContextFrame):
                downstream_blocked.set()
                await downstream_release.wait()
            await self.push_frame(frame, direction)

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    adapter = pipecat_adapter.PipecatRealtimePipelineAdapter(
        runtime=runtime,
        processors=(
            service,
            pipecat_adapter._TalkWiseSTTInputBoundarySpec(),
            UserAggregator(name="UserAggregator"),
            BlockingLLM(name="BlockingLLM"),
        ),
    )
    await adapter.start(
        voice_context(),
        RealtimePipelineConfig(
            provider="pipecat",
            input_audio_format="pcm16",
            metadata={"inputSampleRate": 16000},
        ),
    )

    events: list[dict[str, object]] = []

    async def consume_events() -> None:
        async for event in adapter.events():
            events.append(dict(event))

    consumer_task = asyncio.create_task(consume_events())
    try:
        await adapter.append_audio(
            RealtimeAudioChunk(
                data=b"\x01\x00" * 8000,
                mime_type="audio/pcm",
                metadata={"sampleRate": 16000, "channels": 1},
            )
        )
        await asyncio.wait_for(adapter.commit_audio(), timeout=1.0)
        await asyncio.wait_for(adapter.wait_for_commit_settled(), timeout=1.0)

        assert downstream_blocked.is_set()
        assert [event["type"] for event in events] == ["transcript.done"]
        assert events[0]["text"] == "boundary transcript"
    finally:
        downstream_release.set()
        await adapter.close()
        await consumer_task


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
async def test_pipeline_publishes_one_transcript_for_a_semantic_user_turn():
    runtime = fake_runtime(websocket=False)
    stt = object()
    user_aggregator = FakeLLMUserAggregator(
        FakeLLMContext(),
        FakeLLMUserAggregatorParams(),
    )
    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=runtime,
        context=voice_context(),
        config=realtime_config(),
        processors=[
            stt,
            pipecat_adapter._TalkWiseUserTurnObserverSpec(user_aggregator),
            user_aggregator,
        ],
    )

    assert handle.pipeline.processors[0] is stt
    assert handle.pipeline.processors[1] is user_aggregator
    assert handle.pipeline.processors[2] is handle.event_processor
    assert set(user_aggregator.event_handlers) == {"on_user_turn_stopped"}

    for raw_text in ("partial smart turn", "final STT segment"):
        await handle.event_processor.process_frame(
            FakeTranscriptionFrame(
                text=raw_text,
                user_id="browser",
                timestamp="2026-08-10T00:00:00Z",
            ),
            FakeFrameDirection.DOWNSTREAM,
        )
    assert handle.event_queue.empty()

    text = (
        "\u6211\u4eec\u53ef\u4ee5\u5148\u4ece\u4e00\u4e2a\u5c0f\u8303\u56f4"
        "\u8bd5\u70b9\u5f00\u59cb\uff0c\u4e09\u5341\u5929\u540e\u518d\u51b3\u5b9a"
        "\u662f\u5426\u7ee7\u7eed\u3002"
    )
    await user_aggregator.emit_event(
        "on_user_turn_stopped",
        object(),
        SimpleNamespace(
            content=text,
            user_id="browser",
            timestamp="2026-08-10T00:00:00Z",
        ),
    )

    transcript = await handle.event_queue.get()
    assert transcript == {
        "type": "transcript.done",
        "runtime": "pipecat",
        "text": text,
        "provider": "pipecat",
        "source": "pipecat",
        "timestamp": "2026-08-10T00:00:00Z",
        "metadata": {"aggregation": "pipecat_user_turn"},
        "user_id": "browser",
        "sender_id": "browser",
    }
    assert handle.event_queue.empty()

    await handle.event_processor.process_frame(
        FakeErrorFrame(error="provider failed", fatal=False),
        FakeFrameDirection.DOWNSTREAM,
    )
    error = await handle.event_queue.get()
    assert error["type"] == "error"
    assert error["error"] == {"message": "provider failed", "fatal": False}


@pytest.mark.asyncio
async def test_transcript_preview_updates_without_persisting_each_stt_segment():
    runtime = fake_runtime(websocket=False)
    state = pipecat_adapter._TalkWiseTranscriptPreviewState()
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_transcript_preview_processor(
        runtime,
        queue,
        config=realtime_config(),
        state=state,
    )

    await processor.process_frame(
        FakeInterimTranscriptionFrame(
            text="为了降低风险",
            user_id="browser",
            timestamp="2026-08-10T00:00:00Z",
        ),
        FakeFrameDirection.DOWNSTREAM,
    )
    first = await queue.get()
    assert first["type"] == "transcript.delta"
    assert first["text"] == "为了降低风险"
    assert first["metadata"]["preview"] is True
    assert first["metadata"]["replace"] is True

    await processor.process_frame(
        FakeTranscriptionFrame(
            text="我们可以分成两个阶段",
            user_id="browser",
            timestamp="2026-08-10T00:00:01Z",
        ),
        FakeFrameDirection.DOWNSTREAM,
    )
    second = await queue.get()
    assert second["type"] == "transcript.delta"
    assert second["text"] == "为了降低风险我们可以分成两个阶段"
    assert second["metadata"]["aggregation"] == "pipecat_user_turn_preview"

    await processor.process_frame(
        FakeInterimTranscriptionFrame(
            text="第一阶段验证转化率",
            user_id="browser",
            timestamp="2026-08-10T00:00:02Z",
        ),
        FakeFrameDirection.DOWNSTREAM,
    )
    third = await queue.get()
    assert third["text"] == "为了降低风险我们可以分成两个阶段第一阶段验证转化率"
    assert state.text == third["text"]


def test_pipeline_start_metadata_strips_secret_config_values():
    handle = pipecat_adapter.build_pipecat_pipeline_handle(
        runtime=fake_runtime(websocket=False),
        context=TrainingVoiceContext(
            binding=RealtimeSessionBinding(training_session_id="training-secret", room_id=9),
            metadata={
                "scenario": "coaching",
                "Authorization": "Bearer sk-context-secret",
            },
        ),
        config=RealtimePipelineConfig(
            provider="pipecat",
            metadata={
                "openaiApiKey": "sk-config-secret",
                "safeConfig": "kept",
                "notes": "Bearer sk-note-secret",
                "nested": {"token": "nested-secret", "public": "ok"},
            },
        ),
    )

    start_metadata = handle.worker.kwargs["params"].kwargs["start_metadata"]
    metadata = start_metadata["metadata"]
    assert metadata["scenario"] == "coaching"
    assert metadata["safeConfig"] == "kept"
    assert metadata["notes"] == "Bearer ***"
    assert metadata["nested"] == {"public": "ok"}
    assert "Authorization" not in metadata
    assert "openaiApiKey" not in metadata
    assert "sk-config-secret" not in json.dumps(start_metadata)


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
        pipecat_adapter._TalkWiseSTTInputBoundarySpec,
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
    assert processors[4].kwargs["api_key"] == "sk-test"
    assert processors[4].kwargs["base_url"] is None
    assert processors[4].kwargs["sample_rate"] == 24000
    assert processors[4].kwargs["settings"].kwargs == {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "instructions": "Speak concisely.",
    }


@pytest.mark.asyncio
async def test_build_pipecat_voice_processors_creates_doubao_stt_and_tts_services(
    monkeypatch,
):
    monkeypatch.setattr(pipecat_adapter, "user_billing_enabled", lambda: False)
    monkeypatch.setattr(settings.llm, "api_key", "gateway-token")
    monkeypatch.setattr(settings.llm, "base_url", "http://newapi.test/pg")
    config = RealtimePipelineConfig(
        provider="pipecat",
        voice="zh_female_vv_uranus_bigtts",
        metadata={
            "stt": {
                "provider": "volcengine.doubao",
                "model": "volc.bigasr.sauc.duration",
            },
            "tts": {
                "provider": "volcengine.doubao",
                "model": "seed-tts-2.0",
            },
            "vad": "silero",
            "turnDetection": {
                "provider": "pipecat",
                "userSpeechTimeout": 2.0,
            },
            "inputSampleRate": 16000,
            "outputSampleRate": 24000,
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(fake_runtime(False), config)

    assert [type(processor) for processor in processors] == [
        FakeVADProcessor,
        VolcengineDoubaoSTTService,
        pipecat_adapter._TalkWiseSTTInputBoundarySpec,
        FakeUserTurnProcessor,
        VolcengineDoubaoTTSService,
    ]
    assert processors[1]._transcriptions_url == "http://newapi.test/pg/audio/transcriptions"
    assert processors[1]._init_sample_rate == 16000
    assert processors[1]._vad_segment_settle_seconds == 2.0
    assert processors[4]._speech_url == "http://newapi.test/pg/audio/speech"
    assert processors[4]._init_sample_rate == 24000

    await processors[1].cleanup()
    await processors[4].cleanup()


def test_doubao_pipeline_readiness_distinguishes_missing_and_invalid_configuration(
    monkeypatch,
):
    monkeypatch.setattr(pipecat_adapter, "user_billing_enabled", lambda: False)
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "base_url", "http://newapi.test/pg")
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="gpt-5.5",
        voice="zh_female_vv_uranus_bigtts",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        metadata={
            "stt": {
                "provider": "volcengine.doubao",
                "model": "volc.bigasr.sauc.duration",
            },
            "tts": {
                "provider": "volcengine.doubao",
                "model": "seed-tts-2.0",
            },
            "inputSampleRate": 16000,
            "outputSampleRate": 24000,
        },
    )

    missing = pipecat_adapter.pipecat_pipeline_capability(
        runtime=fake_runtime(False),
        config=config,
    ).readiness_payload()
    assert "MISSING_DOUBAO_VOICE_CREDENTIAL" in {
        item["code"] for item in missing["blockingReasons"]
    }

    monkeypatch.setattr(settings.llm, "api_key", "gateway-token")
    monkeypatch.setattr(settings.llm, "base_url", "invalid-relay")
    invalid = pipecat_adapter.pipecat_pipeline_capability(
        runtime=fake_runtime(False),
        config=config,
    ).readiness_payload()
    invalid_error = next(
        item
        for item in invalid["blockingReasons"]
        if item["code"] == "DOUBAO_VOICE_CONFIG_INVALID"
    )
    assert invalid_error["provider"] == "volcengine.doubao"
    assert invalid_error["metadata"]["errorCategory"] == "configuration"


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
        pipecat_adapter._TalkWiseSTTInputBoundarySpec,
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
    assert processors[3].kwargs == {
        "user_turn_stop_timeout": 3.0,
        "user_idle_timeout": 10.0,
    }
    assert processors[4].kwargs["sample_rate"] == 24000
    assert processors[4].kwargs["settings"].kwargs == {
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
                "baseStopStrategy": "speech_timeout",
                "userSpeechTimeout": 2.0,
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
    stop_strategy = strategies.kwargs["stop"][0]
    assert isinstance(stop_strategy, FakeSpeechTimeoutUserTurnStopStrategy)
    assert stop_strategy.kwargs == {"user_speech_timeout": 2.0}
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
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
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
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    )


def test_build_pipecat_voice_processors_uses_settings_key_without_metadata(monkeypatch):
    monkeypatch.setattr(settings.llm, "api_key", "sk-settings-realtime")

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
    assert processors[2].kwargs["api_key"] == "sk-settings-realtime"


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
                "strategy": "filter_incomplete",
                "baseStopStrategy": "speech_timeout",
                "userSpeechTimeout": 2.0,
                "userTurnStopTimeout": 12.0,
                "userIdleTimeout": 8.0,
                "filterIncompleteUserTurns": True,
                "userTurnCompletionConfig": {
                    "incompleteShortTimeout": 4.0,
                    "incompleteLongTimeout": 8.0,
                },
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
        pipecat_adapter._TalkWiseTranscriptPreviewSpec,
        pipecat_adapter._TalkWiseUserTurnObserverSpec,
        pipecat_adapter._TalkWiseSTTInputBoundarySpec,
        FakeLLMUserAggregator,
        FakeOpenAILLMService,
        FakeOpenAITTSService,
        FakeLLMAssistantAggregator,
    ]
    assert not any(isinstance(processor, FakeUserTurnProcessor) for processor in processors)
    assert processors[2].state is processors[3].preview_state
    assert processors[3].aggregator is processors[5]
    assert processors[3].event_name == "on_user_turn_stopped"
    user_aggregator = processors[5]
    assert user_aggregator.params.kwargs["user_turn_stop_timeout"] == 12.0
    assert user_aggregator.params.kwargs["user_idle_timeout"] == 8.0
    assert user_aggregator.params.kwargs["filter_incomplete_user_turns"] is True
    strategies = user_aggregator.params.kwargs["user_turn_strategies"]
    assert isinstance(strategies, FakeFilterIncompleteUserTurnStrategies)
    stop_strategy = strategies.kwargs["stop"][0]
    assert isinstance(stop_strategy, FakeSpeechTimeoutUserTurnStopStrategy)
    assert stop_strategy.kwargs == {"user_speech_timeout": 2.0}
    completion_config = user_aggregator.params.kwargs["user_turn_completion_config"]
    assert completion_config.kwargs == {
        "incomplete_short_timeout": 4.0,
        "incomplete_long_timeout": 8.0,
    }
    assert user_aggregator.context.messages == [
        {"role": "user", "content": "Can we discuss renewal risk?"},
        {"role": "assistant", "content": "Yes, what risk is most urgent?"},
    ]

    llm = processors[6]
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
    assert capability.metadata["productionReady"] is False
    assert capability.metadata["productionReadiness"]["status"] == "runtime_blocked"
    production_blockers = capability.metadata["productionReadiness"]["blockingReasons"]
    assert [error["code"] for error in production_blockers] == [
        "LOCAL_REALTIME_RUNTIME_NOT_READY",
        "BROWSER_AUDIO_E2E_NOT_VERIFIED",
    ]
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
            metadata={
                "responseId": "response-pipecat-1",
                "providerResponseId": "reply-1",
                "providerQuestionId": "question-1",
            },
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["type"] == "response.audio_transcript.done"
    assert event["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert event["text"] == "assistant final turn"
    assert event["responseId"] == "response-pipecat-1"
    assert event["providerResponseId"] == "reply-1"
    assert event["providerQuestionId"] == "question-1"
    assert event["metadata"]["responseId"] == "response-pipecat-1"
    assert event["metadata"]["pipecatFrame"]["frameName"] == "FakeLLMContextAssistantTurnFrame"


@pytest.mark.asyncio
async def test_talkwise_event_processor_forwards_provider_error_frames():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=RealtimePipelineConfig(provider="volcengine.doubao_realtime"),
    )

    await processor.process_frame(
        FakeErrorFrame(error="provider disconnected", fatal=True),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event == {
        "type": "error",
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": "volcengine.doubao_realtime",
        "source": "pipecat",
        "error": {"message": "provider disconnected", "fatal": True},
    }


@pytest.mark.asyncio
async def test_talkwise_event_processor_preserves_turn_desync_error_contract():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=RealtimePipelineConfig(provider="volcengine.doubao_realtime"),
    )

    await processor.process_frame(
        FakeErrorFrame(
            error="Realtime response identity became ambiguous",
            fatal=True,
            metadata={
                "providerError": {
                    "code": "REALTIME_TURN_DESYNC",
                    "sourceCode": "REALTIME_TURN_DESYNC",
                    "errorCategory": "protocol_desync",
                    "retryable": False,
                    "fatal": True,
                }
            },
        ),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["error"]["code"] == "REALTIME_TURN_DESYNC"
    assert event["error"]["errorCategory"] == "protocol_desync"
    assert event["error"]["retryable"] is False
    assert event["error"]["fatal"] is True


@pytest.mark.asyncio
async def test_talkwise_event_processor_maps_turn_and_interruption_frames():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=RealtimePipelineConfig(
            provider="pipecat",
            metadata={"talkwise": {"trainingSessionId": "training-1", "roomId": 7}},
        ),
    )

    frames = [
        FakeUserStartedSpeakingFrame(),
        FakeVADUserStoppedSpeakingFrame(stop_secs=0.8, timestamp=123.4),
        FakeBotStartedSpeakingFrame(),
        FakeBotStoppedSpeakingFrame(),
        FakeInterruptionFrame(metadata={"reason": "barge_in"}),
        FakeUserIdleTimeoutUpdateFrame(timeout=6.5),
    ]
    for frame in frames:
        await processor.process_frame(frame, FakeFrameDirection.DOWNSTREAM)

    events = [await queue.get() for _ in frames]
    assert [event["type"] for event in events] == [
        "user_turn.started",
        "user_turn.stopped",
        "assistant_speaking.started",
        "assistant_speaking.stopped",
        "interrupted",
        "silence_timeout",
    ]
    assert events[0]["payload"]["participant"] == "user"
    assert events[0]["payload"]["signal"] == "user_turn"
    assert events[1]["payload"]["signal"] == "vad"
    assert events[1]["payload"]["silenceSeconds"] == 0.8
    assert events[1]["payload"]["timestamp"] == 123.4
    assert events[2]["payload"]["participant"] == "assistant"
    assert events[4]["metadata"]["reason"] == "barge_in"
    assert events[5]["payload"]["timeoutSeconds"] == 6.5
    assert events[5]["metadata"]["talkwise"] == {
        "trainingSessionId": "training-1",
        "roomId": 7,
    }


@pytest.mark.asyncio
async def test_talkwise_event_processor_attaches_turn_latency_to_assistant_start(monkeypatch):
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    times = iter([10.0, 11.25, 11.5])
    monkeypatch.setattr(pipecat_adapter, "_monotonic_seconds", lambda: next(times))
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    for frame in (
        FakeUserStartedSpeakingFrame(),
        FakeVADUserStoppedSpeakingFrame(stop_secs=0.8),
        FakeBotStartedSpeakingFrame(),
    ):
        await processor.process_frame(frame, FakeFrameDirection.DOWNSTREAM)

    events = [await queue.get() for _ in range(3)]
    metrics = events[2]["metadata"]["realtimeMetrics"]
    assert [event["type"] for event in events] == [
        "user_turn.started",
        "user_turn.stopped",
        "assistant_speaking.started",
    ]
    assert metrics == {
        "schemaVersion": 1,
        "source": "pipecat_frames",
        "turnSequence": 1,
        "latencyStartEvent": "user_turn.stopped",
        "userSpeechMs": 1250,
        "silenceSeconds": 0.8,
        "latencyEndEvent": "assistant_speaking.started",
        "turnLatencyMs": 250,
    }
    assert "realtimeMetrics" not in events[1].get("metadata", {})


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
            metadata={
                "voice": "alloy",
                "responseId": "reply-2",
                "providerResponseId": "reply-2",
                "providerQuestionId": "question-2",
                "unsafe": object(),
            },
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
    assert event["responseId"] == "reply-2"
    assert event["providerResponseId"] == "reply-2"
    assert event["providerQuestionId"] == "question-2"
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
async def test_talkwise_event_processor_ignores_empty_or_non_bytes_tts_audio():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeTTSAudioRawFrame(audio=b"", sample_rate=16000, num_channels=1),
        FakeFrameDirection.DOWNSTREAM,
    )
    await processor.process_frame(
        FakeTTSAudioRawFrame(audio="not-bytes", sample_rate=16000, num_channels=1),
        FakeFrameDirection.DOWNSTREAM,
    )

    assert queue.empty()
    assert len(processor.pushed) == 2


@pytest.mark.asyncio
async def test_talkwise_event_processor_defaults_invalid_audio_shape_values():
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    await processor.process_frame(
        FakeTTSAudioRawFrame(audio=b"pcm", sample_rate="bad", num_channels="bad"),
        FakeFrameDirection.DOWNSTREAM,
    )

    event = await queue.get()
    assert event["sampleRate"] == 16000
    assert event["channels"] == 1
    assert event["payload"]["sampleRate"] == 16000
    assert event["payload"]["channels"] == 1


@pytest.mark.asyncio
async def test_talkwise_event_processor_attaches_turn_latency_to_first_audio_output(monkeypatch):
    runtime = fake_runtime(websocket=False)
    queue = asyncio.Queue()
    times = iter([20.0, 20.4, 20.55])
    monkeypatch.setattr(pipecat_adapter, "_monotonic_seconds", lambda: next(times))
    processor = pipecat_adapter.create_talkwise_event_processor(
        runtime,
        queue,
        config=realtime_config(),
    )

    for frame in (
        FakeUserStartedSpeakingFrame(),
        FakeUserStoppedSpeakingFrame(),
        FakeTTSAudioRawFrame(audio=b"pcm", sample_rate=16000, num_channels=1),
    ):
        await processor.process_frame(frame, FakeFrameDirection.DOWNSTREAM)

    events = [await queue.get() for _ in range(3)]
    audio_event = events[2]
    metrics = audio_event["metadata"]["realtimeMetrics"]
    assert audio_event["type"] == "audio.output"
    assert metrics["source"] == "pipecat_frames"
    assert metrics["turnSequence"] == 1
    assert metrics["latencyStartEvent"] == "user_turn.stopped"
    assert metrics["latencyEndEvent"] == "audio.output"
    assert metrics["userSpeechMs"] == 400
    assert metrics["turnLatencyMs"] == 150
    assert audio_event["payload"]["metadata"]["realtimeMetrics"] == metrics


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
    assert "pipecat.frames.frames.InterruptionFrame" in snapshot["frameEntrypoints"]
    assert "pipecat.frames.frames.VADUserStartedSpeakingFrame" in snapshot["frameEntrypoints"]
    assert "pipecat.frames.frames.BotStartedSpeakingFrame" in snapshot["frameEntrypoints"]
    assert "pipecat.frames.frames.UserIdleTimeoutUpdateFrame" in snapshot["frameEntrypoints"]
    assert snapshot["audioFrameFields"]["pipecat.frames.frames.OutputAudioRawFrame"] == (
        "audio",
        "sample_rate",
        "num_channels",
        "num_frames",
    )
    assert snapshot["audioFrameFields"]["pipecat.frames.frames.TTSAudioRawFrame"] == ("context_id",)
    assert (
        "TTSAudioRawFrame to provider-neutral audio.output event mirroring"
        in snapshot["talkwiseResponsibilities"]
    )
    assert (
        "Pipecat turn/interruption/silence frames to TalkWise realtime event mirroring"
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
        "pipecat.services.openai.tts.OpenAITTSService.Settings" == snapshot["ttsSettingsEntrypoint"]
    )
    assert "pipecat.services.openai.llm.OpenAILLMService" == snapshot["llmEntrypoint"]
    assert (
        "pipecat.services.openai.llm.OpenAILLMService.Settings" == snapshot["llmSettingsEntrypoint"]
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
