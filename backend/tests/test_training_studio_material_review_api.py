from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_analysis_reader_service,
    get_chatroom_service,
    get_file_asset_service,
    get_stakeholder_llm_client,
)
from api.routes.training_studio import get_training_session_service, router
from application.dto import FileAssetDTO
from application.ports.llm import LLMResponse
from application.services.stakeholder.dto import MessageDTO
from domain.common.exceptions import FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import TrainingSession, TrainingSessionStatus
from domain.training_studio.session_repository import (
    training_session_matches_access_scope,
)


def _task_config() -> TrainingTaskConfig:
    return TrainingTaskConfig(
        role="Account Executive",
        level="Senior",
        tech_stack=["renewal", "enterprise"],
        question_type_ratios={"scenario": 1},
        question_count=3,
        framework="prep",
        difficulty="medium",
        category="sales",
        metadata={
            "messageTreeSelection": {"affectsScoring": False},
            "growthReport": {"status": "existing"},
        },
    )


def _session(
    session_id: str = "training-1",
    *,
    user_id: str = "user-sales-001",
    team_id: str = "team-revenue",
    room_id: str | None = "42",
    report_id: str | None = "9",
    score_id: str | None = "score-1",
) -> TrainingSession:
    return TrainingSession(
        session_id=session_id,
        task_config=_task_config(),
        mode="text",
        scenario_template_id="enterprise-renewal",
        user_id=user_id,
        team_id=team_id,
        status=TrainingSessionStatus.COMPLETED,
        room_id=room_id,
        report_id=report_id,
        score_id=score_id,
        message_count=4,
    )


