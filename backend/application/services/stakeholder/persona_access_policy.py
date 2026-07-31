"""Authorization rules for persisted Persona assets.

Markdown personas predate account ownership. They remain read-only system
templates at the API boundary; this policy applies to persisted v2 assets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from domain.stakeholder.persona_entity import Persona


class PersonaVisibility(StrEnum):
    PRIVATE = "private"
    TEAM = "team"
    SYSTEM = "system"


@dataclass(frozen=True)
class PersonaAccessScope:
    user_id: str
    team_id: str | None = None
    can_manage_team: bool = False
    unrestricted: bool = False


class PersonaAccessDeniedError(PermissionError):
    """Raised when a caller cannot read or mutate a persisted persona."""


def can_read_persona(persona: Persona, scope: PersonaAccessScope) -> bool:
    if scope.unrestricted:
        return True
    if persona.visibility == PersonaVisibility.SYSTEM:
        return True
    if persona.owner_user_id == scope.user_id:
        return True
    return (
        persona.visibility == PersonaVisibility.TEAM
        and bool(scope.team_id)
        and persona.owner_team_id == scope.team_id
    )


def can_manage_persona(persona: Persona, scope: PersonaAccessScope) -> bool:
    if scope.unrestricted:
        return True
    if persona.visibility == PersonaVisibility.SYSTEM:
        return False
    if persona.owner_user_id == scope.user_id:
        return True
    return (
        persona.visibility == PersonaVisibility.TEAM
        and scope.can_manage_team
        and bool(scope.team_id)
        and persona.owner_team_id == scope.team_id
    )


def require_persona_read(persona: Persona, scope: PersonaAccessScope) -> None:
    if not can_read_persona(persona, scope):
        raise PersonaAccessDeniedError("Persona is outside the current user scope")


def require_persona_manage(persona: Persona, scope: PersonaAccessScope) -> None:
    if not can_manage_persona(persona, scope):
        raise PersonaAccessDeniedError("Persona cannot be modified by the current user")
