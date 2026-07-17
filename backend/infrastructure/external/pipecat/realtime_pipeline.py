"""Optional Pipecat realtime pipeline adapter.

Pipecat owns media transport, frame flow, and lifecycle management when it is
installed. This module keeps TalkWise integration thin: capability detection,
dependency-safe factories, and DTO-to-frame adaptation only.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from application.ports.realtime import (
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
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
OPENAI_STT_PIPECAT_MODULE = "pipecat.services.openai.stt"
OPENAI_TTS_PIPECAT_MODULE = "pipecat.services.openai.tts"
OPTIONAL_PIPECAT_FEATURE_MODULES = {
    "vad": (SILERO_VAD_PIPECAT_MODULE, "onnxruntime"),
    "stt": (OPENAI_STT_PIPECAT_MODULE, "websockets"),
    "tts": (OPENAI_TTS_PIPECAT_MODULE, "openai"),
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
    FastAPIWebsocketParams: type | None = None
    FastAPIWebsocketTransport: type | None = None

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
        **optional_status,
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
        "optional_missing_modules": tuple(
            module for modules in missing_by_feature.values() for module in modules
        ),
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
        FastAPIWebsocketParams=websocket_params,
        FastAPIWebsocketTransport=websocket_transport,
    )


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
            processors=self._processors,
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
        params=runtime.PipelineParams(start_metadata=_start_metadata(context, config)),
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
        return _with_frame_metadata(event, frame)
    if isinstance(frame, runtime.LLMContextAssistantTurnFrame):
        event = {
            "type": "response.audio_transcript.done",
            "text": frame.text,
            "provider": config.provider,
            "source": "pipecat",
            "timestamp": getattr(frame, "timestamp", None),
        }
        return _with_frame_metadata(event, frame)
    return None


def _with_frame_metadata(event: dict[str, Any], frame: Any) -> dict[str, Any]:
    metadata = _frame_event_metadata(frame)
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


def _audio_sample_rate(
    chunk: RealtimeAudioChunk,
    config: RealtimePipelineConfig | None,
) -> int:
    value = chunk.metadata.get("sample_rate") or chunk.metadata.get("sampleRate")
    if value is None and config is not None:
        value = config.metadata.get("sample_rate") or config.metadata.get("sampleRate")
    return int(value or 16000)


def _audio_channels(
    chunk: RealtimeAudioChunk,
    config: RealtimePipelineConfig | None,
) -> int:
    value = chunk.metadata.get("channels") or chunk.metadata.get("num_channels")
    if value is None and config is not None:
        value = config.metadata.get("channels") or config.metadata.get("num_channels")
    return int(value or 1)


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
            "pipecat.frames.frames.TranscriptionFrame",
            "pipecat.frames.frames.LLMContextAssistantTurnFrame",
            "pipecat.frames.frames.UserStartedSpeakingFrame",
            "pipecat.frames.frames.UserStoppedSpeakingFrame",
        ),
        "websocketEntrypoint": ("pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport"),
        "vadEntrypoint": ("pipecat.audio.vad.silero.SileroVADAnalyzer"),
        "sttEntrypoint": ("pipecat.services.openai.stt.OpenAIRealtimeSTTService"),
        "ttsEntrypoint": ("pipecat.services.openai.tts.OpenAITTSService"),
        "talkwiseResponsibilities": (
            "optional import and capability detection",
            "pipeline factory configuration",
            "RealtimeAudioChunk to InputAudioRawFrame adaptation",
            "final transcript frame mirroring",
        ),
    }


__all__ = [
    "PipecatCapability",
    "PipecatPipelineHandle",
    "PipecatRealtimePipelineAdapter",
    "PipecatRuntime",
    "build_pipecat_pipeline_handle",
    "create_pipecat_realtime_pipeline",
    "create_talkwise_event_processor",
    "get_pipecat_capability",
    "import_pipecat_runtime",
    "is_pipecat_available",
    "pipecat_source_snapshot",
]
