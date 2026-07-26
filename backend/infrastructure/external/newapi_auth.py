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
        async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False) as client:
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
    "exchange_newapi_authorization_code",
    "fetch_newapi_identity",
]
