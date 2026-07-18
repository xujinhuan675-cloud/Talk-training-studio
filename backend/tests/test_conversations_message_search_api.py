from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_conversation_service
from api.routes.conversations import router
from application.dto import (
    ConversationDTO,
    ForkConversationResultDTO,
    MessageActionResultDTO,
    MessageDTO_Agent,
    MessageLocationDTO,
    MessageSearchResultDTO,
)


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


def _conversation(
    conversation_id: int = 8,
    metadata: dict | None = None,
) -> ConversationDTO:
    now = datetime.now(timezone.utc)
    return ConversationDTO(
        id=conversation_id,
        title="Forked conversation",
        system_prompt=None,
        model="gpt-test",
        status="active",
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


class _FakeChatService:
    def __init__(self) -> None:
        self.search_call = None
        self.path_call = None
        self.children_call = None
        self.locate_call = None
        self.action_call = None
        self.fork_call = None
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

    async def get_conversation(self, conversation_id: int, **kwargs):
        return _conversation(conversation_id=conversation_id)

    async def get_message_path(self, conversation_id: int, message_public_id: str, **kwargs):
        self.path_call = (conversation_id, message_public_id, kwargs)
        return [_message("Path root", public_id=message_public_id)]

    async def list_message_children(self, conversation_id: int, message_public_id: str, **kwargs):
        self.children_call = (conversation_id, message_public_id, kwargs)
        return [_message("Child turn", public_id="msg_child")]

    async def locate_message(self, conversation_id: int, message_public_id: str, **kwargs):
        self.locate_call = (conversation_id, message_public_id, kwargs)
        message = _message("Selected branch turn", public_id=message_public_id)
        return MessageLocationDTO(
            message=message,
            path=[message],
            context=[message],
        )

    async def apply_message_action(self, conversation_id: int, message_public_id: str, payload):
        self.action_call = (conversation_id, message_public_id, payload)
        message = _message("Selected action branch", public_id=message_public_id)
        return MessageActionResultDTO(
            action=payload.action,
            message=message,
            path=[message],
            children=[_message("Child branch", public_id="msg_child")],
            siblings=[message],
            branch_id="main",
        )

    async def edit_message(self, conversation_id: int, message_public_id: str, payload):
        self.edit_call = (conversation_id, message_public_id, payload)
        return _message(payload.content, public_id="msg_edit")

    async def retry_message(self, conversation_id: int, message_public_id: str, payload):
        self.retry_call = (conversation_id, message_public_id, payload)
        return _message(payload.content, public_id="msg_retry")

    async def fork_conversation(self, conversation_id: int, message_public_id: str, payload):
        self.fork_call = (conversation_id, message_public_id, payload)
        message = _message("Forked root", public_id="msg_forked")
        return ForkConversationResultDTO(
            conversation=_conversation(),
            messages=[message],
            source_to_forked_id={message_public_id: "msg_forked"},
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
            "statuses": ["active"],
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
            "statuses": ["active"],
            "provider": None,
            "model": None,
            "include_path": True,
            "context_before": 2,
            "context_after": 3,
        },
    )


def test_get_message_path_route_passes_tree_filters() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.get(
        "/api/v1/conversations/7/messages/msg_selected/path",
        params={
            "limit": 5,
            "include_deleted": True,
            "statuses": ["active", "superseded"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["public_id"] == "msg_selected"
    assert service.path_call == (
        7,
        "msg_selected",
        {
            "limit": 5,
            "include_deleted": True,
            "statuses": ["active", "superseded"],
        },
    )


def test_list_message_children_route_passes_tree_filters() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.get(
        "/api/v1/conversations/7/messages/msg_parent/children",
        params={
            "include_deleted": True,
            "statuses": ["active"],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["public_id"] == "msg_child"
    assert service.children_call == (
        7,
        "msg_parent",
        {"statuses": ["active"], "include_deleted": True},
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


def test_message_action_route_returns_controlled_tree_context() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.post(
        "/api/v1/conversations/7/messages/msg_selected/actions",
        json={
            "action": "branch",
            "include_deleted": True,
            "statuses": ["active", "superseded"],
            "metadata": {"source": "training_room"},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["action"] == "branch"
    assert data["message"]["public_id"] == "msg_selected"
    assert data["path"][0]["content"] == "Selected action branch"
    assert data["children"][0]["public_id"] == "msg_child"
    assert data["siblings"][0]["public_id"] == "msg_selected"
    assert data["branch_id"] == "main"
    assert service.action_call[0:2] == (7, "msg_selected")
    assert service.action_call[2].action == "branch"
    assert service.action_call[2].include_deleted is True
    assert service.action_call[2].statuses == ["active", "superseded"]
    assert service.action_call[2].metadata == {"source": "training_room"}


def test_fork_conversation_route_creates_copied_tree() -> None:
    service = _FakeChatService()
    client = _client(service)

    response = client.post(
        "/api/v1/conversations/7/messages/msg_selected/fork",
        json={
            "title": "Forked conversation",
            "option": "includeBranches",
            "include_deleted": True,
            "statuses": ["active", "superseded"],
            "metadata": {"source": "test"},
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["conversation"]["id"] == 8
    assert data["messages"][0]["public_id"] == "msg_forked"
    assert data["source_to_forked_id"] == {"msg_selected": "msg_forked"}
    assert service.fork_call[0:2] == (7, "msg_selected")
    assert service.fork_call[2].option == "includeBranches"
    assert service.fork_call[2].include_deleted is True
    assert service.fork_call[2].statuses == ["active", "superseded"]


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
