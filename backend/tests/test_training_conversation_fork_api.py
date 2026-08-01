from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_conversation_service
from api.routes.training_studio import (
    get_training_session_service,
    router as training_router,
)
from application.dto import (
    ConversationDTO,
    ForkConversationResultDTO,
    MessageDTO_Agent,
)
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
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


def _session(*, room_id: str = "talkwise-conversation:7") -> TrainingSession:
    session = TrainingSession(
        session_id="session-source",
        task_config=_task_config(),
        mode="text",
        user_id="user-sales-001",
        team_id="team-revenue",
    )
    session.start(room_id)
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
            "authScope": {
                "userId": "user-sales-001",
                "teamId": "team-revenue",
            },
        },
        created_at=now,
        updated_at=now,
    )


class _FakeTrainingSessionService:
    def __init__(self, *, deny_source: bool = False, fail_start: bool = False) -> None:
        self.source = _session()
        self.deny_source = deny_source
        self.fail_start = fail_start
        self.forked: TrainingSession | None = None
        self.get_scopes = []
        self.fork_scopes = []
        self.start_calls = []
        self.record_turn_calls = []
        self.deleted: list[str] = []

    async def get_session(self, session_id: str, *, access_scope):
        self.get_scopes.append(access_scope)
        if self.deny_source:
            raise PermissionError("Training session is outside current user scope")
        if session_id != self.source.session_id:
            raise ValueError(f"Training session not found: {session_id}")
        return self.source

    async def fork_session(self, session_id: str, *, access_scope):
        self.fork_scopes.append(access_scope)
        assert session_id == self.source.session_id
        self.forked = TrainingSession(
            session_id="session-fork",
            task_config=deepcopy(self.source.task_config),
            mode=self.source.mode,
            scenario_template_id=self.source.scenario_template_id,
            user_id=self.source.user_id,
            team_id=self.source.team_id,
        )
        return self.forked

    async def start_session(self, session_id: str, room_id: str, *, metadata, access_scope):
        assert self.forked is not None
        assert session_id == self.forked.session_id
        self.start_calls.append((session_id, room_id, dict(metadata), access_scope))
        if self.fail_start:
            raise RuntimeError("start failed")
        self.forked.task_config.metadata.update(deepcopy(dict(metadata)))
        self.forked.start(room_id)
        return self.forked

    async def record_turns(self, session_id: str, count: int, *, access_scope):
        assert self.forked is not None
        assert session_id == self.forked.session_id
        self.record_turn_calls.append((session_id, count, access_scope))
        self.forked.record_turn(count)
        return self.forked

    async def delete_session(self, session_id: str, *, access_scope):
        self.deleted.append(session_id)


class _FakeConversationService:
    def __init__(
        self,
        *,
        training_session_id: str = "session-source",
        fail_fork: bool = False,
    ) -> None:
        self.source = _conversation(training_session_id=training_session_id)
        self.fail_fork = fail_fork
        self.get_calls = []
        self.fork_call = None
        self.deleted: list[int] = []

    async def get_conversation(self, conversation_id: int, *, metadata_scope):
        self.get_calls.append((conversation_id, metadata_scope))
        return self.source

    async def fork_conversation(
        self,
        conversation_id: int,
        message_public_id: str,
        payload,
        *,
        metadata_scope,
    ):
        self.fork_call = (
            conversation_id,
            message_public_id,
            payload,
            metadata_scope,
        )
        if self.fail_fork:
            raise RuntimeError("fork failed")
        now = datetime.now(UTC)
        message = MessageDTO_Agent(
            id=81,
            conversation_id=8,
            role="assistant",
            content="Forked answer",
            public_id="msg-forked",
            branch_id="main",
            created_at=now,
        )
        return ForkConversationResultDTO(
            conversation=ConversationDTO(
                id=8,
                title=payload.title or self.source.title,
                system_prompt=None,
                model=self.source.model,
                status="active",
                metadata={
                    **self.source.metadata,
                    **dict(payload.metadata),
                    "selectedPath": {
                        "messageIds": ["msg-forked"],
                        "affectsScoring": False,
                        "affectsCompletion": False,
                    },
                },
                created_at=now,
                updated_at=now,
            ),
            messages=[message],
            source_to_forked_id={message_public_id: "msg-forked"},
        )

    async def delete_conversation(self, conversation_id: int, *, metadata_scope):
        self.deleted.append(conversation_id)


