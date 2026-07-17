# input: AbstractUnitOfWork, Conversation/Message/Run/AgentConfig domain entities
# output: ConversationApplicationService conversation, message, search, run, and agent config orchestration
# owner: unknown
# pos: application service - conversation CRUD plus text-history navigation and run queries; update this header and folder docs when changed
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
    ForkConversationDTO,
    ForkConversationResultDTO,
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


def _clean_statuses(values: Sequence[str] | None) -> list[str] | None:
    if not values:
        return None
    statuses = [_clean_optional_text(value) for value in values]
    cleaned = [status for status in statuses if status]
    return cleaned or None


def _select_messages_for_fork(
    messages: Sequence[Message],
    target_public_id: str,
    option: str,
) -> list[Message]:
    by_id = {message.public_id: message for message in messages if message.public_id}
    target = by_id.get(target_public_id)
    if target is None:
        return []

    if option == "directPath":
        return _direct_path(messages, target_public_id)
    if option == "includeBranches":
        return _path_with_branch_siblings(messages, target_public_id)
    return _messages_up_to_target_level(messages, target_public_id)


def _direct_path(messages: Sequence[Message], target_public_id: str) -> list[Message]:
    by_id = {message.public_id: message for message in messages if message.public_id}
    path: list[Message] = []
    seen: set[str] = set()
    current_id: str | None = target_public_id
    while current_id:
        if current_id in seen:
            raise ValueError("Message tree contains a cycle")
        seen.add(current_id)
        current = by_id.get(current_id)
        if current is None:
            break
        path.append(current)
        current_id = current.parent_message_id
    path.reverse()
    return path


def _path_with_branch_siblings(messages: Sequence[Message], target_public_id: str) -> list[Message]:
    path = _direct_path(messages, target_public_id)
    path_ids = {message.public_id for message in path if message.public_id}
    selected: list[Message] = []
    for message in messages:
        if message.public_id == target_public_id:
            selected.append(message)
            continue
        if message.public_id in path_ids and message.public_id != target_public_id:
            selected.append(message)
            continue
        if message.parent_message_id in path_ids and message.parent_message_id != target_public_id:
            selected.append(message)
    return _dedupe_messages(selected)


def _messages_up_to_target_level(messages: Sequence[Message], target_public_id: str) -> list[Message]:
    by_id = {message.public_id: message for message in messages if message.public_id}
    if target_public_id not in by_id:
        return []

    all_ids = set(by_id)
    children_by_parent: dict[str | None, list[Message]] = {}
    for message in messages:
        parent_key = message.parent_message_id if message.parent_message_id in all_ids else None
        children_by_parent.setdefault(parent_key, []).append(message)

    current_level = list(children_by_parent.get(None, [])) or [by_id[target_public_id]]
    selected: list[Message] = list(current_level)
    visited: set[str] = set()

    if any(message.public_id == target_public_id for message in current_level):
        return _dedupe_messages(selected)

    while current_level:
        next_level: list[Message] = []
        for message in current_level:
            if message.public_id in visited:
                raise ValueError("Message tree contains a cycle")
            visited.add(message.public_id)
            next_level.extend(children_by_parent.get(message.public_id, []))

        if not next_level:
            break
        selected.extend(next_level)
        if any(message.public_id == target_public_id for message in next_level):
            break
        current_level = next_level

    return _dedupe_messages(selected)


def _parent_first(messages: Sequence[Message]) -> list[Message]:
    pending = list(_dedupe_messages(messages))
    pending_ids = {message.public_id for message in pending if message.public_id}
    ordered: list[Message] = []
    emitted: set[str] = set()

    while pending:
        progressed = False
        remaining: list[Message] = []
        for message in pending:
            parent_id = message.parent_message_id
            if parent_id not in pending_ids or parent_id in emitted:
                ordered.append(message)
                emitted.add(message.public_id)
                progressed = True
            else:
                remaining.append(message)
        if not progressed:
            raise ValueError("Message tree contains a cycle")
        pending = remaining

    return ordered


def _dedupe_messages(messages: Sequence[Message]) -> list[Message]:
    seen: set[str] = set()
    deduped: list[Message] = []
    for message in messages:
        if message.public_id in seen:
            continue
        seen.add(message.public_id)
        deduped.append(message)
    return deduped


