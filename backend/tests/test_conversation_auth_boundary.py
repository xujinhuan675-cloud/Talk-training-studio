from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies import get_chat_service, get_conversation_service
from api.routes.chat import router as chat_router
from api.routes.conversations import router as conversation_router
from application.dto import AgentConfigDTO, ConversationDTO


def _as_mapping(value: object | None) -> dict:
    return value if isinstance(value, dict) else {}


def _metadata_text(metadata: dict, *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _owned_user_id(metadata: dict) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "userId", "user_id") or _metadata_text(
        metadata,
        "ownerUserId",
        "owner_user_id",
        "createdByUserId",
        "created_by_user_id",
    )


def _owned_team_id(metadata: dict) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "teamId", "team_id") or _metadata_text(
        metadata,
        "teamId",
        "team_id",
        "ownerTeamId",
        "owner_team_id",
    )


def _matches_metadata_scope(metadata: dict, scope) -> bool:
    metadata = _as_mapping(metadata)
    owner_user_id = _owned_user_id(metadata)
    owner_team_id = _owned_team_id(metadata)
    team_id = getattr(scope, "team_id", None)
    if not owner_user_id and not owner_team_id:
        return bool(getattr(scope, "allow_unscoped", False))
    if owner_user_id and owner_user_id == getattr(scope, "user_id", None):
        return True
    if getattr(scope, "include_team_scope", False) and owner_team_id and owner_team_id == team_id:
        return True
    if not owner_user_id and owner_team_id and owner_team_id == team_id:
        return True
    return False


def _require_scope_match(metadata: dict, scope) -> None:
    if scope is not None and not _matches_metadata_scope(metadata, scope):
        raise HTTPException(status_code=404, detail="Resource not found")


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


def _agent_config(
    config_id: int,
    *,
    metadata: dict | None = None,
    tool_ids: list[str] | None = None,
    mcp_server_ids: list[str] | None = None,
) -> AgentConfigDTO:
    now = datetime.now(timezone.utc)
    return AgentConfigDTO(
        id=config_id,
        name=f"agent-{config_id}",
        system_prompt=None,
        model="gpt-test",
        temperature=None,
        max_tokens=None,
        tool_ids=tool_ids or [],
        mcp_server_ids=mcp_server_ids or [],
        metadata=metadata or {},
        created_at=now,
        updated_at=now,
    )


