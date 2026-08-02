from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import CurrentUser, get_current_user, get_defense_prep_service
from api.routes.defense_prep import router
from core.exceptions import register_exception_handlers


class FakeDefenseService:
    def __init__(self) -> None:
        self.create_kwargs: dict[str, object] | None = None
        self.get_scopes = []
        self.deleted_scopes = []
        self.started_session = None

    async def create_session(self, **kwargs):
        self.create_kwargs = kwargs
        return type(
            "Session",
            (),
            {
                "id": 41,
                "persona_ids": kwargs["persona_ids"],
                "scenario_type": kwargs["scenario_type"],
                "document_summary": type("Summary", (), {"title": "Plan"})(),
                "status": "preparing",
                "created_at": None,
            },
        )()

    async def get_session(self, session_id: int, *, access_scope):
        self.get_scopes.append(access_scope)
        return None

    async def delete_session(self, session_id: int, *, access_scope):
        self.deleted_scopes.append(access_scope)
        return False

    async def start_session(
        self,
        session_id: int,
        *,
        access_scope,
        selected_question_indexes=None,
        focus_scope="all",
    ):
        self.get_scopes.append(access_scope)
        self.start_selection = (selected_question_indexes, focus_scope)
        if self.started_session is not None:
            return self.started_session
        raise ValueError(f"Defense session {session_id} not found")

    async def prepare_questions(self, session_id: int, *, access_scope):
        self.get_scopes.append(access_scope)
        if self.started_session is not None:
            return self.started_session
        raise ValueError(f"Defense session {session_id} not found")

    async def generate_report(self, session_id: int, *, access_scope):
        self.get_scopes.append(access_scope)
        raise ValueError(f"Defense session {session_id} not found")


def make_app(current_user: CurrentUser):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    service = FakeDefenseService()
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_defense_prep_service] = lambda: service
    return app, service


def test_defense_creation_derives_owner_only_from_authenticated_user():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    response = TestClient(app).post(
        "/api/v1/defense-prep/sessions",
        data={"persona_ids": "finance-reviewer", "scenario_type": "performance_review"},
        files={"file": ("plan.txt", b"proposal", "text/plain")},
    )

    assert response.status_code == 200
    assert service.create_kwargs["owner_user_id"] == "user-sales-001"
    assert service.create_kwargs["owner_team_id"] == "team-revenue"


def test_defense_read_and_delete_pass_authenticated_scope_and_hide_misses():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    client = TestClient(app)

    assert client.get("/api/v1/defense-prep/sessions/8").status_code == 404
    assert client.delete("/api/v1/defense-prep/sessions/8").status_code == 404
    assert service.get_scopes[0].user_id == "user-sales-001"
    assert service.get_scopes[0].team_id == "team-revenue"
    assert service.get_scopes[0].unrestricted is False
    assert service.deleted_scopes[0].user_id == "user-sales-001"


def test_defense_start_and_report_hide_out_of_scope_sessions():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    client = TestClient(app)

    assert client.post("/api/v1/defense-prep/sessions/8/start").status_code == 404
    assert client.get("/api/v1/defense-prep/sessions/8/report").status_code == 404
    assert [scope.user_id for scope in service.get_scopes] == [
        "user-sales-001",
        "user-sales-001",
    ]


def test_defense_start_returns_native_training_workspace_identifiers():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    service.started_session = type(
        "Session",
        (),
        {
            "id": 8,
            "room_id": 21,
            "training_session_id": "training-defense-8",
            "conversation_id": 55,
            "status": "in_progress",
            "question_strategy": None,
        },
    )()

    response = TestClient(app).post("/api/v1/defense-prep/sessions/8/start")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["training_session_id"] == "training-defense-8"
    assert data["conversation_id"] == 55


def test_defense_start_accepts_confirmed_question_scope():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    service.started_session = type(
        "Session",
        (),
        {
            "id": 8,
            "room_id": 21,
            "training_session_id": "training-defense-8",
            "conversation_id": 55,
            "status": "in_progress",
            "question_strategy": None,
        },
    )()

    response = TestClient(app).post(
        "/api/v1/defense-prep/sessions/8/start",
        json={"selected_question_indexes": [0, 2], "focus_scope": "custom"},
    )

    assert response.status_code == 200
    assert service.start_selection == ([0, 2], "custom")


def test_defense_question_preparation_returns_reviewable_strategy():
    app, service = make_app(
        CurrentUser(
            user_id="user-sales-001", system_role="staff", team_id="team-revenue"
        )
    )
    question = type(
        "Question",
        (),
        {
            "question": "Which evidence supports the forecast?",
            "dimension": "evidence",
            "difficulty": "hard",
            "asked_by": "finance-reviewer",
        },
    )()
    service.started_session = type(
        "Session",
        (),
        {
            "id": 8,
            "document_summary": type("Summary", (), {"title": "Q3 plan"})(),
            "status": "preparing",
            "question_strategy": type("Strategy", (), {"questions": [question]})(),
        },
    )()

    response = TestClient(app).post("/api/v1/defense-prep/sessions/8/questions")

    assert response.status_code == 200
    assert response.json()["data"]["question_strategy"]["questions"] == [
        {
            "question": "Which evidence supports the forecast?",
            "dimension": "evidence",
            "difficulty": "hard",
            "asked_by": "finance-reviewer",
        }
    ]
