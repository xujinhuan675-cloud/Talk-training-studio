from __future__ import annotations

from core.config import LLMSettings, settings
import infrastructure.external.llm as llm_lifecycle


class _FakeGatewayLLM:
    instances: list["_FakeGatewayLLM"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.instances.append(self)


async def test_llm_lifecycle_has_no_static_direct_fallback(monkeypatch) -> None:
    original_llm = settings.llm
    llm_lifecycle._llm_client = None
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", False)
    settings.llm = LLMSettings(
        api_key="legacy-static-key",
        base_url="https://direct-provider.example/v1",
        default_model="legacy-model",
    )

    try:
        await llm_lifecycle.init_llm_client()
        assert llm_lifecycle.get_llm_client() is None
    finally:
        settings.llm = original_llm


async def test_llm_lifecycle_only_initializes_newapi_relay(monkeypatch) -> None:
    original_llm = settings.llm
    llm_lifecycle._llm_client = None
    _FakeGatewayLLM.instances = []
    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    monkeypatch.setattr(settings, "NEWAPI_USER_RELAY_BASE_URL", "https://gateway.example.com/pg")
    monkeypatch.setattr(
        "infrastructure.external.llm.openai_provider.OpenAIProvider",
        _FakeGatewayLLM,
    )
    settings.llm = LLMSettings(
        provider="ignored-direct-provider",
        api_key="ignored-static-key",
        base_url="https://direct-provider.example/v1",
        wire_api="responses",
        default_model="gpt-5.5",
    )

    try:
        await llm_lifecycle.init_llm_client()

        assert len(_FakeGatewayLLM.instances) == 1
        assert _FakeGatewayLLM.instances[0].kwargs["api_key"] == "newapi-user-session"
        assert _FakeGatewayLLM.instances[0].kwargs["base_url"] == "https://gateway.example.com/pg"
        assert _FakeGatewayLLM.instances[0].kwargs["provider_name"] == (
            "newapi_openai_compatible"
        )
        assert _FakeGatewayLLM.instances[0].kwargs["default_model"] == "gpt-5.5"
        assert _FakeGatewayLLM.instances[0].kwargs["wire_api"] == "responses"
    finally:
        llm_lifecycle._llm_client = None
        settings.llm = original_llm
