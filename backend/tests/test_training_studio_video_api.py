"""API tests for Training Studio video answer upload and replay."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import training_studio
from api.routes.training_studio import router
from core.exceptions import register_exception_handlers


def create_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(training_studio, "_VIDEO_ANSWER_DIR", tmp_path)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_video_answer_upload_and_replay(tmp_path, monkeypatch) -> None:
    client = create_client(tmp_path, monkeypatch)

    upload_resp = client.post(
        "/api/v1/training-studio/video-answers",
        content=b"webm-bytes",
        headers={"content-type": "video/webm", "x-filename": "answer.webm"},
    )

    assert upload_resp.status_code == 201
    data = upload_resp.json()["data"]
    assert data["filename"].endswith(".webm")
    assert data["mimeType"] == "video/webm"
    assert data["size"] == len(b"webm-bytes")
    assert data["url"].startswith("/api/v1/training-studio/video-answers/")

    replay_resp = client.get(data["url"])
    assert replay_resp.status_code == 200
    assert replay_resp.content == b"webm-bytes"
    assert replay_resp.headers["content-type"].startswith("video/webm")


def test_video_answer_upload_rejects_non_video(tmp_path, monkeypatch) -> None:
    client = create_client(tmp_path, monkeypatch)

    resp = client.post(
        "/api/v1/training-studio/video-answers",
        content=b"not-video",
        headers={"content-type": "text/plain", "x-filename": "note.txt"},
    )

    assert resp.status_code == 422


def test_video_answer_replay_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    client = create_client(tmp_path, monkeypatch)

    resp = client.get("/api/v1/training-studio/video-answers/..%2Fsecret.webm")

    assert resp.status_code == 404
