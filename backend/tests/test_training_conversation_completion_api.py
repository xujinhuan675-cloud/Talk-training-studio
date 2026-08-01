from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_conversation_service,
    get_growth_service,
    reset_ai_rate_limit_state,
)
from api.routes.training_studio import (
    get_training_runtime_uow_factory,
    get_training_session_service,
    router as training_router,
)
from application.dto import ConversationDTO, MessageDTO_Agent
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from core.exceptions import register_exception_handlers
from domain.training_studio.session import TrainingSession, TrainingSessionStatus


class _Report(BaseModel):
    id: int
    room_id: int
    summary: str = "Selected-path report"
    content: dict = Field(default_factory=dict)


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
            "personaIds": ["persona-1"],
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


class _SessionService:
    def __init__(self) -> None:
        self.session = _session()
        self.metadata_calls: list[dict] = []
        self.complete_calls: list[dict] = []

    async def get_session(self, session_id: str, *, access_scope):
        if session_id != self.session.session_id:
            raise ValueError(f"Training session not found: {session_id}")
        if access_scope.user_id != self.session.user_id:
            raise PermissionError("Training session is outside current user scope")
        return self.session

    async def complete_session(
        self,
        session_id: str,
        report_id=None,
        score_id=None,
        *,
        metadata=None,
        access_scope,
    ):
        await self.get_session(session_id, access_scope=access_scope)
        self.complete_calls.append(dict(metadata or {}))
        self.session.task_config.metadata.update(dict(metadata or {}))
        self.session.complete(report_id=report_id, score_id=score_id)
        return self.session

    async def record_session_metadata(self, session_id: str, *, metadata, access_scope):
        await self.get_session(session_id, access_scope=access_scope)
        self.metadata_calls.append(dict(metadata))
        self.session.task_config.metadata.update(dict(metadata))
        return self.session


class _ConversationService:
    def __init__(self, *, training_session_id: str = "session-source") -> None:
        self.conversation = _conversation(training_session_id=training_session_id)
        self.path_calls: list[tuple] = []

    async def get_conversation(self, conversation_id: int, *, metadata_scope):
        assert conversation_id == 7
        assert metadata_scope.user_id == "user-sales-001"
        return self.conversation

    async def get_message_path(self, conversation_id: int, message_public_id: str, **kwargs):
        self.path_calls.append((conversation_id, message_public_id, kwargs))
        return _path()


class _ProjectionState:
    def __init__(self) -> None:
        self.rooms: dict[int, object] = {}
        self.messages: list[object] = []
        self.deleted_room_ids: list[int] = []
        self.next_room_id = 900


class _ProjectionRoomRepository:
    def __init__(self, state: _ProjectionState) -> None:
        self.state = state

    async def create(self, room):
        room.id = self.state.next_room_id
        self.state.next_room_id += 1
        self.state.rooms[room.id] = room
        return room

    async def update_context_summary(self, room_id, summary, up_to_message_id):
        self.state.rooms[room_id].context_summary = summary
        self.state.rooms[room_id].summary_up_to_message_id = up_to_message_id

    async def delete(self, room_id):
        self.state.deleted_room_ids.append(room_id)
        self.state.rooms.pop(room_id, None)
        self.state.messages = [item for item in self.state.messages if item.room_id != room_id]
        return True


class _ProjectionMessageRepository:
    def __init__(self, state: _ProjectionState) -> None:
        self.state = state

    async def create(self, message):
        message.id = len(self.state.messages) + 1
        self.state.messages.append(message)
        return message


class _ProjectionUnitOfWork:
    def __init__(self, state: _ProjectionState, **_kwargs) -> None:
        self.chat_room_repository = _ProjectionRoomRepository(state)
        self.stakeholder_message_repository = _ProjectionMessageRepository(state)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def get_repository(self, name: str):
        return {
            "chat_room_repository": self.chat_room_repository,
            "stakeholder_message_repository": self.stakeholder_message_repository,
        }.get(name)


class _AnalysisService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[int, object]] = []
        self.reports: dict[int, _Report] = {}

    async def generate_report(self, room_id: int, *, access_scope):
        self.calls.append((room_id, access_scope))
        if self.fail:
            raise RuntimeError("evaluation provider unavailable")
        report = _Report(id=501, room_id=room_id)
        self.reports[report.id] = report
        return report


