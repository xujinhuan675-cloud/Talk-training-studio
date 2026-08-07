"""HTTP adapter for the MVP live meeting-assist turn loop."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.dependencies import CurrentUser, get_current_user
from application.ports.stt import STTPort
from application.services.training_studio.live_assist_service import (
    LiveAssistError,
    LiveAssistService,
    decode_audio_base64,
)
from application.services.training_studio.live_guidance_service import (
    TrainingLiveGuidanceService,
)
from domain.training_studio.session_repository import TrainingSessionAccessScope
from core.response import success_response

router = APIRouter(prefix="/training-assist", tags=["training-assist"])


class LiveAssistTurnRequest(BaseModel):
    """One completed meeting turn from text or a browser-captured audio segment."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str | None = Field(default=None, max_length=20_000)
    audio_base64: str | None = Field(default=None, alias="audioBase64", max_length=22_000_000)
    audio_format: str = Field(default="webm", alias="audioFormat", min_length=1, max_length=20)
    language: str = Field(default="zh", min_length=1, max_length=20)
    speaker_source: Literal["microphone", "system", "mixed"] = Field(
        default="microphone", alias="speakerSource"
    )
    speaker_hint: str | None = Field(default=None, alias="speakerHint", max_length=80)
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_input(self) -> "LiveAssistTurnRequest":
        if not (self.text and self.text.strip()) and not self.audio_base64:
            raise ValueError("Provide text or audioBase64")
        return self


def get_training_assist_session_service():
    """Resolve the shared session service lazily to keep route imports isolated."""

    from api.routes.training_studio import get_training_session_service

    return get_training_session_service()


def get_training_assist_guidance_service() -> TrainingLiveGuidanceService:
    """Reuse the configured live-guidance service (including optional LLM adapter)."""

    from api.routes.training_studio import get_live_guidance_service

    return get_live_guidance_service()


def get_training_assist_stt() -> STTPort | None:
    from infrastructure.external.voice import get_stt_client

    return get_stt_client()


def get_live_assist_service(
    stt: STTPort | None = Depends(get_training_assist_stt),
    guidance: TrainingLiveGuidanceService = Depends(get_training_assist_guidance_service),
) -> LiveAssistService:
    return LiveAssistService(stt=stt, guidance=guidance)


def _access_scope(current_user: CurrentUser) -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id=current_user.user_id,
        team_id=current_user.team_id,
        include_team_scope=current_user.can_manage_team,
    )


@router.post(
    "/sessions/{session_id}/turns",
    summary="Process one live meeting turn and return coaching guidance",
)
async def process_live_assist_turn(
    session_id: str,
    body: LiveAssistTurnRequest,
    assist: LiveAssistService = Depends(get_live_assist_service),
    session_service=Depends(get_training_assist_session_service),
    current_user: CurrentUser = Depends(get_current_user),
):
    audio: bytes | None = None
    if body.audio_base64:
        try:
            audio = decode_audio_base64(body.audio_base64)
        except LiveAssistError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc
    try:
        data = await assist.process_turn(
            session_id,
            user_id=current_user.user_id,
            session_service=session_service,
            access_scope=_access_scope(current_user),
            text=body.text,
            audio=audio,
            audio_format=body.audio_format,
            language=body.language,
            speaker_source=body.speaker_source,
            speaker_hint=body.speaker_hint,
            client_metadata=body.metadata,
        )
    except LiveAssistError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc) or "Training session is outside scope") from exc
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return success_response(data=data)


__all__ = [
    "LiveAssistTurnRequest",
    "get_live_assist_service",
    "get_training_assist_guidance_service",
    "get_training_assist_session_service",
    "get_training_assist_stt",
    "process_live_assist_turn",
    "router",
]