class _FakeConversationService:
    def __init__(
        self,
        conversations: dict[int, ConversationDTO] | None = None,
        agent_configs: dict[int, AgentConfigDTO] | None = None,
    ) -> None:
        self.conversations = conversations or {}
        self.agent_configs = agent_configs or {}
        self.created_payload = None
        self.update_call = None
        self.delete_call = None
        self.action_call = None
        self.list_messages_call = None
        self.get_message_path_call = None
        self.locate_message_call = None
        self.list_message_children_call = None
        self.fork_conversation_call = None
        self.edit_message_call = None
        self.retry_message_call = None
        self.list_runs_call = None
        self.list_call = None
        self.search_call = None
        self.agent_config_create_call = None
        self.agent_config_create_scope_calls = []
        self.agent_config_list_call = None
        self.agent_config_get_call = None
        self.agent_config_update_call = None
        self.agent_config_delete_call = None
        self.get_calls: list[int] = []
        self.create_scope_calls = []
        self.get_scope_calls = []
        self.update_scope_calls = []
        self.delete_scope_calls = []
        self.agent_config_get_calls: list[int] = []
        self.agent_config_get_scope_calls = []
        self.agent_config_update_scope_calls = []
        self.agent_config_delete_scope_calls = []

    async def create_conversation(self, payload, **kwargs):
        self.created_payload = payload
        self.create_scope_calls.append(kwargs.get("metadata_scope"))
        return _conversation(21, metadata=payload.metadata)

    async def list_conversations(self, **kwargs):
        self.list_call = kwargs
        items = list(self.conversations.values())
        metadata_scope = kwargs.get("metadata_scope")
        if metadata_scope is not None:
            items = [item for item in items if _matches_metadata_scope(item.metadata, metadata_scope)]
        total = len(items)
        skip = kwargs.get("skip", 0)
        limit = kwargs.get("limit", 20)
        return items[skip:skip + limit], total

    async def get_conversation(self, conversation_id: int, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.get_calls.append(conversation_id)
        self.get_scope_calls.append(metadata_scope)
        item = self.conversations.get(conversation_id) or _conversation(conversation_id)
        _require_scope_match(item.metadata, metadata_scope)
        return item

    async def update_conversation(self, conversation_id: int, payload, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.update_scope_calls.append(metadata_scope)
        item = self.conversations.get(conversation_id) or _conversation(conversation_id)
        _require_scope_match(item.metadata, metadata_scope)
        self.update_call = (conversation_id, payload)
        return item

    async def delete_conversation(self, conversation_id: int, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.delete_scope_calls.append(metadata_scope)
        item = self.conversations.get(conversation_id) or _conversation(conversation_id)
        _require_scope_match(item.metadata, metadata_scope)
        self.delete_call = conversation_id
        return item

    async def search_messages(self, conversation_id: int, query: str, **kwargs):
        self.search_call = (conversation_id, query, kwargs)
        return []

    async def list_messages(self, conversation_id: int, **kwargs):
        self.list_messages_call = (conversation_id, kwargs)
        return [], 0

    async def get_message_path(self, conversation_id: int, message_public_id: str, **kwargs):
        self.get_message_path_call = (conversation_id, message_public_id, kwargs)
        return []

    async def locate_message(self, conversation_id: int, message_public_id: str, **kwargs):
        self.locate_message_call = (conversation_id, message_public_id, kwargs)
        return None

    async def list_message_children(
        self, conversation_id: int, message_public_id: str, **kwargs
    ):
        self.list_message_children_call = (conversation_id, message_public_id, kwargs)
        return []

    async def fork_conversation(self, conversation_id: int, message_public_id: str, payload, **kwargs):
        self.fork_conversation_call = (conversation_id, message_public_id, payload, kwargs)
        return None

    async def edit_message(self, conversation_id: int, message_public_id: str, payload, **kwargs):
        self.edit_message_call = (conversation_id, message_public_id, payload, kwargs)
        return None

    async def retry_message(self, conversation_id: int, message_public_id: str, payload, **kwargs):
        self.retry_message_call = (conversation_id, message_public_id, payload, kwargs)
        return None

    async def list_runs(self, conversation_id: int, **kwargs):
        self.list_runs_call = (conversation_id, kwargs)
        return []

    async def apply_message_action(self, conversation_id: int, message_public_id: str, payload, **kwargs):
        self.action_call = (conversation_id, message_public_id, payload, kwargs)
        return None

    async def create_agent_config(self, payload, **kwargs):
        self.agent_config_create_scope_calls.append(kwargs.get("metadata_scope"))
        self.agent_config_create_call = payload
        return _agent_config(
            31,
            metadata=payload.metadata,
            tool_ids=payload.tool_ids,
            mcp_server_ids=payload.mcp_server_ids,
        )

    async def list_agent_configs(self, **kwargs):
        self.agent_config_list_call = kwargs
        items = list(self.agent_configs.values())
        metadata_scope = kwargs.get("metadata_scope")
        if metadata_scope is not None:
            items = [item for item in items if _matches_metadata_scope(item.metadata, metadata_scope)]
        total = len(items)
        skip = kwargs.get("skip", 0)
        limit = kwargs.get("limit", 20)
        return items[skip:skip + limit], total

    async def get_agent_config(self, config_id: int, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.agent_config_get_call = config_id
        self.agent_config_get_calls.append(config_id)
        self.agent_config_get_scope_calls.append(metadata_scope)
        item = self.agent_configs.get(config_id) or _agent_config(config_id)
        _require_scope_match(item.metadata, metadata_scope)
        return item

    async def update_agent_config(self, config_id: int, payload, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.agent_config_update_scope_calls.append(metadata_scope)
        source = self.agent_configs.get(config_id) or _agent_config(config_id)
        _require_scope_match(source.metadata, metadata_scope)
        self.agent_config_update_call = (config_id, payload)
        metadata = payload.metadata if payload.metadata is not None else source.metadata
        return source.model_copy(
            update={
                "metadata": metadata,
                "tool_ids": payload.tool_ids if payload.tool_ids is not None else source.tool_ids,
                "mcp_server_ids": (
                    payload.mcp_server_ids
                    if payload.mcp_server_ids is not None
                    else source.mcp_server_ids
                ),
            }
        )

    async def delete_agent_config(self, config_id: int, **kwargs):
        metadata_scope = kwargs.get("metadata_scope")
        self.agent_config_delete_scope_calls.append(metadata_scope)
        source = self.agent_configs.get(config_id) or _agent_config(config_id)
        _require_scope_match(source.metadata, metadata_scope)
        self.agent_config_delete_call = config_id
        return None


class _FakeChatService:
    def __init__(self) -> None:
        self.sync_call = None
        self.stream_call = None

    async def send_message_sync(self, conversation_id: int, payload, **kwargs):
        self.sync_call = (conversation_id, payload, kwargs)
        return {"message_id": 1, "content": "ok"}

    async def send_message_stream(self, conversation_id: int, payload, **kwargs):
        self.stream_call = (conversation_id, payload, kwargs)
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
    assert conversation_service.create_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.create_scope_calls[0].team_id == "team-revenue"
    assert conversation_service.create_scope_calls[0].allow_unscoped is False


def test_cross_user_conversation_search_is_scoped_before_search_call() -> None:
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

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    assert conversation_service.get_scope_calls[0].user_id == "user-sales-001"
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


def test_cross_user_conversation_get_uses_scoped_service_call() -> None:
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

    response = client.get("/api/v1/conversations/7", headers={"X-Mock-User": "sales"})

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    scope = conversation_service.get_scope_calls[0]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False


def test_non_admin_conversation_list_filters_before_pagination() -> None:
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
            9: _conversation(
                9,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
        }
    )
    client = _client(conversation_service)

    first_page = client.get(
        "/api/v1/conversations",
        params={"page": 1, "size": 1},
        headers={"X-Mock-User": "sales"},
    )
    second_page = client.get(
        "/api/v1/conversations",
        params={"page": 2, "size": 1},
        headers={"X-Mock-User": "sales"},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert [item["id"] for item in first_page.json()["data"]["items"]] == [8]
    assert first_page.json()["data"]["total"] == 2
    assert [item["id"] for item in second_page.json()["data"]["items"]] == [9]
    assert second_page.json()["data"]["total"] == 2


def test_cross_user_conversation_mutations_are_blocked_by_scoped_service_call() -> None:
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

    assert update_resp.status_code == 404
    assert delete_resp.status_code == 404
    assert conversation_service.get_calls == []
    assert conversation_service.update_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.delete_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.update_call is None
    assert conversation_service.delete_call is None


def test_leader_single_resource_routes_use_team_metadata_scope() -> None:
    team_metadata = {
        "ownerUserId": "user-peer-001",
        "teamId": "team-revenue",
    }
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata=team_metadata)},
        agent_configs={8: _agent_config(8, metadata=team_metadata)},
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "leader"}

    responses = [
        client.get("/api/v1/conversations/7", headers=headers),
        client.patch("/api/v1/conversations/7", headers=headers, json={"title": "team"}),
        client.delete("/api/v1/conversations/7", headers=headers),
        client.get("/api/v1/agent-configs/8", headers=headers),
        client.patch("/api/v1/agent-configs/8", headers=headers, json={"name": "team-agent"}),
        client.delete("/api/v1/agent-configs/8", headers=headers),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200, 200]
    assert conversation_service.get_scope_calls[0].include_team_scope is True
    assert conversation_service.update_scope_calls[0].include_team_scope is True
    assert conversation_service.delete_scope_calls[0].include_team_scope is True
    assert conversation_service.agent_config_get_scope_calls[0].include_team_scope is True
    assert conversation_service.agent_config_update_scope_calls[0].include_team_scope is True
    assert conversation_service.agent_config_delete_scope_calls[0].include_team_scope is True


def test_admin_single_resource_routes_use_explicit_metadata_scope() -> None:
    admin_metadata = {
        "ownerUserId": "user-admin-001",
        "teamId": "team-ops",
    }
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata=admin_metadata)},
        agent_configs={8: _agent_config(8, metadata=admin_metadata)},
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "admin"}

    responses = [
        client.get("/api/v1/conversations/7", headers=headers),
        client.patch("/api/v1/conversations/7", headers=headers, json={"title": "admin"}),
        client.delete("/api/v1/conversations/7", headers=headers),
        client.get("/api/v1/agent-configs/8", headers=headers),
        client.patch("/api/v1/agent-configs/8", headers=headers, json={"name": "admin-agent"}),
        client.delete("/api/v1/agent-configs/8", headers=headers),
    ]

    assert [response.status_code for response in responses] == [200, 200, 200, 200, 200, 200]
    conversation_scopes = (
        conversation_service.get_scope_calls
        + conversation_service.update_scope_calls
        + conversation_service.delete_scope_calls
    )
    agent_config_scopes = (
        conversation_service.agent_config_get_scope_calls
        + conversation_service.agent_config_update_scope_calls
        + conversation_service.agent_config_delete_scope_calls
    )
    assert conversation_scopes
    assert agent_config_scopes
    for scope in conversation_scopes + agent_config_scopes:
        assert scope is not None
        assert scope.user_id == "user-admin-001"
        assert scope.team_id == "team-ops"
        assert scope.include_team_scope is True
    assert conversation_service.get_scope_calls[0].allow_unscoped is True
    assert conversation_service.update_scope_calls[0].allow_unscoped is False
    assert conversation_service.delete_scope_calls[0].allow_unscoped is False
    assert {scope.allow_unscoped for scope in agent_config_scopes} == {False}


