"""Persistent Training Points ledger tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.services.training_studio.growth_ledger_service import (
    TRAINING_COMPLETION_POINTS,
    TrainingGrowthLedgerService,
    _career_path_for_completed_scenarios,
    _level_for_points,
    _level_threshold,
)
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import TrainingSession
from infrastructure.models import Base
from infrastructure.repositories.training_session_repository import (
    SQLAlchemyTrainingSessionRepository,
)
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


def _task_config() -> TrainingTaskConfig:
    return TrainingTaskConfig(
        role="Account Executive",
        level="Senior",
        tech_stack=["Discovery", "Objection handling"],
        question_type_ratios={"behavioral": 1},
        question_count=4,
        category="sales",
    )


def _completed_session(
    index: int,
    *,
    user_id: str,
    scenario_id: str | None = None,
) -> TrainingSession:
    session = TrainingSession(
        session_id=f"session-{user_id}-{index:03d}",
        task_config=_task_config(),
        mode="text",
        scenario_template_id=scenario_id,
        user_id=user_id,
        team_id="training-team-revenue",
    )
    started_at = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(minutes=index)
    session.start(f"room-{user_id}-{index:03d}")
    session.started_at = started_at
    session.complete()
    session.completed_at = started_at + timedelta(minutes=10)
    return session


@pytest.mark.parametrize(
    ("points", "expected_level"),
    [
        (0, 1),
        (499, 1),
        (500, 2),
        (1499, 2),
        (1500, 3),
        (2999, 3),
        (3000, 4),
    ],
)
def test_training_point_level_thresholds(points: int, expected_level: int) -> None:
    assert _level_for_points(points) == expected_level
    assert _level_threshold(expected_level) <= points
    assert points < _level_threshold(expected_level + 1)


@pytest.mark.parametrize(
    ("completed_scenario_ids", "expected_statuses", "expected_current_stage"),
    [
        (set(), ["current", "locked", "locked", "locked", "locked"], "foundation"),
        (
            {"new-customer-discount", "recruiter-sales-interview"},
            ["completed", "current", "locked", "locked", "locked"],
            "collaboration",
        ),
        (
            {
                "new-customer-discount",
                "recruiter-sales-interview",
                "enterprise-demo-objection",
                "project-scope-creep-boundary",
                "daily-upward-results-report",
                "budget-freeze-expansion",
            },
            ["completed", "completed", "completed", "current", "locked"],
            "interest-communication",
        ),
        (
            {
                "new-customer-discount",
                "recruiter-sales-interview",
                "enterprise-demo-objection",
                "project-scope-creep-boundary",
                "daily-upward-results-report",
                "budget-freeze-expansion",
                "refund-service-recovery",
                "renewal-price-negotiation",
                "cross-team-roadmap-tradeoff",
                "angry-vip-priority",
                "ai-web3-agent-pm-comprehensive-interview",
            },
            ["completed", "completed", "completed", "completed", "completed"],
            None,
        ),
    ],
)
def test_career_path_uses_required_scenario_completion(
    completed_scenario_ids: set[str],
    expected_statuses: list[str],
    expected_current_stage: str | None,
) -> None:
    stages = _career_path_for_completed_scenarios(completed_scenario_ids)

    assert [stage.status for stage in stages] == expected_statuses
    if expected_current_stage is None:
        assert not any(stage.status == "current" for stage in stages)
    else:
        assert next(stage.stage_id for stage in stages if stage.status == "current") == (
            expected_current_stage
        )
    assert stages[0].stage_number == 1
    assert stages[0].required_scenario_count == 2
    assert stages[0].completed_scenario_count == len(
        completed_scenario_ids.intersection(
            {"new-customer-discount", "recruiter-sales-interview"}
        )
    )
    assert all(not hasattr(stage, "threshold_points") for stage in stages)


@pytest.mark.asyncio
async def test_growth_ledger_backfills_all_owned_sessions_and_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db_session:
            repository = SQLAlchemyTrainingSessionRepository(db_session)
            for index in range(205):
                await repository.save(
                    _completed_session(
                        index,
                        user_id="user-1",
                        scenario_id="new-customer-discount",
                    )
                )
            await repository.save(
                _completed_session(
                    1,
                    user_id="user-2",
                    scenario_id="new-customer-discount",
                )
            )
            active = TrainingSession(
                session_id="session-user-1-active",
                task_config=_task_config(),
                mode="voice",
                user_id="user-1",
                team_id="training-team-revenue",
            )
            active.start("room-active")
            await repository.save(active)
            await db_session.commit()

        ledger = TrainingGrowthLedgerService()
        async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
            first = await ledger.summary(uow, user_id="user-1")
        async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
            second = await ledger.summary(uow, user_id="user-1")
        async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
            other = await ledger.summary(uow, user_id="user-2")

        assert first.total_points == 205 * TRAINING_COMPLETION_POINTS
        assert first.completed_sessions == 205
        assert len(first.recent_events) == 10
        assert first.career_path[0].status == "current"
        assert first.career_path[0].completed_scenario_count == 1
        assert first.to_dict()["career_path"][0]["id"] == "foundation"
        assert second.to_dict() == first.to_dict()
        assert other.total_points == TRAINING_COMPLETION_POINTS
        assert other.completed_sessions == 1
        assert other.career_path[0].status == "current"
        assert other.career_path[0].completed_scenario_count == 1
    finally:
        await engine.dispose()
