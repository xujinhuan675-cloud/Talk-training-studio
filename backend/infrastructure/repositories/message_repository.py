# input: SQLAlchemy AsyncSession, MessageModel ORM
# output: SQLAlchemyMessageRepository 仓储实现
# owner: unknown
# pos: 基础设施层 - 消息仓储 SQLAlchemy 实现；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""SQLAlchemy-backed repository for messages."""

from __future__ import annotations

from typing import Optional, Sequence

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
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> Optional[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .limit(1)
        )
        if branch_id is not None:
            query = query.where(MessageModel.branch_id == branch_id)
        query = _apply_status_filter(query, statuses=statuses, include_deleted=include_deleted)
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
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> list[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
        )
        if branch_id is not None:
            query = query.where(MessageModel.branch_id == branch_id)
        query = _apply_status_filter(query, statuses=statuses, include_deleted=include_deleted)
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_children(
        self,
        parent_message_id: str,
        *,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> list[Message]:
        query = (
            select(MessageModel)
            .where(MessageModel.parent_message_id == parent_message_id)
            .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
        )
        query = _apply_status_filter(query, statuses=statuses, include_deleted=include_deleted)
        result = await self.session.execute(query)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_path_to_message(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        limit: int = 200,
        include_deleted: bool = False,
        statuses: Optional[Sequence[str]] = None,
    ) -> list[Message]:
        messages: list[Message] = []
        seen: set[str] = set()
        allowed_statuses = set(statuses or [])
        current_id: str | None = message_public_id
        while current_id and len(messages) < limit:
            if current_id in seen:
                raise ValueError("Message tree contains a cycle")
            seen.add(current_id)

            message = await self.get_by_public_id(current_id)
            if message is None or message.conversation_id != conversation_id:
                return []
            status_allowed = (
                message.status in allowed_statuses
                if allowed_statuses
                else include_deleted or message.status != "deleted"
            )
            if not status_allowed:
                return []
            messages.append(message)
            current_id = message.parent_message_id

        if current_id:
            return []

        messages.reverse()
        return messages

    async def search_by_content(
        self,
        conversation_id: int,
        query: str,
        *,
        skip: int = 0,
        limit: int = 20,
        branch_id: Optional[str] = None,
        roles: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> list[Message]:
        normalized = query.strip().lower()
        if not normalized:
            return []

        like_pattern = f"%{_escape_like(normalized)}%"
        sql = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .where(func.lower(MessageModel.content).like(like_pattern, escape="\\"))
        )
        if branch_id is not None:
            sql = sql.where(MessageModel.branch_id == branch_id)
        if roles:
            sql = sql.where(MessageModel.role.in_(list(roles)))
        if statuses:
            sql = sql.where(MessageModel.status.in_(list(statuses)))
        else:
            sql = sql.where(MessageModel.status != "deleted")
        if provider is not None:
            sql = sql.where(MessageModel.provider == provider)
        if model is not None:
            sql = sql.where(MessageModel.model == model)

        sql = (
            sql.order_by(MessageModel.created_at.desc(), MessageModel.id.desc())
            .offset(skip)
            .limit(limit)
        )

        result = await self.session.execute(sql)
        return [self._to_entity(m) for m in result.scalars().all()]

    async def list_context_window(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        before: int = 2,
        after: int = 2,
        branch_id: Optional[str] = None,
        include_deleted: bool = False,
    ) -> list[Message]:
        target = await self.get_by_public_id(message_public_id)
        if target is None or target.conversation_id != conversation_id or target.id is None:
            return []
        if target.status == "deleted" and not include_deleted:
            return []
        if branch_id is not None and target.branch_id != branch_id:
            return []

        effective_branch_id = branch_id if branch_id is not None else target.branch_id

        path = await self.list_path_to_message(
            conversation_id,
            message_public_id,
            include_deleted=include_deleted,
        )
        if not path or path[-1].public_id != message_public_id:
            return []

        previous = path[max(0, len(path) - before - 1) : -1] if before > 0 else []
        next_messages = await self._list_branch_continuation(
            conversation_id,
            target,
            branch_id=effective_branch_id,
            limit=max(0, after),
            include_deleted=include_deleted,
        )

        return previous + [target] + next_messages

    async def _list_branch_continuation(
        self,
        conversation_id: int,
        target: Message,
        *,
        branch_id: Optional[str],
        limit: int,
        include_deleted: bool,
    ) -> list[Message]:
        messages: list[Message] = []
        current = target
        seen = {target.public_id}

        while len(messages) < limit:
            query = (
                select(MessageModel)
                .where(MessageModel.conversation_id == conversation_id)
                .where(MessageModel.parent_message_id == current.public_id)
                .order_by(MessageModel.created_at.asc(), MessageModel.id.asc())
            )
            if branch_id is not None:
                query = query.where(MessageModel.branch_id == branch_id)
            if not include_deleted:
                query = query.where(MessageModel.status != "deleted")

            result = await self.session.execute(query)
            children = [self._to_entity(m) for m in result.scalars().all()]
            if not children:
                break

            next_message = children[-1]
            if next_message.public_id in seen:
                raise ValueError("Message tree contains a cycle")
            seen.add(next_message.public_id)
            messages.append(next_message)
            current = next_message

        return messages

    async def count_by_conversation(
        self,
        conversation_id: int,
        *,
        branch_id: Optional[str] = None,
        statuses: Optional[Sequence[str]] = None,
        include_deleted: bool = False,
    ) -> int:
        query = (
            select(func.count())
            .select_from(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
        )
        if branch_id is not None:
            query = query.where(MessageModel.branch_id == branch_id)
        query = _apply_status_filter(query, statuses=statuses, include_deleted=include_deleted)
        result = await self.session.execute(query)
        return int(result.scalar() or 0)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _apply_status_filter(sql, *, statuses: Optional[Sequence[str]], include_deleted: bool):
    if statuses:
        return sql.where(MessageModel.status.in_(list(statuses)))
    if include_deleted:
        return sql
    return sql.where(MessageModel.status != "deleted")
