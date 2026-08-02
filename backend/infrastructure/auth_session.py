"""Signed TalkWise browser session cookie helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import asdict
from typing import TYPE_CHECKING
from typing import Any, Mapping

from core.config import settings

if TYPE_CHECKING:
    from api.dependencies import CurrentUser


SESSION_COOKIE_VERSION = 1


class AuthSessionError(Exception):
    """Raised when a TalkWise browser session cookie is missing or invalid."""


def create_session_cookie_value(
    current_user: "CurrentUser",
    *,
    issued_at: int | None = None,
    ttl_seconds: int | None = None,
) -> str:
    now = int(time.time()) if issued_at is None else issued_at
    ttl = int(ttl_seconds or settings.TALKWISE_SESSION_TTL_SECONDS)
    payload = {
        "v": SESSION_COOKIE_VERSION,
        "iat": now,
        "exp": now + ttl,
        "user": asdict(current_user),
    }
    payload_b64 = _urlsafe_b64encode(_canonical_json(payload).encode("utf-8"))
    signature_b64 = _sign(payload_b64)
    return f"{payload_b64}.{signature_b64}"


def current_user_from_session_cookie(cookie_value: str | None) -> CurrentUser | None:
    if not cookie_value:
        return None

    try:
        payload = _decode_and_verify(cookie_value)
        if payload.get("v") != SESSION_COOKIE_VERSION:
            raise AuthSessionError("Unsupported session version")
        exp = int(payload.get("exp") or 0)
        if exp <= int(time.time()):
            raise AuthSessionError("Session expired")
        user = payload.get("user")
        if not isinstance(user, Mapping):
            raise AuthSessionError("Session missing user")
        user_id = _optional_text(user.get("user_id"))
        system_role = _normalize_product_system_role(user.get("system_role"))
        if not user_id or not system_role:
            raise AuthSessionError("Session has invalid user")
        from api.dependencies import CurrentUser

        return CurrentUser(
            user_id=user_id,
            system_role=system_role,
            team_id=_optional_text(user.get("team_id")),
            team_name=_optional_text(user.get("team_name")),
            team_role=_optional_text(user.get("team_role")),
            username=_optional_text(user.get("username")),
            display_name=_optional_text(user.get("display_name")),
            business_role=_optional_text(user.get("business_role")),
            newapi_group=_optional_text(user.get("newapi_group")),
            quota_remaining=_optional_int(user.get("quota_remaining")),
            quota_used=_optional_int(user.get("quota_used")),
            quota_total=_optional_int(user.get("quota_total")),
            request_count=_optional_int(user.get("request_count")),
            subscription_plan=_optional_text(user.get("subscription_plan")),
            subscription_status=_optional_text(user.get("subscription_status")),
            newapi_gateway_base_url=_optional_text(user.get("newapi_gateway_base_url")),
        )
    except AuthSessionError:
        return None
    except Exception:
        return None


def session_cookie_options() -> dict[str, Any]:
    return {
        "key": settings.TALKWISE_SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": not settings.DEBUG,
        "samesite": "lax",
        "max_age": int(settings.TALKWISE_SESSION_TTL_SECONDS),
        "path": "/",
    }


def _decode_and_verify(cookie_value: str) -> Mapping[str, Any]:
    payload_b64, separator, signature_b64 = cookie_value.partition(".")
    if not separator or not payload_b64 or not signature_b64:
        raise AuthSessionError("Session is malformed")
    expected_signature = _sign(payload_b64)
    if not hmac.compare_digest(signature_b64, expected_signature):
        raise AuthSessionError("Session signature mismatch")
    payload_bytes = _urlsafe_b64decode(payload_b64)
    payload = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise AuthSessionError("Session payload is invalid")
    return payload


def _sign(payload_b64: str) -> str:
    secret = (settings.SECRET_KEY or "").encode("utf-8")
    digest = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _urlsafe_b64encode(digest)


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_product_system_role(value: object | None) -> str | None:
    role = _optional_text(value)
    if role in {"admin", "root"}:
        return "admin"
    if role == "staff":
        return "staff"
    return None


__all__ = [
    "AuthSessionError",
    "create_session_cookie_value",
    "current_user_from_session_cookie",
    "session_cookie_options",
]
