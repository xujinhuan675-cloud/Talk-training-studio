# input: FastAPI test app, ChatRoomApplicationService, PersonaLoader stub
# output: Story 2.1 API endpoint tests
# owner: wanhua.gu
# pos: 测试层 - Story 2.1 聊天室 API 路由验收测试；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""API tests for Story 2.1: ChatRoom CRUD endpoints.

Uses a minimal FastAPI app (no lifespan) to avoid aiosqlite threading issues
with full main.app startup.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_battle_prep_service,
    get_chatroom_service,
    get_coaching_service,
    get_growth_service,
    get_stakeholder_chat_service,
)
from api.routes.stakeholder import router
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from core.exceptions import register_exception_handlers
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


# ---------------------------------------------------------------------------
# Stub persona loader
# ---------------------------------------------------------------------------


class _StubPersonaLoader:
    _personas = {
        "jianfeng": type(
            "P",
            (),
            {
                "id": "jianfeng",
                "name": "李建峰",
                "role": "CTO",
                "avatar_color": "#f00",
                "organization_id": None,
                "team_id": "team-revenue",
                "parse_status": "ok",
                "profile_summary": "test",
            },
        )(),
        "robin": type(
            "P",
            (),
            {
                "id": "robin",
                "name": "Robin",
                "role": "CEO",
                "avatar_color": "#0f0",
                "organization_id": None,
                "team_id": "team-revenue",
                "parse_status": "ok",
                "profile_summary": "test",
            },
        )(),
        "casey": type(
            "P",
            (),
            {
                "id": "casey",
                "name": "Casey",
                "role": "Support",
                "avatar_color": "#00f",
                "organization_id": None,
                "team_id": "team-service",
                "parse_status": "ok",
                "profile_summary": "test",
            },
        )(),
    }

    def get_persona(self, pid):
        return self._personas.get(pid)

    def list_personas(self):
        return list(self._personas.values())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def client(session_factory):
    """Create a minimal test FastAPI app with stakeholder router."""
    stub_loader = _StubPersonaLoader()

    def _uow_factory(**kwargs):
        return SQLAlchemyUnitOfWork(session_factory=session_factory, **kwargs)

    svc = ChatRoomApplicationService(uow_factory=_uow_factory, persona_loader=stub_loader)

    class _FakeStakeholderChatService:
        async def send_message(self, room_id, content, *, metadata=None, access_scope):
            raise AssertionError("send_message should not run for inaccessible rooms")

        async def generate_replies(self, room_id, room) -> None:
            raise AssertionError("generate_replies should not run for inaccessible rooms")

    class _FakeRoomScopedDownstreamService:
        async def generate_report(self, room_id, *, access_scope):
            raise AssertionError("generate_report should not run for inaccessible rooms")

        async def list_reports(self, room_id, *, skip=0, limit=50, access_scope):
            raise AssertionError("list_reports should not run for inaccessible rooms")

        async def get_report(self, report_id, *, room_id, access_scope):
            raise AssertionError("get_report should not run for inaccessible rooms")

        async def prepare_start_session(self, room_id, report_id, *, access_scope):
            raise AssertionError("prepare_start_session should not run for inaccessible rooms")

        async def prepare_live_advice(self, room_id, *, access_scope):
            raise AssertionError("prepare_live_advice should not run for inaccessible rooms")

        async def prepare_send_message(self, room_id, session_id, content, *, access_scope):
            raise AssertionError("prepare_send_message should not run for inaccessible rooms")

        async def get_session(self, session_id, *, room_id, access_scope):
            raise AssertionError("get_session should not run for inaccessible rooms")

        async def list_sessions(self, room_id, *, skip=0, limit=50, access_scope):
            raise AssertionError("list_sessions should not run for inaccessible rooms")

        async def generate_cheat_sheet(self, room_id, *, access_scope):
            raise AssertionError("generate_cheat_sheet should not run for inaccessible rooms")

        async def evaluate_competency(self, report_id):
            raise AssertionError("evaluate_competency should not run for inaccessible rooms")

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    # Override dependency
    app.dependency_overrides[get_chatroom_service] = lambda: svc
    app.dependency_overrides[get_stakeholder_chat_service] = _FakeStakeholderChatService
    downstream = _FakeRoomScopedDownstreamService()
    app.dependency_overrides[get_analysis_service] = lambda: downstream
    app.dependency_overrides[get_analysis_reader_service] = lambda: downstream
    app.dependency_overrides[get_coaching_service] = lambda: downstream
    app.dependency_overrides[get_battle_prep_service] = lambda: downstream
    app.dependency_overrides[get_growth_service] = lambda: downstream

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# AC1: POST create private room → 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_private_room(client: AsyncClient):
    resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Private Chat", "type": "private", "persona_ids": ["jianfeng"]},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["type"] == "private"
    assert data["persona_ids"] == ["jianfeng"]


# ---------------------------------------------------------------------------
# AC2: POST create group room → 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_room(client: AsyncClient):
    resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Group Chat", "type": "group", "persona_ids": ["jianfeng", "robin"]},
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["type"] == "group"
    assert len(data["persona_ids"]) == 2