def test_admin_single_resource_routes_reject_resources_outside_explicit_scope() -> None:
    other_metadata = {
        "ownerUserId": "user-cs-001",
        "teamId": "team-service",
    }
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata=other_metadata)},
        agent_configs={8: _agent_config(8, metadata=other_metadata)},
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "admin"}

    responses = [
        client.get("/api/v1/conversations/7", headers=headers),
        client.patch("/api/v1/conversations/7", headers=headers, json={"title": "admin"}),
        client.delete("/api/v1/conversations/7", headers=headers),
        client.get("/api/v1/agent-configs/8", headers=headers),
        client.patch("/api/v1/agent-configs/8", headers=headers, json={"name": "admin-agent"}),
        client.delete("/api/v1/agent-configs/8", headers=headers),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404, 404]
    assert conversation_service.update_call is None
    assert conversation_service.delete_call is None
    assert conversation_service.agent_config_update_call is None
    assert conversation_service.agent_config_delete_call is None


def test_non_admin_cannot_update_or_delete_unscoped_conversation() -> None:
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata={})}
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "sales"}

    update_resp = client.patch(
        "/api/v1/conversations/7",
        headers=headers,
        json={"title": "unscoped update"},
    )
    delete_resp = client.delete("/api/v1/conversations/7", headers=headers)

    assert update_resp.status_code == 404
    assert delete_resp.status_code == 404
    assert conversation_service.update_scope_calls[0].allow_unscoped is False
    assert conversation_service.delete_scope_calls[0].allow_unscoped is False
    assert conversation_service.update_call is None
    assert conversation_service.delete_call is None


