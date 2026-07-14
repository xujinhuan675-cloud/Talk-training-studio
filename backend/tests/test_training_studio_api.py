"""API tests for Training Studio catalog and storybank endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_growth_service,
)
from api.routes.training_studio import get_storybank_service, get_training_session_service, router
from application.services.training_studio.session_service import TrainingSessionService
from core.exceptions import register_exception_handlers
from domain.training_studio.storybank import StoryBankService


class FakeReport(BaseModel):
    id: int
    room_id: int
    summary: str = "Good practice report"
    content: dict = {}


class FakeAnalysisService:
    async def generate_report(self, room_id: int) -> FakeReport:
        return FakeReport(id=501, room_id=room_id)


class FakeAnalysisReaderService:
    def __init__(self) -> None:
        self.reports: dict[int, FakeReport] = {}

    async def get_report(self, report_id: int) -> FakeReport | None:
        return self.reports.get(report_id)


class FakeGrowthService:
    def __init__(self) -> None:
        self.evaluated: list[int] = []

    async def evaluate_competency(self, report_id: int) -> None:
        self.evaluated.append(report_id)


class FakeChatroomService:
    def __init__(self) -> None:
        self.created_rooms: list[object] = []

    async def create_room(self, dto):
        self.created_rooms.append(dto)
        return SimpleNamespace(id=701)


@pytest.fixture
def app():
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(router, prefix="/api/v1")
    storybank = StoryBankService()
    session_service = TrainingSessionService(id_factory=lambda: f"session-{len(session_service.list_sessions()) + 1}")
    reader_service = FakeAnalysisReaderService()
    growth_service = FakeGrowthService()
    chatroom_service = FakeChatroomService()
    test_app.dependency_overrides[get_storybank_service] = lambda: storybank
    test_app.dependency_overrides[get_training_session_service] = lambda: session_service
    test_app.dependency_overrides[get_analysis_service] = lambda: FakeAnalysisService()
    test_app.dependency_overrides[get_analysis_reader_service] = lambda: reader_service
    test_app.dependency_overrides[get_growth_service] = lambda: growth_service
    test_app.dependency_overrides[get_chatroom_service] = lambda: chatroom_service
    test_app.state.training_session_service = session_service
    test_app.state.analysis_reader_service = reader_service
    test_app.state.growth_service = growth_service
    test_app.state.chatroom_service = chatroom_service
    return test_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_catalog_exposes_training_dimensions(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/training-studio/catalog")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {item["value"] for item in data["categories"]} == {
        "interview",
        "sales",
        "negotiation",
        "workplace",
        "product_management",
    }
    assert {item["value"] for item in data["frameworks"]} == {"prep", "star", "scqa", "pyramid"}
    assert "interview-five-dimension-v1" in data["rubric_versions"]
    assert any(item["value"] == "core_pm" for item in data["role_presets"])
    assert any(item["value"] == "hiring_manager" for item in data["role_presets"])
    assert any(item["value"] == "prd_review" for item in data["scenario_presets"])
    assert any(item["value"] == "product_sense_case" for item in data["scenario_presets"])


@pytest.mark.asyncio
async def test_task_config_normalizes_ratios_and_rubric_weights(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/training-studio/task-config",
        json={
            "role": "Backend Engineer",
            "level": "Senior",
            "tech_stack": ["Python", "FastAPI"],
            "question_type_ratios": {"behavioral": 30, "technical": 60, "pressure": 10},
            "question_count": 8,
            "framework": "star",
            "difficulty": "medium",
            "category": "interview",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["difficulty"] == "medium"
    assert round(sum(data["question_type_ratios"].values()), 5) == 1
    assert round(sum(data["rubric_weights"].values()), 5) == 1


def session_payload(mode: str = "voice") -> dict:
    return {
        "mode": mode,
        "task_config": {
            "role": "Sales Associate",
            "level": "Senior",
            "tech_stack": ["discovery", "objection handling"],
            "question_type_ratios": {"behavioral": 30, "craft": 50, "pressure": 20},
            "question_count": 6,
            "framework": "prep",
            "difficulty": "medium",
            "category": "sales",
        },
    }


@pytest.mark.asyncio
async def test_training_session_create_list_and_get(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())

    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["session_id"] == "session-1"
    assert created["status"] == "created"
    assert created["mode"] == "voice"
    assert created["task_config"]["category"] == "sales"
    assert round(sum(created["task_config"]["question_type_ratios"].values()), 5) == 1

    list_resp = await client.get("/api/v1/training-studio/sessions")
    assert list_resp.status_code == 200
    assert [item["session_id"] for item in list_resp.json()["data"]] == ["session-1"]

    get_resp = await client.get("/api/v1/training-studio/sessions/session-1")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_training_session_start_with_explicit_room_id(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "42"

    duplicate_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 43},
    )
    assert duplicate_resp.status_code == 400


@pytest.mark.asyncio
async def test_training_session_start_can_create_room(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("video"))
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"persona_ids": ["customer-1"], "room_name": "Sales practice"},
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "701"


@pytest.mark.asyncio
async def test_training_session_complete_and_report(client: AsyncClient, app: FastAPI) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={},
    )

    assert complete_resp.status_code == 200
    completed = complete_resp.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "501"

    app.state.analysis_reader_service.reports[501] = FakeReport(id=501, room_id=42)
    report_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["id"] == 501


@pytest.mark.asyncio
async def test_training_session_errors(client: AsyncClient) -> None:
    missing_resp = await client.post(
        "/api/v1/training-studio/sessions/missing/start",
        json={"room_id": 1},
    )
    assert missing_resp.status_code == 404

    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"generate_report": False},
    )
    assert complete_resp.status_code == 400


@pytest.mark.asyncio
async def test_storybank_register_and_list(client: AsyncClient) -> None:
    answer = (
        "I led a small platform migration team through a difficult API rewrite. "
        "We reduced latency by 35 percent and recovered trust with two key stakeholders."
    )
    create_resp = await client.post(
        "/api/v1/training-studio/storybank/entries",
        json={"answer_text": answer, "scenario_category": "interview", "tags": ["Impact"]},
    )

    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["scenario_category"] == "interview"
    assert created["tags"] == ["impact"]

    list_resp = await client.get("/api/v1/training-studio/storybank/entries")
    assert list_resp.status_code == 200
    entries = list_resp.json()["data"]
    assert len(entries) == 1
    assert entries[0]["id"] == created["id"]
