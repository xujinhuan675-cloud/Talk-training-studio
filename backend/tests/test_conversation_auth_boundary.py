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
        self.update_call = None
        self.delete_call = None
        self.action_call = None
        self.list_call = None
        self.search_call = None
        self.agent_config_create_call = None
        self.agent_config_list_call = None
        self.agent_config_get_call = None
        self.agent_config_update_call = None
        self.agent_config_delete_call = None
        self.get_calls: list[int] = []

    async def create_conversation(self, payload):
        self.created_payload = payload
        return _conversation(21, metadata=payload.metadata)

    async def list_conversations(self, **kwargs):
        self.list_call = kwargs
        return list(self.conversations.values()), len(self.conversations)

    async def get_conversation(self, conversation_id: int):
        self.get_calls.append(conversation_id)
        return self.conversations.get(conversation_id) or _conversation(conversation_id)

    async def update_conversation(self, conversation_id: int, payload):
        self.update_call = (conversation_id, payload)
        return self.conversations.get(conversation_id) or _conversation(conversation_id)

    async def delete_conversation(self, conversation_id: int):
        self.delete_call = conversation_id
        return self.conversations.get(conversation_id) or _conversation(conversation_id)

    async def search_messages(self, conversation_id: int, query: str, **kwargs):
        self.search_call = (conversation_id, query, kwargs)
        return []

    async def apply_message_action(self, conversation_id: int, message_public_id: str, payload):
        self.action_call = (conversation_id, message_public_id, payload)
        return None

    async def create_agent_config(self, payload):
        self.agent_config_create_call = payload
        return None

    async def list_agent_configs(self, **kwargs):
        self.agent_config_list_call = kwargs
        return [], 0

    async def get_agent_config(self, config_id: int):
        self.agent_config_get_call = config_id
        return None

    async def update_agent_config(self, config_id: int, payload):
        self.agent_config_update_call = (config_id, payload)
        return None

    async def delete_agent_config(self, config_id: int):
        self.agent_config_delete_call = config_id
        return None


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


def test_cross_user_conversation_list_filters_other_user_items() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            ),
            8: _conversation(
                8,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
        }
    )
    client = _client(conversation_service)

    response = client.get("/api/v1/conversations", headers={"X-Mock-User": "sales"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert [item["id"] for item in data["items"]] == [8]
    assert data["total"] == 1


def test_cross_user_conversation_mutations_are_blocked_before_service_call() -> None:
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

    update_resp = client.patch(
        "/api/v1/conversations/7",
        headers={"X-Mock-User": "sales"},
        json={"title": "forged title"},
    )
    delete_resp = client.delete("/api/v1/conversations/7", headers={"X-Mock-User": "sales"})

    assert update_resp.status_code == 403
    assert delete_resp.status_code == 403
    assert conversation_service.get_calls == [7, 7]
    assert conversation_service.update_call is None
    assert conversation_service.delete_call is None


def test_cross_user_message_action_is_blocked_before_service_call() -> None:
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

    response = client.post(
        "/api/v1/conversations/7/messages/msg_answer/actions",
        headers={"X-Mock-User": "sales"},
        json={"action": "retry"},
    )

    assert response.status_code == 403
    assert conversation_service.get_calls == [7]
    assert conversation_service.action_call is None


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


def test_agent_config_routes_reject_unsupported_system_roles_before_service_call() -> None:
    conversation_service = _FakeConversationService()
    client = _client(conversation_service)

    response = client.post(
        "/api/v1/agent-configs",
        headers={"X-System-Role": "auditor"},
        json={"name": "shared-agent"},
    )

    assert response.status_code == 401
    assert conversation_service.agent_config_create_call is None
    assert conversation_service.agent_config_list_call is None
    assert conversation_service.agent_config_get_call is None
    assert conversation_service.agent_config_update_call is None
    assert conversation_service.agent_config_delete_call is None
