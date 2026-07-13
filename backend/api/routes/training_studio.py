"""Training Studio API routes."""

from __future__ import annotations

import base64
import asyncio
import json
import mimetypes
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from application.services.training_studio.realtime_session import (
    RealtimeEvent,
    RealtimeSession,
    RealtimeSessionStateError,
)
from application.services.training_studio.catalog_service import (
    TrainingCatalogService,
    TrainingTaskConfigDTO,
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


class StoryBankRegisterDTO(BaseModel):
    answer_text: str = Field(..., min_length=20, max_length=20000)
    scenario_category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    tags: list[str] = Field(default_factory=list)


def _storybank_entry_to_dict(entry) -> dict:
    return entry.to_dict()


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
