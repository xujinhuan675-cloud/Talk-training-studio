from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import CurrentUser, get_current_user
from api.routes import training_team as training_team_routes
from api.routes.training_team import (
    get_team_training_analytics_service,
    router,
    team_member_names_for_current_user,
)
from application.services.training_studio.team_analytics_service import (
    TeamCompetencyDimensionDTO,
    TeamCompetencyRankingDTO,
    TeamScenarioRankingDTO,
)
from core.exceptions import register_exception_handlers
from infrastructure.external.newapi_auth import (
    NewAPITeam,
    NewAPITeamMember,
    NewAPITeamMembersResult,
)


class FakeTeamAnalyticsService:
    def __init__(self) -> None:
        self.competency_calls: list[dict[str, object]] = []
        self.scenario_calls: list[dict[str, object]] = []

    async def list_competency_rankings(self, **kwargs):
        self.competency_calls.append(kwargs)
        return (
            [
                TeamCompetencyRankingDTO(
                    member_id="user-sales",
                    sample_count=2,
                    dimensions=[
                        TeamCompetencyDimensionDTO(
                            dimension_id="attentiveness",
                            score=80,
                            sample_count=2,
                            scenario_count=2,
                            state="exploring",
                        )
                    ],
                )
            ],
            1,
        )

    async def list_scenario_rankings(self, **kwargs):
        self.scenario_calls.append(kwargs)
        return (
            [
                TeamScenarioRankingDTO(
                    scenario_id="enterprise-demo",
                    member_id="user-sales",
                    rank=1,
                    completed_sessions=2,
                    scored_sessions=2,
                    average_score=80,
                )
            ],
            1,
        )


def make_app(current_user: CurrentUser) -> tuple[FastAPI, FakeTeamAnalyticsService]:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")
    service = FakeTeamAnalyticsService()
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_team_training_analytics_service] = lambda: service
    return app, service


def test_team_competencies_use_authenticated_team_scope_without_query_overrides() -> None:
    app, service = make_app(
        CurrentUser(
            user_id="user-admin-001",
            system_role="admin",
            team_id="team-revenue",
        )
    )

    response = TestClient(app).get(
        "/api/v1/training-studio/team/competencies",
        params={"user_id": "user-service", "team_id": "team-service"},
    )

    assert response.status_code == 200
    assert response.headers["x-total-count"] == "1"
    assert response.json()["data"][0]["member_id"] == "user-sales"
    scope = service.competency_calls[0]["access_scope"]
    assert scope.user_id == "user-admin-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is True


def test_team_scenarios_and_permission_guard() -> None:
    app, service = make_app(
        CurrentUser(
            user_id="user-admin-001",
            system_role="admin",
            team_id="team-revenue",
        )
    )
    response = TestClient(app).get("/api/v1/training-studio/team/scenarios")

    assert response.status_code == 200
    assert response.json()["data"][0]["scenario_id"] == "enterprise-demo"
    assert service.scenario_calls[0]["access_scope"].team_id == "team-revenue"

    denied_app, denied_service = make_app(
        CurrentUser(
            user_id="user-sales",
            system_role="staff",
            team_id="team-revenue",
        )
    )
    denied = TestClient(denied_app).get("/api/v1/training-studio/team/competencies")

    assert denied.status_code == 403
    assert denied_service.competency_calls == []


def test_team_analytics_requires_an_explicit_training_team_assignment() -> None:
    app, service = make_app(
        CurrentUser(
            user_id="newapi:1",
            system_role="admin",
        )
    )

    response = TestClient(app).get("/api/v1/training-studio/team/scenarios")

    assert response.status_code == 422
    body = response.json()
    assert body["message"] == "Team analytics is unavailable without a team assignment"
    assert body["error"]["details"]["detail"] == {
        "code": "TRAINING_TEAM_ASSIGNMENT_REQUIRED",
        "message": "Team analytics is unavailable without a team assignment",
    }
    assert service.scenario_calls == []


@pytest.mark.asyncio
async def test_team_member_names_use_only_the_authenticated_training_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_fetch_team_members(**kwargs):
        calls.append(kwargs)
        return NewAPITeamMembersResult(
            team=NewAPITeam(id="newapi:revenue", name="revenue", group="revenue"),
            members=[
                NewAPITeamMember(
                    id=7,
                    username="sales-lead",
                    display_name="Sales lead",
                )
            ],
            total=1,
        )

    monkeypatch.setattr(
        training_team_routes,
        "fetch_newapi_team_members",
        fake_fetch_team_members,
    )
    names = await team_member_names_for_current_user(
        CurrentUser(
            user_id="newapi:1",
            system_role="admin",
            team_id="newapi:revenue",
        )
    )

    assert calls[0]["group"] is None
    assert calls[0]["team_id"] == "newapi:revenue"
    assert names == {"newapi:7": "Sales lead"}
