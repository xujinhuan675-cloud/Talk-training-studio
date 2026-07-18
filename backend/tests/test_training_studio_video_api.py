"""API tests for Training Studio video answer upload and replay."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import training_studio
from api.routes.training_studio import get_training_session_service, router
from application.services.training_studio.session_service import TrainingSessionService
from core.exceptions import register_exception_handlers


def _session_payload() -> dict:
    return {
        "mode": "video",
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


@pytest.fixture
def app(tmp_path, monkeypatch) -> FastAPI:
    monkeypatch.setattr(training_studio, "_VIDEO_ANSWER_DIR", tmp_path)
    session_service = TrainingSessionService(id_factory=lambda: "session-1")

    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_training_session_service] = lambda: session_service
    test_app.state.training_session_service = session_service
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _start_bound_session(client: TestClient) -> str:
    admin_headers = {"X-Mock-User": "admin"}
    create_resp = client.post(
        "/api/v1/training-studio/sessions",
        json={
            **_session_payload(),
            "user_id": "user-sales-001",
            "team_id": "team-revenue",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
        headers=admin_headers,
    )
    assert start_resp.status_code == 200
    return session_id


def test_video_answer_upload_and_replay_with_session_binding(client: TestClient) -> None:
    headers = {"X-Mock-User": "sales"}
    session_id = _start_bound_session(client)

    upload_resp = client.post(
        f"/api/v1/training-studio/video-answers?training_session_id={session_id}&room_id=42",
        content=b"webm-bytes",
        headers={
            **headers,
            "content-type": "video/webm",
            "x-filename": "answer.webm",
        },
    )

    assert upload_resp.status_code == 201
    data = upload_resp.json()["data"]
    assert data["filename"].endswith(".webm")
    assert data["mimeType"] == "video/webm"
    assert data["size"] == len(b"webm-bytes")
    assert "training_session_id=session-1" in data["url"]
    assert "room_id=42" in data["url"]
    assert "auth_user_id=user-sales-001" in data["url"]

    replay_resp = client.get(data["url"])
    assert replay_resp.status_code == 200
    assert replay_resp.content == b"webm-bytes"
    assert replay_resp.headers["content-type"].startswith("video/webm")


def test_video_answer_upload_rejects_non_video(client: TestClient) -> None:
    headers = {"X-Mock-User": "sales"}
    session_id = _start_bound_session(client)

    resp = client.post(
        f"/api/v1/training-studio/video-answers?training_session_id={session_id}&room_id=42",
        content=b"not-video",
        headers={
            **headers,
            "content-type": "text/plain",
            "x-filename": "note.txt",
        },
    )

    assert resp.status_code == 422


def test_video_answer_upload_rejects_room_mismatch(client: TestClient) -> None:
    headers = {"X-Mock-User": "sales"}
    session_id = _start_bound_session(client)

    resp = client.post(
        f"/api/v1/training-studio/video-answers?training_session_id={session_id}&room_id=99",
        content=b"webm-bytes",
        headers={
            **headers,
            "content-type": "video/webm",
            "x-filename": "answer.webm",
        },
    )

    assert resp.status_code == 400


def test_video_answer_upload_rejects_other_team_user(client: TestClient) -> None:
    session_id = _start_bound_session(client)

    resp = client.post(
        f"/api/v1/training-studio/video-answers?training_session_id={session_id}&room_id=42",
        content=b"webm-bytes",
        headers={
            "X-Mock-User": "customer_service",
            "content-type": "video/webm",
            "x-filename": "answer.webm",
        },
    )

    assert resp.status_code == 403


def test_video_answer_replay_rejects_binding_mismatch(client: TestClient) -> None:
    headers = {"X-Mock-User": "sales"}
    session_id = _start_bound_session(client)

    upload_resp = client.post(
        f"/api/v1/training-studio/video-answers?training_session_id={session_id}&room_id=42",
        content=b"webm-bytes",
        headers={
            **headers,
            "content-type": "video/webm",
            "x-filename": "answer.webm",
        },
    )
    data = upload_resp.json()["data"]

    resp = client.get(data["url"].replace("room_id=42", "room_id=99"))

    assert resp.status_code == 404


def test_video_answer_replay_rejects_path_traversal(client: TestClient) -> None:
    headers = {"X-Mock-User": "sales"}
    session_id = _start_bound_session(client)

    resp = client.get(
        f"/api/v1/training-studio/video-answers/..%2Fsecret.webm?training_session_id={session_id}&room_id=42",
        headers=headers,
    )

    assert resp.status_code == 404
