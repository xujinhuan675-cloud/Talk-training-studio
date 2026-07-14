import pytest

from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import (
    TrainingSession,
    TrainingSessionMode,
    TrainingSessionStatus,
)


def make_task_config() -> TrainingTaskConfig:
    return TrainingTaskConfig(
        role="Product Manager",
        level="Senior",
        tech_stack=["Roadmap", "Metrics"],
        question_type_ratios={"behavioral": 1, "craft": 1},
        question_count=4,
    )


def test_training_session_start_record_and_complete():
    session = TrainingSession(
        session_id="session-1",
        task_config=make_task_config(),
        mode="text",
    )

    session.start("room-1")
    session.record_turn()
    session.record_turn(2)
    session.complete(report_id="report-1", score_id="score-1")

    assert session.mode == TrainingSessionMode.TEXT
    assert session.status == TrainingSessionStatus.COMPLETED
    assert session.room_id == "room-1"
    assert session.started_at is not None
    assert session.completed_at is not None
    assert session.report_id == "report-1"
    assert session.score_id == "score-1"
    assert session.message_count == 3


def test_training_session_rejects_invalid_transitions():
    session = TrainingSession(
        session_id="session-1",
        task_config=make_task_config(),
        mode="voice",
    )

    with pytest.raises(ValueError, match="Cannot complete"):
        session.complete()

    with pytest.raises(ValueError, match="Cannot record"):
        session.record_turn()

    session.start("room-1")
    session.complete()

    with pytest.raises(ValueError, match="Cannot start"):
        session.start("room-2")

    with pytest.raises(ValueError, match="Cannot fail"):
        session.fail("late failure")


def test_training_session_fail_records_reason():
    session = TrainingSession(
        session_id="session-1",
        task_config=make_task_config(),
        mode="realtime",
    )

    session.fail("room creation failed")

    assert session.status == TrainingSessionStatus.FAILED
    assert session.failure_reason == "room creation failed"
    assert session.completed_at is not None


def test_training_session_rejects_non_positive_turn_count():
    session = TrainingSession(
        session_id="session-1",
        task_config=make_task_config(),
        mode="video",
    )
    session.start("room-1")

    with pytest.raises(ValueError, match="count"):
        session.record_turn(0)
