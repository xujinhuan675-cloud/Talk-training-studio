from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.dto import (
    ChatRequestDTO,
    EditMessageDTO,
    ForkConversationDTO,
    MessageActionDTO,
    RetryMessageDTO,
)
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
        self.generate_kwargs: list[dict] = []

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
        self.generate_kwargs.append(dict(_kwargs))
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
async def test_chat_sync_propagates_request_runtime_selection_to_llm_and_metadata(
    session_factory,
):
    conversation, _first_user, first_assistant, _off_path_user = await _seed_conversation(
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
            message="Use the selected model.",
            parent_message_id=first_assistant.public_id,
            provider="openai",
            model="gpt-selected",
            model_spec="openai::https://openai.example/v1::responses::gpt-selected",
            metadata={
                "source": "training_room_selector",
                "llm": {
                    "provider": "metadata-provider",
                    "model": "metadata-model",
                    "model_spec": "metadata-spec",
                },
            },
            stream=False,
        ),
    )

    assert llm.generate_kwargs[0]["model"] == "gpt-selected"
    assert result["message"]["provider"] == "openai"
    assert result["message"]["model"] == "gpt-test"
    assert (
        result["message"]["metadata"]["model_spec"]
        == "openai::https://openai.example/v1::responses::gpt-selected"
    )
    assert result["message"]["metadata"]["source"] == "training_room_selector"
    assert result["message"]["metadata"]["runtime_selection"] == {
        "provider": "openai",
        "model": "gpt-selected",
        "model_spec": "openai::https://openai.example/v1::responses::gpt-selected",
        "source": "chat_request",
    }

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        messages = await uow.message_repository.list_by_conversation(
            conversation.id,
            branch_id="main",
        )
        runs = await uow.run_repository.list_by_conversation(conversation.id)

    user_message = messages[-2]
    assistant_message = messages[-1]
    assert user_message.provider == "openai"
    assert user_message.model == "gpt-selected"
    assert user_message.metadata["llm"]["model"] == "metadata-model"
    assert user_message.metadata["runtime_selection"]["model"] == "gpt-selected"
    assert runs[0].provider == "openai"
    assert runs[0].model == "gpt-selected"
    assert runs[0].metadata["model_spec"] == (
        "openai::https://openai.example/v1::responses::gpt-selected"
    )
    assert runs[0].metadata["runtime_selection"]["source"] == "chat_request"
    assert assistant_message.metadata["runtime_selection"]["model"] == "gpt-selected"


@pytest.mark.asyncio
async def test_chat_sync_uses_parent_message_runtime_metadata_when_request_omits_selection(
    session_factory,
):
    conversation, _first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        first_assistant.metadata = {
            "llm": {
                "provider": "anthropic",
                "model": "claude-selected",
                "model_spec": "anthropic::https://anthropic.example::messages::claude-selected",
            }
        }
        await uow.message_repository.update(first_assistant)
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
            message="Continue with the parent selection.",
            parent_message_id=first_assistant.public_id,
            stream=False,
        ),
    )

    assert llm.generate_kwargs[0]["model"] == "claude-selected"
    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        runs = await uow.run_repository.list_by_conversation(conversation.id)
        latest = await uow.message_repository.get_latest_by_conversation(conversation.id)

    assert runs[0].provider == "anthropic"
    assert runs[0].model == "claude-selected"
    assert runs[0].metadata["runtime_selection"]["source"] == "parent_message_metadata"
    assert latest is not None
    assert latest.metadata["model_spec"] == (
        "anthropic::https://anthropic.example::messages::claude-selected"
    )


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
async def test_chat_sync_keeps_superseded_ancestors_in_selected_branch_history(
    session_factory,
):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        first_user.mark_superseded()
        await uow.message_repository.update(first_user)
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
            message="Continue the visible old branch.",
            parent_message_id=first_assistant.public_id,
            stream=False,
        ),
    )

    assert [message.content for message in llm.calls[0]] == [
        "Stay concise.",
        "Root user turn.",
        "Root assistant turn.",
        "Continue the visible old branch.",
    ]


