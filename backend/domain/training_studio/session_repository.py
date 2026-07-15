"""Repository abstraction for Training Studio sessions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.training_studio.session import TrainingSession


class TrainingSessionRepository(ABC):
    """Contract for persisting and querying Training Studio sessions."""

    @abstractmethod
    async def save(self, session: TrainingSession) -> TrainingSession: ...

    @abstractmethod
    async def get(self, session_id: str) -> Optional[TrainingSession]: ...

    @abstractmethod
    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        user_id: str | None = None,
        team_id: str | None = None,
        scenario_template_id: str | None = None,
    ) -> list[TrainingSession]: ...
