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
import logging
import os
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from application.ports.realtime import (
    OPENAI_REALTIME_API_KEY_ENV_KEYS,
    REALTIME_RUNTIME_PIPECAT,
    RealtimeAudioChunk,
    RealtimeOutputAudio,
    RealtimePipelineAdapter,
    RealtimePipelineCapability,
    RealtimePipelineConfig,
    RealtimeProviderReadiness,
    RealtimeReadinessIssue,
    TrainingVoiceContext,
    build_realtime_readiness,
    classify_realtime_pipeline_start_error_message,
    normalize_realtime_runtime,
    redact_realtime_secret_text,
    sanitize_realtime_public_value,
)
from infrastructure.external.pipecat.provider_catalog import (
    pipecat_integrated_provider_modules,
    pipecat_provider_catalog,
    pipecat_provider_catalog_summary,
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
OPENAI_REALTIME_LLM_PIPECAT_MODULE = "pipecat.services.openai.realtime.llm"
OPENAI_REALTIME_EVENTS_PIPECAT_MODULE = "pipecat.services.openai.realtime.events"
OPENROUTER_LLM_PIPECAT_MODULE = "pipecat.services.openrouter.llm"
LLM_CONTEXT_PIPECAT_MODULE = "pipecat.processors.aggregators.llm_context"
LLM_RESPONSE_PIPECAT_MODULE = "pipecat.processors.aggregators.llm_response_universal"
USER_TURN_PROCESSOR_PIPECAT_MODULE = "pipecat.turns.user_turn_processor"
USER_TURN_STRATEGIES_PIPECAT_MODULE = "pipecat.turns.user_turn_strategies"
USER_TURN_COMPLETION_PIPECAT_MODULE = "pipecat.turns.user_turn_completion_mixin"
OPENAI_API_KEY_ENV_KEYS = OPENAI_REALTIME_API_KEY_ENV_KEYS
OPENAI_REALTIME_MODEL_SETTING = "REALTIME_OPENAI_MODEL"
OPENAI_REALTIME_VOICE_SETTING = "REALTIME_OPENAI_VOICE"
OPENAI_REALTIME_INPUT_AUDIO_FORMAT_SETTING = "REALTIME_OPENAI_INPUT_AUDIO_FORMAT"
_OPENAI_RUNTIME_VALUE_UNSET = object()
OPENROUTER_LLM_PROVIDER = "openrouter"
OPENROUTER_LLM_PROVIDER_ALIASES = {
    OPENROUTER_LLM_PROVIDER,
    "open_router",
    "openrouter_ai",
    "openrouter_compatible",
}
OPENROUTER_LLM_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY_ENV_KEYS = (
    "REALTIME_OPENROUTER_API_KEY",
    "OPENROUTER_API_KEY",
    "LLM__API_KEY",
)
OPENROUTER_BASE_URL_ENV_KEYS = (
    "REALTIME_OPENROUTER_BASE_URL",
    "OPENROUTER_BASE_URL",
    "LLM__BASE_URL",
)
PIPECAT_SUPPORTED_LLM_PROVIDERS = {"openai", OPENROUTER_LLM_PROVIDER}
PIPECAT_REALTIME_PROFILE_CASCADE = "cascade"
PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH = "speech_to_speech"
PIPECAT_REALTIME_PROFILE_ALIASES = {
    "cascade": PIPECAT_REALTIME_PROFILE_CASCADE,
    "cascaded": PIPECAT_REALTIME_PROFILE_CASCADE,
    "chain": PIPECAT_REALTIME_PROFILE_CASCADE,
    "near_realtime": PIPECAT_REALTIME_PROFILE_CASCADE,
    "stt_llm_tts": PIPECAT_REALTIME_PROFILE_CASCADE,
    "transcription_chain": PIPECAT_REALTIME_PROFILE_CASCADE,
    "speech_to_speech": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "speech2speech": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "speechtospeech": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "true_realtime": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "realtime_llm": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "openai_realtime": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "openai_speech_to_speech": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
}
PIPECAT_REALTIME_REQUIRED_FEATURES = {
    "stt": "openai",
    "tts": "openai",
    "llm": "openai",
    "vad": "silero",
    "turnDetection": "pipecat",
}
PIPECAT_REALTIME_SMOKE_CONTRACT_EVENTS = (
    "session.started",
    "audio.input",
    "audio.output",
    "transcript.delta",
    "transcript.done",
    "transcript.persisted",
    "training.live_guidance.triggered",
    "user_turn.started",
    "user_turn.stopped",
    "assistant_speaking.started",
    "assistant_speaking.stopped",
    "interrupted",
    "silence_timeout",
)
PIPECAT_REALTIME_SMOKE_EVENT_ORDER = {
    "finalTranscript": (
        "transcript.done",
        "transcript.persisted",
        "training.live_guidance.triggered",
    ),
    "assistantAudioThenTranscript": (
        "audio.output",
        "transcript.done",
        "transcript.persisted",
    ),
}
PIPECAT_REALTIME_SMOKE_ERROR_TAXONOMY = (
    {
        "errorCategory": "authentication",
        "code": "REALTIME_PROVIDER_AUTHENTICATION",
        "retryable": False,
        "fatal": True,
    },
    {
        "errorCategory": "rate_limit",
        "code": "REALTIME_PROVIDER_RATE_LIMIT",
        "retryable": True,
        "fatal": False,
    },
    {
        "errorCategory": "provider_unavailable",
        "code": "REALTIME_PROVIDER_UNAVAILABLE",
        "retryable": True,
        "fatal": True,
    },
    {
        "errorCategory": "bad_request",
        "code": "REALTIME_PROVIDER_BAD_REQUEST",
        "retryable": False,
        "fatal": True,
    },
    {
        "errorCategory": "provider_error",
        "code": "REALTIME_PROVIDER_ERROR",
        "retryable": False,
        "fatal": True,
    },
)
PIPECAT_REALTIME_BROWSER_AUDIO_E2E_SIGNALS = (
    "microphone_permission_and_capture",
    "websocket_audio_input",
    "provider_neutral_audio_output_playback",
    "turn_interruption_silence_events",
    "realtime_metrics_and_error_taxonomy",
)
PIPECAT_REALTIME_PROFILE_AUDIO = {
    PIPECAT_REALTIME_PROFILE_CASCADE: {
        "inputSampleRate": 16000,
        "outputSampleRate": 24000,
        "inputEncoding": "pcm16",
        "outputEncoding": "pcm16",
    },
    PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH: {
        "inputSampleRate": 24000,
        "outputSampleRate": 24000,
        "inputEncoding": "pcm16",
        "outputEncoding": "pcm16",
    },
}
PIPECAT_REALTIME_FEATURE_REQUIREMENTS = {
    "stt": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "stt:openai",
        "message": "Pipecat OpenAI STT service is required before starting realtime calls",
        "modules": (OPENAI_STT_PIPECAT_MODULE, "websockets"),
    },
    "tts": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "tts:openai",
        "message": "Pipecat OpenAI TTS service is required before starting realtime calls",
        "modules": (OPENAI_TTS_PIPECAT_MODULE, "openai"),
    },
    "llm": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "llm:openai",
        "message": "Pipecat OpenAI LLM service is required before starting realtime calls",
        "modules": (
            OPENAI_LLM_PIPECAT_MODULE,
            LLM_CONTEXT_PIPECAT_MODULE,
            LLM_RESPONSE_PIPECAT_MODULE,
        ),
    },
    "realtimeLlm": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "realtimeLlm:openai",
        "message": (
            "Pipecat OpenAI Realtime LLM service is required before starting "
            "speech-to-speech realtime calls"
        ),
        "modules": (
            OPENAI_REALTIME_LLM_PIPECAT_MODULE,
            OPENAI_REALTIME_EVENTS_PIPECAT_MODULE,
            LLM_CONTEXT_PIPECAT_MODULE,
            LLM_RESPONSE_PIPECAT_MODULE,
        ),
    },
    "vad": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "vad:silero",
        "message": "Pipecat Silero VAD processor is required before starting realtime calls",
        "modules": (
            SILERO_VAD_PIPECAT_MODULE,
            VAD_ANALYZER_PIPECAT_MODULE,
            VAD_PROCESSOR_PIPECAT_MODULE,
            "onnxruntime",
        ),
    },
    "turnDetection": {
        "code": "PIPECAT_FEATURE_UNAVAILABLE",
        "feature": "turnDetection:pipecat",
        "message": "Pipecat user turn detection is required before starting realtime calls",
        "modules": (
            USER_TURN_PROCESSOR_PIPECAT_MODULE,
            USER_TURN_STRATEGIES_PIPECAT_MODULE,
            USER_TURN_COMPLETION_PIPECAT_MODULE,
        ),
    },
}
PIPECAT_OPENROUTER_LLM_FEATURE_REQUIREMENT = {
    "code": "PIPECAT_FEATURE_UNAVAILABLE",
    "feature": "llm:openrouter",
    "message": ("Pipecat OpenRouter LLM service is required before starting realtime calls"),
    "modules": (
        OPENROUTER_LLM_PIPECAT_MODULE,
        LLM_CONTEXT_PIPECAT_MODULE,
        LLM_RESPONSE_PIPECAT_MODULE,
    ),
}
PIPECAT_FEATURE_MODULE_HINTS = {
    "stt": (OPENAI_STT_PIPECAT_MODULE, "websockets"),
    "tts": (OPENAI_TTS_PIPECAT_MODULE, "openai"),
    "llm": (
        OPENAI_LLM_PIPECAT_MODULE,
        LLM_CONTEXT_PIPECAT_MODULE,
        LLM_RESPONSE_PIPECAT_MODULE,
    ),
    "realtimeLlm": (
        OPENAI_REALTIME_LLM_PIPECAT_MODULE,
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE,
        LLM_CONTEXT_PIPECAT_MODULE,
        LLM_RESPONSE_PIPECAT_MODULE,
    ),
    "vad": (
        SILERO_VAD_PIPECAT_MODULE,
        VAD_ANALYZER_PIPECAT_MODULE,
        VAD_PROCESSOR_PIPECAT_MODULE,
        "onnxruntime",
    ),
    "turnDetection": (
        USER_TURN_PROCESSOR_PIPECAT_MODULE,
        USER_TURN_STRATEGIES_PIPECAT_MODULE,
        USER_TURN_COMPLETION_PIPECAT_MODULE,
    ),
}
logger = logging.getLogger(__name__)
CORE_PIPECAT_SYMBOLS: Mapping[str, tuple[str, ...]] = {
    "pipecat.pipeline.pipeline": ("Pipeline",),
    "pipecat.pipeline.worker": ("PipelineParams", "PipelineWorker"),
    "pipecat.workers.base_worker": ("WorkerParams",),
    "pipecat.workers.runner": ("WorkerRunner",),
    "pipecat.frames.frames": (
        "InputAudioRawFrame",
        "EndFrame",
        "TextFrame",
        "TranscriptionFrame",
        "LLMContextAssistantTurnFrame",
        "TTSAudioRawFrame",
    ),
    "pipecat.processors.frame_processor": ("FrameProcessor", "FrameDirection"),
}
WEBSOCKET_PIPECAT_SYMBOLS: Mapping[str, tuple[str, ...]] = {
    WEBSOCKET_PIPECAT_MODULE: ("FastAPIWebsocketParams", "FastAPIWebsocketTransport")
}
OPTIONAL_PIPECAT_FEATURE_SYMBOLS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "vad": {
        SILERO_VAD_PIPECAT_MODULE: ("SileroVADAnalyzer",),
        VAD_ANALYZER_PIPECAT_MODULE: ("VADParams",),
        VAD_PROCESSOR_PIPECAT_MODULE: ("VADProcessor",),
    },
    "stt": {OPENAI_STT_PIPECAT_MODULE: ("OpenAIRealtimeSTTService",)},
    "tts": {OPENAI_TTS_PIPECAT_MODULE: ("OpenAITTSService",)},
    "llm": {
        OPENAI_LLM_PIPECAT_MODULE: ("OpenAILLMService",),
        LLM_CONTEXT_PIPECAT_MODULE: ("LLMContext",),
        LLM_RESPONSE_PIPECAT_MODULE: (
            "LLMContextAggregatorPair",
            "LLMUserAggregatorParams",
            "LLMAssistantAggregatorParams",
        ),
    },
    "realtimeLlm": {
        OPENAI_REALTIME_LLM_PIPECAT_MODULE: ("OpenAIRealtimeLLMService",),
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE: (
            "SessionProperties",
            "AudioConfiguration",
            "AudioInput",
            "AudioOutput",
            "InputAudioTranscription",
            "InputAudioNoiseReduction",
            "SemanticTurnDetection",
            "TurnDetection",
            "PCMAudioFormat",
            "PCMUAudioFormat",
            "PCMAAudioFormat",
        ),
        LLM_CONTEXT_PIPECAT_MODULE: ("LLMContext",),
        LLM_RESPONSE_PIPECAT_MODULE: (
            "LLMContextAggregatorPair",
            "LLMUserAggregatorParams",
            "LLMAssistantAggregatorParams",
        ),
    },
    "openrouter_llm": {OPENROUTER_LLM_PIPECAT_MODULE: ("OpenRouterLLMService",)},
    "turn_detection": {
        USER_TURN_PROCESSOR_PIPECAT_MODULE: ("UserTurnProcessor",),
        USER_TURN_STRATEGIES_PIPECAT_MODULE: (
            "UserTurnStrategies",
            "ExternalUserTurnStrategies",
            "FilterIncompleteUserTurnStrategies",
        ),
        USER_TURN_COMPLETION_PIPECAT_MODULE: ("UserTurnCompletionConfig",),
    },
}
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
    "realtimeLlm": (
        OPENAI_REALTIME_LLM_PIPECAT_MODULE,
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE,
        LLM_CONTEXT_PIPECAT_MODULE,
        LLM_RESPONSE_PIPECAT_MODULE,
    ),
    "openrouter_llm": (OPENROUTER_LLM_PIPECAT_MODULE,),
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
    openai_realtime_llm_available: bool = False
    openrouter_llm_available: bool = False
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
    TTSAudioRawFrame: type
    FrameProcessor: type
    FrameDirection: type
    InterimTranscriptionFrame: type | None = None
    InterruptionFrame: type | None = None
    UserStartedSpeakingFrame: type | None = None
    UserStoppedSpeakingFrame: type | None = None
    VADUserStartedSpeakingFrame: type | None = None
    VADUserStoppedSpeakingFrame: type | None = None
    BotStartedSpeakingFrame: type | None = None
    BotStoppedSpeakingFrame: type | None = None
    UserIdleTimeoutUpdateFrame: type | None = None
    FastAPIWebsocketParams: type | None = None
    FastAPIWebsocketTransport: type | None = None
    SileroVADAnalyzer: type | None = None
    VADParams: type | None = None
    VADProcessor: type | None = None
    OpenAIRealtimeSTTService: type | None = None
    OpenAITTSService: type | None = None
    OpenAILLMService: type | None = None
    OpenAIRealtimeLLMService: type | None = None
    OpenRouterLLMService: type | None = None
    LLMContext: type | None = None
    LLMContextAggregatorPair: type | None = None
    LLMUserAggregatorParams: type | None = None
    LLMAssistantAggregatorParams: type | None = None
    SessionProperties: type | None = None
    AudioConfiguration: type | None = None
    AudioInput: type | None = None
    AudioOutput: type | None = None
    InputAudioTranscription: type | None = None
    InputAudioNoiseReduction: type | None = None
    SemanticTurnDetection: type | None = None
    TurnDetection: type | None = None
    PCMAudioFormat: type | None = None
    PCMUAudioFormat: type | None = None
    PCMAAudioFormat: type | None = None
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