class ConversationApplicationService:
    """High-level conversation workflows bridging API and domain layers."""

    def __init__(self, uow_factory: Callable[..., AbstractUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    # Conversation CRUD

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

    # Messages

    async def list_messages(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        branch_id: str | None = None,
        statuses: Sequence[str] | None = None,
        include_deleted: bool = False,
    ) -> Tuple[list[MessageDTO_Agent], int]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            items = await uow.message_repository.list_by_conversation(
                conversation_id,
                skip=skip,
                limit=limit,
                branch_id=_clean_optional_text(branch_id),
                statuses=_clean_statuses(statuses),
                include_deleted=include_deleted,
            )
            total = await uow.message_repository.count_by_conversation(
                conversation_id,
                branch_id=_clean_optional_text(branch_id),
                statuses=_clean_statuses(statuses),
                include_deleted=include_deleted,
            )
            return [MessageDTO_Agent.model_validate(m) for m in items], total

    async def get_message_path(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        limit: int = 200,
        include_deleted: bool = False,
        statuses: Sequence[str] | None = None,
    ) -> list[MessageDTO_Agent]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            messages = await uow.message_repository.list_path_to_message(
                conversation_id,
                message_public_id,
                limit=limit,
                include_deleted=include_deleted,
                statuses=_clean_statuses(statuses),
            )
            if not messages or messages[-1].public_id != message_public_id:
                raise MessageNotFoundException()
            return [MessageDTO_Agent.model_validate(message) for message in messages]

    async def list_message_children(
        self,
        conversation_id: int,
        message_public_id: str,
        *,
        statuses: Sequence[str] | None = None,
        include_deleted: bool = False,
    ) -> list[MessageDTO_Agent]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            parent = await uow.message_repository.get_by_public_id(message_public_id)
            if parent is None or parent.conversation_id != conversation_id:
                raise MessageNotFoundException()
            children = await uow.message_repository.list_children(
                message_public_id,
                statuses=_clean_statuses(statuses),
                include_deleted=include_deleted,
            )
            children = [
                child
                for child in children
                if child.conversation_id == conversation_id
            ]
            return [MessageDTO_Agent.model_validate(child) for child in children]

    async def fork_conversation(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: ForkConversationDTO,
    ) -> ForkConversationResultDTO:
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            statuses = _clean_statuses(dto.statuses)
            source_messages = await uow.message_repository.list_by_conversation(
                conversation_id,
                limit=10000,
                statuses=statuses,
                include_deleted=dto.include_deleted,
            )
            target = next(
                (message for message in source_messages if message.public_id == message_public_id),
                None,
            )
            if target is None:
                raise MessageNotFoundException()

            selected = _select_messages_for_fork(source_messages, message_public_id, dto.option)
            if not selected:
                raise MessageNotFoundException()

            now = _utcnow()
            metadata = {
                **(conv.metadata or {}),
                **(dto.metadata or {}),
                "forked_from_conversation_id": conversation_id,
                "forked_from_message_id": message_public_id,
                "fork_option": dto.option,
            }
            forked_conversation = await uow.conversation_repository.create(
                Conversation(
                    id=None,
                    title=_clean_optional_text(dto.title) or conv.title,
                    system_prompt=conv.system_prompt,
                    model=conv.model,
                    status="active",
                    metadata=metadata,
                    created_at=now,
                    updated_at=now,
                )
            )

            id_map: dict[str, str] = {}
            created_messages: list[Message] = []
            selected_ids = {message.public_id for message in selected if message.public_id}
            for source in _parent_first(selected):
                parent_id = (
                    id_map.get(source.parent_message_id)
                    if source.parent_message_id in selected_ids
                    else None
                )
                forked = Message(
                    id=None,
                    conversation_id=forked_conversation.id,
                    role=source.role,
                    content=source.content,
                    public_id=None,
                    parent_message_id=parent_id,
                    branch_id=source.branch_id,
                    status=source.status,
                    finish_reason=source.finish_reason,
                    provider=source.provider,
                    model=source.model,
                    content_parts=list(source.content_parts or []),
                    run_id=None,
                    token_count=source.token_count,
                    metadata={
                        **(source.metadata or {}),
                        "forked_from_message_id": source.public_id,
                    },
                    created_at=source.created_at,
                )
                created = await uow.message_repository.create(forked)
                id_map[source.public_id] = created.public_id
                created_messages.append(created)

            return ForkConversationResultDTO(
                conversation=ConversationDTO.model_validate(forked_conversation),
                messages=[MessageDTO_Agent.model_validate(message) for message in created_messages],
                source_to_forked_id=id_map,
            )

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
        statuses: Sequence[str] | None = None,
        provider: str | None = None,
        model: str | None = None,
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
                statuses=_clean_statuses(statuses),
                provider=_clean_optional_text(provider),
                model=_clean_optional_text(model),
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

    # Runs

    async def list_runs(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        provider: str | None = None,
        status: str | None = None,
        trigger_message_id: str | None = None,
    ) -> list[RunDTO]:
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(conversation_id)
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            fetch_limit = max(skip + limit, 500)
            items = await uow.run_repository.list_by_conversation(
                conversation_id, skip=0, limit=fetch_limit
            )
            provider_filter = _clean_optional_text(provider)
            status_filter = _clean_optional_text(status)
            trigger_filter = _clean_optional_text(trigger_message_id)
            if provider_filter is not None:
                items = [run for run in items if run.provider == provider_filter]
            if status_filter is not None:
                items = [run for run in items if run.status == status_filter]
            if trigger_filter is not None:
                items = [
                    run
                    for run in items
                    if (run.metadata or {}).get("trigger_message_id") == trigger_filter
                ]
            items = items[skip : skip + limit]
            return [RunDTO.model_validate(r) for r in items]

    # Agent Config CRUD

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
