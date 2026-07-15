"""Training Studio API routes."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_growth_service,
    get_stakeholder_llm_client,
)
from application.ports.llm import LLMPort
from application.services.stakeholder.analysis_service import AnalysisReaderService, AnalysisService
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.dto import CreateChatRoomDTO, MessageDTO
from application.services.stakeholder.sse import room_event_bus
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
from application.services.training_studio.realtime_session import (
    RealtimeEvent,
    RealtimeSession,
    RealtimeSessionStateError,
)
from application.services.training_studio.catalog_service import (
    TrainingCatalogService,
    TrainingTaskConfigDTO,
)
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingSessionDTO,
    TrainingSessionService,
)
from core.config import settings
from core.response import success_response
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import Message
from domain.common.exceptions import DomainValidationException
from domain.training_studio.catalog import ScenarioCategory
from domain.training_studio.session import TrainingSessionStatus
from domain.training_studio.storybank import JsonFileStoryBankStore, StoryBankService
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

router = APIRouter(prefix="/training-studio", tags=["Training Studio"])
_TRAINING_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "training_studio"
_storybank_service = StoryBankService(
    JsonFileStoryBankStore(_TRAINING_DATA_DIR / "storybank.json")
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


def get_training_catalog_service() -> TrainingCatalogService:
    return TrainingCatalogService()


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
        api_key = settings.llm.api_key
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="OpenAI Realtime is not configured; set LLM__API_KEY or OPENAI_API_KEY",
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


def _storybank_entry_to_dict(entry) -> dict:
    return entry.to_dict()


def _session_to_dict(session) -> dict:
    return TrainingSessionDTO.from_domain(session).model_dump(mode="json")


def _not_found_if_missing(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


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
    metadata.update({
        "message_id": message.id,
        "room_id": message.room_id,
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
        "emotion_score": message.emotion_score,
        "emotion_label": message.emotion_label,
    })
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


async def _require_active_guidance_room_id(session_id: str, svc: TrainingSessionService) -> int:
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Training session must be active before requesting guidance")
    if not session.room_id:
        raise HTTPException(status_code=400, detail="Training session must be started before requesting guidance")
    try:
        return int(session.room_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Session room_id must be numeric to read guidance context") from exc


async def _generate_training_guidance(
    session_id: str,
    body: TrainingGuidanceRequestDTO,
    *,
    svc: TrainingSessionService,
    chatroom_svc: ChatRoomApplicationService,
    guidance_svc: TrainingLiveGuidanceService,
) -> dict[str, object]:
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc

    if session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Training session must be active before requesting guidance")

    if body.recent_turns:
        recent_turns = [
            _request_turn_to_guidance_turn(turn)
            for turn in body.recent_turns
            if turn.text.strip()
        ]
        source = "request"
    else:
        room_id = await _require_active_guidance_room_id(session_id, svc)
        detail = await chatroom_svc.get_room_detail(room_id, message_limit=body.message_limit)
        recent_turns = [
            _message_to_guidance_turn(message)
            for message in detail.messages
            if message.content.strip()
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
            {
                key: value
                for key, value in event.items()
                if key != "created_at"
            }
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
) -> tuple[str, int] | None:
    if session_id is None and room_id is None:
        return None
    if session_id is None:
        raise HTTPException(status_code=400, detail="session_id is required when binding realtime")

    try:
        training_session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    if training_session.status != TrainingSessionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Training session must be active before binding realtime")
    if not training_session.room_id:
        raise HTTPException(status_code=400, detail="Training session must be started before binding realtime")

    bound_room_id = _coerce_optional_room_id(training_session.room_id)
    if bound_room_id is None:
        raise HTTPException(status_code=400, detail="Session room_id must be numeric to bind realtime")
    if room_id is not None and room_id != bound_room_id:
        raise HTTPException(status_code=400, detail="room_id does not match the active training session")

    async with uow_factory(readonly=True) as uow:
        room = await uow.chat_room_repository.get_by_id(bound_room_id)
    if room is None:
        raise HTTPException(status_code=404, detail=f"Chat room {bound_room_id} not found")

    return session_id, bound_room_id


_FINAL_TRANSCRIPT_EVENT_TYPES = {
    "transcript.done",
    "input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.completed",
    "response.audio_transcript.done",
    "response.output_audio_transcript.done",
}


def _extract_final_transcript(payload: dict[str, object]) -> str | None:
    if payload.get("type") not in _FINAL_TRANSCRIPT_EVENT_TYPES:
        return None
    value = _wire_value(payload, "text", "transcript")
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _metadata_scalar(value: object | None) -> object | None:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return None


def _realtime_transcript_metadata(
    payload: dict[str, object],
    *,
    training_session_id: str,
    room_id: int,
    provider: str,
    realtime_session_id: str,
    role: str = "user",
) -> dict[str, object]:
    realtime: dict[str, object] = {
        "schemaVersion": 1,
        "provider": provider,
        "eventType": payload.get("type"),
        "role": role,
        "trainingSessionId": training_session_id,
        "roomId": room_id,
        "realtimeSessionId": realtime_session_id,
        "isFinal": True,
        "receivedAt": datetime.now(UTC).isoformat(),
    }
    for output_key, input_keys in {
        "eventId": ("event_id", "eventId"),
        "itemId": ("item_id", "itemId", "item"),
        "responseId": ("response_id", "responseId", "response"),
        "contentIndex": ("content_index", "contentIndex"),
        "language": ("language", "lang"),
        "confidence": ("confidence",),
        "sequence": ("sequence",),
    }.items():
        value = _metadata_scalar(_wire_value(payload, *input_keys))
        if value is not None:
            realtime[output_key] = value
    return {
        "source": "realtime_voice",
        "trainingMode": "voice",
        "interactionMode": "realtime",
        "realtime": realtime,
    }


def _realtime_role_for_event(payload: dict[str, object]) -> str:
    event_type = str(payload.get("type") or "")
    if event_type.startswith("response."):
        return "assistant"
    return "user"


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

    await room_event_bus.publish(room_id, "message", dto.model_dump(mode="json"))
    return dto


async def _persist_realtime_transcript(
    room_id: int,
    transcript: str,
    *,
    uow_factory: Callable[..., AbstractUnitOfWork],
    metadata: dict[str, object] | None = None,
) -> MessageDTO:
    return await _persist_realtime_message(
        room_id,
        transcript,
        uow_factory=uow_factory,
        metadata=metadata,
        sender_type="user",
        sender_id="user",
    )


async def _pump_openai_realtime_events(
    *,
    openai_client: OpenAIRealtimeTranscriptionClient,
    websocket: WebSocket,
    session: RealtimeSession,
    binding: tuple[str, int],
    provider: str,
    uow_factory: Callable[..., AbstractUnitOfWork],
) -> None:
    while True:
        event = await openai_client.receive_event()
        if event is None:
            return
        event_type = event.get("type")
        if event_type == "error":
            message = _coerce_optional_text(_wire_value(event, "message")) or "OpenAI realtime error"
            await _send_event(websocket, session.fail(message, "OPENAI_REALTIME_ERROR"))
            return
        transcript = _extract_final_transcript(event)
        if transcript is None:
            continue
        if session.status.value == "processing":
            await _send_event(websocket, session.transcript_done(transcript))
        role = _realtime_role_for_event(event)
        metadata = _realtime_transcript_metadata(
            event,
            training_session_id=binding[0],
            room_id=binding[1],
            provider=provider,
            realtime_session_id=session.session_id,
            role=role,
        )
        message = await _persist_realtime_message(
            binding[1],
            transcript,
            uow_factory=uow_factory,
            metadata=metadata,
            sender_type="persona" if role == "assistant" else "user",
            sender_id="assistant" if role == "assistant" else "user",
        )
        await _send_wire_event(
            websocket,
            "transcript.persisted",
            session,
            {
                "trainingSessionId": binding[0],
                "roomId": binding[1],
                "message": message.model_dump(mode="json"),
            },
        )
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
):
    user_id = _coerce_optional_text(body.user_id) or _coerce_optional_text(x_user_id)
    team_id = _coerce_optional_text(body.team_id) or _coerce_optional_text(x_team_id)
    if user_id != body.user_id or team_id != body.team_id:
        body = body.model_copy(update={"user_id": user_id, "team_id": team_id})
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
):
    sessions = await svc.list_sessions(
        skip=skip,
        limit=limit,
        user_id=_coerce_optional_text(user_id) or _coerce_optional_text(x_user_id),
        team_id=_coerce_optional_text(team_id) or _coerce_optional_text(x_team_id),
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
):
    progress = await svc.list_scenario_progress(
        skip=skip,
        limit=limit,
        user_id=_coerce_optional_text(user_id) or _coerce_optional_text(x_user_id),
        team_id=_coerce_optional_text(team_id) or _coerce_optional_text(x_team_id),
    )
    return success_response(data=[item.model_dump(mode="json") for item in progress])


@router.get("/sessions/{session_id}", summary="Get a Training Studio session")
async def get_training_session(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
):
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc
    return success_response(data=_session_to_dict(session))


@router.post("/sessions/{session_id}/start", summary="Start or bind a Training Studio session")
async def start_training_session(
    session_id: str,
    body: StartTrainingSessionDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
):
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc

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
):
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc

    report_id = str(body.report_id).strip() if body.report_id is not None else ""
    if body.generate_report and not report_id:
        if not session.room_id:
            raise HTTPException(status_code=400, detail="Session must be started before generating a report")
        try:
            room_id = int(session.room_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Session room_id must be numeric to generate a report") from exc
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


@router.get("/sessions/{session_id}/report", summary="Get a Training Studio session report")
async def get_training_session_report(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
    reader_svc: AnalysisReaderService = Depends(get_analysis_reader_service),
):
    try:
        session = await svc.get_session(session_id)
    except ValueError as exc:
        raise _not_found_if_missing(exc) from exc

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
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
):
    api_key = settings.llm.api_key
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI Realtime is not configured; set LLM__API_KEY or OPENAI_API_KEY",
        )

    offer_sdp = (await request.body()).decode("utf-8", errors="ignore").strip()
    if not offer_sdp:
        raise HTTPException(status_code=422, detail="SDP offer is required")
    await _resolve_realtime_binding(session_id, room_id, svc=svc, uow_factory=uow_factory)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.post(
                settings.REALTIME_OPENAI_CALL_URL,
                data={"session": json.dumps(_openai_realtime_session_config(), ensure_ascii=False)},
                files={"sdp": ("offer.sdp", offer_sdp, "application/sdp")},
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI Realtime SDP request failed: {exc}") from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=upstream.status_code, detail=upstream.text)
    return Response(content=upstream.text, media_type="application/sdp")


@router.post("/realtime/transcripts", status_code=201, summary="Persist Realtime voice-agent transcripts")
async def persist_realtime_transcripts(
    body: RealtimeTranscriptPersistDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    uow_factory: Callable[..., AbstractUnitOfWork] = Depends(get_training_realtime_uow_factory),
):
    binding = await _resolve_realtime_binding(
        body.session_id,
        body.room_id,
        svc=svc,
        uow_factory=uow_factory,
    )
    if binding is None:
        raise HTTPException(status_code=400, detail="Realtime transcript persistence requires a bound session")

    persisted: list[MessageDTO] = []
    for item in body.messages:
        content = item.content.strip()
        if not content:
            continue
        sender_type = "persona" if item.role == "assistant" else "user"
        sender_id = item.sender_id or ("assistant" if item.role == "assistant" else "user")
        payload: dict[str, object] = {
            "type": f"client.realtime_transcript.{item.role}",
            "event_id": item.event_id,
            "item_id": item.item_id,
            "response_id": item.response_id,
            **item.metadata,
        }
        metadata = _realtime_transcript_metadata(
            payload,
            training_session_id=binding[0],
            room_id=binding[1],
            provider="openai_webrtc",
            realtime_session_id=binding[0],
            role=item.role,
        )
        message = await _persist_realtime_message(
            binding[1],
            content,
            uow_factory=uow_factory,
            metadata=metadata,
            sender_type=sender_type,
            sender_id=sender_id,
        )
        persisted.append(message)

    return success_response(data={"messages": [message.model_dump(mode="json") for message in persisted]})


@router.get("/sessions/{session_id}/guidance", summary="Get Training Studio live guidance")
async def get_training_guidance(
    session_id: str,
    message_limit: int = Query(50, ge=1, le=200),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
):
    data = await _generate_training_guidance(
        session_id,
        TrainingGuidanceRequestDTO(message_limit=message_limit),
        svc=svc,
        chatroom_svc=chatroom_svc,
        guidance_svc=guidance_svc,
    )
    return success_response(data=data)


@router.post("/sessions/{session_id}/guidance", summary="Request Training Studio live guidance")
async def request_training_guidance(
    session_id: str,
    body: TrainingGuidanceRequestDTO,
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
):
    data = await _generate_training_guidance(
        session_id,
        body,
        svc=svc,
        chatroom_svc=chatroom_svc,
        guidance_svc=guidance_svc,
    )
    return success_response(data=data)


@router.get("/sessions/{session_id}/guidance/stream", summary="Stream Training Studio live guidance")
async def stream_training_guidance(
    session_id: str,
    request: Request,
    message_limit: int = Query(50, ge=1, le=200),
    poll_interval_ms: int = Query(1000, ge=250, le=10000),
    max_events: int | None = Query(default=None, ge=1, le=50, include_in_schema=False),
    svc: TrainingSessionService = Depends(get_training_session_service),
    chatroom_svc: ChatRoomApplicationService = Depends(get_chatroom_service),
    guidance_svc: TrainingLiveGuidanceService = Depends(get_live_guidance_service),
):
    body = TrainingGuidanceRequestDTO(message_limit=message_limit)
    room_id = await _require_active_guidance_room_id(session_id, svc)
    initial_data = await _generate_training_guidance(
        session_id,
        body,
        svc=svc,
        chatroom_svc=chatroom_svc,
        guidance_svc=guidance_svc,
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
                    yield _format_sse("guidance_error", {"status_code": exc.status_code, "detail": exc.detail})
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
):
    """Minimal bidirectional realtime session endpoint for audio event wiring."""

    await websocket.accept()
    query_session_id, query_room_id = _query_binding(websocket)
    provider = _query_realtime_provider(websocket)
    session = RealtimeSession(session_id=query_session_id)
    binding: tuple[str, int] | None = None
    openai_client: OpenAIRealtimeTranscriptionClient | None = None
    openai_task: asyncio.Task[None] | None = None
    try:
        binding = await _resolve_realtime_binding(
            query_session_id,
            query_room_id,
            svc=svc,
            uow_factory=uow_factory,
        )
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
                await _send_event(
                    websocket,
                    session.receive_audio(audio_bytes, "audio/pcm"),
                )
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
                audio_bytes = base64.b64decode(audio) if isinstance(audio, str) and audio else b""
                if openai_client is not None:
                    await openai_client.append_audio(audio_bytes)
                await _send_event(
                    websocket,
                    session.receive_audio(audio_bytes, payload.get("mimeType")),
                )
            elif event_type == "audio.commit":
                await _send_event(websocket, session.commit_audio())
                if openai_client is not None:
                    await openai_client.commit_audio()
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
                transcript = _extract_final_transcript(payload)
                if not transcript:
                    await _send_wire_event(
                        websocket,
                        "transcript.ignored",
                        session,
                        {"reason": "empty_transcript"},
                    )
                    continue
                if binding is None:
                    raise HTTPException(status_code=400, detail="Realtime session must be bound before transcript persistence")
                role = _realtime_role_for_event(payload)
                message = await _persist_realtime_message(
                    binding[1],
                    transcript,
                    uow_factory=uow_factory,
                    metadata=_realtime_transcript_metadata(
                        payload,
                        training_session_id=binding[0],
                        room_id=binding[1],
                        provider=provider,
                        realtime_session_id=session.session_id,
                        role=role,
                    ),
                    sender_type="persona" if role == "assistant" else "user",
                    sender_id="assistant" if role == "assistant" else "user",
                )
                await _send_wire_event(
                    websocket,
                    "transcript.persisted",
                    session,
                    {
                        "trainingSessionId": binding[0],
                        "roomId": binding[1],
                        "message": message.model_dump(mode="json"),
                    },
                )
            else:
                await _send_event(websocket, session.fail("Unsupported event type", "UNSUPPORTED_EVENT"))
                break
    except WebSocketDisconnect:
        return
    except HTTPException as exc:
        if session.status.value != "error":
            await _send_event(websocket, session.fail(str(exc.detail), "BINDING_ERROR"))
        await websocket.close(code=1008)
    except (RealtimeSessionStateError, ValueError) as exc:
        if session.status.value != "error":
            await _send_event(websocket, session.fail(str(exc), "SESSION_ERROR"))
        await websocket.close(code=1011)
    finally:
        if openai_task is not None:
            openai_task.cancel()
            with suppress(asyncio.CancelledError):
                await openai_task
        if openai_client is not None:
            await openai_client.close()