class PipecatRealtimePipelineError(RuntimeError):
    """Structured Pipecat adapter error for realtime readiness and startup paths."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str,
        feature: str | None = None,
        missing_modules: Sequence[str] = (),
        missing_env: Sequence[str] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(redact_realtime_secret_text(message))
        self.code = code
        self.phase = phase
        self.provider = "pipecat"
        self.feature = feature
        self.missing_modules = tuple(missing_modules)
        self.missing_env = tuple(missing_env)
        safe_metadata = sanitize_realtime_public_value(dict(metadata or {}))
        self.metadata = dict(safe_metadata) if isinstance(safe_metadata, Mapping) else {}

    def to_realtime_error(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "phase": self.phase,
            "provider": self.provider,
            "runtime": REALTIME_RUNTIME_PIPECAT,
        }
        if self.feature is not None:
            payload["feature"] = self.feature
        if self.missing_modules:
            payload["modules"] = self.missing_modules
        if self.missing_env:
            payload["missingEnv"] = self.missing_env
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


def is_pipecat_available() -> bool:
    """Return whether the core Pipecat pipeline package is importable."""

    return get_pipecat_capability().core_available


def get_pipecat_capability(*, require_websocket: bool = False) -> PipecatCapability:
    """Return a dependency-safe capability report without importing Pipecat eagerly."""

    optional_status = _optional_feature_status()
    try:
        missing = _missing_required_pipecat_entries(require_websocket=require_websocket)
    except ImportError as exc:
        return PipecatCapability(
            available=False,
            core_available=False,
            websocket_available=False,
            **optional_status,
            error=str(exc),
        )

    if missing:
        core_missing = any(
            _entry_belongs_to_modules(entry, CORE_PIPECAT_MODULES) for entry in missing
        )
        websocket_missing = any(
            _entry_belongs_to_modules(entry, (WEBSOCKET_PIPECAT_MODULE,)) for entry in missing
        )
        return PipecatCapability(
            available=False,
            core_available=not core_missing,
            websocket_available=not websocket_missing,
            missing_modules=missing,
            **optional_status,
            error=f"Missing Pipecat runtime symbol(s): {', '.join(missing)}",
        )

    try:
        runtime = import_pipecat_runtime(require_websocket=require_websocket)
    except Exception as exc:
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


def pipecat_realtime_capability_response(
    *,
    require_websocket: bool = True,
    openai_api_key_available: bool | None = None,
    include_source_snapshot: bool = True,
    openai_model: object = _OPENAI_RUNTIME_VALUE_UNSET,
    openai_voice: object = _OPENAI_RUNTIME_VALUE_UNSET,
    input_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
    output_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
) -> dict[str, Any]:
    """Return the public Pipecat capability/readiness payload for realtime calls."""

    try:
        capability = get_pipecat_capability(require_websocket=require_websocket)
    except Exception as exc:
        capability = PipecatCapability(
            available=False,
            core_available=False,
            websocket_available=False,
            error=f"Pipecat capability check failed: {redact_realtime_secret_text(str(exc))}",
        )

    openai_requirements = _resolved_openai_runtime_requirements(
        model=openai_model,
        voice=openai_voice,
        input_audio_format=input_audio_format,
        output_audio_format=output_audio_format,
    )
    data = _pipecat_capability_public_payload(capability)
    data["model"] = openai_requirements["model"]
    data["voice"] = openai_requirements["voice"]
    data["inputAudioFormat"] = openai_requirements["inputAudioFormat"]
    data["outputAudioFormat"] = openai_requirements["outputAudioFormat"]
    readiness = pipecat_realtime_readiness(
        capability,
        require_websocket=require_websocket,
        openai_api_key_available=openai_api_key_available,
        openai_model=openai_requirements["model"],
        openai_voice=openai_requirements["voice"],
        input_audio_format=openai_requirements["inputAudioFormat"],
        output_audio_format=openai_requirements["outputAudioFormat"],
    ).to_dict()
    data["readyForCall"] = readiness["ready"]
    data["readiness"] = readiness
    data["errors"] = readiness["blockingReasons"]
    data["providerCatalogSummary"] = sanitize_realtime_public_value(
        pipecat_provider_catalog_summary()
    )
    smoke = pipecat_realtime_smoke_contract(
        ready_for_call=bool(readiness["ready"]),
        require_websocket=require_websocket,
        input_audio_format=openai_requirements["inputAudioFormat"],
        output_audio_format=openai_requirements["outputAudioFormat"],
    )
    data["smoke"] = smoke
    production_readiness = smoke["productionReadiness"]
    if isinstance(production_readiness, Mapping):
        data["productionReady"] = bool(production_readiness["readyForProduction"])
        data["productionReadiness"] = dict(production_readiness)
    if include_source_snapshot:
        with suppress(Exception):
            source_snapshot = sanitize_realtime_public_value(dict(pipecat_source_snapshot()))
            if isinstance(source_snapshot, Mapping):
                data["sourceSnapshot"] = dict(source_snapshot)
    return data


def pipecat_realtime_smoke_contract(
    *,
    ready_for_call: bool,
    require_websocket: bool = True,
    input_audio_format: str | None = None,
    output_audio_format: str | None = None,
) -> dict[str, object]:
    """Return the deterministic local smoke contract for Pipecat realtime calls."""

    production_readiness = _pipecat_realtime_production_readiness(
        local_runtime_ready=bool(ready_for_call),
    )
    return {
        "verificationLevel": "dependency_and_event_contract",
        "localRuntimeReady": bool(ready_for_call),
        "browserE2EVerified": False,
        "requiresExplicitMediaPermission": True,
        "productionReady": bool(production_readiness["readyForProduction"]),
        "productionReadiness": production_readiness,
        "transport": "websocket" if require_websocket else "audio_chunks",
        "inputAudioFormat": input_audio_format or "pcm16",
        "outputAudioFormat": output_audio_format or input_audio_format or "pcm16",
        "defaultInputSampleRate": 16000,
        "contractEvents": list(PIPECAT_REALTIME_SMOKE_CONTRACT_EVENTS),
        "eventOrder": {
            key: list(events) for key, events in PIPECAT_REALTIME_SMOKE_EVENT_ORDER.items()
        },
        "contractCoverage": _pipecat_realtime_smoke_contract_coverage(),
        "errorTaxonomy": [dict(item) for item in PIPECAT_REALTIME_SMOKE_ERROR_TAXONOMY],
        "readinessAssertions": {
            "readyForCallImpliesLocalRuntimeReady": True,
            "readyForCallImpliesProductionReady": False,
            "browserE2EVerified": False,
            "requiresExplicitMediaPermission": True,
        },
    }


def pipecat_realtime_profile_contracts() -> dict[str, Any]:
    """Return TalkWise's public contract for the two Pipecat-owned voice chains."""

    return {
        PIPECAT_REALTIME_PROFILE_CASCADE: {
            "profile": PIPECAT_REALTIME_PROFILE_CASCADE,
            "pipeline": "stt_llm_tts_cascade",
            "latencyProfile": "near_realtime",
            "costProfile": "lower_cost_split_services",
            "transport": "websocket",
            "inputAudio": {
                "encoding": "pcm16",
                "sampleRate": 16000,
                "channels": 1,
                "source": "browser_microphone",
            },
            "outputAudio": {
                "encoding": "pcm16",
                "sampleRate": 24000,
                "channels": 1,
                "eventType": "audio.output",
            },
            "services": {
                "stt": "openai",
                "llm": "openai_or_openrouter",
                "tts": "openai",
                "vad": "silero",
            },
            "turnDetection": {
                "owner": "pipecat",
                "provider": "pipecat",
                "mode": "vad_user_turn_processor",
                "supportsInterruption": True,
                "supportsSilenceTimeout": True,
            },
            "talkwiseIntegration": {
                "transcriptPersistence": "TrainingTranscriptSink",
                "audioOutputEvent": "audio.output",
                "liveGuidanceEvent": "training.live_guidance.triggered",
                "trainingSemantics": "TrainingVoiceContext",
            },
            "readinessFeatures": dict(PIPECAT_REALTIME_REQUIRED_FEATURES),
            "browserE2E": {
                "verified": False,
                "requiredForProduction": True,
                "requiredSignals": list(PIPECAT_REALTIME_BROWSER_AUDIO_E2E_SIGNALS),
            },
        },
        PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH: {
            "profile": PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
            "pipeline": "openai_realtime_speech_to_speech",
            "latencyProfile": "true_realtime",
            "costProfile": "premium_realtime_audio",
            "transport": "websocket",
            "inputAudio": {
                "encoding": "pcm16",
                "sampleRate": 24000,
                "channels": 1,
                "source": "browser_microphone",
            },
            "outputAudio": {
                "encoding": "pcm16",
                "sampleRate": 24000,
                "channels": 1,
                "eventType": "audio.output",
            },
            "services": {
                "realtimeLlm": "openai",
                "stt": "openai_realtime_transcription",
                "tts": "openai_realtime_audio",
            },
            "turnDetection": {
                "owner": "provider",
                "provider": "openai_realtime",
                "mode": "semantic_vad",
                "supportsInterruption": True,
                "supportsSilenceTimeout": True,
            },
            "talkwiseIntegration": {
                "transcriptPersistence": "TrainingTranscriptSink",
                "audioOutputEvent": "audio.output",
                "liveGuidanceEvent": "training.live_guidance.triggered",
                "trainingSemantics": "TrainingVoiceContext",
            },
            "readinessFeatures": {"realtimeLlm": "openai"},
            "browserE2E": {
                "verified": False,
                "requiredForProduction": True,
                "requiredSignals": list(PIPECAT_REALTIME_BROWSER_AUDIO_E2E_SIGNALS),
            },
        },
    }


def _pipecat_realtime_production_readiness(
    *,
    local_runtime_ready: bool,
    browser_audio_e2e_verified: bool = False,
) -> dict[str, object]:
    blockers: list[dict[str, object]] = []
    if not local_runtime_ready:
        blockers.append(
            {
                "code": "LOCAL_REALTIME_RUNTIME_NOT_READY",
                "message": "Pipecat dependencies and realtime configuration are not ready",
                "phase": "capability_check",
                "provider": "pipecat",
                "runtime": REALTIME_RUNTIME_PIPECAT,
            }
        )
    if not browser_audio_e2e_verified:
        blockers.append(
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
                "requiredSignals": list(PIPECAT_REALTIME_BROWSER_AUDIO_E2E_SIGNALS),
            }
        )

    ready_for_production = bool(local_runtime_ready and browser_audio_e2e_verified)
    return {
        "readyForProduction": ready_for_production,
        "status": (
            "ready"
            if ready_for_production
            else "browser_e2e_verification_required" if local_runtime_ready else "runtime_blocked"
        ),
        "localRuntimeReady": bool(local_runtime_ready),
        "browserAudioE2EVerified": bool(browser_audio_e2e_verified),
        "requiredVerifications": ["browser_audio_e2e"],
        "blockingReasons": blockers,
    }


def _pipecat_realtime_smoke_contract_coverage() -> dict[str, object]:
    return {
        "browserAudioE2E": {
            "verified": False,
            "requiredForProduction": True,
            "requiredSignals": list(PIPECAT_REALTIME_BROWSER_AUDIO_E2E_SIGNALS),
        },
        "providerNeutralAudioOutput": {
            "contracted": True,
            "eventType": "audio.output",
            "payloadFields": [
                "audio",
                "encoding",
                "mimeType",
                "sampleRate",
                "channels",
                "sequence",
                "bytes",
                "runtime",
                "provider",
            ],
        },
        "turnInterruptionSilence": {
            "contracted": True,
            "eventTypes": [
                "user_turn.started",
                "user_turn.stopped",
                "assistant_speaking.started",
                "assistant_speaking.stopped",
                "interrupted",
                "silence_timeout",
            ],
        },
        "metrics": {
            "contracted": True,
            "metadataKey": "realtimeMetrics",
            "latencyEndEvents": ["assistant_speaking.started", "audio.output"],
        },
        "errorTaxonomy": {
            "contracted": True,
            "categories": [
                str(item["errorCategory"]) for item in PIPECAT_REALTIME_SMOKE_ERROR_TAXONOMY
            ],
        },
    }


def pipecat_realtime_readiness(
    capability: PipecatCapability | None = None,
    *,
    require_websocket: bool = True,
    openai_api_key_available: bool | None = None,
    openai_model: object = _OPENAI_RUNTIME_VALUE_UNSET,
    openai_voice: object = _OPENAI_RUNTIME_VALUE_UNSET,
    input_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
    output_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
) -> RealtimeProviderReadiness:
    """Build structured readiness from Pipecat capability and call prerequisites."""

    capability = capability or get_pipecat_capability(require_websocket=require_websocket)
    openai_requirements = _resolved_openai_runtime_requirements(
        model=openai_model,
        voice=openai_voice,
        input_audio_format=input_audio_format,
        output_audio_format=output_audio_format,
    )
    missing_modules = tuple(str(module) for module in capability.missing_modules)
    optional_missing_modules = tuple(str(module) for module in capability.optional_missing_modules)
    blockers: list[RealtimeReadinessIssue] = []
    error_message = redact_realtime_secret_text(capability.error) if capability.error else None

    if not capability.core_available:
        if error_message and not missing_modules:
            blockers.append(
                RealtimeReadinessIssue(
                    code="PIPECAT_CAPABILITY_ERROR",
                    message=error_message,
                    phase="capability_check",
                    provider="pipecat",
                )
            )
        else:
            blockers.append(
                RealtimeReadinessIssue(
                    code="PIPECAT_MODULE_UNAVAILABLE",
                    message="Pipecat core modules are required before starting realtime calls",
                    phase="capability_check",
                    provider="pipecat",
                    modules=missing_modules,
                )
            )
    elif require_websocket and not capability.websocket_available:
        blockers.append(
            RealtimeReadinessIssue(
                code="PIPECAT_WEBSOCKET_UNAVAILABLE",
                message="Pipecat websocket transport is required before starting realtime calls",
                phase="capability_check",
                provider="pipecat",
                modules=missing_modules or (WEBSOCKET_PIPECAT_MODULE,),
            )
        )
    else:
        for feature, required_provider in PIPECAT_REALTIME_REQUIRED_FEATURES.items():
            if _pipecat_feature_available(capability, feature):
                continue
            requirement = PIPECAT_REALTIME_FEATURE_REQUIREMENTS[feature]
            blockers.append(
                RealtimeReadinessIssue(
                    code=str(requirement["code"]),
                    message=str(requirement["message"]),
                    phase="capability_check",
                    provider="pipecat",
                    feature=str(requirement["feature"]),
                    modules=_pipecat_feature_missing_modules(
                        feature,
                        optional_missing_modules,
                    ),
                )
            )

    if openai_api_key_available is None:
        openai_api_key_available = bool(_openai_api_key({}))
    if not openai_api_key_available:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_API_KEY",
                message=(
                    "Set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY "
                    "before starting Pipecat realtime calls"
                ),
                phase="configuration",
                provider="pipecat",
                missing_env=OPENAI_API_KEY_ENV_KEYS,
            )
        )
    if not openai_requirements["model"]:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_MODEL",
                message="Configure REALTIME_OPENAI_MODEL before starting Pipecat realtime calls",
                phase="configuration",
                provider="pipecat",
                feature="model",
                missing_env=(OPENAI_REALTIME_MODEL_SETTING,),
            )
        )
    if not openai_requirements["voice"]:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_VOICE",
                message="Configure REALTIME_OPENAI_VOICE before starting Pipecat realtime calls",
                phase="configuration",
                provider="pipecat",
                feature="voice",
                missing_env=(OPENAI_REALTIME_VOICE_SETTING,),
            )
        )
    if not openai_requirements["inputAudioFormat"]:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
                message=(
                    "Configure REALTIME_OPENAI_INPUT_AUDIO_FORMAT before starting "
                    "Pipecat realtime calls"
                ),
                phase="configuration",
                provider="pipecat",
                feature="audioFormat",
                missing_env=(OPENAI_REALTIME_INPUT_AUDIO_FORMAT_SETTING,),
            )
        )

    if error_message and not blockers:
        blockers.append(
            RealtimeReadinessIssue(
                code="PIPECAT_CAPABILITY_ERROR",
                message=error_message,
                phase="capability_check",
                provider="pipecat",
                modules=missing_modules,
            )
        )

    return build_realtime_readiness(
        required={
            "transport": "websocket" if require_websocket else "audio_chunks",
            "features": dict(PIPECAT_REALTIME_REQUIRED_FEATURES),
            "env": OPENAI_API_KEY_ENV_KEYS,
            "openai": openai_requirements,
        },
        blocking_reasons=blockers,
        runtime=REALTIME_RUNTIME_PIPECAT,
    )