def _material_asset(
    asset_id: int = 7,
    *,
    owner_user_id: str = "user-sales-001",
    team_id: str = "team-revenue",
) -> FileAssetDTO:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAssetDTO(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=f"training_material/{asset_id}.md",
        size=128,
        etag="etag-1",
        content_type="text/markdown",
        original_filename=f"material-{asset_id}.md",
        kind="training_material",
        is_public=False,
        metadata={
            "title": "Renewal playbook",
            "summary": "Ask about success criteria and show ROI proof.",
            "ownerUserId": owner_user_id,
            "teamId": team_id,
        },
        url=None,
        status="active",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class _FakeTrainingSessionService:
    def __init__(self, sessions: list[TrainingSession]) -> None:
        self.sessions = {session.session_id: session for session in sessions}
        self.get_calls: list[dict[str, Any]] = []
        self.mutating_calls: list[str] = []

    async def get_session(self, session_id: str, *, access_scope=None):
        self.get_calls.append({"session_id": session_id, "access_scope": access_scope})
        session = self.sessions.get(session_id)
        if session is None:
            raise ValueError(f"Training session not found: {session_id}")
        if not training_session_matches_access_scope(session, access_scope):
            raise PermissionError("Training session is outside current user scope")
        return session

    async def start_session(self, *args, **kwargs):
        self.mutating_calls.append("start_session")
        raise AssertionError("material review must not start sessions")

    async def complete_session(self, *args, **kwargs):
        self.mutating_calls.append("complete_session")
        raise AssertionError("material review must not complete sessions")


class _FakeFileAssetService:
    def __init__(self, assets: list[FileAssetDTO] | None = None) -> None:
        self.assets = {asset.id: asset for asset in assets or []}
        self.get_calls: list[dict[str, Any]] = []
        self.read_calls: list[dict[str, Any]] = []

    async def get_asset(self, asset_id: int, *, metadata_scope):
        self.get_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        asset = self.assets.get(asset_id)
        if asset is None or not _matches_metadata_scope(asset.metadata, metadata_scope):
            raise FileAssetNotFoundException(asset_id)
        return asset

    async def read_asset_bytes(self, asset_id: int, *, metadata_scope, max_bytes=8192):
        self.read_calls.append(
            {"asset_id": asset_id, "metadata_scope": metadata_scope, "max_bytes": max_bytes}
        )
        asset = self.assets.get(asset_id)
        if asset is None or not _matches_metadata_scope(asset.metadata, metadata_scope):
            raise FileAssetNotFoundException(asset_id)
        return b"Discovery question: confirm success criteria.\nUse ROI proof.", False


class _FakeAnalysisReader:
    def __init__(self) -> None:
        self.get_calls: list[int] = []

    async def get_report(self, report_id: int, *, room_id: int, access_scope):
        self.get_calls.append(report_id)
        return SimpleNamespace(
            id=report_id,
            room_id=42,
            summary="The learner used ROI proof but missed success criteria.",
            content={
                "communication_suggestions": [
                    {"suggestion": "Lead with quantified ROI before discussing discounting."}
                ]
            },
        )


class _FakeChatroomService:
    def __init__(self, messages: list[MessageDTO] | None = None) -> None:
        self.get_calls: list[dict[str, Any]] = []
        self.messages = messages or [
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="user-sales-001",
                content="We can prove ROI with activation metrics.",
                metadata={},
            )
        ]

    async def get_room_detail(
        self,
        room_id: int,
        *,
        message_limit: int = 50,
        access_scope=None,
    ):
        self.get_calls.append(
            {"room_id": room_id, "message_limit": message_limit, "access_scope": access_scope}
        )
        return SimpleNamespace(
            room=SimpleNamespace(id=room_id),
            messages=self.messages,
        )


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    async def generate(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return LLMResponse(content=self.content, model="fake-review-model")


def _matches_metadata_scope(
    metadata: dict[str, Any] | None,
    scope: OwnedMetadataScope,
) -> bool:
    metadata = metadata or {}
    auth_scope = metadata.get("authScope") if isinstance(metadata.get("authScope"), dict) else {}
    owner_user_id = (
        auth_scope.get("userId")
        or auth_scope.get("user_id")
        or metadata.get("ownerUserId")
        or metadata.get("owner_user_id")
        or metadata.get("createdByUserId")
        or metadata.get("created_by_user_id")
    )
    owner_team_id = (
        auth_scope.get("teamId")
        or auth_scope.get("team_id")
        or metadata.get("teamId")
        or metadata.get("team_id")
        or metadata.get("ownerTeamId")
        or metadata.get("owner_team_id")
    )
    owner_user_id = str(owner_user_id).strip() if owner_user_id else ""
    owner_team_id = str(owner_team_id).strip() if owner_team_id else ""

    if owner_user_id and owner_user_id == scope.user_id:
        return True
    if scope.team_id and owner_team_id == scope.team_id:
        return bool(scope.include_team_scope or not owner_user_id)
    if not owner_user_id and not owner_team_id:
        return scope.allow_unscoped
    return False


def _client(
    session_service: _FakeTrainingSessionService,
    file_service: _FakeFileAssetService,
    *,
    reader: _FakeAnalysisReader | None = None,
    chatroom: _FakeChatroomService | None = None,
    llm: _FakeLLM | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_training_session_service] = lambda: session_service
    app.dependency_overrides[get_file_asset_service] = lambda: file_service
    app.dependency_overrides[get_analysis_reader_service] = lambda: reader or _FakeAnalysisReader()
    app.dependency_overrides[get_chatroom_service] = lambda: chatroom or _FakeChatroomService()
    app.dependency_overrides[get_stakeholder_llm_client] = lambda: llm
    return TestClient(app)


def test_material_review_rejects_other_users_session_id() -> None:
    session_service = _FakeTrainingSessionService(
        [_session(user_id="user-cs-001", team_id="team-service")]
    )
    file_service = _FakeFileAssetService([_material_asset()])
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 403
    assert file_service.get_calls == []


def test_material_review_rejects_material_id_outside_scope() -> None:
    session_service = _FakeTrainingSessionService([_session()])
    file_service = _FakeFileAssetService([])
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "selected_material_ids": [999]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Training material not found"
    scope = file_service.get_calls[0]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


def test_material_review_leader_uses_team_scoped_session_and_material_access() -> None:
    session_service = _FakeTrainingSessionService(
        [_session(user_id="user-sales-001", team_id="team-revenue")]
    )
    file_service = _FakeFileAssetService([_material_asset()])
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "leader"},
    )

    assert response.status_code == 200
    session_scope = session_service.get_calls[0]["access_scope"]
    assert session_scope.user_id == "user-leader-001"
    assert session_scope.team_id == "team-revenue"
    assert session_scope.include_team_scope is True
    material_scope = file_service.get_calls[0]["metadata_scope"]
    assert material_scope.user_id == "user-leader-001"
    assert material_scope.team_id == "team-revenue"
    assert material_scope.include_team_scope is True
    assert material_scope.allow_unscoped is False
    assert response.json()["data"]["referenced_materials"][0]["id"] == 7


def test_material_review_rejects_existing_material_outside_scope_without_reading_content() -> None:
    session_service = _FakeTrainingSessionService([_session()])
    file_service = _FakeFileAssetService(
        [_material_asset(owner_user_id="user-cs-001", team_id="team-service")]
    )
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Training material not found"
    assert file_service.read_calls == []


def test_material_review_drops_replay_from_room_bound_to_another_session_user() -> None:
    session_service = _FakeTrainingSessionService([_session()])
    file_service = _FakeFileAssetService([_material_asset()])
    chatroom = _FakeChatroomService(
        messages=[
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="user-cs-001",
                content="Foreign transcript must not enter material review.",
                metadata={},
            )
        ]
    )
    client = _client(session_service, file_service, chatroom=chatroom)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    assert chatroom.get_calls[0]["room_id"] == 42
    assert chatroom.get_calls[0]["message_limit"] == 40
    assert chatroom.get_calls[0]["access_scope"].unrestricted is True
    assert response.json()["data"]["source_state"]["replay_used"] is False


