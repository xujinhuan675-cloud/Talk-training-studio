from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_persona_loader_with_v2
from api.routes.stakeholder import router
from core.exceptions import register_exception_handlers
from domain.stakeholder.persona_entity import HardRule, Persona


class _StubPersonaLoader:
    def list_personas(self) -> list[Persona]:
        return [
            Persona(
                id="legacy",
                name="Legacy",
                role="Markdown persona",
                avatar_color="#0F766E",
            ),
            Persona(
                id="structured",
                name="Structured",
                role="V2 persona",
                avatar_color="#6366f1",
                hard_rules=[HardRule(statement="Keep structured data", severity="high")],
            ),
        ]


@pytest.mark.asyncio
async def test_list_personas_marks_v2_support() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_persona_loader_with_v2] = lambda: _StubPersonaLoader()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas")

    assert resp.status_code == 200
    data = {item["id"]: item for item in resp.json()["data"]}
    assert data["legacy"]["supports_v2"] is False
    assert data["structured"]["supports_v2"] is True
