"""Tests for Training Studio session SQLAlchemy persistence."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.services.training_studio.session_service import TrainingSessionService
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)
from infrastructure.models import Base
from infrastructure.repositories.training_session_repository import (
    SQLAlchemyTrainingSessionRepository,
)
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


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


def _task_config() -> TrainingTaskConfig:
    return TrainingTaskConfig(
        role="Product Manager",
        level="Senior",
        tech_stack=["Roadmap", "Metrics"],
        question_type_ratios={"behavioral": 2, "craft": 1},
        question_count=6,
        framework="prep",
        difficulty="medium",
        category="interview",
    )


def _flat_payload() -> dict:
    return {
        "role": "Product Manager",
        "level": "Senior",
        "tech_stack": ["Roadmap", "Metrics"],
        "question_type_ratios": {"behavioral": 2, "craft": 1},
        "question_count": 6,
        "framework": "prep",
        "difficulty": "medium",
        "category": "interview",
        "mode": "voice",
        "scenario_template_id": "enterprise-demo-objection",
        "user_id": "user-sales-001",
        "team_id": "team-revenue",
    }


@pytest.mark.asyncio
async def test_training_session_repository_round_trips_lifecycle(session_factory) -> None:
    session = TrainingSession(
        session_id="session-1",
        task_config=_task_config(),
        mode="voice",
        scenario_template_id="new-customer-discount",
        user_id="user-sales-001",
        team_id="team-revenue",
    )
    session.start("42")
    session.record_turn(2)
    session.complete(report_id="report-1", score_id="score-1")

    async with session_factory() as db_session:
        repo = SQLAlchemyTrainingSessionRepository(db_session)
        saved = await repo.save(session)
        await db_session.commit()

        assert saved.session_id == "session-1"
        assert saved.status == TrainingSessionStatus.COMPLETED

    async with session_factory() as db_session:
        repo = SQLAlchemyTrainingSessionRepository(db_session)
        loaded = await repo.get("session-1")

    assert loaded is not None
    assert loaded.mode == TrainingSessionMode.VOICE
    assert loaded.scenario_template_id == "new-customer-discount"
    assert loaded.user_id == "user-sales-001"
    assert loaded.team_id == "team-revenue"
    assert loaded.status == TrainingSessionStatus.COMPLETED
    assert loaded.room_id == "42"
    assert loaded.message_count == 2
    assert loaded.report_id == "report-1"
    assert loaded.score_id == "score-1"
    assert loaded.task_config.framework.value == "prep"
    assert round(sum(loaded.task_config.question_type_ratios.values()), 5) == 1


@pytest.mark.asyncio
async def test_training_session_repository_save_is_upsert(session_factory) -> None:
    session = TrainingSession(
        session_id="session-upsert",
        task_config=_task_config(),
        mode="text",
    )

    async with session_factory() as db_session:
        repo = SQLAlchemyTrainingSessionRepository(db_session)
        await repo.save(session)
        session.start("room-1")
        updated = await repo.save(session)
        await db_session.commit()

    assert updated.status == TrainingSessionStatus.ACTIVE
    assert updated.room_id == "room-1"

    async with session_factory() as db_session:
        repo = SQLAlchemyTrainingSessionRepository(db_session)
        loaded = await repo.get("session-upsert")

    assert loaded is not None
    assert loaded.status == TrainingSessionStatus.ACTIVE
    assert loaded.room_id == "room-1"


@pytest.mark.asyncio
async def test_training_session_service_uses_sqlalchemy_uow(session_factory) -> None:
    service = TrainingSessionService(
        uow_factory=_uow_factory(session_factory),
        id_factory=lambda: "service-session",
    )

    created = await service.create_session(_flat_payload())
    started = await service.start_session(created.session_id, room_id="42")

    assert started.status == TrainingSessionStatus.ACTIVE

    fresh_service = TrainingSessionService(uow_factory=_uow_factory(session_factory))
    loaded = await fresh_service.get_session("service-session")
    listed = await fresh_service.list_sessions()

    assert loaded.room_id == "42"
    assert loaded.scenario_template_id == "enterprise-demo-objection"
    assert loaded.user_id == "user-sales-001"
    assert loaded.team_id == "team-revenue"
    assert loaded.status == TrainingSessionStatus.ACTIVE
    assert [item.session_id for item in listed] == ["service-session"]
