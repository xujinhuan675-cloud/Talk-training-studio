"""Training Studio API routes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import mimetypes
import os
import re
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import (
    CurrentUser,
    enforce_ai_rate_limit,
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_current_user,
    get_growth_service,
    get_stakeholder_llm_client,
    require_system_roles,
    training_scope_for,
)
from application.ports.llm import (
    LLMEndpointMetadata,
    LLMModelMetadata,
    LLMPort,
    LLMProviderMetadata,
    build_llm_provider_registry,
)
from application.ports.realtime import (
    PersistedRealtimeTranscript,
    RealtimeAudioChunk,
    RealtimePipelineAdapter,
    RealtimeSessionBinding,
    RealtimeTranscript,
)
from application.services.stakeholder.analysis_service import AnalysisReaderService, AnalysisService
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.dto import CreateChatRoomDTO, MessageDTO
from application.services.stakeholder.sse import room_event_bus
from application.services.training_studio.catalog_service import (
    TrainingCatalogService,
    TrainingTaskConfigDTO,
)
from application.services.training_studio.live_guidance_llm_adapter import LiveGuidanceLLMAdapter
from application.services.training_studio.live_guidance_service import (
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)
from application.services.training_studio.openai_realtime import (
    OpenAIRealtimeConfig,
    OpenAIRealtimeTranscriptionClient,
)
from application.services.training_studio.realtime_pipeline import (
    FINAL_TRANSCRIPT_EVENT_TYPES,
    RealtimeTranscriptPersistenceSink,
    build_realtime_transcript,
    extract_final_transcript,
    realtime_role_for_event,
)
from application.services.training_studio.realtime_pipeline_runner import (
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
    TrainingSessionDTO,
    TrainingSessionService,
)
from application.services.training_studio.training_core import training_core_metadata_for_session
from core.config import LLMSettings, VoiceSettings, settings
from core.response import success_response
from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import Message
from domain.training_studio.catalog import ScenarioCategory
from domain.training_studio.session import TrainingSessionStatus
from domain.training_studio.storybank import JsonFileStoryBankStore, StoryBankService
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

router = APIRouter(prefix="/training-studio", tags=["Training Studio"])
_TRAINING_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "training_studio"
_storybank_service = StoryBankService(JsonFileStoryBankStore(_TRAINING_DATA_DIR / "storybank.json"))
_training_scenario_config_service = TrainingScenarioConfigService(
    JsonFileScenarioConfigStore(_TRAINING_DATA_DIR / "scenario_config.json")
)
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
_TRAINING_GUIDANCE_SENDER_ID = "training_coach"
_ENV_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_VOICE_TTS_PROVIDERS = {"minimax", "elevenlabs", "openrouter"}
_VOICE_STT_PROVIDERS = {"minimax", "whisper"}


class VoicePreferenceConfigDTO(BaseModel):
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
    realtime_model: str
    realtime_voice: str
    realtime_transcription_model: str | None = None
    realtime_call_url: str
    updated_at: str


class VoicePreferenceUpdateDTO(BaseModel):
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
    realtime_model: str | None = None
    realtime_voice: str | None = None
    realtime_transcription_model: str | None = None
    realtime_call_url: str | None = None


def _openai_realtime_api_key() -> str | None:
    return settings.REALTIME_OPENAI_API_KEY or settings.llm.api_key


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
    provider = (_clean_config_text(value) or fallback).lower()
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
    tts_key = settings.voice.tts_api_key
    stt_key = settings.voice.stt_api_key
    realtime_key = settings.REALTIME_OPENAI_API_KEY
    effective_realtime_key = _openai_realtime_api_key()

    explicit_stt_key = _explicit_config_value("VOICE__STT_API_KEY", env_values)
    if explicit_stt_key:
        stt_key_source = "stt"
    elif tts_key:
        stt_key_source = "tts"
    elif settings.llm.api_key:
        stt_key_source = "llm"
    else:
        stt_key_source = "missing"

    explicit_realtime_key = _explicit_config_value("REALTIME_OPENAI_API_KEY", env_values)
    if explicit_realtime_key:
        realtime_key_source = "realtime"
    elif settings.llm.api_key:
        realtime_key_source = "llm"
    else:
        realtime_key_source = "missing"

    return VoicePreferenceConfigDTO(
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
        stt_provider=settings.voice.stt_provider,
        stt_base_url=settings.voice.stt_base_url,
        stt_model=settings.voice.stt_model,
        stt_api_key_configured=bool(stt_key),
        stt_api_key_preview=_secret_preview(stt_key),
        stt_api_key_source=stt_key_source,
        stt_use_tts_api_key=stt_key_source == "tts",
        realtime_api_key_configured=bool(realtime_key),
        realtime_effective_api_key_configured=bool(effective_realtime_key),
        realtime_api_key_preview=_secret_preview(effective_realtime_key),
        realtime_api_key_source=realtime_key_source,
        realtime_model=settings.REALTIME_OPENAI_MODEL,
        realtime_voice=settings.REALTIME_OPENAI_VOICE,
        realtime_transcription_model=settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        realtime_call_url=settings.REALTIME_OPENAI_CALL_URL,
        updated_at=datetime.now(UTC).isoformat(),
    )


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


def _llm_registry_response(llm: LLMPort | None) -> dict[str, object]:
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
    return registry.to_dict()


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


def get_training_realtime_uow_factory() -> Callable[..., AbstractUnitOfWork]:
    return SQLAlchemyUnitOfWork


def get_training_realtime_openai_factory() -> Callable[[], OpenAIRealtimeTranscriptionClient]:
    def _factory() -> OpenAIRealtimeTranscriptionClient:
        api_key = _openai_realtime_api_key()
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OpenAI Realtime is not configured; set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY",
            )
        return OpenAIRealtimeTranscriptionClient(
            OpenAIRealtimeConfig(
                api_key=api_key,
                model=settings.REALTIME_OPENAI_MODEL,
                websocket_url=settings.REALTIME_OPENAI_WS_URL,
                transcription_model=settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
                input_audio_format=settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
            )
        )

    return _factory


RealtimePipelineFactory = Callable[[str], RealtimePipelineAdapter | None]


def get_training_realtime_pipeline_factory() -> RealtimePipelineFactory:
    def _factory(provider: str) -> RealtimePipelineAdapter | None:
        if not _uses_pipecat_realtime(provider):
            return None
        try:
            pipecat_adapter = _load_pipecat_realtime_adapter()
            return pipecat_adapter.create_pipecat_realtime_pipeline()
        except Exception:
            return None

    return _factory


class StoryBankRegisterDTO(BaseModel):
    answer_text: str = Field(..., min_length=20, max_length=20000)
    scenario_category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    tags: list[str] = Field(default_factory=list)


class RealtimeTranscriptMessageDTO(BaseModel):
    role: str = Field(..., pattern=r"^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=20000)
    event_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RealtimeTranscriptPersistDTO(BaseModel):
    session_id: str = Field(..., min_length=1)
    room_id: int
    messages: list[RealtimeTranscriptMessageDTO] = Field(..., min_length=1, max_length=20)


class StartTrainingSessionDTO(BaseModel):
    room_id: int | str | None = None
    persona_ids: list[str] = Field(default_factory=list)
    room_name: str | None = Field(default=None, min_length=1, max_length=255)
    room_type: str = Field(default="battle_prep", pattern=r"^(private|group|battle_prep|defense)$")
    scenario_id: int | None = None


class CompleteTrainingSessionDTO(BaseModel):
    report_id: int | str | None = None
    score_id: int | str | None = None
    generate_report: bool = True


class FailTrainingSessionDTO(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class TrainingGuidanceTurnDTO(BaseModel):
    speaker: str
    text: str
    turn_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TrainingGuidanceRequestDTO(BaseModel):
    task_goal: str | None = None
    rubric: dict[str, object] = Field(default_factory=dict)
    recent_turns: list[TrainingGuidanceTurnDTO] = Field(default_factory=list)
    message_limit: int = Field(default=50, ge=1, le=200)


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


def _storybank_entry_to_dict(entry) -> dict:
    return entry.to_dict()


def _session_to_dict(session) -> dict:
    return TrainingSessionDTO.from_domain(session).model_dump(mode="json")


def _not_found_if_missing(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


def _assert_training_session_access(session, current_user: CurrentUser) -> None:
    if current_user.is_admin:
        return
    if current_user.is_leader:
        if session.team_id and current_user.team_id and session.team_id == current_user.team_id:
            return
        if session.user_id and session.user_id == current_user.user_id:
            return
        raise HTTPException(
            status_code=403, detail="Training session is outside the current team scope"
        )
    if session.user_id and session.user_id == current_user.user_id:
        return
    raise HTTPException(
        status_code=403, detail="Training session is outside the current user scope"
    )


async def _require_accessible_training_session(
    session_id: str,
    *,
    svc: TrainingSessionService,
    current_user: CurrentUser,
):
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    _assert_training_session_access(session, current_user)
    return session


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
    try:
        return int(session.room_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Session room_id must be numeric to save guidance"
        ) from exc


async def _require_active_guidance_room_id(
    session_id: str,
    svc: TrainingSessionService,
    current_user: CurrentUser | None = None,
) -> int:
    if current_user is None:
        try:
            session = await svc.get_session(session_id)
        except ValueError as exc:
            raise _not_found_if_missing(exc) from exc
    else:
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
    try:
        return int(session.room_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Session room_id must be numeric to read guidance context"
        ) from exc


async def _generate_training_guidance(
    session_id: str,
    body: TrainingGuidanceRequestDTO,
    *,
    svc: TrainingSessionService,
    chatroom_svc: ChatRoomApplicationService,
    guidance_svc: TrainingLiveGuidanceService,
    current_user: CurrentUser | None = None,
) -> dict[str, object]:
    if current_user is None:
        try:
            session = await svc.get_session(session_id)
        except ValueError as exc:
            raise _not_found_if_missing(exc) from exc
    else:
        session = await _require_accessible_training_session(
            session_id,
            svc=svc,
            current_user=current_user,
        )

    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=400, detail="Training session must be active before requesting guidance"
        )

    if body.recent_turns:
        recent_turns = [
            _request_turn_to_guidance_turn(turn) for turn in body.recent_turns if turn.text.strip()
        ]
        source = "request"
    else:
        room_id = await _require_active_guidance_room_id(session_id, svc, current_user)
        detail = await chatroom_svc.get_room_detail(room_id, message_limit=body.message_limit)
        recent_turns = [
            _message_to_guidance_turn(message)
            for message in detail.messages
            if message.content.strip() and not _is_training_guidance_message(message)
        ]
        source = "room"

    state = guidance_svc.build_state(
        training_session_id=session_id,
        task_goal=body.task_goal or _task_goal_for_guidance(session),
        rubric=body.rubric or _rubric_for_guidance(session),
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
    }


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


def _openai_realtime_session_config() -> dict[str, object]:
    audio_input: dict[str, object] = {
        "turn_detection": {"type": "semantic_vad"},
    }
    if settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL:
        audio_input["transcription"] = {
            "model": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        }
    return {
        "type": "realtime",
        "model": settings.REALTIME_OPENAI_MODEL,
        "output_modalities": ["audio"],
        "audio": {
            "input": audio_input,
            "output": {
                "voice": settings.REALTIME_OPENAI_VOICE,
            },
        },
        "instructions": _default_realtime_agent_instructions(),
    }


def _pipecat_realtime_pipeline_metadata(binding: tuple[str, int]) -> dict[str, object]:
    stt: dict[str, object] = {
        "provider": "openai",
        "turnDetection": "disabled",
    }
    if settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL:
        stt["model"] = settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL
    llm: dict[str, object] = {
        "provider": "openai",
        "model": settings.llm.default_model,
    }
    if settings.llm.base_url:
        llm["baseUrl"] = settings.llm.base_url

    return {
        "transport": "websocket",
        "transcriptionModel": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
        "inputSampleRate": 16000,
        "outputSampleRate": 24000,
        "stt": stt,
        "llm": llm,
        "context": {"provider": "pipecat", "realtimeServiceMode": False},
        "tts": {"provider": "openai"},
        "vad": {"provider": "silero", "source": "pipecat", "sampleRate": 16000},
        "turnDetection": {"provider": "pipecat", "source": "pipecat"},
        "talkwise": {
            "trainingSessionId": binding[0],
            "roomId": binding[1],
            "runtime": "realtime_voice",
        },
    }


def _openai_realtime_capability_response() -> dict[str, object]:
    effective_key = _openai_realtime_api_key()
    return {
        "configured": bool(
            effective_key and settings.REALTIME_OPENAI_MODEL and settings.REALTIME_OPENAI_VOICE
        ),
        "effectiveKey": bool(effective_key),
        "model": settings.REALTIME_OPENAI_MODEL,
        "voice": settings.REALTIME_OPENAI_VOICE,
    }


def _load_pipecat_realtime_adapter() -> Any:
    from infrastructure.external.pipecat import realtime_pipeline as pipecat_adapter

    return pipecat_adapter


def _pipecat_realtime_capability_response() -> dict[str, object]:
    try:
        pipecat_adapter = _load_pipecat_realtime_adapter()
    except Exception as exc:
        return {
            "available": False,
            "coreAvailable": False,
            "websocketAvailable": False,
            "llmAvailable": False,
            "missingModules": ["infrastructure.external.pipecat"],
            "error": str(exc),
        }

    try:
        capability = pipecat_adapter.get_pipecat_capability(require_websocket=True)
    except Exception as exc:
        return {
            "available": False,
            "coreAvailable": False,
            "websocketAvailable": False,
            "llmAvailable": False,
            "missingModules": [],
            "error": f"Pipecat capability check failed: {exc}",
        }

    data: dict[str, object] = {
        "available": bool(capability.available),
        "coreAvailable": bool(capability.core_available),
        "websocketAvailable": bool(capability.websocket_available),
        "vadAvailable": bool(getattr(capability, "vad_available", False)),
        "sttAvailable": bool(getattr(capability, "stt_available", False)),
        "ttsAvailable": bool(getattr(capability, "tts_available", False)),
        "llmAvailable": bool(getattr(capability, "llm_available", False)),
        "turnDetectionAvailable": bool(
            getattr(capability, "turn_detection_available", False)
        ),
        "missingModules": [str(module) for module in capability.missing_modules],
        "optionalMissingModules": [
            str(module) for module in getattr(capability, "optional_missing_modules", ())
        ],
        "error": capability.error,
    }
    with suppress(Exception):
        data["sourceSnapshot"] = dict(pipecat_adapter.pipecat_source_snapshot())
    return data


def _realtime_capabilities_response() -> dict[str, object]:
    return {
        "openaiRealtime": _openai_realtime_capability_response(),
        "pipecat": _pipecat_realtime_capability_response(),
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


def _query_binding(websocket: WebSocket) -> tuple[str | None, int | None]:
    params = websocket.query_params
    session_id = _coerce_optional_text(params.get("session_id") or params.get("sessionId"))
    room_id = _coerce_optional_room_id(params.get("room_id") or params.get("roomId"))
    return session_id, room_id


def _query_realtime_provider(websocket: WebSocket) -> str:
    provider = _coerce_optional_text(websocket.query_params.get("provider"))
    return (provider or "local").lower()


def _uses_openai_realtime(provider: str) -> bool:
    return provider in {"openai", "openai_realtime", "openai-realtime"}


def _uses_pipecat_realtime(provider: str) -> bool:
    return provider in {"pipecat", "pipecat_pipeline", "pipecat-pipeline"}


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
    current_user: CurrentUser | None = None,
) -> tuple[str, int] | None:
    if session_id is None and room_id is None:
        return None
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required when binding realtime")

    try:
        training_session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    if current_user is not None:
        _assert_training_session_access(training_session, current_user)
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
    svc: TrainingSessionService,
) -> dict[str, object]:
    """Build the TrainingCore-derived context shared by text and voice runtimes."""

    try:
        session = await svc.get_session(binding[0])
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    metadata = training_core_metadata_for_session(
        session,
        runtime="realtime_voice",
        extra={
            "transport": "websocket",
            "provider": provider,
            "roomId": binding[1],
        },
    )
    return {
        "task_goal": _task_goal_for_guidance(session),
        "rubric": _rubric_for_guidance(session),
        "recent_turns": (),
        "metadata": metadata,
    }


_FINAL_TRANSCRIPT_EVENT_TYPES = FINAL_TRANSCRIPT_EVENT_TYPES


def _extract_final_transcript(payload: dict[str, object]) -> str | None:
    return extract_final_transcript(payload)


def _realtime_role_for_event(payload: dict[str, object]) -> str:
    return realtime_role_for_event(payload)


def _normalize_realtime_transcript(
    payload: dict[str, object],
    *,
    training_session_id: str,
    room_id: int,
    provider: str,
    realtime_session_id: str,
    role: str | None = None,
) -> RealtimeTranscript:
    """Normalize realtime transcript payloads from OpenAI, Pipecat, or clients."""

    event_type = str(payload.get("type") or "transcript.done")
    normalized_payload = dict(payload)
    if event_type not in _FINAL_TRANSCRIPT_EVENT_TYPES:
        normalized_payload["type"] = "transcript.done"
        normalized_payload.setdefault("text", _wire_value(payload, "text", "transcript", "content"))

    binding = RealtimeSessionBinding(
        training_session_id=training_session_id,
        room_id=room_id,
    )
    transcript = build_realtime_transcript(
        normalized_payload,
        binding=binding,
        provider=provider,
        realtime_session_id=realtime_session_id,
    )
    if transcript is None:
        text = _coerce_optional_text(_wire_value(payload, "text", "transcript", "content"))
        if text is None:
            raise ValueError("Realtime transcript payload must contain non-empty text")
        transcript = RealtimeTranscript(
            text=text,
            role=role or realtime_role_for_event(payload),
            binding=binding,
            provider=provider,
            realtime_session_id=realtime_session_id,
            event_type=event_type,
        )

    resolved_role = role or transcript.role
    metadata = dict(transcript.metadata)
    realtime = dict(metadata.get("realtime") or {})
    realtime["eventType"] = event_type
    realtime["role"] = resolved_role
    metadata["realtime"] = realtime
    return replace(
        transcript,
        role=resolved_role,
        event_type=event_type,
        metadata=metadata,
    )


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
    ) -> None:
        self._websocket = websocket
        self._session = session
        self._training_session_id = training_session_id
        self._room_id = room_id
        self._sink = RealtimeTranscriptPersistenceSink(
            uow_factory=uow_factory,
            session_service=svc,
            publish_message=_publish_realtime_room_message,
        )

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
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


async def _pump_openai_realtime_events(
    *,
    openai_client: OpenAIRealtimeTranscriptionClient,
    websocket: WebSocket,
    session: RealtimeSession,
    binding: tuple[str, int],
    svc: TrainingSessionService,
    provider: str,
    uow_factory: Callable[..., AbstractUnitOfWork],
) -> None:
    sink = _WebSocketTrainingTranscriptSink(
        websocket=websocket,
        session=session,
        training_session_id=binding[0],
        room_id=binding[1],
        svc=svc,
        uow_factory=uow_factory,
    )
    while True:
        event = await openai_client.receive_event()
        if event is None:
            return
        event_type = event.get("type")
        if event_type == "error":
            message = (
                _coerce_optional_text(_wire_value(event, "message")) or "OpenAI realtime error"
            )
            await _send_event(websocket, session.fail(message, "OPENAI_REALTIME_ERROR"))
            return
        transcript = build_realtime_transcript(
            event,
            binding=RealtimeSessionBinding(training_session_id=binding[0], room_id=binding[1]),
            provider=provider,
            realtime_session_id=session.session_id,
        )
        if transcript is None:
            continue
        if session.status.value == "processing":
            await _send_event(websocket, session.transcript_done(transcript.text))
        await sink.persist(transcript)
        if session.status.value == "processing":
            await _send_event(websocket, session.listen())


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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: str | None = Query(default=None),
    team_id: str | None = Query(default=None),
    scenario_template_id: str | None = Query(default=None),
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
    sessions = await svc.list_sessions(
        skip=skip,
        limit=limit,
        user_id=scope.user_id,
        team_id=scope.team_id,
        scenario_template_id=scenario_template_id,
    )
    return success_response(data=[_session_to_dict(session) for session in sessions])


@router.get("/scenario-progress", summary="List scenario training progress")
@router.get("/sessions/scenario-progress", include_in_schema=False)
async def list_scenario_training_progress(
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
    progress = await svc.list_scenario_progress(
        skip=skip,
        limit=limit,
        user_id=scope.user_id,
        team_id=scope.team_id,
    )
    return success_response(data=[item.model_dump(mode="json") for item in progress])


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


@router.post("/sessions/{session_id}/start", summary="Start or bind a Training Studio session")
async def start_training_session(
    session_id: str,
    body: StartTrainingSessionDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )

    room_id = str(body.room_id).strip() if body.room_id is not None else ""
    if not room_id:
        if not body.persona_ids:
            raise HTTPException(status_code=422, detail="room_id or persona_ids is required")
        room_name = body.room_name or f"Training: {session.task_config.role}"
        room = await chatroom_svc.create_room(
            CreateChatRoomDTO(
                name=room_name,
                type=body.room_type,
                persona_ids=body.persona_ids,
                scenario_id=body.scenario_id,
            )
        )
        room_id = str(room.id)

    try:
        started = await svc.start_session(session_id, room_id=room_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    return success_response(data=_session_to_dict(started))


@router.post("/sessions/{session_id}/complete", summary="Complete a Training Studio session")
async def complete_training_session(
    session_id: str,
    body: CompleteTrainingSessionDTO,
    background_tasks: BackgroundTasks,
    svc: TrainingSessionService = Depends(get_training_session_service),
    analysis_svc: AnalysisService = Depends(get_analysis_service),
    growth_svc=Depends(get_growth_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    session = await _require_accessible_training_session(
        session_id,
        svc=svc,
        current_user=current_user,
    )

    report_id = str(body.report_id).strip() if body.report_id is not None else ""
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
        try:
            report = await analysis_svc.generate_report(room_id)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        report_id = str(report.id)
        background_tasks.add_task(growth_svc.evaluate_competency, report.id)

    score_id = str(body.score_id).strip() if body.score_id is not None else None
    try:
        completed = await svc.complete_session(
            session_id,
            report_id=report_id or None,
            score_id=score_id,
        )
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
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
        failed = await svc.fail_session(session_id, body.reason)
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
        raise HTTPException(status_code=404, detail="Training session report not found")

    try:
        report_lookup_id = int(session.report_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Training session report not found") from exc
    report = await reader_svc.get_report(report_lookup_id)
    if report is None or str(report.room_id) != str(session.room_id):
        raise HTTPException(status_code=404, detail="Training session report not found")
    return success_response(data=report.model_dump(mode="json"))


@router.post("/realtime/sdp", summary="Create an OpenAI Realtime WebRTC call")
async def create_realtime_sdp_call(
    request: Request,
    session_id: str | None = Query(default=None),
    room_id: int | None = Query(default=None),
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
):
    api_key = _openai_realtime_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI Realtime is not configured; set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY",
        )

    offer_sdp = (await request.body()).decode("utf-8", errors="ignore").strip()
    if not offer_sdp:
        raise HTTPException(status_code=422, detail="SDP offer is required")
    await _resolve_realtime_binding(
        session_id,
        room_id,
        svc=svc,
        uow_factory=uow_factory,
        current_user=current_user,
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.post(
                settings.REALTIME_OPENAI_CALL_URL,
                data={"session": json.dumps(_openai_realtime_session_config(), ensure_ascii=False)},
                files={"sdp": ("offer.sdp", offer_sdp, "application/sdp")},
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"OpenAI Realtime SDP request failed: {exc}"
        ) from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=upstream.status_code, detail=upstream.text)
    return Response(content=upstream.text, media_type="application/sdp")


@router.get("/realtime/capabilities", summary="Get realtime provider capabilities")
async def get_realtime_capabilities(
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    return success_response(data=_realtime_capabilities_response())


@router.post(
    "/realtime/transcripts", status_code=201, summary="Persist Realtime voice-agent transcripts"
)
async def persist_realtime_transcripts(
    body: RealtimeTranscriptPersistDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
    current_user: CurrentUser = Depends(get_current_user),
):
    binding = await _resolve_realtime_binding(
        body.session_id,
        body.room_id,
        svc=svc,
        uow_factory=uow_factory,
        current_user=current_user,
    )
    if binding is None:
        raise HTTPException(
            status_code=400, detail="Realtime transcript persistence requires a bound session"
        )

    sink = RealtimeTranscriptPersistenceSink(
        uow_factory=uow_factory,
        session_service=svc,
        publish_message=_publish_realtime_room_message,
    )
    persisted_messages: list[dict[str, object]] = []
    for item in body.messages:
        content = item.content.strip()
        if not content:
            continue
        payload: dict[str, object] = {
            "type": f"client.realtime_transcript.{item.role}",
            "text": content,
            "event_id": item.event_id,
            "item_id": item.item_id,
            "response_id": item.response_id,
            **item.metadata,
        }
        transcript = _normalize_realtime_transcript(
            payload,
            training_session_id=binding[0],
            room_id=binding[1],
            provider="openai_webrtc",
            realtime_session_id=binding[0],
            role=item.role,
        )
        if item.sender_id:
            transcript = replace(
                transcript,
                metadata={**dict(transcript.metadata), "sender_id": item.sender_id},
            )
        persisted = await sink.persist(transcript)
        message = persisted.payload.get("message")
        if isinstance(message, dict):
            persisted_messages.append(message)

    return success_response(data={"messages": persisted_messages})


@router.get("/sessions/{session_id}/guidance", summary="Get Training Studio live guidance")
async def get_training_guidance(
    session_id: str,
    message_limit: int = Query(50, ge=1, le=200),
    _rate_limit: None = Depends(enforce_ai_rate_limit),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await _generate_training_guidance(
        session_id,
        TrainingGuidanceRequestDTO(message_limit=message_limit),
        svc=svc,
        chatroom_svc=chatroom_svc,
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
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    data = await _generate_training_guidance(
        session_id,
        body,
        svc=svc,
        chatroom_svc=chatroom_svc,
        guidance_svc=guidance_svc,
        current_user=current_user,
    )
    return success_response(data=data)


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
                        guidance_svc=guidance_svc,
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
    svc: TrainingCatalogService = Depends(get_training_catalog_service),
):
    templates = svc.get_scenario_templates()
    return success_response(data=[template.model_dump(mode="json") for template in templates])


@router.get("/llm-registry", summary="Get text LLM provider and model registry")
async def get_llm_registry(
    llm: LLMPort | None = Depends(get_stakeholder_llm_client),
    _current_user: CurrentUser = Depends(require_system_roles("admin", "leader", "staff")),
):
    return success_response(data=_llm_registry_response(llm))


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
    llm_base_url = _clean_config_text(body.llm_base_url) or current_llm.base_url
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

    tts_base_url = _clean_config_text(body.tts_base_url) or current_voice.tts_base_url
    stt_base_url = _clean_config_text(body.stt_base_url) or current_voice.stt_base_url
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
    if body.stt_use_tts_api_key:
        stt_api_key = tts_api_key or llm_api_key
    elif body.clear_stt_api_key:
        stt_api_key = None
    elif new_stt_key:
        stt_api_key = new_stt_key

    realtime_api_key = settings.REALTIME_OPENAI_API_KEY
    new_realtime_key = _clean_config_text(body.realtime_api_key)
    if body.clear_realtime_api_key:
        realtime_api_key = None
    elif new_realtime_key:
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
    realtime_call_url = _required_config_text(
        body.realtime_call_url,
        settings.REALTIME_OPENAI_CALL_URL,
        "realtime_call_url",
    )

    env_updates: dict[str, str | None] = {
        "LLM__BASE_URL": llm_base_url,
        "LLM__DEFAULT_MODEL": llm_default_model,
        "LLM__WIRE_API": llm_wire_api,
        "VOICE__TTS_PROVIDER": tts_provider,
        "VOICE__TTS_BASE_URL": tts_base_url,
        "VOICE__TTS_MODEL": tts_model,
        "VOICE__STT_PROVIDER": stt_provider,
        "VOICE__STT_BASE_URL": stt_base_url,
        "VOICE__STT_MODEL": stt_model,
        "REALTIME_OPENAI_MODEL": realtime_model,
        "REALTIME_OPENAI_VOICE": realtime_voice,
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL": realtime_transcription_model,
        "REALTIME_OPENAI_CALL_URL": realtime_call_url,
    }
    if body.clear_llm_api_key or new_llm_key:
        env_updates["LLM__API_KEY"] = llm_api_key
    if body.clear_tts_api_key or new_tts_key:
        env_updates["VOICE__TTS_API_KEY"] = tts_api_key
    if body.stt_use_tts_api_key or body.clear_stt_api_key or new_stt_key:
        env_updates["VOICE__STT_API_KEY"] = "" if body.stt_use_tts_api_key else stt_api_key
    if body.clear_realtime_api_key or new_realtime_key:
        env_updates["REALTIME_OPENAI_API_KEY"] = realtime_api_key

    try:
        _write_env_file_values(env_updates)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to write backend .env: {exc}") from exc

    settings.llm = LLMSettings(
        provider=current_llm.provider,
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
    if not settings.voice.stt_api_key:
        settings.voice.stt_api_key = settings.voice.tts_api_key or settings.llm.api_key
    if not settings.voice.stt_base_url:
        settings.voice.stt_base_url = settings.llm.base_url
    settings.REALTIME_OPENAI_API_KEY = realtime_api_key
    settings.REALTIME_OPENAI_MODEL = realtime_model
    settings.REALTIME_OPENAI_VOICE = realtime_voice
    settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL = realtime_transcription_model
    settings.REALTIME_OPENAI_CALL_URL = realtime_call_url

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
async def upload_video_answer(request: Request):
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
    await asyncio.to_thread(path.write_bytes, data)
    return success_response(
        data={
            "filename": filename,
            "url": f"/api/v1/training-studio/video-answers/{filename}",
            "mimeType": content_type,
            "size": len(data),
        }
    )


@router.get("/video-answers/{filename}", summary="Read a recorded video answer")
async def read_video_answer(filename: str):
    path = _resolve_video_answer_file(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video answer not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type)


@router.websocket("/realtime")
async def realtime_training_session(
    websocket: WebSocket,
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
    openai_factory: Callable[[], OpenAIRealtimeTranscriptionClient] = Depends(
        get_training_realtime_openai_factory
    ),
    pipeline_factory: RealtimePipelineFactory = Depends(get_training_realtime_pipeline_factory),
):
    """Minimal bidirectional realtime session endpoint for audio event wiring."""

    await websocket.accept()
    query_session_id, query_room_id = _query_binding(websocket)
    provider = _query_realtime_provider(websocket)
    session = RealtimeSession(session_id=query_session_id)
    binding: tuple[str, int] | None = None
    openai_client: OpenAIRealtimeTranscriptionClient | None = None
    openai_task: asyncio.Task[None] | None = None
    pipeline_runner: RealtimePipelineSessionRunner | None = None

    async def _ensure_pipeline_runner(active_binding: tuple[str, int]) -> None:
        nonlocal pipeline_runner
        if pipeline_runner is not None or not _uses_pipecat_realtime(provider):
            return
        adapter = pipeline_factory(provider)
        if adapter is None:
            raise HTTPException(
                status_code=503,
                detail="Pipecat realtime pipeline is not available",
            )
        sink = _WebSocketTrainingTranscriptSink(
            websocket=websocket,
            session=session,
            training_session_id=active_binding[0],
            room_id=active_binding[1],
            svc=svc,
            uow_factory=uow_factory,
        )
        runner = RealtimePipelineSessionRunner(adapter=adapter, transcript_sink=sink)
        voice_context = await _build_realtime_voice_context(
            active_binding,
            provider=provider,
            svc=svc,
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
            model=settings.REALTIME_OPENAI_MODEL,
            voice=settings.REALTIME_OPENAI_VOICE,
            input_audio_format=settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
            output_audio_format=settings.REALTIME_OPENAI_INPUT_AUDIO_FORMAT,
            instructions=_default_realtime_agent_instructions(),
            context_metadata=voice_context["metadata"],
            config_metadata=_pipecat_realtime_pipeline_metadata(active_binding),
        )
        pipeline_runner = runner

    try:
        binding = await _resolve_realtime_binding(
            query_session_id,
            query_room_id,
            svc=svc,
            uow_factory=uow_factory,
        )
        if binding is not None:
            await _ensure_pipeline_runner(binding)
        if _uses_openai_realtime(provider):
            if binding is None:
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI realtime requires an active session and bound room",
                )
            openai_client = openai_factory()
            await openai_client.connect()
            openai_task = asyncio.create_task(
                _pump_openai_realtime_events(
                    openai_client=openai_client,
                    websocket=websocket,
                    session=session,
                    binding=binding,
                    svc=svc,
                    provider=provider,
                    uow_factory=uow_factory,
                )
            )
        start_metadata: dict[str, object] = {"transport": "websocket", "provider": provider}
        if binding is not None:
            start_metadata.update({"trainingSessionId": binding[0], "roomId": binding[1]})
        await _send_event(websocket, session.start(start_metadata))
        await _send_event(websocket, session.listen())
        while True:
            raw = await websocket.receive()
            if raw.get("type") == "websocket.disconnect":
                return
            if raw.get("bytes") is not None:
                audio_bytes = raw["bytes"] or b""
                if openai_client is not None:
                    await openai_client.append_audio(audio_bytes)
                audio_event = session.receive_audio(audio_bytes, "audio/pcm")
                if pipeline_runner is not None:
                    await pipeline_runner.append_audio(
                        RealtimeAudioChunk(
                            data=audio_bytes,
                            mime_type="audio/pcm",
                            sequence=session.input_sequence,
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
                if openai_client is not None:
                    await openai_client.append_audio(audio_bytes)
                mime_type = _coerce_optional_text(payload.get("mimeType"))
                audio_event = session.receive_audio(audio_bytes, mime_type)
                if pipeline_runner is not None:
                    await pipeline_runner.append_audio(
                        RealtimeAudioChunk(
                            data=audio_bytes,
                            mime_type=mime_type,
                            sequence=session.input_sequence,
                        )
                    )
                    pipeline_runner.raise_if_failed()
                await _send_event(websocket, audio_event)
            elif event_type == "audio.commit":
                await _send_event(websocket, session.commit_audio())
                if openai_client is not None:
                    await openai_client.commit_audio()
                elif pipeline_runner is not None:
                    await pipeline_runner.commit_audio()
                    await asyncio.sleep(0)
                    pipeline_runner.raise_if_failed()
                    await _send_event(websocket, session.listen())
                else:
                    await _send_event(websocket, session.transcript_delta(""))
                    await _send_event(websocket, session.transcript_done(""))
                    await _send_event(websocket, session.send_audio(b"", "audio/wav"))
                    await _send_event(websocket, session.listen())
            elif event_type == "response.cancel":
                await _send_event(websocket, session.listen())
            elif event_type == "session.close":
                await _send_event(websocket, session.close(payload.get("reason")))
                await websocket.close()
                break
            elif event_type in _FINAL_TRANSCRIPT_EVENT_TYPES:
                if binding is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Realtime session must be bound before transcript persistence",
                    )
                transcript = build_realtime_transcript(
                    payload,
                    binding=RealtimeSessionBinding(
                        training_session_id=binding[0], room_id=binding[1]
                    ),
                    provider=provider,
                    realtime_session_id=session.session_id,
                )
                if transcript is None:
                    await _send_wire_event(
                        websocket,
                        "transcript.ignored",
                        session,
                        {"reason": "empty_transcript"},
                    )
                    continue
                sink = _WebSocketTrainingTranscriptSink(
                    websocket=websocket,
                    session=session,
                    training_session_id=binding[0],
                    room_id=binding[1],
                    svc=svc,
                    uow_factory=uow_factory,
                )
                await sink.persist(transcript)
            else:
                await _send_event(
                    websocket, session.fail("Unsupported event type", "UNSUPPORTED_EVENT")
                )
                break
    except WebSocketDisconnect:
        return
    except HTTPException as exc:
        if session.status.value != "error":
            await _send_event(websocket, session.fail(str(exc.detail), "BINDING_ERROR"))
        await websocket.close(code=1008)
    except (RealtimeSessionStateError, RuntimeError, ValueError) as exc:
        if session.status.value != "error":
            await _send_event(websocket, session.fail(str(exc), "SESSION_ERROR"))
        await websocket.close(code=1011)
    finally:
        if pipeline_runner is not None:
            await pipeline_runner.close()
        if openai_task is not None:
            openai_task.cancel()
            with suppress(asyncio.CancelledError):
                await openai_task
        if openai_client is not None:
            await openai_client.close()
