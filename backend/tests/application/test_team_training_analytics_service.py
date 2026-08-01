from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.team_analytics_service import (
    TeamTrainingAnalyticsService,
)
from domain.common.exceptions import DomainValidationException
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)
from domain.training_studio.session_repository import (
    TrainingSessionAccessScope,
    training_session_matches_access_scope,
)

pytestmark = pytest.mark.asyncio


def make_session(
    session_id: str,
    *,
    user_id: str,
    team_id: str,
    scenario_id: str,
    report_id: str,
    completed_at: datetime,
) -> TrainingSession:
    task_config = TrainingTaskConfigDTO(
        role="Salesperson",
        level="Intermediate",
        tech_stack=["Discovery"],
        question_type_ratios={"behavioral": 1},
        question_count=3,
    ).to_domain()
    return TrainingSession(
        session_id=session_id,
        task_config=task_config,
        mode=TrainingSessionMode.TEXT,
        scenario_template_id=scenario_id,
        user_id=user_id,
        team_id=team_id,
        status=TrainingSessionStatus.COMPLETED,
        report_id=report_id,
        completed_at=completed_at,
    )


class FakeTrainingSessionRepository:
    def __init__(self, sessions: list[TrainingSession]) -> None:
        self.sessions = sessions
        self.last_list_kwargs: dict[str, object] | None = None

    async def count(self, **kwargs) -> int:
        return len(await self.list(skip=0, limit=10_000, **kwargs))

    async def list(self, *, skip: int, limit: int, **kwargs) -> list[TrainingSession]:
        self.last_list_kwargs = {"skip": skip, "limit": limit, **kwargs}
        access_scope = kwargs.get("access_scope")
        team_id = kwargs.get("team_id")
        scoped = [
            session
            for session in self.sessions
            if training_session_matches_access_scope(session, access_scope)
            and (not team_id or session.team_id == team_id)
        ]
        return scoped[skip : skip + limit]


class FakeEvaluationRepository:
    def __init__(self, evaluations: dict[int, object]) -> None:
        self.evaluations = evaluations

    async def get_by_report_id(self, report_id: int):
        return self.evaluations.get(report_id)


class FakeTrainingAnalyticsUnitOfWork:
    def __init__(self, sessions: list[TrainingSession], evaluations: dict[int, object], **kwargs) -> None:
        self.training_session_repository = FakeTrainingSessionRepository(sessions)
        self.competency_evaluation_repository = FakeEvaluationRepository(evaluations)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def analytics_service(
    sessions: list[TrainingSession], evaluations: dict[int, object]
) -> TeamTrainingAnalyticsService:
    return TeamTrainingAnalyticsService(
        uow_factory=lambda **kwargs: FakeTrainingAnalyticsUnitOfWork(
            sessions,
            evaluations,
            **kwargs,
        )
    )


def team_scope() -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id="user-leader",
        team_id="team-revenue",
        include_team_scope=True,
    )


async def test_team_analytics_groups_real_evaluations_by_member_and_scenario() -> None:
    sessions = [
        make_session(
            "sales-older",
            user_id="user-sales",
            team_id="team-revenue",
            scenario_id="enterprise-demo",
            report_id="1",
            completed_at=datetime(2026, 7, 21, tzinfo=UTC),
        ),
        make_session(
            "sales-newer",
            user_id="user-sales",
            team_id="team-revenue",
            scenario_id="enterprise-demo",
            report_id="2",
            completed_at=datetime(2026, 7, 22, tzinfo=UTC),
        ),
        make_session(
            "leader-session",
            user_id="user-leader",
            team_id="team-revenue",
            scenario_id="enterprise-demo",
            report_id="3",
            completed_at=datetime(2026, 7, 23, tzinfo=UTC),
        ),
        make_session(
            "outside-team",
            user_id="user-service",
            team_id="team-service",
            scenario_id="enterprise-demo",
            report_id="4",
            completed_at=datetime(2026, 7, 24, tzinfo=UTC),
        ),
    ]
    evaluations = {
        1: SimpleNamespace(
            overall_score=4.0,
            scores={"persuasion": 4, "active_listening": {"score": 3}},
        ),
        2: SimpleNamespace(
            overall_score=3.0,
            scores={"persuasion": 3, "active_listening": {"score": 4}},
        ),
        3: SimpleNamespace(
            overall_score=4.8,
            scores={"persuasion": 5, "active_listening": {"score": 5}},
        ),
        4: SimpleNamespace(
            overall_score=5.0,
            scores={"persuasion": 5},
        ),
    }
    service = analytics_service(sessions, evaluations)

    competencies, competency_total = await service.list_competency_rankings(
        skip=0,
        limit=50,
        access_scope=team_scope(),
    )
    scenarios, scenario_total = await service.list_scenario_rankings(
        skip=0,
        limit=50,
        access_scope=team_scope(),
    )

    assert competency_total == 2
    assert [item.member_id for item in competencies] == ["user-leader", "user-sales"]
    assert [item.rank for item in competencies] == [1, 2]
    assert [item.average_score for item in competencies] == [96, 70]
    assert competencies[0].dimensions[0].model_dump() == {
        "dimension_id": "persuasion",
        "score": 100,
        "sample_count": 1,
    }
    assert competencies[1].dimensions[0].model_dump() == {
        "dimension_id": "persuasion",
        "score": 70,
        "sample_count": 2,
    }

    assert scenario_total == 2
    assert [item.member_id for item in scenarios] == ["user-leader", "user-sales"]
    assert [item.rank for item in scenarios] == [1, 2]
    assert [item.completed_sessions for item in scenarios] == [1, 2]
    assert [item.average_score for item in scenarios] == [96, 70]
    assert all(item.member_id != "user-service" for item in scenarios)


async def test_scenario_rankings_are_global_across_scenarios() -> None:
    sessions = [
        make_session(
            "lower-score",
            user_id="user-sales",
            team_id="team-revenue",
            scenario_id="new-customer",
            report_id="1",
            completed_at=datetime(2026, 7, 27, tzinfo=UTC),
        ),
        make_session(
            "higher-score",
            user_id="user-sales",
            team_id="team-revenue",
            scenario_id="vip-upgrade",
            report_id="2",
            completed_at=datetime(2026, 7, 28, tzinfo=UTC),
        ),
    ]
    service = analytics_service(
        sessions,
        {
            1: SimpleNamespace(overall_score=42, scores={}),
            2: SimpleNamespace(overall_score=60, scores={}),
        },
    )

    scenarios, total = await service.list_scenario_rankings(
        skip=0,
        limit=50,
        access_scope=team_scope(),
    )

    assert total == 2
    assert [item.scenario_id for item in scenarios] == ["vip-upgrade", "new-customer"]
    assert [item.rank for item in scenarios] == [1, 2]


async def test_team_analytics_requires_authorized_team_scope() -> None:
    service = analytics_service([], {})

    with pytest.raises(DomainValidationException):
        await service.list_competency_rankings(
            skip=0,
            limit=50,
            access_scope=TrainingSessionAccessScope(
                user_id="user-sales",
                team_id="team-revenue",
                include_team_scope=False,
            ),
        )
