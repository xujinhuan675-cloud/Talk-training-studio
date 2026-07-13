"""Regression tests for growth dashboard dependencies."""

from __future__ import annotations

import pytest


class _StubPersonaLoader:
    pass


@pytest.mark.asyncio
async def test_growth_service_allows_missing_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """The read-only dashboard must work even when Anthropic is not configured."""
    import api.dependencies as deps
    from application.services.stakeholder.growth_service import GrowthService

    monkeypatch.setattr(deps, "get_llm_client", lambda: None)
    monkeypatch.setattr(deps, "get_anthropic_client", lambda: None)

    service = await deps.get_growth_service(loader=_StubPersonaLoader())

    assert isinstance(service, GrowthService)
    assert service.has_llm is False


def test_stakeholder_llm_prefers_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stakeholder flows should use the OpenAI-compatible client when present."""
    import api.dependencies as deps

    openai_client = object()
    anthropic_client = object()

    monkeypatch.setattr(deps, "get_llm_client", lambda: openai_client)
    monkeypatch.setattr(deps, "get_anthropic_client", lambda: anthropic_client)

    assert deps.get_stakeholder_llm_client() is openai_client