class _ReaderService:
    def __init__(self, analysis: _AnalysisService) -> None:
        self.analysis = analysis
        self.calls: list[tuple[int, int, object]] = []

    async def get_report(self, report_id: int, *, room_id: int, access_scope):
        self.calls.append((report_id, room_id, access_scope))
        return self.analysis.reports.get(report_id)


class _GrowthService:
    def __init__(self, *, mode: str = "ready") -> None:
        self.mode = mode
        self.calls: list[int] = []

    async def evaluate_competency(self, report_id: int):
        self.calls.append(report_id)
        if self.mode == "unavailable":
            return None
        if self.mode == "failed":
            raise RuntimeError("judge provider unavailable")
        return SimpleNamespace(id=601, overall_score=4.2)


def _client(
    *,
    fail_analysis: bool = False,
    binding: str = "session-source",
    growth_mode: str = "ready",
):
    reset_ai_rate_limit_state()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(training_router, prefix="/api/v1")
    sessions = _SessionService()
    conversations = _ConversationService(training_session_id=binding)
    projections = _ProjectionState()
    analysis = _AnalysisService(fail=fail_analysis)
    reader = _ReaderService(analysis)
    growth = _GrowthService(mode=growth_mode)
    app.dependency_overrides[get_training_session_service] = lambda: sessions
    app.dependency_overrides[get_conversation_service] = lambda: conversations
    app.dependency_overrides[get_training_runtime_uow_factory] = lambda: (
        lambda **kwargs: _ProjectionUnitOfWork(projections, **kwargs)
    )
    app.dependency_overrides[get_analysis_service] = lambda: analysis
    app.dependency_overrides[get_analysis_reader_service] = lambda: reader
    app.dependency_overrides[get_growth_service] = lambda: growth
    return TestClient(app), sessions, conversations, projections, analysis, reader, growth


def _complete_path() -> str:
    return "/api/v1/training-studio/sessions/session-source/complete"


def _report_path() -> str:
    return "/api/v1/training-studio/sessions/session-source/report"


def test_message_tree_completion_uses_server_path_and_reuses_report_pipeline() -> None:
    client, sessions, conversations, projections, analysis, reader, growth = _client()

    response = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 200
    completed = response.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "501"
    assert completed["score_id"] == "601"
    report_state = completed["task_config"]["metadata"]["completionReport"]
    assert report_state["status"] == "ready"
    assert report_state["runtime"] == "message_tree"
    assert report_state["reportId"] == "501"
    assert report_state["analysisRoomId"] == 900
    assert report_state["selectedTailMessageId"] == "msg-tail"
    assert report_state["evaluation"]["status"] == "ready"
    assert completed["task_config"]["metadata"]["selectedPath"]["affectsScoring"] is True
    assert completed["task_config"]["metadata"]["selectedPath"]["affectsCompletion"] is True
    assert conversations.path_calls[0][0:2] == (7, "msg-tail")
    assert conversations.path_calls[0][2]["statuses"] == ["active"]
    assert len(projections.messages) == 2
    assert projections.messages[0].metadata["sourceMessageId"] == "msg-user"
    assert analysis.calls[0][1].guarded_by_training_session_id == "session-source"
    assert analysis.calls[0][1].guarded_room_id == "900"
    assert growth.calls == [501]

    report_response = client.get(_report_path(), headers={"X-Mock-User": "sales"})
    assert report_response.status_code == 200
    assert report_response.json()["data"]["id"] == 501
    assert reader.calls[0][1] == 900
    assert reader.calls[0][2].guarded_room_id == "900"

    repeated = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["report_id"] == "501"
    assert len(analysis.calls) == 1
    assert len(sessions.complete_calls) == 1


