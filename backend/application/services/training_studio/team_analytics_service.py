"""Scoped team-level analytics derived from training sessions and evaluations."""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from pydantic import BaseModel

from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.competency_entity import COMPETENCY_DIMENSIONS
from domain.training_studio.session import TrainingSession, TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope

logger = logging.getLogger(__name__)


class TeamCompetencyDimensionDTO(BaseModel):
    dimension_id: str
    score: int | None = None
    sample_count: int


class TeamCompetencyRankingDTO(BaseModel):
    member_id: str
    member_name: str | None = None
    rank: int
    average_score: int | None = None
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
        recent_limit = max(1, min(50, recent_limit_per_member))
        async with self._uow_factory(readonly=True) as uow:
            sessions = await self._list_team_sessions(uow, scope)
            evaluation_lookup = uow.competency_evaluation_repository.get_by_report_id
            grouped = self._group_completed_sessions_by_member(sessions)
            rankings: list[TeamCompetencyRankingDTO] = []
            for member_id, member_sessions in grouped.items():
                ranking = await self._build_competency_ranking(
                    member_id=member_id,
                    sessions=member_sessions[:recent_limit],
                    evaluation_lookup=evaluation_lookup,
                )
                if ranking is not None:
                    rankings.append(ranking)

        rankings.sort(
            key=lambda item: (
                -(item.average_score if item.average_score is not None else -1),
                -item.sample_count,
                item.member_id,
            )
        )
        for rank, ranking in enumerate(rankings, start=1):
            ranking.rank = rank
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
                item.scenario_id,
                item.rank,
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
    ) -> TeamCompetencyRankingDTO | None:
        totals = {dimension: 0.0 for dimension in COMPETENCY_DIMENSIONS}
        counts = {dimension: 0 for dimension in COMPETENCY_DIMENSIONS}
        overall_scores: list[int] = []
        sample_count = 0

        for session in sessions:
            evaluation = await self._load_evaluation(session, evaluation_lookup)
            if evaluation is None:
                continue
            sample_count += 1
            dimensions = getattr(evaluation, "scores", {})
            if isinstance(dimensions, Mapping):
                for dimension in COMPETENCY_DIMENSIONS:
                    score = self._normalize_dimension_score(dimensions.get(dimension))
                    if score is None:
                        continue
                    totals[dimension] += score
                    counts[dimension] += 1
            overall_score = self._normalize_overall_score(
                getattr(evaluation, "overall_score", None)
            )
            if overall_score is not None:
                overall_scores.append(overall_score)

        if not sample_count:
            return None
        dimensions = [
            TeamCompetencyDimensionDTO(
                dimension_id=dimension,
                score=(round(totals[dimension] / counts[dimension]) if counts[dimension] else None),
                sample_count=counts[dimension],
            )
            for dimension in COMPETENCY_DIMENSIONS
        ]
        average_score = (
            round(sum(overall_scores) / len(overall_scores)) if overall_scores else None
        )
        if average_score is None:
            dimensional_scores = [dimension.score for dimension in dimensions if dimension.score is not None]
            average_score = (
                round(sum(dimensional_scores) / len(dimensional_scores))
                if dimensional_scores
                else None
            )
        return TeamCompetencyRankingDTO(
            member_id=member_id,
            rank=0,
            average_score=average_score,
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
            score = self._normalize_overall_score(
                getattr(evaluation, "overall_score", None)
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
        by_scenario: dict[str, list[TeamScenarioRankingDTO]] = defaultdict(list)
        for ranking in rankings:
            by_scenario[ranking.scenario_id].append(ranking)
        for scenario_rankings in by_scenario.values():
            scenario_rankings.sort(
                key=lambda item: (
                    -(item.average_score if item.average_score is not None else -1),
                    -item.completed_sessions,
                    -TeamTrainingAnalyticsService._as_utc(item.last_practiced_at).timestamp(),
                    item.member_id,
                )
            )
            for rank, ranking in enumerate(scenario_rankings, start=1):
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
    def _normalize_dimension_score(value: object) -> int | None:
        if isinstance(value, Mapping):
            value = value.get("score")
        else:
            value = getattr(value, "score", value)
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(score):
            return None
        if 1 <= score <= 5:
            return round(score * 20)
        if 0 <= score <= 100:
            return round(score)
        return None

    @staticmethod
    def _normalize_overall_score(value: object) -> int | None:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(score):
            return None
        if 0 <= score <= 5:
            return round(score * 20)
        if 0 <= score <= 100:
            return round(score)
        return None

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
