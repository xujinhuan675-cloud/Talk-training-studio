from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_conversation_service
from api.routes.conversations import router
from application.dto import MessageDTO_Agent, MessageLocationDTO, MessageSearchResultDTO


def _message(content: str, public_id: str = "msg_1") -> MessageDTO_Agent:
    return MessageDTO_Agent(
        id=1,
        conversation_id=7,
        role="user",
        content=content,
        public_id=public_id,
        parent_message_id=None,
        branch_id="main",
        status="active",
        created_at=datetime.now(timezone.utc),
    )


class _FakeChatService:
    def __init__(self) -> None:
        self.search_call = None
        self.locate_call = None
        self.edit_call = None
        self.retry_call = None

    async def search_messages(self, conversation_id: int, query: str, **kwargs):
        self.search_call = (conversation_id, query, kwargs)
        message = _message("Pilot metric discussion", public_id="msg_search")
        return [
            MessageSearchResultDTO(
                message=message,
                path=[message],
                context=[message],
            )
        ]

    async def locate_message(self, conversation_id: int, message_public_id: str, **kwargs):
        self.locate_call = (conversation_id, message_public_id, kwargs)
        message = _message("Selected branch turn", public_id=message_public_id)
        return MessageLocationDTO(
            message=message,
            path=[message],
            context=[message],
        )

    async def edit_message(self, conversation_id: int, message_public_id: str, payload):
        self.edit_call = (conversation_id, message_public_id, payload)
        return _message(payload.content, public_id="msg_edit")

    async def retry_message(self, conversation_id: int, message_public_id: str, payload):
        self.retry_call = (conversation_id, message_public_id, payload)
        return _message(payload.content, public_id="msg_retry")


def _client(service: _FakeChatService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_conversation_service] = lambda: service
    return TestClient(app)


def test_search_messages_route_returns_branch_context() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.get(
        "/api/v1/conversations/7/messages/search",
        params={
            "q": "pilot",
            "branch_id": "main",
            "roles": ["user", "assistant"],
            "limit": 10,
            "context_before": 2,
            "context_after": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["message"]["public_id"] == "msg_search"
    assert data[0]["path"][0]["content"] == "Pilot metric discussion"
    assert service.search_call == (
        7,
        "pilot",
        {
            "skip": 0,
            "limit": 10,
            "branch_id": "main",
            "roles": ["user", "assistant"],
            "include_path": True,
            "context_before": 2,
            "context_after": 3,
        },
    )


def test_locate_message_route_returns_message_location() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.get(
        "/api/v1/conversations/7/messages/msg_selected/locate",
        params={"before": 1, "after": 4},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["message"]["public_id"] == "msg_selected"
    assert data["context"][0]["content"] == "Selected branch turn"
    assert service.locate_call == (7, "msg_selected", {"before": 1, "after": 4})


def test_edit_message_route_creates_branch_message() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.post(
        "/api/v1/conversations/7/messages/msg_original/edit",
        json={"content": "Edited turn", "metadata": {"reason": "typo"}},
    )

    assert response.status_code == 200
    assert response.json()["data"]["public_id"] == "msg_edit"
    assert service.edit_call[0:2] == (7, "msg_original")
    assert service.edit_call[2].content == "Edited turn"
    assert service.edit_call[2].metadata == {"reason": "typo"}


def test_retry_message_route_creates_branch_message() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.post(
        "/api/v1/conversations/7/messages/msg_answer/retry",
        json={"content": "Retry answer", "metadata": {"temperature": 0.2}},
    )

    assert response.status_code == 200
    assert response.json()["data"]["public_id"] == "msg_retry"
    assert service.retry_call[0:2] == (7, "msg_answer")
    assert service.retry_call[2].content == "Retry answer"
    assert service.retry_call[2].metadata == {"temperature": 0.2}
