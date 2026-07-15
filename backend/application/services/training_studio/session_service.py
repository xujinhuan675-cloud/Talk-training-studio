"""Application service for Training Studio session orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from domain.common.unit_of_work import AbstractUnitOfWork
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)
from domain.training_studio.session_repository import TrainingSessionRepository
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO


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
    score: int | None = None
    score_status: Literal["ready", "pending"] = "pending"
    overall_score: float | None = None
    evaluation_id: int | None = None
    last_practiced_at: datetime | None = None
    training_session_id: str
    report_id: str | None = None
    score_id: str | None = None


RoomCreator = Callable[[TrainingSession], str]
EvaluationLookup = Callable[[int], Awaitable[object | None]]


class InMemoryTrainingSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, TrainingSession] = {}

    async def save(self, session: TrainingSession) -> TrainingSession:
        self._sessions[session.session_id] = session
        return session

    async def get(self, session_id: str) -> TrainingSession | None:
        return self._sessions.get(session_id)

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
    ) -> list[TrainingSession]:
        sessions = list(self._sessions.values())
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

    async def start_session(self, session_id: str, room_id: str | None = None) -> TrainingSession:
        session = await self._require_session(session_id)
        resolved_room_id = room_id
        if resolved_room_id is None:
            if self._room_creator is None:
                raise ValueError("room_creator is required when room_id is not provided")
            resolved_room_id = self._room_creator(session)
        session.start(resolved_room_id)
        return await self._save(session)

    async def complete_session(
        self,
        session_id: str,
        report_id: str | None = None,
        score_id: str | None = None,
    ) -> TrainingSession:
        session = await self._require_session(session_id)
        session.complete(report_id=report_id, score_id=score_id)
        return await self._save(session)

    async def get_session(self, session_id: str) -> TrainingSession:
        return await self._require_session(session_id)

    async def list_sessions(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
    ) -> list[TrainingSession]:
        user_id = self._normalize_optional_text(user_id)
        team_id = self._normalize_optional_text(team_id)
        scenario_template_id = self._normalize_optional_text(scenario_template_id)
        if self._uow_factory is None:
            return await self._repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
            )
        async with self._uow_factory(readonly=True) as uow:
            sessions = await uow.training_session_repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
                scenario_template_id=scenario_template_id,
            )
        return sessions

    async def list_scenario_progress(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
    ) -> list[ScenarioTrainingProgressDTO]:
        user_id = self._normalize_optional_text(user_id)
        team_id = self._normalize_optional_text(team_id)
        if self._uow_factory is None:
            sessions = await self._repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
            )
            return await self._build_scenario_progress(sessions)

        async with self._uow_factory(readonly=True) as uow:
            sessions = await uow.training_session_repository.list(
                skip=skip,
                limit=limit,
                user_id=user_id,
                team_id=team_id,
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
            key=lambda item: item.last_practiced_at or datetime.min.replace(tzinfo=UTC),
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

    async def _require_session(self, session_id: str) -> TrainingSession:
        if self._uow_factory is None:
            session = await self._repository.get(session_id)
        else:
            async with self._uow_factory(readonly=True) as uow:
                session = await uow.training_session_repository.get(session_id)
        if session is None:
            raise ValueError(f"Training session not found: {session_id}")
        return session

    def _scenario_training_id(self, session: TrainingSession) -> str | None:
        return session.scenario_template_id

    def _scenario_training_status(self, session: TrainingSession) -> str:
        if session.status == TrainingSessionStatus.COMPLETED:
            return "completed"
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
                evaluation = await evaluation_lookup(report_id)
                if evaluation is not None:
                    overall_score = float(getattr(evaluation, "overall_score", 0.0) or 0.0)
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

    def _is_later_session(self, candidate: TrainingSession, current: TrainingSession) -> bool:
        fallback = datetime.min.replace(tzinfo=UTC)
        candidate_time = candidate.completed_at or candidate.started_at or fallback
        current_time = current.completed_at or current.started_at or fallback
        if candidate_time != current_time:
            return candidate_time > current_time
        return candidate.session_id > current.session_id

    def _normalize_optional_text(self, value: object | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
