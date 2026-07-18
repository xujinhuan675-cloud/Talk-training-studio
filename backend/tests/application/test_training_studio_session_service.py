import pytest
from types import SimpleNamespace

from application.services.training_studio.session_service import (
    InMemoryTrainingSessionRepository,
    TrainingSessionService,
)
from domain.training_studio.session import TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope

pytestmark = pytest.mark.asyncio


def make_payload() -> dict:
    return {
        "role": "Product Manager",
        "level": "Senior",
        "tech_stack": ["Roadmap", "Metrics"],
        "question_type_ratios": {"behavioral": 2, "craft": 1},
        "question_count": 6,
        "mode": "text",
    }


async def test_session_service_create_start_complete_with_room_creator():
    created_for = []

    def room_creator(session):
        created_for.append(session.session_id)
        return f"room-{session.session_id}"

    service = TrainingSessionService(
        room_creator=room_creator,
        id_factory=lambda: "session-1",
    )

    session = await service.create_session(make_payload())
    started = await service.start_session(session.session_id)
    completed = await service.complete_session(
        session.session_id,
        report_id="report-1",
        score_id="score-1",
    )

    assert created_for == ["session-1"]
    assert started.room_id == "room-session-1"
    assert completed.status == TrainingSessionStatus.COMPLETED
    assert completed.report_id == "report-1"
    assert completed.score_id == "score-1"
    assert await service.get_session("session-1") is completed
    assert await service.list_sessions() == [completed]


async def test_session_service_tracks_scenario_progress():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(
        {
            **make_payload(),
            "scenario_template_id": "new-customer-discount",
            "user_id": "user-sales-001",
            "team_id": "team-revenue",
        }
    )
    await service.start_session(session.session_id, room_id="42")
    await service.complete_session(session.session_id, report_id="report-1")

    progress = await service.list_scenario_progress(user_id="user-sales-001", team_id="team-revenue")

    assert len(progress) == 1
    assert progress[0].scenario_id == "new-customer-discount"
    assert progress[0].user_id == "user-sales-001"
    assert progress[0].team_id == "team-revenue"
    assert progress[0].status == "completed"
    assert progress[0].failure_reason is None
    assert progress[0].score is None
    assert progress[0].score_status == "pending"
    assert progress[0].training_session_id == "session-1"
    assert progress[0].report_id == "report-1"


async def test_session_service_can_fail_session():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(make_payload())
    failed = await service.fail_session(session.session_id, "room creation failed")

    assert failed.status == TrainingSessionStatus.FAILED
    assert failed.failure_reason == "room creation failed"
    assert failed.completed_at is not None
    assert await service.get_session("session-1") is failed


async def test_session_service_records_turn_count():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(make_payload())
    await service.start_session(session.session_id, room_id="42")
    updated = await service.record_turns(session.session_id, 3)

    assert updated.message_count == 3
    assert (await service.get_session("session-1")).message_count == 3


