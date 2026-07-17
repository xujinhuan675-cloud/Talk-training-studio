# input: SQLAlchemy AsyncSession, RunModel ORM
# output: SQLAlchemyRunRepository 仓储实现
# owner: unknown
# pos: 基础设施层 - Run 仓储 SQLAlchemy 实现；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""SQLAlchemy-backed repository for runs."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.conversation.entity import Run
from domain.conversation.exceptions import RunNotFoundException
from domain.conversation.repository import RunRepository
from infrastructure.models.conversation import RunModel


class SQLAlchemyRunRepository(RunRepository):
    """Persist run entities using SQLAlchemy ORM."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, model: RunModel) -> Run:
        return Run(
            id=model.id,
            conversation_id=model.conversation_id,
            public_id=model.public_id,
            status=model.status,
            provider=model.provider,
            model=model.model,
            finish_reason=model.finish_reason,
            prompt_tokens=model.prompt_tokens,
            completion_tokens=model.completion_tokens,
            total_tokens=model.total_tokens,
            error_message=model.error_message,
            metadata=dict(model.extra_metadata or {}),
            started_at=model.started_at,
            completed_at=model.completed_at,
            created_at=model.created_at,
        )

    async def create(self, run: Run) -> Run:
        model = RunModel(
            public_id=run.public_id,
            conversation_id=run.conversation_id,
            status=run.status,
            provider=run.provider,
            model=run.model,
            finish_reason=run.finish_reason,
            prompt_tokens=run.prompt_tokens,
            completion_tokens=run.completion_tokens,
            total_tokens=run.total_tokens,
            error_message=run.error_message,
            extra_metadata=run.metadata or {},
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, run: Run) -> Run:
        result = await self.session.execute(select(RunModel).where(RunModel.id == run.id))
        model = result.scalar_one_or_none()
        if model is None:
            raise RunNotFoundException(run.id)

        model.public_id = run.public_id
        model.status = run.status
        model.provider = run.provider
        model.model = run.model
        model.finish_reason = run.finish_reason
        model.prompt_tokens = run.prompt_tokens
        model.completion_tokens = run.completion_tokens
        model.total_tokens = run.total_tokens
        model.error_message = run.error_message
        model.extra_metadata = run.metadata or {}
        model.started_at = run.started_at
        model.completed_at = run.completed_at

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, run_id: int) -> Optional[Run]:
        result = await self.session.execute(select(RunModel).where(RunModel.id == run_id))
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        trigger_message_id: Optional[str] = None,
    ) -> list[Run]:
        query = select(RunModel).where(RunModel.conversation_id == conversation_id)
        if provider is not None:
            query = query.where(RunModel.provider == provider)
        if status is not None:
            query = query.where(RunModel.status == status)
        if trigger_message_id is not None:
            trigger_expr = RunModel.extra_metadata["trigger_message_id"].as_string()
            query = query.where(trigger_expr == trigger_message_id)
        query = (
            query.order_by(RunModel.created_at.desc(), RunModel.id.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]
