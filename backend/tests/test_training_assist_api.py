from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import CurrentUser, get_current_user
from api.routes.training_assist import (
    get_live_assist_service,
    get_training_assist_session_service,
    router,
)
from application.services.training_studio.live_assist_service import LiveAssistService
from application.services.training_studio.live_guidance_service import TrainingLiveGuidanceService
from domain.training_studio.session import TrainingSessionStatus


class _FakeSessionService:
    async def get_session(self, session_id: str, *, access_scope):
        if access_scope.user_id != "user-1":
            raise PermissionError("Training session is outside scope")
        return SimpleNamespace(
            session_id=session_id,
            status=TrainingSessionStatus.ACTIVE,
            task_config=SimpleNamespace(
                role="seller",
                level="senior",
                tech_stack=["discovery"],
                category="sales",
                framework="star",
                rubric_weights={},
                metadata={},
            ),
        )

    async def record_session_metadata(self, session_id: str, *, metadata, access_scope):
        return None


def _client(*, user_id="user-1") -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id,
        system_role="staff",
        team_id="team-1",
    )
    app.dependency_overrides[get_training_assist_session_service] = _FakeSessionService
    app.dependency_overrides[get_live_assist_service] = lambda: LiveAssistService(
        stt=None,
        guidance=TrainingLiveGuidanceService(),
    )
    return TestClient(app)


def test_training_assist_processes_transcript_and_returns_turn_guidance() -> None:
    response = _client().post(
        "/api/v1/training-assist/sessions/session-1/turns",
        json={
            "text": "We are worried about the cost.",
            "speakerSource": "system",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["session_id"] == "session-1"
    assert data["user_id"] == "user-1"
    assert data["turn"]["speaker"] == "counterpart"
    assert data["turn"]["text"] == "We are worried about the cost."
    assert any(event["event_type"] == "risk" for event in data["guidance"])


def test_training_assist_requires_text_or_audio() -> None:
    response = _client().post(
        "/api/v1/training-assist/sessions/session-1/turns",
        json={"speakerSource": "microphone"},
    )
    assert response.status_code == 422


def test_training_assist_keeps_session_access_scoped() -> None:
    response = _client(user_id="other-user").post(
        "/api/v1/training-assist/sessions/session-1/turns",
        json={"text": "hello"},
    )
    assert response.status_code == 403
