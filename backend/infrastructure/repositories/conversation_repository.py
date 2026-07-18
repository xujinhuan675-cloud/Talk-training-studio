# input: SQLAlchemy AsyncSession, ConversationModel ORM
# output: SQLAlchemyConversationRepository 仓储实现
# owner: unknown
# pos: 基础设施层 - 对话仓储 SQLAlchemy 实现；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""SQLAlchemy-backed repository for conversations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.conversation.entity import Conversation
from domain.conversation.exceptions import ConversationNotFoundException
from domain.conversation.repository import ConversationRepository, OwnedMetadataScope
from infrastructure.models.conversation import ConversationModel
from infrastructure.repositories.metadata_scope import apply_owned_metadata_scope


class SQLAlchemyConversationRepository(ConversationRepository):
    """Persist conversation aggregates using SQLAlchemy ORM."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, model: ConversationModel) -> Conversation:
        return Conversation(
            id=model.id,
            title=model.title,
            system_prompt=model.system_prompt,
            model=model.model,
            status=model.status,
            metadata=dict(model.extra_metadata or {}),
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    def _apply_filters(
        self,
        query,
        *,
        status: Optional[str],
        metadata_scope: OwnedMetadataScope | None = None,
    ):
        # Exclude soft-deleted by default
        query = query.where(ConversationModel.deleted_at.is_(None))
        if status:
            query = query.where(ConversationModel.status == status)
        query = apply_owned_metadata_scope(query, ConversationModel.extra_metadata, metadata_scope)
        return query

    async def create(self, conversation: Conversation) -> Conversation:
        model = ConversationModel(
            title=conversation.title,
            system_prompt=conversation.system_prompt,
            model=conversation.model,
            status=conversation.status,
            extra_metadata=conversation.metadata or {},
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            deleted_at=conversation.deleted_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(
        self,
        conversation: Conversation,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> Conversation:
        query = select(ConversationModel).where(ConversationModel.id == conversation.id)
        query = apply_owned_metadata_scope(
            query,
            ConversationModel.extra_metadata,
            metadata_scope,
        )
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        if model is None:
            raise ConversationNotFoundException(conversation.id)

        model.title = conversation.title
        model.system_prompt = conversation.system_prompt
        model.model = conversation.model
        model.status = conversation.status
        model.extra_metadata = conversation.metadata or {}
        model.updated_at = conversation.updated_at
        model.deleted_at = conversation.deleted_at

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(
        self,
        conversation_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> Optional[Conversation]:
        query = select(ConversationModel).where(ConversationModel.id == conversation_id)
        query = apply_owned_metadata_scope(
            query,
            ConversationModel.extra_metadata,
            metadata_scope,
        )
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def list(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> list[Conversation]:
        query = select(ConversationModel)
        query = self._apply_filters(query, status=status, metadata_scope=metadata_scope)
        query = query.order_by(
            ConversationModel.updated_at.desc(),
            ConversationModel.id.desc(),
        )
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def count(
        self,
        *,
        status: Optional[str] = None,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> int:
        query = select(func.count()).select_from(ConversationModel)
        query = self._apply_filters(query, status=status, metadata_scope=metadata_scope)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)
