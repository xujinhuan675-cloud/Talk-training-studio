from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    get_chatroom_service,
    get_conversation_service,
    reset_ai_rate_limit_state,
)
from api.routes.training_studio import (
    get_live_guidance_service,
    get_training_session_service,
    router as training_router,
)
from application.dto import ConversationDTO, MessageDTO_Agent
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.live_guidance_service import TrainingLiveGuidanceService
from core.exceptions import register_exception_handlers
from domain.training_studio.session import TrainingSession


def _task_config():
    return TrainingTaskConfigDTO(
        role="Account Manager",
        level="Senior",
        tech_stack=["Renewal"],
        question_type_ratios={"craft": 1},
        question_count=3,
        category="sales",
        metadata={"persona_ids": ["persona-1"]},
    ).to_domain()


def _session() -> TrainingSession:
    session = TrainingSession(
        session_id="session-source",
        task_config=_task_config(),
        mode="text",
        user_id="user-sales-001",
        team_id="team-revenue",
    )
    session.start("talkwise-conversation:7")
    return session


def _conversation(*, training_session_id: str = "session-source") -> ConversationDTO:
    now = datetime.now(UTC)
    return ConversationDTO(
        id=7,
        title="Renewal practice",
        system_prompt=None,
        model="gpt-test",
        status="active",
        metadata={
            "runtime": "conversation_message_tree",
            "trainingSessionId": training_session_id,
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
        },
        created_at=now,
        updated_at=now,
    )


def _path() -> list[MessageDTO_Agent]:
    now = datetime.now(UTC)
    return [
        MessageDTO_Agent(
            id=1,
            conversation_id=7,
            role="user",
            content="We can start with a small pilot.",
            public_id="msg-user",
            parent_message_id=None,
            branch_id="main",
            created_at=now,
        ),
        MessageDTO_Agent(
            id=2,
            conversation_id=7,
            role="assistant",
            content="I am worried the budget is still too risky.",
            public_id="msg-tail",
            parent_message_id="msg-user",
            branch_id="branch-budget",
            created_at=now,
        ),
    ]


class _FakeTrainingSessionService:
    def __init__(self, *, deny: bool = False, fail_record: bool = False) -> None:
        self.session = _session()
        self.deny = deny
        self.fail_record = fail_record
        self.get_scopes = []
        self.record_calls = []

    async def get_session(self, session_id: str, *, access_scope):
        self.get_scopes.append(access_scope)
        if self.deny:
            raise PermissionError("Training session is outside current user scope")
        if session_id != self.session.session_id:
            raise ValueError(f"Training session not found: {session_id}")
        return self.session

    async def record_session_metadata(self, session_id: str, *, metadata, access_scope):
        self.record_calls.append((session_id, metadata, access_scope))
        if self.fail_record:
            raise RuntimeError("simulated metadata storage failure")
        self.session.task_config.metadata = {
            **self.session.task_config.metadata,
            **metadata,
        }
        return self.session


class _FakeConversationService:
    def __init__(self, *, training_session_id: str = "session-source") -> None:
        self.conversation = _conversation(training_session_id=training_session_id)
        self.get_calls = []
        self.path_calls = []

    async def get_conversation(self, conversation_id: int, *, metadata_scope):
        self.get_calls.append((conversation_id, metadata_scope))
        return self.conversation

    async def get_message_path(
        self,
        conversation_id: int,
        message_public_id: str,
        **kwargs,
    ):
        self.path_calls.append((conversation_id, message_public_id, kwargs))
        return _path()


class _UnusedChatroomService:
    async def get_room_detail(self, *args, **kwargs):
        raise AssertionError("message-tree guidance must not read a legacy room")


def _client(
    session_service,
    conversation_service,
    *,
    guidance_service: TrainingLiveGuidanceService | None = None,
) -> TestClient:
    reset_ai_rate_limit_state()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(training_router, prefix="/api/v1")
    app.dependency_overrides[get_training_session_service] = lambda: session_service
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    app.dependency_overrides[get_chatroom_service] = lambda: _UnusedChatroomService()
    app.dependency_overrides[get_live_guidance_service] = lambda: (
        guidance_service or TrainingLiveGuidanceService()
    )
    return TestClient(app)


def _guidance_path(suffix: str = "") -> str:
    return f"/api/v1/training-studio/sessions/session-source/guidance{suffix}"


