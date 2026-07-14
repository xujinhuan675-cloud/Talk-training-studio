"""Training Studio API routes."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_growth_service,
)
from application.services.stakeholder.analysis_service import AnalysisReaderService, AnalysisService
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.dto import CreateChatRoomDTO
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
from core.response import success_response
from domain.common.exceptions import DomainValidationException
from domain.training_studio.catalog import ScenarioCategory
from domain.training_studio.storybank import JsonFileStoryBankStore, StoryBankService

router = APIRouter(prefix="/training-studio", tags=["Training Studio"])
_TRAINING_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "training_studio"
_storybank_service = StoryBankService(
    JsonFileStoryBankStore(_TRAINING_DATA_DIR / "storybank.json")
)
_training_session_service = TrainingSessionService()
_VIDEO_ANSWER_DIR = _TRAINING_DATA_DIR / "video_answers"
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


class StoryBankRegisterDTO(BaseModel):
    answer_text: str = Field(..., min_length=20, max_length=20000)
    scenario_category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    tags: list[str] = Field(default_factory=list)


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


async def _send_event(websocket: WebSocket, event: RealtimeEvent) -> None:
    await websocket.send_json(_event_to_wire(event))


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
    svc: TrainingSessionService = Depends(get_training_session_service),
):
    try:
        session = svc.create_session(body)
    except (DomainValidationException, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return success_response(data=_session_to_dict(session))


@router.get("/sessions", summary="List Training Studio sessions")
async def list_training_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    svc: TrainingSessionService = Depends(get_training_session_service),
):
    sessions = svc.list_sessions()
    window = sessions[skip : skip + limit]
    return success_response(data=[_session_to_dict(session) for session in window])


@router.get("/sessions/{session_id}", summary="Get a Training Studio session")
async def get_training_session(
    session_id: str,
    svc: TrainingSessionService = Depends(get_training_session_service),
):
    try:
        session = svc.get_session(session_id)
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
        session = svc.get_session(session_id)
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
        started = svc.start_session(session_id, room_id=room_id)
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
        session = svc.get_session(session_id)
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
        completed = svc.complete_session(session_id, report_id=report_id or None, score_id=score_id)
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
        session = svc.get_session(session_id)
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


@router.get("/catalog", summary="Get Training Studio catalog options")
async def get_catalog(
    svc: TrainingCatalogService = Depends(get_training_catalog_service),
):
    return success_response(data=svc.get_catalog().model_dump(mode="json"))


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
async def realtime_training_session(websocket: WebSocket):
    """Minimal bidirectional realtime session endpoint for audio event wiring."""

    await websocket.accept()
    session = RealtimeSession()
    try:
        await _send_event(websocket, session.start({"transport": "websocket"}))
        await _send_event(websocket, session.listen())
        while True:
            raw = await websocket.receive()
            if raw.get("bytes") is not None:
                await _send_event(
                    websocket,
                    session.receive_audio(raw["bytes"], "application/octet-stream"),
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
            if event_type == "session.start":
                await _send_event(websocket, session.listen())
            elif event_type == "audio.input":
                audio = payload.get("audio", "")
                audio_bytes = base64.b64decode(audio) if isinstance(audio, str) and audio else b""
                await _send_event(
                    websocket,
                    session.receive_audio(audio_bytes, payload.get("mimeType")),
                )
            elif event_type == "audio.commit":
                await _send_event(websocket, session.commit_audio())
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
            else:
                await _send_event(websocket, session.fail("Unsupported event type", "UNSUPPORTED_EVENT"))
                break
    except WebSocketDisconnect:
        return
    except (RealtimeSessionStateError, ValueError) as exc:
        if session.status.value != "error":
            await _send_event(websocket, session.fail(str(exc), "SESSION_ERROR"))
        await websocket.close(code=1011)