@pytest.mark.parametrize(
    ("path", "request_kwargs", "service_attr"),
    [
        pytest.param(
            "/api/v1/conversations/7/messages/msg_answer/actions",
            {"json": {"action": "retry"}},
            "action_call",
            id="message-action",
        ),
        pytest.param(
            "/api/v1/conversations/7/messages/msg_answer/edit",
            {"json": {"content": "edit"}},
            "edit_message_call",
            id="message-edit",
        ),
        pytest.param(
            "/api/v1/conversations/7/messages/msg_answer/retry",
            {"json": {}},
            "retry_message_call",
            id="message-retry",
        ),
        pytest.param(
            "/api/v1/conversations/7/messages/msg_answer/fork",
            {"json": {}},
            "fork_conversation_call",
            id="message-fork",
        ),
    ],
)
def test_non_admin_cannot_mutate_unscoped_conversation_tree(
    path: str,
    request_kwargs: dict,
    service_attr: str,
) -> None:
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata={})}
    )
    client = _client(conversation_service)

    response = client.post(path, headers={"X-Mock-User": "sales"}, **request_kwargs)

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    assert conversation_service.get_scope_calls[0].allow_unscoped is False
    assert getattr(conversation_service, service_attr) is None


def test_non_admin_cannot_chat_against_unscoped_conversation() -> None:
    conversation_service = _FakeConversationService(
        conversations={7: _conversation(7, metadata={})}
    )
    chat_service = _FakeChatService()
    client = _client(conversation_service, chat_service)

    response = client.post(
        "/api/v1/conversations/7/chat",
        headers={"X-Mock-User": "sales"},
        json={"message": "hello", "stream": False},
    )

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    assert conversation_service.get_scope_calls[0].allow_unscoped is False
    assert chat_service.sync_call is None
    assert chat_service.stream_call is None


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

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    assert conversation_service.get_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.action_call is None


