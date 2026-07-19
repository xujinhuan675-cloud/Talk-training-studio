from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.dependencies import get_conversation_service
from api.routes.conversations import router
from application.dto import (
    ConversationDTO,
    EditMessageDTO,
    ForkConversationDTO,
    MessageDTO_Agent,
    RetryMessageDTO,
)
from application.services.conversation_service import ConversationApplicationService
from core.exceptions import register_exception_handlers
from domain.conversation.entity import Conversation, Message
from domain.conversation.exceptions import MessageNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from shared.codes import BusinessCode


def _metadata() -> dict:
    return {
        "ownerUserId": "user-sales-001",
        "teamId": "team-revenue",
        "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
    }


def _scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


def _message(content: str, public_id: str = "msg_1") -> MessageDTO_Agent:
    return MessageDTO_Agent(
        id=1,
        conversation_id=7,
        role="assistant",
        content=content,
        public_id=public_id,
        parent_message_id=None,
        branch_id="main",
        status="active",
        created_at=datetime.now(timezone.utc),
    )


def _conversation(conversation_id: int = 7) -> ConversationDTO:
    now = datetime.now(timezone.utc)
    return ConversationDTO(
        id=conversation_id,
        title="Conversation",
        system_prompt=None,
        model="gpt-test",
        status="active",
        metadata={},
        created_at=now,
        updated_at=now,
    )


class _FakeActionService:
    def __init__(self) -> None:
        self.action_call = None
        self.retry_call = None

    async def get_message_path(self, conversation_id: int, message_public_id: str, **kwargs):
        raise MessageNotFoundException()

    async def get_conversation(self, conversation_id: int, **kwargs):
        return _conversation(conversation_id=conversation_id)

    async def apply_message_action(self, conversation_id: int, message_public_id: str, payload, **kwargs):
        self.action_call = (conversation_id, message_public_id, payload, kwargs)
        return None

    async def retry_message(
        self,
        conversation_id: int,
        message_public_id: str,
        payload: RetryMessageDTO,
        **kwargs,
    ):
        self.retry_call = (conversation_id, message_public_id, payload, kwargs)
        return _message(payload.content, public_id="msg_retry")


def _client(service: _FakeActionService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_exception_handlers(app)
    app.dependency_overrides[get_conversation_service] = lambda: service
    return TestClient(app)


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


def test_message_action_route_returns_business_404_for_missing_message() -> None:
    service = _FakeActionService()
    client = _client(service)

    response = client.get("/api/v1/conversations/7/messages/msg_missing/path")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == int(BusinessCode.MESSAGE_NOT_FOUND)
    assert body["data"] is None
    assert body["error"]["type"] == "MessageNotFound"


def test_retry_message_route_accepts_empty_payload_default_content() -> None:
    service = _FakeActionService()
    client = _client(service)

    response = client.post("/api/v1/conversations/7/messages/msg_answer/retry", json={})

    assert response.status_code == 200
    assert response.json()["data"]["content"] == ""
    assert service.retry_call[0:2] == (7, "msg_answer")
    assert service.retry_call[2].content == ""


def test_message_action_route_rejects_edit_without_content() -> None:
    service = _FakeActionService()
    client = _client(service)

    response = client.post(
        "/api/v1/conversations/7/messages/msg_answer/actions",
        json={"action": "edit"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "ValidationError"
    assert service.action_call is None


@pytest.mark.asyncio
async def test_search_deleted_status_returns_locatable_path_and_context(session_factory) -> None:
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        conversation = await uow.conversation_repository.create(
            Conversation(id=None, title="Deleted search", metadata=_metadata())
        )
        root = await uow.message_repository.create(
            Message(id=None, conversation_id=conversation.id, role="user", content="root")
        )
        deleted = await uow.message_repository.create(
            root.create_child(role="assistant", content="needle deleted answer")
        )
        deleted.status = "deleted"
        deleted = await uow.message_repository.update(deleted)
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    results = await service.search_messages(
        conversation.id,
        "needle",
        statuses=[" deleted ", ""],
        context_before=1,
        context_after=0,
        metadata_scope=_scope(),
    )

    assert [result.message.public_id for result in results] == [deleted.public_id]
    assert [message.public_id for message in results[0].path] == [
        root.public_id,
        deleted.public_id,
    ]
    assert [message.public_id for message in results[0].context] == [
        root.public_id,
        deleted.public_id,
    ]


@pytest.mark.asyncio
async def test_message_actions_reject_public_id_from_another_conversation(
    session_factory,
) -> None:
    async with SQLAlchemyUnitOfWork(session_factory=session_factory) as uow:
        requested_conversation = await uow.conversation_repository.create(
            Conversation(id=None, title="Requested", metadata=_metadata())
        )
        other_conversation = await uow.conversation_repository.create(
            Conversation(id=None, title="Other", metadata=_metadata())
        )
        other_message = await uow.message_repository.create(
            Message(
                id=None,
                conversation_id=other_conversation.id,
                role="user",
                content="other",
            )
        )
        await uow.commit()

    service = ConversationApplicationService(
        lambda **kwargs: SQLAlchemyUnitOfWork(
            session_factory=session_factory,
            **kwargs,
        )
    )

    with pytest.raises(MessageNotFoundException):
        await service.get_message_path(
            requested_conversation.id,
            other_message.public_id,
            metadata_scope=_scope(),
        )
    with pytest.raises(MessageNotFoundException):
        await service.list_message_children(
            requested_conversation.id,
            other_message.public_id,
            metadata_scope=_scope(),
        )
    with pytest.raises(MessageNotFoundException):
        await service.edit_message(
            requested_conversation.id,
            other_message.public_id,
            EditMessageDTO(content="edit"),
            metadata_scope=_scope(),
        )
    with pytest.raises(MessageNotFoundException):
        await service.retry_message(
            requested_conversation.id,
            other_message.public_id,
            RetryMessageDTO(),
            metadata_scope=_scope(),
        )
    with pytest.raises(MessageNotFoundException):
        await service.fork_conversation(
            requested_conversation.id,
            other_message.public_id,
            ForkConversationDTO(),
            metadata_scope=_scope(),
        )
