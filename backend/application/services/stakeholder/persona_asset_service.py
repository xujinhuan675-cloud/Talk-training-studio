"""Owned persisted Persona asset lifecycle.

This service intentionally does not manage legacy markdown personas. They have
no trustworthy account metadata, so callers must expose them only as read-only
system templates. Persisted v2 assets are scoped before they are returned or
mutated.
"""

from __future__ import annotations

from collections.abc import Callable

from domain.stakeholder.persona_entity import Persona

from .dto import CreatePersonaDTO, UpdatePersonaDTO
from .persona_access_policy import (
    PersonaAccessScope,
    can_read_persona,
    require_persona_manage,
    require_persona_read,
)


class PersonaAssetNotFoundError(ValueError):
    """A persisted persona is absent or soft-deleted."""


class PersonaAssetService:
    def __init__(self, uow_factory: Callable) -> None:
        self._uow_factory = uow_factory

    async def list_visible(self, *, access_scope: PersonaAccessScope) -> list[Persona]:
        async with self._uow_factory() as uow:
            personas = await uow.stakeholder_persona_repository.list_all()
        return [persona for persona in personas if can_read_persona(persona, access_scope)]

    async def get_visible(
        self, persona_id: str, *, access_scope: PersonaAccessScope
    ) -> Persona:
        async with self._uow_factory() as uow:
            persona = await uow.stakeholder_persona_repository.get_by_id(persona_id)
        if persona is None:
            raise PersonaAssetNotFoundError(persona_id)
        require_persona_read(persona, access_scope)
        return persona

    async def create(
        self, dto: CreatePersonaDTO, *, access_scope: PersonaAccessScope
    ) -> Persona:
        async with self._uow_factory() as uow:
            existing = await uow.stakeholder_persona_repository.get_by_id(dto.id)
            if existing is not None:
                raise FileExistsError(f"Persona '{dto.id}' already exists")
            persona = Persona(
                id=dto.id,
                name=dto.name,
                role=dto.role,
                organization_id=dto.organization_id,
                team_id=dto.team_id,
                profile_summary=dto.content[:500],
                user_context=dto.content or None,
                owner_user_id=access_scope.user_id,
                owner_team_id=access_scope.team_id,
                visibility=dto.visibility,
                version=1,
            )
            saved = await uow.stakeholder_persona_repository.save_structured_persona(persona)
            await uow.commit()
            return saved

    async def update(
        self,
        persona_id: str,
        dto: UpdatePersonaDTO,
        *,
        access_scope: PersonaAccessScope,
    ) -> Persona:
        async with self._uow_factory() as uow:
            persona = await uow.stakeholder_persona_repository.get_by_id(persona_id)
            if persona is None:
                raise PersonaAssetNotFoundError(persona_id)
            require_persona_manage(persona, access_scope)
            if dto.name is not None:
                persona.name = dto.name
            if dto.role is not None:
                persona.role = dto.role
            if dto.organization_id is not None:
                persona.organization_id = dto.organization_id
            if dto.team_id is not None:
                persona.team_id = dto.team_id
            if dto.content is not None:
                persona.user_context = dto.content
                persona.profile_summary = dto.content[:500]
            if dto.visibility is not None:
                persona.visibility = dto.visibility
            # organization_id/team_id are legacy stakeholder hierarchy fields;
            # they are never used as account ownership or authorization input.
            saved = await uow.stakeholder_persona_repository.save_structured_persona(persona)
            await uow.commit()
            return saved

    async def delete(self, persona_id: str, *, access_scope: PersonaAccessScope) -> bool:
        async with self._uow_factory() as uow:
            persona = await uow.stakeholder_persona_repository.get_by_id(persona_id)
            if persona is None:
                raise PersonaAssetNotFoundError(persona_id)
            require_persona_manage(persona, access_scope)
            deleted = await uow.stakeholder_persona_repository.delete(persona_id)
            await uow.commit()
            return deleted
