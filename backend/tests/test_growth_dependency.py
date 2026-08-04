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

    service = await deps.get_growth_service(loader=_StubPersonaLoader())

    assert isinstance(service, GrowthService)
    assert service.has_llm is False


def test_stakeholder_llm_uses_shared_gateway_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.dependencies as deps

    gateway_client = object()

    monkeypatch.setattr(deps, "get_llm_client", lambda: gateway_client)

    assert deps.get_stakeholder_llm_client() is gateway_client
