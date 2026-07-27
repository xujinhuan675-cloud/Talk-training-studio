"""Authentication bridge endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel

from api.dependencies import (
    CurrentUser,
    extract_bearer_token,
    get_current_user,
    get_current_user_from_newapi_code,
    get_current_user_from_newapi_credentials,
    get_current_user_from_newapi_token,
)
from core.config import settings
from core.response import Response as ApiResponse
from core.response import success_response
from infrastructure.auth_session import create_session_cookie_value, session_cookie_options
from infrastructure.external.newapi_auth import (
    NewAPIAuthError,
    NewAPIAuthUnavailableError,
    NewAPITeam,
    NewAPITeamMember,
    assign_newapi_team_member as assign_newapi_team_member_control,
    fetch_newapi_team_members,
    search_newapi_team_users as search_newapi_team_users_control,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


class AuthUserDTO(BaseModel):
    provider: str
    user_id: str
    username: str | None = None
    display_name: str | None = None
    system_role: str
    business_role: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    newapi_base_url: str
    newapi_group: str | None = None
    newapi_gateway_base_url: str | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    quota_total: int | None = None
    request_count: int | None = None
    subscription_plan: str | None = None
    subscription_status: str | None = None


class NewAPIExchangeRequest(BaseModel):
    code: str | None = None
    access_token: str | None = None
    redirect_uri: str | None = None


class NewAPILoginRequest(BaseModel):
    username: str | None = None
    password: str | None = None


class AuthTeamDTO(BaseModel):
    id: str
    name: str
    group: str


class AuthTeamMemberDTO(BaseModel):
    id: int
    user_id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    system_role: str | None = None
    group: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    quota_remaining: int | None = None
    quota_used: int | None = None
    quota_total: int | None = None
    request_count: int | None = None
    in_team: bool = False


class AuthTeamMembersDTO(BaseModel):
    team: AuthTeamDTO
    members: list[AuthTeamMemberDTO]
    total: int


class AuthTeamUserSearchDTO(BaseModel):
    team: AuthTeamDTO
    users: list[AuthTeamMemberDTO]
    total: int


class AuthTeamMemberAssignRequest(BaseModel):
    user_id: int


def _auth_user_payload(current_user: CurrentUser) -> AuthUserDTO:
    provider = "newapi" if current_user.user_id.startswith("newapi:") else "mock"
    return AuthUserDTO(
        provider=provider,
        user_id=current_user.user_id,
        username=current_user.username,
        display_name=current_user.display_name,
        system_role=current_user.system_role,
        business_role=current_user.business_role,
        team_id=current_user.team_id,
        team_name=current_user.team_name or current_user.team_id,
        newapi_base_url=settings.NEWAPI_BASE_URL,
        newapi_group=current_user.newapi_group,
        newapi_gateway_base_url=(
            current_user.newapi_gateway_base_url or settings.NEWAPI_GATEWAY_BASE_URL
        ),
        quota_remaining=current_user.quota_remaining,
        quota_used=current_user.quota_used,
        quota_total=current_user.quota_total,
        request_count=current_user.request_count,
        subscription_plan=current_user.subscription_plan,
        subscription_status=current_user.subscription_status,
    )


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _newapi_group_for_current_user(current_user: CurrentUser) -> str:
    if not current_user.user_id.startswith("newapi:"):
        raise HTTPException(
            status_code=400,
            detail="Team membership is only available for signed-in account sessions",
        )
    group = _optional_text(current_user.newapi_group)
    team_id = _optional_text(current_user.team_id)
    if not group and team_id and team_id.startswith("newapi:"):
        group = _optional_text(team_id[len("newapi:") :])
    if not group:
        raise HTTPException(status_code=400, detail="Team group is not available")
    return group


def _require_team_manager(current_user: CurrentUser) -> None:
    if current_user.system_role not in {"admin", "leader"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


def _system_role_from_newapi_member_role(role: int | None) -> str | None:
    if role is None:
        return None
    if role >= settings.NEWAPI_ADMIN_ROLE_VALUE:
        return "admin"
    return "staff"


def _team_payload(team: NewAPITeam) -> AuthTeamDTO:
    return AuthTeamDTO(id=team.id, name=team.name, group=team.group)


def _team_member_payload(member: NewAPITeamMember) -> AuthTeamMemberDTO:
    quota_total = (
        member.quota + member.used_quota
        if member.quota is not None and member.used_quota is not None
        else None
    )
    return AuthTeamMemberDTO(
        id=member.id,
        user_id=member.id,
        username=member.username,
        display_name=member.display_name,
        email=member.email,
        system_role=_system_role_from_newapi_member_role(member.role),
        group=member.group,
        team_id=member.team_id,
        team_name=member.team_name,
        quota_remaining=member.quota,
        quota_used=member.used_quota,
        quota_total=quota_total,
        request_count=member.request_count,
        in_team=member.in_team,
    )


def _newapi_numeric_user_id(current_user: CurrentUser) -> int:
    raw_user_id = _optional_text(current_user.user_id) or ""
    if raw_user_id.startswith("newapi:"):
        raw_user_id = raw_user_id[len("newapi:") :]
    try:
        return int(raw_user_id)
    except ValueError:
        return 0


def _current_user_team_payload(current_user: CurrentUser, group: str) -> AuthTeamDTO:
    team_id = _optional_text(current_user.team_id) or f"newapi:{group}"
    team_name = _optional_text(current_user.team_name) or group
    return AuthTeamDTO(id=team_id, name=team_name, group=group)


def _current_user_team_member_payload(
    current_user: CurrentUser,
    team: AuthTeamDTO,
) -> AuthTeamMemberDTO:
    member_id = _newapi_numeric_user_id(current_user)
    username = (
        _optional_text(current_user.username)
        or _optional_text(current_user.display_name)
        or current_user.user_id
    )
    return AuthTeamMemberDTO(
        id=member_id,
        user_id=member_id,
        username=username,
        display_name=current_user.display_name,
        email=None,
        system_role=current_user.system_role,
        group=team.group,
        team_id=team.id,
        team_name=team.name,
        quota_remaining=current_user.quota_remaining,
        quota_used=current_user.quota_used,
        quota_total=current_user.quota_total,
        request_count=current_user.request_count,
        in_team=True,
    )


def _newapi_team_http_exception(exc: NewAPIAuthError) -> HTTPException:
    if isinstance(exc, NewAPIAuthUnavailableError):
        return HTTPException(status_code=503, detail="Team member service unavailable")
    return HTTPException(status_code=502, detail="Team member request was rejected")


def _set_talkwise_session_cookie(response: Response, current_user: CurrentUser) -> None:
    response.set_cookie(
        value=create_session_cookie_value(current_user),
        **session_cookie_options(),
    )


@router.post(
    "/newapi/session",
    summary="Verify a dashboard access token",
    response_model=ApiResponse[AuthUserDTO],
)
async def create_newapi_session(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    access_token = extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(status_code=401, detail="Access token required")

    current_user = await get_current_user_from_newapi_token(access_token)
    _set_talkwise_session_cookie(response, current_user)
    return success_response(
        data=_auth_user_payload(current_user),
        message="Session verified",
    )


@router.post(
    "/newapi/login",
    summary="Sign in with account username and password",
    response_model=ApiResponse[AuthUserDTO],
)
async def create_newapi_login_session(
    payload: NewAPILoginRequest,
    response: Response,
):
    username = _optional_text(payload.username)
    password = payload.password or ""
    if not username or not password:
        raise HTTPException(
            status_code=422,
            detail="Username and password are required",
        )

    current_user = await get_current_user_from_newapi_credentials(username, password)
    _set_talkwise_session_cookie(response, current_user)
    return success_response(
        data=_auth_user_payload(current_user),
        message="Session verified",
    )


@router.post(
    "/newapi/exchange",
    summary="Exchange a handoff code for a TalkWise browser session",
    response_model=ApiResponse[AuthUserDTO],
)
async def exchange_newapi_session(
    payload: NewAPIExchangeRequest,
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    code = _optional_text(payload.code)
    if code:
        current_user = await get_current_user_from_newapi_code(
            code,
            redirect_uri=_optional_text(payload.redirect_uri),
        )
        _set_talkwise_session_cookie(response, current_user)
        return success_response(
            data=_auth_user_payload(current_user),
            message="Authorization code exchanged",
        )

    access_token = _optional_text(payload.access_token) or extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="Authorization code or access token required",
        )

    current_user = await get_current_user_from_newapi_token(access_token)
    _set_talkwise_session_cookie(response, current_user)
    return success_response(
        data=_auth_user_payload(current_user),
        message="Session verified",
    )


@router.get(
    "/newapi/team/members",
    summary="List the current account group members",
    response_model=ApiResponse[AuthTeamMembersDTO],
)
async def list_newapi_team_members(current_user: CurrentUser = Depends(get_current_user)):
    group = _newapi_group_for_current_user(current_user)
    try:
        result = await fetch_newapi_team_members(
            group=group,
            base_url=settings.NEWAPI_BASE_URL,
            client_id=settings.NEWAPI_TALKWISE_CLIENT_ID,
            client_secret=settings.NEWAPI_TALKWISE_CLIENT_SECRET,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
        )
    except NewAPIAuthUnavailableError:
        team = _current_user_team_payload(current_user, group)
        member = _current_user_team_member_payload(current_user, team)
        return success_response(
            data=AuthTeamMembersDTO(team=team, members=[member], total=1),
            message="Team members loaded from current session",
        )
    except NewAPIAuthError as exc:
        raise _newapi_team_http_exception(exc) from exc

    return success_response(
        data=AuthTeamMembersDTO(
            team=_team_payload(result.team),
            members=[_team_member_payload(member) for member in result.members],
            total=result.total,
        ),
        message="Team members loaded",
    )


@router.get(
    "/newapi/team/users/search",
    summary="Search users for assignment to the current group",
    response_model=ApiResponse[AuthTeamUserSearchDTO],
)
async def search_newapi_team_users(
    keyword: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_team_manager(current_user)
    group = _newapi_group_for_current_user(current_user)
    try:
        result = await search_newapi_team_users_control(
            group=group,
            keyword=keyword,
            base_url=settings.NEWAPI_BASE_URL,
            client_id=settings.NEWAPI_TALKWISE_CLIENT_ID,
            client_secret=settings.NEWAPI_TALKWISE_CLIENT_SECRET,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
            limit=limit,
        )
    except NewAPIAuthError as exc:
        raise _newapi_team_http_exception(exc) from exc

    return success_response(
        data=AuthTeamUserSearchDTO(
            team=_team_payload(result.team),
            users=[_team_member_payload(user) for user in result.users],
            total=result.total,
        ),
        message="Users loaded",
    )


@router.post(
    "/newapi/team/members",
    summary="Assign a user to the current group",
    response_model=ApiResponse[AuthTeamMemberDTO],
)
async def assign_newapi_team_member(
    payload: AuthTeamMemberAssignRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    _require_team_manager(current_user)
    group = _newapi_group_for_current_user(current_user)
    try:
        member = await assign_newapi_team_member_control(
            group=group,
            user_id=payload.user_id,
            base_url=settings.NEWAPI_BASE_URL,
            client_id=settings.NEWAPI_TALKWISE_CLIENT_ID,
            client_secret=settings.NEWAPI_TALKWISE_CLIENT_SECRET,
            timeout_seconds=settings.NEWAPI_AUTH_TIMEOUT_SECONDS,
        )
    except NewAPIAuthError as exc:
        raise _newapi_team_http_exception(exc) from exc

    return success_response(
        data=_team_member_payload(member),
        message="Team member assigned",
    )


@router.post("/logout", summary="Clear the current TalkWise browser session")
async def logout(response: Response):
    response.delete_cookie(
        key=session_cookie_options()["key"],
        path=session_cookie_options()["path"],
        samesite=session_cookie_options()["samesite"],
        secure=session_cookie_options()["secure"],
        httponly=True,
    )
    return success_response(data={"signed_out": True}, message="Signed out")


@router.get("/me", summary="Get the current TalkWise user", response_model=ApiResponse[AuthUserDTO])
async def get_me(current_user: CurrentUser = Depends(get_current_user)):
    return success_response(data=_auth_user_payload(current_user), message="Authenticated")
