"""Authentication bridge endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel

from api.dependencies import (
    CurrentUser,
    extract_bearer_token,
    get_current_user,
    get_current_user_from_newapi_code,
    get_current_user_from_newapi_token,
)
from core.config import settings
from core.response import Response as ApiResponse
from core.response import success_response
from infrastructure.auth_session import create_session_cookie_value, session_cookie_options


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


def _set_talkwise_session_cookie(response: Response, current_user: CurrentUser) -> None:
    response.set_cookie(
        value=create_session_cookie_value(current_user),
        **session_cookie_options(),
    )


@router.post(
    "/newapi/session",
    summary="Verify a NewAPI dashboard access token",
    response_model=ApiResponse[AuthUserDTO],
)
async def create_newapi_session(
    response: Response,
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    access_token = extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(status_code=401, detail="NewAPI access token required")

    current_user = await get_current_user_from_newapi_token(access_token)
    _set_talkwise_session_cookie(response, current_user)
    return success_response(
        data=_auth_user_payload(current_user),
        message="NewAPI session verified",
    )


@router.post(
    "/newapi/exchange",
    summary="Exchange a NewAPI handoff code for a TalkWise browser session",
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
            message="NewAPI authorization code exchanged",
        )

    access_token = _optional_text(payload.access_token) or extract_bearer_token(authorization)
    if not access_token:
        raise HTTPException(
            status_code=401,
            detail="NewAPI authorization code or access token required",
        )

    current_user = await get_current_user_from_newapi_token(access_token)
    _set_talkwise_session_cookie(response, current_user)
    return success_response(
        data=_auth_user_payload(current_user),
        message="NewAPI session verified",
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
