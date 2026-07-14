import pytest

from application.services.training_studio.session_service import (
    TrainingSessionService,
)
from domain.training_studio.session import TrainingSessionStatus


def make_payload() -> dict:
    return {
        "role": "Product Manager",
        "level": "Senior",
        "tech_stack": ["Roadmap", "Metrics"],
        "question_type_ratios": {"behavioral": 2, "craft": 1},
        "question_count": 6,
        "mode": "text",
    }


def test_session_service_create_start_complete_with_room_creator():
    created_for = []

    def room_creator(session):
        created_for.append(session.session_id)
        return f"room-{session.session_id}"

    service = TrainingSessionService(
        room_creator=room_creator,
        id_factory=lambda: "session-1",
    )

    session = service.create_session(make_payload())
    started = service.start_session(session.session_id)
    completed = service.complete_session(
        session.session_id,
        report_id="report-1",
        score_id="score-1",
    )

    assert created_for == ["session-1"]
    assert started.room_id == "room-session-1"
    assert completed.status == TrainingSessionStatus.COMPLETED
    assert completed.report_id == "report-1"
    assert completed.score_id == "score-1"
    assert service.get_session("session-1") is completed
    assert service.list_sessions() == [completed]


def test_session_service_can_start_with_explicit_room_id():
    service = TrainingSessionService(id_factory=lambda: "session-1")

    session = service.create_session(make_payload(), mode="voice")
    started = service.start_session(session.session_id, room_id="room-explicit")

    assert started.status == TrainingSessionStatus.ACTIVE
    assert started.room_id == "room-explicit"


def test_session_service_requires_room_creator_without_room_id():
    service = TrainingSessionService(id_factory=lambda: "session-1")
    session = service.create_session(make_payload())

    with pytest.raises(ValueError, match="room_creator"):
        service.start_session(session.session_id)


def test_session_service_rejects_unknown_session():
    service = TrainingSessionService()

    with pytest.raises(ValueError, match="not found"):
        service.get_session("missing-session")
