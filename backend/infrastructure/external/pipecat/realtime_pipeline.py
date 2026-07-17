"""Optional Pipecat realtime pipeline adapter.

Pipecat owns media transport, frame flow, and lifecycle management when it is
installed. This module keeps TalkWise integration thin: capability detection,
dependency-safe factories, and DTO-to-frame adaptation only.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
    RealtimePipelineCapability,
    RealtimePipelineConfig,
    TrainingVoiceContext,
)

CORE_PIPECAT_MODULES = (
    "pipecat.pipeline.pipeline",
    "pipecat.pipeline.worker",
    "pipecat.workers.base_worker",
    "pipecat.workers.runner",
    "pipecat.frames.frames",
    "pipecat.processors.frame_processor",
)
WEBSOCKET_PIPECAT_MODULE = "pipecat.transports.websocket.fastapi"
SILERO_VAD_PIPECAT_MODULE = "pipecat.audio.vad.silero"
VAD_ANALYZER_PIPECAT_MODULE = "pipecat.audio.vad.vad_analyzer"
VAD_PROCESSOR_PIPECAT_MODULE = "pipecat.processors.audio.vad_processor"
OPENAI_STT_PIPECAT_MODULE = "pipecat.services.openai.stt"
OPENAI_TTS_PIPECAT_MODULE = "pipecat.services.openai.tts"
OPENAI_LLM_PIPECAT_MODULE = "pipecat.services.openai.llm"
LLM_CONTEXT_PIPECAT_MODULE = "pipecat.processors.aggregators.llm_context"
LLM_RESPONSE_PIPECAT_MODULE = "pipecat.processors.aggregators.llm_response_universal"
USER_TURN_PROCESSOR_PIPECAT_MODULE = "pipecat.turns.user_turn_processor"
USER_TURN_STRATEGIES_PIPECAT_MODULE = "pipecat.turns.user_turn_strategies"
USER_TURN_COMPLETION_PIPECAT_MODULE = "pipecat.turns.user_turn_completion_mixin"
OPTIONAL_PIPECAT_FEATURE_MODULES = {
    "vad": (
        SILERO_VAD_PIPECAT_MODULE,
        VAD_ANALYZER_PIPECAT_MODULE,
        VAD_PROCESSOR_PIPECAT_MODULE,
        "onnxruntime",
    ),
    "stt": (OPENAI_STT_PIPECAT_MODULE, "websockets"),
    "tts": (OPENAI_TTS_PIPECAT_MODULE, "openai"),
    "llm": (
        OPENAI_LLM_PIPECAT_MODULE,
        LLM_CONTEXT_PIPECAT_MODULE,
        LLM_RESPONSE_PIPECAT_MODULE,
    ),
    "turn_detection": (
        USER_TURN_PROCESSOR_PIPECAT_MODULE,
        USER_TURN_STRATEGIES_PIPECAT_MODULE,
        USER_TURN_COMPLETION_PIPECAT_MODULE,
    ),
}


@dataclass(frozen=True)
class PipecatCapability:
    """Importability report for the optional Pipecat integration."""

    available: bool
    core_available: bool
    websocket_available: bool
    missing_modules: tuple[str, ...] = ()
    vad_available: bool = False
    stt_available: bool = False
    tts_available: bool = False
    llm_available: bool = False
    turn_detection_available: bool = False
    optional_missing_modules: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class PipecatRuntime:
    """Imported Pipecat symbols used by the TalkWise adapter."""

    Pipeline: type
    PipelineParams: type
    PipelineWorker: type
    WorkerParams: type
    WorkerRunner: type
    InputAudioRawFrame: type
    EndFrame: type
    TextFrame: type
    TranscriptionFrame: type
    LLMContextAssistantTurnFrame: type
    FrameProcessor: type
    FrameDirection: type
    InterimTranscriptionFrame: type | None = None
    FastAPIWebsocketParams: type | None = None
    FastAPIWebsocketTransport: type | None = None
    SileroVADAnalyzer: type | None = None
    VADParams: type | None = None
    VADProcessor: type | None = None
    OpenAIRealtimeSTTService: type | None = None
    OpenAITTSService: type | None = None
    OpenAILLMService: type | None = None
    LLMContext: type | None = None
    LLMContextAggregatorPair: type | None = None
    LLMUserAggregatorParams: type | None = None
    LLMAssistantAggregatorParams: type | None = None
    UserTurnProcessor: type | None = None
    UserTurnStrategies: type | None = None
    ExternalUserTurnStrategies: type | None = None
    FilterIncompleteUserTurnStrategies: type | None = None
    UserTurnCompletionConfig: type | None = None

    @property
    def websocket_available(self) -> bool:
        return (
            self.FastAPIWebsocketParams is not None and self.FastAPIWebsocketTransport is not None
        )


@dataclass
class PipecatPipelineHandle:
    """Concrete Pipecat objects created for a running TalkWise voice pipeline."""

    pipeline: Any
    worker: Any
    runner: Any
    event_queue: asyncio.Queue[Mapping[str, Any]]
    transport: Any | None = None
    event_processor: Any | None = None
    run_task: asyncio.Task | None = None


def is_pipecat_available() -> bool:
    """Return whether the core Pipecat pipeline package is importable."""

    return get_pipecat_capability().core_available


def get_pipecat_capability(*, require_websocket: bool = False) -> PipecatCapability:
    """Return a dependency-safe capability report without importing Pipecat eagerly."""

    modules = [*CORE_PIPECAT_MODULES]
    if require_websocket:
        modules.append(WEBSOCKET_PIPECAT_MODULE)

    optional_status = _optional_feature_status()
    missing = tuple(module for module in modules if not _module_spec_exists(module))
    if missing:
        return PipecatCapability(
            available=False,
            core_available=not any(module in CORE_PIPECAT_MODULES for module in missing),
            websocket_available=WEBSOCKET_PIPECAT_MODULE not in missing,
            missing_modules=missing,
            **optional_status,
            error=f"Missing optional Pipecat module(s): {', '.join(missing)}",
        )

    try:
        runtime = import_pipecat_runtime(require_websocket=require_websocket)
    except ImportError as exc:
        websocket_error = "websocket transport" in str(exc).lower()
        return PipecatCapability(
            available=False,
            core_available=websocket_error,
            websocket_available=False,
            missing_modules=(WEBSOCKET_PIPECAT_MODULE,) if websocket_error else (),
            **optional_status,
            error=str(exc),
        )

    return PipecatCapability(
        available=True if not require_websocket else runtime.websocket_available,
        core_available=True,
        websocket_available=runtime.websocket_available,
        **_runtime_feature_status(runtime, optional_status),
    )


def _module_spec_exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _optional_feature_status() -> dict[str, bool | tuple[str, ...]]:
    missing_by_feature = {
        feature: tuple(module for module in modules if not _module_spec_exists(module))
        for feature, modules in OPTIONAL_PIPECAT_FEATURE_MODULES.items()
    }
    return {
        "vad_available": not missing_by_feature["vad"],
        "stt_available": not missing_by_feature["stt"],
        "tts_available": not missing_by_feature["tts"],
        "llm_available": not missing_by_feature["llm"],
        "turn_detection_available": not missing_by_feature["turn_detection"],
        "optional_missing_modules": tuple(
            module for modules in missing_by_feature.values() for module in modules
        ),
    }


def _runtime_feature_status(
    runtime: PipecatRuntime,
    module_status: Mapping[str, bool | tuple[str, ...]],
) -> dict[str, bool | tuple[str, ...]]:
    return {
        "vad_available": bool(module_status.get("vad_available"))
        and (
            runtime.SileroVADAnalyzer is not None
            and runtime.VADParams is not None
            and runtime.VADProcessor is not None
        ),
        "stt_available": bool(module_status.get("stt_available"))
        and runtime.OpenAIRealtimeSTTService is not None,
        "tts_available": bool(module_status.get("tts_available"))
        and runtime.OpenAITTSService is not None,
        "llm_available": bool(module_status.get("llm_available"))
        and runtime.OpenAILLMService is not None
        and runtime.LLMContext is not None
        and runtime.LLMContextAggregatorPair is not None
        and runtime.LLMUserAggregatorParams is not None
        and runtime.LLMAssistantAggregatorParams is not None,
        "turn_detection_available": bool(module_status.get("turn_detection_available"))
        and (
            runtime.UserTurnProcessor is not None and runtime.UserTurnStrategies is not None
        ),
        "optional_missing_modules": tuple(module_status.get("optional_missing_modules", ())),
    }


def create_pipecat_realtime_pipeline(
    *,
    websocket: Any | None = None,
    processors: Sequence[Any] = (),
    serializer: Any | None = None,
    transport_params: Any | Mapping[str, Any] | None = None,
) -> RealtimePipelineAdapter | None:
    """Create the optional Pipecat adapter when required dependencies exist.

    When ``websocket`` is provided the websocket extra must also be importable,
    because Pipecat's ``FastAPIWebsocketTransport`` should own socket lifecycle.
    Without a websocket, callers may still use Pipecat processors directly and
    feed audio through ``append_audio``.
    """

    require_websocket = websocket is not None
    capability = get_pipecat_capability(require_websocket=require_websocket)
    if not capability.available:
        return None
    return PipecatRealtimePipelineAdapter(
        websocket=websocket,
        processors=processors,
        serializer=serializer,
        transport_params=transport_params,
    )


def import_pipecat_runtime(*, require_websocket: bool = False) -> PipecatRuntime:
    """Import Pipecat symbols lazily so normal application startup stays optional."""

    try:
        pipeline_module = importlib.import_module("pipecat.pipeline.pipeline")
        worker_module = importlib.import_module("pipecat.pipeline.worker")
        worker_params_module = importlib.import_module("pipecat.workers.base_worker")
        runner_module = importlib.import_module("pipecat.workers.runner")
        frames_module = importlib.import_module("pipecat.frames.frames")
        processor_module = importlib.import_module("pipecat.processors.frame_processor")
    except ModuleNotFoundError as exc:
        raise ImportError(f"Pipecat core is not installed: {exc.name}") from exc

    websocket_params = None
    websocket_transport = None
    try:
        websocket_module = importlib.import_module(WEBSOCKET_PIPECAT_MODULE)
        websocket_params = websocket_module.FastAPIWebsocketParams
        websocket_transport = websocket_module.FastAPIWebsocketTransport
    except (ImportError, ModuleNotFoundError) as exc:
        if require_websocket:
            raise ImportError(
                "Pipecat websocket transport is unavailable; install pipecat with websocket extras"
            ) from exc

    silero_vad_analyzer = _optional_pipecat_symbol(
        SILERO_VAD_PIPECAT_MODULE, "SileroVADAnalyzer"
    )
    vad_params = _optional_pipecat_symbol(VAD_ANALYZER_PIPECAT_MODULE, "VADParams")
    vad_processor = _optional_pipecat_symbol(VAD_PROCESSOR_PIPECAT_MODULE, "VADProcessor")
    openai_realtime_stt = _optional_pipecat_symbol(
        OPENAI_STT_PIPECAT_MODULE, "OpenAIRealtimeSTTService"
    )
    openai_tts = _optional_pipecat_symbol(OPENAI_TTS_PIPECAT_MODULE, "OpenAITTSService")
    openai_llm = _optional_pipecat_symbol(OPENAI_LLM_PIPECAT_MODULE, "OpenAILLMService")
    llm_context = _optional_pipecat_symbol(LLM_CONTEXT_PIPECAT_MODULE, "LLMContext")
    llm_context_aggregator_pair = _optional_pipecat_symbol(
        LLM_RESPONSE_PIPECAT_MODULE, "LLMContextAggregatorPair"
    )
    llm_user_aggregator_params = _optional_pipecat_symbol(
        LLM_RESPONSE_PIPECAT_MODULE, "LLMUserAggregatorParams"
    )
    llm_assistant_aggregator_params = _optional_pipecat_symbol(
        LLM_RESPONSE_PIPECAT_MODULE, "LLMAssistantAggregatorParams"
    )
    user_turn_processor = _optional_pipecat_symbol(
        USER_TURN_PROCESSOR_PIPECAT_MODULE, "UserTurnProcessor"
    )
    user_turn_strategies = _optional_pipecat_symbol(
        USER_TURN_STRATEGIES_PIPECAT_MODULE, "UserTurnStrategies"
    )
    external_user_turn_strategies = _optional_pipecat_symbol(
        USER_TURN_STRATEGIES_PIPECAT_MODULE, "ExternalUserTurnStrategies"
    )
    filter_incomplete_user_turn_strategies = _optional_pipecat_symbol(
        USER_TURN_STRATEGIES_PIPECAT_MODULE, "FilterIncompleteUserTurnStrategies"
    )
    user_turn_completion_config = _optional_pipecat_symbol(
        USER_TURN_COMPLETION_PIPECAT_MODULE, "UserTurnCompletionConfig"
    )

    return PipecatRuntime(
        Pipeline=pipeline_module.Pipeline,
        PipelineParams=worker_module.PipelineParams,
        PipelineWorker=worker_module.PipelineWorker,
        WorkerParams=worker_params_module.WorkerParams,
        WorkerRunner=runner_module.WorkerRunner,
        InputAudioRawFrame=frames_module.InputAudioRawFrame,
        EndFrame=frames_module.EndFrame,
        TextFrame=frames_module.TextFrame,
        TranscriptionFrame=frames_module.TranscriptionFrame,
        LLMContextAssistantTurnFrame=frames_module.LLMContextAssistantTurnFrame,
        FrameProcessor=processor_module.FrameProcessor,
        FrameDirection=processor_module.FrameDirection,
        InterimTranscriptionFrame=getattr(frames_module, "InterimTranscriptionFrame", None),
        FastAPIWebsocketParams=websocket_params,
        FastAPIWebsocketTransport=websocket_transport,
        SileroVADAnalyzer=silero_vad_analyzer,
        VADParams=vad_params,
        VADProcessor=vad_processor,
        OpenAIRealtimeSTTService=openai_realtime_stt,
        OpenAITTSService=openai_tts,
        OpenAILLMService=openai_llm,
        LLMContext=llm_context,
        LLMContextAggregatorPair=llm_context_aggregator_pair,
        LLMUserAggregatorParams=llm_user_aggregator_params,
        LLMAssistantAggregatorParams=llm_assistant_aggregator_params,
        UserTurnProcessor=user_turn_processor,
        UserTurnStrategies=user_turn_strategies,
        ExternalUserTurnStrategies=external_user_turn_strategies,
        FilterIncompleteUserTurnStrategies=filter_incomplete_user_turn_strategies,
        UserTurnCompletionConfig=user_turn_completion_config,
    )


def _optional_pipecat_symbol(module_name: str, symbol_name: str) -> type | None:
    try:
        module = importlib.import_module(module_name)
    except (ImportError, ModuleNotFoundError):
        return None
    return getattr(module, symbol_name, None)


class PipecatRealtimePipelineAdapter:
    """Thin TalkWise adapter around Pipecat's pipeline runtime."""

    def __init__(
        self,
        *,
        websocket: Any | None = None,
        processors: Sequence[Any] = (),
        serializer: Any | None = None,
        transport_params: Any | Mapping[str, Any] | None = None,
        runtime: PipecatRuntime | None = None,
    ) -> None:
        self._websocket = websocket
        self._processors = tuple(processors)
        self._serializer = serializer
        self._transport_params = transport_params
        self._runtime = runtime
        self._handle: PipecatPipelineHandle | None = None
        self._context: TrainingVoiceContext | None = None
        self._config: RealtimePipelineConfig | None = None
        self._closed = False

    @property
    def handle(self) -> PipecatPipelineHandle | None:
        """Expose created Pipecat objects for route wiring and tests."""

        return self._handle

    def capability(self) -> RealtimePipelineCapability:
        runtime = self._runtime
        return pipecat_pipeline_capability(
            runtime=runtime,
            config=self._config or RealtimePipelineConfig(provider="pipecat"),
            websocket=self._websocket,
        )

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        if self._handle is not None and not self._closed:
            raise RuntimeError("Pipecat realtime pipeline is already started")

        runtime = self._runtime or import_pipecat_runtime(
            require_websocket=self._websocket is not None
        )
        self._runtime = runtime
        self._context = context
        self._config = config
        self._closed = False
        self._handle = build_pipecat_pipeline_handle(
            runtime=runtime,
            context=context,
            config=config,
            websocket=self._websocket,
            processors=(
                *build_pipecat_voice_processors(runtime, config, context=context),
                *self._processors,
            ),
            serializer=self._serializer,
            transport_params=self._transport_params,
        )
        await self._handle.runner.add_workers(self._handle.worker)
        self._handle.run_task = asyncio.create_task(
            self._handle.runner.run(), name="talkwise-pipecat-realtime"
        )

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self._require_open()
        assert self._handle is not None
        runtime = self._runtime or import_pipecat_runtime(
            require_websocket=self._websocket is not None
        )
        await self._handle.worker.queue_frame(
            runtime.InputAudioRawFrame(
                audio=chunk.data,
                sample_rate=_audio_sample_rate(chunk, self._config),
                num_channels=_audio_channels(chunk, self._config),
            )
        )

    async def commit_audio(self) -> None:
        self._require_open()
        handle = self._handle
        if handle is not None and hasattr(handle.worker, "flush_pipeline"):
            await handle.worker.flush_pipeline()

    async def events(self) -> AsyncIterator[Mapping[str, Any]]:
        self._require_started()
        assert self._handle is not None
        while True:
            event = await self._handle.event_queue.get()
            if event.get("type") == "talkwise.pipecat.closed":
                break
            yield event

    async def close(self) -> None:
        if self._handle is None or self._closed:
            return
        self._closed = True
        runtime = self._runtime or import_pipecat_runtime(
            require_websocket=self._websocket is not None
        )
        try:
            if hasattr(self._handle.worker, "end"):
                await self._handle.worker.end()
            elif hasattr(self._handle.worker, "queue_frame"):
                await self._handle.worker.queue_frame(runtime.EndFrame())
            if self._handle.run_task is not None:
                try:
                    await asyncio.wait_for(self._handle.run_task, timeout=5)
                except TimeoutError:
                    self._handle.run_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._handle.run_task
        finally:
            await self._handle.event_queue.put({"type": "talkwise.pipecat.closed"})

    def _require_started(self) -> None:
        if self._handle is None:
            raise RuntimeError("Pipecat realtime pipeline has not been started")

    def _require_open(self) -> None:
        self._require_started()
        if self._closed:
            raise RuntimeError("Pipecat realtime pipeline is closed")


