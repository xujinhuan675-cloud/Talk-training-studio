from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from domain.conversation.entity import Conversation, Message, Run
from infrastructure.models.base import Base
from infrastructure.repositories.conversation_repository import SQLAlchemyConversationRepository
from infrastructure.repositories.message_repository import SQLAlchemyMessageRepository
from infrastructure.repositories.run_repository import SQLAlchemyRunRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        yield db

    await engine.dispose()


@pytest.mark.asyncio
async def test_message_domain_creates_parent_child_and_branch_semantics() -> None:
    root = Message(id=None, conversation_id=1, role="user", content="Draft")
    child = root.create_child(
        role="assistant",
        content="Answer",
        finish_reason="stop",
        provider="openai",
        model="gpt-test",
        content_parts=[{"type": "text", "text": "Answer"}],
    )
    edit = root.create_edit(content="Edited draft")
    retry = child.create_retry(content="Retry")
    root.mark_superseded()

    assert root.public_id.startswith("msg_")
    assert child.is_child_of(root)
    assert child.branch_id == root.branch_id
    assert child.finish_reason == "stop"
    assert child.content_parts == [{"type": "text", "text": "Answer"}]
    assert edit.metadata["edit_of"] == root.public_id
    assert edit.branch_id.startswith("branch_")
    assert retry.metadata["retry_of"] == child.public_id
    assert root.status == "superseded"


@pytest.mark.asyncio
async def test_message_repository_persists_tree_fields_and_queries_children(session) -> None:
    conv_repo = SQLAlchemyConversationRepository(session)
    msg_repo = SQLAlchemyMessageRepository(session)

    conv = await conv_repo.create(
        Conversation(id=None, title="Tree", system_prompt=None, model="gpt-test")
    )
    root = await msg_repo.create(
        Message(
            id=None,
            conversation_id=conv.id,
            role="user",
            content="hello",
            branch_id="main",
            content_parts=[{"type": "text", "text": "hello"}],
        )
    )
    assistant = await msg_repo.create(
        root.create_child(
            role="assistant",
            content="world",
            provider="openai",
            model="gpt-test",
            finish_reason="stop",
        )
    )
    sibling = await msg_repo.create(root.create_child(role="assistant", content="alternate"))
    sibling.branch_id = "branch-alt"
    sibling = await msg_repo.update(sibling)

    by_public_id = await msg_repo.get_by_public_id(root.public_id)
    latest = await msg_repo.get_latest_by_conversation(conv.id, branch_id="main")
    children = await msg_repo.list_children(root.public_id)
    main_messages = await msg_repo.list_by_conversation(conv.id, branch_id="main")

    assert by_public_id.id == root.id
    assert latest.public_id == assistant.public_id
    assert [m.public_id for m in children] == [assistant.public_id, sibling.public_id]
    assert [m.public_id for m in main_messages] == [root.public_id, assistant.public_id]
    assert assistant.parent_message_id == root.public_id
    assert assistant.provider == "openai"
    assert assistant.model == "gpt-test"
    assert assistant.finish_reason == "stop"
    assert root.content_parts == [{"type": "text", "text": "hello"}]


@pytest.mark.asyncio
async def test_run_repository_persists_public_provider_finish_and_metadata(session) -> None:
    conv_repo = SQLAlchemyConversationRepository(session)
    run_repo = SQLAlchemyRunRepository(session)

    conv = await conv_repo.create(Conversation(id=None, title="Run", model="gpt-test"))
    run = await run_repo.create(
        Run(
            id=None,
            conversation_id=conv.id,
            provider="openai",
            model="gpt-test",
            metadata={"trigger_message_id": "msg_1"},
        )
    )
    run.mark_completed(
        prompt_tokens=2,
        completion_tokens=3,
        total_tokens=5,
        finish_reason="stop",
    )
    updated = await run_repo.update(run)

    assert updated.public_id.startswith("run_")
    assert updated.provider == "openai"
    assert updated.finish_reason == "stop"
    assert updated.metadata == {"trigger_message_id": "msg_1"}
    assert updated.total_tokens == 5