def test_message_tree_completion_failure_keeps_session_active_and_retryable() -> None:
    client, sessions, _conversations, projections, analysis, _reader, growth = _client(
        fail_analysis=True
    )

    response = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 502
    assert sessions.session.status == TrainingSessionStatus.ACTIVE
    assert sessions.session.report_id is None
    failure = sessions.session.task_config.metadata["completionReport"]
    assert failure["status"] == "failed"
    assert failure["retryable"] is True
    assert failure["completedWithoutReport"] is False
    assert projections.rooms == {}
    assert projections.deleted_room_ids == [900]
    assert len(analysis.calls) == 1
    assert growth.calls == []

    report_response = client.get(_report_path(), headers={"X-Mock-User": "sales"})
    assert report_response.status_code == 409
    assert "training_session_report_not_ready" in report_response.text


def test_message_tree_report_can_complete_with_truthful_unavailable_evaluation() -> None:
    client, sessions, _conversations, _projections, _analysis, _reader, growth = _client(
        growth_mode="unavailable"
    )

    response = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 200
    completed = response.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "501"
    assert completed["score_id"] is None
    evaluation = completed["task_config"]["metadata"]["completionReport"]["evaluation"]
    assert evaluation["status"] == "unavailable"
    assert evaluation["retryable"] is True
    assert sessions.session.status == TrainingSessionStatus.COMPLETED
    assert growth.calls == [501]


def test_message_tree_report_can_complete_with_truthful_failed_evaluation() -> None:
    client, sessions, _conversations, _projections, _analysis, _reader, growth = _client(
        growth_mode="failed"
    )

    response = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )

    assert response.status_code == 200
    completed = response.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "501"
    assert completed["score_id"] is None
    evaluation = completed["task_config"]["metadata"]["completionReport"]["evaluation"]
    assert evaluation["status"] == "failed"
    assert evaluation["errorType"] == "RuntimeError"
    assert evaluation["retryable"] is True
    assert sessions.session.status == TrainingSessionStatus.COMPLETED
    assert growth.calls == [501]


def test_message_tree_completion_rejects_unbound_or_forged_completion_inputs() -> None:
    client, sessions, conversations, projections, analysis, _reader, growth = _client(
        binding="session-other"
    )

    unbound = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )
    assert unbound.status_code == 409
    assert "not bound" in unbound.text
    assert sessions.session.status == TrainingSessionStatus.ACTIVE
    assert conversations.path_calls == []
    assert projections.rooms == {}
    assert analysis.calls == []
    assert growth.calls == []

    forged = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={
            "selected_tail_message_id": "msg-tail",
            "report_id": 999,
            "score_id": 888,
            "metadata": {"score": 100, "completed": True},
        },
    )
    assert forged.status_code == 422


def test_message_tree_completion_is_idempotent_only_for_same_selected_path() -> None:
    client, _sessions, _conversations, _projections, _analysis, _reader, _growth = _client()
    first = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-tail"},
    )
    assert first.status_code == 200

    different_path = client.post(
        _complete_path(),
        headers={"X-Mock-User": "sales"},
        json={"selected_tail_message_id": "msg-other"},
    )
    assert different_path.status_code == 409
    assert "different selected path" in different_path.text


def test_legacy_session_forged_completion_metadata_cannot_switch_report_room() -> None:
    client, sessions, _conversations, _projections, analysis, reader, _growth = _client()
    sessions.session.room_id = "42"
    sessions.session.complete(report_id="777")
    sessions.session.task_config.metadata["completionReport"] = {
        "status": "ready",
        "runtime": "message_tree",
        "reportId": "777",
        "analysisRoomId": 900,
        "conversationId": "7",
    }
    analysis.reports[777] = _Report(id=777, room_id=900)

    response = client.get(_report_path(), headers={"X-Mock-User": "sales"})

    assert response.status_code == 404
    assert reader.calls[0][1] == 42
    assert reader.calls[0][2].guarded_room_id == "42"


def test_message_tree_report_metadata_must_match_bound_conversation() -> None:
    client, sessions, _conversations, _projections, analysis, reader, _growth = _client()
    sessions.session.complete(report_id="777")
    sessions.session.task_config.metadata["completionReport"] = {
        "status": "ready",
        "runtime": "message_tree",
        "reportId": "777",
        "analysisRoomId": 900,
        "conversationId": "8",
    }
    analysis.reports[777] = _Report(id=777, room_id=900)

    response = client.get(_report_path(), headers={"X-Mock-User": "sales"})

    assert response.status_code == 404
    assert reader.calls == []