def build_pipecat_pipeline_handle(
    *,
    runtime: PipecatRuntime,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
    websocket: Any | None = None,
    processors: Sequence[Any] = (),
    serializer: Any | None = None,
    transport_params: Any | Mapping[str, Any] | None = None,
) -> PipecatPipelineHandle:
    """Build Pipecat pipeline objects without starting their lifecycle."""

    event_queue: asyncio.Queue[Mapping[str, Any]] = asyncio.Queue()
    event_processor = create_talkwise_event_processor(runtime, event_queue, config=config)

    transport = None
    pipecat_processors = []
    if websocket is not None:
        if not runtime.websocket_available:
            raise RuntimeError("Pipecat FastAPI websocket transport is unavailable")
        params = _coerce_websocket_params(runtime, serializer, transport_params)
        transport = runtime.FastAPIWebsocketTransport(websocket=websocket, params=params)
        pipecat_processors.append(transport.input())

    pipecat_processors.extend(processors)
    pipecat_processors.append(event_processor)

    if transport is not None:
        pipecat_processors.append(transport.output())

    pipeline = runtime.Pipeline(pipecat_processors)
    worker = runtime.PipelineWorker(
        pipeline,
        params=_pipeline_params(runtime, context, config),
        enable_rtvi=False,
        name=f"talkwise-training-{context.binding.training_session_id}",
    )
    runner = runtime.WorkerRunner()

    return PipecatPipelineHandle(
        pipeline=pipeline,
        worker=worker,
        runner=runner,
        event_queue=event_queue,
        transport=transport,
        event_processor=event_processor,
    )


