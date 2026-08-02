"""Scoped team-level analytics derived from training sessions and evaluations."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from statistics import median
from typing import Literal

from pydantic import BaseModel

from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.competency_entity import (
    COMMUNICATION_RUBRIC_VERSION,
    COMPETENCY_DIMENSIONS,
)
from domain.training_studio.session import TrainingSession, TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope

logger = logging.getLogger(__name__)

_STABLE_OBSERVATION_COUNT = 3
_STABLE_SCENARIO_COUNT = 2


class TeamCompetencyDimensionDTO(BaseModel):
    dimension_id: str
    score: int | None = None
    sample_count: int
    scenario_count: int
    state: Literal["exploring", "stable"]


class TeamCompetencyRankingDTO(BaseModel):
    member_id: str
    member_name: str | None = None
    sample_count: int
    dimensions: list[TeamCompetencyDimensionDTO]


class TeamScenarioRankingDTO(BaseModel):
    scenario_id: str
    member_id: str
    member_name: str | None = None
    rank: int
    completed_sessions: int
    scored_sessions: int
    average_score: int | None = None
    last_practiced_at: datetime | None = None


class TeamTrainingAnalyticsService:
    """Builds team analytics without introducing a second source of training truth."""

    def __init__(self, *, uow_factory: Callable[..., AbstractUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def list_competency_rankings(
        self,
        *,
        skip: int,
        limit: int,
        access_scope: TrainingSessionAccessScope,
        recent_limit_per_member: int = 20,
    ) -> tuple[list[TeamCompetencyRankingDTO], int]:
        scope = self._require_team_scope(access_scope)
        recent_limit = max(1, min(5, recent_limit_per_member))
        async with self._uow_factory(readonly=True) as uow:
            sessions = await self._list_team_sessions(uow, scope)
            evaluation_lookup = uow.competency_evaluation_repository.get_by_report_id
            grouped = self._group_completed_sessions_by_member(sessions)
            rankings: list[TeamCompetencyRankingDTO] = []
            for member_id, member_sessions in grouped.items():
                ranking = await self._build_competency_ranking(
                    member_id=member_id,
                    sessions=member_sessions,
                    evaluation_lookup=evaluation_lookup,
                    observation_limit=recent_limit,
                )
                if ranking is not None:
                    rankings.append(ranking)

        rankings.sort(key=lambda item: item.member_id)
        return rankings[skip : skip + limit], len(rankings)

    async def list_scenario_rankings(
        self,
        *,
        skip: int,
        limit: int,
        access_scope: TrainingSessionAccessScope,
    ) -> tuple[list[TeamScenarioRankingDTO], int]:
        scope = self._require_team_scope(access_scope)
        async with self._uow_factory(readonly=True) as uow:
            sessions = await self._list_team_sessions(uow, scope)
            evaluation_lookup = uow.competency_evaluation_repository.get_by_report_id
            grouped: dict[tuple[str, str], list[TrainingSession]] = defaultdict(list)
            for session in sessions:
                if not session.scenario_template_id or not session.user_id:
                    continue
                grouped[(session.scenario_template_id, session.user_id)].append(session)

            rankings = [
                await self._build_scenario_ranking(
                    scenario_id=scenario_id,
                    member_id=member_id,
                    sessions=member_sessions,
                    evaluation_lookup=evaluation_lookup,
                )
                for (scenario_id, member_id), member_sessions in grouped.items()
            ]

        resolved_rankings = [item for item in rankings if item is not None]
        self._assign_scenario_ranks(resolved_rankings)
        resolved_rankings.sort(
            key=lambda item: (
                item.rank,
                item.scenario_id,
                item.member_id,
            )
        )
        return resolved_rankings[skip : skip + limit], len(resolved_rankings)

    async def _list_team_sessions(
        self,
        uow: AbstractUnitOfWork,
        scope: TrainingSessionAccessScope,
    ) -> list[TrainingSession]:
        total = await uow.training_session_repository.count(
            team_id=scope.team_id,
            access_scope=scope,
        )
        return await uow.training_session_repository.list(
            skip=0,
            limit=total,
            team_id=scope.team_id,
            access_scope=scope,
        )

    @staticmethod
    def _require_team_scope(
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSessionAccessScope:
        if (
            not access_scope.include_team_scope
            or not (access_scope.team_id or "").strip()
        ):
            raise DomainValidationException(
                "Team analytics requires an authorized team-scoped access scope"
            )
        return access_scope

    def _group_completed_sessions_by_member(
        self,
        sessions: list[TrainingSession],
    ) -> dict[str, list[TrainingSession]]:
        grouped: dict[str, list[TrainingSession]] = defaultdict(list)
        for session in sessions:
            if (
                session.status == TrainingSessionStatus.COMPLETED
                and session.report_id
                and session.user_id
            ):
                grouped[session.user_id].append(session)
        for member_sessions in grouped.values():
            member_sessions.sort(key=self._session_sort_time, reverse=True)
        return grouped

    async def _build_competency_ranking(
        self,
        *,
        member_id: str,
        sessions: list[TrainingSession],
        evaluation_lookup,
        observation_limit: int,
    ) -> TeamCompetencyRankingDTO | None:
        observations: dict[str, list[tuple[int, str | None]]] = {
            dimension: [] for dimension in COMPETENCY_DIMENSIONS
        }

        for session in sessions:
            evaluation = await self._load_evaluation(session, evaluation_lookup)
            if evaluation is None:
                continue
            payload = self._communication_core_payload(evaluation)
            if payload is None:
                continue
            competencies = payload["competencies"]
            for dimension in COMPETENCY_DIMENSIONS:
                if len(observations[dimension]) >= observation_limit:
                    continue
                rating = self._communication_core_rating(
                    competencies.get(dimension),
                    require_opportunity=True,
                )
                if rating is None:
                    continue
                observations[dimension].append((rating, session.scenario_template_id))
            if all(
                len(dimension_observations) >= observation_limit
                for dimension_observations in observations.values()
            ):
                break

        sample_count = max(
            (len(dimension_observations) for dimension_observations in observations.values()),
            default=0,
        )
        if not sample_count:
            return None
        dimensions = [
            TeamCompetencyDimensionDTO(
                dimension_id=dimension,
                score=(
                    self._communication_rating_to_percent(
                        median(rating for rating, _ in observations[dimension])
                    )
                    if observations[dimension]
                    else None
                ),
                sample_count=len(observations[dimension]),
                scenario_count=len(
                    {
                        scenario_id
                        for _, scenario_id in observations[dimension]
                        if scenario_id is not None
                    }
                ),
                state=self._dimension_state(observations[dimension]),
            )
            for dimension in COMPETENCY_DIMENSIONS
        ]
        return TeamCompetencyRankingDTO(
            member_id=member_id,
            sample_count=sample_count,
            dimensions=dimensions,
        )

    async def _build_scenario_ranking(
        self,
        *,
        scenario_id: str,
        member_id: str,
        sessions: list[TrainingSession],
        evaluation_lookup,
    ) -> TeamScenarioRankingDTO | None:
        completed_sessions = [
            session
            for session in sessions
            if session.status == TrainingSessionStatus.COMPLETED
        ]
        if not completed_sessions:
            return None
        scores: list[int] = []
        last_practiced_at: datetime | None = None
        for session in completed_sessions:
            session_time = self._session_sort_time(session)
            if last_practiced_at is None or session_time > self._as_utc(last_practiced_at):
                last_practiced_at = session.completed_at or session.started_at
            evaluation = await self._load_evaluation(session, evaluation_lookup)
            if evaluation is None:
                continue
            payload = self._communication_core_payload(evaluation)
            score = (
                self._communication_outcome_score(payload)
                if payload is not None
                else None
            )
            if score is not None:
                scores.append(score)

        return TeamScenarioRankingDTO(
            scenario_id=scenario_id,
            member_id=member_id,
            rank=0,
            completed_sessions=len(completed_sessions),
            scored_sessions=len(scores),
            average_score=round(sum(scores) / len(scores)) if scores else None,
            last_practiced_at=last_practiced_at,
        )

    @staticmethod
    def _assign_scenario_ranks(rankings: list[TeamScenarioRankingDTO]) -> None:
        """Assign one deterministic rank across all scenario/member rows.

        The endpoint returns a single leaderboard of scenario/member
        combinations. Ranking separately inside each scenario made a page
        with one member per scenario display multiple ``#1`` rows, which was
        misleading and provided no useful ordering.
        """
        rankings.sort(
            key=lambda item: (
                -(item.average_score if item.average_score is not None else -1),
                -item.completed_sessions,
                -TeamTrainingAnalyticsService._as_utc(item.last_practiced_at).timestamp(),
                item.scenario_id,
                item.member_id,
            )
        )
        for rank, ranking in enumerate(rankings, start=1):
            ranking.rank = rank

    async def _load_evaluation(self, session: TrainingSession, evaluation_lookup):
        if not session.report_id:
            return None
        try:
            report_id = int(session.report_id)
        except (TypeError, ValueError):
            return None
        try:
            return await evaluation_lookup(report_id)
        except Exception:
            logger.warning(
                "Failed to resolve competency evaluation for team analytics",
                exc_info=True,
                extra={
                    "training_session_id": session.session_id,
                    "report_id": session.report_id,
                },
            )
            return None

    @staticmethod
    def _communication_core_payload(evaluation: object) -> Mapping[str, object] | None:
        scores = getattr(evaluation, "scores", None)
        if not isinstance(scores, Mapping):
            return None
        if scores.get("rubric_version") != COMMUNICATION_RUBRIC_VERSION:
            return None
        if scores.get("status") != "ready":
            return None
        competencies = scores.get("competencies")
        if not isinstance(competencies, Mapping):
            return None
        return scores

    @staticmethod
    def _communication_core_rating(
        value: object,
        *,
        require_opportunity: bool = False,
    ) -> int | None:
        if not isinstance(value, Mapping):
            return None
        if require_opportunity and value.get("opportunity_present") is not True:
            return None
        value = value.get("rating")
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 1 <= value <= 5 else None

    def _communication_outcome_score(self, payload: Mapping[str, object]) -> int | None:
        ratings = [
            rating
            for rating in (
                self._communication_core_rating(payload.get("effectiveness")),
                self._communication_core_rating(payload.get("appropriateness")),
            )
            if rating is not None
        ]
        if len(ratings) != 2:
            return None
        return self._communication_rating_to_percent(sum(ratings) / len(ratings))

    @staticmethod
    def _communication_rating_to_percent(rating: float) -> int:
        return max(0, min(100, round((rating - 1) * 25)))

    @staticmethod
    def _dimension_state(
        observations: list[tuple[int, str | None]],
    ) -> Literal["exploring", "stable"]:
        scenario_count = len(
            {scenario_id for _, scenario_id in observations if scenario_id is not None}
        )
        if (
            len(observations) >= _STABLE_OBSERVATION_COUNT
            and scenario_count >= _STABLE_SCENARIO_COUNT
        ):
            return "stable"
        return "exploring"

    @staticmethod
    def _session_sort_time(session: TrainingSession) -> datetime:
        return TeamTrainingAnalyticsService._as_utc(
            session.completed_at or session.started_at
        )

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
