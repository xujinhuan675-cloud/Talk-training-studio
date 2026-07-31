# input: ChatRoomApplicationService, in-memory SQLite, PersonaLoader stub
# output: Story 2.1 application service integration tests
# owner: wanhua.gu
# pos: 测试层 - Story 2.1 聊天室应用服务集成测试；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Tests for ChatRoomApplicationService — Story 2.1 AC coverage."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.services.stakeholder.chatroom_service import StakeholderRoomAccessScope
from application.services.stakeholder.room_access_policy import (
    unrestricted_stakeholder_room_scope,
)
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _uow_factory(session_factory):
    """Return a callable that creates UoW with our test session factory."""

    def factory(**kwargs):
        return SQLAlchemyUnitOfWork(session_factory=session_factory, **kwargs)

    return factory


class FakePersonaLoader:
    """Stub PersonaLoader that knows a fixed set of persona IDs."""

    def __init__(self, known_ids: set[str] | dict[str, str | None]):
        if isinstance(known_ids, dict):
            self._team_by_id = dict(known_ids)
        else:
            self._team_by_id = {persona_id: None for persona_id in known_ids}

    def get_persona(self, persona_id: str):
        if persona_id in self._team_by_id:
            team_id = self._team_by_id[persona_id]
            return type(
                "P",
                (),
                {
                    "id": persona_id,
                    "name": persona_id,
                    "role": "test",
                    "organization_id": None,
                    "team_id": team_id,
                },
            )()
        return None


def _team_scope(team_id: str) -> StakeholderRoomAccessScope:
    return StakeholderRoomAccessScope(
        user_id="user-sales-001",
        team_id=team_id,
        allowed_team_ids=frozenset([team_id]),
    )


def test_room_read_delete_methods_require_explicit_access_scope():
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService

    for method_name in ("list_rooms", "get_room_detail", "delete_room"):
        signature = inspect.signature(getattr(ChatRoomApplicationService, method_name))
        assert signature.parameters["access_scope"].default is inspect.Parameter.empty


