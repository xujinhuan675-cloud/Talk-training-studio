from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from application.dto import (
    CreateAgentConfigDTO,
    CreateConversationDTO,
    EditMessageDTO,
    ForkConversationDTO,
    MessageActionDTO,
    RetryMessageDTO,
    UpdateConversationDTO,
    UpdateAgentConfigDTO,
)
from application.services.conversation_service import ConversationApplicationService
from domain.common.exceptions import DomainValidationException
from domain.conversation.entity import AgentConfig, Conversation
from domain.conversation.exceptions import (
    AgentConfigNotFoundException,
    ConversationNotFoundException,
)
from domain.conversation.repository import OwnedMetadataScope


def _scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


def _read_scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=True,
    )


def _config(config_id: int, name: str) -> AgentConfig:
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return AgentConfig(
        id=config_id,
        name=name,
        system_prompt=None,
        model="gpt-test",
        metadata={
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
        },
        created_at=now,
        updated_at=now,
    )


def _conversation(conversation_id: int) -> Conversation:
    now = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return Conversation(
        id=conversation_id,
        title="Hidden",
        system_prompt=None,
        model="gpt-test",
        metadata={"ownerUserId": "user-cs-001", "teamId": "team-service"},
        created_at=now,
        updated_at=now,
    )


class _ScopedMissConversationRepository:
    def __init__(self) -> None:
        self.get_by_id_calls: list[dict[str, Any]] = []

    async def get_by_id(self, conversation_id: int, *, metadata_scope=None):
        self.get_by_id_calls.append(
            {"conversation_id": conversation_id, "metadata_scope": metadata_scope}
        )
        if metadata_scope is None:
            return _conversation(conversation_id)
        return None


class _FakeAgentConfigRepository:
    def __init__(self) -> None:
        self.config = _config(7, "current")
        self.get_by_name_calls: list[dict[str, Any]] = []
        self.create_calls: list[AgentConfig] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []
        self.count_calls: list[dict[str, Any]] = []

    async def get_by_name(self, name: str, *, metadata_scope=None):
        self.get_by_name_calls.append({"name": name, "metadata_scope": metadata_scope})
        if metadata_scope is None and name == "shared-hidden":
            return _config(99, name)
        return None

    async def get_by_id(self, config_id: int, *, metadata_scope=None):
        if config_id == self.config.id:
            return self.config
        return None

    async def create(self, config: AgentConfig):
        config.id = 8
        self.create_calls.append(config)
        return config

    async def update(self, config: AgentConfig, *, metadata_scope=None):
        self.update_calls.append({"config": config, "metadata_scope": metadata_scope})
        self.config = config
        return config

    async def delete(self, config_id: int, *, metadata_scope=None):
        self.delete_calls.append({"config_id": config_id, "metadata_scope": metadata_scope})

    async def list(self, *, skip: int = 0, limit: int = 20, metadata_scope=None):
        self.list_calls.append({"skip": skip, "limit": limit, "metadata_scope": metadata_scope})
        return [self.config][skip : skip + limit]

    async def count(self, *, metadata_scope=None):
        self.count_calls.append({"metadata_scope": metadata_scope})
        return 1


class _ScopedMissAgentConfigRepository(_FakeAgentConfigRepository):
    def __init__(self) -> None:
        super().__init__()
        self.get_by_id_calls: list[dict[str, Any]] = []

    async def get_by_id(self, config_id: int, *, metadata_scope=None):
        self.get_by_id_calls.append({"config_id": config_id, "metadata_scope": metadata_scope})
        if metadata_scope is None:
            return self.config
        return None


class _FakeUnitOfWork:
    def __init__(
        self,
        agent_config_repository=None,
        *,
        conversation_repository=None,
        readonly: bool = False,
    ) -> None:
        self.agent_config_repository = agent_config_repository
        self.conversation_repository = conversation_repository
        self.readonly = readonly

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakeConversationCreateRepository:
    def __init__(self) -> None:
        self.create_calls: list[Conversation] = []

    async def create(self, conversation: Conversation) -> Conversation:
        conversation.id = 17
        self.create_calls.append(conversation)
        return conversation


