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