def _client(session_service, conversation_service, *, raise_server_exceptions: bool = True):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(training_router, prefix="/api/v1")
    app.dependency_overrides[get_training_session_service] = lambda: session_service
    app.dependency_overrides[get_conversation_service] = lambda: conversation_service
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _fork_path() -> str:
    return "/api/v1/training-studio/sessions/session-source/conversation/messages/msg-source/fork"


def test_training_conversation_fork_creates_fresh_active_session_and_sanitizes_metadata():
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService()
    client = _client(sessions, conversations)

    response = client.post(
        _fork_path(),
        headers={"X-Mock-User": "sales"},
        json={
            "title": "Renewal review fork",
            "option": "directPath",
            "metadata": {
                "fork_reason": "manager review",
                "ownerUserId": "forged-user",
                "teamId": "forged-team",
                "authScope": {"userId": "forged-user"},
                "trainingSessionId": "forged-session",
                "score": 100,
                "completed": True,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["training_session"]["session_id"] == "session-fork"
    assert data["training_session"]["status"] == "active"
    assert data["training_session"]["room_id"] == "talkwise-conversation:8"
    assert data["training_session"]["message_count"] == 1
    assert data["conversation"]["metadata"]["trainingSessionId"] == "session-fork"
    assert data["source_to_forked_id"] == {"msg-source": "msg-forked"}
    assert conversations.fork_call is not None
    payload = conversations.fork_call[2]
    assert payload.metadata == {
        "fork_reason": "manager review",
        "trainingSessionId": "session-fork",
        "forkedFromTrainingSessionId": "session-source",
    }
    assert conversations.fork_call[3].user_id == "user-sales-001"
    assert conversations.fork_call[3].allow_unscoped is False
    assert sessions.fork_scopes[0].user_id == "user-sales-001"
    assert sessions.record_turn_calls[0][1] == 1


def test_training_conversation_fork_rejects_session_outside_authenticated_scope():
    sessions = _FakeTrainingSessionService(deny_source=True)
    conversations = _FakeConversationService()
    response = _client(sessions, conversations).post(
        _fork_path(),
        headers={"X-Mock-User": "sales"},
        json={},
    )

    assert response.status_code == 403
    assert conversations.get_calls == []
    assert conversations.fork_call is None


def test_training_conversation_fork_rejects_session_conversation_binding_mismatch():
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService(training_session_id="session-other")
    response = _client(sessions, conversations).post(
        _fork_path(),
        headers={"X-Mock-User": "sales"},
        json={},
    )

    assert response.status_code == 409
    assert sessions.forked is None
    assert conversations.fork_call is None


def test_training_conversation_fork_cleans_up_created_session_when_tree_fork_fails():
    sessions = _FakeTrainingSessionService()
    conversations = _FakeConversationService(fail_fork=True)
    response = _client(
        sessions,
        conversations,
        raise_server_exceptions=False,
    ).post(
        _fork_path(),
        headers={"X-Mock-User": "sales"},
        json={},
    )

    assert response.status_code == 500
    assert sessions.deleted == ["session-fork"]


def test_training_conversation_fork_cleans_up_both_resources_when_binding_fails():
    sessions = _FakeTrainingSessionService(fail_start=True)
    conversations = _FakeConversationService()
    response = _client(
        sessions,
        conversations,
        raise_server_exceptions=False,
    ).post(
        _fork_path(),
        headers={"X-Mock-User": "sales"},
        json={},
    )

    assert response.status_code == 500
    assert conversations.deleted == [8]
    assert sessions.deleted == ["session-fork"]