def _service(repo: _FakeAgentConfigRepository) -> ConversationApplicationService:
    def uow_factory(*, readonly: bool = False):
        return _FakeUnitOfWork(repo, readonly=readonly)

    return ConversationApplicationService(uow_factory=uow_factory)


def _service_with_repositories(
    *,
    conversation_repository=None,
    agent_config_repository=None,
) -> ConversationApplicationService:
    def uow_factory(*, readonly: bool = False):
        return _FakeUnitOfWork(
            agent_config_repository,
            conversation_repository=conversation_repository,
            readonly=readonly,
        )

    return ConversationApplicationService(uow_factory=uow_factory)


async def _call_conversation_child_method(
    service: ConversationApplicationService,
    method_name: str,
    *,
    metadata_scope=None,
) -> None:
    if method_name == "list_messages":
        await service.list_messages(7, metadata_scope=metadata_scope)
        return
    if method_name == "get_message_path":
        await service.get_message_path(7, "msg-1", metadata_scope=metadata_scope)
        return
    if method_name == "list_message_children":
        await service.list_message_children(7, "msg-1", metadata_scope=metadata_scope)
        return
    if method_name == "apply_message_action":
        await service.apply_message_action(
            7,
            "msg-1",
            MessageActionDTO(action="branch"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "fork_conversation":
        await service.fork_conversation(
            7,
            "msg-1",
            ForkConversationDTO(option="directPath"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "edit_message":
        await service.edit_message(
            7,
            "msg-1",
            EditMessageDTO(content="edited"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "retry_message":
        await service.retry_message(
            7,
            "msg-1",
            RetryMessageDTO(content="retry"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "locate_message":
        await service.locate_message(7, "msg-1", metadata_scope=metadata_scope)
        return
    if method_name == "search_messages":
        await service.search_messages(7, "needle", metadata_scope=metadata_scope)
        return
    if method_name == "list_runs":
        await service.list_runs(7, metadata_scope=metadata_scope)
        return
    raise AssertionError(f"Unknown method under test: {method_name}")


async def _call_conversation_top_level_method(
    service: ConversationApplicationService,
    method_name: str,
    *,
    metadata_scope=None,
) -> None:
    if method_name == "get_conversation":
        await service.get_conversation(7, metadata_scope=metadata_scope)
        return
    if method_name == "list_conversations":
        await service.list_conversations(metadata_scope=metadata_scope)
        return
    if method_name == "update_conversation":
        await service.update_conversation(
            7,
            UpdateConversationDTO(title="updated"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "delete_conversation":
        await service.delete_conversation(7, metadata_scope=metadata_scope)
        return
    raise AssertionError(f"Unknown method under test: {method_name}")


async def _call_conversation_mutation_method(
    service: ConversationApplicationService,
    method_name: str,
    *,
    metadata_scope=None,
) -> None:
    if method_name == "update_conversation":
        await service.update_conversation(
            7,
            UpdateConversationDTO(title="updated"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "delete_conversation":
        await service.delete_conversation(7, metadata_scope=metadata_scope)
        return
    if method_name == "apply_message_action_edit":
        await service.apply_message_action(
            7,
            "msg-1",
            MessageActionDTO(action="edit", content="edited"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "apply_message_action_retry":
        await service.apply_message_action(
            7,
            "msg-1",
            MessageActionDTO(action="retry", content="retry"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "apply_message_action_fork":
        await service.apply_message_action(
            7,
            "msg-1",
            MessageActionDTO(action="fork"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "fork_conversation":
        await service.fork_conversation(
            7,
            "msg-1",
            ForkConversationDTO(option="directPath"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "edit_message":
        await service.edit_message(
            7,
            "msg-1",
            EditMessageDTO(content="edited"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "retry_message":
        await service.retry_message(
            7,
            "msg-1",
            RetryMessageDTO(content="retry"),
            metadata_scope=metadata_scope,
        )
        return
    raise AssertionError(f"Unknown method under test: {method_name}")


async def _call_agent_config_method(
    service: ConversationApplicationService,
    method_name: str,
    *,
    metadata_scope=None,
) -> None:
    metadata = dict(_config(7, "current").metadata)
    if method_name == "create_agent_config":
        await service.create_agent_config(
            CreateAgentConfigDTO(name="new-agent", metadata=metadata),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "get_agent_config":
        await service.get_agent_config(7, metadata_scope=metadata_scope)
        return
    if method_name == "list_agent_configs":
        await service.list_agent_configs(metadata_scope=metadata_scope)
        return
    if method_name == "update_agent_config":
        await service.update_agent_config(
            7,
            UpdateAgentConfigDTO(name="renamed"),
            metadata_scope=metadata_scope,
        )
        return
    if method_name == "delete_agent_config":
        await service.delete_agent_config(7, metadata_scope=metadata_scope)
        return
    raise AssertionError(f"Unknown method under test: {method_name}")


@pytest.mark.asyncio
async def test_agent_config_create_and_update_name_checks_are_metadata_scoped() -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)
    scope = _scope()

    created = await service.create_agent_config(
        CreateAgentConfigDTO(name="shared-hidden", metadata=dict(_config(8, "new").metadata)),
        metadata_scope=scope,
    )
    updated = await service.update_agent_config(
        7,
        UpdateAgentConfigDTO(name="shared-hidden"),
        metadata_scope=scope,
    )

    assert created.name == "shared-hidden"
    assert updated.name == "shared-hidden"
    assert repo.get_by_name_calls == [
        {"name": "shared-hidden", "metadata_scope": scope},
        {"name": "shared-hidden", "metadata_scope": scope},
    ]
    assert repo.create_calls
    assert repo.update_calls[0]["metadata_scope"] == scope


@pytest.mark.asyncio
async def test_create_conversation_requires_metadata_scope() -> None:
    repo = _FakeConversationCreateRepository()
    service = _service_with_repositories(conversation_repository=repo)

    with pytest.raises(DomainValidationException):
        await service.create_conversation(
            CreateConversationDTO(title="Unscoped", metadata=dict(_config(1, "x").metadata)),
        )

    assert repo.create_calls == []


@pytest.mark.asyncio
async def test_create_conversation_rejects_metadata_outside_scope() -> None:
    repo = _FakeConversationCreateRepository()
    service = _service_with_repositories(conversation_repository=repo)

    with pytest.raises(DomainValidationException):
        await service.create_conversation(
            CreateConversationDTO(
                title="Forged",
                metadata={"ownerUserId": "user-cs-001", "teamId": "team-service"},
            ),
            metadata_scope=_scope(),
        )

    assert repo.create_calls == []


@pytest.mark.parametrize(
    "method_name",
    [
        "create_agent_config",
        "get_agent_config",
        "list_agent_configs",
        "update_agent_config",
        "delete_agent_config",
    ],
)
@pytest.mark.asyncio
async def test_agent_config_methods_require_metadata_scope(method_name: str) -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)

    with pytest.raises(DomainValidationException):
        await _call_agent_config_method(service, method_name)

    assert repo.get_by_name_calls == []
    assert repo.create_calls == []
    assert repo.update_calls == []
    assert repo.delete_calls == []
    assert repo.list_calls == []
    assert repo.count_calls == []


@pytest.mark.parametrize(
    "method_name",
    ["create_agent_config", "update_agent_config", "delete_agent_config"],
)
@pytest.mark.asyncio
async def test_agent_config_mutations_reject_read_scope(method_name: str) -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)

    with pytest.raises(DomainValidationException):
        await _call_agent_config_method(
            service,
            method_name,
            metadata_scope=_read_scope(),
        )

    assert repo.get_by_name_calls == []
    assert repo.create_calls == []
    assert repo.update_calls == []
    assert repo.delete_calls == []


@pytest.mark.asyncio
async def test_agent_config_create_rejects_metadata_outside_scope() -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)

    with pytest.raises(DomainValidationException):
        await service.create_agent_config(
            CreateAgentConfigDTO(
                name="forged-agent",
                metadata={"ownerUserId": "user-cs-001", "teamId": "team-service"},
            ),
            metadata_scope=_scope(),
        )

    assert repo.get_by_name_calls == []
    assert repo.create_calls == []


@pytest.mark.asyncio
async def test_agent_config_update_preserves_acl_metadata() -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)

    updated = await service.update_agent_config(
        7,
        UpdateAgentConfigDTO(
            metadata={
                "ownerUserId": "user-cs-001",
                "teamId": "team-service",
                "label": "review helper",
            },
        ),
        metadata_scope=_scope(),
    )

    assert updated.metadata["ownerUserId"] == "user-sales-001"
    assert updated.metadata["teamId"] == "team-revenue"
    assert updated.metadata["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }
    assert updated.metadata["label"] == "review helper"


@pytest.mark.parametrize(
    "method_name",
    [
        "get_conversation",
        "list_conversations",
        "update_conversation",
        "delete_conversation",
    ],
)
@pytest.mark.asyncio
async def test_conversation_top_level_methods_require_metadata_scope(
    method_name: str,
) -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)

    with pytest.raises(DomainValidationException):
        await _call_conversation_top_level_method(service, method_name)

    assert repo.get_by_id_calls == []


@pytest.mark.asyncio
async def test_scoped_conversation_miss_does_not_fall_back_to_unscoped_probe() -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)
    scope = _scope()

    with pytest.raises(ConversationNotFoundException):
        await service.get_conversation(7, metadata_scope=scope)

    assert repo.get_by_id_calls == [{"conversation_id": 7, "metadata_scope": scope}]


@pytest.mark.parametrize(
    "method_name",
    [
        "update_conversation",
        "delete_conversation",
        "apply_message_action_edit",
        "apply_message_action_retry",
        "apply_message_action_fork",
        "fork_conversation",
        "edit_message",
        "retry_message",
    ],
)
@pytest.mark.asyncio
async def test_conversation_mutation_methods_reject_read_scope(
    method_name: str,
) -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)

    with pytest.raises(DomainValidationException):
        await _call_conversation_mutation_method(
            service,
            method_name,
            metadata_scope=_read_scope(),
        )

    assert repo.get_by_id_calls == []


@pytest.mark.asyncio
async def test_conversation_branch_action_allows_read_scope_for_lookup() -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)
    scope = _read_scope()

    with pytest.raises(ConversationNotFoundException):
        await service.apply_message_action(
            7,
            "msg-1",
            MessageActionDTO(action="branch"),
            metadata_scope=scope,
        )

    assert repo.get_by_id_calls == [{"conversation_id": 7, "metadata_scope": scope}]


@pytest.mark.parametrize(
    "method_name",
    [
        "list_messages",
        "get_message_path",
        "list_message_children",
        "apply_message_action",
        "fork_conversation",
        "edit_message",
        "retry_message",
        "locate_message",
        "search_messages",
        "list_runs",
    ],
)
@pytest.mark.asyncio
async def test_conversation_child_methods_require_metadata_scope(method_name: str) -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)

    with pytest.raises(DomainValidationException):
        await _call_conversation_child_method(service, method_name)

    assert repo.get_by_id_calls == []


@pytest.mark.parametrize(
    "method_name",
    [
        "list_messages",
        "get_message_path",
        "list_message_children",
        "apply_message_action",
        "fork_conversation",
        "edit_message",
        "retry_message",
        "locate_message",
        "search_messages",
        "list_runs",
    ],
)
@pytest.mark.asyncio
async def test_conversation_child_methods_do_not_fall_back_after_scoped_miss(
    method_name: str,
) -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)
    scope = _scope()

    with pytest.raises(ConversationNotFoundException):
        await _call_conversation_child_method(
            service,
            method_name,
            metadata_scope=scope,
        )

    assert repo.get_by_id_calls == [{"conversation_id": 7, "metadata_scope": scope}]


@pytest.mark.asyncio
async def test_scoped_agent_config_miss_does_not_fall_back_to_unscoped_probe() -> None:
    repo = _ScopedMissAgentConfigRepository()
    service = _service_with_repositories(agent_config_repository=repo)
    scope = _scope()

    with pytest.raises(AgentConfigNotFoundException):
        await service.get_agent_config(7, metadata_scope=scope)

    assert repo.get_by_id_calls == [{"config_id": 7, "metadata_scope": scope}]