def build_pipecat_voice_processors(
    runtime: PipecatRuntime,
    config: RealtimePipelineConfig,
    *,
    context: TrainingVoiceContext | None = None,
) -> tuple[Any, ...]:
    """Build Pipecat-owned voice processors declared by provider-neutral config."""

    validate_pipecat_voice_config(config)
    processors: list[Any] = []
    metadata = dict(config.metadata)
    llm_provider = _feature_provider(metadata, "llm")

    if _feature_provider(metadata, "vad") == "silero":
        if runtime.SileroVADAnalyzer is None or runtime.VADProcessor is None:
            raise RuntimeError("Pipecat Silero VAD processor is unavailable")
        vad_config = _feature_config(metadata, "vad")
        vad_sample_rate = _metadata_int(
            vad_config,
            "sampleRate",
            "sample_rate",
            "vadSampleRate",
            "vad_sample_rate",
        ) or _metadata_int(
            metadata,
            "vadSampleRate",
            "vad_sample_rate",
            "sampleRate",
            "sample_rate",
        )
        vad_kwargs = _processor_kwargs(
            vad_config,
            allowed={
                "speechActivityPeriod": "speech_activity_period",
                "speech_activity_period": "speech_activity_period",
                "audioIdleTimeout": "audio_idle_timeout",
                "audio_idle_timeout": "audio_idle_timeout",
            },
        )
        vad_analyzer_kwargs: dict[str, Any] = {"sample_rate": vad_sample_rate}
        if vad_params := _vad_params(runtime, vad_config):
            vad_analyzer_kwargs["params"] = vad_params
        processors.append(
            runtime.VADProcessor(
                vad_analyzer=runtime.SileroVADAnalyzer(**vad_analyzer_kwargs),
                **vad_kwargs,
            )
        )

    stt_provider = _feature_provider(metadata, "stt")
    if stt_provider == "openai":
        if runtime.OpenAIRealtimeSTTService is None:
            raise RuntimeError("Pipecat OpenAI realtime STT service is unavailable")
        stt_config = _feature_config(metadata, "stt")
        api_key = _openai_api_key(metadata)
        if not api_key:
            raise RuntimeError("OpenAI API key is required for Pipecat OpenAI STT")
        processors.append(
            runtime.OpenAIRealtimeSTTService(
                api_key=api_key,
                model=_metadata_text(stt_config, "model")
                or _metadata_text(metadata, "sttModel", "stt_model")
                or config.model,
                base_url=_metadata_text(stt_config, "baseUrl", "base_url")
                or "wss://api.openai.com/v1/realtime",
                language=_metadata_text(stt_config, "language"),
                prompt=_metadata_text(stt_config, "prompt"),
                turn_detection=_turn_detection_config(metadata),
                noise_reduction=_metadata_text(
                    stt_config,
                    "noiseReduction",
                    "noise_reduction",
                )
                or _metadata_text(metadata, "noiseReduction", "noise_reduction"),
                should_interrupt=_metadata_bool(
                    stt_config,
                    "shouldInterrupt",
                    "should_interrupt",
                    default=True,
                ),
            )
        )

    if (
        _feature_provider(metadata, "turnDetection", "turn_detection") == "pipecat"
        and llm_provider is None
    ):
        if runtime.UserTurnProcessor is None:
            raise RuntimeError("Pipecat user turn processor is unavailable")
        turn_config = _feature_config(metadata, "turnDetection", "turn_detection")
        turn_kwargs: dict[str, Any] = {
            "user_turn_stop_timeout": _metadata_float(
                turn_config,
                "userTurnStopTimeout",
                "user_turn_stop_timeout",
                default=5.0,
            ),
            "user_idle_timeout": _metadata_float(
                turn_config,
                "userIdleTimeout",
                "user_idle_timeout",
                default=0,
            ),
        }
        user_turn_strategies = _user_turn_strategies(runtime, turn_config)
        if user_turn_strategies is not None:
            turn_kwargs["user_turn_strategies"] = user_turn_strategies
        processors.append(runtime.UserTurnProcessor(**turn_kwargs))

    assistant_aggregator = None
    if llm_provider == "openai":
        user_aggregator, llm, assistant_aggregator = build_pipecat_llm_processors(
            runtime,
            config,
            context=context,
        )
        processors.append(user_aggregator)
        processors.append(llm)

    tts_provider = _feature_provider(metadata, "tts")
    if tts_provider == "openai":
        if runtime.OpenAITTSService is None:
            raise RuntimeError("Pipecat OpenAI TTS service is unavailable")
        tts_config = _feature_config(metadata, "tts")
        api_key = _openai_api_key(metadata)
        if not api_key:
            raise RuntimeError("OpenAI API key is required for Pipecat OpenAI TTS")
        processors.append(
            runtime.OpenAITTSService(
                api_key=api_key,
                base_url=_metadata_text(tts_config, "baseUrl", "base_url"),
                model=_metadata_text(tts_config, "model")
                or _metadata_text(metadata, "ttsModel", "tts_model"),
                voice=config.voice
                or _metadata_text(tts_config, "voice")
                or _metadata_text(metadata, "voice"),
                instructions=config.instructions or _metadata_text(tts_config, "instructions"),
                sample_rate=_metadata_int(tts_config, "sampleRate", "sample_rate")
                or _metadata_int(metadata, "outputSampleRate", "output_sample_rate"),
                speed=_metadata_float(tts_config, "speed"),
            )
        )

    if assistant_aggregator is not None:
        processors.append(assistant_aggregator)

    return tuple(processors)