def test_material_review_admin_uses_explicit_scopes_without_unscoped_material_access() -> None:
    session_service = _FakeTrainingSessionService(
        [_session(user_id="user-admin-001", team_id="team-ops")]
    )
    file_service = _FakeFileAssetService(
        [_material_asset(owner_user_id="user-admin-001", team_id="team-ops")]
    )
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "admin"},
    )

    assert response.status_code == 200
    session_scope = session_service.get_calls[0]["access_scope"]
    assert session_scope is not None
    assert session_scope.user_id == "user-admin-001"
    assert session_scope.team_id == "team-ops"
    assert session_scope.include_team_scope is True
    material_scope = file_service.get_calls[0]["metadata_scope"]
    assert material_scope.user_id == "user-admin-001"
    assert material_scope.team_id == "team-ops"
    assert material_scope.include_team_scope is True
    assert material_scope.allow_unscoped is False


def test_material_review_admin_rejects_material_outside_explicit_scope() -> None:
    session_service = _FakeTrainingSessionService(
        [_session(user_id="user-admin-001", team_id="team-ops")]
    )
    file_service = _FakeFileAssetService(
        [_material_asset(owner_user_id="user-cs-001", team_id="team-service")]
    )
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "admin"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Training material not found"
    session_scope = session_service.get_calls[0]["access_scope"]
    assert session_scope.user_id == "user-admin-001"
    assert session_scope.team_id == "team-ops"
    assert session_scope.include_team_scope is True
    material_scope = file_service.get_calls[0]["metadata_scope"]
    assert material_scope.user_id == "user-admin-001"
    assert material_scope.team_id == "team-ops"
    assert material_scope.include_team_scope is True
    assert material_scope.allow_unscoped is False
    assert file_service.read_calls == []


def test_material_review_uses_optional_llm_adapter_when_configured() -> None:
    session_service = _FakeTrainingSessionService([_session()])
    file_service = _FakeFileAssetService([_material_asset()])
    llm = _FakeLLM(
        """
        {
          "matched_points": [
            {
              "material_id": 7,
              "point": "The learner paired ROI proof with a success metric.",
              "evidence": "The report says the learner used ROI proof."
            }
          ],
          "missed_points": [
            {
              "material_id": 7,
              "point": "Ask who owns renewal approval.",
              "evidence": null
            }
          ],
          "suggested_rewrites": [
            "Next drill: ask for the approval owner before proposing a discount."
          ]
        }
        """
    )
    client = _client(session_service, file_service, llm=llm)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source_state"]["strategy"] == "llm_adapter"
    assert data["source_state"]["llm_used"] is True
    assert data["matched_points"][0]["material_id"] == 7
    assert data["matched_points"][0]["material_title"] == "Renewal playbook"
    assert data["suggested_rewrites"] == [
        "Next drill: ask for the approval owner before proposing a discount."
    ]
    assert len(llm.calls) == 1
    assert session_service.mutating_calls == []


def test_material_review_llm_cannot_reference_unselected_material_ids() -> None:
    session_service = _FakeTrainingSessionService([_session()])
    file_service = _FakeFileAssetService([_material_asset()])
    llm = _FakeLLM(
        """
        {
          "matched_points": [
            {
              "material_id": 999,
              "point": "This material was never scoped into the review.",
              "evidence": "Invented evidence."
            },
            {
              "material_id": 7,
              "material_title": "Forged title",
              "point": "The learner paired ROI proof with a success metric.",
              "evidence": "The report says the learner used ROI proof."
            }
          ],
          "missed_points": [
            {
              "material_id": 999,
              "point": "Unknown material must not be returned.",
              "evidence": null
            }
          ],
          "suggested_rewrites": [
            "Next drill: pair ROI proof with the buyer's success metric."
          ]
        }
        """
    )
    client = _client(session_service, file_service, llm=llm)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    returned_ids = {
        item["material_id"] for item in data["matched_points"] + data["missed_points"]
    }
    assert returned_ids == {7}
    assert data["matched_points"][0]["material_title"] == "Renewal playbook"
    assert "999" not in response.text
    assert len(llm.calls) == 1
    assert session_service.mutating_calls == []


def test_material_review_does_not_pollute_scoring_growth_or_completion() -> None:
    session = _session()
    before = {
        "metadata": deepcopy(session.task_config.metadata),
        "status": session.status,
        "report_id": session.report_id,
        "score_id": session.score_id,
        "completed_at": session.completed_at,
        "message_count": session.message_count,
    }
    session_service = _FakeTrainingSessionService([session])
    file_service = _FakeFileAssetService([_material_asset()])
    client = _client(session_service, file_service)

    response = client.post(
        "/api/v1/training-studio/tool-consumers/review-assistant/material-review",
        json={"session_id": "training-1", "material_ids": [7]},
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    assert session_service.mutating_calls == []
    assert session.task_config.metadata == before["metadata"]
    assert session.status == before["status"]
    assert session.report_id == before["report_id"]
    assert session.score_id == before["score_id"]
    assert session.completed_at == before["completed_at"]
    assert session.message_count == before["message_count"]
