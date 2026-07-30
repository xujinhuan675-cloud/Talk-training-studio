"""Read-only TalkWise announcement API backed by NewAPI public endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import CurrentUser, get_current_user
from core.config import settings
from core.response import Response as ApiResponse
from core.response import success_response
from infrastructure.external.newapi_announcements import (
    AnnouncementSnapshot,
    NewAPIAnnouncementsUnavailableError,
    fetch_newapi_announcements,
)


router = APIRouter(prefix="/announcements", tags=["Announcements"])


class AnnouncementDTO(BaseModel):
    id: str
    content: str
    extra: str | None = None
    published_at: str | None = None
    type: str = "default"


class AnnouncementFeedDTO(BaseModel):
    state: Literal["available", "unavailable"]
    notice: str | None = None
    announcements: list[AnnouncementDTO] = Field(default_factory=list)


def _available_payload(snapshot: AnnouncementSnapshot) -> AnnouncementFeedDTO:
    return AnnouncementFeedDTO(
        state="available",
        notice=snapshot.notice,
        announcements=[AnnouncementDTO(**item.__dict__) for item in snapshot.announcements],
    )


def _unavailable_payload() -> AnnouncementFeedDTO:
    return AnnouncementFeedDTO(state="unavailable")


@router.get("", response_model=ApiResponse[AnnouncementFeedDTO])
async def get_announcements(
    _: CurrentUser = Depends(get_current_user),
):
    """Return normalized public notices. This route intentionally has no mutations."""

    try:
        snapshot = await fetch_newapi_announcements(
            base_url=settings.NEWAPI_BASE_URL,
            timeout_seconds=settings.NEWAPI_ANNOUNCEMENT_TIMEOUT_SECONDS,
            cache_ttl_seconds=settings.NEWAPI_ANNOUNCEMENT_CACHE_TTL_SECONDS,
            max_items=settings.NEWAPI_ANNOUNCEMENT_MAX_ITEMS,
        )
    except NewAPIAnnouncementsUnavailableError:
        return success_response(
            data=_unavailable_payload(),
            message="Announcements unavailable",
        )
    return success_response(data=_available_payload(snapshot), message="Announcements loaded")
