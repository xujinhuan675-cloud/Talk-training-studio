"""Ownership, visibility, and immutable-version behavior for Persona assets."""

from __future__ import annotations

import pytest

from application.services.stakeholder.dto import CreatePersonaDTO, UpdatePersonaDTO
from application.services.stakeholder.persona_access_policy import (
    PersonaAccessDeniedError,
    PersonaAccessScope,
)
from application.services.stakeholder.persona_asset_service import PersonaAssetService
from domain.stakeholder.persona_entity import HardRule, Persona


class _Repo:
    def __init__(self) -> None:
        self.items: dict[str, Persona] = {}

    async def list_all(self):
        return list(self.items.values())

    async def get_by_id(self, persona_id: str):
        return self.items.get(persona_id)

    async def save_structured_persona(self, persona: Persona):
        existing = self.items.get(persona.id)
        if existing is not None:
            persona.version = existing.version + 1
        self.items[persona.id] = persona
        return persona

    async def delete(self, persona_id: str):
        return self.items.pop(persona_id, None) is not None


class _Uow:
    def __init__(self, repo: _Repo) -> None:
        self.stakeholder_persona_repository = repo
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def commit(self):
        self.committed = True


def _service():
    repo = _Repo()

    def factory():
        return _Uow(repo)

    return PersonaAssetService(factory), repo


def _scope(user_id: str, team_id: str = "team-a", **kwargs) -> PersonaAccessScope:
    return PersonaAccessScope(user_id=user_id, team_id=team_id, **kwargs)


@pytest.mark.asyncio
async def test_create_assigns_owner_from_server_scope_not_request_body() -> None:
    service, _ = _service()

    created = await service.create(
        CreatePersonaDTO(
            id="buyer",
            name="Buyer",
            role="Procurement",
            content="Needs evidence",
            visibility="team",
        ),
        access_scope=_scope("newapi:42"),
    )

    assert created.owner_user_id == "newapi:42"
    assert created.owner_team_id == "team-a"
    assert created.visibility == "team"
    assert created.version == 1


@pytest.mark.asyncio
async def test_list_hides_ownerless_legacy_database_records() -> None:
    service, repo = _service()
    repo.items["legacy-db"] = Persona(id="legacy-db", name="Legacy", role="Old")
    repo.items["mine"] = Persona(
        id="mine", name="Mine", role="Owner", owner_user_id="newapi:42", owner_team_id="team-a"
    )

    visible = await service.list_visible(access_scope=_scope("newapi:42"))

    assert [persona.id for persona in visible] == ["mine"]


@pytest.mark.asyncio
async def test_team_persona_is_readable_but_not_editable_by_peer() -> None:
    service, repo = _service()
    repo.items["team-persona"] = Persona(
        id="team-persona",
        name="Team persona",
        role="Buyer",
        owner_user_id="newapi:owner",
        owner_team_id="team-a",
        visibility="team",
    )

    readable = await service.get_visible("team-persona", access_scope=_scope("newapi:peer"))
    assert readable.id == "team-persona"
    with pytest.raises(PersonaAccessDeniedError):
        await service.update(
            "team-persona",
            UpdatePersonaDTO(name="Forged edit"),
            access_scope=_scope("newapi:peer"),
        )


@pytest.mark.asyncio
async def test_update_preserves_owner_and_increments_version_with_snapshot() -> None:
    service, repo = _service()
    original = Persona(
        id="cfo",
        name="CFO",
        role="Finance",
        owner_user_id="newapi:42",
        owner_team_id="team-a",
        hard_rules=[HardRule(statement="Evidence first")],
    )
    repo.items[original.id] = original
    snapshot = original.training_snapshot()

    updated = await service.update(
        "cfo",
        UpdatePersonaDTO(name="CFO updated"),
        access_scope=_scope("newapi:42"),
    )

    assert updated.owner_user_id == "newapi:42"
    assert updated.version == 2
    assert snapshot["version"] == 1
    assert snapshot["name"] == "CFO"