def test_message_tree_guidance_reads_owned_selected_path() -> None:
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService()
    response = _client(sessions, conversations).get(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        params={"selected_tail_message_id": "msg-tail", "message_limit": 12},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "message_tree"
    assert data["context_runtime"] == "message_tree"
    assert data["context_selection"] == "selected_path"
    assert data["selected_tail_message_id"] == "msg-tail"
    assert data["total_turn_count"] == 2
    assert data["capabilities"] == {
        "refresh": True,
        "stream": False,
        "persistence": True,
        "history": True,
        "server_selected_path": True,
    }
    assert data["persistence"] == {
        "status": "not_requested",
        "retryable": False,
        "persisted": False,
    }
    assert {event["event_type"] for event in data["events"]}.issuperset({"risk", "next_reply"})
    assert conversations.get_calls[0][0] == 7
    assert conversations.get_calls[0][1].user_id == "user-sales-001"
    assert conversations.get_calls[0][1].allow_unscoped is False
    assert conversations.path_calls[0][:2] == (7, "msg-tail")
    assert conversations.path_calls[0][2]["limit"] == 200
    assert conversations.path_calls[0][2]["statuses"] == ["active"]
    assert conversations.path_calls[0][2]["metadata_scope"].user_id == "user-sales-001"


def test_message_tree_guidance_prefers_server_path_when_request_also_sends_turns() -> None:
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService()
    response = _client(sessions, conversations).post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={
            "selected_tail_message_id": "msg-tail",
            "recent_turns": [{"speaker": "user", "text": "forged request context"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["source"] == "message_tree"
    assert response.json()["data"]["persistence"]["status"] == "ready"
    assert len(sessions.record_calls) == 1
    assert conversations.path_calls[0][1] == "msg-tail"


def test_message_tree_guidance_keeps_explicit_recent_turns_compatible_without_tail() -> None:
    conversations = _FakeConversationService()
    response = _client(_FakeTrainingSessionService(), conversations).post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={"recent_turns": [{"speaker": "user", "text": "Can we start?"}]},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "request"
    assert data["context_selection"] == "client_recent_turns"
    assert conversations.get_calls == []
    assert conversations.path_calls == []


def test_message_tree_guidance_requires_selected_tail_for_server_refresh() -> None:
    conversations = _FakeConversationService()
    response = _client(_FakeTrainingSessionService(), conversations).get(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 409
    assert "selected_tail_message_id is required" in response.json()["message"]
    assert conversations.get_calls == []


def test_message_tree_guidance_rejects_session_outside_authenticated_scope() -> None:
    conversations = _FakeConversationService()
    response = _client(_FakeTrainingSessionService(deny=True), conversations).get(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        params={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 403
    assert conversations.get_calls == []


def test_message_tree_guidance_rejects_conversation_session_binding_mismatch() -> None:
    conversations = _FakeConversationService(training_session_id="session-other")
    response = _client(_FakeTrainingSessionService(), conversations).get(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        params={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 409
    assert "not bound" in response.json()["message"]
    assert conversations.path_calls == []


def test_message_tree_guidance_stream_is_explicitly_unsupported() -> None:
    response = _client(_FakeTrainingSessionService(), _FakeConversationService()).get(
        _guidance_path("/stream"),
        headers={"X-Mock-User": "sales"},
        params={"max_events": 1},
    )

    assert response.status_code == 409
    assert "streaming is not supported" in response.json()["message"]


def test_message_tree_guidance_persistence_is_explicitly_unsupported() -> None:
    response = _client(_FakeTrainingSessionService(), _FakeConversationService()).post(
        _guidance_path("-events"),
        headers={"X-Mock-User": "sales"},
        json={
            "events": [
                {
                    "event_type": "risk",
                    "severity": "warning",
                    "title": "Budget objection",
                    "message": "Acknowledge the budget concern.",
                }
            ]
        },
    )

    assert response.status_code == 409
    assert "persistence is not supported" in response.json()["message"]


def test_message_tree_guidance_persists_only_server_generated_selected_path_events() -> None:
    class _CapturingGuidanceService(TrainingLiveGuidanceService):
        def __init__(self) -> None:
            super().__init__()
            self.calls = []

        async def generate_guidance_async(self, **kwargs):
            self.calls.append(kwargs)
            return await super().generate_guidance_async(**kwargs)

    sessions = _FakeTrainingSessionService()
    guidance = _CapturingGuidanceService()
    response = _client(
        sessions,
        _FakeConversationService(),
        guidance_service=guidance,
    ).post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={
            "selected_tail_message_id": "msg-tail",
            "task_goal": "forged task goal",
            "rubric": {"forged": 1},
            "recent_turns": [{"speaker": "user", "text": "forged request context"}],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["persistence"]["status"] == "ready"
    assert data["persistence"]["persisted"] is True
    assert data["persistence"]["retryable"] is False
    assert guidance.calls[0]["task_goal"] != "forged task goal"
    assert guidance.calls[0]["rubric"] != {"forged": 1}
    assert len(sessions.record_calls) == 1
    patch = sessions.record_calls[0][1]
    history = patch["liveGuidanceHistory"]
    assert len(history) == 1
    assert history[0]["selectedTailMessageId"] == "msg-tail"
    assert history[0]["source"] == "message_tree"
    assert history[0]["contextSelection"] == "selected_path"
    assert history[0]["events"] == data["events"]
    assert "clientMetadata" not in history[0]
    assert "forged request context" not in str(history[0])


def test_message_tree_guidance_history_revalidates_selected_path_and_scope() -> None:
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService()
    client = _client(sessions, conversations)
    generated = client.post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )
    assert generated.status_code == 200

    response = client.get(
        _guidance_path("-history"),
        headers={"X-Mock-User": "sales"},
        params={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ready"
    assert data["selectedTailMessageId"] == "msg-tail"
    assert data["historyCount"] == 1
    assert data["history"][0]["snapshotId"] == generated.json()["data"]["persistence"]["snapshotId"]
    assert conversations.path_calls[-1][1] == "msg-tail"
    assert conversations.path_calls[-1][2]["metadata_scope"].user_id == "user-sales-001"


def test_message_tree_guidance_reports_retryable_persistence_failure_without_faking_success() -> (
    None
):
    sessions = _FakeTrainingSessionService(fail_record=True)
    response = _client(sessions, _FakeConversationService()).post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["events"]
    assert data["persistence"] == {
        "status": "failed",
        "retryable": True,
        "persisted": False,
        "code": "guidance_persistence_failed",
        "selectedTailMessageId": "msg-tail",
    }


def test_message_tree_guidance_rejects_client_identity_fields() -> None:
    response = _client(_FakeTrainingSessionService(), _FakeConversationService()).post(
        _guidance_path(),
        headers={"X-Mock-User": "sales"},
        json={
            "selected_tail_message_id": "msg-tail",
            "user_id": "forged-user",
            "team_id": "forged-team",
        },
    )

    assert response.status_code == 422