@pytest.mark.asyncio
async def test_room_read_delete_methods_reject_none_access_scope(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO
    from domain.common.exceptions import DomainValidationException

    loader = FakePersonaLoader({"jianfeng"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    room = await svc.create_room(
        CreateChatRoomDTO(name="Scoped Room", type="private", persona_ids=["jianfeng"])
    )

    with pytest.raises(DomainValidationException):
        await svc.list_rooms(access_scope=None)
    with pytest.raises(DomainValidationException):
        await svc.get_room_detail(room.id, access_scope=None)
    with pytest.raises(DomainValidationException):
        await svc.delete_room(room.id, access_scope=None)


# ---------------------------------------------------------------------------
# AC1: Create private room
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_private_room(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"jianfeng"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    dto = CreateChatRoomDTO(name="Test Private", type="private", persona_ids=["jianfeng"])
    result = await svc.create_room(dto)
    assert result.id is not None
    assert result.type == "private"
    assert result.persona_ids == ["jianfeng"]


@pytest.mark.asyncio
async def test_new_room_uses_owner_scope_before_legacy_persona_scope(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"jianfeng"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    owner_scope = StakeholderRoomAccessScope(user_id="newapi:owner", team_id="team-a")
    room = await svc.create_room(
        CreateChatRoomDTO(name="Owned", type="private", persona_ids=["jianfeng"]),
        access_scope=owner_scope,
    )

    owner_rooms = await svc.list_rooms(access_scope=owner_scope)
    peer_rooms = await svc.list_rooms(
        access_scope=StakeholderRoomAccessScope(user_id="newapi:peer", team_id="team-a")
    )
    admin_detail = await svc.get_room_detail(
        room.id,
        access_scope=unrestricted_stakeholder_room_scope(),
    )
    async with _uow_factory(session_factory)(readonly=True) as uow:
        persisted = await uow.chat_room_repository.get_by_id(room.id)

    assert [item.id for item in owner_rooms] == [room.id]
    assert peer_rooms == []
    assert admin_detail.room.id == room.id
    assert persisted.owner_user_id == "newapi:owner"
    assert persisted.persona_snapshots["jianfeng"]["version"] == 1


# ---------------------------------------------------------------------------
# AC2: Create group room
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_room(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"jianfeng", "robin"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    dto = CreateChatRoomDTO(name="Test Group", type="group", persona_ids=["jianfeng", "robin"])
    result = await svc.create_room(dto)
    assert result.type == "group"
    assert len(result.persona_ids) == 2


# ---------------------------------------------------------------------------
# AC3: Private with >1 persona → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_private_room_wrong_persona_count(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO
    from domain.common.exceptions import DomainValidationException

    loader = FakePersonaLoader({"a", "b"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    dto = CreateChatRoomDTO(name="Bad", type="private", persona_ids=["a", "b"])
    with pytest.raises(DomainValidationException, match="exactly 1"):
        await svc.create_room(dto)


# ---------------------------------------------------------------------------
# AC4: Group with <2 personas → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_room_too_few_personas(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO
    from domain.common.exceptions import DomainValidationException

    loader = FakePersonaLoader({"a"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    dto = CreateChatRoomDTO(name="Bad", type="group", persona_ids=["a"])
    with pytest.raises(DomainValidationException, match="at least 2"):
        await svc.create_room(dto)


# ---------------------------------------------------------------------------
# AC5: Nonexistent persona → error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_room_nonexistent_persona(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO
    from domain.common.exceptions import DomainValidationException

    loader = FakePersonaLoader(set())  # no known personas
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    dto = CreateChatRoomDTO(name="Bad", type="private", persona_ids=["nonexistent"])
    with pytest.raises(DomainValidationException, match="not found"):
        await svc.create_room(dto)


# ---------------------------------------------------------------------------
# AC6: List rooms ordered by last_message_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rooms_ordered(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"a", "b", "c"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    # Create two rooms
    await svc.create_room(CreateChatRoomDTO(name="Room1", type="private", persona_ids=["a"]))
    await svc.create_room(CreateChatRoomDTO(name="Room2", type="group", persona_ids=["b", "c"]))

    rooms = await svc.list_rooms(access_scope=unrestricted_stakeholder_room_scope())
    assert len(rooms) == 2
    # Both have no messages yet so last_message_at is None, ordered by id desc
    assert rooms[0].name == "Room2"


@pytest.mark.asyncio
async def test_list_rooms_with_access_scope_filters_by_persona_team(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"sales-persona": "team-revenue", "cs-persona": "team-service"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    await svc.create_room(
        CreateChatRoomDTO(name="Revenue Room", type="private", persona_ids=["sales-persona"])
    )
    await svc.create_room(
        CreateChatRoomDTO(name="Service Room", type="private", persona_ids=["cs-persona"])
    )

    rooms = await svc.list_rooms(access_scope=_team_scope("team-revenue"))

    assert [room.name for room in rooms] == ["Revenue Room"]


# ---------------------------------------------------------------------------
# AC7: Get room detail with messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_room_detail(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO

    loader = FakePersonaLoader({"jianfeng"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    room = await svc.create_room(
        CreateChatRoomDTO(name="Detail Test", type="private", persona_ids=["jianfeng"])
    )
    detail = await svc.get_room_detail(room.id, access_scope=unrestricted_stakeholder_room_scope())
    assert detail.room.id == room.id
    assert isinstance(detail.messages, list)


@pytest.mark.asyncio
async def test_get_and_delete_room_with_access_scope_hide_foreign_room(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from application.services.stakeholder.dto import CreateChatRoomDTO
    from domain.common.exceptions import BusinessException

    loader = FakePersonaLoader({"sales-persona": "team-revenue", "cs-persona": "team-service"})
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    foreign_room = await svc.create_room(
        CreateChatRoomDTO(name="Service Room", type="private", persona_ids=["cs-persona"])
    )

    with pytest.raises(BusinessException):
        await svc.get_room_detail(foreign_room.id, access_scope=_team_scope("team-revenue"))

    deleted = await svc.delete_room(foreign_room.id, access_scope=_team_scope("team-revenue"))
    admin_detail = await svc.get_room_detail(
        foreign_room.id,
        access_scope=unrestricted_stakeholder_room_scope(),
    )

    assert deleted is False
    assert admin_detail.room.id == foreign_room.id


# ---------------------------------------------------------------------------
# AC8: Nonexistent room → not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nonexistent_room(session_factory):
    from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
    from domain.common.exceptions import BusinessException

    loader = FakePersonaLoader(set())
    svc = ChatRoomApplicationService(
        uow_factory=_uow_factory(session_factory), persona_loader=loader
    )
    with pytest.raises(BusinessException):
        await svc.get_room_detail(99999, access_scope=unrestricted_stakeholder_room_scope())
