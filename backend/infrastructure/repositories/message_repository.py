# input: SQLAlchemy AsyncSession, MessageModel ORM
# output: SQLAlchemyMessageRepository 仓储实现
# owner: unknown
# pos: 基础设施层 - 消息仓储 SQLAlchemy 实现；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""SQLAlchemy-backed repository for messages."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.conversation.entity import Message
from domain.conversation.exceptions import MessageNotFoundException
from domain.conversation.repository import MessageRepository
from infrastructure.models.conversation import MessageModel


class SQLAlchemyMessageRepository(MessageRepository):
    """Persist message entities using SQLAlchemy ORM."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, model: MessageModel) -> Message:
        return Message(
            id=model.id,
            conversation_id=model.conversation_id,
            role=model.role,
            content=model.content,
            public_id=model.public_id,
            parent_message_id=model.parent_message_id,
            branch_id=model.branch_id,
            status=model.status,
            finish_reason=model.finish_reason,
            provider=model.provider,
            model=model.model,
            content_parts=list(model.content_parts or []),
            run_id=model.run_id,
            token_count=model.token_count,
            metadata=dict(model.extra_metadata or {}),
            created_at=model.created_at,
        )

    async def create(self, message: Message) -> Message:
        model = MessageModel(
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            public_id=message.public_id,
            parent_message_id=message.parent_message_id,
            branch_id=message.branch_id,
            status=message.status,
            finish_reason=message.finish_reason,
            provider=message.provider,
            model=message.model,
            content_parts=message.content_parts or [],
            run_id=message.run_id,
            token_count=message.token_count,
            extra_metadata=message.metadata or {},
            created_at=message.created_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, message: Message) -> Message:
        result = await self.session.execute(
            select(MessageModel).where(MessageModel.id == message.id)
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise MessageNotFoundException(message.id)

        model.conversation_id = message.conversation_id
        model.role = message.role
        model.content = message.content
        model.public_id = message.public_id
        model.parent_message_id = message.parent_message_id
        model.branch_id = message.branch_id
        model.status = message.status
        model.finish_reason = message.finish_reason
        model.provider = message.provider
        model.model = message.model
        model.content_parts = message.content_parts or []
        model.run_id = message.run_id
        model.token_count = message.token_count
        model.extra_metadata = message.metadata or {}
        model.created_at = message.created_at

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, message_id: int) -> Optional[Message]:
        result = await self.session.execute(
            select(MessageModel).where(MessageModel.id == message_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_public_id(self, public_id: str) -> Optional[Message]:
        result = await self.session.execute(
            select(MessageModel).where(MessageModel.public_id == public_id)
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_latest_by_conversation(
        self,
        conversation_id: int,
        *,
        branch_id: Optional[str] = None,
    ) -> Optional[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(1)
        )
        if branch_id is not None:
            query = query.where(MessageModel.branch_id == branch_id)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        branch_id: Optional[str] = None,
    ) -> list[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
        )
        if branch_id is not None:
            query = query.where(MessageModel.branch_id == branch_id)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_children(self, parent_message_id: str) -> list[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.parent_message_id == parent_message_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
        )
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count_by_conversation(self, conversation_id: int) -> int:
        query = (
            select(func.count())
            .select_from(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
        )
        result = await self.session.execute(query)
        return int(result.scalar() or 0)