# ---------------------------------------------------------------------------
# AC3: Private with 2 personas → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_private_room_wrong_persona_count(client: AsyncClient):
    resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Bad", "type": "private", "persona_ids": ["jianfeng", "robin"]},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC4: Group with 1 persona → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_group_room_too_few_personas(client: AsyncClient):
    resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Bad", "type": "group", "persona_ids": ["jianfeng"]},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC5: Nonexistent persona → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_room_nonexistent_persona(client: AsyncClient):
    resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Bad", "type": "private", "persona_ids": ["nonexistent"]},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC6: List rooms ordered
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rooms(client: AsyncClient):
    await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Room A", "type": "private", "persona_ids": ["jianfeng"]},
    )
    await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Room B", "type": "group", "persona_ids": ["jianfeng", "robin"]},
    )
    resp = await client.get("/api/v1/stakeholder/rooms")
    assert resp.status_code == 200
    rooms = resp.json()["data"]
    assert len(rooms) == 2


@pytest.mark.asyncio
async def test_list_rooms_filters_to_current_user_team(client: AsyncClient):
    await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Revenue Room", "type": "private", "persona_ids": ["jianfeng"]},
    )
    await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Service Room", "type": "private", "persona_ids": ["casey"]},
    )

    resp = await client.get(
        "/api/v1/stakeholder/rooms",
        headers={"X-Mock-User": "sales"},
    )

    assert resp.status_code == 200
    rooms = resp.json()["data"]
    assert [room["name"] for room in rooms] == ["Revenue Room"]


# ---------------------------------------------------------------------------
# AC7: Get room detail with messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_room_detail_with_messages(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Detail", "type": "private", "persona_ids": ["jianfeng"]},
    )
    room_id = create_resp.json()["data"]["id"]
    resp = await client.get(f"/api/v1/stakeholder/rooms/{room_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["room"]["id"] == room_id
    assert isinstance(data["messages"], list)


@pytest.mark.asyncio
async def test_room_detail_and_delete_hide_rooms_outside_scope(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Service Detail", "type": "private", "persona_ids": ["casey"]},
    )
    room_id = create_resp.json()["data"]["id"]

    detail_resp = await client.get(
        f"/api/v1/stakeholder/rooms/{room_id}",
        headers={"X-Mock-User": "sales"},
    )
    delete_resp = await client.delete(
        f"/api/v1/stakeholder/rooms/{room_id}",
        headers={"X-Mock-User": "sales"},
    )
    admin_detail = await client.get(f"/api/v1/stakeholder/rooms/{room_id}")

    assert detail_resp.status_code == 404
    assert delete_resp.status_code == 404
    assert admin_detail.status_code == 200


# ---------------------------------------------------------------------------
# AC8: Get nonexistent room → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_message_hides_room_outside_scope_before_write(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Service Send", "type": "private", "persona_ids": ["casey"]},
    )
    room_id = create_resp.json()["data"]["id"]

    resp = await client.post(
        f"/api/v1/stakeholder/rooms/{room_id}/messages",
        json={"content": "hello"},
        headers={"X-Mock-User": "sales"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_room_scoped_downstream_routes_hide_rooms_outside_scope(client: AsyncClient):
    create_resp = await client.post(
        "/api/v1/stakeholder/rooms",
        json={"name": "Service Workflow", "type": "private", "persona_ids": ["casey"]},
    )
    room_id = create_resp.json()["data"]["id"]
    headers = {"X-Mock-User": "sales"}
    cases = [
        ("GET", f"/api/v1/stakeholder/rooms/{room_id}/stream", {}),
        ("POST", f"/api/v1/stakeholder/rooms/{room_id}/analysis", {}),
        ("GET", f"/api/v1/stakeholder/rooms/{room_id}/analysis", {}),
        ("GET", f"/api/v1/stakeholder/rooms/{room_id}/analysis/1", {}),
        ("POST", f"/api/v1/stakeholder/rooms/{room_id}/analysis/1/coaching", {}),
        ("POST", f"/api/v1/stakeholder/rooms/{room_id}/coaching/live", {}),
        (
            "POST",
            f"/api/v1/stakeholder/rooms/{room_id}/coaching/live/reply",
            {"json": {"content": "help", "history": []}},
        ),
        (
            "POST",
            f"/api/v1/stakeholder/rooms/{room_id}/coaching/1/messages",
            {"json": {"content": "follow up"}},
        ),
        ("GET", f"/api/v1/stakeholder/rooms/{room_id}/coaching/1", {}),
        ("GET", f"/api/v1/stakeholder/rooms/{room_id}/coaching", {}),
        ("POST", f"/api/v1/stakeholder/rooms/{room_id}/cheatsheet", {}),
    ]

    for method, path, kwargs in cases:
        resp = await client.request(method, path, headers=headers, **kwargs)
        assert resp.status_code == 404, path


@pytest.mark.asyncio
async def test_get_nonexistent_room(client: AsyncClient):
    resp = await client.get("/api/v1/stakeholder/rooms/99999")
    assert resp.status_code == 404
