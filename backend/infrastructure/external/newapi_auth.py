"""NewAPI control-plane authentication client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class NewAPIAuthError(Exception):
    """Raised when NewAPI rejects a dashboard credential."""


class NewAPIAuthUnavailableError(NewAPIAuthError):
    """Raised when TalkWise cannot reach NewAPI auth services."""


@dataclass(frozen=True)
class NewAPIIdentity:
    id: int
    username: str
    display_name: str | None
    role: int
    status: int | None = None
    group: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    quota: int | None = None
    used_quota: int | None = None
    request_count: int | None = None
    subscription_plan: str | None = None
    subscription_status: str | None = None
    gateway_base_url: str | None = None


@dataclass(frozen=True)
class NewAPITeam:
    id: str
    name: str
    group: str


@dataclass(frozen=True)
class NewAPITeamMember:
    id: int
    username: str
    display_name: str | None = None
    email: str | None = None
    role: int | None = None
    status: int | None = None
    group: str | None = None
    team_id: str | None = None
    team_name: str | None = None
    quota: int | None = None
    used_quota: int | None = None
    request_count: int | None = None
    in_team: bool = False


@dataclass(frozen=True)
class NewAPITeamMembersResult:
    team: NewAPITeam
    members: list[NewAPITeamMember]
    total: int


@dataclass(frozen=True)
class NewAPITeamUserSearchResult:
    team: NewAPITeam
    users: list[NewAPITeamMember]
    total: int


def _coerce_int(value: Any, *, field_name: str, required: bool = True) -> int | None:
    if value is None:
        if required:
            raise NewAPIAuthError(f"NewAPI response missing {field_name}")
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise NewAPIAuthError(f"NewAPI response has invalid {field_name}") from exc


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _first_mapping(data: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    for key in keys:
        candidate = _optional_mapping(data.get(key))
        if candidate is not None:
            return candidate
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _join_url(base_url: str, path: str) -> str:
    trimmed_path = path.strip()
    if not trimmed_path:
        raise NewAPIAuthError("NewAPI exchange path is required")
    if trimmed_path.startswith("http://") or trimmed_path.startswith("https://"):
        return trimmed_path
    return f"{base_url.rstrip('/')}/{trimmed_path.lstrip('/')}"


def _identity_from_payload(payload: Mapping[str, Any]) -> NewAPIIdentity:
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise NewAPIAuthError("NewAPI response missing user data")

    user_data = _first_mapping(data, "user", "profile", "identity") or data
    subscription_data = _first_mapping(data, "subscription", "billing", "plan")
    gateway_data = _first_mapping(data, "gateway", "relay")
    team_data = _first_mapping(data, "team", "organization", "tenant")

    user_id = _coerce_int(
        _first_present(user_data.get("id"), user_data.get("user_id")),
        field_name="id",
    )
    role = _coerce_int(user_data.get("role"), field_name="role")
    status = _coerce_int(user_data.get("status"), field_name="status", required=False)
    if user_id is None or role is None:
        raise NewAPIAuthError("NewAPI response missing required user fields")
    username = _coerce_optional_text(user_data.get("username"))
    if not username:
        raise NewAPIAuthError("NewAPI response missing username")

    if status is not None and status != 1:
        raise NewAPIAuthError("NewAPI user is not enabled")

    return NewAPIIdentity(
        id=user_id,
        username=username,
        display_name=_coerce_optional_text(
            _first_present(user_data.get("display_name"), user_data.get("displayName"))
        ),
        role=role,
        status=status,
        group=_coerce_optional_text(user_data.get("group")),
        team_id=_coerce_optional_text(
            _first_present(
                data.get("team_id"),
                user_data.get("team_id"),
                team_data.get("id") if team_data else None,
            )
        ),
        team_name=_coerce_optional_text(
            _first_present(
                data.get("team_name"),
                user_data.get("team_name"),
                team_data.get("name") if team_data else None,
            )
        ),
        quota=_coerce_int(
            _first_present(data.get("quota"), user_data.get("quota")),
            field_name="quota",
            required=False,
        ),
        used_quota=_coerce_int(
            _first_present(data.get("used_quota"), user_data.get("used_quota")),
            field_name="used_quota",
            required=False,
        ),
        request_count=_coerce_int(
            _first_present(data.get("request_count"), user_data.get("request_count")),
            field_name="request_count",
            required=False,
        ),
        subscription_plan=_coerce_optional_text(
            _first_present(
                data.get("subscription_plan"),
                subscription_data.get("plan") if subscription_data else None,
                subscription_data.get("name") if subscription_data else None,
            )
        ),
        subscription_status=_coerce_optional_text(
            _first_present(
                data.get("subscription_status"),
                subscription_data.get("status") if subscription_data else None,
            )
        ),
        gateway_base_url=_coerce_optional_text(
            _first_present(
                data.get("gateway_base_url"),
                gateway_data.get("base_url") if gateway_data else None,
                gateway_data.get("url") if gateway_data else None,
            )
        ),
    )


def _team_from_payload(payload: Any, *, fallback_group: str) -> NewAPITeam:
    data = _optional_mapping(payload) or {}
    group = _coerce_optional_text(_first_present(data.get("group"), fallback_group))
    if not group:
        raise NewAPIAuthError("NewAPI response missing team group")
    team_id = _coerce_optional_text(data.get("id")) or f"newapi:{group}"
    team_name = _coerce_optional_text(data.get("name")) or group
    return NewAPITeam(id=team_id, name=team_name, group=group)


def _team_member_from_payload(payload: Any, *, team: NewAPITeam) -> NewAPITeamMember:
    data = _optional_mapping(payload)
    if data is None:
        raise NewAPIAuthError("NewAPI response has invalid team member data")

    user_id = _coerce_int(
        _first_present(data.get("id"), data.get("user_id")),
        field_name="user_id",
    )
    if user_id is None:
        raise NewAPIAuthError("NewAPI response missing team member id")
    username = _coerce_optional_text(data.get("username"))
    if not username:
        raise NewAPIAuthError("NewAPI response missing team member username")

    group = _coerce_optional_text(_first_present(data.get("group"), team.group))
    team_id = _coerce_optional_text(data.get("team_id")) or (
        f"newapi:{group}" if group else team.id
    )
    team_name = _coerce_optional_text(data.get("team_name")) or group or team.name
    return NewAPITeamMember(
        id=user_id,
        username=username,
        display_name=_coerce_optional_text(
            _first_present(data.get("display_name"), data.get("displayName"))
        ),
        email=_coerce_optional_text(data.get("email")),
        role=_coerce_int(data.get("role"), field_name="role", required=False),
        status=_coerce_int(data.get("status"), field_name="status", required=False),
        group=group,
        team_id=team_id,
        team_name=team_name,
        quota=_coerce_int(data.get("quota"), field_name="quota", required=False),
        used_quota=_coerce_int(
            data.get("used_quota"),
            field_name="used_quota",
            required=False,
        ),
        request_count=_coerce_int(
            data.get("request_count"),
            field_name="request_count",
            required=False,
        ),
        in_team=_coerce_bool(data.get("in_team"), default=group == team.group),
    )


def _extract_success_data(payload: Any, *, service_label: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise NewAPIAuthUnavailableError(f"{service_label} returned invalid payload")
    if payload.get("success") is False:
        message = _coerce_optional_text(payload.get("message")) or (
            f"{service_label} request was rejected"
        )
        raise NewAPIAuthError(message)
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise NewAPIAuthUnavailableError(f"{service_label} returned invalid data")
    return data


def _normalize_limit(value: int | None, *, default: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(parsed, maximum)


async def _post_talkwise_control(
    *,
    base_url: str,
    client_id: str,
    client_secret: str | None,
    path: str,
    timeout_seconds: float,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    client = client_id.strip()
    if not client:
        raise NewAPIAuthError("NewAPI TalkWise client id is required")
    secret = _coerce_optional_text(client_secret)
    if not secret:
        raise NewAPIAuthError("NewAPI TalkWise client secret is required")

    endpoint = _join_url(base_url, path)
    body: dict[str, Any] = {
        "client_id": client,
        "client_secret": secret,
        **dict(payload),
    }
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client_session:
            response = await client_session.post(
                endpoint,
                headers={"Accept": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise NewAPIAuthUnavailableError("NewAPI team service unavailable") from exc

    if response.status_code in {400, 401, 403, 409}:
        raise NewAPIAuthError("NewAPI team request was rejected")
    if response.status_code >= 400:
        raise NewAPIAuthUnavailableError("NewAPI team service returned an error")

    try:
        response_payload = response.json()
    except ValueError as exc:
        raise NewAPIAuthUnavailableError("NewAPI team service returned invalid JSON") from exc

    return _extract_success_data(response_payload, service_label="NewAPI team service")


async def fetch_newapi_identity(
    access_token: str,
    *,
    base_url: str,
    timeout_seconds: float,
) -> NewAPIIdentity:
    token = access_token.strip()
    if not token:
        raise NewAPIAuthError("NewAPI access token is required")

    endpoint = f"{base_url.rstrip('/')}/api/user/self"
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.get(
                endpoint,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        raise NewAPIAuthUnavailableError("NewAPI authentication service unavailable") from exc

    if response.status_code in {401, 403}:
        raise NewAPIAuthError("NewAPI access token was rejected")
    if response.status_code >= 400:
        raise NewAPIAuthUnavailableError("NewAPI authentication service returned an error")

    try:
        payload = response.json()
    except ValueError as exc:
        raise NewAPIAuthUnavailableError(
            "NewAPI authentication service returned invalid JSON"
        ) from exc

    if not isinstance(payload, Mapping) or payload.get("success") is not True:
        raise NewAPIAuthError("NewAPI access token was rejected")

    return _identity_from_payload(payload)


async def fetch_newapi_team_members(
    *,
    group: str,
    base_url: str,
    client_id: str,
    client_secret: str | None,
    timeout_seconds: float,
    limit: int | None = 100,
) -> NewAPITeamMembersResult:
    team_group = _coerce_optional_text(group)
    if not team_group:
        raise NewAPIAuthError("NewAPI team group is required")

    data = await _post_talkwise_control(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        path="/api/talkwise/team/members",
        timeout_seconds=timeout_seconds,
        payload={
            "group": team_group,
            "limit": _normalize_limit(limit, default=100, maximum=200),
        },
    )
    team = _team_from_payload(data.get("team"), fallback_group=team_group)
    members_raw = data.get("members")
    members = [
        _team_member_from_payload(member, team=team)
        for member in members_raw
        if isinstance(member, Mapping)
    ] if isinstance(members_raw, list) else []
    total = _coerce_int(data.get("total"), field_name="total", required=False)
    return NewAPITeamMembersResult(
        team=team,
        members=members,
        total=total if total is not None else len(members),
    )


async def search_newapi_team_users(
    *,
    group: str,
    keyword: str,
    base_url: str,
    client_id: str,
    client_secret: str | None,
    timeout_seconds: float,
    limit: int | None = 20,
) -> NewAPITeamUserSearchResult:
    team_group = _coerce_optional_text(group)
    if not team_group:
        raise NewAPIAuthError("NewAPI team group is required")
    search_keyword = _coerce_optional_text(keyword)
    if not search_keyword:
        raise NewAPIAuthError("NewAPI team user search keyword is required")

    data = await _post_talkwise_control(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        path="/api/talkwise/team/users/search",
        timeout_seconds=timeout_seconds,
        payload={
            "group": team_group,
            "keyword": search_keyword,
            "limit": _normalize_limit(limit, default=20, maximum=100),
        },
    )
    team = _team_from_payload(data.get("team"), fallback_group=team_group)
    users_raw = data.get("users")
    users = [
        _team_member_from_payload(user, team=team)
        for user in users_raw
        if isinstance(user, Mapping)
    ] if isinstance(users_raw, list) else []
    total = _coerce_int(data.get("total"), field_name="total", required=False)
    return NewAPITeamUserSearchResult(
        team=team,
        users=users,
        total=total if total is not None else len(users),
    )


async def assign_newapi_team_member(
    *,
    group: str,
    user_id: int,
    base_url: str,
    client_id: str,
    client_secret: str | None,
    timeout_seconds: float,
) -> NewAPITeamMember:
    team_group = _coerce_optional_text(group)
    if not team_group:
        raise NewAPIAuthError("NewAPI team group is required")
    member_id = _coerce_int(user_id, field_name="user_id")
    if member_id is None:
        raise NewAPIAuthError("NewAPI team member id is required")

    data = await _post_talkwise_control(
        base_url=base_url,
        client_id=client_id,
        client_secret=client_secret,
        path="/api/talkwise/team/members/assign",
        timeout_seconds=timeout_seconds,
        payload={"group": team_group, "user_id": member_id},
    )
    team = _team_from_payload(data.get("team"), fallback_group=team_group)
    return _team_member_from_payload(data.get("member"), team=team)


async def exchange_newapi_authorization_code(
    code: str,
    *,
    base_url: str,
    client_id: str,
    client_secret: str | None,
    redirect_uri: str | None,
    exchange_path: str,
    timeout_seconds: float,
) -> NewAPIIdentity:
    authorization_code = code.strip()
    if not authorization_code:
        raise NewAPIAuthError("NewAPI authorization code is required")

    client = client_id.strip()
    if not client:
        raise NewAPIAuthError("NewAPI TalkWise client id is required")

    body: dict[str, Any] = {
        "code": authorization_code,
        "client_id": client,
    }
    secret = _coerce_optional_text(client_secret)
    if secret:
        body["client_secret"] = secret
    redirect = _coerce_optional_text(redirect_uri)
    if redirect:
        body["redirect_uri"] = redirect

    endpoint = _join_url(base_url, exchange_path)
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client_session:
            response = await client_session.post(
                endpoint,
                headers={"Accept": "application/json"},
                json=body,
            )
    except httpx.HTTPError as exc:
        raise NewAPIAuthUnavailableError("NewAPI authorization service unavailable") from exc

    if response.status_code in {400, 401, 403, 409}:
        raise NewAPIAuthError("NewAPI authorization code was rejected")
    if response.status_code >= 400:
        raise NewAPIAuthUnavailableError("NewAPI authorization service returned an error")

    try:
        payload = response.json()
    except ValueError as exc:
        raise NewAPIAuthUnavailableError(
            "NewAPI authorization service returned invalid JSON"
        ) from exc

    if not isinstance(payload, Mapping):
        raise NewAPIAuthUnavailableError("NewAPI authorization service returned invalid payload")
    if payload.get("success") is False:
        raise NewAPIAuthError("NewAPI authorization code was rejected")

    return _identity_from_payload(payload)


__all__ = [
    "NewAPIAuthError",
    "NewAPIAuthUnavailableError",
    "NewAPIIdentity",
    "NewAPITeam",
    "NewAPITeamMember",
    "NewAPITeamMembersResult",
    "NewAPITeamUserSearchResult",
    "assign_newapi_team_member",
    "exchange_newapi_authorization_code",
    "fetch_newapi_identity",
    "fetch_newapi_team_members",
    "search_newapi_team_users",
]
