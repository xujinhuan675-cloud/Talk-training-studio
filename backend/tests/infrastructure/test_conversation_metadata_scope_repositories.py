from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from domain.conversation.entity import AgentConfig, Conversation
from domain.conversation.exceptions import (
    AgentConfigNotFoundException,
    ConversationNotFoundException,
)
from domain.common.exceptions import DomainValidationException
from domain.conversation.repository import OwnedMetadataScope
from infrastructure.models.base import Base
from infrastructure.repositories.agent_config_repository import SQLAlchemyAgentConfigRepository
from infrastructure.repositories.conversation_repository import SQLAlchemyConversationRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        yield db

    await engine.dispose()


def _at(day: int) -> datetime:
    return datetime(2026, 1, day, tzinfo=timezone.utc)


def _conversation(title: str, day: int, metadata: dict) -> Conversation:
    return Conversation(
        id=None,
        title=title,
        system_prompt=None,
        model="gpt-test",
        metadata=metadata,
        created_at=_at(day),
        updated_at=_at(day),
    )


def _agent_config(name: str, day: int, metadata: dict) -> AgentConfig:
    return AgentConfig(
        id=None,
        name=name,
        system_prompt=None,
        model="gpt-test",
        metadata=metadata,
        created_at=_at(day),
        updated_at=_at(day),
    )


@pytest.mark.asyncio
async def test_conversation_repository_filters_metadata_scope_before_pagination(session) -> None:
    repo = SQLAlchemyConversationRepository(session)
    await repo.create(
        _conversation(
            "conflicting-hidden",
            6,
            {
                "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                "ownerUserId": "user-sales-001",
                "teamId": "team-revenue",
            },
        )
    )
    await repo.create(
        _conversation(
            "hidden-newest",
            5,
            {"ownerUserId": "user-cs-001", "teamId": "team-service"},
        )
    )
    await repo.create(
        _conversation(
            "sales-auth-scope",
            4,
            {"authScope": {"userId": "user-sales-001", "teamId": "team-revenue"}},
        )
    )
    await repo.create(_conversation("sales-team-owned", 3, {"teamId": "team-revenue"}))
    await repo.create(
        _conversation(
            "other-sales-user",
            2,
            {"ownerUserId": "user-peer-001", "teamId": "team-revenue"},
        )
    )
    await repo.create(_conversation("unscoped", 1, {}))

    staff_scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=True,
    )
    first_page = await repo.list(skip=0, limit=1, metadata_scope=staff_scope)
    all_staff = await repo.list(skip=0, limit=10, metadata_scope=staff_scope)

    assert [item.title for item in first_page] == ["sales-auth-scope"]
    assert [item.title for item in all_staff] == [
        "sales-auth-scope",
        "sales-team-owned",
        "unscoped",
    ]
    assert await repo.count(metadata_scope=staff_scope) == 3

    leader_scope = OwnedMetadataScope(
        user_id="user-sales-lead-001",
        team_id="team-revenue",
        include_team_scope=True,
        allow_unscoped=True,
    )
    all_leader = await repo.list(skip=0, limit=10, metadata_scope=leader_scope)

    assert [item.title for item in all_leader] == [
        "sales-auth-scope",
        "sales-team-owned",
        "other-sales-user",
        "unscoped",
    ]
    assert await repo.count(metadata_scope=leader_scope) == 4


@pytest.mark.asyncio
async def test_conversation_repository_applies_metadata_scope_to_single_resource_crud(
    session,
) -> None:
    repo = SQLAlchemyConversationRepository(session)
    hidden = await repo.create(
        _conversation("hidden", 2, {"ownerUserId": "user-cs-001", "teamId": "team-service"})
    )
    visible = await repo.create(
        _conversation("visible", 1, {"ownerUserId": "user-sales-001", "teamId": "team-revenue"})
    )
    assert hidden.id is not None
    assert visible.id is not None

    scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=True,
    )

    assert await repo.get_by_id(hidden.id, metadata_scope=scope) is None
    visible_item = await repo.get_by_id(visible.id, metadata_scope=scope)
    assert visible_item is not None
    visible_item.update_title("visible-updated")
    updated = await repo.update(visible_item, metadata_scope=scope)

    assert updated.title == "visible-updated"
    hidden.title = "hidden-updated"
    with pytest.raises(ConversationNotFoundException):
        await repo.update(hidden, metadata_scope=scope)


@pytest.mark.asyncio
async def test_conversation_repository_rejects_unscoped_update_when_allow_unscoped_false(
    session,
) -> None:
    repo = SQLAlchemyConversationRepository(session)
    unscoped = await repo.create(_conversation("legacy-unscoped", 1, {}))
    unscoped.update_title("should-not-update")
    scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )

    with pytest.raises(ConversationNotFoundException):
        await repo.update(unscoped, metadata_scope=scope)

    persisted = await repo.get_by_id_for_maintenance(unscoped.id or 0)
    assert persisted is not None
    assert persisted.title == "legacy-unscoped"


