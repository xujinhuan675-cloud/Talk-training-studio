# input: AbstractUnitOfWork, ChatRoomDomainService, PersonaLoader, DTOs
# output: ChatRoomApplicationService 聊天室 CRUD 用例编排
# owner: wanhua.gu
# pos: 应用层服务 - 聊天室创建/查询/列表用例编排；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Application service for stakeholder chat room CRUD."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from application.services.stakeholder.dto import (
    ChatRoomDTO,
    ChatRoomDetailDTO,
    CreateChatRoomDTO,
    MessageDTO,
)
from domain.common.exceptions import BusinessException, DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import ChatRoom
from domain.stakeholder.persona_entity import Persona
from domain.stakeholder.service import ChatRoomDomainService
from shared.codes import BusinessCode


@dataclass(frozen=True)
class StakeholderRoomAccessScope:
    """Caller visibility boundary for stakeholder rooms.

    Rooms do not yet persist owner/team metadata, so scoped access is derived
    from every persona currently attached to the room.
    """

    user_id: str | None = None
    team_id: str | None = None
    include_team_scope: bool = False
    allowed_persona_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_team_ids: frozenset[str] = field(default_factory=frozenset)
    allowed_organization_ids: frozenset[str] = field(default_factory=frozenset)
    unrestricted: bool = False


def _normalized_scope_value(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_scope_values(values: list[object | None]) -> frozenset[str]:
    return frozenset(text for value in values if (text := _normalized_scope_value(value)))


class ChatRoomApplicationService:
    """Orchestrates chat room creation, listing, and detail retrieval."""

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        persona_loader,
    ) -> None:
        self._uow_factory = uow_factory
        self._persona_loader = persona_loader
        self._domain_service = ChatRoomDomainService()

    async def create_room(self, dto: CreateChatRoomDTO) -> ChatRoomDTO:
        # 1. Validate persona_ids count per room type (domain rule)
        self._domain_service.validate_room_creation(dto.type, dto.persona_ids)

        # 2. Validate all persona_ids exist
        for pid in dto.persona_ids:
            if self._persona_loader.get_persona(pid) is None:
                raise DomainValidationException(
                    f"Persona '{pid}' not found",
                    field="persona_ids",
                    details={"persona_id": pid},
                )

        # 3. Create and persist
        room = ChatRoom(
            id=None,
            name=dto.name,
            type=dto.type,
            persona_ids=dto.persona_ids,
            scenario_id=dto.scenario_id,
        )
        async with self._uow_factory() as uow:
            created = await uow.chat_room_repository.create(room)
            return ChatRoomDTO.model_validate(created)

    def _room_matches_access_scope(
        self,
        room: ChatRoom,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> bool:
        if access_scope is None or access_scope.unrestricted:
            return True
        if not room.persona_ids:
            return False
        return all(
            self._persona_id_matches_access_scope(persona_id, access_scope)
            for persona_id in room.persona_ids
        )

    def _persona_id_matches_access_scope(
        self,
        persona_id: str,
        access_scope: StakeholderRoomAccessScope,
    ) -> bool:
        if persona_id in access_scope.allowed_persona_ids:
            return True

        persona = self._persona_loader.get_persona(persona_id)
        if persona is None:
            return False

        persona_scope = _persona_scope_values(persona)
        if persona_scope["team_ids"] & access_scope.allowed_team_ids:
            return True
        if persona_scope["organization_ids"] & access_scope.allowed_organization_ids:
            return True
        return False

    async def list_rooms(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> list[ChatRoomDTO]:
        async with self._uow_factory(readonly=True) as uow:
            if access_scope is not None and not access_scope.unrestricted:
                rooms = await self._list_scoped_rooms(
                    uow,
                    skip=skip,
                    limit=limit,
                    access_scope=access_scope,
                )
                return [ChatRoomDTO.model_validate(r) for r in rooms]
            rooms = await uow.chat_room_repository.list_rooms(skip=skip, limit=limit)
            return [ChatRoomDTO.model_validate(r) for r in rooms]

    async def _list_scoped_rooms(
        self,
        uow: AbstractUnitOfWork,
        *,
        skip: int,
        limit: int,
        access_scope: StakeholderRoomAccessScope,
    ) -> list[ChatRoom]:
        visible: list[ChatRoom] = []
        repo_skip = 0
        batch_size = max(50, skip + limit)
        target_count = skip + limit

        while len(visible) < target_count:
            batch = await uow.chat_room_repository.list_rooms(skip=repo_skip, limit=batch_size)
            if not batch:
                break
            visible.extend(
                room for room in batch if self._room_matches_access_scope(room, access_scope)
            )
            repo_skip += len(batch)
            if len(batch) < batch_size:
                break

        return visible[skip:target_count]

    async def delete_room(
        self,
        room_id: int,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> bool:
        async with self._uow_factory() as uow:
            if access_scope is not None and not access_scope.unrestricted:
                room = await uow.chat_room_repository.get_by_id(room_id)
                if room is None or not self._room_matches_access_scope(room, access_scope):
                    return False
            deleted = await uow.chat_room_repository.delete(room_id)
            return deleted

    async def get_room_detail(
        self,
        room_id: int,
        *,
        message_limit: int = 50,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> ChatRoomDetailDTO:
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            if room is None or not self._room_matches_access_scope(room, access_scope):
                _raise_room_not_found(room_id)
            messages = await uow.stakeholder_message_repository.list_by_room_id(
                room_id, limit=message_limit
            )
            return ChatRoomDetailDTO(
                room=ChatRoomDTO.model_validate(room),
                messages=[MessageDTO.model_validate(m) for m in messages],
            )


def _persona_scope_values(persona: Persona) -> dict[str, frozenset[str]]:
    return {
        "team_ids": _normalized_scope_values([getattr(persona, "team_id", None)]),
        "organization_ids": _normalized_scope_values(
            [getattr(persona, "organization_id", None)]
        ),
    }


def _raise_room_not_found(room_id: int) -> None:
    raise BusinessException(
        code=BusinessCode.CHATROOM_NOT_FOUND,
        message=f"Chat room {room_id} not found",
        error_type="ChatRoomNotFound",
        details={"room_id": room_id},
    )