def _pipecat_capability_public_payload(capability: PipecatCapability) -> dict[str, Any]:
    return {
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": "pipecat",
        "available": bool(capability.available),
        "coreAvailable": bool(capability.core_available),
        "websocketAvailable": bool(capability.websocket_available),
        "vadAvailable": bool(capability.vad_available),
        "sttAvailable": bool(capability.stt_available),
        "ttsAvailable": bool(capability.tts_available),
        "llmAvailable": bool(capability.llm_available),
        "openaiRealtimeLlmAvailable": bool(capability.openai_realtime_llm_available),
        "openrouterLlmAvailable": bool(capability.openrouter_llm_available),
        "turnDetectionAvailable": bool(capability.turn_detection_available),
        "profiles": _pipecat_realtime_profile_payload(capability),
        "missingModules": [str(module) for module in capability.missing_modules],
        "optionalMissingModules": [str(module) for module in capability.optional_missing_modules],
        "error": redact_realtime_secret_text(capability.error) if capability.error else None,
    }


def _pipecat_realtime_profile_payload(capability: PipecatCapability) -> dict[str, Any]:
    contracts = pipecat_realtime_profile_contracts()
    cascade_ready = all(
        (
            capability.available,
            capability.stt_available,
            capability.tts_available,
            capability.llm_available,
            capability.vad_available,
            capability.turn_detection_available,
        )
    )
    speech_to_speech_ready = all(
        (
            capability.available,
            capability.openai_realtime_llm_available,
        )
    )
    return {
        "default": PIPECAT_REALTIME_PROFILE_CASCADE,
        "supported": [
            PIPECAT_REALTIME_PROFILE_CASCADE,
            PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
        ],
        PIPECAT_REALTIME_PROFILE_CASCADE: {
            "ready": cascade_ready,
            "features": dict(PIPECAT_REALTIME_REQUIRED_FEATURES),
            "contract": contracts[PIPECAT_REALTIME_PROFILE_CASCADE],
        },
        PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH: {
            "ready": speech_to_speech_ready,
            "features": {"realtimeLlm": "openai"},
            "contract": contracts[PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH],
        },
    }


def _pipecat_feature_available(capability: PipecatCapability, feature: str) -> bool:
    if feature == "realtimeLlm":
        return bool(capability.openai_realtime_llm_available)
    return bool(
        getattr(
            capability,
            "turn_detection_available" if feature == "turnDetection" else f"{feature}_available",
            False,
        )
    )


def _pipecat_feature_missing_modules(
    feature: str,
    optional_missing_modules: Sequence[str],
    provider: str | None = None,
) -> tuple[str, ...]:
    requirement = _pipecat_feature_requirement(feature, provider or "")
    hints = (
        (OPENROUTER_LLM_PIPECAT_MODULE,)
        if feature == "llm" and provider == OPENROUTER_LLM_PROVIDER
        else PIPECAT_FEATURE_MODULE_HINTS[feature]
    )
    missing = tuple(
        module
        for module in optional_missing_modules
        if any(module == hint or module.startswith(f"{hint}.") for hint in hints)
    )
    if missing:
        return missing
    if requirement is None:
        return ()
    return tuple(str(module) for module in requirement["modules"])


def _pipecat_feature_requirement(
    feature_name: str,
    provider: str,
) -> Mapping[str, object] | None:
    if feature_name == "llm" and provider == OPENROUTER_LLM_PROVIDER:
        return PIPECAT_OPENROUTER_LLM_FEATURE_REQUIREMENT
    return PIPECAT_REALTIME_FEATURE_REQUIREMENTS.get(
        "turnDetection" if feature_name == "turnDetection" else feature_name
    )


def _module_spec_exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _missing_required_pipecat_entries(*, require_websocket: bool) -> tuple[str, ...]:
    missing = tuple(module for module in CORE_PIPECAT_SYMBOLS if not _module_spec_exists(module))
    if missing:
        return missing

    core_missing = _missing_pipecat_symbols(
        CORE_PIPECAT_SYMBOLS,
        strict_import_errors=True,
    )
    if core_missing or not require_websocket:
        return core_missing

    websocket_missing = tuple(
        module for module in WEBSOCKET_PIPECAT_SYMBOLS if not _module_spec_exists(module)
    )
    if websocket_missing:
        return websocket_missing
    return _missing_pipecat_symbols(
        WEBSOCKET_PIPECAT_SYMBOLS,
        strict_import_errors=False,
    )


def _missing_pipecat_symbols(
    symbol_map: Mapping[str, Sequence[str]],
    *,
    strict_import_errors: bool = False,
) -> tuple[str, ...]:
    missing: list[str] = []
    for module_name, symbol_names in symbol_map.items():
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            if strict_import_errors:
                raise ImportError(
                    f"Pipecat module import failed while checking {module_name}: {exc}"
                ) from exc
            missing.append(module_name)
            continue

        for symbol_name in symbol_names:
            if getattr(module, symbol_name, None) is None:
                missing.append(_entrypoint(module_name, symbol_name))
    return tuple(missing)


def _entrypoint(module_name: str, symbol_name: str) -> str:
    return f"{module_name}.{symbol_name}"


def _entry_belongs_to_modules(entry: str, modules: Sequence[str]) -> bool:
    return any(entry == module or entry.startswith(f"{module}.") for module in modules)


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
        "openai_realtime_llm_available": not missing_by_feature["realtimeLlm"],
        "openrouter_llm_available": not missing_by_feature["openrouter_llm"],
        "turn_detection_available": not missing_by_feature["turn_detection"],
        "optional_missing_modules": tuple(
            module for modules in missing_by_feature.values() for module in modules
        ),
    }


def _runtime_feature_status(
    runtime: PipecatRuntime,
    module_status: Mapping[str, bool | tuple[str, ...]],
) -> dict[str, bool | tuple[str, ...]]:
    optional_missing = list(module_status.get("optional_missing_modules", ()))
    optional_missing.extend(_runtime_missing_optional_symbols(runtime, optional_missing))
    return {
        "vad_available": bool(module_status.get("vad_available"))
        and (
            runtime.SileroVADAnalyzer is not None
            and runtime.VADParams is not None
            and runtime.VADProcessor is not None
        ),
        "stt_available": bool(module_status.get("stt_available"))
        and runtime.OpenAIRealtimeSTTService is not None
        and getattr(runtime.OpenAIRealtimeSTTService, "Settings", None) is not None,
        "tts_available": bool(module_status.get("tts_available"))
        and runtime.OpenAITTSService is not None
        and getattr(runtime.OpenAITTSService, "Settings", None) is not None,
        "llm_available": bool(module_status.get("llm_available"))
        and runtime.OpenAILLMService is not None
        and getattr(runtime.OpenAILLMService, "Settings", None) is not None
        and runtime.LLMContext is not None
        and runtime.LLMContextAggregatorPair is not None
        and runtime.LLMUserAggregatorParams is not None
        and runtime.LLMAssistantAggregatorParams is not None,
        "openai_realtime_llm_available": bool(module_status.get("openai_realtime_llm_available"))
        and runtime.OpenAIRealtimeLLMService is not None
        and getattr(runtime.OpenAIRealtimeLLMService, "Settings", None) is not None
        and runtime.SessionProperties is not None
        and runtime.AudioConfiguration is not None
        and runtime.AudioInput is not None
        and runtime.AudioOutput is not None
        and runtime.InputAudioTranscription is not None
        and runtime.InputAudioNoiseReduction is not None
        and runtime.SemanticTurnDetection is not None
        and runtime.TurnDetection is not None
        and runtime.PCMAudioFormat is not None
        and runtime.PCMUAudioFormat is not None
        and runtime.PCMAAudioFormat is not None
        and runtime.LLMContext is not None
        and runtime.LLMContextAggregatorPair is not None
        and runtime.LLMUserAggregatorParams is not None
        and runtime.LLMAssistantAggregatorParams is not None,
        "openrouter_llm_available": bool(module_status.get("openrouter_llm_available"))
        and runtime.OpenRouterLLMService is not None
        and getattr(runtime.OpenRouterLLMService, "Settings", None) is not None
        and runtime.LLMContext is not None
        and runtime.LLMContextAggregatorPair is not None
        and runtime.LLMUserAggregatorParams is not None
        and runtime.LLMAssistantAggregatorParams is not None,
        "turn_detection_available": bool(module_status.get("turn_detection_available"))
        and (runtime.UserTurnProcessor is not None and runtime.UserTurnStrategies is not None),
        "optional_missing_modules": tuple(dict.fromkeys(optional_missing)),
    }


def _runtime_missing_optional_symbols(
    runtime: PipecatRuntime,
    known_missing: Sequence[str],
) -> tuple[str, ...]:
    missing_modules = set(known_missing)
    missing: list[str] = []
    for symbol_map in OPTIONAL_PIPECAT_FEATURE_SYMBOLS.values():
        for module_name, symbol_names in symbol_map.items():
            if module_name in missing_modules:
                continue
            for symbol_name in symbol_names:
                if getattr(runtime, symbol_name, None) is None:
                    missing.append(_entrypoint(module_name, symbol_name))
    if (
        runtime.OpenAIRealtimeSTTService is not None
        and getattr(
            runtime.OpenAIRealtimeSTTService,
            "Settings",
            None,
        )
        is None
    ):
        missing.append(_entrypoint(OPENAI_STT_PIPECAT_MODULE, "OpenAIRealtimeSTTService.Settings"))
    if (
        runtime.OpenAITTSService is not None
        and getattr(
            runtime.OpenAITTSService,
            "Settings",
            None,
        )
        is None
    ):
        missing.append(_entrypoint(OPENAI_TTS_PIPECAT_MODULE, "OpenAITTSService.Settings"))
    if (
        runtime.OpenAILLMService is not None
        and getattr(
            runtime.OpenAILLMService,
            "Settings",
            None,
        )
        is None
    ):
        missing.append(_entrypoint(OPENAI_LLM_PIPECAT_MODULE, "OpenAILLMService.Settings"))
    if (
        runtime.OpenAIRealtimeLLMService is not None
        and getattr(
            runtime.OpenAIRealtimeLLMService,
            "Settings",
            None,
        )
        is None
    ):
        missing.append(
            _entrypoint(
                OPENAI_REALTIME_LLM_PIPECAT_MODULE,
                "OpenAIRealtimeLLMService.Settings",
            )
        )
    if (
        runtime.OpenRouterLLMService is not None
        and getattr(
            runtime.OpenRouterLLMService,
            "Settings",
            None,
        )
        is None
    ):
        missing.append(_entrypoint(OPENROUTER_LLM_PIPECAT_MODULE, "OpenRouterLLMService.Settings"))
    return tuple(missing)


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
        pipeline_module = _import_pipecat_module("pipecat.pipeline.pipeline")
        worker_module = _import_pipecat_module("pipecat.pipeline.worker")
        worker_params_module = _import_pipecat_module("pipecat.workers.base_worker")
        runner_module = _import_pipecat_module("pipecat.workers.runner")
        frames_module = _import_pipecat_module("pipecat.frames.frames")
        processor_module = _import_pipecat_module("pipecat.processors.frame_processor")
    except ImportError as exc:
        raise ImportError(f"Pipecat core is unavailable: {exc}") from exc

    websocket_params = None
    websocket_transport = None
    try:
        websocket_module = _import_pipecat_module(WEBSOCKET_PIPECAT_MODULE)
        websocket_params = _required_pipecat_symbol(
            websocket_module, WEBSOCKET_PIPECAT_MODULE, "FastAPIWebsocketParams"
        )
        websocket_transport = _required_pipecat_symbol(
            websocket_module, WEBSOCKET_PIPECAT_MODULE, "FastAPIWebsocketTransport"
        )
    except ImportError as exc:
        if require_websocket:
            raise ImportError(
                "Pipecat websocket transport is unavailable; install pipecat with websocket extras"
            ) from exc

    silero_vad_analyzer = _optional_pipecat_symbol(SILERO_VAD_PIPECAT_MODULE, "SileroVADAnalyzer")
    vad_params = _optional_pipecat_symbol(VAD_ANALYZER_PIPECAT_MODULE, "VADParams")
    vad_processor = _optional_pipecat_symbol(VAD_PROCESSOR_PIPECAT_MODULE, "VADProcessor")
    openai_realtime_stt = _optional_pipecat_symbol(
        OPENAI_STT_PIPECAT_MODULE, "OpenAIRealtimeSTTService"
    )
    openai_tts = _optional_pipecat_symbol(OPENAI_TTS_PIPECAT_MODULE, "OpenAITTSService")
    openai_llm = _optional_pipecat_symbol(OPENAI_LLM_PIPECAT_MODULE, "OpenAILLMService")
    openai_realtime_llm = _optional_pipecat_symbol(
        OPENAI_REALTIME_LLM_PIPECAT_MODULE, "OpenAIRealtimeLLMService"
    )
    openrouter_llm = _optional_pipecat_symbol(OPENROUTER_LLM_PIPECAT_MODULE, "OpenRouterLLMService")
    realtime_session_properties = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "SessionProperties"
    )
    realtime_audio_configuration = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "AudioConfiguration"
    )
    realtime_audio_input = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "AudioInput"
    )
    realtime_audio_output = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "AudioOutput"
    )
    realtime_input_audio_transcription = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "InputAudioTranscription"
    )
    realtime_input_audio_noise_reduction = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "InputAudioNoiseReduction"
    )
    realtime_semantic_turn_detection = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "SemanticTurnDetection"
    )
    realtime_turn_detection = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "TurnDetection"
    )
    realtime_pcm_audio_format = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "PCMAudioFormat"
    )
    realtime_pcmu_audio_format = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "PCMUAudioFormat"
    )
    realtime_pcma_audio_format = _optional_pipecat_symbol(
        OPENAI_REALTIME_EVENTS_PIPECAT_MODULE, "PCMAAudioFormat"
    )
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
        Pipeline=_required_pipecat_symbol(pipeline_module, "pipecat.pipeline.pipeline", "Pipeline"),
        PipelineParams=_required_pipecat_symbol(
            worker_module, "pipecat.pipeline.worker", "PipelineParams"
        ),
        PipelineWorker=_required_pipecat_symbol(
            worker_module, "pipecat.pipeline.worker", "PipelineWorker"
        ),
        WorkerParams=_required_pipecat_symbol(
            worker_params_module, "pipecat.workers.base_worker", "WorkerParams"
        ),
        WorkerRunner=_required_pipecat_symbol(
            runner_module, "pipecat.workers.runner", "WorkerRunner"
        ),
        InputAudioRawFrame=_required_pipecat_symbol(
            frames_module, "pipecat.frames.frames", "InputAudioRawFrame"
        ),
        EndFrame=_required_pipecat_symbol(frames_module, "pipecat.frames.frames", "EndFrame"),
        TextFrame=_required_pipecat_symbol(frames_module, "pipecat.frames.frames", "TextFrame"),
        TranscriptionFrame=_required_pipecat_symbol(
            frames_module, "pipecat.frames.frames", "TranscriptionFrame"
        ),
        LLMContextAssistantTurnFrame=_required_pipecat_symbol(
            frames_module, "pipecat.frames.frames", "LLMContextAssistantTurnFrame"
        ),
        TTSAudioRawFrame=_required_pipecat_symbol(
            frames_module, "pipecat.frames.frames", "TTSAudioRawFrame"
        ),
        FrameProcessor=_required_pipecat_symbol(
            processor_module, "pipecat.processors.frame_processor", "FrameProcessor"
        ),
        FrameDirection=_required_pipecat_symbol(
            processor_module, "pipecat.processors.frame_processor", "FrameDirection"
        ),
        InterimTranscriptionFrame=getattr(frames_module, "InterimTranscriptionFrame", None),
        InterruptionFrame=getattr(frames_module, "InterruptionFrame", None),
        UserStartedSpeakingFrame=getattr(frames_module, "UserStartedSpeakingFrame", None),
        UserStoppedSpeakingFrame=getattr(frames_module, "UserStoppedSpeakingFrame", None),
        VADUserStartedSpeakingFrame=getattr(frames_module, "VADUserStartedSpeakingFrame", None),
        VADUserStoppedSpeakingFrame=getattr(frames_module, "VADUserStoppedSpeakingFrame", None),
        BotStartedSpeakingFrame=getattr(frames_module, "BotStartedSpeakingFrame", None),
        BotStoppedSpeakingFrame=getattr(frames_module, "BotStoppedSpeakingFrame", None),
        UserIdleTimeoutUpdateFrame=getattr(frames_module, "UserIdleTimeoutUpdateFrame", None),
        FastAPIWebsocketParams=websocket_params,
        FastAPIWebsocketTransport=websocket_transport,
        SileroVADAnalyzer=silero_vad_analyzer,
        VADParams=vad_params,
        VADProcessor=vad_processor,
        OpenAIRealtimeSTTService=openai_realtime_stt,
        OpenAITTSService=openai_tts,
        OpenAILLMService=openai_llm,
        OpenAIRealtimeLLMService=openai_realtime_llm,
        OpenRouterLLMService=openrouter_llm,
        LLMContext=llm_context,
        LLMContextAggregatorPair=llm_context_aggregator_pair,
        LLMUserAggregatorParams=llm_user_aggregator_params,
        LLMAssistantAggregatorParams=llm_assistant_aggregator_params,
        SessionProperties=realtime_session_properties,
        AudioConfiguration=realtime_audio_configuration,
        AudioInput=realtime_audio_input,
        AudioOutput=realtime_audio_output,
        InputAudioTranscription=realtime_input_audio_transcription,
        InputAudioNoiseReduction=realtime_input_audio_noise_reduction,
        SemanticTurnDetection=realtime_semantic_turn_detection,
        TurnDetection=realtime_turn_detection,
        PCMAudioFormat=realtime_pcm_audio_format,
        PCMUAudioFormat=realtime_pcmu_audio_format,
        PCMAAudioFormat=realtime_pcma_audio_format,
        UserTurnProcessor=user_turn_processor,
        UserTurnStrategies=user_turn_strategies,
        ExternalUserTurnStrategies=external_user_turn_strategies,
        FilterIncompleteUserTurnStrategies=filter_incomplete_user_turn_strategies,
        UserTurnCompletionConfig=user_turn_completion_config,
    )


