"""Identity-scope regression tests for GrowthService aggregation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from application.services.stakeholder.growth_service import GrowthService
from application.services.stakeholder.room_access_policy import StakeholderRoomAccessScope
from domain.common.exceptions import DomainValidationException
from domain.stakeholder.competency_entity import CompetencyEvaluation
from domain.stakeholder.entity import ChatRoom


class _RoomRepository:
    def __init__(self, rooms: list[ChatRoom]) -> None:
        self._rooms = rooms

    async def list_rooms(self, *, skip: int = 0, limit: int = 50) -> list[ChatRoom]:
        return self._rooms[skip : skip + limit]


class _EvaluationRepository:
    def __init__(self, evaluations: list[CompetencyEvaluation]) -> None:
        self._evaluations = evaluations

    async def list_all(
        self,
        *,
        skip: int = 0,
        limit: int = 500,
    ) -> list[CompetencyEvaluation]:
        return self._evaluations[skip : skip + limit]


class _UnitOfWork:
    def __init__(
        self,
        rooms: list[ChatRoom],
        evaluations: list[CompetencyEvaluation],
    ) -> None:
        self.chat_room_repository = _RoomRepository(rooms)
        self.competency_evaluation_repository = _EvaluationRepository(evaluations)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _UnitOfWorkFactory:
    def __init__(
        self,
        rooms: list[ChatRoom],
        evaluations: list[CompetencyEvaluation],
    ) -> None:
        self._rooms = rooms
        self._evaluations = evaluations

    def __call__(self, **_kwargs) -> _UnitOfWork:
        return _UnitOfWork(self._rooms, self._evaluations)


def _room(room_id: int, *, owner_user_id: str, owner_team_id: str) -> ChatRoom:
    return ChatRoom(
        id=room_id,
        name=f"Room {room_id}",
        type="private",
        persona_ids=[],
        owner_user_id=owner_user_id,
        owner_team_id=owner_team_id,
    )


def _evaluation(
    evaluation_id: int,
    *,
    room_id: int,
    score: float,
) -> CompetencyEvaluation:
    return CompetencyEvaluation(
        id=evaluation_id,
        report_id=100 + evaluation_id,
        room_id=room_id,
        scores={
            "persuasion": {
                "score": score,
                "evidence": f"evidence-{evaluation_id}",
                "suggestion": f"suggestion-{evaluation_id}",
            }
        },
        overall_score=score,
        created_at=datetime(2026, 8, evaluation_id, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_dashboard_excludes_foreign_room_evaluations() -> None:
    rooms = [
        _room(1, owner_user_id="newapi:7", owner_team_id="team-a"),
        _room(2, owner_user_id="newapi:8", owner_team_id="team-b"),
    ]
    evaluations = [
        _evaluation(1, room_id=1, score=4.0),
        _evaluation(2, room_id=2, score=5.0),
    ]
    service = GrowthService(
        uow_factory=_UnitOfWorkFactory(rooms, evaluations),
        llm=None,
        persona_loader=None,
    )

    dashboard = await service.get_dashboard(
        access_scope=StakeholderRoomAccessScope(
            user_id="newapi:7",
            team_id="team-a",
        )
    )

    assert dashboard.overview.total_sessions == 1
    assert dashboard.overview.total_evaluations == 1
    assert dashboard.overview.avg_overall_score == 4.0
    assert [evaluation.room_id for evaluation in dashboard.evaluations] == [1]


@pytest.mark.asyncio
async def test_dashboard_requires_an_explicit_identity_scope() -> None:
    service = GrowthService(
        uow_factory=_UnitOfWorkFactory([], []),
        llm=None,
        persona_loader=None,
    )

    with pytest.raises(DomainValidationException, match="access_scope"):
        await service.get_dashboard(access_scope=None)


@pytest.mark.asyncio
async def test_profile_card_threshold_uses_only_visible_evaluations() -> None:
    rooms = [
        _room(1, owner_user_id="newapi:7", owner_team_id="team-a"),
        _room(2, owner_user_id="newapi:8", owner_team_id="team-b"),
    ]
    service = GrowthService(
        uow_factory=_UnitOfWorkFactory(
            rooms,
            [
                _evaluation(1, room_id=1, score=4.0),
                _evaluation(2, room_id=2, score=5.0),
            ],
        ),
        llm=None,
        persona_loader=None,
    )

    card = await service.generate_profile_card(
        access_scope=StakeholderRoomAccessScope(
            user_id="newapi:7",
            team_id="team-a",
        )
    )

    assert card.style_label == ""
    assert card.scores == {}
    assert "至少完成 2 次" in card.summary
