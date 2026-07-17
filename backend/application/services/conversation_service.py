# input: AbstractUnitOfWork, Conversation/AgentConfig 领域实体
# output: ConversationApplicationService 对话 CRUD 编排
# owner: unknown
# pos: 应用层服务 - 对话与 Agent 配置 CRUD 用例编排；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Application service for conversation and agent config CRUD."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional, Sequence, Tuple

from application.dto import (
    AgentConfigDTO,
    ConversationDTO,
    CreateAgentConfigDTO,
    CreateConversationDTO,
    EditMessageDTO,
    MessageLocationDTO,
    MessageDTO_Agent,
    MessageSearchResultDTO,
    RetryMessageDTO,
    RunDTO,
    UpdateAgentConfigDTO,
    UpdateConversationDTO,
)
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.entity import AgentConfig, Conversation, Message
from domain.conversation.exceptions import (
    AgentConfigNameExistsException,
    AgentConfigNotFoundException,
    ConversationNotFoundException,
    MessageNotFoundException,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class ConversationApplicationService:
    """High-level conversation workflows bridging API and domain layers."""

    def __init__(self, uow_factory: Callable[..., AbstractUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    # ── Conversation CRUD ──────────────────────────────────────────

    async def create_conversation(self, dto: CreateConversationDTO) -> ConversationDTO:
        now = _utcnow()
        conv = Conversation(
            id=None,
            title=dto.title,
            system_prompt=dto.system_prompt,
            model=dto.model,
            metadata=dto.metadata or {},
            created_at=now,
            updated_at=now,
        )
        async with self._uow_factory() as uow:
            created = await uow.conversation_repository.create(conv)
            return ConversationDTO.model_validate(created)

    async def get_conversation(self, conversation_id: int) -> ConversationDTO:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            return ConversationDTO.model_validate(conv)

    async def list_conversations(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[ConversationDTO], int]:
        async with self._uow_factory(readonly=True) as uow:
            items = await uow.conversation_repository.list(status=status, skip=skip, limit=limit)
            total = await uow.conversation_repository.count(status=status)
            return [ConversationDTO.model_validate(c) for c in items], total

    async def update_conversation(
        self, conversation_id: int, dto: UpdateConversationDTO
    ) -> ConversationDTO:
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            changed = False
            if dto.title is not None:
                conv.update_title(dto.title)
                changed = True
            if dto.system_prompt is not None:
                conv.system_prompt = dto.system_prompt
                changed = True
            if dto.model is not None:
                conv.model = dto.model
                changed = True
            if changed:
                conv._touch()
            updated = await uow.conversation_repository.update(conv)
            return ConversationDTO.model_validate(updated)

    async def delete_conversation(self, conversation_id: int) -> ConversationDTO:
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            conv.soft_delete()
            updated = await uow.conversation_repository.update(conv)
            return ConversationDTO.model_validate(updated)

    # ── Messages ───────────────────────────────────────────────────

    async def list_messages(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[list[MessageDTO_Agent], int]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            items = await uow.message_repository.list_by_conversation(
                conversation_id, skip=skip, limit=limit
            )
            total = await uow.message_repository.count_by_conversation(conversation_id)
            return [MessageDTO_Agent.model_validate(m) for m in items], total

    async def get_message_path(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        limit: int = 200,
    ) -> list[MessageDTO_Agent]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            messages = await uow.message_repository.list_path_to_message(
                conversation_id,
                message_public_id,
                limit=limit,
            )
            if not messages or messages[-1].public_id != message_public_id:
                raise MessageNotFoundException()
            return [MessageDTO_Agent.model_validate(message) for message in messages]

    async def list_message_children(
        self,
        conversation_id: int,
        message_public_id: str,
    ) -> list[MessageDTO_Agent]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            parent = await uow.message_repository.get_by_public_id(message_public_id)
            if parent is None or parent.conversation_id != conversation_id:
                raise MessageNotFoundException()
            children = await uow.message_repository.list_children(message_public_id)
            children = [
                child
                for child in children
                if child.conversation_id == conversation_id and child.status != "deleted"
            ]
            return [MessageDTO_Agent.model_validate(child) for child in children]

    async def edit_message(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: EditMessageDTO,
    ) -> MessageDTO_Agent:
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            source = await uow.message_repository.get_by_public_id(message_public_id)
            if source is None or source.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if source.status == "deleted":
                raise MessageNotFoundException()

            edited = source.create_edit(content=dto.content, metadata=dto.metadata)
            source.mark_superseded()
            await uow.message_repository.update(source)
            created = await uow.message_repository.create(edited)
            return MessageDTO_Agent.model_validate(created)

    async def retry_message(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: RetryMessageDTO,
    ) -> MessageDTO_Agent:
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            source = await uow.message_repository.get_by_public_id(message_public_id)
            if source is None or source.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if source.status == "deleted":
                raise MessageNotFoundException()

            retry = source.create_retry(content=dto.content, metadata=dto.metadata)
            source.mark_superseded()
            await uow.message_repository.update(source)
            created = await uow.message_repository.create(retry)
            return MessageDTO_Agent.model_validate(created)

    async def locate_message(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        before: int = 2,
        after: int = 2,
    ) -> MessageLocationDTO:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            path = await uow.message_repository.list_path_to_message(
                conversation_id,
                message_public_id,
            )
            if not path or path[-1].public_id != message_public_id:
                raise MessageNotFoundException()

            context = await uow.message_repository.list_context_window(
                conversation_id,
                message_public_id,
                before=max(0, before),
                after=max(0, after),
            )
            if not context:
                raise MessageNotFoundException()

            target = path[-1]
            return MessageLocationDTO(
                message=MessageDTO_Agent.model_validate(target),
                path=[MessageDTO_Agent.model_validate(message) for message in path],
                context=[MessageDTO_Agent.model_validate(message) for message in context],
            )

    async def search_messages(
        self,
        conversation_id: int,
        query: str,
        *,
        skip: int = 0,
        limit: int = 20,
        branch_id: str | None = None,
        roles: Sequence[str] | None = None,
        include_path: bool = True,
        context_before: int = 1,
        context_after: int = 1,
    ) -> list[MessageSearchResultDTO]:
        normalized_query = _clean_optional_text(query)
        if normalized_query is None:
            return []

        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            matches = await uow.message_repository.search_by_content(
                conversation_id,
                normalized_query,
                skip=max(0, skip),
                limit=max(1, limit),
                branch_id=_clean_optional_text(branch_id),
                roles=roles,
            )

            results: list[MessageSearchResultDTO] = []
            for match in matches:
                path: list[Message] = []
                if include_path:
                    path = await uow.message_repository.list_path_to_message(
                        conversation_id,
                        match.public_id,
                    )
                context = await uow.message_repository.list_context_window(
                    conversation_id,
                    match.public_id,
                    before=max(0, context_before),
                    after=max(0, context_after),
                )
                results.append(
                    MessageSearchResultDTO(
                        message=MessageDTO_Agent.model_validate(match),
                        path=[MessageDTO_Agent.model_validate(message) for message in path],
                        context=[MessageDTO_Agent.model_validate(message) for message in context],
                    )
                )
            return results

    # ── Runs ───────────────────────────────────────────────────────

    async def list_runs(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[RunDTO]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            items = await uow.run_repository.list_by_conversation(
                conversation_id, skip=skip, limit=limit
            )
            return [RunDTO.model_validate(r) for r in items]

    # ── Agent Config CRUD ──────────────────────────────────────────

    async def create_agent_config(self, dto: CreateAgentConfigDTO) -> AgentConfigDTO:
        now = _utcnow()
        async with self._uow_factory() as uow:
            existing = await uow.agent_config_repository.get_by_name(dto.name)
            if existing is not None:
                raise AgentConfigNameExistsException(dto.name)
            config = AgentConfig(
                id=None,
                name=dto.name,
                system_prompt=dto.system_prompt,
                model=dto.model,
                temperature=dto.temperature,
                max_tokens=dto.max_tokens,
                metadata=dto.metadata or {},
                created_at=now,
                updated_at=now,
            )
            created = await uow.agent_config_repository.create(config)
            return AgentConfigDTO.model_validate(created)

    async def get_agent_config(self, config_id: int) -> AgentConfigDTO:
        async with self._uow_factory(readonly=True) as uow:
            config = await uow.agent_config_repository.get_by_id(config_id)
            if config is None:
                raise AgentConfigNotFoundException(config_id)
            return AgentConfigDTO.model_validate(config)

    async def list_agent_configs(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[list[AgentConfigDTO], int]:
        async with self._uow_factory(readonly=True) as uow:
            items = await uow.agent_config_repository.list(skip=skip, limit=limit)
            total = await uow.agent_config_repository.count()
            return [AgentConfigDTO.model_validate(c) for c in items], total

    async def update_agent_config(
        self, config_id: int, dto: UpdateAgentConfigDTO
    ) -> AgentConfigDTO:
        async with self._uow_factory() as uow:
            config = await uow.agent_config_repository.get_by_id(config_id)
            if config is None:
                raise AgentConfigNotFoundException(config_id)
            if dto.name is not None:
                # Check uniqueness
                existing = await uow.agent_config_repository.get_by_name(dto.name)
                if existing is not None and existing.id != config_id:
                    raise AgentConfigNameExistsException(dto.name)
                config.name = dto.name
            if dto.system_prompt is not None:
                config.system_prompt = dto.system_prompt
            if dto.model is not None:
                config.model = dto.model
            if dto.temperature is not None:
                config.temperature = dto.temperature
            if dto.max_tokens is not None:
                config.max_tokens = dto.max_tokens
            if dto.metadata is not None:
                config.metadata = dto.metadata
            config._touch()
            updated = await uow.agent_config_repository.update(config)
            return AgentConfigDTO.model_validate(updated)

    async def delete_agent_config(self, config_id: int) -> None:
        async with self._uow_factory() as uow:
            config = await uow.agent_config_repository.get_by_id(config_id)
            if config is None:
                raise AgentConfigNotFoundException(config_id)
            await uow.agent_config_repository.delete(config_id)
