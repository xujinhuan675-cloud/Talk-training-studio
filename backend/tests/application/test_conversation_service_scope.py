from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from application.dto import CreateAgentConfigDTO, UpdateAgentConfigDTO
from application.services.conversation_service import ConversationApplicationService
from domain.conversation.entity import AgentConfig, Conversation
from domain.conversation.exceptions import (
    AgentConfigNameExistsException,
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


@pytest.mark.asyncio
async def test_agent_config_create_and_update_name_checks_are_metadata_scoped() -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)
    scope = _scope()

    created = await service.create_agent_config(
        CreateAgentConfigDTO(name="shared-hidden"),
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
async def test_agent_config_unscoped_name_check_still_detects_visible_conflict() -> None:
    repo = _FakeAgentConfigRepository()
    service = _service(repo)

    with pytest.raises(AgentConfigNameExistsException):
        await service.create_agent_config(CreateAgentConfigDTO(name="shared-hidden"))

    assert repo.get_by_name_calls == [{"name": "shared-hidden", "metadata_scope": None}]


@pytest.mark.asyncio
async def test_scoped_conversation_miss_does_not_fall_back_to_unscoped_probe() -> None:
    repo = _ScopedMissConversationRepository()
    service = _service_with_repositories(conversation_repository=repo)
    scope = _scope()

    with pytest.raises(ConversationNotFoundException):
        await service.get_conversation(7, metadata_scope=scope)

    assert repo.get_by_id_calls == [{"conversation_id": 7, "metadata_scope": scope}]


@pytest.mark.asyncio
async def test_scoped_agent_config_miss_does_not_fall_back_to_unscoped_probe() -> None:
    repo = _ScopedMissAgentConfigRepository()
    service = _service_with_repositories(agent_config_repository=repo)
    scope = _scope()

    with pytest.raises(AgentConfigNotFoundException):
        await service.get_agent_config(7, metadata_scope=scope)

    assert repo.get_by_id_calls == [{"config_id": 7, "metadata_scope": scope}]
