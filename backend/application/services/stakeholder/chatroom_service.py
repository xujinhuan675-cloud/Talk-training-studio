# input: AbstractUnitOfWork, ChatRoomDomainService, PersonaLoader, DTOs
# output: ChatRoomApplicationService 聊天室 CRUD 用例编排
# owner: wanhua.gu
# pos: 应用层服务 - 聊天室创建/查询/列表用例编排；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Application service for stakeholder chat room CRUD."""

from __future__ import annotations

from typing import Callable

from application.services.stakeholder.dto import (
    ChatRoomDTO,
    ChatRoomDetailDTO,
    CreateChatRoomDTO,
    MessageDTO,
)
from application.services.stakeholder.room_access_policy import (
    StakeholderRoomAccessScope,
    StakeholderRoomAction,
    raise_stakeholder_room_not_found,
    require_stakeholder_room_access,
    require_stakeholder_room_access_scope,
    stakeholder_room_matches_access_scope,
)
from application.services.stakeholder.persona_access_policy import (
    PersonaAccessScope,
    can_read_persona,
)
from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import ChatRoom
from domain.stakeholder.service import ChatRoomDomainService


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

    async def create_room(
        self,
        dto: CreateChatRoomDTO,
        *,
        access_scope: StakeholderRoomAccessScope | None = None,
    ) -> ChatRoomDTO:
        # 1. Validate persona_ids count per room type (domain rule)
        self._domain_service.validate_room_creation(dto.type, dto.persona_ids)

        # 2. Validate all persona_ids exist
        personas = []
        for pid in dto.persona_ids:
            persona = self._persona_loader.get_persona(pid)
            if persona is None:
                raise DomainValidationException(
                    f"Persona '{pid}' not found",
                    field="persona_ids",
                    details={"persona_id": pid},
                )
            if not self._persona_is_readable_for_room(persona, access_scope):
                raise DomainValidationException(
                    f"Persona '{pid}' is outside the current user scope",
                    field="persona_ids",
                    details={"persona_id": pid},
                )
            personas.append(persona)

        # 3. Create and persist
        room = ChatRoom(
            id=None,
            name=dto.name,
            type=dto.type,
            persona_ids=dto.persona_ids,
            scenario_id=dto.scenario_id,
            owner_user_id=(access_scope.user_id if access_scope and not access_scope.unrestricted else None),
            owner_team_id=(access_scope.team_id if access_scope and not access_scope.unrestricted else None),
            persona_snapshots={persona.id: self._persona_snapshot(persona) for persona in personas},
        )
        async with self._uow_factory() as uow:
            created = await uow.chat_room_repository.create(room)
            return ChatRoomDTO.model_validate(created)

    @staticmethod
    def _persona_is_readable_for_room(persona, access_scope: StakeholderRoomAccessScope | None) -> bool:
        """Enforce persisted asset ownership while keeping legacy templates usable."""

        if access_scope is None or access_scope.unrestricted:
            return True
        if not getattr(persona, "owner_user_id", None) and not getattr(persona, "owner_team_id", None):
            return True
        return can_read_persona(
            persona,
            PersonaAccessScope(
                user_id=access_scope.user_id or "",
                team_id=access_scope.team_id,
                can_manage_team=access_scope.include_team_scope,
            ),
        )

    @staticmethod
    def _persona_snapshot(persona) -> dict:
        snapshot = getattr(persona, "training_snapshot", None)
        if callable(snapshot):
            return snapshot()
        # Compatibility for legacy collaborators and isolated test doubles.
        return {
            "persona_id": persona.id,
            "version": getattr(persona, "version", 1),
            "name": getattr(persona, "name", persona.id),
            "role": getattr(persona, "role", ""),
            "profile_summary": getattr(persona, "profile_summary", ""),
        }

    def _room_matches_access_scope(
        self,
        room: ChatRoom,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> bool:
        return stakeholder_room_matches_access_scope(
            room,
            access_scope,
            self._persona_loader,
        )

    async def list_rooms(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> list[ChatRoomDTO]:
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="list_stakeholder_rooms",
        )
        async with self._uow_factory(readonly=True) as uow:
            if not scope.unrestricted:
                rooms = await self._list_scoped_rooms(
                    uow,
                    skip=skip,
                    limit=limit,
                    access_scope=scope,
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
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="delete_stakeholder_room",
        )
        async with self._uow_factory() as uow:
            if not scope.unrestricted:
                room = await uow.chat_room_repository.get_by_id(room_id)
                if room is None or not self._room_matches_access_scope(room, scope):
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
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="read_stakeholder_room",
        )
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            room = require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            ).room
            messages = await uow.stakeholder_message_repository.list_by_room_id(
                room_id, limit=message_limit
            )
            return ChatRoomDetailDTO(
                room=ChatRoomDTO.model_validate(room),
                messages=[MessageDTO.model_validate(m) for m in messages],
            )

_raise_room_not_found = raise_stakeholder_room_not_found
