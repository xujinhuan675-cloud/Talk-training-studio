# input: AbstractUnitOfWork, Conversation/Message/Run/AgentConfig domain entities
# output: ConversationApplicationService conversation, message, search, run, and agent config orchestration
# owner: unknown
# pos: application service - conversation CRUD plus text-history navigation and run queries; update this header and folder docs when changed
"""Application service for conversation and agent config CRUD."""

from __future__ import annotations

from collections.abc import Mapping, Sequence as SequenceABC
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal, Optional, Sequence, Tuple

from application.dto import (
    AgentConfigDTO,
    ConversationDTO,
    CreateAgentConfigDTO,
    CreateConversationDTO,
    EditMessageDTO,
    ForkConversationDTO,
    ForkConversationResultDTO,
    MessageActionDTO,
    MessageActionResultDTO,
    MessageLocationDTO,
    MessageDTO_Agent,
    MessageSearchResultDTO,
    RetryMessageDTO,
    RunDTO,
    UpdateAgentConfigDTO,
    UpdateConversationDTO,
)
from domain.common.exceptions import DomainValidationException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.entity import (
    AgentConfig,
    Conversation,
    Message,
    normalize_agent_resource_ids,
)
from domain.conversation.exceptions import (
    AgentConfigNameExistsException,
    AgentConfigNotFoundException,
    ConversationNotFoundException,
    MessageNotFoundException,
)
from domain.conversation.repository import OwnedMetadataScope


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


def _require_metadata_scope(
    scope: OwnedMetadataScope | None,
    *,
    operation: str,
) -> OwnedMetadataScope:
    if scope is None:
        raise DomainValidationException(
            "metadata_scope is required for conversation access",
            field="metadata_scope",
            details={"operation": operation},
            message_key="conversation.scope.required",
        )
    return scope


def _require_mutation_metadata_scope(
    scope: OwnedMetadataScope | None,
    *,
    operation: str,
) -> OwnedMetadataScope:
    scope = _require_metadata_scope(scope, operation=operation)
    if scope.allow_unscoped:
        raise DomainValidationException(
            "metadata_scope.allow_unscoped is not allowed for conversation mutations",
            field="metadata_scope.allow_unscoped",
            details={"operation": operation},
            message_key="conversation.scope.allow_unscoped_forbidden",
        )
    return scope


_ACL_METADATA_KEYS = {
    "authScope",
    "ownerUserId",
    "owner_user_id",
    "createdByUserId",
    "created_by_user_id",
    "teamId",
    "team_id",
    "ownerTeamId",
    "owner_team_id",
}
_OWNER_USER_KEYS = ("ownerUserId", "owner_user_id", "createdByUserId", "created_by_user_id")
_OWNER_TEAM_KEYS = ("teamId", "team_id", "ownerTeamId", "owner_team_id")