@pytest.mark.asyncio
async def test_chat_sync_omitted_parent_uses_latest_non_deleted_branch_message(
    session_factory,
):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        first_assistant.status = "deleted"
        await uow.message_repository.update(first_assistant)
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
            message="Continue after deleted tail.",
            branch_id="main",
            stream=False,
        ),
    )

    assert [message.content for message in llm.calls[0]] == [
        "Stay concise.",
        "Root user turn.",
        "Continue after deleted tail.",
    ]
    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        messages = await uow.message_repository.list_by_conversation(
            conversation.id,
            branch_id="main",
        )

    assert messages[-2].content == "Continue after deleted tail."
    assert messages[-2].parent_message_id == first_user.public_id


@pytest.mark.asyncio
async def test_chat_sync_rejects_selected_branch_with_inactive_ancestor(
    session_factory,
):
    conversation, _first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        leaf = await uow.message_repository.create(
            first_assistant.create_child(role="user", content="Leaf after deleted middle.")
        )
        middle = await uow.message_repository.get_by_public_id(first_assistant.public_id)
        assert middle is not None
        middle.status = "deleted"
        await uow.message_repository.update(middle)
        await uow.commit()

    llm = _FakeLLM()
    service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )

    with pytest.raises(ValueError, match="inactive message"):
        await service.send_message_sync(
            conversation.id,
            ChatRequestDTO(
                message="This path is disconnected.",
                parent_message_id=leaf.public_id,
                stream=False,
            ),
        )

    assert llm.calls == []


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
async def test_conversation_service_message_action_returns_tree_context_and_runtime_metadata(
    session_factory,
):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    first_user.provider = "openai"
    first_user.model = "gpt-4.1"
    first_user.metadata = {
        "provider": "openai",
        "model": "gpt-4.1",
        "model_spec": "openai::https://openai.example/v1::responses::gpt-4.1",
        "runtime_selection": {
            "provider": "openai",
            "model": "gpt-4.1",
            "model_spec": "openai::https://openai.example/v1::responses::gpt-4.1",
            "source": "chat_request",
        },
    }
    first_assistant.provider = "anthropic"
    first_assistant.model = "claude-sonnet"
    first_assistant.metadata = {
        "provider": "anthropic",
        "model": "claude-sonnet",
        "model_spec": "anthropic::https://anthropic.example::messages::claude-sonnet",
    }
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        await uow.message_repository.update(first_user)
        await uow.message_repository.update(first_assistant)
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    edit_result = await service.apply_message_action(
        conversation.id,
        first_user.public_id,
        MessageActionDTO(
            action="edit",
            content="Edited root user turn.",
            metadata={"reason": "training correction"},
        ),
    )
    retry_result = await service.apply_message_action(
        conversation.id,
        first_assistant.public_id,
        MessageActionDTO(action="retry", content="Retry assistant turn."),
    )

    assert edit_result.action == "edit"
    assert edit_result.message is not None
    assert edit_result.message.provider == "openai"
    assert edit_result.message.model == "gpt-4.1"
    assert edit_result.message.metadata["edit_of"] == first_user.public_id
    assert edit_result.message.metadata["reason"] == "training correction"
    assert edit_result.message.metadata["model_spec"] == (
        "openai::https://openai.example/v1::responses::gpt-4.1"
    )
    assert edit_result.message.metadata["runtime_selection"]["source"] == "chat_request"
    assert [message.public_id for message in edit_result.path] == [
        edit_result.message.public_id
    ]
    assert {message.public_id for message in edit_result.siblings} == {
        first_user.public_id,
        edit_result.message.public_id,
    }
    assert edit_result.children == []

    assert retry_result.action == "retry"
    assert retry_result.message is not None
    assert retry_result.message.provider == "anthropic"
    assert retry_result.message.model == "claude-sonnet"
    assert retry_result.message.metadata["retry_of"] == first_assistant.public_id
    assert retry_result.message.metadata["model_spec"] == (
        "anthropic::https://anthropic.example::messages::claude-sonnet"
    )
    assert [message.public_id for message in retry_result.path] == [
        first_user.public_id,
        retry_result.message.public_id,
    ]
    assert {message.public_id for message in retry_result.siblings} == {
        first_assistant.public_id,
        off_path_user.public_id,
        retry_result.message.public_id,
    }


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
async def test_conversation_service_fork_remaps_selected_path_metadata(session_factory):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation.metadata = {
            "selectedPath": {
                "branchId": first_assistant.branch_id,
                "tailMessageId": first_assistant.public_id,
                "messageIds": [
                    first_user.public_id,
                    first_assistant.public_id,
                    off_path_user.public_id,
                ],
                "purpose": "training_replay_context",
                "replayContextOnly": True,
                "affectsScoring": False,
                "affectsCompletion": False,
            },
            "currentBranchTail": {
                "branchId": off_path_user.branch_id,
                "messageId": off_path_user.public_id,
            },
            "messageTreeSelection": {
                "selectedMessageId": first_assistant.public_id,
                "path": [
                    {"publicId": first_user.public_id, "role": "user"},
                    {
                        "publicId": first_assistant.public_id,
                        "parentMessageId": first_user.public_id,
                        "role": "assistant",
                    },
                    {"publicId": off_path_user.public_id, "role": "user"},
                ],
                "affectsScoring": False,
                "affectsCompletion": False,
            },
        }
        await uow.conversation_repository.update(conversation)

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    result = await service.fork_conversation(
        conversation.id,
        first_assistant.public_id,
        ForkConversationDTO(option="directPath", statuses=["active"]),
    )

    copied_by_source = result.source_to_forked_id
    metadata = result.conversation.metadata
    assert set(copied_by_source) == {first_user.public_id, first_assistant.public_id}
    assert metadata["selectedPath"]["tailMessageId"] == copied_by_source[
        first_assistant.public_id
    ]
    assert metadata["selectedPath"]["messageIds"] == [
        copied_by_source[first_user.public_id],
        copied_by_source[first_assistant.public_id],
    ]
    assert metadata["selectedPath"]["affectsScoring"] is False
    assert metadata["selectedPath"]["affectsCompletion"] is False
    assert metadata["currentBranchTail"]["messageId"] is None
    assert metadata["messageTreeSelection"]["selectedMessageId"] == copied_by_source[
        first_assistant.public_id
    ]
    assert [item["publicId"] for item in metadata["messageTreeSelection"]["path"]] == [
        copied_by_source[first_user.public_id],
        copied_by_source[first_assistant.public_id],
    ]
    assert metadata["messageTreeSelection"]["path"][1]["parentMessageId"] == copied_by_source[
        first_user.public_id
    ]
    assert metadata["messageTreeSelection"]["affectsScoring"] is False
    assert metadata["messageTreeSelection"]["affectsCompletion"] is False