def test_conversation_child_routes_pass_metadata_scope_to_service_calls() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            )
        }
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "sales"}

    responses = [
        client.get("/api/v1/conversations/7/messages", headers=headers),
        client.get("/api/v1/conversations/7/messages/search", params={"q": "deal"}, headers=headers),
        client.get("/api/v1/conversations/7/messages/msg_answer/path", headers=headers),
        client.get("/api/v1/conversations/7/messages/msg_answer/locate", headers=headers),
        client.get("/api/v1/conversations/7/messages/msg_answer/children", headers=headers),
        client.get("/api/v1/conversations/7/runs", headers=headers),
        client.post(
            "/api/v1/conversations/7/messages/msg_answer/actions",
            json={"action": "retry"},
            headers=headers,
        ),
        client.post(
            "/api/v1/conversations/7/messages/msg_answer/fork",
            json={},
            headers=headers,
        ),
        client.post(
            "/api/v1/conversations/7/messages/msg_answer/edit",
            json={"content": "edit"},
            headers=headers,
        ),
        client.post(
            "/api/v1/conversations/7/messages/msg_answer/retry",
            json={},
            headers=headers,
        ),
    ]

    assert [response.status_code for response in responses] == [200] * len(responses)
    read_calls = [
        conversation_service.list_messages_call,
        conversation_service.search_call,
        conversation_service.get_message_path_call,
        conversation_service.locate_message_call,
        conversation_service.list_message_children_call,
        conversation_service.list_runs_call,
    ]
    write_calls = [
        conversation_service.action_call,
        conversation_service.fork_conversation_call,
        conversation_service.edit_message_call,
        conversation_service.retry_message_call,
    ]
    for call in read_calls:
        scope = call[-1]["metadata_scope"]
        assert scope.user_id == "user-sales-001"
        assert scope.allow_unscoped is True
    for call in write_calls:
        scope = call[-1]["metadata_scope"]
        assert scope.user_id == "user-sales-001"
        assert scope.allow_unscoped is False


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs", "service_attr"),
    [
        pytest.param(
            "get",
            "/api/v1/conversations/7/messages",
            {"params": {"branch_id": "main"}},
            "list_messages_call",
            id="messages",
        ),
        pytest.param(
            "get",
            "/api/v1/conversations/7/messages/msg_answer/path",
            {"params": {"limit": 5}},
            "get_message_path_call",
            id="message-path",
        ),
        pytest.param(
            "get",
            "/api/v1/conversations/7/messages/msg_answer/locate",
            {"params": {"before": 1, "after": 1}},
            "locate_message_call",
            id="message-locate",
        ),
        pytest.param(
            "get",
            "/api/v1/conversations/7/messages/msg_answer/children",
            {"params": {"include_deleted": True}},
            "list_message_children_call",
            id="message-children",
        ),
        pytest.param(
            "post",
            "/api/v1/conversations/7/messages/msg_answer/fork",
            {"json": {}},
            "fork_conversation_call",
            id="message-fork",
        ),
        pytest.param(
            "post",
            "/api/v1/conversations/7/messages/msg_answer/edit",
            {"json": {"content": "edit"}},
            "edit_message_call",
            id="message-edit",
        ),
        pytest.param(
            "post",
            "/api/v1/conversations/7/messages/msg_answer/retry",
            {"json": {}},
            "retry_message_call",
            id="message-retry",
        ),
        pytest.param(
            "get",
            "/api/v1/conversations/7/runs",
            {"params": {"limit": 10, "status": "completed"}},
            "list_runs_call",
            id="runs",
        ),
    ],
)
def test_cross_user_conversation_child_routes_are_scoped_before_service_call(
    method: str,
    path: str,
    request_kwargs: dict,
    service_attr: str,
) -> None:
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

    response = client.request(
        method.upper(),
        path,
        headers={"X-Mock-User": "sales"},
        **request_kwargs,
    )

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    scope = conversation_service.get_scope_calls[0]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert getattr(conversation_service, service_attr) is None


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

    assert response.status_code == 404
    assert conversation_service.get_calls == [7]
    assert conversation_service.get_scope_calls[0].user_id == "user-sales-001"
    assert chat_service.sync_call is None
    assert chat_service.stream_call is None


