"""SQLAlchemy persistence adapter for Training Points."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.training_studio.growth import TrainingPointEvent
from domain.training_studio.growth_repository import TrainingPointEventRepository
from infrastructure.models.training_growth import TrainingPointEventModel


class SQLAlchemyTrainingPointEventRepository(TrainingPointEventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_source_ids(
        self, *, user_id: str, source_type: str, event_type: str
    ) -> set[str]:
        result = await self.session.execute(
            select(TrainingPointEventModel.source_id).where(
                TrainingPointEventModel.user_id == user_id,
                TrainingPointEventModel.source_type == source_type,
                TrainingPointEventModel.event_type == event_type,
            )
        )
        return set(result.scalars())

    async def add(self, event: TrainingPointEvent) -> bool:
        model = TrainingPointEventModel(
            user_id=event.user_id,
            team_id=event.team_id,
            source_type=event.source_type,
            source_id=event.source_id,
            event_type=event.event_type,
            points=event.points,
            created_at=event.created_at,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(model)
                await self.session.flush()
        except IntegrityError:
            return False
        return True

    async def sum_points(self, *, user_id: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(TrainingPointEventModel.points), 0)).where(
                TrainingPointEventModel.user_id == user_id
            )
        )
        return int(result.scalar_one())

    async def recent(self, *, user_id: str, limit: int) -> list[TrainingPointEvent]:
        result = await self.session.execute(
            select(TrainingPointEventModel)
            .where(TrainingPointEventModel.user_id == user_id)
            .order_by(
                TrainingPointEventModel.created_at.desc(),
                TrainingPointEventModel.id.desc(),
            )
            .limit(limit)
        )
        return [self._to_event(row) for row in result.scalars()]

    async def count(self, *, user_id: str, event_type: str) -> int:
        result = await self.session.execute(
            select(func.count(TrainingPointEventModel.id)).where(
                TrainingPointEventModel.user_id == user_id,
                TrainingPointEventModel.event_type == event_type,
            )
        )
        return int(result.scalar_one())

    @staticmethod
    def _to_event(row: TrainingPointEventModel) -> TrainingPointEvent:
        return TrainingPointEvent(
            id=row.id,
            user_id=row.user_id,
            team_id=row.team_id,
            source_type=row.source_type,
            source_id=row.source_id,
            event_type=row.event_type,
            points=row.points,
            created_at=row.created_at,
        )