@pytest.mark.asyncio
async def test_conversation_service_message_action_fork_returns_forked_context(
    session_factory,
):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    result = await service.apply_message_action(
        conversation.id,
        first_assistant.public_id,
        MessageActionDTO(
            action="fork",
            title="Action fork",
            option="directPath",
            metadata={"source": "training_action"},
        ),
    )

    assert result.action == "fork"
    assert result.conversation is not None
    assert result.conversation.id != conversation.id
    assert result.conversation.title == "Action fork"
    assert result.conversation.metadata["source"] == "training_action"
    assert result.message is not None
    assert result.source_to_forked_id[first_assistant.public_id] == result.message.public_id
    assert set(result.source_to_forked_id) == {
        first_user.public_id,
        first_assistant.public_id,
    }
    path_ids = [message.public_id for message in result.path]
    assert path_ids == [
        result.source_to_forked_id[first_user.public_id],
        result.source_to_forked_id[first_assistant.public_id],
    ]
    assert [message.public_id for message in result.messages] == path_ids


@pytest.mark.asyncio
async def test_librechat_message_tree_acceptance_matrix_keeps_selected_paths(
    session_factory,
):
    conversation, first_user, first_assistant, _off_path_user = await _seed_conversation(
        session_factory
    )
    llm = _FakeLLM()
    chat_service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )
    tree_service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    regenerate_result = await tree_service.apply_message_action(
        conversation.id,
        first_assistant.public_id,
        MessageActionDTO(
            action="retry",
            content="Regenerated assistant answer.",
            metadata={"acceptance_case": "regenerate"},
        ),
    )
    regenerated = regenerate_result.message
    assert regenerated is not None
    assert regenerated.metadata["retry_of"] == first_assistant.public_id
    assert [message.public_id for message in regenerate_result.path] == [
        first_user.public_id,
        regenerated.public_id,
    ]
    assert {message.public_id for message in regenerate_result.siblings} >= {
        first_assistant.public_id,
        regenerated.public_id,
    }

    first_continue = await chat_service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Continue from the regenerated answer.",
            parent_message_id=regenerated.public_id,
            branch_id=regenerated.branch_id,
            stream=False,
        ),
    )
    assert [message.content for message in llm.calls[-1]] == [
        "Stay concise.",
        "Root user turn.",
        "Regenerated assistant answer.",
        "Continue from the regenerated answer.",
    ]
    first_continue_tail = first_continue["message"]["public_id"]
    reloaded_path = await tree_service.get_message_path(conversation.id, first_continue_tail)
    assert [message.content for message in reloaded_path] == [
        "Root user turn.",
        "Regenerated assistant answer.",
        "Continue from the regenerated answer.",
        "Assistant reply.",
    ]
    assert "Root assistant turn." not in [message.content for message in reloaded_path]

    branch_search_results = await tree_service.search_messages(
        conversation.id,
        "Regenerated assistant",
        branch_id=regenerated.branch_id,
        include_path=True,
        context_before=1,
        context_after=2,
    )
    assert [result.message.public_id for result in branch_search_results] == [
        regenerated.public_id
    ]
    branch_search_result = branch_search_results[0]
    assert [message.public_id for message in branch_search_result.path] == [
        first_user.public_id,
        regenerated.public_id,
    ]
    assert [message.branch_id for message in branch_search_result.path] == [
        first_user.branch_id,
        regenerated.branch_id,
    ]
    assert [message.content for message in branch_search_result.context] == [
        "Root user turn.",
        "Regenerated assistant answer.",
        "Continue from the regenerated answer.",
        "Assistant reply.",
    ]
    assert {message.branch_id for message in branch_search_result.context[1:]} == {
        regenerated.branch_id
    }
    assert first_assistant.public_id not in {
        message.public_id
        for message in branch_search_result.path + branch_search_result.context
    }

    edited_result = await tree_service.apply_message_action(
        conversation.id,
        first_user.public_id,
        MessageActionDTO(action="edit", content="Edited root user turn."),
    )
    edited = edited_result.message
    assert edited is not None
    assert edited.metadata["edit_of"] == first_user.public_id
    assert [message.public_id for message in edited_result.path] == [edited.public_id]

    await chat_service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Follow the edited branch.",
            parent_message_id=edited.public_id,
            branch_id=edited.branch_id,
            stream=False,
        ),
    )
    assert [message.content for message in llm.calls[-1]] == [
        "Stay concise.",
        "Edited root user turn.",
        "Follow the edited branch.",
    ]

    fork_result = await tree_service.apply_message_action(
        conversation.id,
        regenerated.public_id,
        MessageActionDTO(
            action="fork",
            title="Fork regenerated path",
            option="directPath",
            metadata={"review_mode": "branch"},
        ),
    )
    assert fork_result.conversation is not None
    assert fork_result.conversation.id != conversation.id
    assert fork_result.conversation.metadata["fork_option"] == "directPath"
    assert fork_result.conversation.metadata["review_mode"] == "branch"
    assert set(fork_result.source_to_forked_id) == {
        first_user.public_id,
        regenerated.public_id,
    }
    assert [message.public_id for message in fork_result.path] == [
        fork_result.source_to_forked_id[first_user.public_id],
        fork_result.source_to_forked_id[regenerated.public_id],
    ]

    await chat_service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Continue after reload.",
            parent_message_id=reloaded_path[-1].public_id,
            branch_id=reloaded_path[-1].branch_id,
            stream=False,
        ),
    )
    assert [message.content for message in llm.calls[-1]] == [
        "Stay concise.",
        "Root user turn.",
        "Regenerated assistant answer.",
        "Continue from the regenerated answer.",
        "Assistant reply.",
        "Continue after reload.",
    ]


