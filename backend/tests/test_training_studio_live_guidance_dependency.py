"""Dependency tests for Training Studio live guidance."""

from __future__ import annotations

import api.routes.training_studio as routes
from application.services.training_studio.live_guidance_llm_adapter import LiveGuidanceLLMAdapter
from application.services.training_studio.live_guidance_service import TrainingLiveGuidanceService


class _FakeLLM:
    async def generate(self, messages, **kwargs):  # pragma: no cover - should not be called here
        raise AssertionError("generate should not be called in dependency tests")


def test_get_live_guidance_service_without_llm_returns_fallback(monkeypatch) -> None:
    monkeypatch.setattr(routes, "get_stakeholder_llm_client", lambda: None)
    monkeypatch.setattr(routes, "_live_guidance_llm_client", None, raising=False)
    monkeypatch.setattr(routes, "_live_guidance_llm_service", None, raising=False)

    service = routes.get_live_guidance_service()

    assert isinstance(service, TrainingLiveGuidanceService)
    assert service.async_llm_callback is None


def test_get_live_guidance_service_with_llm_wraps_adapter(monkeypatch) -> None:
    fake_llm = _FakeLLM()
    monkeypatch.setattr(routes, "get_stakeholder_llm_client", lambda: fake_llm)
    monkeypatch.setattr(routes, "_live_guidance_llm_client", None, raising=False)
    monkeypatch.setattr(routes, "_live_guidance_llm_service", None, raising=False)

    service = routes.get_live_guidance_service()

    assert isinstance(service, TrainingLiveGuidanceService)
    assert isinstance(service.async_llm_callback, LiveGuidanceLLMAdapter)
