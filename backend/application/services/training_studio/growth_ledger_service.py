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
class TrainingCareerPathStageDefinition:
    stage_id: str
    title: str
    focus_ids: tuple[str, ...]
    required_scenario_ids: tuple[str, ...]


_CAREER_PATH_STAGES = (
    TrainingCareerPathStageDefinition(
        stage_id="foundation",
        title="Workplace foundations",
        focus_ids=("attentiveness", "expression"),
        required_scenario_ids=(
            "new-customer-discount",
            "recruiter-sales-interview",
        ),
    ),
    TrainingCareerPathStageDefinition(
        stage_id="collaboration",
        title="Collaborative communication",
        focus_ids=("expression", "coordination"),
        required_scenario_ids=(
            "enterprise-demo-objection",
            "project-scope-creep-boundary",
        ),
    ),
    TrainingCareerPathStageDefinition(
        stage_id="upward-management",
        title="Upward management",
        focus_ids=("attentiveness", "expression", "coordination"),
        required_scenario_ids=(
            "daily-upward-results-report",
            "budget-freeze-expansion",
        ),
    ),
    TrainingCareerPathStageDefinition(
        stage_id="interest-communication",
        title="Interest communication",
        focus_ids=("coordination", "composure"),
        required_scenario_ids=(
            "refund-service-recovery",
            "renewal-price-negotiation",
            "cross-team-roadmap-tradeoff",
        ),
    ),
    TrainingCareerPathStageDefinition(
        stage_id="influence-mentor",
        title="Influence and coaching",
        focus_ids=(
            "attentiveness",
            "expression",
            "coordination",
            "composure",
        ),
        required_scenario_ids=(
            "angry-vip-priority",
            "ai-web3-agent-pm-comprehensive-interview",
        ),
    ),
)


@dataclass(frozen=True)
class TrainingCareerPathStage:
    stage_id: str
    stage_number: int
    title: str
    status: str
    required_scenario_ids: tuple[str, ...]
    completed_scenario_count: int
    required_scenario_count: int
    focus_ids: tuple[str, ...]
    recommended_scenario_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.stage_id,
            "stage_number": self.stage_number,
            "title": self.title,
            "status": self.status,
            "required_scenario_ids": list(self.required_scenario_ids),
            "completed_scenario_count": self.completed_scenario_count,
            "required_scenario_count": self.required_scenario_count,
            "focus_ids": list(self.focus_ids),
            "recommended_scenario_ids": list(self.recommended_scenario_ids),
        }


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
    career_path: tuple[TrainingCareerPathStage, ...]

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
            "career_path": [stage.to_dict() for stage in self.career_path],
        }


class TrainingGrowthLedgerService:
    """Derive an auditable, idempotent growth ledger from owned sessions."""

    async def sync_completed_sessions(self, uow, *, user_id: str) -> set[str]:
        repository = uow.training_point_event_repository
        completed_scenario_ids: set[str] = set()
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
                ):
                    continue
                if session.scenario_template_id:
                    completed_scenario_ids.add(session.scenario_template_id)
                if session.session_id in existing:
                    continue
                event = TrainingPointEvent(
                    user_id=user_id,
                    team_id=session.team_id,
                    source_type="training_session",
                    source_id=session.session_id,
                    event_type="session_completed",
                    points=TRAINING_COMPLETION_POINTS,
                    created_at=(session.completed_at or session.started_at or datetime.now(UTC)),
                )
                repository_added = await repository.add(event)
                if repository_added:
                    existing.add(session.session_id)
            if len(sessions) < page_size:
                break
            offset += page_size
        return completed_scenario_ids

    async def summary(self, uow, *, user_id: str) -> TrainingGrowthSummary:
        completed_scenario_ids = await self.sync_completed_sessions(uow, user_id=user_id)
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
            (total_points - current_threshold) * 100 / max(1, next_threshold - current_threshold)
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
            career_path=_career_path_for_completed_scenarios(completed_scenario_ids),
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


def _career_path_for_completed_scenarios(
    completed_scenario_ids: set[str] | frozenset[str] | tuple[str, ...],
) -> tuple[TrainingCareerPathStage, ...]:
    completed_ids = set(completed_scenario_ids)
    current_stage_index = next(
        (
            index
            for index, definition in enumerate(_CAREER_PATH_STAGES)
            if not set(definition.required_scenario_ids).issubset(completed_ids)
        ),
        len(_CAREER_PATH_STAGES),
    )
    stages: list[TrainingCareerPathStage] = []
    for index, definition in enumerate(_CAREER_PATH_STAGES):
        status = (
            "completed"
            if index < current_stage_index
            else "current" if index == current_stage_index else "locked"
        )
        completed_count = len(
            set(definition.required_scenario_ids).intersection(completed_ids)
        )
        stages.append(
            TrainingCareerPathStage(
                stage_id=definition.stage_id,
                stage_number=index + 1,
                title=definition.title,
                status=status,
                required_scenario_ids=definition.required_scenario_ids,
                completed_scenario_count=completed_count,
                required_scenario_count=len(definition.required_scenario_ids),
                focus_ids=definition.focus_ids,
                recommended_scenario_ids=tuple(
                    scenario_id
                    for scenario_id in definition.required_scenario_ids
                    if scenario_id not in completed_ids
                ),
            )
        )
    return tuple(stages)