def _import_pipecat_module(module_name: str) -> Any:
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ImportError(f"{module_name} is not importable: {exc.name}") from exc
    except ImportError as exc:
        raise ImportError(f"{module_name} import failed: {exc}") from exc


def _required_pipecat_symbol(module: Any, module_name: str, symbol_name: str) -> type:
    symbol = getattr(module, symbol_name, None)
    if symbol is None:
        raise ImportError(f"Pipecat symbol is unavailable: {_entrypoint(module_name, symbol_name)}")
    return symbol


def _service_settings(
    service: type,
    service_entrypoint: str,
    settings_kwargs: Mapping[str, Any],
) -> Any:
    settings_factory = getattr(service, "Settings", None)
    if settings_factory is None:
        raise RuntimeError(f"Pipecat settings class is unavailable: {service_entrypoint}.Settings")
    return settings_factory(**settings_kwargs)


def _pipecat_config(config: RealtimePipelineConfig) -> RealtimePipelineConfig:
    runtime = normalize_realtime_runtime(config.runtime, provider=config.provider)
    if runtime == REALTIME_RUNTIME_PIPECAT and config.runtime == REALTIME_RUNTIME_PIPECAT:
        return config
    return replace(config, runtime=REALTIME_RUNTIME_PIPECAT)


def _optional_pipecat_symbol(module_name: str, symbol_name: str) -> type | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return None
    return getattr(module, symbol_name, None)


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _settings_text(name: str) -> str | None:
    try:
        from core.config import settings as app_settings
    except Exception:
        return None
    return _clean_text(getattr(app_settings, name, None))


def _resolve_openai_runtime_value(
    value: object = _OPENAI_RUNTIME_VALUE_UNSET,
    *,
    setting_name: str | None = None,
) -> str | None:
    if value is _OPENAI_RUNTIME_VALUE_UNSET:
        return _settings_text(setting_name) if setting_name is not None else None
    return _clean_text(value)


def _resolved_openai_runtime_requirements(
    *,
    model: object = _OPENAI_RUNTIME_VALUE_UNSET,
    voice: object = _OPENAI_RUNTIME_VALUE_UNSET,
    input_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
    output_audio_format: object = _OPENAI_RUNTIME_VALUE_UNSET,
) -> dict[str, str | None]:
    resolved_input_audio_format = _resolve_openai_runtime_value(
        input_audio_format,
        setting_name=OPENAI_REALTIME_INPUT_AUDIO_FORMAT_SETTING,
    )
    resolved_output_audio_format = _clean_text(
        output_audio_format
        if output_audio_format is not _OPENAI_RUNTIME_VALUE_UNSET
        else resolved_input_audio_format
    )
    return {
        "model": _resolve_openai_runtime_value(
            model,
            setting_name=OPENAI_REALTIME_MODEL_SETTING,
        ),
        "voice": _resolve_openai_runtime_value(
            voice,
            setting_name=OPENAI_REALTIME_VOICE_SETTING,
        ),
        "inputAudioFormat": resolved_input_audio_format,
        "outputAudioFormat": resolved_output_audio_format,
    }


def _pipecat_dependency_probe(
    capability: PipecatCapability,
    *,
    require_websocket: bool,
) -> dict[str, object]:
    return {
        "checkedAt": datetime.now(UTC).isoformat(),
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "requireWebsocket": require_websocket,
        "coreAvailable": bool(capability.core_available),
        "websocketAvailable": bool(capability.websocket_available),
        "available": bool(capability.available),
        "featureAvailability": {
            "stt": bool(capability.stt_available),
            "tts": bool(capability.tts_available),
            "llm": bool(capability.llm_available),
            "realtimeLlm": bool(capability.openai_realtime_llm_available),
            "vad": bool(capability.vad_available),
            "turnDetection": bool(capability.turn_detection_available),
        },
        "missingModules": [str(module) for module in capability.missing_modules],
        "optionalMissingModules": [str(module) for module in capability.optional_missing_modules],
        "error": redact_realtime_secret_text(capability.error) if capability.error else None,
    }


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
            config=self._config
            or RealtimePipelineConfig(provider="pipecat", runtime=REALTIME_RUNTIME_PIPECAT),
            websocket=self._websocket,
        )

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        if self._handle is not None and not self._closed:
            raise RuntimeError("Pipecat realtime pipeline is already started")

        try:
            runtime = self._runtime or import_pipecat_runtime(
                require_websocket=self._websocket is not None
            )
            config = _pipecat_config(config)
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
        except PipecatRealtimePipelineError:
            raise
        except Exception as exc:
            error = _pipecat_start_error(
                exc,
                websocket=self._websocket is not None,
                context=context,
                config=config,
            )
            logger.warning(
                "Pipecat realtime pipeline start failed",
                extra={"realtime_error": error.to_realtime_error()},
                exc_info=True,
            )
            raise error from exc

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


def _pipecat_start_error(
    exc: BaseException,
    *,
    websocket: bool,
    context: TrainingVoiceContext,
    config: RealtimePipelineConfig,
) -> PipecatRealtimePipelineError:
    message = str(exc)
    metadata: dict[str, Any] = {
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "trainingSessionId": context.binding.training_session_id,
        "roomId": context.binding.room_id,
        "requestedFeatures": _requested_feature_metadata(config),
    }
    if isinstance(exc, ImportError):
        return PipecatRealtimePipelineError(
            message,
            code="PIPECAT_MODULE_UNAVAILABLE",
            phase="runtime_import",
            missing_modules=_missing_modules_for_start_error(websocket),
            metadata=metadata,
        )
    if isinstance(exc, ValueError):
        return PipecatRealtimePipelineError(
            message,
            code="PIPECAT_CONFIG_INVALID",
            phase="configuration",
            metadata=metadata,
        )

    classified = _classify_pipecat_start_error(message, websocket=websocket)
    return PipecatRealtimePipelineError(
        message,
        code=str(classified.get("code") or "PIPECAT_PIPELINE_START_FAILED"),
        phase=str(classified.get("phase") or "pipeline_start"),
        feature=classified.get("feature"),
        missing_modules=tuple(classified.get("modules") or ()),
        missing_env=tuple(classified.get("missingEnv") or ()),
        metadata=metadata,
    )


def _missing_modules_for_start_error(websocket: bool) -> tuple[str, ...]:
    with suppress(Exception):
        capability = get_pipecat_capability(require_websocket=websocket)
        return tuple(capability.missing_modules)
    return ()


def _requested_feature_metadata(config: RealtimePipelineConfig) -> dict[str, str | None]:
    metadata = dict(config.metadata)
    if _pipecat_realtime_profile(config) == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        return {
            "realtimeLlm": _realtime_llm_provider(metadata),
            "vad": (
                _feature_provider(metadata, "vad")
                if _realtime_turn_detection_is_disabled(metadata)
                else None
            ),
        }
    return {
        "stt": _feature_provider(metadata, "stt"),
        "tts": _feature_provider(metadata, "tts"),
        "llm": _feature_provider(metadata, "llm"),
        "vad": _feature_provider(metadata, "vad"),
        "turnDetection": _feature_provider(metadata, "turnDetection", "turn_detection"),
    }


def _pipecat_realtime_profile(config: RealtimePipelineConfig) -> str:
    metadata = dict(config.metadata)
    for key in (
        "profile",
        "realtimeProfile",
        "realtime_profile",
        "pipelineProfile",
        "pipeline_profile",
        "voiceProfile",
        "voice_profile",
    ):
        if profile := _normalize_pipecat_realtime_profile(metadata.get(key)):
            return profile

    for key in ("talkwise", "realtime", "runtime"):
        nested = metadata.get(key)
        if isinstance(nested, Mapping):
            for nested_key in (
                "profile",
                "realtimeProfile",
                "realtime_profile",
                "pipelineProfile",
                "pipeline_profile",
            ):
                if profile := _normalize_pipecat_realtime_profile(nested.get(nested_key)):
                    return profile
    return PIPECAT_REALTIME_PROFILE_CASCADE


