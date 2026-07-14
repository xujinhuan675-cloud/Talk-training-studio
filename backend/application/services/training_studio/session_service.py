"""Application service for Training Studio session orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)


class TrainingSessionDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True, arbitrary_types_allowed=True)

    session_id: str
    task_config: TrainingTaskConfigDTO
    mode: TrainingSessionMode | str
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


class TrainingSessionRepository(Protocol):
    def save(self, session: TrainingSession) -> TrainingSession:
        ...

    def get(self, session_id: str) -> TrainingSession | None:
        ...

    def list(self) -> list[TrainingSession]:
        ...


class InMemoryTrainingSessionRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, TrainingSession] = {}

    def save(self, session: TrainingSession) -> TrainingSession:
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> TrainingSession | None:
        return self._sessions.get(session_id)

    def list(self) -> list[TrainingSession]:
        return list(self._sessions.values())


RoomCreator = Callable[[TrainingSession], str]


class TrainingSessionService:
    """Coordinates session lifecycle without owning persistence or chat-room creation."""

    def __init__(
        self,
        repository: TrainingSessionRepository | None = None,
        room_creator: RoomCreator | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository or InMemoryTrainingSessionRepository()
        self._room_creator = room_creator
        self._id_factory = id_factory or (lambda: str(uuid4()))

    def create_session(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | TrainingTaskConfig | dict,
        mode: TrainingSessionMode | str = TrainingSessionMode.TEXT,
    ) -> TrainingSession:
        task_config, session_mode = self._resolve_create_payload(payload, mode)
        session = TrainingSession(
            session_id=self._id_factory(),
            task_config=task_config,
            mode=session_mode,
        )
        return self._repository.save(session)

    def start_session(self, session_id: str, room_id: str | None = None) -> TrainingSession:
        session = self._require_session(session_id)
        resolved_room_id = room_id
        if resolved_room_id is None:
            if self._room_creator is None:
                raise ValueError("room_creator is required when room_id is not provided")
            resolved_room_id = self._room_creator(session)
        session.start(resolved_room_id)
        return self._repository.save(session)

    def complete_session(
        self,
        session_id: str,
        report_id: str | None = None,
        score_id: str | None = None,
    ) -> TrainingSession:
        session = self._require_session(session_id)
        session.complete(report_id=report_id, score_id=score_id)
        return self._repository.save(session)

    def get_session(self, session_id: str) -> TrainingSession:
        return self._require_session(session_id)

    def list_sessions(self) -> list[TrainingSession]:
        return self._repository.list()

    def _resolve_create_payload(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | TrainingTaskConfig | dict,
        mode: TrainingSessionMode | str,
    ) -> tuple[TrainingTaskConfig, TrainingSessionMode | str]:
        if isinstance(payload, CreateTrainingSessionDTO):
            return payload.task_config.to_domain(), payload.mode
        if isinstance(payload, TrainingTaskConfigDTO):
            return payload.to_domain(), mode
        if isinstance(payload, TrainingTaskConfig):
            return payload, mode
        if "task_config" in payload:
            dto = CreateTrainingSessionDTO(**payload)
            return dto.task_config.to_domain(), dto.mode
        flat_payload = dict(payload)
        session_mode = flat_payload.pop("mode", mode)
        return TrainingTaskConfigDTO(**flat_payload).to_domain(), session_mode

    def _require_session(self, session_id: str) -> TrainingSession:
        session = self._repository.get(session_id)
        if session is None:
            raise ValueError(f"Training session not found: {session_id}")
        return session