@pytest.mark.asyncio
async def test_conversation_repository_requires_explicit_metadata_scope(session) -> None:
    repo = SQLAlchemyConversationRepository(session)
    conversation = await repo.create(
        _conversation(
            "explicit-scope",
            1,
            {"ownerUserId": "user-sales-001", "teamId": "team-revenue"},
        )
    )

    with pytest.raises(DomainValidationException):
        await repo.get_by_id(conversation.id, metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.list(metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.count(metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.update(conversation, metadata_scope=None)

    loaded = await repo.get_by_id_for_maintenance(conversation.id or 0)
    assert loaded is not None
    assert loaded.title == "explicit-scope"


@pytest.mark.asyncio
async def test_agent_config_repository_filters_metadata_scope_before_pagination(session) -> None:
    repo = SQLAlchemyAgentConfigRepository(session)
    await repo.create(
        _agent_config(
            "conflicting-hidden",
            6,
            {
                "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                "ownerUserId": "user-sales-001",
                "teamId": "team-revenue",
            },
        )
    )
    await repo.create(
        _agent_config(
            "hidden-newest",
            5,
            {"ownerUserId": "user-cs-001", "teamId": "team-service"},
        )
    )
    await repo.create(
        _agent_config(
            "sales-auth-scope",
            4,
            {"authScope": {"userId": "user-sales-001", "teamId": "team-revenue"}},
        )
    )
    await repo.create(_agent_config("sales-team-owned", 3, {"teamId": "team-revenue"}))
    await repo.create(
        _agent_config(
            "other-sales-user",
            2,
            {"ownerUserId": "user-peer-001", "teamId": "team-revenue"},
        )
    )
    await repo.create(_agent_config("unscoped", 1, {}))

    staff_scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )
    first_page = await repo.list(skip=0, limit=1, metadata_scope=staff_scope)
    all_staff = await repo.list(skip=0, limit=10, metadata_scope=staff_scope)

    assert [item.name for item in first_page] == ["sales-auth-scope"]
    assert [item.name for item in all_staff] == ["sales-auth-scope", "sales-team-owned"]
    assert await repo.count(metadata_scope=staff_scope) == 2

    leader_scope = OwnedMetadataScope(
        user_id="user-sales-lead-001",
        team_id="team-revenue",
        include_team_scope=True,
        allow_unscoped=False,
    )
    all_leader = await repo.list(skip=0, limit=10, metadata_scope=leader_scope)

    assert [item.name for item in all_leader] == [
        "sales-auth-scope",
        "sales-team-owned",
        "other-sales-user",
    ]
    assert await repo.count(metadata_scope=leader_scope) == 3


@pytest.mark.asyncio
async def test_agent_config_repository_applies_metadata_scope_to_single_resource_crud(
    session,
) -> None:
    repo = SQLAlchemyAgentConfigRepository(session)
    hidden = await repo.create(
        _agent_config("hidden", 2, {"ownerUserId": "user-cs-001", "teamId": "team-service"})
    )
    visible = await repo.create(
        _agent_config("visible", 1, {"ownerUserId": "user-sales-001", "teamId": "team-revenue"})
    )
    assert hidden.id is not None
    assert visible.id is not None

    scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )

    assert await repo.get_by_id(hidden.id, metadata_scope=scope) is None
    visible_item = await repo.get_by_id(visible.id, metadata_scope=scope)
    assert visible_item is not None
    visible_item.system_prompt = "updated"
    updated = await repo.update(visible_item, metadata_scope=scope)

    assert updated.system_prompt == "updated"
    with pytest.raises(AgentConfigNotFoundException):
        await repo.delete(hidden.id, metadata_scope=scope)
    await repo.delete(visible.id, metadata_scope=scope)
    assert await repo.get_by_id_for_maintenance(visible.id) is None


@pytest.mark.asyncio
async def test_agent_config_repository_get_by_name_applies_metadata_scope(session) -> None:
    repo = SQLAlchemyAgentConfigRepository(session)
    await repo.create(
        _agent_config("hidden-name", 2, {"ownerUserId": "user-cs-001", "teamId": "team-service"})
    )
    await repo.create(
        _agent_config("visible-name", 1, {"ownerUserId": "user-sales-001", "teamId": "team-revenue"})
    )
    scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )

    assert await repo.get_by_name("hidden-name", metadata_scope=scope) is None
    visible = await repo.get_by_name("visible-name", metadata_scope=scope)
    assert visible is not None
    assert visible.name == "visible-name"


@pytest.mark.asyncio
async def test_agent_config_repository_requires_explicit_metadata_scope(session) -> None:
    repo = SQLAlchemyAgentConfigRepository(session)
    config = await repo.create(
        _agent_config(
            "explicit-scope",
            1,
            {"ownerUserId": "user-sales-001", "teamId": "team-revenue"},
        )
    )

    with pytest.raises(DomainValidationException):
        await repo.get_by_id(config.id, metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.get_by_name(config.name, metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.list(metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.count(metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.update(config, metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await repo.delete(config.id, metadata_scope=None)

    loaded = await repo.get_by_id_for_maintenance(config.id or 0)
    assert loaded is not None
    assert loaded.name == "explicit-scope"


@pytest.mark.asyncio
async def test_agent_config_repository_round_trips_resource_bindings(session) -> None:
    repo = SQLAlchemyAgentConfigRepository(session)
    created = await repo.create(
        AgentConfig(
            id=None,
            name="bound-agent",
            system_prompt=None,
            model="gpt-test",
            tool_ids=(" crm.lookup ", "", "crm.lookup", "report.generate"),
            mcp_server_ids=(" crm ", "crm", "calendar"),
            metadata={"ownerUserId": "user-sales-001", "teamId": "team-revenue"},
            created_at=_at(1),
            updated_at=_at(1),
        )
    )
    assert created.id is not None

    scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )
    loaded = await repo.get_by_id(created.id, metadata_scope=scope)

    assert loaded is not None
    assert loaded.tool_ids == ("crm.lookup", "report.generate")
    assert loaded.mcp_server_ids == ("crm", "calendar")

    loaded.tool_ids = ("calendar.lookup", "calendar.lookup")
    loaded.mcp_server_ids = (" calendar ",)
    updated = await repo.update(loaded, metadata_scope=scope)

    assert updated.tool_ids == ("calendar.lookup",)
    assert updated.mcp_server_ids == ("calendar",)
