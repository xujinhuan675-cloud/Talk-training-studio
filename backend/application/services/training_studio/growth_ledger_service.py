"""Persistent Training Points and level progression."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isqrt

from domain.training_studio.growth import TrainingPointEvent
from domain.training_studio.session import TrainingSessionStatus


TRAINING_COMPLETION_POINTS = 100
_LEVEL_STEP_POINTS = 500
_LEVEL_TITLES = (
    "Foundation",
    "Practitioner",
    "Specialist",
    "Strategist",
    "Mentor",
)


@dataclass(frozen=True)
class TrainingGrowthSummary:
    total_points: int
    level: int
    level_title: str
    current_level_points: int
    next_level_points: int
    level_progress_percentage: int
    completed_sessions: int
    recent_events: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "unit": "TP",
            "unit_name": "Training Points",
            "total_points": self.total_points,
            "level": self.level,
            "level_title": self.level_title,
            "current_level_points": self.current_level_points,
            "next_level_points": self.next_level_points,
            "level_progress_percentage": self.level_progress_percentage,
            "completed_sessions": self.completed_sessions,
            "recent_events": list(self.recent_events),
        }


class TrainingGrowthLedgerService:
    """Derive an auditable, idempotent growth ledger from owned sessions."""

    async def sync_completed_sessions(self, uow, *, user_id: str) -> None:
        repository = uow.training_point_event_repository
        existing = await repository.list_source_ids(
            user_id=user_id,
            source_type="training_session",
            event_type="session_completed",
        )
        offset = 0
        page_size = 200
        while True:
            sessions = await uow.training_session_repository.list(
                skip=offset,
                limit=page_size,
                user_id=user_id,
            )
            for session in sessions:
                if (
                    session.status != TrainingSessionStatus.COMPLETED
                    or session.user_id != user_id
                    or session.session_id in existing
                ):
                    continue
                event = TrainingPointEvent(
                    user_id=user_id,
                    team_id=session.team_id,
                    source_type="training_session",
                    source_id=session.session_id,
                    event_type="session_completed",
                    points=TRAINING_COMPLETION_POINTS,
                    created_at=(
                        session.completed_at
                        or session.started_at
                        or datetime.now(UTC)
                    ),
                )
                repository_added = await repository.add(event)
                if repository_added:
                    existing.add(session.session_id)
            if len(sessions) < page_size:
                break
            offset += page_size

    async def summary(self, uow, *, user_id: str) -> TrainingGrowthSummary:
        await self.sync_completed_sessions(uow, user_id=user_id)
        repository = uow.training_point_event_repository
        total_points = await repository.sum_points(user_id=user_id)
        recent_events = tuple(
            {
                "id": event.id,
                "event_type": event.event_type,
                "points": event.points,
                "source_type": event.source_type,
                "source_id": event.source_id,
                "created_at": event.created_at,
            }
            for event in await repository.recent(user_id=user_id, limit=10)
        )
        completed_sessions = await repository.count(
            user_id=user_id,
            event_type="session_completed",
        )
        level = _level_for_points(total_points)
        current_threshold = _level_threshold(level)
        next_threshold = _level_threshold(level + 1)
        progress = round(
            (total_points - current_threshold)
            * 100
            / max(1, next_threshold - current_threshold)
        )
        return TrainingGrowthSummary(
            total_points=total_points,
            level=level,
            level_title=_level_title(level),
            current_level_points=current_threshold,
            next_level_points=next_threshold,
            level_progress_percentage=max(0, min(100, progress)),
            completed_sessions=completed_sessions,
            recent_events=recent_events,
        )


def _level_threshold(level: int) -> int:
    normalized = max(1, level)
    return _LEVEL_STEP_POINTS * (normalized - 1) * normalized // 2


def _level_for_points(points: int) -> int:
    normalized = max(0, points)
    scaled = normalized // _LEVEL_STEP_POINTS
    return max(1, (isqrt(1 + 8 * scaled) - 1) // 2 + 1)


def _level_title(level: int) -> str:
    return _LEVEL_TITLES[min(max(level, 1), len(_LEVEL_TITLES)) - 1]
