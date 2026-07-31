"""Application service for Training Studio session orchestration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.competency_entity import COMPETENCY_DIMENSIONS
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)
from domain.training_studio.session_repository import (
    TrainingSessionAccessScope,
    TrainingSessionRepository,
    training_session_matches_access_scope,
)
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO

logger = logging.getLogger(__name__)


class TrainingSessionDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True, arbitrary_types_allowed=True)

    session_id: str
    task_config: TrainingTaskConfigDTO
    mode: TrainingSessionMode | str
    scenario_template_id: str | None = None
    user_id: str | None = None
    team_id: str | None = None
    status: TrainingSessionStatus | str
    room_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_id: str | None = None
    score_id: str | None = None
    message_count: int
    failure_reason: str | None = None

    @classmethod
    def from_domain(cls, session: TrainingSession) -> "TrainingSessionDTO":
        return cls(
            session_id=session.session_id,
            task_config=TrainingTaskConfigDTO.from_domain(session.task_config),
            mode=session.mode.value,
            scenario_template_id=session.scenario_template_id,
            user_id=session.user_id,
            team_id=session.team_id,
            status=session.status.value,
            room_id=session.room_id,
            started_at=session.started_at,
            completed_at=session.completed_at,
            report_id=session.report_id,
            score_id=session.score_id,
            message_count=session.message_count,
            failure_reason=session.failure_reason,
        )


class CreateTrainingSessionDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    task_config: TrainingTaskConfigDTO
    mode: TrainingSessionMode | str = TrainingSessionMode.TEXT
    scenario_template_id: str | None = None
    user_id: str | None = None
    team_id: str | None = None


class ScenarioTrainingProgressDTO(BaseModel):
    scenario_id: str
    user_id: str | None = None
    team_id: str | None = None
    status: str
    failure_reason: str | None = None
    score: int | None = None
    score_status: Literal["ready", "pending"] = "pending"
    overall_score: float | None = None
    evaluation_id: int | None = None
    last_practiced_at: datetime | None = None
    training_session_id: str
    report_id: str | None = None
    score_id: str | None = None


class ScenarioTrainingProgressSummaryDTO(BaseModel):
    tracked_scenarios: int
    completed_scenarios: int
    scored_scenarios: int
    average_score: int | None = None
    completion_percentage: int


class TrainingCompetencyRadarDimensionDTO(BaseModel):
    dimension_id: str
    score: int
    sample_count: int


class TrainingCompetencyRadarDTO(BaseModel):
    sample_size: int
    dimensions: list[TrainingCompetencyRadarDimensionDTO]


RoomCreator = Callable[[TrainingSession], str]
EvaluationLookup = Callable[[int], Awaitable[object | None]]


class InMemoryTrainingSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, TrainingSession] = {}

    async def save(self, session: TrainingSession) -> TrainingSession:
        self._sessions[session.session_id] = session
        return session

    async def get(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> TrainingSession | None:
        session = self._sessions.get(session_id)
        if session is not None and not training_session_matches_access_scope(
            session,
            access_scope,
        ):
            return None
        return session

    async def delete(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> bool:
        session = await self.get(session_id, access_scope=access_scope)
        if session is None:
            return False
        del self._sessions[session_id]
        return True

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> list[TrainingSession]:
        sessions = list(self._sessions.values())
        if access_scope is not None:
            sessions = [
                session
                for session in sessions
                if training_session_matches_access_scope(session, access_scope)
            ]
        if user_id:
            sessions = [session for session in sessions if session.user_id == user_id]
        if team_id:
            sessions = [session for session in sessions if session.team_id == team_id]
        if scenario_template_id:
            sessions = [
                session for session in sessions
                if session.scenario_template_id == scenario_template_id
            ]
        return sessions[skip : skip + limit]

    async def count(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> int:
        sessions = await self.list(
            skip=0,
            limit=len(self._sessions),
            user_id=user_id,
            team_id=team_id,
            scenario_template_id=scenario_template_id,
            access_scope=access_scope,
        )
        return len(sessions)


class TrainingSessionService:
    """Coordinates session lifecycle without owning persistence or chat-room creation."""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., AbstractUnitOfWork] | None = None,
        repository: TrainingSessionRepository | None = None,
        room_creator: RoomCreator | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._repository = repository or InMemoryTrainingSessionRepository()
        self._room_creator = room_creator
        self._id_factory = id_factory or (lambda: str(uuid4()))

    async def create_session(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | TrainingTaskConfig | dict,
        mode: TrainingSessionMode | str = TrainingSessionMode.TEXT,
    ) -> TrainingSession:
        task_config, session_mode, scenario_template_id, user_id, team_id = self._resolve_create_payload(payload, mode)
        session = TrainingSession(
            session_id=self._id_factory(),
            task_config=task_config,
            mode=session_mode,
            scenario_template_id=scenario_template_id,
            user_id=user_id,
            team_id=team_id,
        )
        return await self._save(session)

    async def start_session(
        self,
        session_id: str,
        room_id: str | None = None,
        *,
        metadata: Mapping[str, object] | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        session = await self._require_session(session_id, access_scope=access_scope)
        resolved_room_id = room_id
        if resolved_room_id is None:
            if self._room_creator is None:
                raise ValueError("room_creator is required when room_id is not provided")
            resolved_room_id = self._room_creator(session)
        _merge_task_config_metadata(session, metadata)
        session.start(resolved_room_id)
        return await self._save(session)

    async def delete_session(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> None:
        scope = _require_access_scope(access_scope)
        await self._require_session(session_id, access_scope=scope)
        if self._uow_factory is None:
            deleted = await self._repository.delete(session_id, access_scope=scope)
        else:
            async with self._uow_factory() as uow:
                deleted = await uow.training_session_repository.delete(
                    session_id,
                    access_scope=scope,
                )
        if not deleted:
            raise ValueError(f"Training session not found: {session_id}")

    async def complete_session(
        self,
        session_id: str,
        report_id: str | None = None,
        score_id: str | None = None,
        *,
        metadata: Mapping[str, object] | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        session = await self._require_session(session_id, access_scope=access_scope)
        _merge_task_config_metadata(session, metadata)
        session.complete(report_id=report_id, score_id=score_id)
        return await self._save(session)

    async def record_completion_report(
        self,
        session_id: str,
        report_id: str | None = None,
        score_id: str | None = None,
        *,
        metadata: Mapping[str, object] | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        session = await self._require_session(session_id, access_scope=access_scope)
        if session.status != TrainingSessionStatus.COMPLETED:
            raise ValueError(f"Cannot record completion report while {session.status.value}")
        _merge_task_config_metadata(session, metadata)
        if report_id is not None:
            session.attach_completion_report(report_id, score_id=score_id)
        elif score_id is not None:
            session.score_id = score_id.strip() if score_id and score_id.strip() else None
        return await self._save(session)

    async def fail_session(
        self,
        session_id: str,
        reason: str,
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        session = await self._require_session(session_id, access_scope=access_scope)
        session.fail(reason)
        return await self._save(session)

    async def record_turns(
        self,
        session_id: str,
        count: int = 1,
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        session = await self._require_session(session_id, access_scope=access_scope)
        session.record_turn(count)
        return await self._save(session)

    async def get_session(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> TrainingSession:
        return await self._require_session(session_id, access_scope=access_scope)

    async def list_sessions(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> list[TrainingSession]:
        sessions, _ = await self.list_sessions_page(
            skip=skip,
            limit=limit,
            user_id=user_id,
            team_id=team_id,
            scenario_template_id=scenario_template_id,
            access_scope=access_scope,
        )
        return sessions

    async def list_sessions_page(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> tuple[list[TrainingSession], int]:
        scope = _require_access_scope(access_scope)
        user_id = self._normalize_optional_text(user_id)
        team_id = self._normalize_optional_text(team_id)
        scenario_template_id = self._normalize_optional_text(scenario_template_id)
        if self._uow_factory is None:
            sessions = await self._repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
                access_scope=scope,
            )
            total = await self._repository.count(
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
                access_scope=scope,
            )
            return sessions, total
        async with self._uow_factory(readonly=True) as uow:
            sessions = await uow.training_session_repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
                access_scope=scope,
            )
            total = await uow.training_session_repository.count(
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
                access_scope=scope,
            )
        return sessions, total

    async def list_scenario_progress(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> list[ScenarioTrainingProgressDTO]:
        progress, _ = await self.list_scenario_progress_page(
            skip=skip,
            limit=limit,
            user_id=user_id,
            team_id=team_id,
            access_scope=access_scope,
        )
        return progress

    async def list_scenario_progress_page(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> tuple[list[ScenarioTrainingProgressDTO], int]:
        progress = await self._load_scenario_progress(
            user_id=user_id,
            team_id=team_id,
            access_scope=access_scope,
        )
        return progress[skip : skip + limit], len(progress)

    async def get_scenario_progress_summary(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        access_scope: TrainingSessionAccessScope,
    ) -> ScenarioTrainingProgressSummaryDTO:
        progress = await self._load_scenario_progress(
            user_id=user_id,
            team_id=team_id,
            access_scope=access_scope,
        )
        scored_progress = [
            item
            for item in progress
            if item.score_status == "ready" and item.score is not None
        ]
        tracked_scenarios = len(progress)
        completed_scenarios = sum(
            item.status == "completed" for item in progress
        )
        scored_scenarios = len(scored_progress)
        average_score = (
            round(sum(item.score or 0 for item in scored_progress) / scored_scenarios)
            if scored_scenarios
            else None
        )
        return ScenarioTrainingProgressSummaryDTO(
            tracked_scenarios=tracked_scenarios,
            completed_scenarios=completed_scenarios,
            scored_scenarios=scored_scenarios,
            average_score=average_score,
            completion_percentage=(
                round((completed_scenarios / tracked_scenarios) * 100)
                if tracked_scenarios
                else 0
            ),
        )

    async def get_competency_radar(
        self,
        *,
        user_id: str | None,
        team_id: str | None,
        access_scope: TrainingSessionAccessScope,
        recent_limit: int = 10,
    ) -> TrainingCompetencyRadarDTO:
        scope = _require_access_scope(access_scope)
        user_id = self._normalize_optional_text(user_id)
        team_id = self._normalize_optional_text(team_id)
        if self._uow_factory is None:
            return TrainingCompetencyRadarDTO(sample_size=0, dimensions=[])

        async with self._uow_factory(readonly=True) as uow:
            total = await uow.training_session_repository.count(
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            sessions = await uow.training_session_repository.list(
                skip=0,
                limit=total,
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            evaluation_lookup = uow.competency_evaluation_repository.get_by_report_id

            totals = {dimension: 0.0 for dimension in COMPETENCY_DIMENSIONS}
            counts = {dimension: 0 for dimension in COMPETENCY_DIMENSIONS}
            sample_size = 0
            for session in sorted(
                sessions,
                key=self._session_sort_time,
                reverse=True,
            ):
                if (
                    sample_size >= recent_limit
                    or session.status != TrainingSessionStatus.COMPLETED
                    or not session.report_id
                ):
                    continue
                try:
                    report_id = int(session.report_id)
                except (TypeError, ValueError):
                    continue
                evaluation = await evaluation_lookup(report_id)
                if evaluation is None:
                    continue

                sample_size += 1
                scores = getattr(evaluation, "scores", {})
                if not isinstance(scores, Mapping):
                    continue
                for dimension in COMPETENCY_DIMENSIONS:
                    normalized = self._normalize_competency_score(
                        scores.get(dimension)
                    )
                    if normalized is None:
                        continue
                    totals[dimension] += normalized
                    counts[dimension] += 1

        return TrainingCompetencyRadarDTO(
            sample_size=sample_size,
            dimensions=[
                TrainingCompetencyRadarDimensionDTO(
                    dimension_id=dimension,
                    score=round(totals[dimension] / counts[dimension]),
                    sample_count=counts[dimension],
                )
                for dimension in COMPETENCY_DIMENSIONS
                if counts[dimension] > 0
            ],
        )

    async def _load_scenario_progress(
        self,
        *,
        user_id: str | None,
        team_id: str | None,
        access_scope: TrainingSessionAccessScope,
    ) -> list[ScenarioTrainingProgressDTO]:
        scope = _require_access_scope(access_scope)
        user_id = self._normalize_optional_text(user_id)
        team_id = self._normalize_optional_text(team_id)
        if self._uow_factory is None:
            total = await self._repository.count(
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            sessions = await self._repository.list(
                skip=0,
                limit=total,
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            return await self._build_scenario_progress(sessions)

        async with self._uow_factory(readonly=True) as uow:
            total = await uow.training_session_repository.count(
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            sessions = await uow.training_session_repository.list(
                skip=0,
                limit=total,
                user_id=user_id,
                team_id=team_id,
                access_scope=scope,
            )
            return await self._build_scenario_progress(
                sessions,
                evaluation_lookup=uow.competency_evaluation_repository.get_by_report_id,
            )

    async def _build_scenario_progress(
        self,
        sessions: list[TrainingSession],
        evaluation_lookup: EvaluationLookup | None = None,
    ) -> list[ScenarioTrainingProgressDTO]:
        latest_by_scenario: dict[str, TrainingSession] = {}

        for session in sessions:
            scenario_id = self._scenario_training_id(session)
            if scenario_id is None:
                continue
            current = latest_by_scenario.get(scenario_id)
            if current is None or self._is_later_session(session, current):
                latest_by_scenario[scenario_id] = session

        progress = [
            await self._session_to_scenario_progress(session, evaluation_lookup)
            for session in latest_by_scenario.values()
        ]

        return sorted(
            progress,
            key=lambda item: self._as_utc_datetime(item.last_practiced_at),
            reverse=True,
        )

    async def _session_to_scenario_progress(
        self,
        session: TrainingSession,
        evaluation_lookup: EvaluationLookup | None = None,
    ) -> ScenarioTrainingProgressDTO:
        score_data = await self._scenario_training_score(session, evaluation_lookup)
        return ScenarioTrainingProgressDTO(
            scenario_id=session.scenario_template_id or "",
            user_id=session.user_id,
            team_id=session.team_id,
            status=self._scenario_training_status(session),
            failure_reason=session.failure_reason,
            score=score_data["score"],
            score_status=score_data["score_status"],
            overall_score=score_data["overall_score"],
            evaluation_id=score_data["evaluation_id"],
            last_practiced_at=session.completed_at or session.started_at,
            training_session_id=session.session_id,
            report_id=session.report_id,
            score_id=session.score_id,
        )

    def _resolve_create_payload(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | TrainingTaskConfig | dict,
        mode: TrainingSessionMode | str,
    ) -> tuple[TrainingTaskConfig, TrainingSessionMode | str, str | None, str | None, str | None]:
        if isinstance(payload, CreateTrainingSessionDTO):
            return (
                payload.task_config.to_domain(),
                payload.mode,
                self._normalize_optional_text(payload.scenario_template_id),
                self._normalize_optional_text(payload.user_id),
                self._normalize_optional_text(payload.team_id),
            )
        if isinstance(payload, TrainingTaskConfigDTO):
            return payload.to_domain(), mode, None, None, None
        if isinstance(payload, TrainingTaskConfig):
            return payload, mode, None, None, None
        if "task_config" in payload:
            dto = CreateTrainingSessionDTO(**payload)
            return (
                dto.task_config.to_domain(),
                dto.mode,
                self._normalize_optional_text(dto.scenario_template_id),
                self._normalize_optional_text(dto.user_id),
                self._normalize_optional_text(dto.team_id),
            )
        flat_payload = dict(payload)
        session_mode = flat_payload.pop("mode", mode)
        scenario_template_id = self._normalize_optional_text(flat_payload.pop("scenario_template_id", None))
        user_id = self._normalize_optional_text(flat_payload.pop("user_id", None))
        team_id = self._normalize_optional_text(flat_payload.pop("team_id", None))
        return TrainingTaskConfigDTO(**flat_payload).to_domain(), session_mode, scenario_template_id, user_id, team_id

    async def _save(self, session: TrainingSession) -> TrainingSession:
        if self._uow_factory is None:
            return await self._repository.save(session)
        async with self._uow_factory() as uow:
            saved = await uow.training_session_repository.save(session)
        return saved

    async def _require_session(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None,
    ) -> TrainingSession:
        scope = _require_access_scope(access_scope)
        if self._uow_factory is None:
            repository = self._repository
            session = await repository.get(session_id, access_scope=scope)
            if session is None:
                await self._raise_missing_or_forbidden(
                    repository,
                    session_id,
                    scope,
                )
        else:
            async with self._uow_factory(readonly=True) as uow:
                repository = uow.training_session_repository
                session = await repository.get(session_id, access_scope=scope)
                if session is None:
                    await self._raise_missing_or_forbidden(
                        repository,
                        session_id,
                        scope,
                    )
        return session

    async def _raise_missing_or_forbidden(
        self,
        repository: TrainingSessionRepository,
        session_id: str,
        access_scope: TrainingSessionAccessScope,
    ) -> None:
        existing = await repository.get(session_id)
        if existing is not None:
            raise PermissionError("Training session is outside current user scope")
        raise ValueError(f"Training session not found: {session_id}")

    def _scenario_training_id(self, session: TrainingSession) -> str | None:
        return session.scenario_template_id

    def _scenario_training_status(self, session: TrainingSession) -> str:
        if session.status == TrainingSessionStatus.COMPLETED:
            return "completed"
        if session.status == TrainingSessionStatus.FAILED:
            return "failed"
        if session.status == TrainingSessionStatus.CREATED:
            return "not_started"
        return "in_progress"

    async def _scenario_training_score(
        self,
        session: TrainingSession,
        evaluation_lookup: EvaluationLookup | None = None,
    ) -> dict[str, int | float | str | None]:
        if session.report_id and evaluation_lookup is not None:
            try:
                report_id = int(session.report_id)
            except ValueError:
                report_id = None
            if report_id is not None:
                try:
                    evaluation = await evaluation_lookup(report_id)
                except Exception:
                    logger.warning(
                        "Failed to resolve competency evaluation for scenario progress",
                        exc_info=True,
                        extra={
                            "training_session_id": session.session_id,
                            "report_id": session.report_id,
                        },
                    )
                    evaluation = None
                if evaluation is not None:
                    try:
                        overall_score = float(getattr(evaluation, "overall_score", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        logger.warning(
                            "Ignoring invalid competency evaluation score for scenario progress",
                            extra={
                                "training_session_id": session.session_id,
                                "report_id": session.report_id,
                                "evaluation_id": getattr(evaluation, "id", None),
                            },
                        )
                    else:
                        return {
                            "score": self._overall_score_to_percent(overall_score),
                            "score_status": "ready",
                            "overall_score": overall_score,
                            "evaluation_id": getattr(evaluation, "id", None),
                        }

        return {
            "score": None,
            "score_status": "pending",
            "overall_score": None,
            "evaluation_id": None,
        }

    def _overall_score_to_percent(self, overall_score: float) -> int:
        return max(0, min(100, round(overall_score * 20)))

    def _normalize_competency_score(self, value: object) -> int | None:
        if isinstance(value, Mapping):
            value = value.get("score")
        else:
            value = getattr(value, "score", value)
        try:
            score = float(value)
        except (TypeError, ValueError):
            return None
        if 1 <= score <= 5:
            return round(score * 20)
        if 0 <= score <= 100:
            return round(score)
        return None

    def _is_later_session(self, candidate: TrainingSession, current: TrainingSession) -> bool:
        candidate_time = self._session_sort_time(candidate)
        current_time = self._session_sort_time(current)
        if candidate_time != current_time:
            return candidate_time > current_time
        return candidate.session_id > current.session_id

    def _session_sort_time(self, session: TrainingSession) -> datetime:
        return self._as_utc_datetime(session.completed_at or session.started_at)

    def _as_utc_datetime(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _normalize_optional_text(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


def _require_access_scope(
    access_scope: TrainingSessionAccessScope | None,
) -> TrainingSessionAccessScope:
    if access_scope is None:
        raise DomainValidationException(
            "access_scope is required for training session access",
            field="access_scope",
            message_key="training_session.scope.required",
        )
    return access_scope


def _merge_task_config_metadata(
    session: TrainingSession,
    metadata: Mapping[str, object] | None,
) -> None:
    if not metadata:
        return
    merged = dict(session.task_config.metadata or {})
    for key, value in metadata.items():
        text_key = str(key).strip()
        if text_key:
            merged[text_key] = deepcopy(value)
    session.task_config.metadata = merged
