"""Training studio session aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from domain.training_studio.catalog import TrainingTaskConfig, normalize_training_task_config


class TrainingSessionMode(StrEnum):
    TEXT = "text"
    VOICE = "voice"
    VIDEO = "video"
    REALTIME = "realtime"


class TrainingSessionStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TrainingSession:
    session_id: str
    task_config: TrainingTaskConfig
    mode: TrainingSessionMode | str
    scenario_template_id: str | None = None
    user_id: str | None = None
    team_id: str | None = None
    status: TrainingSessionStatus | str = TrainingSessionStatus.CREATED
    room_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    report_id: str | None = None
    score_id: str | None = None
    message_count: int = 0
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        self.session_id = self.session_id.strip()
        if not self.session_id:
            raise ValueError("session_id cannot be empty")
        self.task_config = normalize_training_task_config(self.task_config)
        self.mode = self._coerce_enum(TrainingSessionMode, self.mode, "mode")
        self.status = self._coerce_enum(TrainingSessionStatus, self.status, "status")
        if self.scenario_template_id is not None:
            self.scenario_template_id = self.scenario_template_id.strip() or None
        if self.user_id is not None:
            self.user_id = self.user_id.strip() or None
        if self.team_id is not None:
            self.team_id = self.team_id.strip() or None
        if self.room_id is not None:
            self.room_id = self.room_id.strip() or None
        if self.report_id is not None:
            self.report_id = self.report_id.strip() or None
        if self.score_id is not None:
            self.score_id = self.score_id.strip() or None
        if self.message_count < 0:
            raise ValueError("message_count cannot be negative")

    def start(self, room_id: str) -> None:
        if self.status != TrainingSessionStatus.CREATED:
            raise ValueError(f"Cannot start session while {self.status.value}")
        normalized_room_id = room_id.strip()
        if not normalized_room_id:
            raise ValueError("room_id cannot be empty")
        self.room_id = normalized_room_id
        self.started_at = datetime.now(UTC)
        self.status = TrainingSessionStatus.ACTIVE

    def record_turn(self, count: int = 1) -> None:
        if self.status != TrainingSessionStatus.ACTIVE:
            raise ValueError(f"Cannot record turns while {self.status.value}")
        if count < 1:
            raise ValueError("count must be greater than 0")
        self.message_count += count

    def complete(self, report_id: str | None = None, score_id: str | None = None) -> None:
        if self.status != TrainingSessionStatus.ACTIVE:
            raise ValueError(f"Cannot complete session while {self.status.value}")
        self.report_id = report_id.strip() if report_id and report_id.strip() else None
        self.score_id = score_id.strip() if score_id and score_id.strip() else None
        self.completed_at = datetime.now(UTC)
        self.status = TrainingSessionStatus.COMPLETED

    def attach_completion_report(
        self,
        report_id: str,
        score_id: str | None = None,
    ) -> None:
        if self.status != TrainingSessionStatus.COMPLETED:
            raise ValueError(f"Cannot attach report while {self.status.value}")
        normalized_report_id = report_id.strip()
        if not normalized_report_id:
            raise ValueError("report_id cannot be empty")
        self.report_id = normalized_report_id
        if score_id is not None:
            self.score_id = score_id.strip() if score_id and score_id.strip() else None

    def fail(self, reason: str) -> None:
        if self.status not in {TrainingSessionStatus.CREATED, TrainingSessionStatus.ACTIVE}:
            raise ValueError(f"Cannot fail session while {self.status.value}")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("reason cannot be empty")
        self.failure_reason = normalized_reason
        self.completed_at = datetime.now(UTC)
        self.status = TrainingSessionStatus.FAILED

    def _coerce_enum(
        self,
        enum_type: type[TrainingSessionMode] | type[TrainingSessionStatus],
        value: StrEnum | str,
        field_name: str,
    ) -> TrainingSessionMode | TrainingSessionStatus:
        if isinstance(value, enum_type):
            return value
        try:
            return enum_type(str(value).strip().lower())
        except ValueError as exc:
            raise ValueError(f"Invalid {field_name}: {value}") from exc
