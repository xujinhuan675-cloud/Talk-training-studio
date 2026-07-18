from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from domain.conversation.entity import AgentConfig, Conversation
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
