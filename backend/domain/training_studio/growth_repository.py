"""Persistence port for the Training Points ledger."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .growth import TrainingPointEvent


class TrainingPointEventRepository(ABC):
    @abstractmethod
    async def list_source_ids(
        self, *, user_id: str, source_type: str, event_type: str
    ) -> set[str]:
        ...

    @abstractmethod
    async def add(self, event: TrainingPointEvent) -> bool:
        """Insert an event, returning False when the idempotency key exists."""
        ...

    @abstractmethod
    async def sum_points(self, *, user_id: str) -> int:
        ...

    @abstractmethod
    async def recent(self, *, user_id: str, limit: int) -> list[TrainingPointEvent]:
        ...

    @abstractmethod
    async def count(self, *, user_id: str, event_type: str) -> int:
        ...
