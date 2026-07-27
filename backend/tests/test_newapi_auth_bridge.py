from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.responses import Response

from api import dependencies as deps
from api.routes import auth as auth_routes
from infrastructure.auth_session import create_session_cookie_value, session_cookie_options
from infrastructure.external.newapi_auth import (
    NewAPIAuthError,
    NewAPIAuthUnavailableError,
    NewAPIIdentity,
    NewAPITeam,
    NewAPITeamMember,
    NewAPITeamMembersResult,
    NewAPITeamUserSearchResult,
)


async def _resolve_user(**overrides):
    params = {
        "talkwise_session": None,
        "authorization": None,
        "x_mock_user": None,
        "x_user_id": None,
        "x_user_role": None,
        "x_system_role": None,
        "x_role": None,
        "x_team_id": None,
        "q_mock_user": None,
        "q_user_id": None,
        "q_system_role": None,
        "q_team_id": None,
    }
    params.update(overrides)
    return await deps.get_current_user(**params)


def test_extract_bearer_token_accepts_case_insensitive_scheme() -> None:
    assert deps.extract_bearer_token("bearer live-token") == "live-token"
    assert deps.extract_bearer_token("Bearer   spaced-token  ") == "spaced-token"
    assert deps.extract_bearer_token("Token live-token") is None
    assert deps.extract_bearer_token("Bearer") is None