def build_pipecat_llm_processors(
    runtime: PipecatRuntime,
    config: RealtimePipelineConfig,
    *,
    context: TrainingVoiceContext | None = None,
) -> tuple[Any, Any, Any]:
    """Build Pipecat-native LLM context, aggregators, and OpenAI LLM processor."""

    if runtime.OpenAILLMService is None:
        raise RuntimeError("Pipecat OpenAI LLM service is unavailable")
    if (
        runtime.LLMContext is None
        or runtime.LLMContextAggregatorPair is None
        or runtime.LLMUserAggregatorParams is None
        or runtime.LLMAssistantAggregatorParams is None
    ):
        raise RuntimeError("Pipecat LLM context aggregators are unavailable")

    metadata = dict(config.metadata)
    llm_config = _feature_config(metadata, "llm")
    api_key = (
        _metadata_text(llm_config, "openaiApiKey", "openai_api_key", "apiKey", "api_key")
        or _openai_api_key(metadata)
    )
    if not api_key:
        raise RuntimeError("OpenAI API key is required for Pipecat OpenAI LLM")

    settings_kwargs: dict[str, Any] = {}
    model = (
        _metadata_text(llm_config, "model")
        or _metadata_text(metadata, "llmModel", "llm_model")
        or config.model
    )
    if model:
        settings_kwargs["model"] = model
    system_instruction = _llm_system_instruction(context, config)
    if system_instruction:
        settings_kwargs["system_instruction"] = system_instruction
    temperature = _metadata_float(llm_config, "temperature")
    if temperature is not None:
        settings_kwargs["temperature"] = temperature
    max_completion_tokens = _metadata_int(
        llm_config,
        "maxCompletionTokens",
        "max_completion_tokens",
        "maxTokens",
        "max_tokens",
    )
    if max_completion_tokens is not None:
        settings_kwargs["max_completion_tokens"] = max_completion_tokens

    llm = runtime.OpenAILLMService(
        api_key=api_key,
        base_url=_metadata_text(llm_config, "baseUrl", "base_url")
        or _metadata_text(metadata, "llmBaseUrl", "llm_base_url"),
        settings=runtime.OpenAILLMService.Settings(**settings_kwargs),
    )
    llm_context = runtime.LLMContext(messages=_llm_context_messages(context))
    context_config = _feature_config(metadata, "context")
    user_aggregator, assistant_aggregator = runtime.LLMContextAggregatorPair(
        llm_context,
        user_params=_llm_user_aggregator_params(runtime, metadata),
        assistant_params=runtime.LLMAssistantAggregatorParams(),
        realtime_service_mode=_metadata_bool(
            context_config,
            "realtimeServiceMode",
            "realtime_service_mode",
            default=False,
        ),
    )
    return user_aggregator, llm, assistant_aggregator


