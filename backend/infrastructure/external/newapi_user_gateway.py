# input: current NewAPI dashboard bearer token, core.config.settings
# output: request-scoped NewAPI user relay credentials and endpoint helpers
# owner: TalkWise platform integration
# pos: infrastructure - keeps per-user gateway billing credentials out of domain state and persistence
"""Request-scoped credentials for NewAPI native user billing."""

from __future__ import annotations

from contextvars import ContextVar, Token
from urllib.parse import urlsplit, urlunsplit

from core.config import settings

_USER_ACCESS_TOKEN: ContextVar[str | None] = ContextVar(
    "newapi_user_gateway_access_token",
    default=None,
)
_PLACEHOLDER_API_KEY = "newapi-user-session"


class NewAPIUserBillingContextError(RuntimeError):
    """Raised when gateway-only billing has no authenticated user context."""


class NewAPIUserGatewayContextMiddleware:
    """Bind and clear the inbound bearer for one HTTP or WebSocket scope."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        authorization = None
        for raw_name, raw_value in scope.get("headers", ()):
            if raw_name.lower() == b"authorization":
                authorization = raw_value.decode("latin-1")
                break
        context_token = bind_user_access_token(_bearer_token(authorization))
        try:
            await self.app(scope, receive, send)
        finally:
            reset_user_access_token(context_token)


def _bearer_token(authorization: str | None) -> str | None:
    value = str(authorization or "").strip()
    scheme, separator, token = value.partition(" ")
    if separator and scheme.lower() == "bearer":
        return token.strip() or None
    return None


def user_billing_enabled() -> bool:
    return bool(settings.NEWAPI_USER_BILLING_ENABLED)


def bind_user_access_token(access_token: str | None) -> Token[str | None]:
    value = str(access_token or "").strip() or None
    return _USER_ACCESS_TOKEN.set(value)


def reset_user_access_token(token: Token[str | None]) -> None:
    _USER_ACCESS_TOKEN.reset(token)


def current_user_access_token() -> str | None:
    return _USER_ACCESS_TOKEN.get()


def require_user_access_token() -> str:
    access_token = current_user_access_token()
    if access_token:
        return access_token
    raise NewAPIUserBillingContextError(
        "NewAPI user billing requires an authenticated dashboard access token"
    )


def runtime_api_key(configured_api_key: str | None = None) -> str | None:
    if user_billing_enabled():
        return _PLACEHOLDER_API_KEY
    return configured_api_key


def authorization_headers(configured_api_key: str | None = None) -> dict[str, str]:
    api_key = require_user_access_token() if user_billing_enabled() else configured_api_key
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def user_relay_base_url() -> str:
    configured = str(settings.NEWAPI_USER_RELAY_BASE_URL or "").strip()
    if configured:
        return configured.rstrip("/")
    return f"{settings.NEWAPI_BASE_URL.rstrip('/')}/pg"


def user_relay_realtime_url() -> str:
    configured = str(settings.NEWAPI_USER_RELAY_REALTIME_URL or "").strip()
    if configured:
        return configured.rstrip("/")

    parsed = urlsplit(user_relay_base_url())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    path = f"{parsed.path.rstrip('/')}/realtime"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


__all__ = [
    "NewAPIUserBillingContextError",
    "NewAPIUserGatewayContextMiddleware",
    "authorization_headers",
    "bind_user_access_token",
    "current_user_access_token",
    "require_user_access_token",
    "reset_user_access_token",
    "runtime_api_key",
    "user_billing_enabled",
    "user_relay_base_url",
    "user_relay_realtime_url",
]