def _normalize_pipecat_realtime_profile(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not text or text in {"none", "false", "disabled", "default"}:
        return None
    compact = text.replace("_", "")
    return PIPECAT_REALTIME_PROFILE_ALIASES.get(
        text,
        PIPECAT_REALTIME_PROFILE_ALIASES.get(compact),
    )


def _realtime_llm_provider(metadata: Mapping[str, Any]) -> str | None:
    provider = _feature_provider(
        metadata,
        "realtimeLlm",
        "realtime_llm",
        "openaiRealtime",
        "openai_realtime",
    )
    if provider is not None:
        return provider
    llm_provider = _feature_provider(metadata, "llm")
    return llm_provider or "openai"


def _realtime_llm_config(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    return _feature_config(
        metadata,
        "realtimeLlm",
        "realtime_llm",
        "openaiRealtime",
        "openai_realtime",
        "llm",
    )


def _realtime_turn_detection_is_disabled(metadata: Mapping[str, Any]) -> bool:
    raw_value = _realtime_turn_detection_raw_value(metadata)
    if raw_value is False:
        return True
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
        return normalized in {"false", "disabled", "none", "local", "manual"}
    if isinstance(raw_value, Mapping):
        mode = _metadata_text(raw_value, "mode", "type", "strategy")
        provider = _metadata_text(raw_value, "provider", "source")
        normalized = str(mode or provider or "").strip().lower().replace("-", "_")
        return normalized in {"false", "disabled", "none", "local", "manual", "pipecat"}
    return False


def _realtime_turn_detection_raw_value(metadata: Mapping[str, Any]) -> object | None:
    realtime_config = _realtime_llm_config(metadata)
    for source in (realtime_config, metadata):
        for key in (
            "turnDetection",
            "turn_detection",
            "realtimeTurnDetection",
            "realtime_turn_detection",
        ):
            if key in source:
                return source[key]
    return None


def _classify_pipecat_start_error(message: str, *, websocket: bool) -> dict[str, object]:
    classified = classify_realtime_pipeline_start_error_message(
        message,
        feature_phase="voice_processor_config",
    )
    if not classified:
        return {}

    if "openrouter" in message.lower() and classified.get("feature") == "llm:openai":
        classified["feature"] = "llm:openrouter"
    feature = str(classified.get("feature") or "")
    code = str(classified.get("code") or "")
    if code == "PIPECAT_MODULE_UNAVAILABLE":
        modules = _missing_modules_for_start_error(websocket)
    else:
        modules = _pipecat_start_error_modules(feature)
    if modules:
        classified["modules"] = modules
    return classified


def _pipecat_start_error_modules(feature: str) -> tuple[str, ...]:
    feature_name = feature.split(":", 1)[0] if feature else ""
    if feature_name in PIPECAT_FEATURE_MODULE_HINTS:
        return tuple(PIPECAT_FEATURE_MODULE_HINTS[feature_name])
    return ()


def _pipecat_feature_unavailable_error(
    message: str,
    *,
    feature: str,
    modules: Sequence[str],
) -> PipecatRealtimePipelineError:
    return PipecatRealtimePipelineError(
        message,
        code="PIPECAT_FEATURE_UNAVAILABLE",
        phase="voice_processor_config",
        feature=feature,
        missing_modules=tuple(modules),
    )


def _missing_openai_api_key_error(feature: str) -> PipecatRealtimePipelineError:
    label = feature.upper()
    return PipecatRealtimePipelineError(
        f"OpenAI API key is required for Pipecat OpenAI {label}",
        code="MISSING_OPENAI_API_KEY",
        phase="configuration",
        feature=f"{feature}:openai",
        missing_env=OPENAI_API_KEY_ENV_KEYS,
    )


def _missing_openrouter_api_key_error(feature: str) -> PipecatRealtimePipelineError:
    label = feature.upper()
    return PipecatRealtimePipelineError(
        f"OpenRouter API key is required for Pipecat OpenRouter {label}",
        code="MISSING_OPENROUTER_API_KEY",
        phase="configuration",
        feature=f"{feature}:openrouter",
        missing_env=OPENROUTER_API_KEY_ENV_KEYS,
    )


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
            raise PipecatRealtimePipelineError(
                "Pipecat FastAPI websocket transport is unavailable",
                code="PIPECAT_WEBSOCKET_UNAVAILABLE",
                phase="pipeline_build",
                missing_modules=(WEBSOCKET_PIPECAT_MODULE,),
            )
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
    if _pipecat_realtime_profile(config) == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        return build_pipecat_speech_to_speech_processors(runtime, config, context=context)

    llm_provider = _feature_provider(metadata, "llm")

    if _feature_provider(metadata, "vad") == "silero":
        if runtime.SileroVADAnalyzer is None or runtime.VADProcessor is None:
            raise _pipecat_feature_unavailable_error(
                "Pipecat Silero VAD processor is unavailable",
                feature="vad:silero",
                modules=(SILERO_VAD_PIPECAT_MODULE, VAD_PROCESSOR_PIPECAT_MODULE),
            )
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
            raise _pipecat_feature_unavailable_error(
                "Pipecat OpenAI realtime STT service is unavailable",
                feature="stt:openai",
                modules=(OPENAI_STT_PIPECAT_MODULE,),
            )
        stt_config = _feature_config(metadata, "stt")
        api_key = _openai_api_key(metadata)
        if not api_key:
            raise _missing_openai_api_key_error("stt")
        stt_settings_kwargs: dict[str, Any] = {}
        stt_model = (
            _metadata_text(stt_config, "model")
            or _metadata_text(metadata, "sttModel", "stt_model")
            or config.model
        )
        if stt_model:
            stt_settings_kwargs["model"] = stt_model
        if language := _metadata_text(stt_config, "language"):
            stt_settings_kwargs["language"] = language
        if prompt := _metadata_text(stt_config, "prompt"):
            stt_settings_kwargs["prompt"] = prompt
        noise_reduction = _metadata_text(
            stt_config,
            "noiseReduction",
            "noise_reduction",
        ) or _metadata_text(metadata, "noiseReduction", "noise_reduction")
        if noise_reduction:
            stt_settings_kwargs["noise_reduction"] = noise_reduction
        processors.append(
            runtime.OpenAIRealtimeSTTService(
                api_key=api_key,
                base_url=_metadata_text(stt_config, "baseUrl", "base_url")
                or "wss://api.openai.com/v1/realtime",
                turn_detection=_turn_detection_config(metadata),
                should_interrupt=_metadata_bool(
                    stt_config,
                    "shouldInterrupt",
                    "should_interrupt",
                    default=True,
                ),
                settings=_service_settings(
                    runtime.OpenAIRealtimeSTTService,
                    _entrypoint(OPENAI_STT_PIPECAT_MODULE, "OpenAIRealtimeSTTService"),
                    stt_settings_kwargs,
                ),
            )
        )

    if (
        _feature_provider(metadata, "turnDetection", "turn_detection") == "pipecat"
        and llm_provider is None
    ):
        if runtime.UserTurnProcessor is None:
            raise _pipecat_feature_unavailable_error(
                "Pipecat user turn processor is unavailable",
                feature="turnDetection:pipecat",
                modules=(USER_TURN_PROCESSOR_PIPECAT_MODULE,),
            )
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
    if llm_provider in PIPECAT_SUPPORTED_LLM_PROVIDERS:
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
            raise _pipecat_feature_unavailable_error(
                "Pipecat OpenAI TTS service is unavailable",
                feature="tts:openai",
                modules=(OPENAI_TTS_PIPECAT_MODULE,),
            )
        tts_config = _feature_config(metadata, "tts")
        api_key = _openai_api_key(metadata)
        if not api_key:
            raise _missing_openai_api_key_error("tts")
        tts_settings_kwargs: dict[str, Any] = {}
        if tts_model := (
            _metadata_text(tts_config, "model") or _metadata_text(metadata, "ttsModel", "tts_model")
        ):
            tts_settings_kwargs["model"] = tts_model
        if voice := (
            config.voice or _metadata_text(tts_config, "voice") or _metadata_text(metadata, "voice")
        ):
            tts_settings_kwargs["voice"] = voice
        if instructions := (config.instructions or _metadata_text(tts_config, "instructions")):
            tts_settings_kwargs["instructions"] = instructions
        if (speed := _metadata_float(tts_config, "speed")) is not None:
            tts_settings_kwargs["speed"] = speed
        processors.append(
            runtime.OpenAITTSService(
                api_key=api_key,
                base_url=_metadata_text(tts_config, "baseUrl", "base_url"),
                sample_rate=_metadata_int(tts_config, "sampleRate", "sample_rate")
                or _metadata_int(metadata, "outputSampleRate", "output_sample_rate"),
                settings=_service_settings(
                    runtime.OpenAITTSService,
                    _entrypoint(OPENAI_TTS_PIPECAT_MODULE, "OpenAITTSService"),
                    tts_settings_kwargs,
                ),
            )
        )

    if assistant_aggregator is not None:
        processors.append(assistant_aggregator)

    return tuple(processors)


def build_pipecat_speech_to_speech_processors(
    runtime: PipecatRuntime,
    config: RealtimePipelineConfig,
    *,
    context: TrainingVoiceContext | None = None,
) -> tuple[Any, Any, Any]:
    """Build Pipecat's OpenAI realtime speech-to-speech processor chain."""

    metadata = dict(config.metadata)
    realtime_config = _realtime_llm_config(metadata)
    _ensure_realtime_llm_runtime_available(runtime)

    api_key = _openai_api_key(metadata) or _metadata_text(
        realtime_config,
        "openaiApiKey",
        "openai_api_key",
        "apiKey",
        "api_key",
    )
    if not api_key:
        raise _missing_openai_api_key_error("realtimeLlm")

    model = (
        _metadata_text(realtime_config, "model")
        or _metadata_text(
            metadata,
            "realtimeModel",
            "realtime_model",
            "openaiRealtimeModel",
            "openai_realtime_model",
            "model",
        )
        or config.model
    )
    system_instruction = _llm_system_instruction(context, config)
    session_properties = _openai_realtime_session_properties(
        runtime,
        config=config,
        metadata=metadata,
        realtime_config=realtime_config,
        system_instruction=system_instruction,
    )
    settings_kwargs: dict[str, Any] = {"session_properties": session_properties}
    if model:
        settings_kwargs["model"] = model
    if system_instruction:
        settings_kwargs["system_instruction"] = system_instruction
    if (temperature := _metadata_float(realtime_config, "temperature")) is not None:
        settings_kwargs["temperature"] = temperature
    if (max_tokens := _metadata_int(realtime_config, "maxTokens", "max_tokens")) is not None:
        settings_kwargs["max_tokens"] = max_tokens
    if (top_p := _metadata_float(realtime_config, "topP", "top_p")) is not None:
        settings_kwargs["top_p"] = top_p

    service_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": _metadata_text(realtime_config, "baseUrl", "base_url")
        or _metadata_text(metadata, "realtimeBaseUrl", "realtime_base_url")
        or "wss://api.openai.com/v1/realtime",
        "settings": _service_settings(
            runtime.OpenAIRealtimeLLMService,
            _entrypoint(
                OPENAI_REALTIME_LLM_PIPECAT_MODULE,
                "OpenAIRealtimeLLMService",
            ),
            settings_kwargs,
        ),
        "start_audio_paused": _metadata_bool(
            realtime_config,
            "startAudioPaused",
            "start_audio_paused",
            default=False,
        ),
    }
    if user_audio_preroll := _metadata_float(
        realtime_config,
        "userAudioPrerollSecs",
        "user_audio_preroll_secs",
    ):
        service_kwargs["user_audio_preroll_secs"] = user_audio_preroll
    if video_detail := _metadata_text(realtime_config, "videoFrameDetail", "video_frame_detail"):
        service_kwargs["video_frame_detail"] = video_detail
    if start_video_paused := _metadata_bool(
        realtime_config,
        "startVideoPaused",
        "start_video_paused",
        default=None,
    ):
        service_kwargs["start_video_paused"] = start_video_paused

    llm = runtime.OpenAIRealtimeLLMService(**service_kwargs)
    llm_context = runtime.LLMContext(messages=_llm_context_messages(context))
    user_aggregator, assistant_aggregator = runtime.LLMContextAggregatorPair(
        llm_context,
        user_params=_realtime_llm_user_aggregator_params(
            runtime,
            metadata,
            local_vad=_realtime_turn_detection_is_disabled(metadata),
        ),
        assistant_params=runtime.LLMAssistantAggregatorParams(),
        realtime_service_mode=True,
    )
    return user_aggregator, llm, assistant_aggregator


def build_pipecat_llm_processors(
    runtime: PipecatRuntime,
    config: RealtimePipelineConfig,
    *,
    context: TrainingVoiceContext | None = None,
) -> tuple[Any, Any, Any]:
    """Build Pipecat-native LLM context, aggregators, and selected LLM service."""

    metadata = dict(config.metadata)
    llm_provider = _feature_provider(metadata, "llm") or "openai"
    llm_feature = _llm_feature(llm_provider)
    llm_service = _llm_service_class(runtime, llm_provider)
    if llm_service is None:
        raise _pipecat_feature_unavailable_error(
            _llm_service_unavailable_message(llm_provider),
            feature=llm_feature,
            modules=(_llm_service_module(llm_provider),),
        )
    if (
        runtime.LLMContext is None
        or runtime.LLMContextAggregatorPair is None
        or runtime.LLMUserAggregatorParams is None
        or runtime.LLMAssistantAggregatorParams is None
    ):
        raise _pipecat_feature_unavailable_error(
            "Pipecat LLM context aggregators are unavailable",
            feature=llm_feature,
            modules=(LLM_CONTEXT_PIPECAT_MODULE, LLM_RESPONSE_PIPECAT_MODULE),
        )

    llm_config = _feature_config(metadata, "llm")
    api_key = _llm_api_key(metadata, llm_config, llm_provider)
    if not api_key:
        if llm_provider == OPENROUTER_LLM_PROVIDER:
            raise _missing_openrouter_api_key_error("llm")
        raise _missing_openai_api_key_error("llm")

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

    llm = llm_service(
        api_key=api_key,
        base_url=_llm_base_url(metadata, llm_config, llm_provider),
        settings=_service_settings(
            llm_service,
            _entrypoint(_llm_service_module(llm_provider), _llm_service_name(llm_provider)),
            settings_kwargs,
        ),
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
    profile = _pipecat_realtime_profile(config)
    requested_features = _requested_feature_metadata(config)
    openai_requirements = _resolved_openai_runtime_requirements(
        model=config.model or _metadata_text(metadata, "model", "openaiModel", "openai_model"),
        voice=config.voice or _metadata_text(metadata, "voice"),
        input_audio_format=config.input_audio_format
        or _metadata_text(metadata, "inputAudioFormat", "input_audio_format"),
        output_audio_format=config.output_audio_format
        or _metadata_text(metadata, "outputAudioFormat", "output_audio_format"),
    )
    missing: list[str] = []
    llm_provider = _feature_provider(metadata, "llm")
    if profile == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        if (
            _realtime_llm_provider(metadata) == "openai"
            and not capability.openai_realtime_llm_available
        ):
            missing.append("realtimeLlm:openai")
        if (
            _realtime_turn_detection_is_disabled(metadata)
            and _feature_provider(metadata, "vad") == "silero"
            and not capability.vad_available
        ):
            missing.append("vad:silero")
    else:
        if _feature_provider(metadata, "stt") == "openai" and not capability.stt_available:
            missing.append("stt:openai")
        if _feature_provider(metadata, "tts") == "openai" and not capability.tts_available:
            missing.append("tts:openai")
        if llm_provider == "openai" and not capability.llm_available:
            missing.append("llm:openai")
        if llm_provider == OPENROUTER_LLM_PROVIDER and not capability.openrouter_llm_available:
            missing.append(_llm_feature(llm_provider))
        if _feature_provider(metadata, "vad") == "silero" and not capability.vad_available:
            missing.append("vad:silero")
        if (
            _feature_provider(metadata, "turnDetection", "turn_detection") == "pipecat"
            and not capability.turn_detection_available
        ):
            missing.append("turnDetection:pipecat")
    readiness = _pipecat_pipeline_readiness(
        capability,
        config=config,
        websocket=websocket,
        requested_features=requested_features,
        missing_features=missing,
        openai_requirements=openai_requirements,
    )
    readiness_payload = readiness.to_dict()
    production_readiness = _pipecat_realtime_production_readiness(
        local_runtime_ready=readiness.ready,
    )

    return RealtimePipelineCapability(
        provider=config.provider,
        core_available=capability.core_available,
        media_transport="pipecat.websocket" if websocket is not None else "talkwise.audio_chunks",
        runtime=REALTIME_RUNTIME_PIPECAT,
        stt=(
            "openai_realtime"
            if profile == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH
            else _feature_provider(metadata, "stt")
        ),
        tts=(
            "openai_realtime"
            if profile == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH
            else _feature_provider(metadata, "tts")
        ),
        llm=(
            "openai_realtime"
            if profile == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH
            else llm_provider
        ),
        vad=(
            _feature_provider(metadata, "vad")
            if profile != PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH
            or _realtime_turn_detection_is_disabled(metadata)
            else None
        ),
        turn_detection=(
            "openai_realtime"
            if profile == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH
            and not _realtime_turn_detection_is_disabled(metadata)
            else _feature_provider(metadata, "turnDetection", "turn_detection")
        ),
        missing_features=tuple(missing),
        ready_for_call=readiness.ready,
        readiness=readiness,
        errors=tuple(dict(error) for error in readiness_payload["blockingReasons"]),
        metadata={
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "coreAvailable": capability.core_available,
            "websocketAvailable": capability.websocket_available,
            "sttAvailable": capability.stt_available,
            "ttsAvailable": capability.tts_available,
            "llmAvailable": capability.llm_available,
            "openaiRealtimeLlmAvailable": capability.openai_realtime_llm_available,
            "openrouterLlmAvailable": capability.openrouter_llm_available,
            "vadAvailable": capability.vad_available,
            "turnDetectionAvailable": capability.turn_detection_available,
            "profile": profile,
            "profileContract": pipecat_realtime_profile_contracts()[profile],
            "profiles": _pipecat_realtime_profile_payload(capability),
            "requestedFeatures": requested_features,
            "openaiRuntime": dict(openai_requirements),
            "productionReady": bool(production_readiness["readyForProduction"]),
            "productionReadiness": production_readiness,
            "dependencyProbe": _pipecat_dependency_probe(
                capability,
                require_websocket=websocket is not None,
            ),
            "providerCatalogSummary": pipecat_provider_catalog_summary(),
            "optionalMissingModules": capability.optional_missing_modules,
            "runtimeLoaded": runtime is not None,
            "vadEntrypoint": SILERO_VAD_PIPECAT_MODULE,
            "sttEntrypoint": OPENAI_STT_PIPECAT_MODULE,
            "ttsEntrypoint": OPENAI_TTS_PIPECAT_MODULE,
            "llmEntrypoint": OPENAI_LLM_PIPECAT_MODULE,
            "realtimeLlmEntrypoint": OPENAI_REALTIME_LLM_PIPECAT_MODULE,
            "realtimeEventsEntrypoint": OPENAI_REALTIME_EVENTS_PIPECAT_MODULE,
            "llmService": _llm_service_metadata(metadata),
            "turnDetectionEntrypoint": USER_TURN_PROCESSOR_PIPECAT_MODULE,
        },
    )


def _pipecat_pipeline_readiness(
    capability: PipecatCapability,
    *,
    config: RealtimePipelineConfig,
    websocket: Any | None,
    requested_features: Mapping[str, str | None],
    missing_features: Sequence[str],
    openai_requirements: Mapping[str, str | None],
) -> RealtimeProviderReadiness:
    blockers: list[RealtimeReadinessIssue] = []
    if not capability.core_available:
        blockers.append(
            RealtimeReadinessIssue(
                code="PIPECAT_MODULE_UNAVAILABLE",
                message="Pipecat core modules are required before starting realtime calls",
                phase="capability_check",
                provider="pipecat",
                modules=tuple(str(module) for module in capability.missing_modules),
            )
        )
    elif websocket is not None and not capability.websocket_available:
        blockers.append(
            RealtimeReadinessIssue(
                code="PIPECAT_WEBSOCKET_UNAVAILABLE",
                message="Pipecat websocket transport is required before starting realtime calls",
                phase="capability_check",
                provider="pipecat",
                modules=tuple(str(module) for module in capability.missing_modules)
                or (WEBSOCKET_PIPECAT_MODULE,),
            )
        )

    optional_missing_modules = tuple(str(module) for module in capability.optional_missing_modules)
    for feature in missing_features:
        feature_name, _, provider = feature.partition(":")
        requirement = _pipecat_feature_requirement(feature_name, provider)
        blockers.append(
            RealtimeReadinessIssue(
                code=str(requirement["code"]) if requirement else "PIPECAT_FEATURE_UNAVAILABLE",
                message=(
                    str(requirement["message"])
                    if requirement
                    else (
                        f"Pipecat {feature_name} provider '{provider}' is required "
                        "before starting realtime calls"
                    )
                ),
                phase="capability_check",
                provider="pipecat",
                feature=str(requirement["feature"]) if requirement else feature,
                modules=_pipecat_feature_missing_modules(
                    feature_name,
                    optional_missing_modules,
                    provider,
                ),
            )
        )

    metadata = dict(config.metadata)
    uses_openai_key = any(
        requested_features.get(feature) == "openai"
        for feature in ("stt", "tts", "llm", "realtimeLlm")
    )
    uses_openrouter_key = requested_features.get("llm") == OPENROUTER_LLM_PROVIDER
    if uses_openai_key and not _openai_api_key(metadata):
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_API_KEY",
                message=(
                    "Set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY "
                    "before starting Pipecat realtime calls"
                ),
                phase="configuration",
                provider="pipecat",
                missing_env=OPENAI_API_KEY_ENV_KEYS,
            )
        )
    if uses_openrouter_key and not _openrouter_api_key(metadata):
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENROUTER_API_KEY",
                message=(
                    "Set REALTIME_OPENROUTER_API_KEY, OPENROUTER_API_KEY, or "
                    "LLM__API_KEY with LLM__PROVIDER=openrouter before starting "
                    "Pipecat realtime calls"
                ),
                phase="configuration",
                provider="pipecat",
                feature="llm:openrouter",
                missing_env=OPENROUTER_API_KEY_ENV_KEYS,
            )
        )
    if not openai_requirements.get("model"):
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_MODEL",
                message="Configure REALTIME_OPENAI_MODEL before starting Pipecat realtime calls",
                phase="configuration",
                provider="pipecat",
                feature="model",
                missing_env=(OPENAI_REALTIME_MODEL_SETTING,),
            )
        )
    if not openai_requirements.get("voice"):
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_VOICE",
                message="Configure REALTIME_OPENAI_VOICE before starting Pipecat realtime calls",
                phase="configuration",
                provider="pipecat",
                feature="voice",
                missing_env=(OPENAI_REALTIME_VOICE_SETTING,),
            )
        )
    if not openai_requirements.get("inputAudioFormat"):
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
                message=(
                    "Configure REALTIME_OPENAI_INPUT_AUDIO_FORMAT before starting "
                    "Pipecat realtime calls"
                ),
                phase="configuration",
                provider="pipecat",
                feature="audioFormat",
                missing_env=(OPENAI_REALTIME_INPUT_AUDIO_FORMAT_SETTING,),
            )
        )

    return build_realtime_readiness(
        required={
            "transport": "websocket" if websocket is not None else "audio_chunks",
            "features": dict(requested_features),
            "env": _pipecat_required_env(requested_features),
            "openai": dict(openai_requirements),
            "openrouter": _openrouter_required_metadata(metadata),
        },
        blocking_reasons=blockers,
        runtime=REALTIME_RUNTIME_PIPECAT,
    )


