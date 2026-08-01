"""Training Studio API routes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import importlib.util
import json
import logging
import mimetypes
import os
import re
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import urlencode, urlsplit

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies import (
    CurrentUser,
    enforce_ai_rate_limit,
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_conversation_service,
    get_current_user,
    get_file_asset_service,
    get_growth_service,
    get_persona_editor_service,
    get_stakeholder_llm_client,
    require_system_roles,
    training_scope_for,
)
from api.conversation_scope import owned_metadata_scope_for_current_user
from application.dto import ForkConversationDTO, MessageDTO_Agent
from application.ports.capabilities import build_text_runtime_capability_registry
from application.ports.llm import (
    LLMEndpointMetadata,
    LLMModelMetadata,
    LLMPort,
    LLMProviderMetadata,
    build_llm_registry_artifacts,
    build_llm_provider_registry,
)
from application.ports.realtime import (
    OPENAI_REALTIME_API_KEY_ENV_KEYS,
    REALTIME_RUNTIME_PIPECAT,
    REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    PersistedRealtimeTranscript,
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
    RealtimeReadinessIssue,
    RealtimeSessionBinding,
    build_realtime_readiness,
    classify_realtime_pipeline_start_error_message,
    is_sensitive_realtime_metadata_key,
    normalize_realtime_runtime,
    redact_realtime_secret_text,
    realtime_runtime_for_provider,
    sanitize_realtime_public_value,
)
from application.services.stakeholder.analysis_service import AnalysisReaderService, AnalysisService
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.dto import CreateChatRoomDTO, CreatePersonaDTO, MessageDTO
from application.services.stakeholder.persona_editor_service import PersonaEditorService
from application.services.stakeholder.room_access_policy import (
    StakeholderRoomAccessScope,
    legacy_training_session_room_scope,
)
from application.services.stakeholder.sse import room_event_bus
from application.services.conversation_service import ConversationApplicationService
from application.services.training_studio.catalog_service import (
    ScenarioTrainingDimensionWeightDTO,
    ScenarioTrainingPersonaDTO,
    ScenarioTrainingTemplateDTO,
    TrainingCatalogService,
    TrainingTaskConfigDTO,
)
from application.services.training_studio.live_guidance_llm_adapter import LiveGuidanceLLMAdapter
from application.services.training_studio.live_guidance_service import (
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)
from application.services.training_studio.guidance_persistence_service import (
    append_selected_path_guidance,
    guidance_persistence_failure,
    read_selected_path_guidance_history,
)
from application.services.training_studio.realtime_pipeline import (
    FINAL_TRANSCRIPT_EVENT_TYPES,
    RealtimeTranscriptPersistenceSink,
    build_realtime_transcript,
)
from application.services.training_studio.realtime_pipeline_runner import (
    REALTIME_PROVIDER_ERROR_TAXONOMY,
    RealtimePipelineSessionRunner,
)
from application.services.training_studio.realtime_session import (
    RealtimeEvent,
    RealtimeSession,
    RealtimeSessionStateError,
)
from application.services.training_studio.scenario_config_service import (
    JsonFileScenarioConfigStore,
    ScenarioConfigStateDTO,
    TrainingScenarioConfigService,
)
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingCompetencyRadarDTO,
    TrainingSessionDTO,
    TrainingSessionService,
)
from application.services.training_studio.material_review_llm_adapter import (
    MaterialReviewLLMAdapter,
)
from application.services.training_studio.material_review_service import (
    MaterialReviewReplayContext,
    MaterialReviewReportContext,
    TrainingMaterialReviewService,
    normalize_material_review_ids,
)
from application.services.training_studio.message_tree_completion_service import (
    MessageTreeCompletionConflict,
    MessageTreeReportGenerationError,
    MessageTreeTrainingCompletionService,
    message_tree_analysis_room_id,
    message_tree_completion_report_metadata,
)
from application.services.training_studio.training_material_tool_service import (
    TrainingMaterialToolConsumerService,
)
from application.services.training_studio.training_core import (
    ConversationRef,
    StartedTrainingSession,
    TrainingCoreOrchestrator,
    training_core_metadata_for_session,
)
from application.services.file_asset_service import FileAssetApplicationService
from core.config import LLMSettings, VoiceSettings, settings
from core.response import success_response
from domain.common.exceptions import (
    BusinessException,
    DomainValidationException,
    FileAssetNotFoundException,
)
from domain.conversation.repository import OwnedMetadataScope
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import Message
from domain.training_studio.catalog import ScenarioCategory
from domain.training_studio.session import TrainingSessionMode, TrainingSessionStatus
from domain.training_studio.session_repository import (
    TrainingSessionAccessScope,
    training_session_matches_access_scope,
)
from domain.training_studio.storybank import JsonFileStoryBankStore, StoryBankService
from infrastructure.adapters.training_conversation import ConversationTrainingConversationAdapter
from infrastructure.external.pipecat.realtime_pipeline import (
    pipecat_realtime_capability_response as build_pipecat_realtime_capability_response,
    pipecat_realtime_profile_contracts,
    pipecat_realtime_smoke_contract,
)
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

router = APIRouter(prefix="/training-studio", tags=["Training Studio"])
logger = logging.getLogger(__name__)
_TRAINING_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "training_studio"
_storybank_service = StoryBankService(JsonFileStoryBankStore(_TRAINING_DATA_DIR / "storybank.json"))
_training_scenario_config_service = TrainingScenarioConfigService(
    JsonFileScenarioConfigStore(_TRAINING_DATA_DIR / "scenario_config.json")
)
_PIPECAT_REALTIME_REQUIRED_FEATURES = {
    "stt": "openai",
    "tts": "openai",
    "llm": "openai",
    "vad": "silero",
    "turnDetection": "pipecat",
}
_PIPECAT_REALTIME_PROVIDER_ALIASES = {
    "pipecat",
    "pipecat_pipeline",
    "openai",
    "openai.realtime",
    "openai_realtime",
    "openai_webrtc",
}
_VOLCENGINE_DOUBAO_REALTIME_PROVIDER = "volcengine.doubao_realtime"
_VOLCENGINE_DOUBAO_REALTIME_PROVIDER_ALIASES = {
    _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
    "volcengine_doubao_realtime",
    "doubao_realtime",
    "doubao.realtime",
}
_VOLCENGINE_DOUBAO_REALTIME_PLACEHOLDER_VOICES = {
    "marin",
    "your-voice",
    "your-doubao-voice",
    "your-volcengine-voice",
    "your-volcengine-realtime-voice",
}
_DEFAULT_VOLCENGINE_DOUBAO_REALTIME_VOICE = "zh_female_vv_uranus_bigtts"
_VOLCENGINE_DOUBAO_REALTIME_REQUIRED_FEATURES = {
    "stt": "volcengine.doubao_realtime",
    "tts": "volcengine.doubao_realtime",
    "llm": "volcengine.doubao_realtime",
    "turnDetection": "volcengine.doubao_realtime",
}
_PIPECAT_REALTIME_PROFILE_CASCADE = "cascade"
_PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH = "speech_to_speech"
_PIPECAT_REALTIME_PROFILE_ALIASES = {
    "cascade": _PIPECAT_REALTIME_PROFILE_CASCADE,
    "cascaded": _PIPECAT_REALTIME_PROFILE_CASCADE,
    "chain": _PIPECAT_REALTIME_PROFILE_CASCADE,
    "near_realtime": _PIPECAT_REALTIME_PROFILE_CASCADE,
    "stt_llm_tts": _PIPECAT_REALTIME_PROFILE_CASCADE,
    "speech_to_speech": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "speech2speech": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "speechtospeech": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "true_realtime": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "realtime_llm": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "openai_realtime": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    "openai_speech_to_speech": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
}
_OPENAI_REALTIME_API_KEY_ENV_KEYS = OPENAI_REALTIME_API_KEY_ENV_KEYS
_CLIENT_REALTIME_EVENT_TYPES = {
    "realtime.start_requested",
    "realtime.ws_connected",
    "realtime.ws_error",
    "realtime.configure_failed",
    "realtime.start_failed",
    "realtime.server_error",
    "realtime.closed",
    "mic.unavailable",
    "mic.permission_denied",
    "mic.capture_started",
    "audio.input_send_failed",
    "audio.output_received",
    "audio.output_played",
    "audio.output_playback_failed",
    "transcript.persisted",
}
_CLIENT_REALTIME_EVENT_SEVERITIES = {"debug", "info", "warning", "error"}
_CLIENT_EVENT_PAYLOAD_OMIT_KEYS = {
    "audio",
    "audiodata",
    "buffer",
    "blob",
    "content",
    "data",
    "pcm",
    "raw",
    "samples",
    "text",
    "transcript",
    "utterance",
}
_CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS = 512
_CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS = 20
_CLIENT_EVENT_PAYLOAD_MAX_DEPTH = 5


def _pipecat_realtime_profile_contract(
    profile: str,
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    contracts = pipecat_realtime_profile_contracts()
    selected = contracts.get(profile) or contracts[_PIPECAT_REALTIME_PROFILE_CASCADE]
    contract = dict(selected)
    for key in (
        "inputAudio",
        "outputAudio",
        "services",
        "turnDetection",
        "talkwiseIntegration",
        "readinessFeatures",
        "browserE2E",
    ):
        value = selected.get(key)
        if isinstance(value, Mapping):
            contract[key] = dict(value)
    browser_e2e = contract.get("browserE2E")
    if isinstance(browser_e2e, dict) and isinstance(browser_e2e.get("requiredSignals"), list):
        browser_e2e["requiredSignals"] = list(browser_e2e["requiredSignals"])
    input_audio = contract.get("inputAudio")
    if input_sample_rate is not None and isinstance(input_audio, dict):
        input_audio["sampleRate"] = input_sample_rate
    return contract


def _pipecat_realtime_audio_contract(
    profile: str,
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    contract = _pipecat_realtime_profile_contract(
        profile,
        input_sample_rate=input_sample_rate,
    )
    return {
        "input": contract.get("inputAudio", {}),
        "output": contract.get("outputAudio", {}),
        "transport": "websocket.binary_frames",
    }


def _merge_pipecat_realtime_profile_contracts(
    profiles: object,
) -> dict[str, object]:
    payload = dict(profiles) if isinstance(profiles, Mapping) else {}
    payload.setdefault("default", _PIPECAT_REALTIME_PROFILE_CASCADE)
    payload.setdefault(
        "supported",
        [
            _PIPECAT_REALTIME_PROFILE_CASCADE,
            _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
        ],
    )
    for profile in (
        _PIPECAT_REALTIME_PROFILE_CASCADE,
        _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
    ):
        current = payload.get(profile)
        item = dict(current) if isinstance(current, Mapping) else {}
        contract = _pipecat_realtime_profile_contract(profile)
        item.setdefault("contract", contract)
        item.setdefault("latencyProfile", contract.get("latencyProfile"))
        item.setdefault("costProfile", contract.get("costProfile"))
        item.setdefault("audioContract", _pipecat_realtime_audio_contract(profile))
        item.setdefault(
            "browserE2E",
            contract.get("browserE2E", {}),
        )
        payload[profile] = item
    return payload


_training_session_service = TrainingSessionService(uow_factory=SQLAlchemyUnitOfWork)
_live_guidance_service = TrainingLiveGuidanceService()
_live_guidance_llm_client: LLMPort | None = None
_live_guidance_llm_service: TrainingLiveGuidanceService | None = None
_VIDEO_ANSWER_DIR = _TRAINING_DATA_DIR / "video_answers"
_VIDEO_ANSWER_MARKER = "[video-answer]"
_VIDEO_MAX_BYTES = 100 * 1024 * 1024
_VIDEO_EXTENSIONS = {
    "video/webm": ".webm",
    "video/mp4": ".mp4",
    "video/ogg": ".ogv",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}
_TRAINING_GUIDANCE_MESSAGE_SOURCE = "training_live_guidance"
_TRAINING_GUIDANCE_SELECTED_PATH_LIMIT = 200
_REALTIME_CONTEXT_RECENT_TURN_LIMIT = 8
_TRAINING_GUIDANCE_SENDER_ID = "training_coach"
_REALTIME_LIFECYCLE_CONTRACT_EVENTS = (
    "status.changed",
    "session.configured",
    "session.closed",
    "error",
)
_ENV_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_LLM_PROVIDERS = {
    "anthropic",
    "aws",
    "azure",
    "cerebras",
    "deepseek",
    "flowguide",
    "google",
    "groq",
    "mistral",
    "ollama",
    "openai",
    "openrouter",
    "perplexity",
    "qwen",
    "together",
    "volcengine",
    "xai",
}
_VOICE_TTS_PROVIDERS = {
    "asyncai",
    "aws",
    "azure",
    "cartesia",
    "deepgram",
    "elevenlabs",
    "fish",
    "google",
    "groq",
    "hume",
    "inworld",
    "kokoro",
    "lmnt",
    "minimax",
    "mistral",
    "openai",
    "openrouter",
    "piper",
    "resembleai",
    "rime",
    "soniox",
    "speechmatics",
    "together",
    "volcengine",
    "xai",
}
_VOICE_STT_PROVIDERS = {
    "assemblyai",
    "aws",
    "azure",
    "cartesia",
    "deepgram",
    "elevenlabs",
    "google",
    "groq",
    "minimax",
    "mistral",
    "openai",
    "soniox",
    "speechmatics",
    "volcengine",
    "whisper",
    "xai",
}
_REALTIME_PROVIDERS = {
    "aws.nova_sonic",
    "azure.realtime",
    "google.gemini_live",
    "google.gemini_live.vertex",
    "grok.realtime",
    "inworld.realtime",
    "openai",
    "openai.realtime",
    "openai_realtime",
    "ultravox.realtime",
    "volcengine.doubao_realtime",
    "xai.realtime",
}
_OPENROUTER_LLM_PROVIDER = "openrouter"
_OPENROUTER_LLM_PROVIDER_ALIASES = {
    "openrouter",
    "open_router",
    "openrouter_ai",
    "openrouter_compatible",
    "open_router_compatible",
}
_TEXT_MESSAGE_TREE_RUNTIME = "conversation_message_tree"
_TEXT_MESSAGE_TREE_PROVIDER = ConversationTrainingConversationAdapter.provider
_TEXT_MESSAGE_TREE_OPT_IN_VALUES = {
    _TEXT_MESSAGE_TREE_RUNTIME,
    _TEXT_MESSAGE_TREE_PROVIDER,
    "message_tree",
    "conversation_tree",
}


class VoicePreferenceConfigDTO(BaseModel):
    llm_provider: str
    llm_base_url: str | None = None
    llm_default_model: str
    llm_wire_api: str
    llm_api_key_configured: bool
    llm_api_key_preview: str | None = None
    tts_provider: str
    tts_base_url: str | None = None
    tts_model: str
    tts_api_key_configured: bool
    tts_api_key_preview: str | None = None
    tts_runtime_available: bool
    tts_runtime_status: str
    tts_runtime_message: str | None = None
    stt_provider: str
    stt_base_url: str | None = None
    stt_model: str
    stt_api_key_configured: bool
    stt_api_key_preview: str | None = None
    stt_api_key_source: str
    stt_use_tts_api_key: bool
    realtime_api_key_configured: bool
    realtime_effective_api_key_configured: bool
    realtime_api_key_preview: str | None = None
    realtime_api_key_source: str
    realtime_provider: str
    realtime_base_url: str | None = None
    realtime_model: str
    realtime_voice: str
    realtime_transcription_model: str | None = None
    updated_at: str


class VoicePreferenceUpdateDTO(BaseModel):
    llm_provider: str | None = None
    llm_base_url: str | None = None
    llm_default_model: str | None = None
    llm_wire_api: str | None = None
    llm_api_key: str | None = None
    clear_llm_api_key: bool = False
    tts_provider: str | None = None
    tts_base_url: str | None = None
    tts_model: str | None = None
    tts_api_key: str | None = None
    clear_tts_api_key: bool = False
    stt_provider: str | None = None
    stt_base_url: str | None = None
    stt_model: str | None = None
    stt_api_key: str | None = None
    clear_stt_api_key: bool = False
    stt_use_tts_api_key: bool = True
    realtime_api_key: str | None = None
    clear_realtime_api_key: bool = False
    realtime_provider: str | None = None
    realtime_base_url: str | None = None
    realtime_model: str | None = None
    realtime_voice: str | None = None
    realtime_transcription_model: str | None = None


def _openai_realtime_api_key() -> str | None:
    realtime_provider = _normalized_realtime_llm_provider(
        getattr(settings, "REALTIME_PROVIDER", None)
    )
    generic_realtime_key = (
        settings.REALTIME_API_KEY
        if realtime_provider in {"openai", "openai_realtime", "openai.realtime"}
        else None
    )
    return (
        settings.REALTIME_OPENAI_API_KEY
        or generic_realtime_key
        or settings.llm.api_key
        or settings.OPENAI_API_KEY
    )


def _settings_env_file_path() -> Path:
    env_file = settings.model_config.get("env_file")
    if isinstance(env_file, (list, tuple)):
        env_file = env_file[0] if env_file else ".env"
    return Path(env_file or ".env").resolve()


def _clean_config_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise HTTPException(
            status_code=400, detail="Configuration values cannot contain line breaks"
        )
    return text or None


def _clean_optional_config_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise HTTPException(
            status_code=400, detail="Configuration values cannot contain line breaks"
        )
    return text


def _required_config_text(value: str | None, fallback: str | None, field_name: str) -> str:
    text = _clean_config_text(value) or _clean_config_text(fallback)
    if not text:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return text


def _normalized_provider(
    value: str | None,
    fallback: str,
    *,
    allowed: set[str],
    field_name: str,
) -> str:
    provider = (_clean_config_text(value) or fallback).lower().replace("-", "_").replace(" ", "_")
    if provider not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be one of: {allowed_values}",
        )
    return provider


def _secret_preview(secret: str | None) -> str | None:
    if not secret:
        return None
    return f"***{secret[-4:]}" if len(secret) > 4 else "***"


def _parse_env_value(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def _read_env_file_values(path: Path | None = None) -> dict[str, str]:
    env_path = path or _settings_env_file_path()
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if key:
            values[key] = _parse_env_value(value)
    return values


def _explicit_config_value(key: str, env_values: dict[str, str]) -> str | None:
    if key in os.environ:
        return os.environ[key] or None
    return env_values.get(key) or None


def _format_env_value(value: str | None) -> str:
    if not value:
        return ""
    if "\n" in value or "\r" in value:
        raise HTTPException(
            status_code=400, detail="Configuration values cannot contain line breaks"
        )
    if any(ch.isspace() for ch in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_env_file_values(updates: dict[str, str | None]) -> None:
    env_path = _settings_env_file_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = (
        env_path.read_text(encoding="utf-8").splitlines(keepends=True) if env_path.exists() else []
    )
    pending = dict(updates)

    for index, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        match = _ENV_ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key = match.group(1)
        if key in pending:
            lines[index] = f"{key}={_format_env_value(pending.pop(key))}\n"

    if pending:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] = f"{lines[-1]}\n"
        for key, value in pending.items():
            lines.append(f"{key}={_format_env_value(value)}\n")

    env_path.write_text("".join(lines), encoding="utf-8")
    for key, value in updates.items():
        os.environ[key] = value or ""


def _voice_config_response() -> VoicePreferenceConfigDTO:
    env_values = _read_env_file_values()
    llm_key = settings.llm.api_key
    explicit_tts_key = settings.voice.tts_api_key
    tts_key = _effective_voice_tts_key()
    tts_runtime_available, tts_runtime_status, tts_runtime_message = _voice_tts_runtime_state(
        tts_key
    )
    stt_key = settings.voice.stt_api_key
    stt_can_reuse_shared_key = _voice_stt_provider_can_use_shared_key(settings.voice.stt_provider)
    selected_realtime_provider = _normalized_realtime_llm_provider(
        getattr(settings, "REALTIME_PROVIDER", None) or "openai"
    )
    public_realtime_provider = (
        "openai"
        if selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
        else selected_realtime_provider
    )
    selected_realtime_key = (
        settings.REALTIME_OPENAI_API_KEY
        if selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
        else settings.REALTIME_API_KEY
    )
    effective_realtime_key = _openai_realtime_api_key()

    explicit_stt_key = _explicit_config_value("VOICE__STT_API_KEY", env_values)
    if explicit_stt_key:
        stt_key = explicit_stt_key
        stt_key_source = "stt"
    elif stt_can_reuse_shared_key and explicit_tts_key and stt_key == explicit_tts_key:
        stt_key_source = "tts"
    elif stt_can_reuse_shared_key and settings.llm.api_key and stt_key == settings.llm.api_key:
        stt_key_source = "llm"
    elif stt_key:
        stt_key_source = "stt"
    elif stt_can_reuse_shared_key and explicit_tts_key:
        stt_key = explicit_tts_key
        stt_key_source = "tts"
    elif stt_can_reuse_shared_key and settings.llm.api_key:
        stt_key = settings.llm.api_key
        stt_key_source = "llm"
    else:
        stt_key = None
        stt_key_source = "missing"

    explicit_realtime_key = _explicit_config_value(
        (
            "REALTIME_OPENAI_API_KEY"
            if selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
            else "REALTIME_API_KEY"
        ),
        env_values,
    )
    if explicit_realtime_key or selected_realtime_key:
        realtime_key_source = "realtime"
    elif (
        selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
        and settings.llm.api_key
    ):
        realtime_key_source = "llm"
    else:
        realtime_key_source = "missing"

    return VoicePreferenceConfigDTO(
        llm_provider=settings.llm.provider,
        llm_base_url=settings.llm.base_url,
        llm_default_model=settings.llm.default_model,
        llm_wire_api=settings.llm.wire_api,
        llm_api_key_configured=bool(llm_key),
        llm_api_key_preview=_secret_preview(llm_key),
        tts_provider=settings.voice.tts_provider,
        tts_base_url=settings.voice.tts_base_url,
        tts_model=settings.voice.tts_model,
        tts_api_key_configured=bool(tts_key),
        tts_api_key_preview=_secret_preview(tts_key),
        tts_runtime_available=tts_runtime_available,
        tts_runtime_status=tts_runtime_status,
        tts_runtime_message=tts_runtime_message,
        stt_provider=settings.voice.stt_provider,
        stt_base_url=settings.voice.stt_base_url,
        stt_model=settings.voice.stt_model,
        stt_api_key_configured=bool(stt_key),
        stt_api_key_preview=_secret_preview(stt_key),
        stt_api_key_source=stt_key_source,
        stt_use_tts_api_key=stt_key_source == "tts",
        realtime_api_key_configured=bool(selected_realtime_key),
        realtime_effective_api_key_configured=(
            bool(effective_realtime_key)
            if selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
            else bool(selected_realtime_key)
        ),
        realtime_api_key_preview=_secret_preview(
            effective_realtime_key
            if selected_realtime_provider in {"openai", "openai.realtime", "openai_realtime"}
            else selected_realtime_key
        ),
        realtime_api_key_source=realtime_key_source,
        realtime_provider=public_realtime_provider,
        realtime_base_url=settings.REALTIME_BASE_URL,
        realtime_model=settings.REALTIME_OPENAI_MODEL,
        realtime_voice=settings.REALTIME_OPENAI_VOICE,
        realtime_transcription_model=settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        updated_at=datetime.now(UTC).isoformat(),
    )


def _voice_tts_runtime_state(tts_key: str | None) -> tuple[bool, str, str | None]:
    from infrastructure.external.voice import get_tts_client

    if get_tts_client() is not None:
        return True, "ready", "TTS runtime client is initialized"
    if tts_key:
        return (
            False,
            "not_initialized",
            (
                "TTS credentials are configured, but the current backend process "
                "has no initialized TTS client. Save the voice settings or restart "
                "the backend, then check backend logs if this remains unavailable."
            ),
        )
    return (
        False,
        "missing_key",
        "TTS credentials are missing; configure a supported TTS provider before using voice playback.",
    )


def _completion_report_failure_metadata(exc: Exception) -> dict[str, object]:
    raw_message = getattr(exc, "message", None) or str(exc)
    message = redact_realtime_secret_text(str(raw_message or "").strip())
    if len(message) > 500:
        message = f"{message[:500].rstrip()}..."
    return {
        "status": "failed",
        "phase": "generate_report",
        "errorType": type(exc).__name__,
        "message": message or "Report generation failed",
        "completedWithoutReport": True,
        "recordedAt": datetime.now(UTC).isoformat(),
    }


def _completion_report_pending_metadata() -> dict[str, object]:
    return {
        "status": "pending",
        "phase": "generate_report",
        "generation": "background",
        "completedWithoutReport": False,
        "requestedAt": datetime.now(UTC).isoformat(),
    }


def _completion_report_ready_metadata(
    report_id: int | str,
    *,
    generation: str = "background",
) -> dict[str, object]:
    return {
        "status": "ready",
        "phase": "generate_report",
        "generation": generation,
        "reportId": str(report_id),
        "completedWithoutReport": False,
        "recordedAt": datetime.now(UTC).isoformat(),
    }


def _effective_voice_tts_key() -> str | None:
    if settings.voice.tts_api_key:
        return settings.voice.tts_api_key
    if (
        settings.voice.tts_provider == _OPENROUTER_LLM_PROVIDER
        and settings.llm.api_key
        and (
            _normalized_realtime_llm_provider(settings.llm.provider)
            in _OPENROUTER_LLM_PROVIDER_ALIASES
            or _is_openrouter_base_url(settings.llm.base_url)
        )
    ):
        return settings.llm.api_key
    return None


def _voice_stt_provider_can_use_shared_key(provider: str | None) -> bool:
    normalized = (provider or "").strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {
        "minimax",
        "openai",
        "whisper",
        "volcengine",
        "volc_engine",
        "doubao",
        "byteplus",
        "bytedance",
        "volcengine_doubao",
    }


def _settings_llm_provider_metadata() -> LLMProviderMetadata:
    llm_cfg = settings.llm
    default_model = LLMModelMetadata(
        name=llm_cfg.default_model,
        provider=llm_cfg.provider,
        endpoint=llm_cfg.base_url,
        is_default=True,
        max_output_tokens=llm_cfg.max_tokens,
    )
    endpoint = LLMEndpointMetadata(
        provider=llm_cfg.provider,
        endpoint=llm_cfg.base_url,
        wire_api=llm_cfg.wire_api,
        default_model=llm_cfg.default_model,
        models=[default_model],
    )
    return LLMProviderMetadata(
        provider=llm_cfg.provider,
        default_model=llm_cfg.default_model,
        endpoint=llm_cfg.base_url,
        wire_api=llm_cfg.wire_api,
        max_retries=llm_cfg.max_retries,
        models=[default_model],
        endpoints=[endpoint],
    )


def _llm_registry_response(
    llm: LLMPort | None,
    *,
    agent_configs: object | None = None,
    tool_configs: object | None = None,
    mcp_servers: object | None = None,
) -> dict[str, object]:
    source = "active_client" if llm is not None else "settings"
    provider_metadata = (
        llm.provider_metadata if llm is not None else _settings_llm_provider_metadata()
    )
    api_key_configured = bool(
        llm is not None or settings.llm.api_key or settings.stakeholder.anthropic_api_key
    )
    registry = build_llm_provider_registry(
        [provider_metadata],
        provider="talkwise",
        default_model=provider_metadata.default_model or settings.llm.default_model,
        extra={
            "configured": api_key_configured,
            "client_configured": llm is not None,
            "api_key_configured": api_key_configured,
            "source": source,
        },
    )
    payload = registry.to_dict()
    payload.update(build_llm_registry_artifacts(registry))
    payload["capability_registry"] = build_text_runtime_capability_registry(
        registry,
        model_specs=payload["model_specs"],
        agent_configs=agent_configs,
        tool_configs=tool_configs,
        mcp_servers=mcp_servers,
    ).to_dict()
    return payload


async def _agent_config_inventory_for_user(
    service: ConversationApplicationService,
    current_user: CurrentUser,
) -> list[object]:
    scan_limit = max(1, int(settings.capability_inventory.agent_config_scan_limit))
    page_size = max(1, min(int(settings.MAX_PAGE_SIZE), scan_limit))
    metadata_scope = owned_metadata_scope_for_current_user(
        current_user,
    )
    items: list[object] = []
    skip = 0
    try:
        while len(items) < scan_limit:
            page_limit = min(page_size, scan_limit - len(items))
            page_items, total = await service.list_agent_configs(
                skip=skip,
                limit=page_limit,
                metadata_scope=metadata_scope,
            )
            if not page_items:
                break
            items.extend(page_items)
            skip += len(page_items)
            if skip >= total or len(page_items) < page_limit:
                break
    except Exception as exc:
        logger.warning("Failed to load agent config inventory for capability registry: %s", exc)
        return []
    return list(items)


async def _reload_voice_clients() -> None:
    from infrastructure.external.voice import (
        init_stt_client,
        init_tts_client,
        shutdown_stt_client,
        shutdown_tts_client,
    )

    await shutdown_stt_client()
    await shutdown_tts_client()
    await init_tts_client()
    await init_stt_client()


async def _reload_llm_client() -> None:
    from infrastructure.external.llm import init_llm_client, shutdown_llm_client

    await shutdown_llm_client()
    await init_llm_client()


def get_training_catalog_service() -> TrainingCatalogService:
    return TrainingCatalogService()


def get_training_scenario_config_service() -> TrainingScenarioConfigService:
    return _training_scenario_config_service


def _scenario_templates_from_config(
    config: ScenarioConfigStateDTO,
) -> list[ScenarioTrainingTemplateDTO]:
    return [
        ScenarioTrainingTemplateDTO(
            id=draft.id,
            title=draft.title,
            description=draft.description,
            customer_profile=draft.customer_profile,
            difficulty=draft.difficulty,
            category=draft.category,
            required=draft.required,
            status="not_started",
            opening_line=draft.opening_line,
            persona=ScenarioTrainingPersonaDTO(
                name=draft.persona.name,
                role=draft.persona.role,
                style=draft.persona.style,
            ),
            learner_role=draft.learner_role,
            framework=draft.framework,
            training_points=list(draft.training_points),
            dimension_weights=[
                ScenarioTrainingDimensionWeightDTO(
                    dimension_id=weight.dimension_id,
                    weight=weight.weight,
                )
                for weight in draft.dimension_weights
            ],
        )
        for draft in config.scenarios
        if draft.enabled
    ]


def get_storybank_service() -> StoryBankService:
    return _storybank_service


def get_training_session_service() -> TrainingSessionService:
    return _training_session_service


def get_live_guidance_service() -> TrainingLiveGuidanceService:
    llm = get_stakeholder_llm_client()
    if llm is None:
        return _live_guidance_service

    global _live_guidance_llm_client, _live_guidance_llm_service
    if _live_guidance_llm_service is None or llm is not _live_guidance_llm_client:
        _live_guidance_llm_client = llm
        _live_guidance_llm_service = TrainingLiveGuidanceService(
            async_llm_callback=LiveGuidanceLLMAdapter(llm)
        )
    return _live_guidance_llm_service


def get_training_runtime_uow_factory() -> Callable[..., AbstractUnitOfWork]:
    return SQLAlchemyUnitOfWork


def get_training_realtime_uow_factory() -> Callable[..., AbstractUnitOfWork]:
    return get_training_runtime_uow_factory()


RealtimePipelineFactory = Callable[[str], RealtimePipelineAdapter | None]


def get_training_realtime_pipeline_factory() -> RealtimePipelineFactory:
    def _factory(provider: str) -> RealtimePipelineAdapter | None:
        if _uses_pipecat_realtime(provider):
            try:
                pipecat_adapter = _load_pipecat_realtime_adapter()
                return pipecat_adapter.create_pipecat_realtime_pipeline()
            except Exception as exc:
                logger.warning(
                    "Pipecat realtime pipeline factory failed",
                    extra={
                        "realtime_error": {
                            "provider": provider,
                            "runtime": "realtime_voice",
                            "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
                            "phase": "pipeline_factory",
                            "code": "PIPECAT_PIPELINE_FACTORY_FAILED",
                            "message": str(exc),
                        }
                    },
                    exc_info=True,
                )
                return None
        if _uses_volcengine_doubao_realtime(provider):
            try:
                volcengine_adapter = _load_volcengine_doubao_realtime_adapter()
                return volcengine_adapter.create_volcengine_doubao_realtime_adapter(
                    api_key=settings.REALTIME_API_KEY,
                    base_url=settings.REALTIME_BASE_URL,
                    model=settings.REALTIME_OPENAI_MODEL,
                    voice=_realtime_voice_for_provider(provider),
                )
            except Exception as exc:
                logger.warning(
                    "Volcengine Doubao realtime pipeline factory failed",
                    extra={
                        "realtime_error": {
                            "provider": provider,
                            "runtime": "realtime_voice",
                            "realtimeRuntime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
                            "phase": "pipeline_factory",
                            "code": "VOLCENGINE_REALTIME_PIPELINE_FACTORY_FAILED",
                            "message": str(exc),
                        }
                    },
                    exc_info=True,
                )
                return None
        return None

    return _factory


class StoryBankRegisterDTO(BaseModel):
    answer_text: str = Field(..., min_length=20, max_length=20000)
    scenario_category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    tags: list[str] = Field(default_factory=list)


class TrainingRuntimePersonaDTO(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., min_length=1, max_length=200)
    style: str = Field(..., min_length=1, max_length=2000)
    scenario_context: str = Field(..., min_length=1, max_length=8000)
    training_points: list[str] = Field(default_factory=list, max_length=20)
    difficulty: str = Field(default="normal", pattern=r"^(easy|normal|hard)$")


class TrainingOpeningMessageDTO(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    sender_id: str | None = Field(default=None, min_length=1, max_length=100)
    metadata: dict[str, object] = Field(default_factory=dict)


class StartTrainingSessionDTO(BaseModel):
    room_id: int | str | None = None
    persona_ids: list[str] = Field(default_factory=list)
    room_name: str | None = Field(default=None, min_length=1, max_length=255)
    room_type: str = Field(default="battle_prep", pattern=r"^(private|group|battle_prep|defense)$")
    scenario_id: int | None = None
    runtime: str | None = Field(default=None, min_length=1, max_length=80)
    provider: str | None = Field(default=None, min_length=1, max_length=120)
    runtime_persona: TrainingRuntimePersonaDTO | None = None
    opening_message: TrainingOpeningMessageDTO | None = None


class CompleteTrainingSessionDTO(BaseModel):
    report_id: int | str | None = None
    score_id: int | str | None = None
    generate_report: bool = True
    report_generation: str = Field(default="sync", pattern=r"^(sync|background)$")
    selected_tail_message_id: str | None = Field(default=None, min_length=1, max_length=160)
    metadata: dict[str, object] = Field(default_factory=dict)


class FailTrainingSessionDTO(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class TrainingGuidanceTurnDTO(BaseModel):
    speaker: str
    text: str
    turn_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TrainingGuidanceRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_goal: str | None = None
    rubric: dict[str, object] = Field(default_factory=dict)
    recent_turns: list[TrainingGuidanceTurnDTO] = Field(default_factory=list)
    message_limit: int = Field(default=50, ge=1, le=200)
    selected_tail_message_id: str | None = Field(default=None, min_length=1, max_length=160)


class TrainingGuidanceEventDTO(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=80)
    severity: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=300)
    message: str = Field(..., min_length=1, max_length=2000)
    suggested_text: str | None = Field(default=None, max_length=2000)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = None


class PersistTrainingGuidanceEventsDTO(BaseModel):
    events: list[TrainingGuidanceEventDTO] = Field(..., min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=80)
    source: str | None = Field(default=None, max_length=80)
    window_size: int | None = Field(default=None, ge=0, le=500)
    total_turn_count: int | None = Field(default=None, ge=0, le=10000)
    trigger: dict[str, object] | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ClientRealtimeEventDTO(BaseModel):
    event_type: str = Field(..., alias="eventType", min_length=1, max_length=120)
    event_category: str | None = Field(default=None, alias="eventCategory", max_length=80)
    severity: str = Field(default="info", min_length=1, max_length=20)
    training_session_id: str | None = Field(default=None, alias="trainingSessionId", max_length=120)
    room_id: int | str | None = Field(default=None, alias="roomId")
    provider: str | None = Field(default="pipecat", max_length=80)
    realtime_profile: str | None = Field(default=None, alias="realtimeProfile", max_length=80)
    error_category: str | None = Field(default=None, alias="errorCategory", max_length=120)
    message: str | None = Field(default=None, max_length=1000)
    payload: dict[str, object] = Field(default_factory=dict)


class MaterialReviewRequestDTO(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=120)
    material_ids: list[int] = Field(default_factory=list, max_length=10)
    selected_material_ids: list[int] = Field(default_factory=list, max_length=10)


def _storybank_entry_to_dict(entry) -> dict:
    return entry.to_dict()


def _session_to_dict(session) -> dict:
    return TrainingSessionDTO.from_domain(session).model_dump(mode="json")


def _started_training_session_to_dict(started: StartedTrainingSession) -> dict:
    payload = _session_to_dict(started.session)
    payload["conversation"] = _conversation_ref_to_dict(started.conversation)
    return payload


def _conversation_ref_to_dict(conversation: ConversationRef) -> dict[str, object]:
    return {
        "provider": conversation.provider,
        "conversationId": conversation.conversation_id,
        "branchTailMessageId": conversation.branch_tail_message_id,
        "legacyRoomId": conversation.legacy_room_id,
        "metadata": dict(conversation.metadata),
    }


def _forked_training_conversation_to_dict(session, forked) -> dict[str, object]:
    return {
        "training_session": _session_to_dict(session),
        "conversation": forked.conversation.model_dump(mode="json"),
        "messages": [message.model_dump(mode="json") for message in forked.messages],
        "source_to_forked_id": dict(forked.source_to_forked_id),
    }


_TRAINING_RUNTIME_DIFFICULTY_RULES = {
    "easy": "Keep pressure moderate, ask one clear follow-up at a time, and help the learner build momentum.",
    "normal": "Challenge weak claims, ask for evidence, and keep the conversation realistic.",
    "hard": "Apply strong pressure, expose vague answers quickly, and require concrete tradeoffs or proof.",
}


def _required_runtime_persona_text(value: str, field_name: str) -> str:
    text = value.strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"runtime_persona.{field_name} cannot be blank")
    return text


def _training_runtime_persona_content(persona: TrainingRuntimePersonaDTO) -> str:
    style = _required_runtime_persona_text(persona.style, "style")
    scenario_context = _required_runtime_persona_text(
        persona.scenario_context,
        "scenario_context",
    )
    training_points = [point.strip() for point in persona.training_points if point.strip()]
    lines = [
        style,
        "",
        "Scenario context:",
        scenario_context,
        "",
        "Training points:",
    ]
    if training_points:
        lines.extend(f"- {point}" for point in training_points)
    else:
        lines.append("- Follow the scenario objective and push for observable learner behavior.")
    lines.extend(
        [
            "",
            "Training runtime rules:",
            "- Stay in the assigned counterpart persona; do not act as the learner's assistant.",
            "- Keep replies concise, natural, and grounded in the scenario.",
            "- Reveal constraints gradually and make the learner earn trust.",
            f"- Difficulty behavior: {_TRAINING_RUNTIME_DIFFICULTY_RULES[persona.difficulty]}",
        ]
    )
    return "\n".join(lines)


def _create_training_runtime_persona(
    persona: TrainingRuntimePersonaDTO,
    persona_editor: PersonaEditorService,
) -> str:
    name = _required_runtime_persona_text(persona.name, "name")
    role = _required_runtime_persona_text(persona.role, "role")
    content = _training_runtime_persona_content(persona)
    for _ in range(8):
        persona_id = f"ts-{uuid4().hex[:10]}"
        try:
            persona_editor.create_persona(
                CreatePersonaDTO(
                    id=persona_id,
                    name=name,
                    role=role,
                    avatar_color="#2563eb",
                    content=content,
                    temporary=True,
                )
            )
            return persona_id
        except FileExistsError:
            continue
    raise HTTPException(status_code=500, detail="Failed to allocate a training runtime persona")


async def _persist_training_opening_message(
    *,
    room_id: str,
    opening_message: TrainingOpeningMessageDTO | None,
    session_id: str,
    uow_factory: Callable[..., AbstractUnitOfWork],
) -> MessageDTO | None:
    if opening_message is None:
        return None
    try:
        numeric_room_id = int(str(room_id).strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Session room_id must be numeric to save opening message",
        ) from exc

    async with uow_factory() as uow:
        room = await uow.chat_room_repository.get_by_id(numeric_room_id)
        if room is None:
            raise HTTPException(status_code=404, detail=f"Chat room {numeric_room_id} not found")
        sender_id = (opening_message.sender_id or "").strip()
        if not sender_id:
            sender_id = room.persona_ids[0] if room.persona_ids else "training_customer"
        metadata = dict(opening_message.metadata)
        metadata.setdefault("source", "training_opening_message")
        metadata["eventKind"] = "scenario_opening"
        metadata["trainingSessionId"] = session_id
        saved = await uow.stakeholder_message_repository.create(
            Message(
                id=None,
                room_id=numeric_room_id,
                sender_type="persona",
                sender_id=sender_id,
                content=opening_message.content,
                metadata=metadata,
            )
        )
        await uow.chat_room_repository.update_last_message_at(
            numeric_room_id,
            saved.timestamp,
        )
        dto = MessageDTO.model_validate(saved)

    await room_event_bus.publish(numeric_room_id, "message", dto.model_dump(mode="json"))
    return dto


def _requests_message_tree_runtime(body: StartTrainingSessionDTO) -> bool:
    requested = [
        _coerce_optional_text(body.runtime),
        _coerce_optional_text(body.provider),
    ]
    return any(
        str(value).strip().lower() in _TEXT_MESSAGE_TREE_OPT_IN_VALUES
        for value in requested
        if value
    )


def _not_found_if_missing(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _training_session_access_scope_for_current_user(
    current_user: CurrentUser,
) -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id=current_user.user_id,
        team_id=current_user.team_id,
        include_team_scope=current_user.is_admin or current_user.is_leader,
    )


def _message_tree_conversation_id_for_session(session) -> int:
    room_id = str(getattr(session, "room_id", None) or "").strip()
    prefix = f"{ConversationTrainingConversationAdapter.provider}:"
    if not room_id.startswith(prefix):
        raise HTTPException(
            status_code=409,
            detail="Training session is not bound to the message-tree conversation runtime",
        )
    try:
        return int(room_id.removeprefix(prefix))
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail="Training session has an invalid message-tree conversation binding",
        ) from exc


def _guidance_runtime_contract(session) -> tuple[str, dict[str, bool]]:
    room_id = str(getattr(session, "room_id", None) or "").strip()
    if room_id.startswith(f"{ConversationTrainingConversationAdapter.provider}:"):
        return (
            "message_tree",
            {
                "refresh": True,
                "stream": False,
                "persistence": True,
                "history": True,
                "server_selected_path": True,
            },
        )
    if room_id:
        try:
            int(room_id)
        except ValueError:
            return (
                "unknown",
                {
                    "refresh": True,
                    "stream": False,
                    "persistence": False,
                    "history": False,
                    "server_selected_path": False,
                },
            )
        return (
            "legacy_room",
            {
                "refresh": True,
                "stream": True,
                "persistence": True,
                "history": False,
                "server_selected_path": False,
            },
        )
    return (
        "request",
        {
            "refresh": True,
            "stream": False,
            "persistence": False,
            "history": False,
            "server_selected_path": False,
        },
    )


def _training_fork_metadata(
    metadata: Mapping[str, object] | None,
    *,
    source_session_id: str,
    forked_session_id: str,
) -> dict[str, object]:
    source = dict(metadata or {})
    clean = {key: source[key] for key in ("fork_reason", "message_tree_status") if key in source}
    clean.update(
        {
            "trainingSessionId": forked_session_id,
            "forkedFromTrainingSessionId": source_session_id,
        }
    )
    return clean


def _stakeholder_room_scope_for_current_user(
    current_user: CurrentUser,
) -> StakeholderRoomAccessScope:
    """Create owned training rooms from the authenticated user, not client input."""

    team_id = (current_user.team_id or "").strip() or None
    return StakeholderRoomAccessScope(
        user_id=current_user.user_id,
        team_id=team_id,
        include_team_scope=current_user.is_admin or current_user.is_leader,
        allowed_team_ids=frozenset([team_id]) if team_id else frozenset(),
        # Administrative read access must not make a newly created room
        # ownerless. The session remains owned by the authenticated creator.
        unrestricted=False,
    )


def _session_access_denied(exc: PermissionError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc) or "Training session is outside scope")


async def _require_accessible_training_session(
    session_id: str,
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
):
    try:
        return await svc.get_session(
            session_id,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc


def _legacy_room_scope_for_accessible_training_session(
    session,
    current_user: CurrentUser,
    *,
    room_id: int,
    operation: str,
) -> StakeholderRoomAccessScope:
    """Name the legacy room escape hatch and bind it back to session ACL."""

    session_scope = _training_session_access_scope_for_current_user(current_user)
    if not training_session_matches_access_scope(session, session_scope):
        raise _session_access_denied(
            PermissionError("Training session is outside current user scope")
        )
    session_room_id = _stakeholder_room_id_for_training_session(session)
    if room_id != session_room_id:
        raise HTTPException(
            status_code=403,
            detail="room_id does not match the accessible training session",
        )
    return legacy_training_session_room_scope(
        training_session_id=getattr(session, "session_id", None),
        room_id=session_room_id,
        operation=operation,
    )


async def _require_report_id_for_training_session(
    report_id: str,
    *,
    session,
    reader_svc: AnalysisReaderService,
    current_user: CurrentUser,
) -> str:
    try:
        report_lookup_id = int(report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Training session report not found") from exc
    try:
        room_lookup_id = _stakeholder_room_id_for_training_session(session)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Training session report not found") from exc
    report = await reader_svc.get_report(
        report_lookup_id,
        room_id=room_lookup_id,
        access_scope=_legacy_room_scope_for_accessible_training_session(
            session,
            current_user,
            room_id=room_lookup_id,
            operation="explicit_report_lookup",
        ),
    )
    if report is None or str(report.room_id) != str(room_lookup_id):
        raise HTTPException(status_code=404, detail="Training session report not found")
    return str(report_lookup_id)


async def _generate_training_completion_report_background(
    *,
    session_id: str,
    room_id: int,
    session_access_scope: TrainingSessionAccessScope,
    room_access_scope: StakeholderRoomAccessScope,
    svc: TrainingSessionService,
    analysis_svc: AnalysisService,
    growth_svc,
) -> None:
    try:
        report = await analysis_svc.generate_report(
            room_id,
            access_scope=room_access_scope,
        )
    except (BusinessException, ValueError) as exc:
        logger.warning(
            "training_session_background_report_failed",
            extra={
                "session_id": session_id,
                "room_id": room_id,
                "error_type": type(exc).__name__,
            },
        )
        await _record_training_completion_report_failure(
            session_id=session_id,
            exc=exc,
            svc=svc,
            access_scope=session_access_scope,
        )
        return
    except Exception as exc:
        logger.exception(
            "training_session_background_report_failed",
            extra={"session_id": session_id, "room_id": room_id},
        )
        await _record_training_completion_report_failure(
            session_id=session_id,
            exc=exc,
            svc=svc,
            access_scope=session_access_scope,
        )
        return

    try:
        await svc.record_completion_report(
            session_id,
            report_id=str(report.id),
            metadata={"completionReport": _completion_report_ready_metadata(report.id)},
            access_scope=session_access_scope,
        )
    except Exception:
        logger.exception(
            "training_session_background_report_record_failed",
            extra={"session_id": session_id, "room_id": room_id, "report_id": report.id},
        )
        return

    try:
        await growth_svc.evaluate_competency(report.id)
    except Exception:
        logger.exception(
            "training_session_background_competency_eval_failed",
            extra={"session_id": session_id, "room_id": room_id, "report_id": report.id},
        )


async def _record_training_completion_report_failure(
    *,
    session_id: str,
    exc: Exception,
    svc: TrainingSessionService,
    access_scope: TrainingSessionAccessScope,
) -> None:
    try:
        await svc.record_completion_report(
            session_id,
            metadata={"completionReport": _completion_report_failure_metadata(exc)},
            access_scope=access_scope,
        )
    except Exception:
        logger.exception(
            "training_session_completion_report_failure_record_failed",
            extra={"session_id": session_id},
        )


def _stakeholder_room_id_for_training_session(session) -> int:
    room_id = getattr(session, "room_id", None)
    if room_id is None:
        raise ValueError("Training session room_id is missing")
    return int(room_id)


def _event_to_wire(event: RealtimeEvent) -> dict:
    return {
        "type": event.type.value,
        "sessionId": event.session_id,
        "status": event.status.value,
        "payload": event.payload,
        "createdAt": event.created_at.isoformat(),
    }


def _realtime_wire_event(
    event_type: str,
    session: RealtimeSession,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "type": event_type,
        "sessionId": session.session_id,
        "status": session.status.value,
        "payload": payload or {},
        "createdAt": datetime.now(UTC).isoformat(),
    }


def _exception_realtime_error_payload(
    exc: BaseException,
    *,
    provider: str,
    default_code: str,
    default_phase: str,
    binding: tuple[str, int] | None = None,
) -> dict[str, object]:
    structured = _structured_error_from_exception(exc)
    message = _coerce_optional_text(structured.get("message")) or str(exc)
    code = _coerce_optional_text(structured.get("code")) or default_code
    phase = _coerce_optional_text(structured.get("phase")) or default_phase

    if isinstance(exc, HTTPException):
        message = _coerce_optional_text(exc.detail) or message
        if (
            _uses_pipecat_realtime(provider)
            and exc.status_code == 503
            and "Pipecat realtime pipeline is not available" in message
        ):
            code = "PIPECAT_PIPELINE_UNAVAILABLE"
            phase = "pipeline_factory"
        elif (
            _uses_volcengine_doubao_realtime(provider)
            and exc.status_code == 503
            and "Volcengine Doubao realtime pipeline is not available" in message
        ):
            code = "VOLCENGINE_REALTIME_PIPELINE_UNAVAILABLE"
            phase = "pipeline_factory"
        elif exc.status_code == 400 and "Pipecat only" in message:
            code = "UNSUPPORTED_REALTIME_PROVIDER"
            phase = "provider"

    fallback = (
        classify_realtime_pipeline_start_error_message(message)
        if _uses_pipecat_realtime(provider)
        else {}
    )
    code = _coerce_optional_text(structured.get("code")) or fallback.get("code") or code
    phase = _coerce_optional_text(structured.get("phase")) or fallback.get("phase") or phase

    payload: dict[str, object] = {
        "message": message,
        "code": code,
        "provider": provider,
        "phase": phase,
        "runtime": "realtime_voice",
        "realtimeRuntime": normalize_realtime_runtime(
            structured.get("runtime"),
            provider=provider,
        ),
    }
    for key in (
        "errorCategory",
        "feature",
        "fatal",
        "missingEnv",
        "modules",
        "eventType",
        "processor",
        "retryable",
        "sourceCode",
        "metadata",
    ):
        value = structured.get(key) if key in structured else fallback.get(key)
        safe_value = _json_safe_realtime_value(value)
        if safe_value is not None:
            payload[key] = safe_value
    if binding is not None:
        payload["trainingSessionId"] = binding[0]
        payload["roomId"] = binding[1]
    return payload


def _structured_error_from_exception(exc: BaseException) -> dict[str, object]:
    for method_name in ("to_realtime_error", "to_dict"):
        method = getattr(exc, method_name, None)
        if callable(method):
            with suppress(Exception):
                value = method()
                if isinstance(value, Mapping):
                    return {str(key): item for key, item in value.items()}

    data: dict[str, object] = {}
    for attr_name, output_key in {
        "code": "code",
        "phase": "phase",
        "provider": "provider",
        "feature": "feature",
        "missing_env": "missingEnv",
        "missing_modules": "modules",
        "event_type": "eventType",
        "source_code": "sourceCode",
        "metadata": "metadata",
    }.items():
        if hasattr(exc, attr_name):
            value = getattr(exc, attr_name)
            if value is not None:
                data[output_key] = value
    return data


def _realtime_session_fail_event(
    session: RealtimeSession,
    payload: dict[str, object],
) -> RealtimeEvent:
    message = str(payload.get("message") or "Realtime session failed")
    code = str(payload.get("code") or "SESSION_ERROR")
    event = session.fail(message, code)
    for key, value in payload.items():
        if key in {"message", "code"}:
            continue
        safe_value = _json_safe_realtime_value(value)
        if safe_value is not None:
            event.payload[key] = safe_value
    return event


def _task_goal_for_guidance(session) -> str:
    config = session.task_config
    focus = ", ".join(config.tech_stack[:3]) if config.tech_stack else config.category.value
    return (
        f"{config.level} {config.role} {config.category.value} practice "
        f"using {config.framework.value}; focus: {focus}"
    )


def _rubric_for_guidance(session) -> dict[str, object]:
    return {
        key.value if hasattr(key, "value") else str(key): value
        for key, value in session.task_config.rubric_weights.items()
    }


def _speaker_from_sender_type(sender_type: str) -> TranscriptSpeaker:
    if sender_type == "persona":
        return TranscriptSpeaker.COUNTERPART
    if sender_type == "system":
        return TranscriptSpeaker.SYSTEM
    return TranscriptSpeaker.USER


def _split_video_answer_content(content: str) -> tuple[str, dict[str, object] | None]:
    if _VIDEO_ANSWER_MARKER not in content:
        return content, None

    marker_index = content.index(_VIDEO_ANSWER_MARKER)
    caption = content[:marker_index].strip()
    raw = content[marker_index + len(_VIDEO_ANSWER_MARKER) :].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return caption or content, None
    if not isinstance(parsed, dict):
        return caption or content, None
    return caption or str(parsed.get("title") or "Video answer submitted"), parsed


def _message_to_guidance_turn(message: MessageDTO) -> TranscriptTurn:
    text, video_answer = _split_video_answer_content(message.content)
    metadata: dict[str, object] = dict(message.metadata or {})
    metadata.update(
        {
            "message_id": message.id,
            "room_id": message.room_id,
            "sender_type": message.sender_type,
            "sender_id": message.sender_id,
            "emotion_score": message.emotion_score,
            "emotion_label": message.emotion_label,
        }
    )
    if video_answer is not None:
        metadata.update(
            {
                "source": "video_answer",
                "videoUrl": video_answer.get("url"),
                "mimeType": video_answer.get("mimeType"),
                "durationMs": video_answer.get("durationMs"),
                "recordedAt": video_answer.get("recordedAt"),
                "trainingEvent": video_answer.get("trainingEvent"),
            }
        )
    return TranscriptTurn(
        speaker=_speaker_from_sender_type(message.sender_type),
        text=text,
        turn_id=str(message.id),
        created_at=message.timestamp,
        metadata=metadata,
    )


def _request_turn_to_guidance_turn(turn: TrainingGuidanceTurnDTO) -> TranscriptTurn:
    return TranscriptTurn(
        speaker=turn.speaker,
        text=turn.text,
        turn_id=turn.turn_id,
        metadata=dict(turn.metadata),
    )


def _guidance_turn_to_realtime_context_turn(turn: TranscriptTurn) -> dict[str, object]:
    context_turn: dict[str, object] = {
        "speaker": turn.normalized_speaker,
        "text": turn.text,
    }
    if turn.turn_id is not None:
        context_turn["turn_id"] = turn.turn_id
    if turn.created_at is not None:
        context_turn["created_at"] = turn.created_at.isoformat()
    if turn.metadata:
        context_turn["metadata"] = dict(turn.metadata)
    return context_turn


def _is_training_guidance_message(message: MessageDTO) -> bool:
    return (message.metadata or {}).get("source") == _TRAINING_GUIDANCE_MESSAGE_SOURCE


def _training_guidance_event_content(event: TrainingGuidanceEventDTO) -> str:
    parts = [event.title.strip(), event.message.strip()]
    if event.suggested_text and event.suggested_text.strip():
        parts.append(event.suggested_text.strip())
    return "\n\n".join(part for part in parts if part)


async def _require_guidance_persistence_room_id(
    session_id: str,
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
) -> int:
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    if session.status not in {TrainingSessionStatus.ACTIVE, TrainingSessionStatus.COMPLETED}:
        raise HTTPException(
            status_code=400,
            detail="Training session must be active or completed before saving guidance",
        )
    if not session.room_id:
        raise HTTPException(
            status_code=400, detail="Training session must be started before saving guidance"
        )
    if str(session.room_id).startswith(f"{ConversationTrainingConversationAdapter.provider}:"):
        raise HTTPException(
            status_code=409,
            detail="Guidance persistence is not supported for message-tree training sessions",
        )
    try:
        return int(session.room_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Session room_id must be numeric to save guidance"
        ) from exc


async def _require_active_guidance_room_id(
    session_id: str,
    svc: TrainingSessionService,
    current_user: CurrentUser,
) -> int:
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail="Training session must be active before requesting guidance"
        )
    if not session.room_id:
        raise HTTPException(
            status_code=400, detail="Training session must be started before requesting guidance"
        )
    if str(session.room_id).startswith(f"{ConversationTrainingConversationAdapter.provider}:"):
        raise HTTPException(
            status_code=409,
            detail="Guidance streaming is not supported for message-tree training sessions; use refresh guidance",
        )
    try:
        return int(session.room_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Session room_id must be numeric to read guidance context"
        ) from exc


def _conversation_message_to_guidance_turn(message: MessageDTO_Agent) -> TranscriptTurn:
    role = str(message.role or "").strip().lower()
    speaker = {
        "user": TranscriptSpeaker.USER,
        "assistant": TranscriptSpeaker.COUNTERPART,
        "system": TranscriptSpeaker.SYSTEM,
        "tool": TranscriptSpeaker.SYSTEM,
    }.get(role, TranscriptSpeaker.COUNTERPART)
    metadata: dict[str, object] = dict(message.metadata or {})
    metadata.update(
        {
            "message_id": message.public_id or str(message.id),
            "conversation_id": message.conversation_id,
            "role": message.role,
            "branch_id": message.branch_id,
            "parent_message_id": message.parent_message_id,
        }
    )
    return TranscriptTurn(
        speaker=speaker,
        text=message.content.strip(),
        turn_id=message.public_id or str(message.id),
        created_at=message.created_at,
        metadata=metadata,
    )


async def _message_tree_guidance_turns(
    session_id: str,
    session,
    body: TrainingGuidanceRequestDTO,
    *,
    conversation_svc: ConversationApplicationService,
    current_user: CurrentUser,
) -> tuple[list[TranscriptTurn], str]:
    conversation_id = _message_tree_conversation_id_for_session(session)
    metadata_scope = owned_metadata_scope_for_current_user(current_user)
    conversation = await conversation_svc.get_conversation(
        conversation_id,
        metadata_scope=metadata_scope,
    )
    bound_session_id = str(
        conversation.metadata.get("trainingSessionId")
        or conversation.metadata.get("training_session_id")
        or ""
    ).strip()
    if bound_session_id != session_id:
        raise HTTPException(
            status_code=409,
            detail="Conversation is not bound to the requested training session",
        )
    selected_tail_message_id = _coerce_optional_text(body.selected_tail_message_id)
    if not selected_tail_message_id:
        raise HTTPException(
            status_code=409,
            detail="selected_tail_message_id is required for message-tree guidance",
        )
    path = await conversation_svc.get_message_path(
        conversation_id,
        selected_tail_message_id,
        limit=_TRAINING_GUIDANCE_SELECTED_PATH_LIMIT,
        statuses=["active"],
        metadata_scope=metadata_scope,
    )
    turns = [
        _conversation_message_to_guidance_turn(message)
        for message in path
        if message.content.strip()
        and (message.metadata or {}).get("source") != _TRAINING_GUIDANCE_MESSAGE_SOURCE
    ]
    return turns, selected_tail_message_id


async def _generate_training_guidance(
    session_id: str,
    body: TrainingGuidanceRequestDTO,
    *,
    svc: TrainingSessionService,
    chatroom_svc: ChatRoomApplicationService,
    conversation_svc: ConversationApplicationService,
    guidance_svc: TrainingLiveGuidanceService,
    current_user: CurrentUser,
) -> dict[str, object]:
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )

    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail="Training session must be active before requesting guidance"
        )

    runtime, capabilities = _guidance_runtime_contract(session)
    selected_tail_message_id: str | None = None
    if runtime == "message_tree" and not body.selected_tail_message_id and not body.recent_turns:
        raise HTTPException(
            status_code=409,
            detail="selected_tail_message_id is required for message-tree guidance",
        )
    if runtime == "message_tree" and body.selected_tail_message_id:
        recent_turns, selected_tail_message_id = await _message_tree_guidance_turns(
            session_id,
            session,
            body,
            conversation_svc=conversation_svc,
            current_user=current_user,
        )
        source = "message_tree"
    elif body.recent_turns:
        recent_turns = [
            _request_turn_to_guidance_turn(turn) for turn in body.recent_turns if turn.text.strip()
        ]
        source = "request"
    else:
        room_id = await _require_active_guidance_room_id(session_id, svc, current_user)
        detail = await chatroom_svc.get_room_detail(
            room_id,
            message_limit=body.message_limit,
            access_scope=_legacy_room_scope_for_accessible_training_session(
                session,
                current_user,
                room_id=room_id,
                operation="guidance_context",
            ),
        )
        recent_turns = [
            _message_to_guidance_turn(message)
            for message in detail.messages
            if message.content.strip() and not _is_training_guidance_message(message)
        ]
        source = "room"

    # A selected message-tree path is the source of truth for text training.
    # Ignore client-supplied task/rubric overrides here so a caller cannot
    # manufacture a different coaching context for the persisted snapshot.
    task_goal = _task_goal_for_guidance(session)
    rubric = _rubric_for_guidance(session)
    if runtime != "message_tree":
        task_goal = body.task_goal or task_goal
        rubric = body.rubric or rubric

    state = guidance_svc.build_state(
        training_session_id=session_id,
        task_goal=task_goal,
        rubric=rubric,
        recent_turns=recent_turns,
    )
    events = await guidance_svc.generate_guidance_async(
        training_session_id=session_id,
        task_goal=state.task_goal,
        rubric=state.rubric,
        recent_turns=recent_turns,
    )
    return {
        "session_id": session_id,
        "room_id": str(session.room_id) if session.room_id is not None else None,
        "events": [event.to_sse_payload() for event in events],
        "source": source,
        "window_size": state.window_size,
        "total_turn_count": state.total_turn_count,
        "context_runtime": runtime,
        "context_selection": (
            "selected_path"
            if source == "message_tree"
            else "client_recent_turns" if source == "request" else "room_messages"
        ),
        "selected_tail_message_id": selected_tail_message_id,
        "capabilities": capabilities,
        "persistence": {
            "status": "not_requested",
            "retryable": False,
            "persisted": False,
        },
    }


async def _persist_generated_message_tree_guidance(
    session_id: str,
    data: dict[str, object],
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
) -> dict[str, object]:
    """Persist only guidance produced from a server-validated selected path."""

    if data.get("context_runtime") != "message_tree" or data.get("source") != "message_tree":
        return {
            "status": "not_supported",
            "retryable": False,
            "persisted": False,
        }
    selected_tail_message_id = _coerce_optional_text(data.get("selected_tail_message_id"))
    if not selected_tail_message_id:
        return {
            "status": "failed",
            "retryable": False,
            "persisted": False,
            "code": "selected_path_missing",
        }

    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    patch, persistence = append_selected_path_guidance(
        session.task_config.metadata,
        session_id=session_id,
        selected_tail_message_id=selected_tail_message_id,
        events=data.get("events"),
        source=str(data.get("source") or "message_tree"),
        context_runtime=str(data.get("context_runtime") or "message_tree"),
        context_selection=str(data.get("context_selection") or "selected_path"),
        window_size=int(data.get("window_size") or 0),
        total_turn_count=int(data.get("total_turn_count") or 0),
    )
    try:
        await svc.record_session_metadata(
            session_id,
            metadata=patch,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except Exception:
        logger.exception(
            "Failed to persist selected-path training guidance",
            extra={"training_session_id": session_id},
        )
        return guidance_persistence_failure(
            selected_tail_message_id=selected_tail_message_id,
        )
    return persistence


def _format_sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _guidance_payload_signature(data: dict[str, object]) -> str:
    events = data.get("events", [])
    stable_events = []
    if isinstance(events, list):
        stable_events = [
            {key: value for key, value in event.items() if key != "created_at"}
            for event in events
            if isinstance(event, dict)
        ]
    stable = {
        "source": data.get("source"),
        "total_turn_count": data.get("total_turn_count"),
        "events": stable_events,
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, default=str)


def _guidance_stream_payload(
    data: dict[str, object],
    *,
    reason: str,
    trigger: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "reason": reason,
        "trigger": trigger,
        **data,
    }


def _guidance_trigger_from_room_event(event: str, data: object) -> dict[str, object]:
    trigger: dict[str, object] = {"event": event}
    if isinstance(data, dict):
        for key in ("id", "sender_type", "sender_id", "room_id"):
            if key in data:
                trigger["message_id" if key == "id" else key] = data[key]
    return trigger


async def _send_event(websocket: WebSocket, event: RealtimeEvent) -> None:
    await websocket.send_json(_event_to_wire(event))


async def _send_wire_event(
    websocket: WebSocket,
    event_type: str,
    session: RealtimeSession,
    payload: dict[str, object] | None = None,
) -> None:
    await websocket.send_json(_realtime_wire_event(event_type, session, payload))


def _default_realtime_agent_instructions() -> str:
    return (
        "You are a concise AI training counterpart in Talk Training Studio. "
        "Run a spoken role-play with the user, answer naturally, ask short follow-up "
        "questions, and keep each reply brief enough for live practice. "
        "Do not evaluate at length during the call; focus on keeping the conversation moving."
    )


def _normalized_realtime_llm_provider(value: object | None) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _is_openrouter_base_url(value: object | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlsplit(text if "://" in text else f"https://{text}")
    hostname = (parsed.hostname or "").lower()
    return hostname == "openrouter.ai" or hostname.endswith(".openrouter.ai")


def _pipecat_realtime_llm_provider() -> str:
    llm_settings = settings.llm
    provider = _normalized_realtime_llm_provider(getattr(llm_settings, "provider", None))
    if provider in _OPENROUTER_LLM_PROVIDER_ALIASES or _is_openrouter_base_url(
        getattr(llm_settings, "base_url", None)
    ):
        return _OPENROUTER_LLM_PROVIDER
    return "openai"


def _pipecat_realtime_pipeline_metadata(
    binding: tuple[str, int],
    *,
    profile: str = _PIPECAT_REALTIME_PROFILE_CASCADE,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    if profile == _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        return _pipecat_speech_to_speech_pipeline_metadata(
            binding,
            input_sample_rate=input_sample_rate,
        )
    return _pipecat_cascade_pipeline_metadata(
        binding,
        input_sample_rate=input_sample_rate,
    )


def _pipecat_cascade_pipeline_metadata(
    binding: tuple[str, int],
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    resolved_input_sample_rate = input_sample_rate or 16000
    profile_contract = _pipecat_realtime_profile_contract(
        _PIPECAT_REALTIME_PROFILE_CASCADE,
        input_sample_rate=resolved_input_sample_rate,
    )
    stt: dict[str, object] = {
        "provider": "openai",
        "turnDetection": "disabled",
    }
    if settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL:
        stt["model"] = settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL
    llm: dict[str, object] = {
        "provider": _pipecat_realtime_llm_provider(),
        "model": settings.llm.default_model,
    }
    if settings.llm.base_url:
        llm["baseUrl"] = settings.llm.base_url

    return {
        "transport": "websocket",
        "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
        "profile": _PIPECAT_REALTIME_PROFILE_CASCADE,
        "realtimeProfile": _PIPECAT_REALTIME_PROFILE_CASCADE,
        "transcriptionModel": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        "inputSampleRate": resolved_input_sample_rate,
        "outputSampleRate": 24000,
        "inputAudioFormat": "pcm16",
        "outputAudioFormat": "pcm16",
        "audioContract": _pipecat_realtime_audio_contract(
            _PIPECAT_REALTIME_PROFILE_CASCADE,
            input_sample_rate=resolved_input_sample_rate,
        ),
        "profileContract": profile_contract,
        "latencyProfile": profile_contract["latencyProfile"],
        "costProfile": profile_contract["costProfile"],
        "browserE2E": profile_contract["browserE2E"],
        "readinessFeatures": profile_contract["readinessFeatures"],
        "stt": stt,
        "llm": llm,
        "context": {"provider": "pipecat", "realtimeServiceMode": False},
        "tts": {"provider": "openai"},
        "vad": {"provider": "silero", "source": "pipecat", "sampleRate": 16000},
        "turnDetection": {"provider": "pipecat", "source": "pipecat"},
        "talkwise": {
            "trainingSessionId": binding[0],
            "roomId": binding[1],
            "provider": "pipecat",
            "runtime": "realtime_voice",
            "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
            "transport": "websocket",
        },
    }


def _pipecat_speech_to_speech_pipeline_metadata(
    binding: tuple[str, int],
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    resolved_input_sample_rate = input_sample_rate or 24000
    profile_contract = _pipecat_realtime_profile_contract(
        _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
        input_sample_rate=resolved_input_sample_rate,
    )
    turn_detection = {
        "provider": "openai",
        "source": "openai_realtime",
        "mode": "semantic_vad",
    }
    realtime_llm: dict[str, object] = {
        "provider": "openai",
        "model": settings.REALTIME_OPENAI_MODEL,
        "voice": settings.REALTIME_OPENAI_VOICE,
        "turnDetection": turn_detection,
        "noiseReduction": "near_field",
        "outputModalities": ["audio"],
    }
    if settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL:
        realtime_llm["transcriptionModel"] = settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL

    return {
        "transport": "websocket",
        "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
        "profile": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
        "realtimeProfile": _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
        "transcriptionModel": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        "inputSampleRate": resolved_input_sample_rate,
        "outputSampleRate": 24000,
        "inputAudioFormat": settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
        "outputAudioFormat": settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
        "audioContract": _pipecat_realtime_audio_contract(
            _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH,
            input_sample_rate=resolved_input_sample_rate,
        ),
        "profileContract": profile_contract,
        "latencyProfile": profile_contract["latencyProfile"],
        "costProfile": profile_contract["costProfile"],
        "browserE2E": profile_contract["browserE2E"],
        "readinessFeatures": profile_contract["readinessFeatures"],
        "realtimeLlm": realtime_llm,
        "context": {"provider": "pipecat", "realtimeServiceMode": True},
        "turnDetection": turn_detection,
        "talkwise": {
            "trainingSessionId": binding[0],
            "roomId": binding[1],
            "provider": "pipecat",
            "runtime": "realtime_voice",
            "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
            "transport": "websocket",
        },
    }


def _volcengine_doubao_realtime_audio_contract(
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    resolved_input_sample_rate = input_sample_rate or 16000
    return {
        "input": {
            "encoding": "pcm16",
            "sampleRate": resolved_input_sample_rate,
            "channels": 1,
            "mimeType": "audio/pcm",
        },
        "output": {
            "encoding": "pcm16",
            "sampleRate": 24000,
            "channels": 1,
            "mimeType": "audio/pcm",
        },
        "transport": "websocket.json_base64_audio",
    }


def _volcengine_doubao_realtime_profile_contract(
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    return {
        "latencyProfile": "true_realtime",
        "costProfile": "provider_metered",
        "inputAudio": _volcengine_doubao_realtime_audio_contract(
            input_sample_rate=input_sample_rate,
        )["input"],
        "outputAudio": _volcengine_doubao_realtime_audio_contract()["output"],
        "services": dict(_VOLCENGINE_DOUBAO_REALTIME_REQUIRED_FEATURES),
        "turnDetection": {
            "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
            "source": "volcengine_doubao_realtime",
        },
        "talkwiseIntegration": {
            "transcriptsPersisted": True,
            "liveGuidanceTriggered": True,
            "providerNativeRealtime": True,
        },
        "browserE2E": {
            "verified": False,
            "requiredSignals": [
                "session.started",
                "session.configured",
                "audio.output",
                "transcript.done",
                "transcript.persisted",
            ],
        },
        "readinessFeatures": dict(_VOLCENGINE_DOUBAO_REALTIME_REQUIRED_FEATURES),
    }


def _volcengine_doubao_realtime_pipeline_metadata(
    binding: tuple[str, int],
    *,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    resolved_input_sample_rate = input_sample_rate or 16000
    profile_contract = _volcengine_doubao_realtime_profile_contract(
        input_sample_rate=resolved_input_sample_rate,
    )
    model = settings.REALTIME_OPENAI_MODEL or "1.2.6.0"
    voice = _realtime_voice_for_provider(_VOLCENGINE_DOUBAO_REALTIME_PROVIDER)
    realtime_llm: dict[str, object] = {
        "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
        "model": model,
        "turnDetection": profile_contract["turnDetection"],
        "outputModalities": ["audio", "text"],
    }
    if voice:
        realtime_llm["voice"] = voice
    if settings.REALTIME_BASE_URL:
        realtime_llm["baseUrl"] = settings.REALTIME_BASE_URL

    return {
        "transport": "websocket",
        "realtimeRuntime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
        "profile": "native_duplex",
        "realtimeProfile": "native_duplex",
        "inputSampleRate": resolved_input_sample_rate,
        "outputSampleRate": 24000,
        "inputAudioFormat": "pcm16",
        "outputAudioFormat": "pcm16",
        "audioContract": _volcengine_doubao_realtime_audio_contract(
            input_sample_rate=resolved_input_sample_rate,
        ),
        "profileContract": profile_contract,
        "latencyProfile": profile_contract["latencyProfile"],
        "costProfile": profile_contract["costProfile"],
        "browserE2E": profile_contract["browserE2E"],
        "readinessFeatures": profile_contract["readinessFeatures"],
        "realtimeLlm": realtime_llm,
        "context": {
            "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
            "realtimeServiceMode": True,
            "providerNativeRealtime": True,
        },
        "stt": {"provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER},
        "tts": {"provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER},
        "turnDetection": profile_contract["turnDetection"],
        "talkwise": {
            "trainingSessionId": binding[0],
            "roomId": binding[1],
            "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
            "runtime": "realtime_voice",
            "realtimeRuntime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
            "transport": "websocket",
        },
    }


def _realtime_pipeline_metadata(
    provider: str,
    binding: tuple[str, int],
    *,
    profile: str = _PIPECAT_REALTIME_PROFILE_CASCADE,
    input_sample_rate: int | None = None,
) -> dict[str, object]:
    if _uses_volcengine_doubao_realtime(provider):
        return _volcengine_doubao_realtime_pipeline_metadata(
            binding,
            input_sample_rate=input_sample_rate,
        )
    return _pipecat_realtime_pipeline_metadata(
        binding,
        profile=profile,
        input_sample_rate=input_sample_rate,
    )


def _load_pipecat_realtime_adapter() -> Any:
    from infrastructure.external.pipecat import realtime_pipeline as pipecat_adapter

    return pipecat_adapter


def _load_volcengine_doubao_realtime_adapter() -> Any:
    from infrastructure.external.voice import volcengine_realtime

    return volcengine_realtime


def _pipecat_unavailable_capability_response(
    *,
    message: str,
    code: str,
    modules: tuple[str, ...] = (),
) -> dict[str, object]:
    readiness = build_realtime_readiness(
        required={
            "transport": "websocket",
            "features": dict(_PIPECAT_REALTIME_REQUIRED_FEATURES),
            "env": _OPENAI_REALTIME_API_KEY_ENV_KEYS,
        },
        blocking_reasons=(
            RealtimeReadinessIssue(
                code=code,
                message=message,
                phase="capability_check",
                provider="pipecat",
                modules=modules,
            ),
        ),
        runtime=REALTIME_RUNTIME_PIPECAT,
    ).to_dict()
    payload = {
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": "pipecat",
        "available": False,
        "coreAvailable": False,
        "websocketAvailable": False,
        "vadAvailable": False,
        "sttAvailable": False,
        "ttsAvailable": False,
        "llmAvailable": False,
        "openaiRealtimeLlmAvailable": False,
        "turnDetectionAvailable": False,
        "profiles": _merge_pipecat_realtime_profile_contracts(None),
        "missingModules": list(modules),
        "optionalMissingModules": [],
        "error": message,
        "readyForCall": readiness["ready"],
        "readiness": readiness,
        "errors": readiness["blockingReasons"],
        "smoke": pipecat_realtime_smoke_contract(
            ready_for_call=False,
            require_websocket=True,
        ),
    }
    payload["smoke"] = _provider_neutral_realtime_smoke_contract(payload["smoke"])
    return payload


def _provider_neutral_realtime_smoke_contract(smoke: object) -> dict[str, object]:
    smoke_payload = dict(smoke) if isinstance(smoke, Mapping) else {}
    contract_events = [str(event) for event in (smoke_payload.get("contractEvents") or ())]
    for event_type in _REALTIME_LIFECYCLE_CONTRACT_EVENTS:
        if event_type not in contract_events:
            contract_events.append(event_type)
    smoke_payload["contractEvents"] = contract_events
    smoke_payload["errorTaxonomy"] = [dict(item) for item in REALTIME_PROVIDER_ERROR_TAXONOMY]
    smoke_payload["eventOrder"] = {
        "finalTranscript": [
            "transcript.done",
            "transcript.persisted",
            "training.live_guidance.triggered",
        ],
        "assistantAudioThenTranscript": [
            "audio.output",
            "transcript.done",
            "transcript.persisted",
        ],
    }
    smoke_payload["readinessAssertions"] = {
        "readyForCallImpliesLocalRuntimeReady": True,
        "browserE2EVerified": False,
        "requiresExplicitMediaPermission": True,
    }
    return smoke_payload


def _pipecat_realtime_capability_response() -> dict[str, object]:
    try:
        response = build_pipecat_realtime_capability_response(
            require_websocket=True,
            openai_api_key_available=bool(_openai_realtime_api_key()),
            include_source_snapshot=True,
        )
    except Exception as exc:
        return _pipecat_unavailable_capability_response(
            message=f"Pipecat capability check failed: {exc}",
            code="PIPECAT_CAPABILITY_ERROR",
        )
    data = dict(response)
    data["profiles"] = _merge_pipecat_realtime_profile_contracts(data.get("profiles"))
    data["smoke"] = _provider_neutral_realtime_smoke_contract(data.get("smoke"))
    return data


def _volcengine_doubao_realtime_capability_response() -> dict[str, object]:
    try:
        websocket_available = importlib.util.find_spec("websockets") is not None
    except Exception:
        websocket_available = False
    api_key_configured = bool(settings.REALTIME_API_KEY)
    missing_modules = [] if websocket_available else ["websockets"]
    blocking_reasons: list[RealtimeReadinessIssue] = []
    if not websocket_available:
        blocking_reasons.append(
            RealtimeReadinessIssue(
                code="VOLCENGINE_REALTIME_DEPENDENCY_MISSING",
                message="Volcengine Doubao realtime requires the 'websockets' package",
                phase="runtime_import",
                provider=_VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
                modules=("websockets",),
            )
        )
    if not api_key_configured:
        blocking_reasons.append(
            RealtimeReadinessIssue(
                code="MISSING_VOLCENGINE_REALTIME_API_KEY",
                message="Volcengine Doubao realtime API key is required",
                phase="configuration",
                provider=_VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
                missing_env=("REALTIME_API_KEY",),
            )
        )

    readiness = build_realtime_readiness(
        required={
            "transport": "websocket",
            "features": dict(_VOLCENGINE_DOUBAO_REALTIME_REQUIRED_FEATURES),
            "env": ["REALTIME_API_KEY"],
            "model": settings.REALTIME_OPENAI_MODEL or "1.2.6.0",
            "voice": _realtime_voice_for_provider(_VOLCENGINE_DOUBAO_REALTIME_PROVIDER),
            "baseUrl": (
                settings.REALTIME_BASE_URL
                or "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
            ),
        },
        blocking_reasons=blocking_reasons,
        runtime=REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    ).to_dict()
    profile_contract = _volcengine_doubao_realtime_profile_contract()
    smoke = _provider_neutral_realtime_smoke_contract(
        {
            "contractEvents": [
                "session.ready",
                "session.configured",
                "session.closed",
                "audio.output",
                "transcript.delta",
                "transcript.done",
                "transcript.persisted",
                "user_turn.started",
                "user_turn.stopped",
                "assistant_speaking.started",
                "assistant_speaking.stopped",
                "interrupted",
                "silence_timeout",
                "error",
            ],
            "eventOrder": {
                "finalTranscript": [
                    "transcript.done",
                    "transcript.persisted",
                    "training.live_guidance.triggered",
                ],
                "assistantAudioThenTranscript": [
                    "audio.output",
                    "transcript.done",
                    "transcript.persisted",
                ],
                "turnLifecycle": [
                    "user_turn.started",
                    "user_turn.stopped",
                    "assistant_speaking.started",
                    "assistant_speaking.stopped",
                ],
            },
            "readinessAssertions": {
                "readyForCallImpliesLocalRuntimeReady": True,
                "browserE2EVerified": False,
                "requiresExplicitMediaPermission": True,
                "providerNativeRuntime": True,
            },
        }
    )
    smoke["eventOrder"] = {
        "finalTranscript": [
            "transcript.done",
            "transcript.persisted",
            "training.live_guidance.triggered",
        ],
        "assistantAudioThenTranscript": [
            "audio.output",
            "transcript.done",
            "transcript.persisted",
        ],
        "turnLifecycle": [
            "user_turn.started",
            "user_turn.stopped",
            "assistant_speaking.started",
            "assistant_speaking.stopped",
        ],
    }
    smoke["readinessAssertions"] = {
        "readyForCallImpliesLocalRuntimeReady": True,
        "browserE2EVerified": False,
        "requiresExplicitMediaPermission": True,
        "providerNativeRuntime": True,
    }
    payload = {
        "runtime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
        "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
        "available": bool(readiness["ready"]),
        "coreAvailable": websocket_available,
        "websocketAvailable": websocket_available,
        "vadAvailable": True,
        "sttAvailable": True,
        "ttsAvailable": True,
        "llmAvailable": True,
        "openaiRealtimeLlmAvailable": False,
        "turnDetectionAvailable": True,
        "profiles": {
            "default": "native_duplex",
            "supported": ["native_duplex"],
            "native_duplex": {
                "contract": profile_contract,
                "latencyProfile": "true_realtime",
                "costProfile": "provider_metered",
                "audioContract": _volcengine_doubao_realtime_audio_contract(),
                "browserE2E": profile_contract["browserE2E"],
            },
        },
        "missingModules": missing_modules,
        "optionalMissingModules": [],
        "error": None if readiness["ready"] else readiness["blockingReasons"][0]["message"],
        "readyForCall": readiness["ready"],
        "readiness": readiness,
        "errors": readiness["blockingReasons"],
        "smoke": smoke,
    }
    return payload


def _realtime_capabilities_response() -> dict[str, object]:
    pipecat = _pipecat_realtime_capability_response()
    volcengine = _volcengine_doubao_realtime_capability_response()
    return {
        "pipecat": pipecat,
        "volcengineDoubaoRealtime": volcengine,
        "providers": {
            "pipecat": pipecat,
            "openai": pipecat,
            _VOLCENGINE_DOUBAO_REALTIME_PROVIDER: volcengine,
        },
    }


def _wire_value(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    nested = payload.get("payload")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if value is not None:
                return value
    return None


def _coerce_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_optional_room_id(value: object | None) -> int | None:
    text = _coerce_optional_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="room_id must be numeric") from exc


def _client_event_key_forms(key: object) -> tuple[str, str]:
    lowered = str(key).strip().lower()
    snake = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    compact = "".join(ch for ch in lowered if ch.isalnum())
    return snake, compact


def _omit_client_event_payload_key(key: object) -> bool:
    snake, compact = _client_event_key_forms(key)
    return (
        snake in _CLIENT_EVENT_PAYLOAD_OMIT_KEYS
        or compact in _CLIENT_EVENT_PAYLOAD_OMIT_KEYS
        or is_sensitive_realtime_metadata_key(key)
        or snake.endswith(("_audio", "_blob", "_content", "_raw", "_text", "_transcript"))
        or compact.endswith(("audio", "blob", "content", "raw", "text", "transcript"))
    )


def _truncate_client_event_text(value: str) -> str:
    redacted = redact_realtime_secret_text(value)
    if len(redacted) <= _CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS:
        return redacted
    return f"{redacted[:_CLIENT_EVENT_PAYLOAD_STRING_MAX_CHARS]}...[truncated]"


def _sanitize_client_event_payload_value(value: object, *, depth: int = 0) -> object | None:
    if depth > _CLIENT_EVENT_PAYLOAD_MAX_DEPTH:
        return "[max_depth_exceeded]"
    if isinstance(value, str):
        return _truncate_client_event_text(value)
    if isinstance(value, int | float | bool):
        return value
    if value is None:
        return None
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested_value in value.items():
            if _omit_client_event_payload_key(raw_key):
                continue
            safe_value = _sanitize_client_event_payload_value(nested_value, depth=depth + 1)
            if safe_value is not None:
                sanitized[str(raw_key)] = safe_value
        return sanitized
    if isinstance(value, list | tuple):
        sanitized_items: list[object] = []
        for item in list(value)[:_CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS]:
            safe_item = _sanitize_client_event_payload_value(item, depth=depth + 1)
            if safe_item is not None:
                sanitized_items.append(safe_item)
        omitted_items = len(value) - _CLIENT_EVENT_PAYLOAD_ARRAY_MAX_ITEMS
        if omitted_items > 0:
            sanitized_items.append({"truncated": True, "omittedItems": omitted_items})
        return sanitized_items
    return sanitize_realtime_public_value(value)


def _safe_client_event_payload(payload: Mapping[str, object]) -> dict[str, object]:
    safe_payload = _sanitize_client_event_payload_value(payload)
    if not isinstance(safe_payload, dict):
        return {}

    max_payload_bytes = max(256, int(settings.CLIENT_EVENT_LOGGING_MAX_PAYLOAD_BYTES))
    serialized = json.dumps(safe_payload, ensure_ascii=False, sort_keys=True)
    payload_bytes = len(serialized.encode("utf-8"))
    if payload_bytes <= max_payload_bytes:
        return safe_payload
    return {
        "truncated": True,
        "payloadBytes": payload_bytes,
        "maxPayloadBytes": max_payload_bytes,
    }


def _client_event_severity(value: object | None) -> str:
    severity = _coerce_optional_text(value) or "info"
    normalized = severity.lower()
    if normalized not in _CLIENT_REALTIME_EVENT_SEVERITIES:
        raise HTTPException(status_code=400, detail="Unsupported client event severity")
    return normalized


def _client_realtime_event_type(value: object | None) -> str:
    event_type = _coerce_optional_text(value)
    if event_type not in _CLIENT_REALTIME_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported client realtime event type")
    return event_type


async def _resolve_client_event_training_scope(
    body: ClientRealtimeEventDTO,
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
) -> tuple[str | None, int | None]:
    session_id = _coerce_optional_text(body.training_session_id)
    room_id = _coerce_optional_room_id(body.room_id)
    if session_id is None:
        if room_id is not None:
            raise HTTPException(
                status_code=400,
                detail="trainingSessionId is required when logging room-scoped client events",
            )
        return None, None

    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    session_room_id = _coerce_optional_room_id(getattr(session, "room_id", None))
    if room_id is not None and session_room_id is not None and room_id != session_room_id:
        raise HTTPException(
            status_code=403,
            detail="room_id does not match the accessible training session",
        )
    return session_id, room_id or session_room_id


def _query_binding(websocket: WebSocket) -> tuple[str | None, int | None]:
    params = websocket.query_params
    session_id = _coerce_optional_text(params.get("session_id") or params.get("sessionId"))
    room_id = _coerce_optional_room_id(params.get("room_id") or params.get("roomId"))
    return session_id, room_id


def _query_realtime_provider(websocket: WebSocket) -> str:
    provider = _coerce_optional_text(websocket.query_params.get("provider"))
    if provider is None:
        return "pipecat"
    normalized = _normalized_realtime_llm_provider(provider)
    if normalized in {"pipecat", "pipecat_pipeline"}:
        return "pipecat"
    if normalized in {"openai", "openai.realtime", "openai_realtime", "openai_webrtc"}:
        return "pipecat"
    if normalized in _VOLCENGINE_DOUBAO_REALTIME_PROVIDER_ALIASES:
        return _VOLCENGINE_DOUBAO_REALTIME_PROVIDER
    return normalized


def _query_realtime_profile(websocket: WebSocket) -> str:
    profile = _coerce_optional_text(
        websocket.query_params.get("profile")
        or websocket.query_params.get("realtimeProfile")
        or websocket.query_params.get("realtime_profile")
    )
    if profile is None:
        return _PIPECAT_REALTIME_PROFILE_CASCADE
    normalized = profile.lower().replace("-", "_").replace(" ", "_")
    compact = normalized.replace("_", "")
    selected = _PIPECAT_REALTIME_PROFILE_ALIASES.get(
        normalized,
        _PIPECAT_REALTIME_PROFILE_ALIASES.get(compact),
    )
    if selected is None:
        allowed = ", ".join(sorted(_PIPECAT_REALTIME_PROFILE_ALIASES))
        raise HTTPException(
            status_code=400,
            detail=f"Realtime profile must be one of: {allowed}",
        )
    return selected


def _default_realtime_input_sample_rate(profile: str) -> int:
    if profile == _PIPECAT_REALTIME_PROFILE_SPEECH_TO_SPEECH:
        return 24000
    return 16000


def _query_realtime_input_sample_rate(websocket: WebSocket, *, profile: str) -> int:
    value = (
        websocket.query_params.get("input_sample_rate")
        or websocket.query_params.get("inputSampleRate")
        or websocket.query_params.get("sample_rate")
        or websocket.query_params.get("sampleRate")
    )
    if value is None:
        return _default_realtime_input_sample_rate(profile)
    sample_rate = _coerce_optional_int(value)
    if sample_rate is None or sample_rate < 8000 or sample_rate > 48000:
        raise HTTPException(
            status_code=400,
            detail="Realtime input sample rate must be between 8000 and 48000 Hz",
        )
    return sample_rate


def _realtime_audio_chunk_metadata(
    *,
    provider: str,
    profile: str,
    input_sample_rate: int,
    payload: Mapping[str, object] | None = None,
) -> dict[str, object]:
    sample_rate = input_sample_rate
    channels = 1
    if payload is not None:
        sample_rate = (
            _coerce_optional_int(payload.get("sampleRate") or payload.get("sample_rate"))
            or input_sample_rate
        )
        channels = _coerce_optional_int(payload.get("channels") or payload.get("numChannels")) or 1
    return {
        "profile": profile,
        "realtimeProfile": profile,
        "sampleRate": sample_rate,
        "inputSampleRate": sample_rate,
        "channels": channels,
        "audioContract": (
            _volcengine_doubao_realtime_audio_contract(input_sample_rate=sample_rate)
            if _uses_volcengine_doubao_realtime(provider)
            else _pipecat_realtime_audio_contract(
                profile,
                input_sample_rate=sample_rate,
            )
        ),
    }


def _uses_pipecat_realtime(provider: str) -> bool:
    return _normalized_realtime_llm_provider(provider) in _PIPECAT_REALTIME_PROVIDER_ALIASES


def _uses_volcengine_doubao_realtime(provider: str) -> bool:
    return (
        _normalized_realtime_llm_provider(provider) in _VOLCENGINE_DOUBAO_REALTIME_PROVIDER_ALIASES
    )


def _uses_supported_realtime_provider(provider: str) -> bool:
    return _uses_pipecat_realtime(provider) or _uses_volcengine_doubao_realtime(provider)


def _realtime_pipeline_unavailable_detail(provider: str) -> str:
    if _uses_volcengine_doubao_realtime(provider):
        return "Volcengine Doubao realtime pipeline is not available"
    return "Pipecat realtime pipeline is not available"


def _realtime_voice_for_provider(provider: str) -> str | None:
    voice = _coerce_optional_text(settings.REALTIME_OPENAI_VOICE)
    if _uses_volcengine_doubao_realtime(provider):
        if voice is None:
            return _DEFAULT_VOLCENGINE_DOUBAO_REALTIME_VOICE
        normalized = voice.lower().replace("_", "-").replace(" ", "-")
        if normalized in _VOLCENGINE_DOUBAO_REALTIME_PLACEHOLDER_VOICES:
            return _DEFAULT_VOLCENGINE_DOUBAO_REALTIME_VOICE
    if voice is None:
        return None
    return voice


def _echoes_realtime_transcript_done(provider: str) -> bool:
    return _uses_pipecat_realtime(provider) or _uses_volcengine_doubao_realtime(provider)


def _realtime_start_metadata(
    provider: str,
    binding: tuple[str, int] | None,
    *,
    profile: str,
    input_sample_rate: int,
) -> dict[str, object]:
    if _uses_volcengine_doubao_realtime(provider):
        metadata: dict[str, object] = {
            "transport": "websocket",
            "provider": _VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
            "realtimeRuntime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
            "realtimeProfile": "native_duplex",
            "inputSampleRate": input_sample_rate,
            "audioContract": _volcengine_doubao_realtime_audio_contract(
                input_sample_rate=input_sample_rate,
            ),
            "profileContract": _volcengine_doubao_realtime_profile_contract(
                input_sample_rate=input_sample_rate,
            ),
        }
    else:
        metadata = {
            "transport": "websocket",
            "provider": provider,
            "realtimeRuntime": realtime_runtime_for_provider(provider),
            "realtimeProfile": profile,
            "inputSampleRate": input_sample_rate,
            "audioContract": _pipecat_realtime_audio_contract(
                profile,
                input_sample_rate=input_sample_rate,
            ),
            "profileContract": _pipecat_realtime_profile_contract(
                profile,
                input_sample_rate=input_sample_rate,
            ),
        }
    if binding is not None:
        metadata.update({"trainingSessionId": binding[0], "roomId": binding[1]})
    return metadata


def _configure_binding(payload: dict[str, object]) -> tuple[str | None, int | None]:
    session_id = _coerce_optional_text(_wire_value(payload, "session_id", "sessionId"))
    room_id = _coerce_optional_room_id(_wire_value(payload, "room_id", "roomId"))
    return session_id, room_id


async def _resolve_realtime_binding(
    session_id: str | None,
    room_id: int | None,
    *,
    svc: TrainingSessionService,
    uow_factory: Callable[..., AbstractUnitOfWork],
    current_user: CurrentUser,
) -> tuple[str, int] | None:
    if session_id is None and room_id is None:
        return None
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required when binding realtime")

    try:
        training_session = await svc.get_session(
            session_id,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    if training_session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail="Training session must be active before binding realtime"
        )
    if not training_session.room_id:
        raise HTTPException(
            status_code=400, detail="Training session must be started before binding realtime"
        )

    bound_room_id = _coerce_optional_room_id(training_session.room_id)
    if bound_room_id is None:
        raise HTTPException(
            status_code=400, detail="Session room_id must be numeric to bind realtime"
        )
    if room_id is not None and room_id != bound_room_id:
        raise HTTPException(
            status_code=400, detail="room_id does not match the active training session"
        )

    async with uow_factory(readonly=True) as uow:
        room = await uow.chat_room_repository.get_by_id(bound_room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Chat room {bound_room_id} not found")

    return session_id, bound_room_id


async def _build_realtime_voice_context(
    binding: tuple[str, int],
    *,
    provider: str,
    realtime_profile: str = _PIPECAT_REALTIME_PROFILE_CASCADE,
    svc: TrainingSessionService,
    uow_factory: Callable[..., AbstractUnitOfWork],
    current_user: CurrentUser,
) -> dict[str, object]:
    """Build the TrainingCore-derived context shared by text and voice runtimes."""

    session = await _require_accessible_training_session(
        binding[0],
        svc=svc,
        current_user=current_user,
    )
    metadata = training_core_metadata_for_session(
        session,
        runtime="realtime_voice",
        extra={
            "transport": "websocket",
            "provider": provider,
            "realtimeRuntime": realtime_runtime_for_provider(provider),
            "realtimeProfile": realtime_profile,
            "roomId": binding[1],
        },
    )
    return {
        "task_goal": _task_goal_for_guidance(session),
        "rubric": _rubric_for_guidance(session),
        "recent_turns": await _recent_realtime_context_turns(
            binding[1],
            uow_factory=uow_factory,
            limit=_REALTIME_CONTEXT_RECENT_TURN_LIMIT,
        ),
        "metadata": metadata,
    }


async def _recent_realtime_context_turns(
    room_id: int,
    *,
    uow_factory: Callable[..., AbstractUnitOfWork],
    limit: int,
) -> tuple[dict[str, object], ...]:
    if limit < 1:
        return ()

    async with uow_factory(readonly=True) as uow:
        total = await uow.stakeholder_message_repository.count_by_room_id(room_id)
        skip = max(total - limit, 0)
        messages = await uow.stakeholder_message_repository.list_by_room_id(
            room_id,
            skip=skip,
            limit=limit,
        )

    turns: list[dict[str, object]] = []
    for message in messages:
        dto = MessageDTO.model_validate(message)
        if not dto.content.strip() or _is_training_guidance_message(dto):
            continue
        turns.append(_guidance_turn_to_realtime_context_turn(_message_to_guidance_turn(dto)))
    return tuple(turns)


_FINAL_TRANSCRIPT_EVENT_TYPES = FINAL_TRANSCRIPT_EVENT_TYPES


async def _persist_realtime_message(
    room_id: int,
    content: str,
    *,
    uow_factory: Callable[..., AbstractUnitOfWork],
    metadata: dict[str, object] | None = None,
    sender_type: str = "user",
    sender_id: str = "user",
) -> MessageDTO:
    async with uow_factory() as uow:
        room = await uow.chat_room_repository.get_by_id(room_id)
        if room is None:
            raise HTTPException(status_code=404, detail=f"Chat room {room_id} not found")
        saved = await uow.stakeholder_message_repository.create(
            Message(
                id=None,
                room_id=room_id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=content,
                metadata=metadata or {},
            )
        )
        await uow.chat_room_repository.update_last_message_at(room_id, saved.timestamp)
        dto = MessageDTO.model_validate(saved)

    await _publish_realtime_room_message(room_id, dto)
    return dto


async def _publish_realtime_room_message(room_id: int, message: MessageDTO) -> None:
    await room_event_bus.publish(room_id, "message", message.model_dump(mode="json"))


class _WebSocketTrainingTranscriptSink:
    def __init__(
        self,
        *,
        websocket: WebSocket,
        session: RealtimeSession,
        training_session_id: str,
        room_id: int,
        svc: TrainingSessionService,
        uow_factory: Callable[..., AbstractUnitOfWork],
        access_scope: TrainingSessionAccessScope,
    ) -> None:
        self._websocket = websocket
        self._session = session
        self._training_session_id = training_session_id
        self._room_id = room_id
        self._sink = RealtimeTranscriptPersistenceSink(
            uow_factory=uow_factory,
            session_service=svc,
            publish_message=_publish_realtime_room_message,
            access_scope=access_scope,
        )

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
        if _echoes_realtime_transcript_done(transcript.provider):
            await _send_wire_event(
                self._websocket,
                "transcript.done",
                self._session,
                _realtime_transcript_done_payload(transcript),
            )
        persisted = await self._sink.persist(transcript)
        payload = dict(persisted.payload)
        payload.setdefault("trainingSessionId", self._training_session_id)
        payload.setdefault("roomId", self._room_id)
        await _send_wire_event(
            self._websocket,
            "transcript.persisted",
            self._session,
            payload,
        )
        return persisted


def _realtime_transcript_done_payload(transcript: RealtimeTranscript) -> dict[str, object]:
    payload: dict[str, object] = {
        "text": transcript.text,
        "role": transcript.role,
        "eventType": transcript.event_type,
        "runtime": transcript.runtime,
        "provider": transcript.provider,
        "trainingSessionId": transcript.binding.training_session_id,
        "roomId": transcript.binding.room_id,
        "realtimeSessionId": transcript.realtime_session_id,
    }
    for key, value in {
        "eventId": transcript.event_id,
        "itemId": transcript.item_id,
        "responseId": transcript.response_id,
    }.items():
        if value is not None:
            payload[key] = value
    return payload


def _pipeline_event_type(payload: Mapping[str, object]) -> str:
    return str(payload.get("type") or "").strip().lower()


def _pipeline_event_value(payload: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    nested = payload.get("payload")
    if isinstance(nested, Mapping):
        for key in keys:
            value = nested.get(key)
            if value is not None:
                return value
    return None


def _decode_pipeline_audio_bytes(payload: Mapping[str, object]) -> bytes:
    value = _pipeline_event_value(payload, "audio", "audioData", "data", "chunk", "base64")
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return b""
        if "," in text and text.lower().startswith("data:"):
            text = text.split(",", 1)[1].strip()
        try:
            return base64.b64decode(text, validate=True)
        except ValueError:
            return b""
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        try:
            return bytes(value)
        except ValueError:
            return b""
    return b""


def _coerce_optional_int(value: object | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe_realtime_value(value: object) -> object | None:
    return sanitize_realtime_public_value(value)


def _pipeline_realtime_event_payload(payload: Mapping[str, object]) -> dict[str, object]:
    event_payload: dict[str, object] = {}
    for key, value in payload.items():
        if key == "type":
            continue
        safe_value = _json_safe_realtime_value(value)
        if safe_value is not None:
            event_payload[str(key)] = safe_value
    return event_payload


def _pipeline_audio_output_payload(
    payload: Mapping[str, object],
    *,
    audio_bytes: bytes,
    mime_type: str | None,
    sequence: int | None,
) -> dict[str, object]:
    output: dict[str, object] = {}
    nested = payload.get("payload")
    if isinstance(nested, Mapping):
        for key, value in nested.items():
            safe_value = _json_safe_realtime_value(value)
            if safe_value is not None:
                output[str(key)] = safe_value
    for key, value in payload.items():
        if key in {"type", "payload"}:
            continue
        safe_value = _json_safe_realtime_value(value)
        if safe_value is not None:
            output[str(key)] = safe_value

    for key in ("audio", "audioData", "data", "chunk", "base64"):
        output.pop(key, None)
    output["audio"] = base64.b64encode(audio_bytes).decode("ascii")
    output["bytes"] = len(audio_bytes)
    if mime_type:
        output["mime_type"] = mime_type
        output["mimeType"] = mime_type
    if sequence is not None:
        output["sequence"] = sequence
    return output


async def _send_pipeline_audio_output_event(
    *,
    websocket: WebSocket,
    session: RealtimeSession,
    payload: Mapping[str, object],
) -> None:
    audio_bytes = _decode_pipeline_audio_bytes(payload)
    mime_type = _coerce_optional_text(
        _pipeline_event_value(payload, "mimeType", "mime_type", "contentType", "content_type")
    )
    try:
        event = session.send_audio(audio_bytes, mime_type)
        wire_event = _event_to_wire(event)
        sequence = _coerce_optional_int(event.payload.get("sequence"))
    except RealtimeSessionStateError:
        wire_event = _realtime_wire_event("audio.output", session)
        sequence = _coerce_optional_int(_pipeline_event_value(payload, "sequence"))
    wire_event["payload"] = _pipeline_audio_output_payload(
        payload,
        audio_bytes=audio_bytes,
        mime_type=mime_type,
        sequence=sequence,
    )
    await websocket.send_json(wire_event)


def _normalize_video_content_type(content_type: str | None) -> str:
    return (content_type or "application/octet-stream").split(";")[0].strip().lower()


def _video_extension(filename: str | None, content_type: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in {".webm", ".mp4", ".ogv", ".ogg", ".mov", ".mkv"}:
        return ext
    return _VIDEO_EXTENSIONS.get(content_type) or mimetypes.guess_extension(content_type) or ".webm"


def _resolve_video_answer_file(filename: str) -> Path:
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Video answer not found")
    root = _VIDEO_ANSWER_DIR.resolve()
    path = (_VIDEO_ANSWER_DIR / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Video answer not found") from exc
    return path


_VIDEO_ANSWER_METADATA_SUFFIX = ".meta.json"


def _resolve_video_answer_metadata_file(filename: str) -> Path:
    return _resolve_video_answer_file(f"{filename}{_VIDEO_ANSWER_METADATA_SUFFIX}")


def _load_video_answer_metadata(filename: str) -> dict[str, object]:
    path = _resolve_video_answer_metadata_file(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video answer not found")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Video answer not found") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=404, detail="Video answer not found")
    return raw


def _write_video_answer_record(
    path: Path,
    *,
    data: bytes,
    metadata: dict[str, object],
) -> None:
    path.write_bytes(data)
    metadata_path = _resolve_video_answer_metadata_file(path.name)
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")


def _build_video_answer_url(
    filename: str,
    *,
    training_session_id: str,
    room_id: int,
) -> str:
    params: dict[str, str] = {
        "training_session_id": training_session_id,
        "room_id": str(room_id),
    }
    return f"/api/v1/training-studio/video-answers/{filename}?{urlencode(params)}"


def _training_material_tool_scope_for_current_user(current_user: CurrentUser) -> OwnedMetadataScope:
    return owned_metadata_scope_for_current_user(current_user)


def _training_material_tool_consumer(
    file_assets: FileAssetApplicationService,
) -> TrainingMaterialToolConsumerService:
    return TrainingMaterialToolConsumerService(file_assets)


def _material_review_session_access_scope_for_current_user(
    current_user: CurrentUser,
) -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id=current_user.user_id,
        team_id=current_user.team_id,
        include_team_scope=current_user.is_admin or current_user.is_leader,
    )


async def _require_material_review_training_session(
    session_id: str,
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
):
    try:
        return await svc.get_session(
            session_id,
            access_scope=_material_review_session_access_scope_for_current_user(current_user),
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc


async def _material_review_report_context(
    session,
    *,
    reader_svc: AnalysisReaderService,
    current_user: CurrentUser,
) -> MaterialReviewReportContext:
    if not session.report_id:
        return MaterialReviewReportContext()
    try:
        report_lookup_id = int(session.report_id)
    except (TypeError, ValueError):
        return MaterialReviewReportContext()
    try:
        room_lookup_id = _stakeholder_room_id_for_training_session(session)
    except (TypeError, ValueError):
        return MaterialReviewReportContext()
    with suppress(Exception):
        report = await reader_svc.get_report(
            report_lookup_id,
            room_id=room_lookup_id,
            access_scope=_legacy_room_scope_for_accessible_training_session(
                session,
                current_user,
                room_id=room_lookup_id,
                operation="material_review_report_context",
            ),
        )
        if report is None or str(report.room_id) != str(room_lookup_id):
            return MaterialReviewReportContext()
        return MaterialReviewReportContext(
            summary=report.summary or "",
            content=_material_review_report_content(report.content),
        )
    return MaterialReviewReportContext()


def _material_review_report_content(content: object) -> dict[str, Any]:
    if hasattr(content, "model_dump"):
        dumped = content.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return dict(content) if isinstance(content, dict) else {}


async def _material_review_replay_context(
    session,
    *,
    chatroom_svc: ChatRoomApplicationService,
    current_user: CurrentUser,
) -> MaterialReviewReplayContext:
    try:
        room_id = int(session.room_id) if session.room_id is not None else None
    except (TypeError, ValueError):
        return MaterialReviewReplayContext(turns=[])
    if room_id is None:
        return MaterialReviewReplayContext(turns=[])

    replay_limit = 40
    with suppress(Exception):
        detail = await chatroom_svc.get_room_detail(
            room_id,
            message_limit=replay_limit,
            access_scope=_legacy_room_scope_for_accessible_training_session(
                session,
                current_user,
                room_id=room_id,
                operation="material_review_replay_context",
            ),
        )
        if not _material_review_room_matches_session(detail, session):
            return MaterialReviewReplayContext(turns=[])
        turns = [
            _material_review_message_text(message)
            for message in detail.messages
            if message.content.strip() and not _is_training_guidance_message(message)
        ]
        return MaterialReviewReplayContext(
            turns=[turn for turn in turns if turn],
            truncated=len(detail.messages) >= replay_limit,
        )
    return MaterialReviewReplayContext(turns=[])


def _material_review_room_matches_session(detail, session) -> bool:
    room = getattr(detail, "room", None)
    room_id = getattr(room, "id", None)
    if room_id is not None and str(room_id) != str(session.room_id):
        return False
    session_user_id = str(getattr(session, "user_id", "") or "").strip()
    if not session_user_id:
        return False
    messages = list(getattr(detail, "messages", []) or [])
    if not messages:
        return True
    saw_session_user_message = False
    for message in messages:
        if getattr(message, "sender_type", None) != "user":
            continue
        sender_id = str(getattr(message, "sender_id", "") or "").strip()
        if not sender_id or sender_id != session_user_id:
            return False
        saw_session_user_message = True
    return saw_session_user_message


def _material_review_message_text(message: MessageDTO) -> str:
    if message.sender_type == "user":
        speaker = "User"
    elif message.sender_type == "system":
        speaker = "System"
    else:
        speaker = "Counterpart"
    content = re.sub(r"\s+", " ", message.content).strip()
    if len(content) > 500:
        content = f"{content[:500].rstrip()}..."
    return f"{speaker}: {content}" if content else ""


@router.post("/sessions", status_code=201, summary="Create a Training Studio session")
async def create_training_session(
    body: CreateTrainingSessionDTO,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    scope = training_scope_for(
        current_user,
        requested_user_id=_coerce_optional_text(body.user_id) or _coerce_optional_text(x_user_id),
        requested_team_id=_coerce_optional_text(body.team_id) or _coerce_optional_text(x_team_id),
    )
    if scope.user_id != body.user_id or scope.team_id != body.team_id:
        body = body.model_copy(update={"user_id": scope.user_id, "team_id": scope.team_id})
    try:
        session = await svc.create_session(body)
    except (DomainValidationException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=_session_to_dict(session))


@router.get("/sessions", summary="List Training Studio sessions")
async def list_training_sessions(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    scenario_template_id: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=200),
    activity_from: datetime | None = Query(default=None),
    activity_to: datetime | None = Query(default=None),
    mode: TrainingSessionMode | None = Query(default=None),
    source: str | None = Query(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    ),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    scope = training_scope_for(
        current_user,
        requested_user_id=user_id or x_user_id,
        requested_team_id=team_id or x_team_id,
    )
    try:
        sessions, total = await svc.list_sessions_page(
            skip=skip,
            limit=limit,
            user_id=scope.user_id,
            team_id=scope.team_id,
            scenario_template_id=scenario_template_id,
            query=query,
            activity_from=activity_from,
            activity_to=activity_to,
            mode=mode,
            source=source,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response.headers["X-Total-Count"] = str(total)
    return success_response(data=[_session_to_dict(session) for session in sessions])


@router.get("/scenario-progress", summary="List scenario training progress")
@router.get("/sessions/scenario-progress", include_in_schema=False)
async def list_scenario_training_progress(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    scope = training_scope_for(
        current_user,
        requested_user_id=user_id or x_user_id,
        requested_team_id=team_id or x_team_id,
    )
    progress, total = await svc.list_scenario_progress_page(
        skip=skip,
        limit=limit,
        user_id=scope.user_id,
        team_id=scope.team_id,
        access_scope=_training_session_access_scope_for_current_user(current_user),
    )
    response.headers["X-Total-Count"] = str(total)
    return success_response(data=[item.model_dump(mode="json") for item in progress])


@router.get(
    "/scenario-progress/summary",
    summary="Get scenario training progress summary",
)
async def get_scenario_training_progress_summary(
    user_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    scope = training_scope_for(
        current_user,
        requested_user_id=user_id or x_user_id,
        requested_team_id=team_id or x_team_id,
    )
    summary = await svc.get_scenario_progress_summary(
        user_id=scope.user_id,
        team_id=scope.team_id,
        access_scope=_training_session_access_scope_for_current_user(current_user),
    )
    return success_response(data=summary.model_dump(mode="json"))


@router.get(
    "/scenario-progress/competency-radar",
    summary="Get scoped training competency radar",
    response_model=None,
)
async def get_training_competency_radar(
    user_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    sample_size: int = Query(default=10, ge=1, le=50),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_team_id: str | None = Header(default=None, alias="X-Team-Id"),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    scope = training_scope_for(
        current_user,
        requested_user_id=user_id or x_user_id,
        requested_team_id=team_id or x_team_id,
    )
    radar: TrainingCompetencyRadarDTO = await svc.get_competency_radar(
        user_id=scope.user_id,
        team_id=scope.team_id,
        access_scope=_training_session_access_scope_for_current_user(current_user),
        recent_limit=sample_size,
    )
    return success_response(data=radar.model_dump(mode="json"))


@router.get("/sessions/{session_id}", summary="Get a Training Studio session")
async def get_training_session(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    return success_response(data=_session_to_dict(session))


@router.post(
    "/sessions/{session_id}/conversation/messages/{message_public_id}/fork",
    summary="Fork a message-tree training session",
)
async def fork_training_conversation(
    session_id: str,
    message_public_id: str,
    body: ForkConversationDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session_scope = _training_session_access_scope_for_current_user(current_user)
    source_session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    conversation_id = _message_tree_conversation_id_for_session(source_session)
    conversation_scope = owned_metadata_scope_for_current_user(current_user)
    source_conversation = await conversation_svc.get_conversation(
        conversation_id,
        metadata_scope=conversation_scope,
    )
    source_training_session_id = str(
        source_conversation.metadata.get("trainingSessionId")
        or source_conversation.metadata.get("training_session_id")
        or ""
    ).strip()
    if source_training_session_id != session_id:
        raise HTTPException(
            status_code=409,
            detail="Conversation is not bound to the requested training session",
        )

    try:
        forked_session = await svc.fork_session(
            session_id,
            access_scope=session_scope,
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc

    fork_body = body.model_copy(
        update={
            "metadata": _training_fork_metadata(
                body.metadata,
                source_session_id=session_id,
                forked_session_id=forked_session.session_id,
            )
        }
    )
    try:
        forked = await conversation_svc.fork_conversation(
            conversation_id,
            message_public_id,
            fork_body,
            metadata_scope=conversation_scope,
        )
    except Exception:
        with suppress(Exception):
            await svc.delete_session(
                forked_session.session_id,
                access_scope=session_scope,
            )
        raise

    forked_room_id = f"{ConversationTrainingConversationAdapter.provider}:{forked.conversation.id}"
    try:
        started_session = await svc.start_session(
            forked_session.session_id,
            room_id=forked_room_id,
            metadata=forked.conversation.metadata,
            access_scope=session_scope,
        )
        if forked.messages:
            started_session = await svc.record_turns(
                forked_session.session_id,
                count=len(forked.messages),
                access_scope=session_scope,
            )
    except Exception:
        with suppress(Exception):
            await conversation_svc.delete_conversation(
                forked.conversation.id,
                metadata_scope=conversation_scope,
            )
        with suppress(Exception):
            await svc.delete_session(
                forked_session.session_id,
                access_scope=session_scope,
            )
        raise

    return success_response(data=_forked_training_conversation_to_dict(started_session, forked))


@router.delete("/sessions/{session_id}", summary="Delete a Training Studio session")
async def delete_training_session(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        await svc.delete_session(
            session_id,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    return success_response(data={"session_id": session_id, "deleted": True})


@router.post("/sessions/{session_id}/start", summary="Start or bind a Training Studio session")
async def start_training_session(
    session_id: str,
    body: StartTrainingSessionDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    persona_editor: PersonaEditorService = Depends(get_persona_editor_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_runtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
):
    access_scope = _training_session_access_scope_for_current_user(current_user)
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )

    if _requests_message_tree_runtime(body):
        if body.runtime_persona is not None:
            raise HTTPException(
                status_code=422,
                detail="runtime_persona is only available for room-backed training sessions",
            )
        if body.opening_message is not None:
            raise HTTPException(
                status_code=422,
                detail="opening_message is only available for room-backed training sessions",
            )
        mode = str(getattr(session.mode, "value", session.mode)).strip().lower()
        if mode != "text":
            raise HTTPException(
                status_code=422,
                detail="conversation_message_tree runtime is only available for text sessions",
            )
        if body.room_id is not None and str(body.room_id).strip():
            raise HTTPException(
                status_code=422,
                detail="room_id cannot be provided when starting a conversation_message_tree session",
            )
        orchestrator = TrainingCoreOrchestrator(
            session_service=svc,
            conversation_adapter=ConversationTrainingConversationAdapter(uow_factory),
        )
        try:
            started = await orchestrator.start_existing_session(
                session_id,
                access_scope=access_scope,
            )
        except PermissionError as exc:
            raise _session_access_denied(exc) from exc
        except ValueError as exc:
            raise _not_found_if_missing(exc) from exc
        return success_response(data=_started_training_session_to_dict(started))

    room_id = str(body.room_id).strip() if body.room_id is not None else ""
    if room_id and body.runtime_persona is not None:
        raise HTTPException(
            status_code=422,
            detail="runtime_persona cannot be provided when binding an existing room",
        )
    if body.persona_ids and body.runtime_persona is not None:
        raise HTTPException(
            status_code=422,
            detail="runtime_persona cannot be combined with persona_ids",
        )
    if not room_id:
        persona_ids = list(body.persona_ids)
        room_name = body.room_name
        if body.runtime_persona is not None:
            persona_ids = [_create_training_runtime_persona(body.runtime_persona, persona_editor)]
            room_name = room_name or f"Training: {body.runtime_persona.name.strip()}"
        if not persona_ids:
            raise HTTPException(
                status_code=422,
                detail="room_id, persona_ids, or runtime_persona is required",
            )
        room_name = room_name or f"Training: {session.task_config.role}"
        room = await chatroom_svc.create_room(
            CreateChatRoomDTO(
                name=room_name,
                type=body.room_type,
                persona_ids=persona_ids,
                scenario_id=body.scenario_id,
            ),
            access_scope=_stakeholder_room_scope_for_current_user(current_user),
        )
        room_id = str(room.id)
    elif not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only admins can bind an existing room to a training session",
        )

    try:
        started = await svc.start_session(
            session_id,
            room_id=room_id,
            access_scope=access_scope,
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    await _persist_training_opening_message(
        room_id=room_id,
        opening_message=body.opening_message,
        session_id=session_id,
        uow_factory=uow_factory,
    )
    return success_response(data=_session_to_dict(started))


@router.post("/sessions/{session_id}/complete", summary="Complete a Training Studio session")
async def complete_training_session(
    session_id: str,
    body: CompleteTrainingSessionDTO,
    background_tasks: BackgroundTasks,
    svc: TrainingSessionService = Depends(get_training_session_service),
    analysis_svc: AnalysisService = Depends(get_analysis_service),
    reader_svc: AnalysisReaderService = Depends(get_analysis_reader_service),
    growth_svc=Depends(get_growth_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_runtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    session_access_scope = _training_session_access_scope_for_current_user(current_user)
    completion_metadata: dict[str, object] = dict(body.metadata or {})

    if str(session.room_id or "").startswith(
        f"{ConversationTrainingConversationAdapter.provider}:"
    ):
        if not body.selected_tail_message_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "message_tree_selected_tail_required",
                    "status": "blocked",
                    "phase": "validate_selected_path",
                    "message": "selected_tail_message_id is required for message-tree completion",
                    "retryable": True,
                },
            )
        if body.report_id is not None or body.score_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Message-tree completion does not accept client report_id or score_id",
            )
        if not body.generate_report:
            raise HTTPException(
                status_code=422,
                detail="Message-tree completion requires server-generated evaluation and report",
            )
        if body.report_generation != "sync":
            raise HTTPException(
                status_code=422,
                detail="Message-tree completion currently supports synchronous report generation only",
            )
        if body.metadata:
            raise HTTPException(
                status_code=422,
                detail="Message-tree completion metadata is derived from the server-selected path",
            )
        completion_svc = MessageTreeTrainingCompletionService(
            uow_factory=uow_factory,
            session_service=svc,
            conversation_service=conversation_svc,
            analysis_service=analysis_svc,
            growth_service=growth_svc,
        )
        try:
            outcome = await completion_svc.complete(
                session_id,
                selected_tail_message_id=body.selected_tail_message_id,
                session_access_scope=session_access_scope,
                conversation_metadata_scope=owned_metadata_scope_for_current_user(current_user),
            )
        except PermissionError as exc:
            raise _session_access_denied(exc) from exc
        except MessageTreeCompletionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "message_tree_completion_conflict",
                    "status": "blocked",
                    "phase": "validate_selected_path",
                    "message": str(exc),
                    "retryable": True,
                },
            ) from exc
        except MessageTreeReportGenerationError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "message_tree_report_generation_failed",
                    "status": "failed",
                    "completionReport": exc.metadata,
                },
            ) from exc
        return success_response(data=_session_to_dict(outcome.session))

    if body.selected_tail_message_id is not None:
        raise HTTPException(
            status_code=422,
            detail="selected_tail_message_id is only available for message-tree sessions",
        )

    report_id = str(body.report_id).strip() if body.report_id is not None else ""
    report_generation = body.report_generation.strip().lower()
    background_report_room_id: int | None = None
    background_report_access_scope: StakeholderRoomAccessScope | None = None
    if body.generate_report and not report_id:
        if not session.room_id:
            raise HTTPException(
                status_code=400, detail="Session must be started before generating a report"
            )
        try:
            room_id = int(session.room_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Session room_id must be numeric to generate a report"
            ) from exc
        report_access_scope = _legacy_room_scope_for_accessible_training_session(
            session,
            current_user,
            room_id=room_id,
            operation="generate_report",
        )
        if report_generation == "background":
            completion_metadata["completionReport"] = _completion_report_pending_metadata()
            background_report_room_id = room_id
            background_report_access_scope = report_access_scope
        else:
            try:
                report = await analysis_svc.generate_report(
                    room_id,
                    access_scope=report_access_scope,
                )
            except (BusinessException, ValueError) as exc:
                logger.warning(
                    "training_session_completion_report_failed",
                    extra={
                        "session_id": session_id,
                        "room_id": session.room_id,
                        "error_type": type(exc).__name__,
                    },
                )
                completion_metadata["completionReport"] = _completion_report_failure_metadata(exc)
            except Exception as exc:
                logger.exception(
                    "training_session_completion_report_failed",
                    extra={"session_id": session_id, "room_id": session.room_id},
                )
                completion_metadata["completionReport"] = _completion_report_failure_metadata(exc)
            else:
                report_id = str(report.id)
                completion_metadata["completionReport"] = _completion_report_ready_metadata(
                    report.id,
                    generation="sync",
                )
                background_tasks.add_task(growth_svc.evaluate_competency, report.id)
    elif report_id:
        report_id = await _require_report_id_for_training_session(
            report_id,
            session=session,
            reader_svc=reader_svc,
            current_user=current_user,
        )
        completion_metadata["completionReport"] = _completion_report_ready_metadata(
            report_id,
            generation="explicit",
        )

    score_id = str(body.score_id).strip() if body.score_id is not None else None
    try:
        completed = await svc.complete_session(
            session_id,
            report_id=report_id or None,
            score_id=score_id,
            metadata=completion_metadata,
            access_scope=session_access_scope,
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    if background_report_room_id is not None and background_report_access_scope is not None:
        background_tasks.add_task(
            _generate_training_completion_report_background,
            session_id=session_id,
            room_id=background_report_room_id,
            session_access_scope=session_access_scope,
            room_access_scope=background_report_access_scope,
            svc=svc,
            analysis_svc=analysis_svc,
            growth_svc=growth_svc,
        )
    return success_response(data=_session_to_dict(completed))


@router.post("/sessions/{session_id}/fail", summary="Fail a Training Studio session")
async def fail_training_session(
    session_id: str,
    body: FailTrainingSessionDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    try:
        failed = await svc.fail_session(
            session_id,
            body.reason,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )
    except PermissionError as exc:
        raise _session_access_denied(exc) from exc
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    return success_response(data=_session_to_dict(failed))


@router.get("/sessions/{session_id}/report", summary="Get a Training Studio session report")
async def get_training_session_report(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
    reader_svc: AnalysisReaderService = Depends(get_analysis_reader_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )

    if not session.report_id:
        completion_report = message_tree_completion_report_metadata(session)
        if completion_report:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "training_session_report_not_ready",
                    "status": completion_report.get("status", "pending"),
                    "completionReport": completion_report,
                },
            )
        raise HTTPException(status_code=404, detail="Training session report not found")

    try:
        report_lookup_id = int(session.report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Training session report not found") from exc
    room_lookup_id = message_tree_analysis_room_id(session)
    if room_lookup_id is not None:
        completion_report = message_tree_completion_report_metadata(session)
        if str(completion_report.get("reportId") or "") != str(session.report_id):
            raise HTTPException(status_code=404, detail="Training session report not found")
        report_scope = legacy_training_session_room_scope(
            training_session_id=session.session_id,
            room_id=room_lookup_id,
            operation="message_tree_session_report",
        )
    else:
        try:
            room_lookup_id = _stakeholder_room_id_for_training_session(session)
        except ValueError as exc:
            raise HTTPException(
                status_code=404, detail="Training session report not found"
            ) from exc
        report_scope = _legacy_room_scope_for_accessible_training_session(
            session,
            current_user,
            room_id=room_lookup_id,
            operation="session_report",
        )
    report = await reader_svc.get_report(
        report_lookup_id,
        room_id=room_lookup_id,
        access_scope=report_scope,
    )
    if report is None or str(report.room_id) != str(room_lookup_id):
        raise HTTPException(status_code=404, detail="Training session report not found")
    return success_response(data=report.model_dump(mode="json"))


@router.get("/realtime/capabilities", summary="Get realtime provider capabilities")
async def get_realtime_capabilities(
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    return success_response(data=_realtime_capabilities_response())


@router.post(
    "/client-events",
    status_code=202,
    summary="Record Training Studio browser runtime events",
)
async def record_training_client_event(
    body: ClientRealtimeEventDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    event_type = _client_realtime_event_type(body.event_type)
    severity = _client_event_severity(body.severity)

    if not settings.CLIENT_EVENT_LOGGING_ENABLED:
        return success_response(
            data={
                "accepted": False,
                "eventType": event_type,
                "reason": "client_event_logging_disabled",
            }
        )

    training_session_id, room_id = await _resolve_client_event_training_scope(
        body,
        svc=svc,
        current_user=current_user,
    )
    payload = _safe_client_event_payload(body.payload)
    client_event_provider = _coerce_optional_text(body.provider) or "pipecat"
    client_event = {
        "eventType": event_type,
        "eventCategory": _coerce_optional_text(body.event_category) or "realtime_voice",
        "severity": severity,
        "trainingSessionId": training_session_id,
        "roomId": room_id,
        "provider": client_event_provider,
        "realtimeRuntime": realtime_runtime_for_provider(client_event_provider),
        "realtimeProfile": _coerce_optional_text(body.realtime_profile),
        "errorCategory": _coerce_optional_text(body.error_category),
        "message": _truncate_client_event_text(body.message) if body.message else None,
        "payload": payload,
        "userId": current_user.user_id,
        "teamId": current_user.team_id,
        "systemRole": current_user.system_role,
    }
    log_kwargs = {"extra": {"client_event": client_event}}
    if severity == "error":
        logger.error("Training Studio client realtime event", **log_kwargs)
    elif severity == "warning":
        logger.warning("Training Studio client realtime event", **log_kwargs)
    elif severity == "debug":
        logger.debug("Training Studio client realtime event", **log_kwargs)
    else:
        logger.info("Training Studio client realtime event", **log_kwargs)

    return success_response(
        data={
            "accepted": True,
            "eventType": event_type,
            "trainingSessionId": training_session_id,
            "roomId": room_id,
            "loggingScope": "training_realtime_voice",
        }
    )


@router.get("/sessions/{session_id}/guidance", summary="Get Training Studio live guidance")
async def get_training_guidance(
    session_id: str,
    message_limit: int = Query(50, ge=1, le=200),
    selected_tail_message_id: str | None = Query(default=None, min_length=1, max_length=160),
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await _generate_training_guidance(
        session_id,
        TrainingGuidanceRequestDTO(
            message_limit=message_limit,
            selected_tail_message_id=selected_tail_message_id,
        ),
        svc=svc,
        chatroom_svc=chatroom_svc,
        conversation_svc=conversation_svc,
        guidance_svc=guidance_svc,
        current_user=current_user,
    )
    return success_response(data=data)


@router.post("/sessions/{session_id}/guidance", summary="Request Training Studio live guidance")
async def request_training_guidance(
    session_id: str,
    body: TrainingGuidanceRequestDTO,
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await _generate_training_guidance(
        session_id,
        body,
        svc=svc,
        chatroom_svc=chatroom_svc,
        conversation_svc=conversation_svc,
        guidance_svc=guidance_svc,
        current_user=current_user,
    )
    data["persistence"] = await _persist_generated_message_tree_guidance(
        session_id,
        data,
        svc=svc,
        current_user=current_user,
    )
    return success_response(data=data)


@router.get(
    "/sessions/{session_id}/guidance-history",
    summary="Get persisted selected-path Training Studio guidance",
)
async def get_training_guidance_history(
    session_id: str,
    selected_tail_message_id: str = Query(..., min_length=1, max_length=160),
    svc: TrainingSessionService = Depends(get_training_session_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    await _message_tree_guidance_turns(
        session_id,
        session,
        TrainingGuidanceRequestDTO(
            selected_tail_message_id=selected_tail_message_id,
        ),
        conversation_svc=conversation_svc,
        current_user=current_user,
    )
    return success_response(
        data=read_selected_path_guidance_history(
            session.task_config.metadata,
            selected_tail_message_id=selected_tail_message_id,
        )
    )


@router.post(
    "/sessions/{session_id}/guidance-events",
    status_code=201,
    summary="Persist Training Studio live guidance events",
)
async def persist_training_guidance_events(
    session_id: str,
    body: PersistTrainingGuidanceEventsDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
):
    room_id = await _require_guidance_persistence_room_id(
        session_id,
        svc=svc,
        current_user=current_user,
    )
    batch_id = str(uuid4())
    persisted_at = datetime.now(UTC).isoformat()
    persisted: list[MessageDTO] = []

    for index, event in enumerate(body.events):
        event_payload = event.model_dump(mode="json", exclude_none=True)
        metadata: dict[str, object] = {
            "schemaVersion": 1,
            "source": _TRAINING_GUIDANCE_MESSAGE_SOURCE,
            "eventKind": "guidance",
            "trainingSessionId": session_id,
            "roomId": room_id,
            "batchId": batch_id,
            "batchIndex": index,
            "persistedAt": persisted_at,
            "guidanceSource": body.source,
            "reason": body.reason,
            "windowSize": body.window_size,
            "totalTurnCount": body.total_turn_count,
            "trigger": body.trigger or {},
            "clientMetadata": dict(body.metadata),
            "guidance": event_payload,
        }
        message = await _persist_realtime_message(
            room_id,
            _training_guidance_event_content(event),
            uow_factory=uow_factory,
            metadata=metadata,
            sender_type="system",
            sender_id=_TRAINING_GUIDANCE_SENDER_ID,
        )
        persisted.append(message)

    return success_response(
        data={
            "batch_id": batch_id,
            "saved_count": len(persisted),
            "messages": [message.model_dump(mode="json") for message in persisted],
        }
    )


@router.get(
    "/sessions/{session_id}/guidance/stream", summary="Stream Training Studio live guidance"
)
async def stream_training_guidance(
    session_id: str,
    request: Request,
    message_limit: int = Query(50, ge=1, le=200),
    poll_interval_ms: int = Query(1000, ge=250, le=10000),
    max_events: int | None = Query(default=None, ge=1, le=50, include_in_schema=False),
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    body = TrainingGuidanceRequestDTO(message_limit=message_limit)
    room_id = await _require_active_guidance_room_id(session_id, svc, current_user)
    initial_data = await _generate_training_guidance(
        session_id,
        body,
        svc=svc,
        chatroom_svc=chatroom_svc,
        conversation_svc=conversation_svc,
        guidance_svc=guidance_svc,
        current_user=current_user,
    )

    async def event_generator():
        sent_guidance_events = 0
        last_signature = _guidance_payload_signature(initial_data)
        queue = room_event_bus.subscribe(room_id)

        try:
            yield _format_sse(
                "guidance_snapshot",
                _guidance_stream_payload(initial_data, reason="initial"),
            )
            sent_guidance_events += 1
            if max_events is not None and sent_guidance_events >= max_events:
                return

            while True:
                if await request.is_disconnected():
                    return
                try:
                    room_event, room_event_data = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if room_event != "message":
                    continue
                try:
                    data = await _generate_training_guidance(
                        session_id,
                        body,
                        svc=svc,
                        chatroom_svc=chatroom_svc,
                        conversation_svc=conversation_svc,
                        guidance_svc=guidance_svc,
                        current_user=current_user,
                    )
                except HTTPException as exc:
                    yield _format_sse(
                        "guidance_error", {"status_code": exc.status_code, "detail": exc.detail}
                    )
                    return

                signature = _guidance_payload_signature(data)
                if signature == last_signature:
                    continue
                last_signature = signature
                yield _format_sse(
                    "guidance_snapshot",
                    _guidance_stream_payload(
                        data,
                        reason="room_message",
                        trigger=_guidance_trigger_from_room_event(room_event, room_event_data),
                    ),
                )
                sent_guidance_events += 1
                if max_events is not None and sent_guidance_events >= max_events:
                    return
        finally:
            room_event_bus.unsubscribe(room_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/catalog", summary="Get Training Studio catalog options")
async def get_catalog(
    svc: TrainingCatalogService = Depends(get_training_catalog_service),
):
    return success_response(data=svc.get_catalog().model_dump(mode="json"))


@router.get("/scenario-templates", summary="Get scenario training templates")
async def get_scenario_templates(
    scenario_config_svc: TrainingScenarioConfigService = Depends(
        get_training_scenario_config_service
    ),
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    config = scenario_config_svc.get_config()
    templates = _scenario_templates_from_config(config)
    return success_response(data=[template.model_dump(mode="json") for template in templates])


@router.post(
    "/tool-consumers/review-assistant/material-review",
    summary="Compare a training session against scoped material snippets",
)
async def create_review_assistant_material_review(
    body: MaterialReviewRequestDTO,
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    file_assets: FileAssetApplicationService = Depends(get_file_asset_service),
    session_svc: TrainingSessionService = Depends(get_training_session_service),
    reader_svc: AnalysisReaderService = Depends(get_analysis_reader_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    llm: LLMPort | None = Depends(get_stakeholder_llm_client),
    current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    material_ids = normalize_material_review_ids(body.material_ids, body.selected_material_ids)
    if not material_ids:
        raise HTTPException(status_code=422, detail="material_ids is required")

    session = await _require_material_review_training_session(
        body.session_id,
        svc=session_svc,
        current_user=current_user,
    )

    material_service = _training_material_tool_consumer(file_assets)
    material_scope = _training_material_tool_scope_for_current_user(current_user)
    materials = []
    try:
        for material_id in material_ids:
            materials.append(
                await material_service.get_material(
                    material_id,
                    metadata_scope=material_scope,
                    include_content_excerpt=True,
                )
            )
    except FileAssetNotFoundException as exc:
        raise HTTPException(status_code=404, detail="Training material not found") from exc
    except DomainValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc

    report_context, replay_context = await asyncio.gather(
        _material_review_report_context(
            session,
            reader_svc=reader_svc,
            current_user=current_user,
        ),
        _material_review_replay_context(
            session,
            chatroom_svc=chatroom_svc,
            current_user=current_user,
        ),
    )
    review = await TrainingMaterialReviewService().build_review_async(
        session=session,
        materials=materials,
        requested_material_ids=material_ids,
        report=report_context,
        replay=replay_context,
        async_llm_callback=MaterialReviewLLMAdapter(llm) if llm is not None else None,
    )
    return success_response(data=review.model_dump(mode="json"))


@router.get(
    "/tool-consumers/training-materials",
    summary="List scoped training materials for narrow tool consumers",
)
async def list_training_material_tool_consumer_materials(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    include_content_excerpt: bool = Query(False),
    file_assets: FileAssetApplicationService = Depends(get_file_asset_service),
    current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    service = _training_material_tool_consumer(file_assets)
    try:
        materials = await service.list_materials(
            metadata_scope=_training_material_tool_scope_for_current_user(current_user),
            skip=skip,
            limit=limit,
            include_content_excerpt=include_content_excerpt,
        )
    except DomainValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return success_response(data=materials.model_dump(mode="json"))


@router.get(
    "/tool-consumers/training-materials/{asset_id}",
    summary="Get a scoped training material summary for narrow tool consumers",
)
async def get_training_material_tool_consumer_material(
    asset_id: int,
    include_content_excerpt: bool = Query(False),
    file_assets: FileAssetApplicationService = Depends(get_file_asset_service),
    current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    service = _training_material_tool_consumer(file_assets)
    try:
        material = await service.get_material(
            asset_id,
            metadata_scope=_training_material_tool_scope_for_current_user(current_user),
            include_content_excerpt=include_content_excerpt,
        )
    except FileAssetNotFoundException as exc:
        raise HTTPException(status_code=404, detail="Training material not found") from exc
    except DomainValidationException as exc:
        raise HTTPException(status_code=422, detail=exc.message) from exc
    return success_response(data=material.model_dump(mode="json"))


@router.get("/llm-registry", summary="Get text LLM provider and model registry")
async def get_llm_registry(
    llm: LLMPort | None = Depends(get_stakeholder_llm_client),
    conversation_svc: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    agent_configs = await _agent_config_inventory_for_user(conversation_svc, current_user)
    return success_response(
        data=_llm_registry_response(
            llm,
            agent_configs=agent_configs,
            tool_configs=settings.capability_inventory.tool_configs,
            mcp_servers=settings.capability_inventory.mcp_servers,
        )
    )


@router.get("/voice-config", summary="Get voice preference configuration")
async def get_voice_config(
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    return success_response(data=_voice_config_response().model_dump(mode="json"))


@router.put("/voice-config", summary="Save voice preference configuration")
async def save_voice_config(
    body: VoicePreferenceUpdateDTO,
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader")),
):
    current_llm = settings.llm
    llm_api_key = current_llm.api_key
    new_llm_key = _clean_config_text(body.llm_api_key)
    if body.clear_llm_api_key:
        llm_api_key = None
    elif new_llm_key:
        llm_api_key = new_llm_key
    llm_provider = _normalized_provider(
        body.llm_provider,
        current_llm.provider,
        allowed=_LLM_PROVIDERS,
        field_name="llm_provider",
    )
    llm_base_url = (
        _clean_optional_config_text(body.llm_base_url)
        if body.llm_base_url is not None
        else current_llm.base_url
    )
    llm_default_model = _required_config_text(
        body.llm_default_model,
        current_llm.default_model,
        "llm_default_model",
    )
    llm_wire_api = _normalized_provider(
        body.llm_wire_api,
        current_llm.wire_api,
        allowed={"chat_completions", "responses"},
        field_name="llm_wire_api",
    )

    current_voice = settings.voice
    tts_provider = _normalized_provider(
        body.tts_provider,
        current_voice.tts_provider,
        allowed=_VOICE_TTS_PROVIDERS,
        field_name="tts_provider",
    )
    stt_provider = _normalized_provider(
        body.stt_provider,
        current_voice.stt_provider,
        allowed=_VOICE_STT_PROVIDERS,
        field_name="stt_provider",
    )

    tts_base_url = (
        _clean_optional_config_text(body.tts_base_url)
        if body.tts_base_url is not None
        else current_voice.tts_base_url
    )
    stt_base_url = (
        _clean_optional_config_text(body.stt_base_url)
        if body.stt_base_url is not None
        else current_voice.stt_base_url
    )
    tts_model = _required_config_text(body.tts_model, current_voice.tts_model, "tts_model")
    stt_model = _required_config_text(body.stt_model, current_voice.stt_model, "stt_model")

    tts_api_key = current_voice.tts_api_key
    new_tts_key = _clean_config_text(body.tts_api_key)
    if body.clear_tts_api_key:
        tts_api_key = None
    elif new_tts_key:
        tts_api_key = new_tts_key

    stt_api_key = current_voice.stt_api_key
    new_stt_key = _clean_config_text(body.stt_api_key)
    if new_stt_key:
        stt_api_key = new_stt_key
    elif body.clear_stt_api_key:
        stt_api_key = None
    elif body.stt_use_tts_api_key and _voice_stt_provider_can_use_shared_key(stt_provider):
        stt_api_key = tts_api_key or llm_api_key

    realtime_provider = _normalized_provider(
        body.realtime_provider,
        getattr(settings, "REALTIME_PROVIDER", "openai"),
        allowed=_REALTIME_PROVIDERS,
        field_name="realtime_provider",
    )
    realtime_base_url = (
        _clean_optional_config_text(body.realtime_base_url)
        if body.realtime_base_url is not None
        else settings.REALTIME_BASE_URL
    )
    realtime_openai_api_key = settings.REALTIME_OPENAI_API_KEY
    realtime_api_key = settings.REALTIME_API_KEY
    new_realtime_key = _clean_config_text(body.realtime_api_key)
    if body.clear_realtime_api_key:
        if realtime_provider in {"openai", "openai.realtime"}:
            realtime_openai_api_key = None
        else:
            realtime_api_key = None
    elif new_realtime_key:
        if realtime_provider in {"openai", "openai.realtime"}:
            realtime_openai_api_key = new_realtime_key
        else:
            realtime_api_key = new_realtime_key

    realtime_model = _required_config_text(
        body.realtime_model,
        settings.REALTIME_OPENAI_MODEL,
        "realtime_model",
    )
    realtime_voice = _required_config_text(
        body.realtime_voice,
        settings.REALTIME_OPENAI_VOICE,
        "realtime_voice",
    )
    realtime_transcription_model = (
        _clean_config_text(body.realtime_transcription_model)
        if body.realtime_transcription_model is not None
        else settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL
    )
    env_updates: dict[str, str | None] = {
        "LLM__PROVIDER": llm_provider,
        "LLM__BASE_URL": llm_base_url,
        "LLM__DEFAULT_MODEL": llm_default_model,
        "LLM__WIRE_API": llm_wire_api,
        "VOICE__TTS_PROVIDER": tts_provider,
        "VOICE__TTS_BASE_URL": tts_base_url,
        "VOICE__TTS_MODEL": tts_model,
        "VOICE__STT_PROVIDER": stt_provider,
        "VOICE__STT_BASE_URL": stt_base_url,
        "VOICE__STT_MODEL": stt_model,
        "REALTIME_PROVIDER": realtime_provider,
        "REALTIME_BASE_URL": realtime_base_url,
        "REALTIME_OPENAI_MODEL": realtime_model,
        "REALTIME_OPENAI_VOICE": realtime_voice,
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL": realtime_transcription_model,
    }
    if body.clear_llm_api_key or new_llm_key:
        env_updates["LLM__API_KEY"] = llm_api_key
    if body.clear_tts_api_key or new_tts_key:
        env_updates["VOICE__TTS_API_KEY"] = tts_api_key
    stt_uses_shared_key = (
        body.stt_use_tts_api_key
        and _voice_stt_provider_can_use_shared_key(stt_provider)
        and not new_stt_key
        and not body.clear_stt_api_key
    )
    if stt_uses_shared_key or body.clear_stt_api_key or new_stt_key:
        env_updates["VOICE__STT_API_KEY"] = "" if stt_uses_shared_key else stt_api_key
    if body.clear_realtime_api_key or new_realtime_key:
        if realtime_provider in {"openai", "openai.realtime"}:
            env_updates["REALTIME_OPENAI_API_KEY"] = realtime_openai_api_key
        else:
            env_updates["REALTIME_API_KEY"] = realtime_api_key

    try:
        _write_env_file_values(env_updates)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write backend .env: {exc}") from exc

    settings.llm = LLMSettings(
        provider=llm_provider,
        api_key=llm_api_key,
        base_url=llm_base_url,
        wire_api=llm_wire_api,
        default_model=llm_default_model,
        temperature=current_llm.temperature,
        max_tokens=current_llm.max_tokens,
        timeout=current_llm.timeout,
        max_retries=current_llm.max_retries,
        user_agent=current_llm.user_agent,
    )
    settings.voice = VoiceSettings(
        tts_provider=tts_provider,
        tts_api_key=tts_api_key,
        tts_base_url=tts_base_url,
        tts_model=tts_model,
        stt_provider=stt_provider,
        stt_api_key=stt_api_key,
        stt_base_url=stt_base_url,
        stt_model=stt_model,
    )
    if not settings.voice.stt_api_key and _voice_stt_provider_can_use_shared_key(
        settings.voice.stt_provider
    ):
        settings.voice.stt_api_key = settings.voice.tts_api_key or settings.llm.api_key
    if not settings.voice.stt_base_url and _voice_stt_provider_can_use_shared_key(
        settings.voice.stt_provider
    ):
        settings.voice.stt_base_url = settings.llm.base_url
    settings.REALTIME_PROVIDER = realtime_provider
    settings.REALTIME_BASE_URL = realtime_base_url
    settings.REALTIME_OPENAI_API_KEY = realtime_openai_api_key
    settings.REALTIME_API_KEY = realtime_api_key
    settings.REALTIME_OPENAI_MODEL = realtime_model
    settings.REALTIME_OPENAI_VOICE = realtime_voice
    settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL = realtime_transcription_model

    try:
        await _reload_llm_client()
        await _reload_voice_clients()
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Configuration saved but reload failed: {exc}"
        ) from exc

    return success_response(
        data=_voice_config_response().model_dump(mode="json"),
        message="Configuration saved",
    )


@router.get("/scenario-config", summary="Get scenario configuration state")
async def get_scenario_config(
    svc: TrainingScenarioConfigService = Depends(get_training_scenario_config_service),
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    config = svc.get_config()
    return success_response(data=config.model_dump(mode="json", by_alias=True, exclude_none=True))


@router.put("/scenario-config", summary="Save scenario configuration state")
async def save_scenario_config(
    body: ScenarioConfigStateDTO,
    svc: TrainingScenarioConfigService = Depends(get_training_scenario_config_service),
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader")),
):
    config = svc.save_config(body)
    return success_response(data=config.model_dump(mode="json", by_alias=True, exclude_none=True))


@router.get("/rubrics/default", summary="Get default rubric weights")
async def get_default_rubric(
    category: str = Query(ScenarioCategory.INTERVIEW.value),
    svc: TrainingCatalogService = Depends(get_training_catalog_service),
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    try:
        rubric = svc.get_default_rubric_weights(category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=rubric.model_dump(mode="json"))


@router.post("/task-config", summary="Normalize a Training Studio task configuration")
async def create_training_task_config(
    body: TrainingTaskConfigDTO,
    svc: TrainingCatalogService = Depends(get_training_catalog_service),
):
    try:
        config = svc.create_training_task_config(body)
    except (DomainValidationException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=config.model_dump(mode="json"))


@router.post("/storybank/entries", status_code=201, summary="Register a reusable story")
async def register_storybank_entry(
    body: StoryBankRegisterDTO,
    svc: StoryBankService = Depends(get_storybank_service),
):
    try:
        entry = svc.extract_and_register(
            body.answer_text,
            scenario_category=body.scenario_category,
            tags=body.tags or None,
        )
    except (DomainValidationException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=_storybank_entry_to_dict(entry))


@router.get("/storybank/entries", summary="List reusable stories")
async def list_storybank_entries(
    scenario_category: str | None = None,
    svc: StoryBankService = Depends(get_storybank_service),
):
    try:
        entries = svc.list_entries(scenario_category=scenario_category)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=[_storybank_entry_to_dict(entry) for entry in entries])


@router.post("/video-answers", status_code=201, summary="Upload a recorded video answer")
async def upload_video_answer(
    request: Request,
    training_session_id: str = Query(..., min_length=1),
    room_id: int = Query(..., ge=1),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        training_session_id,
        svc=svc,
        current_user=current_user,
    )
    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400,
            detail="Training session must be active before uploading video answers",
        )
    bound_room_id = _coerce_optional_room_id(session.room_id)
    if bound_room_id is None:
        raise HTTPException(
            status_code=400,
            detail="Training session must be started before uploading video answers",
        )
    if room_id != bound_room_id:
        raise HTTPException(
            status_code=400,
            detail="room_id does not match the active training session",
        )

    content_type = _normalize_video_content_type(request.headers.get("content-type"))
    if not content_type.startswith("video/"):
        raise HTTPException(status_code=422, detail="Only video uploads are supported")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _VIDEO_MAX_BYTES:
                raise HTTPException(status_code=413, detail="Video answer is too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid content length") from exc

    data = await request.body()
    if not data:
        raise HTTPException(status_code=422, detail="Video answer is empty")
    if len(data) > _VIDEO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Video answer is too large")

    _VIDEO_ANSWER_DIR.mkdir(parents=True, exist_ok=True)
    original_filename = request.headers.get("x-filename")
    filename = f"{uuid4().hex}{_video_extension(original_filename, content_type)}"
    path = _VIDEO_ANSWER_DIR / filename
    metadata = {
        "filename": filename,
        "trainingSessionId": training_session_id,
        "roomId": room_id,
        "userId": current_user.user_id,
        "systemRole": current_user.system_role,
        "teamId": current_user.team_id,
        "mimeType": content_type,
        "size": len(data),
        "originalFilename": original_filename,
        "createdAt": datetime.now(UTC).isoformat(),
    }
    await asyncio.to_thread(_write_video_answer_record, path, data=data, metadata=metadata)
    return success_response(
        data={
            "filename": filename,
            "url": _build_video_answer_url(
                filename,
                training_session_id=training_session_id,
                room_id=room_id,
            ),
            "mimeType": content_type,
            "size": len(data),
        }
    )


@router.get("/video-answers/{filename}", summary="Read a recorded video answer")
async def read_video_answer(
    filename: str,
    training_session_id: str = Query(..., min_length=1),
    room_id: int = Query(..., ge=1),
    svc: TrainingSessionService = Depends(get_training_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    metadata = _load_video_answer_metadata(filename)
    if _coerce_optional_text(metadata.get("trainingSessionId")) != training_session_id:
        raise HTTPException(status_code=404, detail="Video answer not found")
    stored_room_id = _coerce_optional_room_id(metadata.get("roomId"))
    if stored_room_id != room_id:
        raise HTTPException(status_code=404, detail="Video answer not found")
    session = await _require_accessible_training_session(
        training_session_id,
        svc=svc,
        current_user=current_user,
    )
    session_room_id = _coerce_optional_room_id(session.room_id)
    if session_room_id != room_id:
        raise HTTPException(status_code=404, detail="Video answer not found")
    path = _resolve_video_answer_file(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video answer not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.websocket("/realtime")
async def realtime_training_session(
    websocket: WebSocket,
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
    pipeline_factory: RealtimePipelineFactory = Depends(get_training_realtime_pipeline_factory),
):
    """Minimal bidirectional realtime session endpoint for audio event wiring."""

    await websocket.accept()
    query_session_id, query_room_id = _query_binding(websocket)
    provider = _query_realtime_provider(websocket)
    realtime_profile = _query_realtime_profile(websocket)
    input_sample_rate = _query_realtime_input_sample_rate(websocket, profile=realtime_profile)
    logger.info(
        "Training realtime websocket accepted",
        extra={
            "realtime_session": dict(
                sanitize_realtime_public_value(
                    {
                        "provider": provider,
                        "runtime": realtime_runtime_for_provider(provider),
                        "realtimeProfile": realtime_profile,
                        "queryTrainingSessionId": query_session_id,
                        "queryRoomId": query_room_id,
                        "inputSampleRate": input_sample_rate,
                        "userId": current_user.user_id,
                        "teamId": current_user.team_id,
                    }
                )
                or {}
            )
        },
    )
    session = RealtimeSession(session_id=query_session_id)
    binding: tuple[str, int] | None = None
    pipeline_runner: RealtimePipelineSessionRunner | None = None

    async def _ensure_pipeline_runner(active_binding: tuple[str, int]) -> None:
        nonlocal pipeline_runner
        if pipeline_runner is not None:
            return
        adapter = pipeline_factory(provider)
        if adapter is None:
            raise HTTPException(
                status_code=503,
                detail=_realtime_pipeline_unavailable_detail(provider),
            )
        sink = _WebSocketTrainingTranscriptSink(
            websocket=websocket,
            session=session,
            training_session_id=active_binding[0],
            room_id=active_binding[1],
            svc=svc,
            uow_factory=uow_factory,
            access_scope=_training_session_access_scope_for_current_user(current_user),
        )

        async def _relay_pipeline_event(payload: Mapping[str, Any]) -> None:
            event_type = _pipeline_event_type(payload)
            if event_type == "audio.output":
                await _send_pipeline_audio_output_event(
                    websocket=websocket,
                    session=session,
                    payload=payload,
                )
            elif event_type == "training.live_guidance.triggered":
                await _send_wire_event(
                    websocket,
                    "training.live_guidance.triggered",
                    session,
                    _pipeline_realtime_event_payload(payload),
                )
            elif event_type:
                await _send_wire_event(
                    websocket,
                    event_type,
                    session,
                    _pipeline_realtime_event_payload(payload),
                )

        runner = RealtimePipelineSessionRunner(
            adapter=adapter,
            transcript_sink=sink,
            event_sink=_relay_pipeline_event,
        )
        voice_context = await _build_realtime_voice_context(
            active_binding,
            provider=provider,
            realtime_profile=realtime_profile,
            svc=svc,
            uow_factory=uow_factory,
            current_user=current_user,
        )
        pipeline_metadata = _realtime_pipeline_metadata(
            provider,
            active_binding,
            profile=realtime_profile,
            input_sample_rate=input_sample_rate,
        )
        logger.info(
            "Training realtime pipeline starting",
            extra={
                "realtime_session": dict(
                    sanitize_realtime_public_value(
                        {
                            "provider": provider,
                            "runtime": realtime_runtime_for_provider(provider),
                            "realtimeProfile": pipeline_metadata.get("realtimeProfile")
                            or realtime_profile,
                            "trainingSessionId": active_binding[0],
                            "roomId": active_binding[1],
                            "inputSampleRate": pipeline_metadata.get("inputSampleRate"),
                            "outputSampleRate": pipeline_metadata.get("outputSampleRate"),
                            "inputAudioFormat": pipeline_metadata.get("inputAudioFormat"),
                            "outputAudioFormat": pipeline_metadata.get("outputAudioFormat"),
                            "model": settings.REALTIME_OPENAI_MODEL,
                            "voice": _realtime_voice_for_provider(provider),
                            "voiceIgnored": bool(
                                _coerce_optional_text(settings.REALTIME_OPENAI_VOICE)
                                and _realtime_voice_for_provider(provider) is None
                            ),
                            "baseUrl": settings.REALTIME_BASE_URL,
                            "apiKeyConfigured": (
                                bool(settings.REALTIME_API_KEY)
                                if _uses_volcengine_doubao_realtime(provider)
                                else bool(_openai_realtime_api_key())
                            ),
                        }
                    )
                    or {}
                )
            },
        )
        await runner.start(
            binding=RealtimeSessionBinding(
                training_session_id=active_binding[0],
                room_id=active_binding[1],
            ),
            provider=provider,
            realtime_session_id=session.session_id,
            task_goal=voice_context["task_goal"],
            rubric=voice_context["rubric"],
            recent_turns=voice_context["recent_turns"],
            runtime=realtime_runtime_for_provider(provider),
            model=settings.REALTIME_OPENAI_MODEL,
            voice=_realtime_voice_for_provider(provider),
            input_audio_format=settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
            output_audio_format=settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
            instructions=_default_realtime_agent_instructions(),
            context_metadata=voice_context["metadata"],
            config_metadata=pipeline_metadata,
        )
        pipeline_runner = runner

    try:
        if not _uses_supported_realtime_provider(provider):
            raise HTTPException(
                status_code=400,
                detail="Realtime voice provider is not wired to a backend runtime",
            )
        binding = await _resolve_realtime_binding(
            query_session_id,
            query_room_id,
            svc=svc,
            uow_factory=uow_factory,
            current_user=current_user,
        )
        if binding is not None:
            await _ensure_pipeline_runner(binding)
        start_metadata = _realtime_start_metadata(
            provider,
            binding,
            profile=realtime_profile,
            input_sample_rate=input_sample_rate,
        )
        await _send_event(websocket, session.start(start_metadata))
        await _send_event(websocket, session.listen())
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                return
            if raw.get("bytes") is not None:
                audio_bytes = raw["bytes"] or b""
                if pipeline_runner is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Realtime session must be bound before audio input",
                    )
                audio_event = session.receive_audio(audio_bytes, "audio/pcm")
                await pipeline_runner.append_audio(
                    RealtimeAudioChunk(
                        data=audio_bytes,
                        mime_type="audio/pcm",
                        sequence=session.input_sequence,
                        metadata=_realtime_audio_chunk_metadata(
                            provider=provider,
                            profile=realtime_profile,
                            input_sample_rate=input_sample_rate,
                        ),
                    )
                )
                pipeline_runner.raise_if_failed()
                await _send_event(websocket, audio_event)
                continue

            text = raw.get("text")
            if text is None:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await _send_event(websocket, session.fail("Invalid JSON frame", "INVALID_JSON"))
                break

            event_type = payload.get("type")
            if event_type == "session.configure":
                configured = await _resolve_realtime_binding(
                    *_configure_binding(payload),
                    svc=svc,
                    uow_factory=uow_factory,
                    current_user=current_user,
                )
                if configured is None:
                    await _send_wire_event(
                        websocket,
                        "session.configured",
                        session,
                        {"bound": False},
                    )
                    continue
                if binding is not None and configured != binding:
                    raise HTTPException(status_code=400, detail="Realtime session is already bound")
                binding = configured
                session.session_id = configured[0]
                await _ensure_pipeline_runner(binding)
                await _send_wire_event(
                    websocket,
                    "session.configured",
                    session,
                    {"bound": True, "trainingSessionId": configured[0], "roomId": configured[1]},
                )
            elif event_type == "session.start":
                await _send_event(websocket, session.listen())
            elif event_type == "audio.input":
                audio = payload.get("audio", "")
                try:
                    audio_bytes = (
                        base64.b64decode(audio, validate=True)
                        if isinstance(audio, str) and audio
                        else b""
                    )
                except (binascii.Error, ValueError):
                    await _send_event(
                        websocket, session.fail("Invalid base64 audio frame", "INVALID_AUDIO")
                    )
                    break
                if pipeline_runner is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Realtime session must be bound before audio input",
                    )
                mime_type = _coerce_optional_text(payload.get("mimeType"))
                audio_event = session.receive_audio(audio_bytes, mime_type)
                await pipeline_runner.append_audio(
                    RealtimeAudioChunk(
                        data=audio_bytes,
                        mime_type=mime_type,
                        sequence=session.input_sequence,
                        metadata=_realtime_audio_chunk_metadata(
                            provider=provider,
                            profile=realtime_profile,
                            input_sample_rate=input_sample_rate,
                            payload=payload,
                        ),
                    )
                )
                pipeline_runner.raise_if_failed()
                await _send_event(websocket, audio_event)
            elif event_type == "audio.commit":
                if pipeline_runner is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Realtime session must be bound before audio commit",
                    )
                await _send_event(websocket, session.commit_audio())
                await pipeline_runner.commit_audio()
                await asyncio.sleep(0)
                pipeline_runner.raise_if_failed()
                await _send_event(websocket, session.listen())
            elif event_type == "response.cancel":
                if pipeline_runner is not None:
                    await pipeline_runner.cancel_response(
                        _coerce_optional_text(payload.get("reason"))
                    )
                    pipeline_runner.raise_if_failed()
                await _send_event(websocket, session.listen())
            elif event_type == "session.close":
                await _send_event(websocket, session.close(payload.get("reason")))
                await websocket.close()
                break
            elif event_type in _FINAL_TRANSCRIPT_EVENT_TYPES:
                await _send_event(
                    websocket,
                    session.fail(
                        "Transcript events must come from the realtime pipeline",
                        "UNSUPPORTED_EVENT",
                    ),
                )
                break
            else:
                await _send_event(
                    websocket, session.fail("Unsupported event type", "UNSUPPORTED_EVENT")
                )
                break
    except WebSocketDisconnect:
        return
    except HTTPException as exc:
        if session.status.value != "error":
            error_payload = _exception_realtime_error_payload(
                exc,
                provider=provider,
                default_code="BINDING_ERROR",
                default_phase="binding",
                binding=binding,
            )
            logger.warning(
                "Training realtime websocket failed",
                extra={"realtime_error": error_payload},
            )
            await _send_event(websocket, _realtime_session_fail_event(session, error_payload))
        await websocket.close(code=1008)
    except (RealtimeSessionStateError, RuntimeError, ValueError) as exc:
        if session.status.value != "error":
            error_payload = _exception_realtime_error_payload(
                exc,
                provider=provider,
                default_code="SESSION_ERROR",
                default_phase="session",
                binding=binding,
            )
            logger.warning(
                "Training realtime websocket failed",
                extra={"realtime_error": error_payload},
                exc_info=True,
            )
            await _send_event(websocket, _realtime_session_fail_event(session, error_payload))
        await websocket.close(code=1011)
    finally:
        if pipeline_runner is not None:
            await pipeline_runner.close()