def pipecat_pipeline_capability(
    *,
    runtime: PipecatRuntime | None,
    config: RealtimePipelineConfig,
    websocket: Any | None = None,
) -> RealtimePipelineCapability:
    """Describe which realtime pieces Pipecat, not TalkWise, is expected to own."""

    capability = get_pipecat_capability(require_websocket=websocket is not None)
    metadata = dict(config.metadata)
    missing: list[str] = []
    if _feature_provider(metadata, "stt") == "openai" and not capability.stt_available:
        missing.append("stt:openai")
    if _feature_provider(metadata, "tts") == "openai" and not capability.tts_available:
        missing.append("tts:openai")
    if _feature_provider(metadata, "llm") == "openai" and not capability.llm_available:
        missing.append("llm:openai")
    if _feature_provider(metadata, "vad") == "silero" and not capability.vad_available:
        missing.append("vad:silero")
    if (
        _feature_provider(metadata, "turnDetection", "turn_detection") == "pipecat"
        and not capability.turn_detection_available
    ):
        missing.append("turn_detection:pipecat")

    return RealtimePipelineCapability(
        provider=config.provider,
        core_available=capability.core_available,
        media_transport="pipecat.websocket" if websocket is not None else "talkwise.audio_chunks",
        stt=_feature_provider(metadata, "stt"),
        tts=_feature_provider(metadata, "tts"),
        vad=_feature_provider(metadata, "vad"),
        turn_detection=_feature_provider(metadata, "turnDetection", "turn_detection"),
        missing_features=tuple(missing),
        metadata={
            "coreAvailable": capability.core_available,
            "websocketAvailable": capability.websocket_available,
            "sttAvailable": capability.stt_available,
            "ttsAvailable": capability.tts_available,
            "llmAvailable": capability.llm_available,
            "vadAvailable": capability.vad_available,
            "turnDetectionAvailable": capability.turn_detection_available,
            "requestedFeatures": {
                "stt": _feature_provider(metadata, "stt"),
                "tts": _feature_provider(metadata, "tts"),
                "llm": _feature_provider(metadata, "llm"),
                "vad": _feature_provider(metadata, "vad"),
                "turnDetection": _feature_provider(metadata, "turnDetection", "turn_detection"),
            },
            "optionalMissingModules": capability.optional_missing_modules,
            "runtimeLoaded": runtime is not None,
            "vadEntrypoint": SILERO_VAD_PIPECAT_MODULE,
            "sttEntrypoint": OPENAI_STT_PIPECAT_MODULE,
            "ttsEntrypoint": OPENAI_TTS_PIPECAT_MODULE,
            "llmEntrypoint": OPENAI_LLM_PIPECAT_MODULE,
            "turnDetectionEntrypoint": USER_TURN_PROCESSOR_PIPECAT_MODULE,
        },
    )


def create_talkwise_event_processor(
    runtime: PipecatRuntime,
    event_queue: asyncio.Queue[Mapping[str, Any]],
    *,
    config: RealtimePipelineConfig,
) -> Any:
    """Create a small Pipecat processor that mirrors final transcript frames."""

    class TalkWiseEventProcessor(runtime.FrameProcessor):  # type: ignore[misc, valid-type]
        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)
            event = _event_from_pipecat_frame(runtime, frame, config=config)
            if event is not None:
                await event_queue.put(event)
            await self.push_frame(frame, direction)

    return TalkWiseEventProcessor(name="TalkWiseEventProcessor")


def _event_from_pipecat_frame(
    runtime: PipecatRuntime,
    frame: Any,
    *,
    config: RealtimePipelineConfig,
) -> Mapping[str, Any] | None:
    if runtime.InterimTranscriptionFrame is not None and isinstance(
        frame, runtime.InterimTranscriptionFrame
    ):
        user_id = getattr(frame, "user_id", None)
        text = getattr(frame, "text", "")
        event: dict[str, Any] = {
            "type": "transcript.delta",
            "text": text,
            "delta": text,
            "provider": config.provider,
            "source": "pipecat",
            "user_id": user_id,
            "sender_id": user_id,
            "language": str(getattr(frame, "language", "") or "") or None,
            "timestamp": getattr(frame, "timestamp", None),
        }
        return _with_frame_metadata(event, frame, config=config)
    if isinstance(frame, runtime.TranscriptionFrame):
        user_id = getattr(frame, "user_id", None)
        event: dict[str, Any] = {
            "type": "transcript.done",
            "text": frame.text,
            "provider": config.provider,
            "source": "pipecat",
            "user_id": user_id,
            "sender_id": user_id,
            "language": str(getattr(frame, "language", "") or "") or None,
            "timestamp": getattr(frame, "timestamp", None),
        }
        return _with_frame_metadata(event, frame, config=config)
    if isinstance(frame, runtime.LLMContextAssistantTurnFrame):
        event = {
            "type": "response.audio_transcript.done",
            "text": frame.text,
            "provider": config.provider,
            "source": "pipecat",
            "timestamp": getattr(frame, "timestamp", None),
        }
        return _with_frame_metadata(event, frame, config=config)
    return None


def _with_frame_metadata(
    event: dict[str, Any],
    frame: Any,
    *,
    config: RealtimePipelineConfig,
) -> dict[str, Any]:
    metadata = _frame_event_metadata(frame)
    talkwise_metadata = _json_safe_metadata(
        config.metadata.get("talkwise") or config.metadata.get("talkwiseMetadata")
    )
    if isinstance(talkwise_metadata, Mapping):
        metadata.setdefault("talkwise", dict(talkwise_metadata))
    if metadata:
        event["metadata"] = metadata
    return event