def create_talkwise_event_processor(
    runtime: PipecatRuntime,
    event_queue: asyncio.Queue[Mapping[str, Any]],
    *,
    config: RealtimePipelineConfig,
) -> Any:
    """Create a small Pipecat processor that mirrors transcript and TTS audio frames."""

    class TalkWiseEventProcessor(runtime.FrameProcessor):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._audio_output_sequence = 0
            self._turn_sequence = 0
            self._user_turn_open = False
            self._user_turn_started_at: float | None = None
            self._pending_user_turn_metrics: dict[str, Any] | None = None
            self._pending_user_turn_stopped_at: float | None = None

        async def process_frame(self, frame: Any, direction: Any) -> None:
            await super().process_frame(frame, direction)
            observed_at = _monotonic_seconds()
            audio_sequence = None
            if isinstance(frame, runtime.TTSAudioRawFrame):
                self._audio_output_sequence += 1
                audio_sequence = self._audio_output_sequence
            event = _event_from_pipecat_frame(
                runtime,
                frame,
                config=config,
                audio_sequence=audio_sequence,
            )
            if event is not None:
                self._enrich_realtime_metrics(event, observed_at=observed_at)
                await event_queue.put(event)
            await self.push_frame(frame, direction)

        def _enrich_realtime_metrics(
            self,
            event: Mapping[str, Any],
            *,
            observed_at: float,
        ) -> None:
            event_type = str(event.get("type") or "")
            if event_type == "user_turn.started":
                if not self._user_turn_open:
                    self._turn_sequence += 1
                    self._user_turn_started_at = observed_at
                self._user_turn_open = True
                self._pending_user_turn_metrics = None
                self._pending_user_turn_stopped_at = None
                return

            if event_type == "user_turn.stopped":
                if not self._user_turn_open and self._turn_sequence == 0:
                    self._turn_sequence += 1
                user_speech_ms = _elapsed_ms(self._user_turn_started_at, observed_at)
                self._user_turn_open = False
                self._pending_user_turn_stopped_at = observed_at
                metrics: dict[str, Any] = {
                    "schemaVersion": 1,
                    "source": "pipecat_frames",
                    "turnSequence": self._turn_sequence,
                    "latencyStartEvent": "user_turn.stopped",
                }
                if user_speech_ms is not None:
                    metrics["userSpeechMs"] = user_speech_ms
                silence_seconds = _event_payload_float(event, "silenceSeconds")
                if silence_seconds is not None:
                    metrics["silenceSeconds"] = silence_seconds
                self._pending_user_turn_metrics = metrics
                self._user_turn_started_at = None
                return

            if event_type not in {"assistant_speaking.started", "audio.output"}:
                return
            if not self._pending_user_turn_metrics:
                return

            metrics = dict(self._pending_user_turn_metrics)
            metrics["latencyEndEvent"] = event_type
            turn_latency_ms = _elapsed_ms(self._pending_user_turn_stopped_at, observed_at)
            if turn_latency_ms is not None:
                metrics["turnLatencyMs"] = turn_latency_ms
            _attach_realtime_metrics(event, metrics)
            self._pending_user_turn_metrics = None
            self._pending_user_turn_stopped_at = None

    return TalkWiseEventProcessor(name="TalkWiseEventProcessor")


def _event_from_pipecat_frame(
    runtime: PipecatRuntime,
    frame: Any,
    *,
    config: RealtimePipelineConfig,
    audio_sequence: int | None = None,
) -> Mapping[str, Any] | None:
    if isinstance(frame, runtime.TTSAudioRawFrame):
        return _tts_audio_event_from_pipecat_frame(
            frame,
            config=config,
            audio_sequence=audio_sequence,
        )
    if event := _talkwise_turn_event_from_pipecat_frame(runtime, frame, config=config):
        return event
    if runtime.InterimTranscriptionFrame is not None and isinstance(
        frame, runtime.InterimTranscriptionFrame
    ):
        user_id = getattr(frame, "user_id", None)
        text = getattr(frame, "text", "")
        event: dict[str, Any] = {
            "type": "transcript.delta",
            "runtime": REALTIME_RUNTIME_PIPECAT,
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
            "runtime": REALTIME_RUNTIME_PIPECAT,
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
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "text": frame.text,
            "provider": config.provider,
            "source": "pipecat",
            "timestamp": getattr(frame, "timestamp", None),
        }
        return _with_frame_metadata(event, frame, config=config)
    return None


def _talkwise_turn_event_from_pipecat_frame(
    runtime: PipecatRuntime,
    frame: Any,
    *,
    config: RealtimePipelineConfig,
) -> Mapping[str, Any] | None:
    if _is_pipecat_frame(frame, runtime.UserStartedSpeakingFrame):
        return _talkwise_realtime_event(
            "user_turn.started",
            frame,
            config=config,
            participant="user",
            state="started",
            signal="user_turn",
        )
    if _is_pipecat_frame(frame, runtime.VADUserStartedSpeakingFrame):
        return _talkwise_realtime_event(
            "user_turn.started",
            frame,
            config=config,
            participant="user",
            state="started",
            signal="vad",
            payload={"speechSeconds": _frame_float(frame, "start_secs")},
        )
    if _is_pipecat_frame(frame, runtime.UserStoppedSpeakingFrame):
        return _talkwise_realtime_event(
            "user_turn.stopped",
            frame,
            config=config,
            participant="user",
            state="stopped",
            signal="user_turn",
        )
    if _is_pipecat_frame(frame, runtime.VADUserStoppedSpeakingFrame):
        return _talkwise_realtime_event(
            "user_turn.stopped",
            frame,
            config=config,
            participant="user",
            state="stopped",
            signal="vad",
            payload={"silenceSeconds": _frame_float(frame, "stop_secs")},
        )
    if _is_pipecat_frame(frame, runtime.BotStartedSpeakingFrame):
        return _talkwise_realtime_event(
            "assistant_speaking.started",
            frame,
            config=config,
            participant="assistant",
            state="started",
            signal="bot_speaking",
        )
    if _is_pipecat_frame(frame, runtime.BotStoppedSpeakingFrame):
        return _talkwise_realtime_event(
            "assistant_speaking.stopped",
            frame,
            config=config,
            participant="assistant",
            state="stopped",
            signal="bot_speaking",
        )
    if _is_pipecat_frame(frame, runtime.InterruptionFrame):
        return _talkwise_realtime_event(
            "interrupted",
            frame,
            config=config,
            participant="user",
            state="interrupted",
            signal="interruption",
        )
    if _is_pipecat_frame(frame, runtime.UserIdleTimeoutUpdateFrame):
        return _talkwise_realtime_event(
            "silence_timeout",
            frame,
            config=config,
            participant="user",
            state="updated",
            signal="user_idle_timeout",
            payload={"timeoutSeconds": _frame_float(frame, "timeout")},
        )
    return None


def _is_pipecat_frame(frame: Any, frame_type: type | None) -> bool:
    return frame_type is not None and isinstance(frame, frame_type)


