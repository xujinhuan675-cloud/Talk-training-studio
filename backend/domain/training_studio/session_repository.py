"""Repository abstraction for Training Studio sessions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Optional

from domain.training_studio.session import TrainingSession


@dataclass(frozen=True)
class TrainingSessionAccessScope:
    """Repository-level visibility scope for Training Studio sessions."""

    user_id: str | None = None
    team_id: str | None = None
    include_team_scope: bool = False


@dataclass(frozen=True)
class TrainingSessionHistoryFilter:
    """Normalized, non-authorization filters for paginated session history."""

    query: str | None = None
    activity_from: datetime | None = None
    activity_to: datetime | None = None
    mode: str | None = None
    source: str | None = None


_VISIBLE_METADATA_TEXT_KEYS = frozenset({"description", "label", "name", "title"})
_VISIBLE_METADATA_CONTAINERS = (
    "scenario",
    "scenario_training",
    "scenarioTraining",
    "task",
    "training",
)
_SESSION_SOURCE_KEYS = ("source", "training_source", "trainingSource")


def training_session_activity_at(
    session: TrainingSession,
    *,
    created_at: datetime | None = None,
) -> datetime | None:
    """Return the latest lifecycle milestone used by history date filters."""

    value = session.completed_at or session.started_at or created_at
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def training_session_matches_history_filter(
    session: TrainingSession,
    history_filter: TrainingSessionHistoryFilter | None,
    *,
    created_at: datetime | None = None,
) -> bool:
    if history_filter is None:
        return True
    if history_filter.mode and session.mode.value != history_filter.mode:
        return False
    if history_filter.source and history_filter.source.casefold() not in {
        value.casefold() for value in _session_source_values(session.task_config.metadata)
    }:
        return False
    activity_at = training_session_activity_at(session, created_at=created_at)
    if history_filter.activity_from and (
        activity_at is None or activity_at < history_filter.activity_from
    ):
        return False
    if history_filter.activity_to and (
        activity_at is None or activity_at > history_filter.activity_to
    ):
        return False
    if history_filter.query:
        needle = history_filter.query.casefold()
        return any(
            needle in value.casefold() for value in training_session_visible_search_values(session)
        )
    return True


def training_session_visible_search_values(session: TrainingSession) -> tuple[str, ...]:
    """Expose only user-visible training fields to history full-text search."""

    config = session.task_config
    values = [
        session.session_id,
        session.scenario_template_id or "",
        config.role,
        config.category.value,
        *config.tech_stack,
    ]
    values.extend(_visible_metadata_values(config.metadata))
    return tuple(value for value in values if value)


def _session_source_values(metadata: Mapping[str, object] | None) -> tuple[str, ...]:
    values: list[str] = []
    source = dict(metadata or {})
    for key in _SESSION_SOURCE_KEYS:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return tuple(values)


def _visible_metadata_values(value: object) -> tuple[str, ...]:
    values: list[str] = []
    if not isinstance(value, Mapping):
        return ()
    for key in _VISIBLE_METADATA_TEXT_KEYS:
        child = value.get(key)
        if isinstance(child, str) and child.strip():
            values.append(child.strip())
    for container_key in _VISIBLE_METADATA_CONTAINERS:
        container = value.get(container_key)
        if not isinstance(container, Mapping):
            continue
        for key in _VISIBLE_METADATA_TEXT_KEYS:
            child = container.get(key)
            if isinstance(child, str) and child.strip():
                values.append(child.strip())
    return tuple(values)


def training_session_matches_access_scope(
    session: TrainingSession,
    access_scope: TrainingSessionAccessScope | None,
) -> bool:
    if access_scope is None:
        return True
    user_id = (access_scope.user_id or "").strip()
    team_id = (access_scope.team_id or "").strip()
    if user_id and session.user_id == user_id:
        return True
    if access_scope.include_team_scope and team_id and session.team_id == team_id:
        return True
    return False


class TrainingSessionRepository(ABC):
    """Contract for persisting and querying Training Studio sessions."""

    @abstractmethod
    async def save(self, session: TrainingSession) -> TrainingSession: ...

    @abstractmethod
    async def get(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> Optional[TrainingSession]: ...

    @abstractmethod
    async def delete(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> bool: ...

    @abstractmethod
    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        history_filter: TrainingSessionHistoryFilter | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> list[TrainingSession]: ...

    @abstractmethod
    async def count(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        history_filter: TrainingSessionHistoryFilter | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> int: ...
