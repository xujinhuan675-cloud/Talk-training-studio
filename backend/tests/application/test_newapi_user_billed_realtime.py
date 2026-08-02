from __future__ import annotations

from core.config import settings
from infrastructure.external.newapi_user_gateway import (
    bind_user_access_token,
    reset_user_access_token,
)
from infrastructure.external.pipecat import realtime_pipeline


def test_pipecat_uses_current_user_gateway_for_all_openai_services(monkeypatch) -> None:
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "NEWAPI_USER_RELAY_BASE_URL",
        "https://gateway.example.com/pg",
    )
    monkeypatch.setattr(
        settings,
        "NEWAPI_USER_RELAY_REALTIME_URL",
        "wss://gateway.example.com/pg/realtime",
    )
    context_token = bind_user_access_token("dashboard-user-token")
    try:
        assert realtime_pipeline._openai_api_key({}) == "dashboard-user-token"
        assert realtime_pipeline._openrouter_api_key({}) == "dashboard-user-token"
        assert (
            realtime_pipeline._llm_base_url({}, {}, "openai")
            == "https://gateway.example.com/pg"
        )
        assert (
            realtime_pipeline.user_relay_realtime_url()
            == "wss://gateway.example.com/pg/realtime"
        )
    finally:
        reset_user_access_token(context_token)