def _metadata_mapping(value: object | None) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _metadata_string(metadata: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _metadata_owner_user_id(metadata: Mapping[str, Any]) -> str | None:
    auth_scope = _metadata_mapping(metadata.get("authScope"))
    return _metadata_string(auth_scope, "userId", "user_id") or _metadata_string(
        metadata,
        *_OWNER_USER_KEYS,
    )


def _metadata_owner_team_id(metadata: Mapping[str, Any]) -> str | None:
    auth_scope = _metadata_mapping(metadata.get("authScope"))
    return _metadata_string(auth_scope, "teamId", "team_id") or _metadata_string(
        metadata,
        *_OWNER_TEAM_KEYS,
    )


def _metadata_matches_scope(
    metadata: Mapping[str, Any] | None,
    scope: OwnedMetadataScope,
) -> bool:
    metadata = _metadata_mapping(metadata)
    owner_user_id = _metadata_owner_user_id(metadata)
    owner_team_id = _metadata_owner_team_id(metadata)
    team_id = (scope.team_id or "").strip()

    if owner_user_id and owner_user_id == scope.user_id:
        return True
    if team_id and owner_team_id == team_id:
        if scope.include_team_scope or not owner_user_id:
            return True
    if not owner_user_id and not owner_team_id:
        return scope.allow_unscoped
    return False


def _require_metadata_within_scope(
    metadata: Mapping[str, Any] | None,
    scope: OwnedMetadataScope,
    *,
    operation: str,
) -> None:
    if not _metadata_matches_scope(metadata, scope):
        raise DomainValidationException(
            "metadata is outside the current metadata_scope",
            field="metadata",
            details={"operation": operation},
            message_key="conversation.scope.metadata_outside_scope",
        )


def _merge_metadata_preserving_acl(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(incoming or {}).items():
        if key not in _ACL_METADATA_KEYS:
            merged[key] = value
    for key in _ACL_METADATA_KEYS:
        if existing and key in existing:
            merged[key] = existing[key]
    return merged


async def _raise_conversation_not_found(
    conversation_id: int,
) -> None:
    raise ConversationNotFoundException(conversation_id)


async def _raise_agent_config_not_found(
    config_id: int,
) -> None:
    raise AgentConfigNotFoundException(config_id)


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


def _forked_created_at_after_parent(
    source_created_at: datetime | None,
    parent_created_at: datetime | None,
) -> datetime | None:
    if source_created_at is None or parent_created_at is None:
        return source_created_at
    if source_created_at > parent_created_at:
        return source_created_at
    return parent_created_at + timedelta(microseconds=1)


def _remap_fork_conversation_metadata(
    metadata: dict[str, Any],
    source_to_forked_id: Mapping[str, str],
) -> dict[str, Any]:
    remapped = dict(metadata)
    for key, remap in {
        "selectedPath": _remap_selected_path_metadata,
        "currentBranchTail": _remap_branch_tail_metadata,
        "messageTreeSelection": _remap_message_tree_selection_metadata,
    }.items():
        value = remapped.get(key)
        if isinstance(value, Mapping):
            remapped[key] = remap(value, source_to_forked_id)
    return remapped


def _remap_selected_path_metadata(
    metadata: Mapping[str, Any],
    source_to_forked_id: Mapping[str, str],
) -> dict[str, Any]:
    remapped = dict(metadata)
    if isinstance(remapped.get("messageIds"), SequenceABC) and not isinstance(
        remapped.get("messageIds"), str | bytes | bytearray
    ):
        remapped["messageIds"] = [
            mapped_id
            for raw_id in remapped["messageIds"]
            if (mapped_id := _forked_message_id(raw_id, source_to_forked_id)) is not None
        ]
    for key in ("tailMessageId", "selectedMessageId", "messageId"):
        if key in remapped:
            remapped[key] = _forked_message_id(remapped[key], source_to_forked_id)
    return remapped


def _remap_branch_tail_metadata(
    metadata: Mapping[str, Any],
    source_to_forked_id: Mapping[str, str],
) -> dict[str, Any]:
    remapped = dict(metadata)
    for key in ("messageId", "publicId", "tailMessageId", "selectedMessageId"):
        if key in remapped:
            remapped[key] = _forked_message_id(remapped[key], source_to_forked_id)
    return remapped


def _remap_message_tree_selection_metadata(
    metadata: Mapping[str, Any],
    source_to_forked_id: Mapping[str, str],
) -> dict[str, Any]:
    remapped = _remap_branch_tail_metadata(metadata, source_to_forked_id)
    path = remapped.get("path")
    if isinstance(path, SequenceABC) and not isinstance(path, str | bytes | bytearray):
        remapped["path"] = [
            remapped_item
            for item in path
            if (remapped_item := _remap_message_tree_path_item(item, source_to_forked_id))
            is not None
        ]
    return remapped


def _remap_message_tree_path_item(
    item: object,
    source_to_forked_id: Mapping[str, str],
) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    remapped = dict(item)
    has_required_public_id = False
    for key in ("publicId", "public_id", "messageId", "message_id"):
        if key not in remapped:
            continue
        mapped_id = _forked_message_id(remapped[key], source_to_forked_id)
        if mapped_id is None:
            return None
        remapped[key] = mapped_id
        has_required_public_id = True
    for key in ("parentMessageId", "parent_message_id"):
        if key in remapped:
            remapped[key] = _forked_message_id(remapped[key], source_to_forked_id)
    return remapped if has_required_public_id else dict(item)


def _forked_message_id(
    value: object,
    source_to_forked_id: Mapping[str, str],
) -> str | None:
    if not isinstance(value, str):
        return None
    return source_to_forked_id.get(value)


def _message_action_metadata(
    source: Message,
    *,
    action_key: str,
    metadata: dict | None,
) -> dict:
    inherited = dict(source.metadata or {})
    merged = {
        **inherited,
        **(metadata or {}),
        action_key: source.public_id,
    }
    if source.provider is not None and not _clean_optional_text(merged.get("provider")):
        merged["provider"] = source.provider
    if source.model is not None and not _clean_optional_text(merged.get("model")):
        merged["model"] = source.model
    return merged


class ConversationApplicationService:
    """High-level conversation workflows bridging API and domain layers."""

    def __init__(self, uow_factory: Callable[..., AbstractUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    # Conversation CRUD

    async def create_conversation(
        self,
        dto: CreateConversationDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="create_conversation")
        _require_metadata_within_scope(dto.metadata, scope, operation="create_conversation")
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

    async def get_conversation(
        self,
        conversation_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationDTO:
        scope = _require_metadata_scope(metadata_scope, operation="get_conversation")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                await _raise_conversation_not_found(conversation_id)
            return ConversationDTO.model_validate(conv)

    async def list_conversations(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> Tuple[list[ConversationDTO], int]:
        scope = _require_metadata_scope(metadata_scope, operation="list_conversations")
        async with self._uow_factory(readonly=True) as uow:
            items = await uow.conversation_repository.list(
                status=status,
                skip=skip,
                limit=limit,
                metadata_scope=scope,
            )
            total = await uow.conversation_repository.count(
                status=status,
                metadata_scope=scope,
            )
            return [ConversationDTO.model_validate(c) for c in items], total

    async def update_conversation(
        self,
        conversation_id: int,
        dto: UpdateConversationDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="update_conversation")
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                await _raise_conversation_not_found(conversation_id)
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
            updated = await uow.conversation_repository.update(
                conv,
                metadata_scope=scope,
            )
            return ConversationDTO.model_validate(updated)

    async def delete_conversation(
        self,
        conversation_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="delete_conversation")
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                await _raise_conversation_not_found(conversation_id)
            conv.soft_delete()
            updated = await uow.conversation_repository.update(
                conv,
                metadata_scope=scope,
            )
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> Tuple[list[MessageDTO_Agent], int]:
        scope = _require_metadata_scope(metadata_scope, operation="list_messages")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> list[MessageDTO_Agent]:
        scope = _require_metadata_scope(metadata_scope, operation="get_message_path")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> list[MessageDTO_Agent]:
        scope = _require_metadata_scope(metadata_scope, operation="list_message_children")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            parent = await uow.message_repository.get_by_public_id(message_public_id)
            if parent is None or parent.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if parent.status == "deleted" and not include_deleted:
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

    async def apply_message_action(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: MessageActionDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> MessageActionResultDTO:
        action = dto.action
        if action == "branch":
            scope = _require_metadata_scope(metadata_scope, operation="apply_message_action")
            return await self._build_message_action_result(
                conversation_id=conversation_id,
                message_public_id=message_public_id,
                action=action,
                include_deleted=dto.include_deleted,
                statuses=dto.statuses,
                metadata_scope=scope,
            )
        scope = _require_mutation_metadata_scope(
            metadata_scope,
            operation=f"apply_message_action.{action}",
        )
        if action == "edit":
            created = await self.edit_message(
                conversation_id,
                message_public_id,
                EditMessageDTO(content=dto.content or "", metadata=dto.metadata),
                metadata_scope=scope,
            )
            return await self._build_message_action_result(
                conversation_id=conversation_id,
                message_public_id=created.public_id or "",
                action=action,
                metadata_scope=scope,
            )
        if action == "retry":
            created = await self.retry_message(
                conversation_id,
                message_public_id,
                RetryMessageDTO(content=dto.content or "", metadata=dto.metadata),
                metadata_scope=scope,
            )
            return await self._build_message_action_result(
                conversation_id=conversation_id,
                message_public_id=created.public_id or "",
                action=action,
                metadata_scope=scope,
            )

        forked = await self.fork_conversation(
            conversation_id,
            message_public_id,
            ForkConversationDTO(
                title=dto.title,
                option=dto.option,
                include_deleted=dto.include_deleted,
                statuses=dto.statuses,
                metadata=dto.metadata,
            ),
            metadata_scope=scope,
        )
        forked_message_id = forked.source_to_forked_id.get(message_public_id)
        message = next(
            (item for item in forked.messages if item.public_id == forked_message_id),
            None,
        )
        if message is None:
            raise MessageNotFoundException()
        return MessageActionResultDTO(
            action=action,
            message=message,
            path=forked.messages,
            children=[],
            siblings=[message],
            branch_id=message.branch_id,
            conversation=forked.conversation,
            messages=forked.messages,
            source_to_forked_id=forked.source_to_forked_id,
        )

    async def _build_message_action_result(
        self,
        *,
        conversation_id: int,
        message_public_id: str,
        action: Literal["branch", "edit", "retry", "fork"],
        include_deleted: bool = False,
        statuses: Sequence[str] | None = None,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> MessageActionResultDTO:
        scope = _require_metadata_scope(
            metadata_scope,
            operation="build_message_action_result",
        )
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            message = await uow.message_repository.get_by_public_id(message_public_id)
            if message is None or message.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if message.status == "deleted" and not include_deleted:
                raise MessageNotFoundException()

            cleaned_statuses = _clean_statuses(statuses)
            path = await uow.message_repository.list_path_to_message(
                conversation_id,
                message_public_id,
                include_deleted=include_deleted,
                statuses=cleaned_statuses,
            )
            if not path or path[-1].public_id != message_public_id:
                raise MessageNotFoundException()

            children = await uow.message_repository.list_children(
                message_public_id,
                statuses=cleaned_statuses,
                include_deleted=include_deleted,
            )
            children = [
                child for child in children if child.conversation_id == conversation_id
            ]

            if message.parent_message_id:
                siblings = await uow.message_repository.list_children(
                    message.parent_message_id,
                    statuses=cleaned_statuses,
                    include_deleted=include_deleted,
                )
                siblings = [
                    sibling
                    for sibling in siblings
                    if sibling.conversation_id == conversation_id
                ]
            else:
                roots = await uow.message_repository.list_by_conversation(
                    conversation_id,
                    limit=10000,
                    statuses=cleaned_statuses,
                    include_deleted=include_deleted,
                )
                siblings = [root for root in roots if root.parent_message_id is None]

            return MessageActionResultDTO(
                action=action,
                message=MessageDTO_Agent.model_validate(message),
                path=[MessageDTO_Agent.model_validate(item) for item in path],
                children=[MessageDTO_Agent.model_validate(item) for item in children],
                siblings=[MessageDTO_Agent.model_validate(item) for item in siblings],
                branch_id=message.branch_id,
            )

    async def fork_conversation(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: ForkConversationDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ForkConversationResultDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="fork_conversation")
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
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
                **_merge_metadata_preserving_acl(conv.metadata, dto.metadata),
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
            created_at_by_source_id: dict[str, datetime | None] = {}
            selected_ids = {message.public_id for message in selected if message.public_id}
            for source in _parent_first(selected):
                parent_id = (
                    id_map.get(source.parent_message_id)
                    if source.parent_message_id in selected_ids
                    else None
                )
                parent_created_at = (
                    created_at_by_source_id.get(source.parent_message_id)
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
                    created_at=_forked_created_at_after_parent(
                        source.created_at,
                        parent_created_at,
                    ),
                )
                created = await uow.message_repository.create(forked)
                id_map[source.public_id] = created.public_id
                created_at_by_source_id[source.public_id] = created.created_at
                created_messages.append(created)

            forked_conversation.metadata = _remap_fork_conversation_metadata(
                forked_conversation.metadata,
                id_map,
            )
            forked_conversation.updated_at = _utcnow()
            forked_conversation = await uow.conversation_repository.update(
                forked_conversation,
                metadata_scope=scope,
            )

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
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> MessageDTO_Agent:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="edit_message")
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            source = await uow.message_repository.get_by_public_id(message_public_id)
            if source is None or source.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if source.status == "deleted":
                raise MessageNotFoundException()

            edited = source.create_edit(
                content=dto.content,
                metadata=_message_action_metadata(
                    source,
                    action_key="edit_of",
                    metadata=dto.metadata,
                ),
            )
            source.mark_superseded()
            await uow.message_repository.update(source)
            created = await uow.message_repository.create(edited)
            return MessageDTO_Agent.model_validate(created)

    async def retry_message(
        self,
        conversation_id: int,
        message_public_id: str,
        dto: RetryMessageDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> MessageDTO_Agent:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="retry_message")
        async with self._uow_factory() as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            source = await uow.message_repository.get_by_public_id(message_public_id)
            if source is None or source.conversation_id != conversation_id:
                raise MessageNotFoundException()
            if source.status == "deleted":
                raise MessageNotFoundException()

            retry = source.create_retry(
                content=dto.content,
                metadata=_message_action_metadata(
                    source,
                    action_key="retry_of",
                    metadata=dto.metadata,
                ),
            )
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> MessageLocationDTO:
        scope = _require_metadata_scope(metadata_scope, operation="locate_message")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> list[MessageSearchResultDTO]:
        scope = _require_metadata_scope(metadata_scope, operation="search_messages")
        normalized_query = _clean_optional_text(query)
        if normalized_query is None:
            return []
        cleaned_statuses = _clean_statuses(statuses)
        include_deleted_locators = bool(cleaned_statuses and "deleted" in cleaned_statuses)

        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)

            matches = await uow.message_repository.search_by_content(
                conversation_id,
                normalized_query,
                skip=max(0, skip),
                limit=max(1, limit),
                branch_id=_clean_optional_text(branch_id),
                roles=roles,
                statuses=cleaned_statuses,
                provider=_clean_optional_text(provider),
                model=_clean_optional_text(model),
            )

            results: list[MessageSearchResultDTO] = []
            for match in matches:
                include_deleted_for_match = (
                    include_deleted_locators or match.status == "deleted"
                )
                path: list[Message] = []
                if include_path:
                    path = await uow.message_repository.list_path_to_message(
                        conversation_id,
                        match.public_id,
                        include_deleted=include_deleted_for_match,
                    )
                context = await uow.message_repository.list_context_window(
                    conversation_id,
                    match.public_id,
                    before=max(0, context_before),
                    after=max(0, context_after),
                    include_deleted=include_deleted_for_match,
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
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> list[RunDTO]:
        scope = _require_metadata_scope(metadata_scope, operation="list_runs")
        async with self._uow_factory(readonly=True) as uow:
            conv = await uow.conversation_repository.get_by_id(
                conversation_id,
                metadata_scope=scope,
            )
            if conv is None:
                raise ConversationNotFoundException(conversation_id)
            items = await uow.run_repository.list_by_conversation(
                conversation_id,
                skip=skip,
                limit=limit,
                provider=_clean_optional_text(provider),
                status=_clean_optional_text(status),
                trigger_message_id=_clean_optional_text(trigger_message_id),
            )
            return [RunDTO.model_validate(r) for r in items]

    # Agent Config CRUD

    async def create_agent_config(
        self,
        dto: CreateAgentConfigDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> AgentConfigDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="create_agent_config")
        _require_metadata_within_scope(dto.metadata, scope, operation="create_agent_config")
        now = _utcnow()
        async with self._uow_factory() as uow:
            existing = await uow.agent_config_repository.get_by_name(
                dto.name,
                metadata_scope=scope,
            )
            if existing is not None:
                raise AgentConfigNameExistsException(dto.name)
            config = AgentConfig(
                id=None,
                name=dto.name,
                system_prompt=dto.system_prompt,
                model=dto.model,
                temperature=dto.temperature,
                max_tokens=dto.max_tokens,
                tool_ids=tuple(normalize_agent_resource_ids(dto.tool_ids)),
                mcp_server_ids=tuple(normalize_agent_resource_ids(dto.mcp_server_ids)),
                metadata=dto.metadata or {},
                created_at=now,
                updated_at=now,
            )
            created = await uow.agent_config_repository.create(config)
            return AgentConfigDTO.model_validate(created)

    async def get_agent_config(
        self,
        config_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> AgentConfigDTO:
        scope = _require_metadata_scope(metadata_scope, operation="get_agent_config")
        async with self._uow_factory(readonly=True) as uow:
            config = await uow.agent_config_repository.get_by_id(
                config_id,
                metadata_scope=scope,
            )
            if config is None:
                await _raise_agent_config_not_found(config_id)
            return AgentConfigDTO.model_validate(config)

    async def list_agent_configs(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> Tuple[list[AgentConfigDTO], int]:
        scope = _require_metadata_scope(metadata_scope, operation="list_agent_configs")
        async with self._uow_factory(readonly=True) as uow:
            items = await uow.agent_config_repository.list(
                skip=skip,
                limit=limit,
                metadata_scope=scope,
            )
            total = await uow.agent_config_repository.count(metadata_scope=scope)
            return [AgentConfigDTO.model_validate(c) for c in items], total

    async def update_agent_config(
        self,
        config_id: int,
        dto: UpdateAgentConfigDTO,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> AgentConfigDTO:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="update_agent_config")
        async with self._uow_factory() as uow:
            config = await uow.agent_config_repository.get_by_id(
                config_id,
                metadata_scope=scope,
            )
            if config is None:
                await _raise_agent_config_not_found(config_id)
            if dto.name is not None:
                # Check uniqueness
                existing = await uow.agent_config_repository.get_by_name(
                    dto.name,
                    metadata_scope=scope,
                )
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
            if dto.tool_ids is not None:
                config.tool_ids = normalize_agent_resource_ids(dto.tool_ids)
            if dto.mcp_server_ids is not None:
                config.mcp_server_ids = normalize_agent_resource_ids(dto.mcp_server_ids)
            if dto.metadata is not None:
                config.metadata = _merge_metadata_preserving_acl(config.metadata, dto.metadata)
            config._touch()
            updated = await uow.agent_config_repository.update(
                config,
                metadata_scope=scope,
            )
            return AgentConfigDTO.model_validate(updated)

    async def delete_agent_config(
        self,
        config_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> None:
        scope = _require_mutation_metadata_scope(metadata_scope, operation="delete_agent_config")
        async with self._uow_factory() as uow:
            config = await uow.agent_config_repository.get_by_id(
                config_id,
                metadata_scope=scope,
            )
            if config is None:
                await _raise_agent_config_not_found(config_id)
            await uow.agent_config_repository.delete(
                config_id,
                metadata_scope=scope,
            )
