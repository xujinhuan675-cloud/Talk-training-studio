from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.dto import ChatRequestDTO, EditMessageDTO, ForkConversationDTO, RetryMessageDTO
from application.ports.llm import LLMMessage, LLMProviderMetadata, LLMResponse
from application.services.chat_service import ChatApplicationService
from application.services.conversation_service import ConversationApplicationService
from domain.conversation.entity import Conversation, Message
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


class _FakeLLM:
    def __init__(self) -> None:
        self.provider = "fake-provider"
        self.calls: list[list[LLMMessage]] = []

    @property
    def provider_metadata(self) -> LLMProviderMetadata:
        return LLMProviderMetadata(
            provider=self.provider,
            default_model="gpt-test",
            endpoint="https://fake.example/v1",
            wire_api="chat_completions",
            max_retries=2,
        )

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


class _FailingLLM(_FakeLLM):
    async def generate(self, messages, **_kwargs) -> LLMResponse:
        self.calls.append(list(messages))
        exc = TimeoutError("provider timed out")
        raise exc


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
    assert result["message"]["provider"] == "fake-provider"
    assert result["message"]["metadata"]["provider"] == "fake-provider"
    assert result["message"]["metadata"]["model"] == "gpt-test"
    assert (
        result["message"]["metadata"]["provider_metadata"]["endpoint"]
        == "https://fake.example/v1"
    )

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        messages = await uow.message_repository.list_by_conversation(
            conversation.id,
            branch_id="branch-selected",
        )
        runs = await uow.run_repository.list_by_conversation(conversation.id)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].parent_message_id == first_assistant.public_id
    assert messages[0].provider == "fake-provider"
    assert messages[0].metadata["provider"] == "fake-provider"
    assert messages[0].metadata["provider_metadata"]["endpoint"] == "https://fake.example/v1"
    assert messages[1].parent_message_id == messages[0].public_id
    assert runs[0].provider == "fake-provider"
    assert runs[0].model == "gpt-test"
    assert runs[0].metadata["trigger_message_id"] == messages[0].public_id
    assert runs[0].metadata["branch_id"] == "branch-selected"
    assert runs[0].metadata["provider_metadata"]["wire_api"] == "chat_completions"
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
async def test_chat_sync_respects_history_limit(session_factory):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        second_user = await uow.message_repository.create(
            first_assistant.create_child(role="user", content="Second user turn.")
        )
        second_assistant = await uow.message_repository.create(
            second_user.create_child(role="assistant", content="Second assistant turn.")
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
            message="Only keep the recent window.",
            parent_message_id=second_assistant.public_id,
            history_limit=2,
            stream=False,
        ),
    )

    assert [message.content for message in llm.calls[0]] == [
        "Stay concise.",
        "Second assistant turn.",
        "Only keep the recent window.",
    ]


@pytest.mark.asyncio
async def test_chat_sync_failure_marks_run_retryable(session_factory):
    conversation, *_ = await _seed_conversation(session_factory)
    llm = _FailingLLM()
    service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )

    with pytest.raises(Exception):
        await service.send_message_sync(
            conversation.id,
            ChatRequestDTO(message="This will fail.", stream=False),
        )

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        runs = await uow.run_repository.list_by_conversation(conversation.id)

    assert runs[0].status == "failed"
    assert runs[0].error_message == "provider timed out"
    assert runs[0].metadata["error_type"] == "TimeoutError"
    assert runs[0].metadata["retryable"] is True
    assert runs[0].metadata["trigger_message_id"].startswith("msg_")


