from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.dto import ChatRequestDTO
from application.ports.llm import LLMMessage, LLMResponse
from application.services.chat_service import ChatApplicationService
from application.services.conversation_service import ConversationApplicationService
from domain.conversation.entity import Conversation, Message
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


class _FakeLLM:
    def __init__(self) -> None:
        self.calls: list[list[LLMMessage]] = []

    async def generate(self, messages, **_kwargs) -> LLMResponse:
        self.calls.append(list(messages))
        return LLMResponse(
            content="Assistant reply.",
            model="gpt-test",
            prompt_tokens=3,
            completion_tokens=4,
            total_tokens=7,
            finish_reason="stop",
        )

    async def stream(self, messages, **_kwargs):
        raise AssertionError("stream is not used in these tests")


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed_conversation(session_factory):
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(
                id=None,
                title="Message tree",
                system_prompt="Stay concise.",
                model="gpt-test",
            )
        )
        first_user = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="user",
                content="Root user turn.",
                branch_id="main",
            )
        )
        first_assistant = await uow.message_repository.create(
            first_user.create_child(role="assistant", content="Root assistant turn.")
        )
        off_path_user = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="user",
                content="Unrelated branch turn.",
                parent_message_id=first_user.public_id,
                branch_id="branch-unrelated",
            )
        )
        await uow.commit()
    return conversation, first_user, first_assistant, off_path_user


@pytest.mark.asyncio
async def test_chat_sync_uses_explicit_parent_message_path_for_llm_history(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    llm = _FakeLLM()
    service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )

    result = await service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Follow the selected branch.",
            parent_message_id=first_assistant.public_id,
            branch_id="branch-selected",
            stream=False,
        ),
    )

    assert [message.content for message in llm.calls[0]] == [
        "Stay concise.",
        "Root user turn.",
        "Root assistant turn.",
        "Follow the selected branch.",
    ]
    assert "Unrelated branch turn." not in [message.content for message in llm.calls[0]]
    assert result["message"]["parent_message_id"].startswith("msg_")
    assert result["message"]["branch_id"] == "branch-selected"

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        messages = await uow.message_repository.list_by_conversation(
            conversation.id,
            branch_id="branch-selected",
        )
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].parent_message_id == first_assistant.public_id
    assert messages[1].parent_message_id == messages[0].public_id
    assert off_path_user.public_id not in {message.public_id for message in messages}


@pytest.mark.asyncio
async def test_chat_sync_uses_branch_latest_when_parent_is_omitted(session_factory):
    conversation, first_user, _first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        branch_user = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="user",
                content="Branch seed.",
                parent_message_id=first_user.public_id,
                branch_id="branch-existing",
            )
        )
        await uow.commit()

    llm = _FakeLLM()
    service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )

    await service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Continue branch.",
            branch_id="branch-existing",
            stream=False,
        ),
    )

    assert [message.content for message in llm.calls[0]] == [
        "Stay concise.",
        "Root user turn.",
        "Branch seed.",
        "Continue branch.",
    ]
    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        latest = await uow.message_repository.get_latest_by_conversation(
            conversation.id,
            branch_id="branch-existing",
        )
    assert latest is not None
    assert latest.role == "assistant"
    assert latest.parent_message_id != branch_user.public_id


@pytest.mark.asyncio
async def test_conversation_service_returns_message_path_and_children(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    path = await service.get_message_path(conversation.id, first_assistant.public_id)
    children = await service.list_message_children(conversation.id, first_user.public_id)

    assert [message.content for message in path] == [
        "Root user turn.",
        "Root assistant turn.",
    ]
    assert {message.public_id for message in children} == {
        first_assistant.public_id,
        off_path_user.public_id,
    }
