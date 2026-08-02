from __future__ import annotations

import pytest

from core.config import settings
from infrastructure.external.newapi_user_gateway import (
    NewAPIUserBillingContextError,
    NewAPIUserGatewayContextMiddleware,
    authorization_headers,
    bind_user_access_token,
    current_user_access_token,
    reset_user_access_token,
    runtime_api_key,
    user_relay_base_url,
    user_relay_realtime_url,
)


@pytest.fixture(autouse=True)
def _clear_gateway_context():
    token = bind_user_access_token(None)
    try:
        yield
    finally:
        reset_user_access_token(token)


def test_user_gateway_derives_http_and_websocket_relay_urls(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEWAPI_BASE_URL", "https://talkwise.example.com")
    monkeypatch.setattr(settings, "NEWAPI_USER_RELAY_BASE_URL", None)
    monkeypatch.setattr(settings, "NEWAPI_USER_RELAY_REALTIME_URL", None)

    assert user_relay_base_url() == "https://talkwise.example.com/pg"
    assert user_relay_realtime_url() == "wss://talkwise.example.com/pg/realtime"


def test_user_billing_uses_current_dashboard_token_instead_of_static_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    bind_user_access_token("dashboard-user-token")

    assert runtime_api_key("shared-service-key") == "newapi-user-session"
    assert authorization_headers("shared-service-key") == {
        "Authorization": "Bearer dashboard-user-token"
    }


def test_user_billing_never_falls_back_to_static_key_without_login(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)

    with pytest.raises(NewAPIUserBillingContextError, match="authenticated dashboard"):
        authorization_headers("shared-service-key")


@pytest.mark.asyncio
async def test_gateway_context_middleware_clears_token_after_websocket_scope() -> None:
    seen_tokens: list[str | None] = []

    async def app(scope, receive, send) -> None:
        seen_tokens.append(current_user_access_token())

    middleware = NewAPIUserGatewayContextMiddleware(app)
    await middleware(
        {
            "type": "websocket",
            "headers": [(b"authorization", b"Bearer websocket-user-token")],
        },
        None,
        None,
    )

    assert seen_tokens == ["websocket-user-token"]
    assert current_user_access_token() is None