def test_chat_route_passes_current_user_scope_to_chat_service() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
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

    assert response.status_code == 200
    scope = chat_service.sync_call[-1]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


def test_chat_stream_route_passes_current_user_scope_to_chat_service() -> None:
    conversation_service = _FakeConversationService(
        {
            7: _conversation(
                7,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            )
        }
    )
    chat_service = _FakeChatService()
    client = _client(conversation_service, chat_service)

    response = client.post(
        "/api/v1/conversations/7/chat",
        headers={"X-Mock-User": "sales"},
        json={"message": "hello", "stream": True},
    )

    assert response.status_code == 200
    assert chat_service.sync_call is None
    scope = chat_service.stream_call[-1]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


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


def test_create_agent_config_stamps_current_mock_user_scope() -> None:
    conversation_service = _FakeConversationService()
    client = _client(conversation_service)

    response = client.post(
        "/api/v1/agent-configs",
        headers={"X-Mock-User": "sales"},
        json={
            "name": "sales-agent",
            "tool_ids": ["crm.lookup"],
            "mcp_server_ids": ["crm"],
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
    assert response.json()["data"]["tool_ids"] == ["crm.lookup"]
    assert response.json()["data"]["mcp_server_ids"] == ["crm"]
    assert (
        conversation_service.agent_config_create_call.metadata["ownerUserId"]
        == "user-sales-001"
    )
    assert conversation_service.agent_config_create_call.tool_ids == ["crm.lookup"]
    assert conversation_service.agent_config_create_call.mcp_server_ids == ["crm"]
    scope = conversation_service.agent_config_create_scope_calls[0]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


def test_agent_config_routes_enforce_owner_metadata_scope() -> None:
    conversation_service = _FakeConversationService(
        agent_configs={
            7: _agent_config(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            ),
            8: _agent_config(
                8,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
            9: _agent_config(9, metadata={}),
        }
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "sales"}

    list_resp = client.get("/api/v1/agent-configs", headers=headers)
    get_resp = client.get("/api/v1/agent-configs/7", headers=headers)
    update_resp = client.patch(
        "/api/v1/agent-configs/7",
        headers=headers,
        json={"name": "forged-agent"},
    )
    delete_resp = client.delete("/api/v1/agent-configs/7", headers=headers)

    assert list_resp.status_code == 200
    assert [item["id"] for item in list_resp.json()["data"]["items"]] == [8]
    assert get_resp.status_code == 404
    assert update_resp.status_code == 404
    assert delete_resp.status_code == 404
    assert conversation_service.agent_config_get_calls == [7, 7]
    assert [scope.user_id for scope in conversation_service.agent_config_get_scope_calls] == [
        "user-sales-001",
        "user-sales-001",
    ]
    assert conversation_service.agent_config_delete_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.agent_config_update_call is None
    assert conversation_service.agent_config_delete_call is None


def test_non_admin_cannot_update_or_delete_unscoped_agent_config() -> None:
    conversation_service = _FakeConversationService(
        agent_configs={9: _agent_config(9, metadata={})}
    )
    client = _client(conversation_service)
    headers = {"X-Mock-User": "sales"}

    update_resp = client.patch(
        "/api/v1/agent-configs/9",
        headers=headers,
        json={"name": "legacy-agent"},
    )
    delete_resp = client.delete("/api/v1/agent-configs/9", headers=headers)

    assert update_resp.status_code == 404
    assert delete_resp.status_code == 404
    assert conversation_service.agent_config_get_scope_calls[0].allow_unscoped is False
    assert conversation_service.agent_config_delete_scope_calls[0].allow_unscoped is False
    assert conversation_service.agent_config_update_call is None
    assert conversation_service.agent_config_delete_call is None


def test_non_admin_agent_config_list_filters_before_pagination() -> None:
    conversation_service = _FakeConversationService(
        agent_configs={
            7: _agent_config(
                7,
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            ),
            8: _agent_config(
                8,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
            9: _agent_config(
                9,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                },
            ),
        }
    )
    client = _client(conversation_service)

    first_page = client.get(
        "/api/v1/agent-configs",
        params={"page": 1, "size": 1},
        headers={"X-Mock-User": "sales"},
    )
    second_page = client.get(
        "/api/v1/agent-configs",
        params={"page": 2, "size": 1},
        headers={"X-Mock-User": "sales"},
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert [item["id"] for item in first_page.json()["data"]["items"]] == [8]
    assert first_page.json()["data"]["total"] == 2
    assert [item["id"] for item in second_page.json()["data"]["items"]] == [9]
    assert second_page.json()["data"]["total"] == 2


def test_agent_config_update_preserves_existing_owner_scope() -> None:
    conversation_service = _FakeConversationService(
        agent_configs={
            8: _agent_config(
                8,
                metadata={
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                    "source": "original",
                },
            ),
        }
    )
    client = _client(conversation_service)

    response = client.patch(
        "/api/v1/agent-configs/8",
        headers={"X-Mock-User": "sales"},
        json={
            "metadata": {
                "ownerUserId": "user-cs-001",
                "teamId": "team-service",
                "source": "updated",
            },
        },
    )

    assert response.status_code == 200
    assert conversation_service.agent_config_get_scope_calls[0].user_id == "user-sales-001"
    assert conversation_service.agent_config_update_scope_calls[0].user_id == "user-sales-001"
    _, payload = conversation_service.agent_config_update_call
    assert payload.metadata["ownerUserId"] == "user-sales-001"
    assert payload.metadata["teamId"] == "team-revenue"
    assert payload.metadata["authScope"]["userId"] == "user-sales-001"
    assert payload.metadata["authScope"]["teamId"] == "team-revenue"
    assert payload.metadata["source"] == "updated"
