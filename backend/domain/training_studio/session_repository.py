"""Repository abstraction for Training Studio sessions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from domain.training_studio.session import TrainingSession


@dataclass(frozen=True)
class TrainingSessionAccessScope:
    """Repository-level visibility scope for Training Studio sessions."""

    user_id: str | None = None
    team_id: str | None = None
    include_team_scope: bool = False


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
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> list[TrainingSession]: ...

    @abstractmethod
    async def count(
        self,
        *,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
        access_scope: TrainingSessionAccessScope | None = None,
    ) -> int: ...