def _talkwise_realtime_event(
    event_type: str,
    frame: Any,
    *,
    config: RealtimePipelineConfig,
    participant: str,
    state: str,
    signal: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event_payload: dict[str, Any] = {
        "schemaVersion": 1,
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": config.provider,
        "source": "pipecat",
        "participant": participant,
        "state": state,
        "signal": signal,
        "sourceEvent": frame.__class__.__name__,
    }
    if payload:
        for key, value in payload.items():
            safe_value = _json_safe_metadata(value)
            if safe_value is not None:
                event_payload[str(key)] = safe_value
    timestamp = _json_safe_metadata(getattr(frame, "timestamp", None))
    if timestamp is not None:
        event_payload["timestamp"] = timestamp

    event = {
        "type": event_type,
        "schemaVersion": 1,
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": config.provider,
        "source": "pipecat",
        "participant": participant,
        "state": state,
        "signal": signal,
        "payload": event_payload,
    }
    return _with_frame_metadata(event, frame, config=config)


def _frame_float(frame: Any, attr_name: str) -> float | None:
    value = getattr(frame, attr_name, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_payload_float(event: Mapping[str, Any], key: str) -> float | None:
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        return None
    value = payload.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(started_at: float | None, ended_at: float) -> int | None:
    if started_at is None:
        return None
    return max(0, int(round((ended_at - started_at) * 1000)))


def _monotonic_seconds() -> float:
    return time.monotonic()


def _attach_realtime_metrics(event: Mapping[str, Any], metrics: Mapping[str, Any]) -> None:
    if not isinstance(event, dict):
        return
    safe_metrics = _json_safe_metadata(metrics)
    if not isinstance(safe_metrics, Mapping):
        return

    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        event["metadata"] = metadata
    metadata["realtimeMetrics"] = dict(safe_metrics)

    payload = event.get("payload")
    if isinstance(payload, dict):
        payload_metadata = payload.get("metadata")
        if isinstance(payload_metadata, dict):
            payload_metadata["realtimeMetrics"] = dict(safe_metrics)


def _tts_audio_event_from_pipecat_frame(
    frame: Any,
    *,
    config: RealtimePipelineConfig,
    audio_sequence: int | None,
) -> Mapping[str, Any] | None:
    audio = _bytes_from_audio_frame(frame)
    if audio is None:
        return None

    sequence = _frame_audio_sequence(frame, fallback=audio_sequence)
    context_id = _json_safe_metadata(getattr(frame, "context_id", None))
    return RealtimeOutputAudio(
        data=audio,
        provider=config.provider,
        runtime=REALTIME_RUNTIME_PIPECAT,
        mime_type=_output_audio_mime_type(config, frame),
        sequence=sequence,
        sample_rate=_frame_sample_rate(frame, config),
        channels=_frame_channels(frame, config),
        context_id=str(context_id) if context_id is not None else None,
        metadata=_frame_config_metadata(frame, config=config),
    ).to_event()


def _bytes_from_audio_frame(frame: Any) -> bytes | None:
    audio = getattr(frame, "audio", None)
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, bytearray):
        return bytes(audio)
    if isinstance(audio, memoryview):
        return audio.tobytes()
    return None


def _frame_audio_sequence(frame: Any, *, fallback: int | None) -> int | None:
    raw_metadata = getattr(frame, "metadata", None)
    if isinstance(raw_metadata, Mapping):
        for key in ("sequence", "audioSequence", "audio_sequence"):
            if key in raw_metadata:
                try:
                    return int(raw_metadata[key])
                except (TypeError, ValueError):
                    break
    return fallback


def _frame_sample_rate(frame: Any, config: RealtimePipelineConfig) -> int:
    value = getattr(frame, "sample_rate", None)
    if value is None:
        value = _audio_out_sample_rate(config) or _audio_in_sample_rate(config)
    return int(value or 16000)


def _frame_channels(frame: Any, config: RealtimePipelineConfig) -> int:
    value = getattr(frame, "num_channels", None)
    if value is None:
        value = getattr(frame, "channels", None)
    if value is None:
        value = config.metadata.get("outputChannels") or config.metadata.get("channels")
    return int(value or 1)


def _output_audio_mime_type(config: RealtimePipelineConfig, frame: Any) -> str:
    raw_metadata = getattr(frame, "metadata", None)
    if isinstance(raw_metadata, Mapping):
        mime_type = _metadata_text(raw_metadata, "mimeType", "mime_type")
        if mime_type:
            return _normalize_audio_mime_type(mime_type)

    metadata = dict(config.metadata)
    mime_type = _metadata_text(
        metadata,
        "outputMimeType",
        "output_mime_type",
        "audioOutputMimeType",
        "audio_output_mime_type",
    )
    if mime_type:
        return _normalize_audio_mime_type(mime_type)

    tts_config = _feature_config(metadata, "tts")
    mime_type = _metadata_text(tts_config, "mimeType", "mime_type", "outputMimeType")
    if mime_type:
        return _normalize_audio_mime_type(mime_type)

    audio_format = (
        config.output_audio_format
        or _metadata_text(metadata, "outputAudioFormat", "output_audio_format")
        or _metadata_text(tts_config, "format", "audioFormat", "audio_format")
    )
    if audio_format:
        return _normalize_audio_mime_type(audio_format)
    return "audio/pcm"


def _normalize_audio_mime_type(value: str) -> str:
    text = value.strip().lower()
    if not text:
        return "audio/pcm"
    if "/" in text:
        return text
    aliases = {
        "pcm": "audio/pcm",
        "pcm16": "audio/pcm",
        "s16le": "audio/pcm",
        "l16": "audio/l16",
        "wav": "audio/wav",
        "wave": "audio/wav",
        "mp3": "audio/mpeg",
        "mpeg": "audio/mpeg",
        "opus": "audio/opus",
        "ogg": "audio/ogg",
        "webm": "audio/webm",
    }
    return aliases.get(text, f"audio/{text}")


def _with_frame_metadata(
    event: dict[str, Any],
    frame: Any,
    *,
    config: RealtimePipelineConfig,
) -> dict[str, Any]:
    metadata = _frame_config_metadata(frame, config=config)
    if metadata:
        event["metadata"] = metadata
    return event


def _frame_config_metadata(
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
    return metadata


def _frame_event_metadata(frame: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    raw_metadata = getattr(frame, "metadata", None)
    if isinstance(raw_metadata, Mapping):
        safe_metadata = _json_safe_metadata(raw_metadata)
        if isinstance(safe_metadata, Mapping):
            metadata.update(dict(safe_metadata))

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
    return sanitize_realtime_public_value(value)


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
        scenario_template_id = metadata.get("scenarioTemplateId") or metadata.get(
            "scenario_template_id"
        )
        if scenario_template_id:
            rendered = _compact_json(scenario_template_id)
            if rendered:
                parts.append(f"Scenario template ID: {rendered}")
        category = metadata.get("category")
        if category:
            rendered = _compact_json(category)
            if rendered:
                parts.append(f"Scenario category: {rendered}")
        active_persona = _active_persona_from_metadata(metadata)
        if active_persona:
            parts.append(f"Active persona ID: {active_persona}")
        live_guidance = metadata.get("liveGuidance") or metadata.get("live_guidance")
        if live_guidance:
            rendered = _compact_json(live_guidance)
            if rendered:
                parts.append(f"Live guidance: {rendered}")
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
    metadata = {**dict(context.metadata), **dict(config.metadata)}
    start_metadata: dict[str, Any] = {
        "source": "talkwise",
        "provider": config.provider,
        "model": config.model,
        "voice": config.voice,
        "trainingSessionId": context.binding.training_session_id,
        "roomId": context.binding.room_id,
        "taskGoal": context.task_goal,
        "rubric": dict(context.rubric),
        "metadata": metadata,
    }
    for output_key, input_keys in {
        "personaIds": ("personaIds", "persona_ids"),
        "scenarioId": ("scenarioId", "scenario_id"),
        "scenarioTemplateId": ("scenarioTemplateId", "scenario_template_id"),
        "category": ("category",),
        "liveGuidance": ("liveGuidance", "live_guidance"),
    }.items():
        for input_key in input_keys:
            safe_value = _json_safe_metadata(metadata.get(input_key))
            if safe_value is not None:
                start_metadata[output_key] = safe_value
                break
    recent_turns = _json_safe_metadata(tuple(dict(turn) for turn in context.recent_turns))
    if recent_turns is not None:
        start_metadata["recentTurns"] = recent_turns
    return start_metadata


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
                if text.replace("-", "_").replace(" ", "_") in OPENROUTER_LLM_PROVIDER_ALIASES:
                    return OPENROUTER_LLM_PROVIDER
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


def _ensure_realtime_llm_runtime_available(runtime: PipecatRuntime) -> None:
    if runtime.OpenAIRealtimeLLMService is None:
        raise _pipecat_feature_unavailable_error(
            "Pipecat OpenAI realtime LLM service is unavailable",
            feature="realtimeLlm:openai",
            modules=(OPENAI_REALTIME_LLM_PIPECAT_MODULE,),
        )
    missing_context = (
        runtime.LLMContext is None
        or runtime.LLMContextAggregatorPair is None
        or runtime.LLMUserAggregatorParams is None
        or runtime.LLMAssistantAggregatorParams is None
    )
    if missing_context:
        raise _pipecat_feature_unavailable_error(
            "Pipecat realtime LLM context aggregators are unavailable",
            feature="realtimeLlm:openai",
            modules=(LLM_CONTEXT_PIPECAT_MODULE, LLM_RESPONSE_PIPECAT_MODULE),
        )
    event_symbols = (
        runtime.SessionProperties,
        runtime.AudioConfiguration,
        runtime.AudioInput,
        runtime.AudioOutput,
        runtime.InputAudioTranscription,
        runtime.InputAudioNoiseReduction,
        runtime.SemanticTurnDetection,
        runtime.TurnDetection,
        runtime.PCMAudioFormat,
        runtime.PCMUAudioFormat,
        runtime.PCMAAudioFormat,
    )
    if any(symbol is None for symbol in event_symbols):
        raise _pipecat_feature_unavailable_error(
            "Pipecat OpenAI realtime event configuration classes are unavailable",
            feature="realtimeLlm:openai",
            modules=(OPENAI_REALTIME_EVENTS_PIPECAT_MODULE,),
        )


def _openai_realtime_session_properties(
    runtime: PipecatRuntime,
    *,
    config: RealtimePipelineConfig,
    metadata: Mapping[str, Any],
    realtime_config: Mapping[str, Any],
    system_instruction: str | None,
) -> Any:
    input_audio_format = _openai_realtime_audio_format(
        runtime,
        _metadata_text(realtime_config, "inputAudioFormat", "input_audio_format")
        or config.input_audio_format
        or _metadata_text(metadata, "inputAudioFormat", "input_audio_format"),
    )
    output_format_name = (
        _metadata_text(realtime_config, "outputAudioFormat", "output_audio_format")
        or config.output_audio_format
        or _metadata_text(metadata, "outputAudioFormat", "output_audio_format")
        or _metadata_text(realtime_config, "inputAudioFormat", "input_audio_format")
        or config.input_audio_format
        or _metadata_text(metadata, "inputAudioFormat", "input_audio_format")
    )
    output_audio_format = _openai_realtime_audio_format(runtime, output_format_name)
    transcription = runtime.InputAudioTranscription(
        model=(
            _metadata_text(
                realtime_config,
                "transcriptionModel",
                "transcription_model",
            )
            or _metadata_text(metadata, "transcriptionModel", "transcription_model")
        ),
        language=_metadata_text(realtime_config, "language")
        or _metadata_text(metadata, "language"),
        prompt=_metadata_text(realtime_config, "prompt")
        or _metadata_text(metadata, "transcriptionPrompt", "transcription_prompt"),
    )
    noise_reduction = _openai_realtime_noise_reduction(runtime, metadata, realtime_config)
    audio_input = runtime.AudioInput(
        format=input_audio_format,
        transcription=transcription,
        noise_reduction=noise_reduction,
        turn_detection=_openai_realtime_turn_detection(runtime, metadata),
    )
    audio_output = runtime.AudioOutput(
        format=output_audio_format,
        voice=(
            config.voice
            or _metadata_text(realtime_config, "voice")
            or _metadata_text(metadata, "voice")
        ),
        speed=_metadata_float(realtime_config, "speed"),
    )
    kwargs: dict[str, Any] = {
        "output_modalities": _realtime_output_modalities(realtime_config),
        "audio": runtime.AudioConfiguration(input=audio_input, output=audio_output),
    }
    if model := (
        _metadata_text(realtime_config, "model")
        or _metadata_text(
            metadata,
            "realtimeModel",
            "realtime_model",
            "openaiRealtimeModel",
            "openai_realtime_model",
            "model",
        )
        or config.model
    ):
        kwargs["model"] = model
    if system_instruction:
        kwargs["instructions"] = system_instruction
    max_output_tokens = _metadata_int(
        realtime_config,
        "maxOutputTokens",
        "max_output_tokens",
    )
    if max_output_tokens is not None:
        kwargs["max_output_tokens"] = max_output_tokens
    if tool_choice := _metadata_text(realtime_config, "toolChoice", "tool_choice"):
        kwargs["tool_choice"] = tool_choice
    if include := _metadata_text_list(realtime_config, "include"):
        kwargs["include"] = include
    return runtime.SessionProperties(**kwargs)


def _openai_realtime_audio_format(runtime: PipecatRuntime, value: object | None) -> Any:
    normalized = _normalize_openai_realtime_audio_format_name(value)
    if normalized == "pcm":
        return runtime.PCMAudioFormat()
    if normalized == "pcmu":
        return runtime.PCMUAudioFormat()
    if normalized == "pcma":
        return runtime.PCMAAudioFormat()
    raise ValueError(
        "OpenAI realtime audio format must be pcm16, audio/pcm, audio/pcmu, or audio/pcma"
    )


def _normalize_openai_realtime_audio_format_name(value: object | None) -> str:
    text = str(value or "pcm16").strip().lower().replace("-", "_")
    compact = text.replace("_", "").replace("/", "")
    if compact in {"pcm", "pcm16", "audiopcm", "linear16", "l16"}:
        return "pcm"
    if compact in {"pcmu", "audiopcmu", "g711ulaw", "ulaw", "mulaw"}:
        return "pcmu"
    if compact in {"pcma", "audiopcma", "g711alaw", "alaw"}:
        return "pcma"
    return text


def _openai_realtime_noise_reduction(
    runtime: PipecatRuntime,
    metadata: Mapping[str, Any],
    realtime_config: Mapping[str, Any],
) -> Any | None:
    noise_reduction = (
        _metadata_text(realtime_config, "noiseReduction", "noise_reduction")
        or _metadata_text(metadata, "noiseReduction", "noise_reduction")
        or "near_field"
    )
    normalized = noise_reduction.strip().lower()
    if normalized in {"none", "false", "disabled", "off"}:
        return None
    return runtime.InputAudioNoiseReduction(type=normalized)


def _openai_realtime_turn_detection(
    runtime: PipecatRuntime,
    metadata: Mapping[str, Any],
) -> Any:
    raw_value = _realtime_turn_detection_raw_value(metadata)
    if raw_value is None or raw_value is True:
        return runtime.SemanticTurnDetection()
    if raw_value is False:
        return False
    if isinstance(raw_value, str):
        return _openai_realtime_turn_detection_from_name(runtime, raw_value)
    if isinstance(raw_value, Mapping):
        mode = _metadata_text(raw_value, "mode", "type", "strategy")
        provider = _metadata_text(raw_value, "provider", "source")
        selected = mode or provider or "semantic_vad"
        normalized = selected.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {"openai", "openai_realtime", "semantic", "semantic_vad"}:
            return runtime.SemanticTurnDetection(
                **_processor_kwargs(
                    raw_value,
                    allowed={
                        "eagerness": "eagerness",
                        "createResponse": "create_response",
                        "create_response": "create_response",
                        "interruptResponse": "interrupt_response",
                        "interrupt_response": "interrupt_response",
                    },
                )
            )
        if normalized in {"server", "server_vad"}:
            return runtime.TurnDetection(
                **_processor_kwargs(
                    raw_value,
                    allowed={
                        "threshold": "threshold",
                        "prefixPaddingMs": "prefix_padding_ms",
                        "prefix_padding_ms": "prefix_padding_ms",
                        "silenceDurationMs": "silence_duration_ms",
                        "silence_duration_ms": "silence_duration_ms",
                    },
                )
            )
        if normalized in {"false", "disabled", "none", "local", "manual", "pipecat"}:
            return False
    raise ValueError("OpenAI realtime turn detection must be semantic_vad, server_vad, or disabled")


def _openai_realtime_turn_detection_from_name(runtime: PipecatRuntime, value: str) -> Any:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"semantic", "semantic_vad", "openai", "openai_realtime", "true"}:
        return runtime.SemanticTurnDetection()
    if normalized in {"server", "server_vad"}:
        return runtime.TurnDetection()
    if normalized in {"false", "disabled", "none", "local", "manual", "pipecat"}:
        return False
    raise ValueError("OpenAI realtime turn detection must be semantic_vad, server_vad, or disabled")


def _realtime_output_modalities(metadata: Mapping[str, Any]) -> list[str]:
    values = _metadata_text_list(
        metadata,
        "outputModalities",
        "output_modalities",
        "modalities",
    )
    if not values:
        return ["audio"]
    normalized: list[str] = []
    for value in values:
        item = value.strip().lower()
        if item == "both":
            normalized.extend(["text", "audio"])
            continue
        if item not in {"text", "audio"}:
            raise ValueError("OpenAI realtime output modalities must be text, audio, or both")
        normalized.append(item)
    return list(dict.fromkeys(normalized))


def _metadata_text_list(metadata: Mapping[str, Any], *keys: str) -> list[str] | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            values = [item.strip() for item in value.split(",")]
            return [item for item in values if item]
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
            values = [str(item).strip() for item in value]
            return [item for item in values if item]
    return None


def _realtime_llm_user_aggregator_params(
    runtime: PipecatRuntime,
    metadata: Mapping[str, Any],
    *,
    local_vad: bool,
) -> Any:
    turn_config = _feature_config(metadata, "turnDetection", "turn_detection")
    kwargs: dict[str, Any] = {}
    if local_vad:
        if runtime.SileroVADAnalyzer is None:
            raise _pipecat_feature_unavailable_error(
                "Pipecat Silero VAD analyzer is unavailable for local realtime turns",
                feature="vad:silero",
                modules=(SILERO_VAD_PIPECAT_MODULE,),
            )
        vad_config = _feature_config(metadata, "vad")
        vad_analyzer_kwargs: dict[str, Any] = {}
        if sample_rate := _metadata_int(
            vad_config,
            "sampleRate",
            "sample_rate",
            "vadSampleRate",
            "vad_sample_rate",
        ):
            vad_analyzer_kwargs["sample_rate"] = sample_rate
        if vad_params := _vad_params(runtime, vad_config):
            vad_analyzer_kwargs["params"] = vad_params
        kwargs["vad_analyzer"] = runtime.SileroVADAnalyzer(**vad_analyzer_kwargs)
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


def _openrouter_api_key(metadata: Mapping[str, Any]) -> str | None:
    llm_config = _feature_config(metadata, "llm")
    openrouter_config = _feature_config(metadata, "openrouter", "open_router")
    return (
        _metadata_text(
            llm_config,
            "openrouterApiKey",
            "openRouterApiKey",
            "openrouter_api_key",
            "apiKey",
            "api_key",
        )
        or _metadata_text(
            openrouter_config,
            "apiKey",
            "api_key",
            "openrouterApiKey",
            "openRouterApiKey",
            "openrouter_api_key",
        )
        or _metadata_text(
            metadata,
            "openrouterApiKey",
            "openRouterApiKey",
            "openrouter_api_key",
        )
        or _settings_openrouter_api_key()
        or os.getenv("REALTIME_OPENROUTER_API_KEY")
        or os.getenv("OPENROUTER_API_KEY")
    )


def _llm_api_key(
    metadata: Mapping[str, Any],
    llm_config: Mapping[str, Any],
    provider: str,
) -> str | None:
    if provider == OPENROUTER_LLM_PROVIDER:
        return _openrouter_api_key(metadata)
    return _metadata_text(
        llm_config,
        "openaiApiKey",
        "openai_api_key",
        "apiKey",
        "api_key",
    ) or _openai_api_key(metadata)


def _llm_base_url(
    metadata: Mapping[str, Any],
    llm_config: Mapping[str, Any],
    provider: str,
) -> str | None:
    configured = _metadata_text(llm_config, "baseUrl", "base_url") or _metadata_text(
        metadata,
        "llmBaseUrl",
        "llm_base_url",
    )
    if provider != OPENROUTER_LLM_PROVIDER:
        return configured

    openrouter_config = _feature_config(metadata, "openrouter", "open_router")
    return (
        configured
        or _metadata_text(
            llm_config,
            "openrouterBaseUrl",
            "openRouterBaseUrl",
            "openrouter_base_url",
        )
        or _metadata_text(
            openrouter_config,
            "baseUrl",
            "base_url",
            "openrouterBaseUrl",
            "openRouterBaseUrl",
            "openrouter_base_url",
        )
        or _metadata_text(
            metadata,
            "openrouterBaseUrl",
            "openRouterBaseUrl",
            "openrouter_base_url",
        )
        or _settings_openrouter_base_url()
        or os.getenv("REALTIME_OPENROUTER_BASE_URL")
        or os.getenv("OPENROUTER_BASE_URL")
        or OPENROUTER_LLM_BASE_URL
    )


def _llm_feature(provider: str | None) -> str:
    if provider == OPENROUTER_LLM_PROVIDER:
        return "llm:openrouter"
    return "llm:openai"


def _llm_service_unavailable_message(provider: str | None) -> str:
    if provider == OPENROUTER_LLM_PROVIDER:
        return "Pipecat OpenRouter LLM service is unavailable"
    return "Pipecat OpenAI LLM service is unavailable"


def _llm_service_class(runtime: PipecatRuntime, provider: str | None) -> type | None:
    if provider == OPENROUTER_LLM_PROVIDER:
        return runtime.OpenRouterLLMService
    return runtime.OpenAILLMService


def _llm_service_module(provider: str | None) -> str:
    if provider == OPENROUTER_LLM_PROVIDER:
        return OPENROUTER_LLM_PIPECAT_MODULE
    return OPENAI_LLM_PIPECAT_MODULE


def _llm_service_name(provider: str | None) -> str:
    if provider == OPENROUTER_LLM_PROVIDER:
        return "OpenRouterLLMService"
    return "OpenAILLMService"


def _llm_service_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    llm_provider = _feature_provider(metadata, "llm")
    llm_config = _feature_config(metadata, "llm")
    provider = llm_provider or "openai"
    return {
        "provider": llm_provider,
        "service": "openrouter" if provider == OPENROUTER_LLM_PROVIDER else "openai",
        "baseUrl": _llm_base_url(metadata, llm_config, provider),
        "entrypoint": _llm_service_module(provider),
    }


def _pipecat_required_env(requested_features: Mapping[str, str | None]) -> tuple[str, ...]:
    env_keys: list[str] = []
    if any(
        requested_features.get(feature) == "openai"
        for feature in ("stt", "tts", "llm", "realtimeLlm")
    ):
        env_keys.extend(OPENAI_API_KEY_ENV_KEYS)
    if requested_features.get("llm") == OPENROUTER_LLM_PROVIDER:
        env_keys.extend(OPENROUTER_API_KEY_ENV_KEYS)
    return tuple(dict.fromkeys(env_keys or list(OPENAI_API_KEY_ENV_KEYS)))


def _openrouter_required_metadata(metadata: Mapping[str, Any]) -> dict[str, object]:
    if _feature_provider(metadata, "llm") != OPENROUTER_LLM_PROVIDER:
        return {}
    llm_config = _feature_config(metadata, "llm")
    return {
        "baseUrl": _llm_base_url(metadata, llm_config, OPENROUTER_LLM_PROVIDER),
        "env": OPENROUTER_API_KEY_ENV_KEYS,
        "baseUrlEnv": OPENROUTER_BASE_URL_ENV_KEYS,
    }


def _settings_openai_api_key() -> str | None:
    try:
        from core.config import settings as app_settings
    except Exception:
        return None
    llm_settings = getattr(app_settings, "llm", None)
    llm_provider = (
        str(getattr(llm_settings, "provider", "") or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    llm_base_url = str(getattr(llm_settings, "base_url", "") or "").strip().lower()
    if llm_provider in OPENROUTER_LLM_PROVIDER_ALIASES or "openrouter.ai" in llm_base_url:
        llm_api_key = None
    else:
        llm_api_key = getattr(llm_settings, "api_key", None) if llm_settings is not None else None
    return (
        app_settings.REALTIME_OPENAI_API_KEY
        or llm_api_key
        or getattr(app_settings, "OPENAI_API_KEY", None)
    )


def _settings_openrouter_api_key() -> str | None:
    return _settings_llm_value_for_provider(OPENROUTER_LLM_PROVIDER, "api_key")


def _settings_openrouter_base_url() -> str | None:
    return _settings_llm_value_for_provider(OPENROUTER_LLM_PROVIDER, "base_url")


def _settings_llm_value_for_provider(provider: str, attr: str) -> str | None:
    try:
        from core.config import settings as app_settings
    except Exception:
        return None

    llm_settings = getattr(app_settings, "llm", None)
    if llm_settings is None:
        return None
    settings_provider = (
        str(getattr(llm_settings, "provider", "") or "")
        .strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )
    settings_base_url = str(getattr(llm_settings, "base_url", "") or "").strip().lower()
    if provider == OPENROUTER_LLM_PROVIDER:
        provider_matches = (
            settings_provider in OPENROUTER_LLM_PROVIDER_ALIASES
            or "openrouter.ai" in settings_base_url
        )
    else:
        provider_matches = settings_provider == provider
    if not provider_matches:
        return None
    return _clean_text(getattr(llm_settings, attr, None))


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
    _validate_pipecat_realtime_profile(metadata)
    if _pipecat_realtime_profile(config) == PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        _validate_pipecat_speech_to_speech_config(config)
        return

    _validate_provider(metadata, "stt", supported={"openai"})
    _validate_provider(metadata, "tts", supported={"openai"})
    _validate_provider(metadata, "llm", supported=PIPECAT_SUPPORTED_LLM_PROVIDERS)
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


def _validate_pipecat_realtime_profile(metadata: Mapping[str, Any]) -> None:
    for key in (
        "profile",
        "realtimeProfile",
        "realtime_profile",
        "pipelineProfile",
        "pipeline_profile",
        "voiceProfile",
        "voice_profile",
    ):
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text or text.lower() in {"none", "false", "disabled", "default"}:
            continue
        if _normalize_pipecat_realtime_profile(text) is None:
            supported = ", ".join(sorted(PIPECAT_REALTIME_PROFILE_ALIASES))
            raise ValueError(
                f"Unsupported Pipecat realtime profile '{text}'; expected one of: {supported}"
            )


def _validate_pipecat_speech_to_speech_config(config: RealtimePipelineConfig) -> None:
    metadata = dict(config.metadata)
    realtime_config = _realtime_llm_config(metadata)
    provider = _realtime_llm_provider(metadata)
    if provider != "openai":
        raise ValueError(f"Unsupported Pipecat realtimeLlm provider '{provider}'; expected openai")

    for value in (
        _metadata_text(realtime_config, "inputAudioFormat", "input_audio_format")
        or config.input_audio_format
        or _metadata_text(metadata, "inputAudioFormat", "input_audio_format"),
        _metadata_text(realtime_config, "outputAudioFormat", "output_audio_format")
        or config.output_audio_format
        or _metadata_text(metadata, "outputAudioFormat", "output_audio_format"),
    ):
        if value is not None:
            normalized = _normalize_openai_realtime_audio_format_name(value)
            if normalized not in {"pcm", "pcmu", "pcma"}:
                raise ValueError(
                    "OpenAI realtime audio format must be pcm16, audio/pcm, audio/pcmu, "
                    "or audio/pcma"
                )

    noise_reduction = _metadata_text(
        realtime_config, "noiseReduction", "noise_reduction"
    ) or _metadata_text(metadata, "noiseReduction", "noise_reduction")
    if noise_reduction is not None:
        normalized_noise = noise_reduction.strip().lower()
        if normalized_noise not in {"near_field", "far_field", "none", "false", "disabled", "off"}:
            raise ValueError("OpenAI realtime noise reduction must be near_field or far_field")

    if _realtime_turn_detection_raw_value(metadata) is not None:
        _validate_openai_realtime_turn_detection_value(metadata)

    if (
        _realtime_turn_detection_is_disabled(metadata)
        and _feature_provider(metadata, "vad") == "silero"
    ):
        vad_config = _feature_config(metadata, "vad")
        vad_sample_rate = _metadata_int(
            vad_config,
            "sampleRate",
            "sample_rate",
            "vadSampleRate",
            "vad_sample_rate",
        ) or _metadata_int(metadata, "vadSampleRate", "vad_sample_rate")
        if vad_sample_rate not in {None, 8000, 16000}:
            raise ValueError("Silero VAD sample rate must be 8000 or 16000")

    if (
        speed := _metadata_float(realtime_config, "speed")
    ) is not None and not 0.25 <= speed <= 4.0:
        raise ValueError("OpenAI realtime output speed must be between 0.25 and 4.0")
    temperature = _metadata_float(realtime_config, "temperature")
    if temperature is not None and not 0 <= temperature <= 2:
        raise ValueError("OpenAI realtime LLM temperature must be between 0 and 2")
    _realtime_output_modalities(realtime_config)


def _validate_openai_realtime_turn_detection_value(metadata: Mapping[str, Any]) -> None:
    raw_value = _realtime_turn_detection_raw_value(metadata)
    if raw_value is None or isinstance(raw_value, bool):
        return
    if isinstance(raw_value, str):
        _openai_realtime_turn_detection_from_name(_NoopRealtimeTurnRuntime, raw_value)
        return
    if isinstance(raw_value, Mapping):
        mode = _metadata_text(raw_value, "mode", "type", "strategy")
        provider = _metadata_text(raw_value, "provider", "source")
        selected = mode or provider or "semantic_vad"
        normalized = selected.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in {
            "openai",
            "openai_realtime",
            "semantic",
            "semantic_vad",
            "server",
            "server_vad",
            "false",
            "disabled",
            "none",
            "local",
            "manual",
            "pipecat",
        }:
            return
    raise ValueError("OpenAI realtime turn detection must be semantic_vad, server_vad, or disabled")


class _NoopRealtimeTurnRuntime:
    SemanticTurnDetection = object
    TurnDetection = object


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
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "coreEntrypoints": (
            "pipecat.pipeline.pipeline.Pipeline",
            "pipecat.pipeline.worker.PipelineParams",
            "pipecat.pipeline.worker.PipelineWorker",
            "pipecat.workers.base_worker.WorkerParams",
            "pipecat.workers.runner.WorkerRunner",
            "pipecat.processors.frame_processor.FrameProcessor",
            "pipecat.processors.frame_processor.FrameDirection",
        ),
        "frameEntrypoints": (
            "pipecat.frames.frames.InputAudioRawFrame",
            "pipecat.frames.frames.InterimTranscriptionFrame",
            "pipecat.frames.frames.TranscriptionFrame",
            "pipecat.frames.frames.LLMContextAssistantTurnFrame",
            "pipecat.frames.frames.TTSAudioRawFrame",
            "pipecat.frames.frames.InterruptionFrame",
            "pipecat.frames.frames.UserStartedSpeakingFrame",
            "pipecat.frames.frames.UserStoppedSpeakingFrame",
            "pipecat.frames.frames.VADUserStartedSpeakingFrame",
            "pipecat.frames.frames.VADUserStoppedSpeakingFrame",
            "pipecat.frames.frames.BotStartedSpeakingFrame",
            "pipecat.frames.frames.BotStoppedSpeakingFrame",
            "pipecat.frames.frames.UserIdleTimeoutUpdateFrame",
        ),
        "audioFrameFields": {
            "pipecat.frames.frames.OutputAudioRawFrame": (
                "audio",
                "sample_rate",
                "num_channels",
                "num_frames",
            ),
            "pipecat.frames.frames.TTSAudioRawFrame": ("context_id",),
        },
        "websocketEntrypoint": ("pipecat.transports.websocket.fastapi.FastAPIWebsocketTransport"),
        "vadParamsEntrypoint": ("pipecat.audio.vad.vad_analyzer.VADParams"),
        "vadEntrypoint": ("pipecat.audio.vad.silero.SileroVADAnalyzer"),
        "vadProcessorEntrypoint": ("pipecat.processors.audio.vad_processor.VADProcessor"),
        "sttEntrypoint": ("pipecat.services.openai.stt.OpenAIRealtimeSTTService"),
        "sttSettingsEntrypoint": ("pipecat.services.openai.stt.OpenAIRealtimeSTTService.Settings"),
        "ttsEntrypoint": ("pipecat.services.openai.tts.OpenAITTSService"),
        "ttsSettingsEntrypoint": ("pipecat.services.openai.tts.OpenAITTSService.Settings"),
        "llmEntrypoint": ("pipecat.services.openai.llm.OpenAILLMService"),
        "llmSettingsEntrypoint": ("pipecat.services.openai.llm.OpenAILLMService.Settings"),
        "openaiRealtimeLlmAdapter": {
            "provider": "openai",
            "serviceEntrypoint": ("pipecat.services.openai.realtime.llm.OpenAIRealtimeLLMService"),
            "settingsEntrypoint": (
                "pipecat.services.openai.realtime.llm.OpenAIRealtimeLLMService.Settings"
            ),
            "eventsEntrypoint": "pipecat.services.openai.realtime.events",
            "mode": "native_pipecat_speech_to_speech_service",
            "defaultTurnDetection": "semantic_vad",
            "defaultAudioSampleRate": 24000,
        },
        "openrouterLlmAdapter": {
            "provider": OPENROUTER_LLM_PROVIDER,
            "baseUrl": OPENROUTER_LLM_BASE_URL,
            "serviceEntrypoint": "pipecat.services.openrouter.llm.OpenRouterLLMService",
            "settingsEntrypoint": ("pipecat.services.openrouter.llm.OpenRouterLLMService.Settings"),
            "mode": "native_pipecat_llm_service",
        },
        "providerCatalog": pipecat_provider_catalog(probe_imports=False),
        "runtimeIntegratedProviderModules": pipecat_integrated_provider_modules(),
        "llmContextEntrypoints": (
            "pipecat.processors.aggregators.llm_context.LLMContext",
            "pipecat.processors.aggregators.llm_response_universal.LLMContextAggregatorPair",
            "pipecat.processors.aggregators.llm_response_universal.LLMUserAggregatorParams",
            "pipecat.processors.aggregators.llm_response_universal.LLMAssistantAggregatorParams",
        ),
        "turnDetectionEntrypoint": ("pipecat.turns.user_turn_processor.UserTurnProcessor"),
        "turnStrategyEntrypoints": (
            "pipecat.turns.user_turn_strategies.UserTurnStrategies",
            "pipecat.turns.user_turn_strategies.ExternalUserTurnStrategies",
            "pipecat.turns.user_turn_strategies.FilterIncompleteUserTurnStrategies",
            "pipecat.turns.user_turn_completion_mixin.UserTurnCompletionConfig",
        ),
        "talkwiseResponsibilities": (
            "optional import and Pipecat symbol capability detection",
            "pipeline factory configuration",
            "RealtimeAudioChunk to InputAudioRawFrame adaptation",
            "TrainingVoiceContext to LLMContext seed adaptation",
            "Pipecat runtime to provider-neutral readiness adaptation",
            "interim transcript frame mirroring",
            "final transcript frame mirroring",
            "TTSAudioRawFrame to provider-neutral audio.output event mirroring",
            "Pipecat turn/interruption/silence frames to TalkWise realtime event mirroring",
        ),
    }


__all__ = [
    "PipecatCapability",
    "PipecatPipelineHandle",
    "PipecatRealtimePipelineError",
    "PipecatRealtimePipelineAdapter",
    "PipecatRuntime",
    "build_pipecat_pipeline_handle",
    "build_pipecat_llm_processors",
    "build_pipecat_speech_to_speech_processors",
    "build_pipecat_voice_processors",
    "create_pipecat_realtime_pipeline",
    "create_talkwise_event_processor",
    "get_pipecat_capability",
    "import_pipecat_runtime",
    "is_pipecat_available",
    "pipecat_pipeline_capability",
    "pipecat_realtime_capability_response",
    "pipecat_realtime_profile_contracts",
    "pipecat_realtime_readiness",
    "pipecat_realtime_smoke_contract",
    "pipecat_provider_catalog",
    "pipecat_provider_catalog_summary",
    "pipecat_source_snapshot",
    "validate_pipecat_voice_config",
]
