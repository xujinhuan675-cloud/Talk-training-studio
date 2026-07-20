"""Scoped access policy for stakeholder chat rooms."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from domain.common.exceptions import BusinessException, DomainValidationException
from domain.stakeholder.entity import ChatRoom
from domain.stakeholder.persona_entity import Persona
from shared.codes import BusinessCode


@dataclass(frozen=True)
class StakeholderRoomAccessScope:
    """Caller visibility boundary for stakeholder rooms.

    Rooms do not yet persist owner/team metadata, so scoped access is derived
    from every persona currently attached to the room. Callers must pass this
    explicitly; trusted internal/admin reads use ``unrestricted=True``.
    """

    user_id: str | None = None
    team_id: str | None = None
    include_team_scope: bool = False
    allowed_persona_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_team_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_organization_ids: frozenset[str] = field(default_factory=frozenset)
    unrestricted: bool = False


class StakeholderRoomAction(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"


@dataclass(frozen=True)
class ResolvedStakeholderRoom:
    room: ChatRoom
    access_scope: StakeholderRoomAccessScope
    action: StakeholderRoomAction


def unrestricted_stakeholder_room_scope() -> StakeholderRoomAccessScope:
    return StakeholderRoomAccessScope(unrestricted=True)


def require_stakeholder_room_access_scope(
    access_scope: StakeholderRoomAccessScope | None,
    *,
    operation: str,
) -> StakeholderRoomAccessScope:
    if access_scope is None:
        raise DomainValidationException(
            "access_scope is required for stakeholder room access",
            field="access_scope",
            details={"operation": operation},
            message_key="stakeholder_room.scope.required",
        )
    return access_scope


def stakeholder_room_matches_access_scope(
    room: ChatRoom,
    access_scope: StakeholderRoomAccessScope | None,
    persona_loader,
    *,
    operation: str = "read_stakeholder_room",
) -> bool:
    scope = require_stakeholder_room_access_scope(access_scope, operation=operation)
    if scope.unrestricted:
        return True
    if not room.persona_ids:
        return False
    return all(
        stakeholder_persona_matches_access_scope(persona_id, scope, persona_loader)
        for persona_id in room.persona_ids
    )


def require_stakeholder_room_access(
    room: ChatRoom | None,
    *,
    room_id: int,
    access_scope: StakeholderRoomAccessScope | None,
    persona_loader,
    action: StakeholderRoomAction = StakeholderRoomAction.READ,
) -> ResolvedStakeholderRoom:
    scope = require_stakeholder_room_access_scope(
        access_scope,
        operation=f"{action.value}_stakeholder_room",
    )
    if room is None:
        raise_stakeholder_room_not_found(room_id)
    if not stakeholder_room_matches_access_scope(
        room,
        scope,
        persona_loader,
        operation=f"{action.value}_stakeholder_room",
    ):
        raise_stakeholder_room_not_found(room_id)
    return ResolvedStakeholderRoom(room=room, access_scope=scope, action=action)


def stakeholder_persona_matches_access_scope(
    persona_id: str,
    access_scope: StakeholderRoomAccessScope,
    persona_loader,
) -> bool:
    if persona_id in access_scope.allowed_persona_ids:
        return True

    persona = persona_loader.get_persona(persona_id) if persona_loader else None
    if persona is None:
        return False

    persona_scope = _persona_scope_values(persona)
    if persona_scope["team_ids"] & access_scope.allowed_team_ids:
        return True
    if persona_scope["organization_ids"] & access_scope.allowed_organization_ids:
        return True
    return False


def raise_stakeholder_room_not_found(room_id: int) -> None:
    raise BusinessException(
        code=BusinessCode.CHATROOM_NOT_FOUND,
        message=f"Chat room {room_id} not found",
        error_type="ChatRoomNotFound",
        details={"room_id": room_id},
    )


def _persona_scope_values(persona: Persona) -> dict[str, frozenset[str]]:
    return {
        "team_ids": _normalized_scope_values([getattr(persona, "team_id", None)]),
        "organization_ids": _normalized_scope_values(
            [getattr(persona, "organization_id", None)]
        ),
    }


def _normalized_scope_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_scope_values(values: list[object | None]) -> frozenset[str]:
    return frozenset(text for value in values if (text := _normalized_scope_value(value)))