@pytest.mark.asyncio
async def test_newapi_bearer_token_maps_to_talkwise_user(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_identity(access_token: str, *, base_url: str, timeout_seconds: float):
        assert access_token == "live-token"
        assert base_url == "https://newapi.example"
        assert timeout_seconds == 2.5
        return NewAPIIdentity(
            id=42,
            username="alice",
            display_name="Alice Zhang",
            role=100,
            status=1,
            group="paid",
            quota=1200,
            used_quota=300,
            request_count=12,
            subscription_plan="pro",
            subscription_status="active",
            gateway_base_url="https://gateway.example/v1",
        )

    monkeypatch.setattr(deps.settings, "NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_TIMEOUT_SECONDS", 2.5)
    monkeypatch.setattr(deps, "fetch_newapi_identity", fake_fetch_identity)

    current_user = await _resolve_user(authorization="Bearer live-token")

    assert current_user.user_id == "newapi:42"
    assert current_user.username == "alice"
    assert current_user.display_name == "Alice Zhang"
    assert current_user.system_role == "admin"
    assert current_user.business_role == "sales"
    assert current_user.team_id == "newapi:paid"
    assert current_user.quota_remaining == 1200
    assert current_user.quota_used == 300
    assert current_user.quota_total == 1500
    assert current_user.subscription_plan == "pro"
    assert current_user.subscription_status == "active"
    assert current_user.newapi_gateway_base_url == "https://gateway.example/v1"


@pytest.mark.asyncio
async def test_newapi_authorization_code_exchange_maps_control_plane_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_exchange_code(
        code: str,
        *,
        base_url: str,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str | None,
        exchange_path: str,
        timeout_seconds: float,
    ):
        assert code == "handoff-code"
        assert base_url == "https://newapi.example"
        assert client_id == "talkwise-prod"
        assert client_secret == "client-secret"
        assert redirect_uri == "https://talkwise.example/login"
        assert exchange_path == "/api/talkwise/auth/exchange"
        assert timeout_seconds == 3.0
        return NewAPIIdentity(
            id=88,
            username="carol",
            display_name="Carol Chen",
            role=10,
            status=1,
            group="premium",
            team_id="team-acme",
            team_name="Acme Revenue",
            quota=900,
            used_quota=100,
            request_count=7,
            subscription_plan="enterprise",
            subscription_status="active",
            gateway_base_url="https://gateway.example/v1",
        )

    monkeypatch.setattr(deps.settings, "NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(deps.settings, "NEWAPI_TALKWISE_CLIENT_ID", "talkwise-prod")
    monkeypatch.setattr(deps.settings, "NEWAPI_TALKWISE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(deps.settings, "NEWAPI_TALKWISE_REDIRECT_URI", None)
    monkeypatch.setattr(
        deps.settings,
        "NEWAPI_TALKWISE_AUTH_EXCHANGE_PATH",
        "/api/talkwise/auth/exchange",
    )
    monkeypatch.setattr(deps, "exchange_newapi_authorization_code", fake_exchange_code)

    current_user = await deps.get_current_user_from_newapi_code(
        "handoff-code",
        redirect_uri="https://talkwise.example/login",
    )

    assert current_user.user_id == "newapi:88"
    assert current_user.username == "carol"
    assert current_user.system_role == "admin"
    assert current_user.team_id == "team-acme"
    assert current_user.team_name == "Acme Revenue"
    assert current_user.newapi_group == "premium"
    assert current_user.quota_remaining == 900
    assert current_user.quota_used == 100
    assert current_user.quota_total == 1000
    assert current_user.request_count == 7
    assert current_user.subscription_plan == "enterprise"
    assert current_user.subscription_status == "active"
    assert current_user.newapi_gateway_base_url == "https://gateway.example/v1"


@pytest.mark.asyncio
async def test_newapi_credentials_login_maps_to_talkwise_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_authenticate_credentials(
        username: str,
        password: str,
        *,
        base_url: str,
        login_path: str,
        timeout_seconds: float,
    ):
        assert username == "alice@example.com"
        assert password == "secret-password"
        assert base_url == "https://newapi.example"
        assert login_path == "/api/user/login"
        assert timeout_seconds == 2.5
        return NewAPIIdentity(
            id=42,
            username="alice",
            display_name="Alice Zhang",
            role=10,
            status=1,
            group="paid",
            quota=1200,
            used_quota=300,
            request_count=12,
        )

    monkeypatch.setattr(deps.settings, "NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setattr(deps.settings, "NEWAPI_LOGIN_PATH", "/api/user/login")
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_TIMEOUT_SECONDS", 2.5)
    monkeypatch.setattr(deps, "authenticate_newapi_credentials", fake_authenticate_credentials)

    current_user = await deps.get_current_user_from_newapi_credentials(
        "alice@example.com",
        "secret-password",
    )

    assert current_user.user_id == "newapi:42"
    assert current_user.username == "alice"
    assert current_user.display_name == "Alice Zhang"
    assert current_user.system_role == "admin"
    assert current_user.team_id == "newapi:paid"
    assert current_user.quota_remaining == 1200
    assert current_user.quota_used == 300
    assert current_user.quota_total == 1500


@pytest.mark.asyncio
async def test_newapi_exchange_route_sets_talkwise_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_user_from_code(code: str, *, redirect_uri: str | None = None):
        assert code == "handoff-code"
        assert redirect_uri == "https://talkwise.example/login"
        return deps.CurrentUser(
            user_id="newapi:88",
            username="carol",
            display_name="Carol Chen",
            system_role="leader",
            business_role="sales",
            team_id="team-acme",
            team_name="Acme Revenue",
            quota_remaining=900,
            quota_used=100,
            quota_total=1000,
            subscription_plan="enterprise",
            subscription_status="active",
        )

    monkeypatch.setattr(auth_routes, "get_current_user_from_newapi_code", fake_get_user_from_code)
    response = Response()

    result = await auth_routes.exchange_newapi_session(
        auth_routes.NewAPIExchangeRequest(
            code="handoff-code",
            redirect_uri="https://talkwise.example/login",
        ),
        response,
    )

    assert result.data is not None
    assert result.data.user_id == "newapi:88"
    assert result.data.team_name == "Acme Revenue"
    assert result.data.quota_remaining == 900
    assert result.data.subscription_plan == "enterprise"
    set_cookie = response.headers["set-cookie"]
    assert deps.settings.TALKWISE_SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_newapi_login_route_sets_talkwise_session_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_user_from_credentials(username: str, password: str):
        assert username == "alice@example.com"
        assert password == "secret-password"
        return deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            display_name="Alice Zhang",
            system_role="leader",
            business_role="sales",
            team_id="newapi:paid",
            team_name="paid",
            quota_remaining=1200,
            quota_used=300,
            quota_total=1500,
        )

    monkeypatch.setattr(
        auth_routes,
        "get_current_user_from_newapi_credentials",
        fake_get_user_from_credentials,
    )
    response = Response()

    result = await auth_routes.create_newapi_login_session(
        auth_routes.NewAPILoginRequest(
            username="  alice@example.com  ",
            password="secret-password",
        ),
        response,
    )

    assert result.data is not None
    assert result.data.user_id == "newapi:42"
    assert result.data.username == "alice"
    assert result.data.team_name == "paid"
    assert result.data.quota_total == 1500
    set_cookie = response.headers["set-cookie"]
    assert deps.settings.TALKWISE_SESSION_COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie


@pytest.mark.asyncio
async def test_newapi_exchange_route_requires_code_or_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.exchange_newapi_session(
            auth_routes.NewAPIExchangeRequest(),
            Response(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authorization code or access token required"


@pytest.mark.asyncio
async def test_newapi_team_members_route_uses_current_users_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_team_members(
        *,
        group: str,
        base_url: str,
        client_id: str,
        client_secret: str | None,
        timeout_seconds: float,
        limit: int | None = 100,
    ):
        assert group == "paid"
        assert base_url == "https://newapi.example"
        assert client_id == "talkwise-prod"
        assert client_secret == "client-secret"
        assert timeout_seconds == 3.0
        assert limit == 100
        return NewAPITeamMembersResult(
            team=NewAPITeam(id="newapi:paid", name="paid", group="paid"),
            members=[
                NewAPITeamMember(
                    id=42,
                    username="alice",
                    display_name="Alice Zhang",
                    role=10,
                    status=1,
                    group="paid",
                    team_id="newapi:paid",
                    team_name="paid",
                    quota=120,
                    used_quota=30,
                    request_count=8,
                    in_team=True,
                )
            ],
            total=1,
        )

    monkeypatch.setattr(auth_routes.settings, "NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setattr(auth_routes.settings, "NEWAPI_AUTH_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(auth_routes.settings, "NEWAPI_TALKWISE_CLIENT_ID", "talkwise-prod")
    monkeypatch.setattr(auth_routes.settings, "NEWAPI_TALKWISE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(auth_routes, "fetch_newapi_team_members", fake_fetch_team_members)

    result = await auth_routes.list_newapi_team_members(
        current_user=deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            system_role="staff",
            team_id="newapi:paid",
            team_name="paid",
            newapi_group="paid",
        )
    )

    assert result.data is not None
    assert result.data.team.id == "newapi:paid"
    assert result.data.members[0].user_id == 42
    assert result.data.members[0].system_role == "admin"
    assert result.data.members[0].quota_total == 150


@pytest.mark.asyncio
async def test_newapi_team_members_route_requires_newapi_group() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.list_newapi_team_members(
            current_user=deps.CurrentUser(
                user_id="newapi:42",
                username="alice",
                system_role="staff",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Team group is not available"


@pytest.mark.asyncio
async def test_newapi_team_members_route_falls_back_to_current_user_when_service_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch_team_members(**_kwargs):
        raise NewAPIAuthUnavailableError("service down")

    monkeypatch.setattr(auth_routes, "fetch_newapi_team_members", fake_fetch_team_members)

    result = await auth_routes.list_newapi_team_members(
        current_user=deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            display_name="Alice Zhang",
            system_role="leader",
            team_id="team-paid",
            team_name="Paid Team",
            newapi_group="paid",
            quota_remaining=120,
            quota_used=30,
            quota_total=150,
            request_count=8,
        )
    )

    assert result.data is not None
    assert result.data.team.id == "team-paid"
    assert result.data.team.name == "Paid Team"
    assert result.data.team.group == "paid"
    assert result.data.total == 1
    assert result.data.members[0].user_id == 42
    assert result.data.members[0].username == "alice"
    assert result.data.members[0].display_name == "Alice Zhang"
    assert result.data.members[0].system_role == "leader"
    assert result.data.members[0].team_id == "team-paid"
    assert result.data.members[0].team_name == "Paid Team"
    assert result.data.members[0].quota_remaining == 120
    assert result.data.members[0].quota_total == 150
    assert result.data.members[0].request_count == 8
    assert result.data.members[0].in_team is True


@pytest.mark.asyncio
async def test_newapi_team_user_search_requires_manager() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await auth_routes.search_newapi_team_users(
            keyword="bob",
            limit=20,
            current_user=deps.CurrentUser(
                user_id="newapi:42",
                username="alice",
                system_role="staff",
                team_id="newapi:paid",
                newapi_group="paid",
            ),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"


@pytest.mark.asyncio
async def test_newapi_team_user_search_uses_current_users_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_team_users(
        *,
        group: str,
        keyword: str,
        base_url: str,
        client_id: str,
        client_secret: str | None,
        timeout_seconds: float,
        limit: int | None = 20,
    ):
        assert group == "paid"
        assert keyword == "bob"
        assert limit == 10
        return NewAPITeamUserSearchResult(
            team=NewAPITeam(id="newapi:paid", name="paid", group="paid"),
            users=[
                NewAPITeamMember(
                    id=7,
                    username="bob",
                    display_name="Bob Li",
                    role=1,
                    status=1,
                    group="free",
                    team_id="newapi:free",
                    team_name="free",
                    in_team=False,
                )
            ],
            total=1,
        )

    monkeypatch.setattr(auth_routes, "search_newapi_team_users_control", fake_search_team_users)

    result = await auth_routes.search_newapi_team_users(
        keyword="bob",
        limit=10,
        current_user=deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            system_role="leader",
            team_id="newapi:paid",
            newapi_group="paid",
        ),
    )

    assert result.data is not None
    assert result.data.team.group == "paid"
    assert result.data.users[0].user_id == 7
    assert result.data.users[0].group == "free"
    assert result.data.users[0].in_team is False


@pytest.mark.asyncio
async def test_newapi_team_member_assign_uses_current_users_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_assign_team_member(
        *,
        group: str,
        user_id: int,
        base_url: str,
        client_id: str,
        client_secret: str | None,
        timeout_seconds: float,
    ):
        assert group == "paid"
        assert user_id == 7
        return NewAPITeamMember(
            id=7,
            username="bob",
            display_name="Bob Li",
            role=1,
            status=1,
            group="paid",
            team_id="newapi:paid",
            team_name="paid",
            quota=10,
            used_quota=2,
            in_team=True,
        )

    monkeypatch.setattr(auth_routes, "assign_newapi_team_member_control", fake_assign_team_member)

    result = await auth_routes.assign_newapi_team_member(
        auth_routes.AuthTeamMemberAssignRequest(user_id=7),
        current_user=deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            system_role="admin",
            team_id="newapi:paid",
            newapi_group="paid",
        ),
    )

    assert result.data is not None
    assert result.data.user_id == 7
    assert result.data.group == "paid"
    assert result.data.team_id == "newapi:paid"
    assert result.data.quota_total == 12


@pytest.mark.asyncio
async def test_newapi_admin_maps_to_talkwise_admin(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_identity(access_token: str, *, base_url: str, timeout_seconds: float):
        return NewAPIIdentity(id=7, username="manager", display_name=None, role=10)

    monkeypatch.setattr(deps, "fetch_newapi_identity", fake_fetch_identity)

    current_user = await _resolve_user(authorization="Bearer manager-token")

    assert current_user.system_role == "admin"
    assert current_user.team_id == deps.settings.NEWAPI_DEFAULT_TEAM_ID


@pytest.mark.asyncio
async def test_newapi_auth_enabled_requires_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ENABLED", True)
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", False)

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_user(x_mock_user="admin")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Access token required"


@pytest.mark.asyncio
async def test_mock_default_still_works_when_newapi_auth_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ENABLED", False)

    current_user = await _resolve_user()

    assert current_user.user_id == "user-admin-001"
    assert current_user.system_role == "admin"


@pytest.mark.asyncio
async def test_invalid_newapi_bearer_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_identity(access_token: str, *, base_url: str, timeout_seconds: float):
        raise NewAPIAuthError("rejected")

    monkeypatch.setattr(deps, "fetch_newapi_identity", fake_fetch_identity)

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_user(authorization="Bearer bad-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid access token"


@pytest.mark.asyncio
async def test_talkwise_session_cookie_maps_to_current_user_when_newapi_auth_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ENABLED", True)
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", False)

    cookie_value = create_session_cookie_value(
        deps.CurrentUser(
            user_id="newapi:42",
            username="alice",
            display_name="Alice Zhang",
            system_role="leader",
            business_role="sales",
            team_id="newapi:paid",
            team_name="paid",
            quota_remaining=100,
            quota_used=50,
            quota_total=150,
        )
    )

    current_user = await _resolve_user(talkwise_session=cookie_value)

    assert current_user.user_id == "newapi:42"
    assert current_user.username == "alice"
    assert current_user.system_role == "leader"
    assert current_user.team_id == "newapi:paid"
    assert current_user.team_name == "paid"
    assert current_user.quota_remaining == 100
    assert current_user.quota_total == 150


@pytest.mark.asyncio
async def test_tampered_talkwise_session_cookie_is_rejected_when_newapi_auth_is_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ENABLED", True)
    monkeypatch.setattr(deps.settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", False)

    cookie_value = create_session_cookie_value(
        deps.CurrentUser(user_id="newapi:42", username="alice", system_role="leader")
    )

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_user(talkwise_session=f"{cookie_value}tampered")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Access token required"


def test_session_cookie_options_are_httponly() -> None:
    options = session_cookie_options()

    assert options["key"] == deps.settings.TALKWISE_SESSION_COOKIE_NAME
    assert options["httponly"] is True
    assert options["samesite"] == "lax"