def _frame_event_metadata(frame: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    raw_metadata = getattr(frame, "metadata", None)
    if isinstance(raw_metadata, Mapping):
        for key, value in raw_metadata.items():
            safe_value = _json_safe_metadata(value)
            if safe_value is not None:
                metadata[str(key)] = safe_value

    pipecat_frame: dict[str, Any] = {}
    for output_key, attr_name in {
        "frameId": "id",
        "frameName": "name",
        "pts": "pts",
    }.items():
        safe_value = _json_safe_metadata(getattr(frame, attr_name, None))
        if safe_value is not None:
            pipecat_frame[output_key] = safe_value
    if pipecat_frame:
        metadata["pipecatFrame"] = pipecat_frame
    return metadata


def _json_safe_metadata(value: Any) -> Any | None:
    if isinstance(value, str | int | float | bool):
        return value
    if value is None:
        return None
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe_item = _json_safe_metadata(item)
            if safe_item is not None:
                result[str(key)] = safe_item
        return result or None
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        result = [
            safe_item for item in value if (safe_item := _json_safe_metadata(item)) is not None
        ]
        return result or None
    return None


def _llm_system_instruction(
    context: TrainingVoiceContext | None,
    config: RealtimePipelineConfig,
) -> str | None:
    parts: list[str] = []
    if config.instructions and config.instructions.strip():
        parts.append(config.instructions.strip())
    if context is not None:
        if context.task_goal:
            parts.append(f"Training goal: {context.task_goal}")
        if context.rubric:
            rubric = _compact_json(context.rubric)
            if rubric:
                parts.append(f"Rubric: {rubric}")
        metadata = dict(context.metadata)
        persona_ids = metadata.get("personaIds") or metadata.get("persona_ids")
        if persona_ids:
            rendered = _compact_json(persona_ids)
            if rendered:
                parts.append(f"Persona IDs: {rendered}")
        scenario_id = metadata.get("scenarioId") or metadata.get("scenario_id")
        if scenario_id:
            rendered = _compact_json(scenario_id)
            if rendered:
                parts.append(f"Scenario ID: {rendered}")
        active_persona = _active_persona_from_metadata(metadata)
        if active_persona:
            parts.append(f"Active persona ID: {active_persona}")
    if len(parts) > 1:
        parts.append(
            "Use this context to run the role-play; do not produce a long evaluation during the call."
        )
    return "\n\n".join(parts) or None


def _llm_context_messages(context: TrainingVoiceContext | None) -> list[dict[str, str]]:
    if context is None:
        return []

    messages: list[dict[str, str]] = []
    for turn in context.recent_turns:
        text = _metadata_text(turn, "text", "content", "transcript")
        if not text:
            continue
        messages.append({"role": _llm_message_role(turn), "content": text})
    return messages


def _llm_message_role(turn: Mapping[str, Any]) -> str:
    raw_role = turn.get("role") or turn.get("speaker")
    role = str(raw_role or "").strip().lower()
    if role in {"assistant", "agent", "coach", "counterpart", "model", "persona"}:
        return "assistant"
    return "user"


def _active_persona_from_metadata(metadata: Mapping[str, Any]) -> str | None:
    dispatcher = metadata.get("dispatcher")
    if not isinstance(dispatcher, Mapping):
        return None
    return _metadata_text(
        dispatcher,
        "activePersonaId",
        "active_persona_id",
        "selectedPersonaId",
        "selected_persona_id",
        "personaId",
        "persona_id",
    )


def _compact_json(value: Any, *, max_chars: int = 1200) -> str | None:
    safe_value = _json_safe_metadata(value)
    if safe_value is None:
        return None
    text = json.dumps(safe_value, ensure_ascii=False, sort_keys=True)
    if len(text) > max_chars:
        return f"{text[:max_chars]}..."
    return text


def _coerce_websocket_params(
    runtime: PipecatRuntime,
    serializer: Any | None,
    transport_params: Any | Mapping[str, Any] | None,
) -> Any:
    if transport_params is not None and not isinstance(transport_params, Mapping):
        return transport_params

    values = dict(transport_params or {})
    if serializer is not None:
        values.setdefault("serializer", serializer)
    return runtime.FastAPIWebsocketParams(**values)


def _start_metadata(
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
) -> dict[str, Any]:
    return {
        "source": "talkwise",
        "provider": config.provider,
        "model": config.model,
        "voice": config.voice,
        "trainingSessionId": context.binding.training_session_id,
        "roomId": context.binding.room_id,
        "taskGoal": context.task_goal,
        "rubric": dict(context.rubric),
        "metadata": {**dict(context.metadata), **dict(config.metadata)},
    }


def _pipeline_params(
    runtime: PipecatRuntime,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
) -> Any:
    values: dict[str, Any] = {"start_metadata": _start_metadata(context, config)}
    audio_in_sample_rate = _audio_in_sample_rate(config)
    audio_out_sample_rate = _audio_out_sample_rate(config)
    if audio_in_sample_rate is not None:
        values["audio_in_sample_rate"] = audio_in_sample_rate
    if audio_out_sample_rate is not None:
        values["audio_out_sample_rate"] = audio_out_sample_rate
    return runtime.PipelineParams(**values)


def _audio_in_sample_rate(config: RealtimePipelineConfig) -> int | None:
    metadata = dict(config.metadata)
    return _metadata_int(
        metadata,
        "audioInSampleRate",
        "audio_in_sample_rate",
        "inputSampleRate",
        "input_sample_rate",
        "sampleRate",
        "sample_rate",
    )


def _audio_out_sample_rate(config: RealtimePipelineConfig) -> int | None:
    metadata = dict(config.metadata)
    return _metadata_int(
        metadata,
        "audioOutSampleRate",
        "audio_out_sample_rate",
        "outputSampleRate",
        "output_sample_rate",
    )


def _audio_sample_rate(
    chunk: RealtimeAudioChunk,
    config: RealtimePipelineConfig | None,
) -> int:
    value = (
        chunk.metadata.get("sample_rate")
        or chunk.metadata.get("sampleRate")
        or chunk.metadata.get("input_sample_rate")
        or chunk.metadata.get("inputSampleRate")
    )
    if value is None and config is not None:
        value = _audio_in_sample_rate(config)
    return int(value or 16000)


def _audio_channels(
    chunk: RealtimeAudioChunk,
    config: RealtimePipelineConfig | None,
) -> int:
    value = chunk.metadata.get("channels") or chunk.metadata.get("num_channels")
    if value is None and config is not None:
        value = config.metadata.get("channels") or config.metadata.get("num_channels")
    return int(value or 1)


def _feature_provider(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, Mapping):
            value = value.get("provider")
        if isinstance(value, str):
            text = value.strip().lower()
            if text and text not in {"none", "false", "disabled"}:
                return text
    return None


def _feature_config(metadata: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _metadata_text(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _metadata_int(metadata: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return int(value)
    return None


def _metadata_float(
    metadata: Mapping[str, Any],
    *keys: str,
    default: float | None = None,
) -> float | None:
    for key in keys:
        value = metadata.get(key)
        if value is not None:
            return float(value)
    return default


def _metadata_bool(
    metadata: Mapping[str, Any],
    *keys: str,
    default: bool | None = None,
) -> bool | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False
    return default


def _processor_kwargs(
    metadata: Mapping[str, Any],
    *,
    allowed: Mapping[str, str],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    for source_key, target_key in allowed.items():
        if source_key in metadata:
            kwargs[target_key] = metadata[source_key]
    return kwargs


def _vad_params(runtime: PipecatRuntime, metadata: Mapping[str, Any]) -> Any | None:
    vad_kwargs = _processor_kwargs(
        metadata,
        allowed={
            "confidence": "confidence",
            "startSecs": "start_secs",
            "start_secs": "start_secs",
            "stopSecs": "stop_secs",
            "stop_secs": "stop_secs",
            "minVolume": "min_volume",
            "min_volume": "min_volume",
        },
    )
    if not vad_kwargs:
        return None
    if runtime.VADParams is None:
        raise RuntimeError("Pipecat VAD params are unavailable")
    return runtime.VADParams(**vad_kwargs)


def _llm_user_aggregator_params(
    runtime: PipecatRuntime,
    metadata: Mapping[str, Any],
) -> Any:
    turn_config = _feature_config(metadata, "turnDetection", "turn_detection")
    kwargs: dict[str, Any] = {}
    user_turn_stop_timeout = _metadata_float(
        turn_config,
        "userTurnStopTimeout",
        "user_turn_stop_timeout",
    )
    if user_turn_stop_timeout is not None:
        kwargs["user_turn_stop_timeout"] = user_turn_stop_timeout
    user_idle_timeout = _metadata_float(
        turn_config,
        "userIdleTimeout",
        "user_idle_timeout",
    )
    if user_idle_timeout is not None:
        kwargs["user_idle_timeout"] = user_idle_timeout
    if user_turn_strategies := _user_turn_strategies(runtime, turn_config):
        kwargs["user_turn_strategies"] = user_turn_strategies
    filter_incomplete = _metadata_bool(
        turn_config,
        "filterIncompleteUserTurns",
        "filter_incomplete_user_turns",
        default=None,
    )
    if filter_incomplete is not None:
        kwargs["filter_incomplete_user_turns"] = filter_incomplete
    if completion_config := _user_turn_completion_config(runtime, turn_config):
        kwargs["user_turn_completion_config"] = completion_config
    return runtime.LLMUserAggregatorParams(**kwargs)


def _openai_api_key(metadata: Mapping[str, Any]) -> str | None:
    return (
        _metadata_text(metadata, "openaiApiKey", "openai_api_key", "apiKey", "api_key")
        or _settings_openai_api_key()
        or os.getenv("REALTIME_OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )


def _settings_openai_api_key() -> str | None:
    try:
        from core.config import settings as app_settings
    except Exception:
        return None
    return (
        app_settings.REALTIME_OPENAI_API_KEY
        or getattr(app_settings.llm, "api_key", None)
        or getattr(app_settings, "OPENAI_API_KEY", None)
    )


def _turn_detection_config(metadata: Mapping[str, Any]) -> Mapping[str, Any] | bool | None:
    stt_config = _feature_config(metadata, "stt")
    value = (
        stt_config.get("turnDetection")
        or stt_config.get("turn_detection")
        or metadata.get("sttTurnDetection")
        or metadata.get("stt_turn_detection")
    )
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"server", "server_vad"}:
            return None
        if text in {"disabled", "false", "local"}:
            return False
    return False


def _user_turn_strategies(runtime: PipecatRuntime, metadata: Mapping[str, Any]) -> Any | None:
    strategy = _user_turn_strategy_name(metadata)
    if strategy is None:
        return None

    if strategy == "external":
        if runtime.ExternalUserTurnStrategies is None:
            raise RuntimeError("Pipecat external user turn strategies are unavailable")
        return runtime.ExternalUserTurnStrategies()

    if runtime.FilterIncompleteUserTurnStrategies is None:
        raise RuntimeError("Pipecat filter-incomplete user turn strategies are unavailable")
    completion_config = _user_turn_completion_config(runtime, metadata)
    if completion_config is None:
        return runtime.FilterIncompleteUserTurnStrategies()
    return runtime.FilterIncompleteUserTurnStrategies(config=completion_config)


def _user_turn_strategy_name(metadata: Mapping[str, Any]) -> str | None:
    selected = _metadata_text(
        metadata,
        "userTurnStrategies",
        "user_turn_strategies",
        "userTurnStrategy",
        "user_turn_strategy",
        "strategy",
    )
    if selected is None and _metadata_bool(
        metadata,
        "filterIncompleteUserTurns",
        "filter_incomplete_user_turns",
        default=False,
    ):
        selected = "filter_incomplete"
    if selected is None:
        return None

    normalized = selected.strip().lower().replace("-", "_").replace(" ", "_")
    compact = normalized.replace("_", "")
    if compact in {"", "default", "none", "false", "disabled", "pipecat"}:
        return None
    if compact in {"external", "externaluserturn", "externaluserturnstrategies"}:
        return "external"
    if compact in {
        "filterincomplete",
        "filterincompleteuserturn",
        "filterincompleteuserturns",
        "filterincompleteuserturnstrategies",
    }:
        return "filter_incomplete"
    raise ValueError(
        "Unsupported Pipecat user turn strategy "
        f"'{selected}'; expected external or filter_incomplete"
    )


def _user_turn_completion_config(
    runtime: PipecatRuntime,
    metadata: Mapping[str, Any],
) -> Any | None:
    completion_metadata = _user_turn_completion_metadata(metadata)
    if not completion_metadata:
        return None

    kwargs: dict[str, Any] = {}
    if instructions := _metadata_text(completion_metadata, "instructions"):
        kwargs["instructions"] = instructions
    incomplete_short_timeout = _metadata_float(
        completion_metadata,
        "incompleteShortTimeout",
        "incomplete_short_timeout",
    )
    if incomplete_short_timeout is not None:
        kwargs["incomplete_short_timeout"] = incomplete_short_timeout
    incomplete_long_timeout = _metadata_float(
        completion_metadata,
        "incompleteLongTimeout",
        "incomplete_long_timeout",
    )
    if incomplete_long_timeout is not None:
        kwargs["incomplete_long_timeout"] = incomplete_long_timeout
    if incomplete_short_prompt := _metadata_text(
        completion_metadata,
        "incompleteShortPrompt",
        "incomplete_short_prompt",
    ):
        kwargs["incomplete_short_prompt"] = incomplete_short_prompt
    if incomplete_long_prompt := _metadata_text(
        completion_metadata,
        "incompleteLongPrompt",
        "incomplete_long_prompt",
    ):
        kwargs["incomplete_long_prompt"] = incomplete_long_prompt

    if not kwargs:
        return None
    if runtime.UserTurnCompletionConfig is None:
        raise RuntimeError("Pipecat user turn completion config is unavailable")
    return runtime.UserTurnCompletionConfig(**kwargs)


def _user_turn_completion_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in (
        "userTurnCompletionConfig",
        "user_turn_completion_config",
        "completionConfig",
        "completion_config",
        "filterIncompleteUserTurns",
        "filter_incomplete_user_turns",
        "filterIncomplete",
        "filter_incomplete",
    ):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            return value

    direct_config_keys = {
        "instructions",
        "incompleteShortTimeout",
        "incomplete_short_timeout",
        "incompleteLongTimeout",
        "incomplete_long_timeout",
        "incompleteShortPrompt",
        "incomplete_short_prompt",
        "incompleteLongPrompt",
        "incomplete_long_prompt",
    }
    if any(key in metadata for key in direct_config_keys):
        return metadata
    return {}


def validate_pipecat_voice_config(config: RealtimePipelineConfig) -> None:
    """Validate supported Pipecat-owned voice chain options before constructing services."""

    metadata = dict(config.metadata)
    _validate_provider(metadata, "stt", supported={"openai"})
    _validate_provider(metadata, "tts", supported={"openai"})
    _validate_provider(metadata, "llm", supported={"openai"})
    _validate_provider(metadata, "vad", supported={"silero"})
    _validate_provider(metadata, "turnDetection", "turn_detection", supported={"pipecat"})
    if _feature_provider(metadata, "turnDetection", "turn_detection") == "pipecat":
        _user_turn_strategy_name(_feature_config(metadata, "turnDetection", "turn_detection"))

    vad_provider = _feature_provider(metadata, "vad")
    stt_provider = _feature_provider(metadata, "stt")
    stt_turn_detection = _turn_detection_config(metadata)
    if vad_provider == "silero" and stt_provider == "openai" and stt_turn_detection is not False:
        raise ValueError(
            "Pipecat OpenAI STT server-side turn detection cannot be combined with Silero VAD"
        )

    vad_config = _feature_config(metadata, "vad")
    vad_sample_rate = _metadata_int(
        vad_config,
        "sampleRate",
        "sample_rate",
        "vadSampleRate",
        "vad_sample_rate",
    ) or _metadata_int(metadata, "vadSampleRate", "vad_sample_rate")
    if vad_provider == "silero" and vad_sample_rate not in {None, 8000, 16000}:
        raise ValueError("Silero VAD sample rate must be 8000 or 16000")

    noise_reduction = _metadata_text(
        _feature_config(metadata, "stt"),
        "noiseReduction",
        "noise_reduction",
    ) or _metadata_text(metadata, "noiseReduction", "noise_reduction")
    if noise_reduction is not None and noise_reduction not in {"near_field", "far_field"}:
        raise ValueError("OpenAI realtime STT noise reduction must be near_field or far_field")

    tts_speed = _metadata_float(_feature_config(metadata, "tts"), "speed")
    if tts_speed is not None and not 0.25 <= tts_speed <= 4.0:
        raise ValueError("OpenAI TTS speed must be between 0.25 and 4.0")

    llm_temperature = _metadata_float(_feature_config(metadata, "llm"), "temperature")
    if llm_temperature is not None and not 0 <= llm_temperature <= 2:
        raise ValueError("OpenAI LLM temperature must be between 0 and 2")


def _validate_provider(
    metadata: Mapping[str, Any],
    *keys: str,
    supported: set[str],
) -> None:
    provider = _feature_provider(metadata, *keys)
    if provider is not None and provider not in supported:
        feature = keys[0]
        supported_text = ", ".join(sorted(supported))
        raise ValueError(
            f"Unsupported Pipecat {feature} provider '{provider}'; expected {supported_text}"
        )


def pipecat_source_snapshot() -> Mapping[str, Any]:
    """Summarize the Pipecat entrypoints this adapter intentionally reuses."""

    return {
        "checkedAt": datetime.now(UTC).isoformat(),
        "coreEntrypoints": (
            "pipecat.pipeline.pipeline.Pipeline",
            "pipecat.pipeline.worker.PipelineWorker",
            "pipecat.workers.runner.WorkerRunner",
        ),
        "frameEntrypoints": (
            "pipecat.frames.frames.InputAudioRawFrame",
            "pipecat.frames.frames.InterimTranscriptionFrame",
            "pipecat.frames.frames.TranscriptionFrame",
            "pipecat.frames.frames.LLMContextAssistantTurnFrame",
            "pipecat.frames.frames.UserStartedSpeakingFrame",
            "pipecat.frames.frames.UserStoppedSpeakingFrame",
        ),
        "websocketEntrypoint": ("pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport"),
        "vadParamsEntrypoint": ("pipecat.audio.vad.vad_analyzer.VADParams"),
        "vadEntrypoint": ("pipecat.audio.vad.silero.SileroVADAnalyzer"),
        "vadProcessorEntrypoint": ("pipecat.processors.audio.vad_processor.VADProcessor"),
        "sttEntrypoint": ("pipecat.services.openai.stt.OpenAIRealtimeSTTService"),
        "ttsEntrypoint": ("pipecat.services.openai.tts.OpenAITTSService"),
        "llmEntrypoint": ("pipecat.services.openai.llm.OpenAILLMService"),
        "llmContextEntrypoints": (
            "pipecat.processors.aggregators.llm_context.LLMContext",
            "pipecat.processors.aggregators.llm_response_universal.LLMContextAggregatorPair",
        ),
        "turnDetectionEntrypoint": ("pipecat.turns.user_turn_processor.UserTurnProcessor"),
        "turnStrategyEntrypoints": (
            "pipecat.turns.user_turn_strategies.ExternalUserTurnStrategies",
            "pipecat.turns.user_turn_strategies.FilterIncompleteUserTurnStrategies",
        ),
        "talkwiseResponsibilities": (
            "optional import and capability detection",
            "pipeline factory configuration",
            "RealtimeAudioChunk to InputAudioRawFrame adaptation",
            "TrainingVoiceContext to LLMContext seed adaptation",
            "interim transcript frame mirroring",
            "final transcript frame mirroring",
        ),
    }


__all__ = [
    "PipecatCapability",
    "PipecatPipelineHandle",
    "PipecatRealtimePipelineAdapter",
    "PipecatRuntime",
    "build_pipecat_pipeline_handle",
    "build_pipecat_llm_processors",
    "build_pipecat_voice_processors",
    "create_pipecat_realtime_pipeline",
    "create_talkwise_event_processor",
    "get_pipecat_capability",
    "import_pipecat_runtime",
    "is_pipecat_available",
    "pipecat_pipeline_capability",
    "pipecat_source_snapshot",
    "validate_pipecat_voice_config",
]