async def test_session_service_start_merges_runtime_metadata_when_started():
    service = TrainingSessionService(id_factory=lambda: "session-1")
    session = await service.create_session(
        {
            **make_payload(),
            "metadata": {"source": "scenario_training"},
        }
    )
    runtime_metadata = {
        "runtime": "conversation_message_tree",
        "selectedPath": {
            "branchId": "branch-review",
            "tailMessageId": "msg-tail",
            "messageIds": ["msg-root", "msg-tail"],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "currentBranchTail": {
            "branchId": "branch-review",
            "messageId": "msg-tail",
        },
    }

    started = await service.start_session(
        session.session_id,
        room_id="talkwise-conversation:7",
        metadata=runtime_metadata,
    )
    runtime_metadata["selectedPath"]["tailMessageId"] = "mutated"

    assert started.room_id == "talkwise-conversation:7"
    assert started.task_config.metadata["source"] == "scenario_training"
    assert started.task_config.metadata["runtime"] == "conversation_message_tree"
    assert started.task_config.metadata["selectedPath"]["tailMessageId"] == "msg-tail"
    assert (await service.get_session("session-1")).task_config.metadata[
        "currentBranchTail"
    ] == {
        "branchId": "branch-review",
        "messageId": "msg-tail",
    }


async def test_session_service_applies_access_scope_to_get_list_and_mutations():
    session_ids = iter(["session-sales", "session-peer", "session-service"])
    service = TrainingSessionService(id_factory=lambda: next(session_ids))
    sales = await service.create_session(
        {
            **make_payload(),
            "user_id": "user-sales-001",
            "team_id": "team-revenue",
        }
    )
    peer = await service.create_session(
        {
            **make_payload(),
            "user_id": "user-peer-001",
            "team_id": "team-revenue",
        }
    )
    service_session = await service.create_session(
        {
            **make_payload(),
            "user_id": "user-cs-001",
            "team_id": "team-service",
        }
    )

    staff_scope = TrainingSessionAccessScope(
        user_id="user-sales-001",
        team_id="team-revenue",
    )
    leader_scope = TrainingSessionAccessScope(
        user_id="user-sales-lead-001",
        team_id="team-revenue",
        include_team_scope=True,
    )

    assert await service.get_session(sales.session_id, access_scope=staff_scope) is sales
    with pytest.raises(PermissionError, match="outside current user scope"):
        await service.get_session(service_session.session_id, access_scope=staff_scope)
    with pytest.raises(PermissionError, match="outside current user scope"):
        await service.start_session(service_session.session_id, room_id="42", access_scope=staff_scope)

    staff_sessions = await service.list_sessions(access_scope=staff_scope)
    leader_sessions = await service.list_sessions(access_scope=leader_scope)

    assert [session.session_id for session in staff_sessions] == [sales.session_id]
    assert [session.session_id for session in leader_sessions] == [
        sales.session_id,
        peer.session_id,
    ]


async def test_session_service_progress_preserves_failed_status_and_reason():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(
        {
            **make_payload(),
            "scenario_template_id": "new-customer-discount",
            "user_id": "user-sales-001",
            "team_id": "team-revenue",
        }
    )
    await service.start_session(session.session_id, room_id="42")
    await service.fail_session(session.session_id, "analysis failed")

    progress = await service.list_scenario_progress(user_id="user-sales-001", team_id="team-revenue")

    assert len(progress) == 1
    assert progress[0].status == "failed"
    assert progress[0].failure_reason == "analysis failed"
    assert progress[0].score_status == "pending"


async def test_session_service_selected_branch_metadata_is_not_scoring_completion_state():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(
        {
            **make_payload(),
            "scenario_template_id": "new-customer-discount",
            "user_id": "user-sales-001",
            "metadata": {
                "branchPolicy": {"owner": "training_core"},
                "selectedPath": {
                    "branchId": "branch-review",
                    "tailMessageId": "msg-tail",
                    "purpose": "training_replay_context",
                    "affectsScoring": True,
                    "affectsCompletion": True,
                },
                "currentBranchTail": {
                    "branchId": "branch-review",
                    "messageId": "msg-tail",
                },
                "evaluation": {"status": "completed", "overall_score": 5},
                "growth_report": {"status": "completed", "report_id": "shadow-report"},
            },
        }
    )
    await service.start_session(session.session_id, room_id="42")

    progress = await service.list_scenario_progress(user_id="user-sales-001")

    assert len(progress) == 1
    assert progress[0].status == "in_progress"
    assert progress[0].score is None
    assert progress[0].score_status == "pending"
    assert progress[0].report_id is None
    assert progress[0].score_id is None


async def test_session_service_complete_merges_branch_metadata_into_task_config():
    service = TrainingSessionService(id_factory=lambda: "session-1")
    session = await service.create_session(
        {
            **make_payload(),
            "scenario_template_id": "new-customer-discount",
            "user_id": "user-sales-001",
            "metadata": {
                "source": "scenario_training",
                "scenario_training": {"id": "new-customer-discount"},
            },
        }
    )
    await service.start_session(session.session_id, room_id="42")
    completion_metadata = {
        "messageTreeSelection": {
            "provider": "talkwise-conversation",
            "conversationId": "7",
            "selectedMessageId": "msg-tail",
            "branchId": "branch-review",
            "path": [
                {"publicId": "msg-root", "role": "user", "content": "Can we revisit pricing?"},
                {
                    "publicId": "msg-tail",
                    "role": "assistant",
                    "content": "Use a measurable pilot.",
                    "branchId": "branch-review",
                },
            ],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "selectedPath": {
            "branchId": "branch-review",
            "tailMessageId": "msg-tail",
            "messageIds": ["msg-root", "msg-tail"],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "currentBranchTail": {
            "branchId": "branch-review",
            "messageId": "msg-tail",
        },
    }

    completed = await service.complete_session(
        session.session_id,
        report_id="report-1",
        metadata=completion_metadata,
    )
    completion_metadata["messageTreeSelection"]["path"][0]["publicId"] = "mutated"

    assert completed.task_config.metadata["source"] == "scenario_training"
    assert completed.task_config.metadata["scenario_training"] == {
        "id": "new-customer-discount"
    }
    assert completed.task_config.metadata["messageTreeSelection"]["selectedMessageId"] == (
        "msg-tail"
    )
    assert completed.task_config.metadata["messageTreeSelection"]["path"][0]["publicId"] == (
        "msg-root"
    )
    assert completed.task_config.metadata["selectedPath"]["affectsScoring"] is False
    progress = await service.list_scenario_progress(user_id="user-sales-001")
    assert progress[0].status == "completed"
    assert progress[0].report_id == "report-1"
    assert progress[0].score_status == "pending"


class FakeTrainingUow:
    def __init__(self, repository, evaluations):
        self.training_session_repository = repository
        self.competency_evaluation_repository = evaluations

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeEvaluationRepository:
    def __init__(self, evaluations):
        self.evaluations = evaluations

    async def get_by_report_id(self, report_id: int):
        return self.evaluations.get(report_id)


async def test_session_service_progress_uses_competency_evaluation_scores():
    session_ids = iter(["session-1", "session-2"])
    repository = InMemoryTrainingSessionRepository()
    evaluations = FakeEvaluationRepository({
        501: SimpleNamespace(id=12, overall_score=4.25),
    })
    service = TrainingSessionService(
        uow_factory=lambda **_: FakeTrainingUow(repository, evaluations),
        id_factory=lambda: next(session_ids),
    )

    first = await service.create_session({
        **make_payload(),
        "scenario_template_id": "new-customer-discount",
        "user_id": "user-sales-001",
        "team_id": "team-revenue",
    })
    await service.start_session(first.session_id, room_id="42")
    await service.complete_session(first.session_id, report_id="501")

    second = await service.create_session({
        **make_payload(),
        "scenario_template_id": "new-customer-discount",
        "user_id": "admin",
        "team_id": "team-ops",
    })
    await service.start_session(second.session_id, room_id="43")
    await service.complete_session(second.session_id, report_id="502")

    progress = await service.list_scenario_progress(user_id="user-sales-001")

    assert len(progress) == 1
    assert progress[0].training_session_id == "session-1"
    assert progress[0].score_status == "ready"
    assert progress[0].score == 85
    assert progress[0].overall_score == 4.25
    assert progress[0].evaluation_id == 12


async def test_session_service_can_start_with_explicit_room_id():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = await service.create_session(make_payload(), mode="voice")
    started = await service.start_session(session.session_id, room_id="room-explicit")

    assert started.status == TrainingSessionStatus.ACTIVE
    assert started.room_id == "room-explicit"


async def test_session_service_requires_room_creator_without_room_id():
    service = TrainingSessionService(id_factory=lambda: "session-1")
    session = await service.create_session(make_payload())

    with pytest.raises(ValueError, match="room_creator"):
        await service.start_session(session.session_id)


async def test_session_service_rejects_unknown_session():
    service = TrainingSessionService()

    with pytest.raises(ValueError, match="not found"):
        await service.get_session("missing-session")