@pytest.mark.asyncio
async def test_conversation_service_reads_branch_path_and_search_locations(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    path = await service.get_message_path(conversation.id, off_path_user.public_id)
    location = await service.locate_message(
        conversation.id,
        first_assistant.public_id,
        before=1,
        after=1,
    )
    branch_location = await service.locate_message(
        conversation.id,
        off_path_user.public_id,
        before=1,
        after=0,
    )
    search_results = await service.search_messages(
        conversation.id,
        "assistant turn",
        branch_id="main",
    )

    assert [message.content for message in path] == [
        "Root user turn.",
        "Unrelated branch turn.",
    ]
    assert [message.content for message in location.path] == [
        "Root user turn.",
        "Root assistant turn.",
    ]
    assert [message.public_id for message in location.context] == [
        first_user.public_id,
        first_assistant.public_id,
    ]
    assert [message.public_id for message in branch_location.context] == [
        first_user.public_id,
        off_path_user.public_id,
    ]
    assert [result.message.public_id for result in search_results] == [first_assistant.public_id]
    assert [message.public_id for message in search_results[0].path] == [
        first_user.public_id,
        first_assistant.public_id,
    ]
    assert [message.public_id for message in search_results[0].context] == [
        first_user.public_id,
        first_assistant.public_id,
    ]


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


@pytest.mark.asyncio
async def test_conversation_service_creates_edit_and_retry_branches(session_factory):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    edited = await service.edit_message(
        conversation.id,
        first_user.public_id,
        EditMessageDTO(content="Edited root user turn.", metadata={"reason": "clarity"}),
    )
    retry = await service.retry_message(
        conversation.id,
        first_assistant.public_id,
        RetryMessageDTO(content="Retry assistant turn.", metadata={"temperature": 0.1}),
    )

    assert edited.parent_message_id == first_user.parent_message_id
    assert edited.branch_id.startswith("branch_")
    assert edited.metadata["edit_of"] == first_user.public_id
    assert edited.metadata["reason"] == "clarity"
    assert retry.parent_message_id == first_assistant.parent_message_id
    assert retry.branch_id.startswith("branch_")
    assert retry.metadata["retry_of"] == first_assistant.public_id
    assert retry.metadata["temperature"] == 0.1

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        original_user = await uow.message_repository.get_by_public_id(first_user.public_id)
        original_assistant = await uow.message_repository.get_by_public_id(
            first_assistant.public_id
        )
        edited_path = await uow.message_repository.list_path_to_message(
            conversation.id,
            edited.public_id,
        )
        retry_path = await uow.message_repository.list_path_to_message(
            conversation.id,
            retry.public_id,
        )

    assert original_user.status == "superseded"
    assert original_assistant.status == "superseded"
    assert [message.public_id for message in edited_path] == [edited.public_id]
    assert [message.public_id for message in retry_path] == [first_user.public_id, retry.public_id]


@pytest.mark.asyncio
async def test_conversation_service_forks_message_tree_with_remapped_parents(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    result = await service.fork_conversation(
        conversation.id,
        first_assistant.public_id,
        ForkConversationDTO(
            title="Forked tree",
            option="includeBranches",
            statuses=["active"],
            metadata={"reason": "branch review"},
        ),
    )

    assert result.conversation.id != conversation.id
    assert result.conversation.title == "Forked tree"
    assert result.conversation.metadata["forked_from_conversation_id"] == conversation.id
    assert result.conversation.metadata["forked_from_message_id"] == first_assistant.public_id
    assert result.conversation.metadata["fork_option"] == "includeBranches"
    assert result.conversation.metadata["reason"] == "branch review"

    copied_by_source = result.source_to_forked_id
    assert set(copied_by_source) == {
        first_user.public_id,
        first_assistant.public_id,
        off_path_user.public_id,
    }
    assert all(source_id != forked_id for source_id, forked_id in copied_by_source.items())

    copied_messages = {message.public_id: message for message in result.messages}
    copied_root = copied_messages[copied_by_source[first_user.public_id]]
    copied_assistant = copied_messages[copied_by_source[first_assistant.public_id]]
    copied_branch = copied_messages[copied_by_source[off_path_user.public_id]]

    assert copied_root.parent_message_id is None
    assert copied_assistant.parent_message_id == copied_root.public_id
    assert copied_branch.parent_message_id == copied_root.public_id
    assert copied_assistant.metadata["forked_from_message_id"] == first_assistant.public_id

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        forked_path = await uow.message_repository.list_path_to_message(
            result.conversation.id,
            copied_assistant.public_id,
        )

    assert [message.public_id for message in forked_path] == [
        copied_root.public_id,
        copied_assistant.public_id,
    ]


@pytest.mark.asyncio
async def test_conversation_service_fork_direct_path_excludes_siblings(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    result = await service.fork_conversation(
        conversation.id,
        off_path_user.public_id,
        ForkConversationDTO(option="directPath"),
    )

    assert set(result.source_to_forked_id) == {
        first_user.public_id,
        off_path_user.public_id,
    }
    assert first_assistant.public_id not in result.source_to_forked_id
