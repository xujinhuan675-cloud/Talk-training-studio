"""Scope-safe team analytics endpoints for the NewAPI training module."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.dependencies import CurrentUser, get_current_user
from application.services.training_studio.team_analytics_service import (
    TeamTrainingAnalyticsService,
)
from core.config import settings
from core.response import success_response
from domain.common.exceptions import DomainValidationException
from domain.training_studio.session_repository import TrainingSessionAccessScope
from infrastructure.external.newapi_auth import (
    NewAPIAuthError,
    NewAPIAuthUnavailableError,
    fetch_newapi_team_members,
)
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

# Nested below the established Training Studio API so NewAPI's existing
# same-origin `/api/talkwise/training/*` proxy can carry these requests.
router = APIRouter(prefix="/training-studio/team", tags=["Training Team Analytics"])
_team_analytics_service = TeamTrainingAnalyticsService(uow_factory=SQLAlchemyUnitOfWork)


def get_team_training_analytics_service() -> TeamTrainingAnalyticsService:
    return _team_analytics_service


def team_analytics_scope_for_current_user(
    current_user: CurrentUser,
) -> TrainingSessionAccessScope:
    if not (current_user.is_admin or current_user.is_leader):
        raise HTTPException(
            status_code=403,
            detail="Team analytics requires a team administrator or leader role",
        )
    team_id = (current_user.team_id or "").strip()
    if not team_id:
        raise HTTPException(
            status_code=422,
            detail="Team analytics is unavailable without a team assignment",
        )
    return TrainingSessionAccessScope(
        user_id=current_user.user_id,
        team_id=team_id,
        include_team_scope=True,
    )


async def team_member_names_for_current_user(
    current_user: CurrentUser,
) -> dict[str, str]:
    """Resolve names only from the authenticated user's NewAPI group."""

    group = (current_user.newapi_group or "").strip()
    if not group:
        return {}
    try:
        result = await fetch_newapi_team_members(
            group=group,
            base_url=settings.NEWAPI_BASE_URL,
            client_id=settings.NEWAPI_TALKWISE_CLIENT_ID,
            client_secret=settings.NEWAPI_TALKWISE_CLIENT_SECRET,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
        )
    except (NewAPIAuthError, NewAPIAuthUnavailableError):
        return {}

    return {
        f"newapi:{member.id}": member.display_name or member.username
        for member in result.members
        if member.display_name or member.username
    }


def with_member_names(items, member_names: dict[str, str]):
    return [
        item.model_copy(update={"member_name": member_names.get(item.member_id)})
        for item in items
    ]


@router.get("/competencies", summary="List scoped team competency rankings")
async def list_team_competency_rankings(
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    svc: TeamTrainingAnalyticsService = Depends(get_team_training_analytics_service),
):
    try:
        items, total = await svc.list_competency_rankings(
            skip=skip,
            limit=limit,
            access_scope=team_analytics_scope_for_current_user(current_user),
        )
    except DomainValidationException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    member_names = await team_member_names_for_current_user(current_user)
    response.headers["X-Total-Count"] = str(total)
    return success_response(
        data=[
            item.model_dump(mode="json")
            for item in with_member_names(items, member_names)
        ]
    )


@router.get("/scenarios", summary="List scoped team scenario rankings")
async def list_team_scenario_rankings(
    response: Response,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    svc: TeamTrainingAnalyticsService = Depends(get_team_training_analytics_service),
):
    try:
        items, total = await svc.list_scenario_rankings(
            skip=skip,
            limit=limit,
            access_scope=team_analytics_scope_for_current_user(current_user),
        )
    except DomainValidationException as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    member_names = await team_member_names_for_current_user(current_user)
    response.headers["X-Total-Count"] = str(total)
    return success_response(
        data=[
            item.model_dump(mode="json")
            for item in with_member_names(items, member_names)
        ]
    )
