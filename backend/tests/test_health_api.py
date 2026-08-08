from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import health as health_routes
from core.config import settings


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(health_routes.router)
    return TestClient(app)


def test_voice_health_requires_configured_monitor_token(monkeypatch) -> None:
    monkeypatch.setattr(settings.health, "access_token", None)

    response = _client().get("/health/voice/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Health access token is not configured"


def test_voice_health_rejects_invalid_monitor_token(monkeypatch) -> None:
    monkeypatch.setattr(settings.health, "access_token", "monitor-token")

    response = _client().get(
        "/health/voice/ready",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 403


def test_voice_health_returns_monitorable_status(monkeypatch) -> None:
    monkeypatch.setattr(settings.health, "access_token", "monitor-token")
    monkeypatch.setattr(
        health_routes,
        "build_voice_health_report",
        lambda **_: {"status": "ready", "ready": True, "routes": []},
    )

    response = _client().get(
        "/health/voice/ready",
        headers={"X-Access-Token": "monitor-token"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["ready"] is True
