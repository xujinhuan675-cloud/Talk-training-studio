from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.services.stakeholder.coaching_service import CoachingService
from application.services.stakeholder.room_access_policy import StakeholderRoomAccessScope
from domain.common.exceptions import BusinessException
from domain.stakeholder.entity import AnalysisReport, ChatRoom, CoachingSession
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


@dataclass
class _Persona:
    id: str
    name: str
    role: str
    team_id: str | None = None
    organization_id: str | None = None


class _PersonaLoader:
    def __init__(self) -> None:
        self._personas = {
            "service-persona": _Persona(
                id="service-persona",
                name="Service",
                role="Customer Success",
                team_id="team-service",
            )
        }

    def get_persona(self, persona_id: str):
        return self._personas.get(persona_id)


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
    def factory(**kwargs):
        return SQLAlchemyUnitOfWork(session_factory=session_factory, **kwargs)

    return factory


def _foreign_scope() -> StakeholderRoomAccessScope:
    return StakeholderRoomAccessScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        allowed_team_ids=frozenset(["team-revenue"]),
    )


async def _seed_room_and_report(session_factory) -> tuple[int, int]:
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        room = await uow.chat_room_repository.create(
            ChatRoom(
                id=None,
                name="Service room",
                type="private",
                persona_ids=["service-persona"],
            )
        )
        report = await uow.analysis_report_repository.create(
            AnalysisReport(
                id=None,
                room_id=room.id,
                summary="Report",
                content={},
            )
        )
        return room.id, report.id


@pytest.mark.asyncio
async def test_prepare_start_session_scoped_miss_does_not_create_session(session_factory):
    room_id, report_id = await _seed_room_and_report(session_factory)
    service = CoachingService(
        uow_factory=_uow_factory(session_factory),
        llm=None,
        persona_loader=_PersonaLoader(),
    )

    with pytest.raises(BusinessException):
        await service.prepare_start_session(
            room_id,
            report_id,
            access_scope=_foreign_scope(),
        )

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        sessions = await uow.coaching_session_repository.list_by_room_id(room_id)

    assert sessions == []


@pytest.mark.asyncio
async def test_prepare_send_message_scoped_miss_does_not_create_message(session_factory):
    room_id, report_id = await _seed_room_and_report(session_factory)
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        session = await uow.coaching_session_repository.create(
            CoachingSession(id=None, room_id=room_id, report_id=report_id)
        )
    service = CoachingService(
        uow_factory=_uow_factory(session_factory),
        llm=None,
        persona_loader=_PersonaLoader(),
    )

    with pytest.raises(BusinessException):
        await service.prepare_send_message(
            room_id,
            session.id,
            "Follow up",
            access_scope=_foreign_scope(),
        )

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        messages = await uow.coaching_message_repository.list_by_session_id(session.id)

    assert messages == []
