"""API tests for Training Studio catalog and storybank endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.routes.training_studio import get_storybank_service, router
from core.exceptions import register_exception_handlers
from domain.training_studio.storybank import StoryBankService


@pytest.fixture
def app():
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(router, prefix="/api/v1")
    storybank = StoryBankService()
    test_app.dependency_overrides[get_storybank_service] = lambda: storybank
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
    }
    assert {item["value"] for item in data["frameworks"]} == {"prep", "star", "scqa", "pyramid"}
    assert "interview-five-dimension-v1" in data["rubric_versions"]


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
