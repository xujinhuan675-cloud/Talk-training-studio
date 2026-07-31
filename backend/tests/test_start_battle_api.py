# input: FastAPI minimal app + BattlePrepService stub override
# output: Story 2.8 POST /personas/{id}/start-battle API 测试
# owner: wanhua.gu
# pos: 测试层 - Story 2.8 start-battle 路由测试；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""API tests for Story 2.8: POST /personas/{id}/start-battle (AC1, AC2)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_battle_prep_service
from api.routes.stakeholder import router
from application.services.stakeholder.dto import ChatRoomDTO
from core.exceptions import register_exception_handlers


class _StubBattlePrepService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def launch_persona_training(
        self,
        persona_id: str,
        *,
        access_scope=None,
        training_session_service=None,
        conversation_adapter=None,
    ):
        self.calls.append(persona_id)
        self.access_scope = access_scope
        if persona_id == "missing":
            raise ValueError(f"Persona {persona_id} not found")
        return _StubBattleLaunch(persona_id=persona_id, room_id=42)

    async def launch_battle_training(
        self,
        body,
        *,
        access_scope=None,
        training_session_service=None,
        conversation_adapter=None,
    ):
        self.calls.append(body.persona_name)
        self.access_scope = access_scope
        return _StubBattleLaunch(persona_id="generated-persona", room_id=77)


class _StubBattleLaunch:
    def __init__(self, *, persona_id: str, room_id: int) -> None:
        self.persona_id = persona_id
        self.room_id = room_id

    def to_dict(self) -> dict[str, object]:
        conversation = {
            "provider": "talkwise-conversation",
            "conversationId": "conversation-9",
            "metadata": {"runtime": "conversation_message_tree"},
        }
        return {
            "training_session": {
                "session_id": "training-9",
                "mode": "text",
                "status": "active",
                "room_id": "talkwise-conversation:conversation-9",
                "conversation": conversation,
            },
            "training_session_id": "training-9",
            "conversation_id": "conversation-9",
            "room_id": self.room_id,
            "persona_snapshot": {"persona_id": self.persona_id, "version": 1},
            "conversation": conversation,
            "room": {"id": self.room_id, "persona_ids": [self.persona_id]},
        }


@pytest.fixture
def client():
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    stub = _StubBattlePrepService()
    app.dependency_overrides[get_battle_prep_service] = lambda: stub
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test"), stub


@pytest.mark.asyncio
async def test_start_battle_happy(client) -> None:
    ac, stub = client
    async with ac as c:
        resp = await c.post("/api/v1/stakeholder/personas/cfo/start-battle")
        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["room_id"] == 42
        assert body["data"]["training_session"]["session_id"] == "training-9"
        assert body["data"]["training_session"]["conversation"]["conversationId"] == "conversation-9"
        assert body["data"]["persona_snapshot"]["persona_id"] == "cfo"
    assert stub.calls == ["cfo"]
    assert stub.access_scope.user_id == "user-admin-001"


@pytest.mark.asyncio
async def test_start_battle_persona_not_found(client) -> None:
    ac, _ = client
    async with ac as c:
        resp = await c.post("/api/v1/stakeholder/personas/missing/start-battle")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generated_battle_returns_newapi_conversation_launch_contract(client) -> None:
    ac, stub = client
    async with ac as c:
        resp = await c.post(
            "/api/v1/stakeholder/battle-prep/start",
            json={
                "persona_name": "Alex",
                "persona_role": "VP Sales",
                "persona_style": "Direct and skeptical.",
                "scenario_context": "Budget review.",
                "selected_training_points": ["Handle objections"],
                "difficulty": "normal",
            },
        )

    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["training_session_id"] == "training-9"
    assert body["conversation_id"] == "conversation-9"
    assert body["training_session"]["mode"] == "text"
    assert body["conversation"]["metadata"]["runtime"] == "conversation_message_tree"
    assert stub.calls == ["Alex"]
    assert stub.access_scope.user_id == "user-admin-001"