@pytest.mark.asyncio
async def test_search_locations_preserve_edited_branch_replay_metadata_context(
    session_factory,
):
    conversation, first_user, first_assistant, off_path_user = await _seed_conversation(
        session_factory
    )
    replay_metadata = {
        "branchPolicy": {
            "owner": "training_core",
            "selectedPathPurpose": "training_replay_context",
        },
        "selectedPath": {
            "branchId": "metadata-shadow-branch",
            "tailMessageId": "metadata-shadow-tail",
            "messageIds": ["metadata-shadow-root", "metadata-shadow-tail"],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "currentBranchTail": {
            "branchId": "metadata-shadow-branch",
            "messageId": "metadata-shadow-tail",
        },
    }
    llm = _FakeLLM()
    chat_service = ChatApplicationService(
        uow_factory=lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        ),
        llm=llm,
    )
    tree_service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    edited_result = await tree_service.apply_message_action(
        conversation.id,
        first_user.public_id,
        MessageActionDTO(
            action="edit",
            content="Edited root user turn with needle-edited-search.",
            metadata=replay_metadata,
        ),
    )
    edited = edited_result.message
    assert edited is not None
    assert edited.branch_id != "metadata-shadow-branch"
    assert edited.metadata["selectedPath"]["affectsScoring"] is False
    assert edited.metadata["selectedPath"]["affectsCompletion"] is False

    edited_continue = await chat_service.send_message_sync(
        conversation.id,
        ChatRequestDTO(
            message="Follow the edited search branch.",
            parent_message_id=edited.public_id,
            branch_id=edited.branch_id,
            model="runtime-edited-model",
            metadata=replay_metadata,
            stream=False,
        ),
    )
    edited_tail = edited_continue["message"]["public_id"]
    edited_path = await tree_service.get_message_path(conversation.id, edited_tail)
    edited_user = edited_path[-2]

    edited_results = await tree_service.search_messages(
        conversation.id,
        "needle-edited-search",
        branch_id=edited.branch_id,
        include_path=True,
        context_before=1,
        context_after=1,
    )
    assert [result.message.public_id for result in edited_results] == [edited.public_id]
    assert [message.public_id for message in edited_results[0].path] == [edited.public_id]
    assert [message.branch_id for message in edited_results[0].path] == [edited.branch_id]
    assert [message.public_id for message in edited_results[0].context] == [
        edited.public_id,
        edited_user.public_id,
    ]
    assert [message.branch_id for message in edited_results[0].context] == [
        edited.branch_id,
        edited.branch_id,
    ]
    edited_excluded_ids = {
        first_user.public_id,
        first_assistant.public_id,
        off_path_user.public_id,
    }
    edited_location_ids = {
        message.public_id for message in edited_results[0].path + edited_results[0].context
    }
    assert edited_excluded_ids.isdisjoint(edited_location_ids)
    assert llm.generate_kwargs[-1]["model"] == "runtime-edited-model"
    assert edited_continue["run"]["completion_tokens"] == 4
    assert (
        edited_continue["run"]["metadata"]["selectedPath"]["purpose"]
        == "training_replay_context"
    )


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


@pytest.mark.asyncio
async def test_conversation_service_fork_preserves_parent_before_child_order(
    session_factory,
):
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(
                id=None,
                title="Out-of-order source",
                system_prompt=None,
                model="gpt-test",
            )
        )
        parent = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="user",
                content="Parent created later.",
                branch_id="main",
                created_at=base_time + timedelta(seconds=10),
            )
        )
        child = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=conversation.id,
                role="assistant",
                content="Child created earlier.",
                parent_message_id=parent.public_id,
                branch_id="main",
                created_at=base_time,
            )
        )
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    result = await service.fork_conversation(
        conversation.id,
        child.public_id,
        ForkConversationDTO(option="directPath"),
    )

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        forked_messages = await uow.message_repository.list_by_conversation(
            result.conversation.id,
        )

    assert [message.content for message in forked_messages] == [
        "Parent created later.",
        "Child created earlier.",
    ]
    assert forked_messages[1].created_at > forked_messages[0].created_at
