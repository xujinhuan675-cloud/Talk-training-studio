from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import (
    CurrentUser,
    get_current_user,
    get_persona_asset_service,
    get_persona_loader_with_v2,
)
from api.routes.stakeholder import router
from application.services.stakeholder.persona_asset_service import PersonaAssetNotFoundError
from core.exceptions import register_exception_handlers
from domain.stakeholder.persona_entity import HardRule, Persona


class _StubPersonaLoader:
    def __init__(self, persona_dir: Path, personas: list[Persona]) -> None:
        self._persona_dir = persona_dir
        self._personas = personas

    def list_personas(self) -> list[Persona]:
        return self._personas

    def get_persona(self, persona_id: str) -> Persona | None:
        return next((persona for persona in self._personas if persona.id == persona_id), None)

    @staticmethod
    def _strip_frontmatter(raw: str) -> str:
        return raw


class _StubPersonaAssetService:
    def __init__(self, personas: list[Persona]) -> None:
        self._personas = personas

    async def list_visible(self, *, access_scope):
        return self._personas

    async def get_visible(self, persona_id: str, *, access_scope):
        persona = next((item for item in self._personas if item.id == persona_id), None)
        if persona is None:
            raise PersonaAssetNotFoundError(persona_id)
        return persona


def _current_user(*, user_id: str, role: str = "staff") -> CurrentUser:
    return CurrentUser(user_id=user_id, system_role=role, team_id="team-a")


def _personas() -> list[Persona]:
    return [
        Persona(
            id="system-template",
            name="System template",
            role="Markdown persona",
        ),
        Persona(
            id="owned",
            name="Owned",
            role="Owner asset",
            owner_user_id="newapi:owner",
            owner_team_id="team-a",
            hard_rules=[HardRule(statement="Keep structured data", severity="high")],
        ),
        Persona(
            id="team-shared",
            name="Team shared",
            role="Peer asset",
            owner_user_id="newapi:teammate",
            owner_team_id="team-a",
            visibility="team",
        ),
    ]


def _app_for(
    tmp_path: Path,
    current_user: CurrentUser,
    personas: list[Persona] | None = None,
) -> FastAPI:
    personas = personas or _personas()
    (tmp_path / "system-template.md").write_text("System persona", encoding="utf-8")
    loader = _StubPersonaLoader(tmp_path, personas)
    asset_service = _StubPersonaAssetService(personas[1:])

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_persona_loader_with_v2] = lambda: loader
    app.dependency_overrides[get_persona_asset_service] = lambda: asset_service
    app.dependency_overrides[get_current_user] = lambda: current_user
    return app


@pytest.mark.asyncio
async def test_list_personas_projects_owner_peer_and_system_permissions(tmp_path: Path) -> None:
    app = _app_for(tmp_path, _current_user(user_id="newapi:owner"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas")

    assert resp.status_code == 200
    data = {item["id"]: item for item in resp.json()["data"]}
    assert data["system-template"]["supports_v2"] is False
    assert "avatar_color" not in data["system-template"]
    assert data["system-template"]["can_manage"] is False
    assert data["system-template"]["read_only"] is True
    assert data["owned"]["supports_v2"] is True
    assert data["owned"]["can_manage"] is True
    assert data["owned"]["read_only"] is False
    assert data["team-shared"]["can_manage"] is False
    assert data["team-shared"]["read_only"] is True


@pytest.mark.asyncio
async def test_list_personas_collapses_duplicate_template_and_structured_asset(
    tmp_path: Path,
) -> None:
    personas = _personas()
    personas.append(
        Persona(
            id="structured-system-template",
            name="System template",
            role="Markdown persona",
            owner_user_id="newapi:owner",
            owner_team_id="team-a",
            hard_rules=[HardRule(statement="Prefer structured persona", severity="high")],
        )
    )
    app = _app_for(
        tmp_path,
        _current_user(user_id="newapi:owner"),
        personas,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas")

    assert resp.status_code == 200
    matching = [
        item
        for item in resp.json()["data"]
        if item["name"] == "System template" and item["role"] == "Markdown persona"
    ]
    assert [item["id"] for item in matching] == ["structured-system-template"]


@pytest.mark.asyncio
async def test_create_persona_rejects_removed_avatar_color(tmp_path: Path) -> None:
    app = _app_for(tmp_path, _current_user(user_id="newapi:owner"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.post(
            "/api/v1/stakeholder/personas",
            json={
                "id": "legacy-color",
                "name": "Legacy color",
                "role": "Removed field contract",
                "avatar_color": "#0f766e",
            },
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_personas_projects_admin_management_permission(tmp_path: Path) -> None:
    app = _app_for(
        tmp_path,
        _current_user(user_id="newapi:admin", role="admin"),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas")

    assert resp.status_code == 200
    data = {item["id"]: item for item in resp.json()["data"]}
    assert data["team-shared"]["can_manage"] is True
    assert data["team-shared"]["read_only"] is False
    assert data["system-template"]["can_manage"] is False
    assert data["system-template"]["read_only"] is True


@pytest.mark.asyncio
async def test_persona_detail_projects_team_peer_permission(tmp_path: Path) -> None:
    app = _app_for(tmp_path, _current_user(user_id="newapi:peer"))

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas/team-shared")

    assert resp.status_code == 200
    assert resp.json()["data"]["can_manage"] is False
    assert resp.json()["data"]["read_only"] is True


@pytest.mark.asyncio
async def test_persona_detail_keeps_system_template_read_only_for_admin(tmp_path: Path) -> None:
    app = _app_for(
        tmp_path,
        _current_user(user_id="newapi:admin", role="admin"),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/stakeholder/personas/system-template")

    assert resp.status_code == 200
    assert resp.json()["data"]["source"] == "system_template"
    assert resp.json()["data"]["can_manage"] is False
    assert resp.json()["data"]["read_only"] is True
