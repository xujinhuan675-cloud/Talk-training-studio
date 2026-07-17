from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_chat_service, get_conversation_service
from api.routes.chat import router as chat_router
from api.routes.conversations import router as conversation_router
from application.dto import ConversationDTO


def _conversation(
    conversation_id: int,
    *,
    metadata: dict | None = None,
) -> ConversationDTO:
    now = datetime.now(timezone.utc)
    return ConversationDTO(
        id=conversation_id,
        title="Scoped conversation",
        system_prompt=None,
        model="gpt-test",
        status="active",
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


class _FakeConversationService:
    def __init__(self, conversations: dict[int, ConversationDTO] | None = None) -> None:
        self.conversations = conversations or {}
        self.created_payload = None
        self.search_call = None
        self.get_calls: list[int] = []

    async def create_conversation(self, payload):
        self.created_payload = payload
        return _conversation(21, metadata=payload.metadata)

    async def get_conversation(self, conversation_id: int):
        self.get_calls.append(conversation_id)
        return self.conversations.get(conversation_id) or _conversation(conversation_id)

    async def search_messages(self, conversation_id: int, query: str, **kwargs):
        self.search_call = (conversation_id, query, kwargs)
        return []


class _FakeChatService:
    def __init__(self) -> None:
        self.sync_call = None
        self.stream_call = None

    async def send_message_sync(self, conversation_id: int, payload):
        self.sync_call = (conversation_id, payload)
        return {"message_id": 1, "content": "ok"}

    async def send_message_stream(self, conversation_id: int, payload):
        self.stream_call = (conversation_id, payload)
        yield "event: done\ndata: {}\n\n"


def _client(
    conversation_service: _FakeConversationService,
    chat_service: _FakeChatService | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(conversation_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    if chat_service is not None:
        app.dependency_overrides[get_chat_service] = lambda: chat_service
    return TestClient(app)


def test_create_conversation_stamps_current_mock_user_scope() -> None:
    conversation_service = _FakeConversationService()
    client = _client(conversation_service)

    response = client.post(
        "/api/v1/conversations",
        headers={"X-Mock-User": "sales"},
        json={
            "title": "Sales branch",
            "metadata": {
                "ownerUserId": "user-cs-001",
                "teamId": "team-service",
                "source": "test",
            },
        },
    )

    assert response.status_code == 200
    metadata = response.json()["data"]["metadata"]
    assert metadata["ownerUserId"] == "user-sales-001"
    assert metadata["teamId"] == "team-revenue"
    assert metadata["authScope"]["userId"] == "user-sales-001"
    assert metadata["authScope"]["teamId"] == "team-revenue"
    assert metadata["source"] == "test"
    assert conversation_service.created_payload.metadata["ownerUserId"] == "user-sales-001"


def test_cross_user_conversation_search_is_blocked_before_service_call() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            )
        }
    )
    client = _client(conversation_service)

    response = client.get(
        "/api/v1/conversations/7/messages/search",
        params={"q": "renewal"},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 403
    assert conversation_service.get_calls == [7]
    assert conversation_service.search_call is None


def test_cross_user_chat_is_blocked_before_llm_service_call() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            )
        }
    )
    chat_service = _FakeChatService()
    client = _client(conversation_service, chat_service)

    response = client.post(
        "/api/v1/conversations/7/chat",
        headers={"X-Mock-User": "sales"},
        json={"message": "hello", "stream": False},
    )

    assert response.status_code == 403
    assert conversation_service.get_calls == [7]
    assert chat_service.sync_call is None
    assert chat_service.stream_call is None
