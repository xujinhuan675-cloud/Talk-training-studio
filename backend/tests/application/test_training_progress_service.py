from __future__ import annotations

import pytest

from application.services.training_studio.training_progress_service import (
    count_finalized_learner_turns,
    evaluate_training_progress,
)


def _metadata(*, source: str = "scenario_training", profile: str = "standard") -> dict:
    return {
        "source": source,
        "question_count": 9,
        "trainingPlan": {
            "length": {"profile": profile},
        },
        "scenario_training": {
            "training_points": ["conclusion", "facts", "next-step"],
            "dimension_weights": [
                {"dimensionId": "structure", "weight": 50},
                {"dimensionId": "substance", "weight": 50},
            ],
        },
    }


def _complete_evidence() -> dict:
    return {
        "coveredTrainingPoints": ["conclusion", "facts", "next-step"],
        "coveredRubric": ["structure", "substance"],
        "evidenceCount": 3,
    }


def test_counts_only_finalized_learner_turns() -> None:
    assert count_finalized_learner_turns(
        [
            {"role": "user", "status": "finalized"},
            {"role": "assistant", "status": "finalized"},
            {"role": "learner", "finalized": True},
            {"role": "user", "finalized": False},
            {"role": "user", "status": "streaming"},
        ]
    ) == 2


def test_non_scenario_training_does_not_enable_policy() -> None:
    assert (
        evaluate_training_progress(
            _metadata(source="battle_prep"),
            finalized_learner_turns=9,
            evidence=_complete_evidence(),
        )
        is None
    )


def test_length_profiles_use_configurable_default_limits() -> None:
    expected = {
        "quick": (3, 6, 8),
        "standard": (5, 9, 12),
        "complete": (7, 12, 16),
    }

    for profile, limits in expected.items():
        progress = evaluate_training_progress(
            _metadata(profile=profile), finalized_learner_turns=0
        )

        assert progress is not None
        assert (
            progress["minimumTurns"],
            progress["targetTurns"],
            progress["hardCapTurns"],
        ) == limits


def test_plan_metadata_can_override_each_turn_limit() -> None:
    metadata = _metadata(profile="standard")
    metadata["trainingPlan"]["length"].update(
        {"minimumTurns": 4, "turnBudget": 7, "hardCapTurns": 10}
    )

    progress = evaluate_training_progress(metadata, finalized_learner_turns=0)

    assert progress is not None
    assert progress["minimumTurns"] == 4
    assert progress["targetTurns"] == 7
    assert progress["hardCapTurns"] == 10


def test_target_is_ready_without_an_external_evidence_evaluator() -> None:
    progress = evaluate_training_progress(
        _metadata(), finalized_learner_turns=9
    )

    assert progress is not None
    assert progress["state"] == "ready_to_finish"
    assert progress["evidence"]["sufficient"] is None
    assert progress["canFinish"] is True
    assert progress["shouldFinish"] is False
    assert progress["reasonCodes"] == ["target_turns_reached"]


def test_user_requested_finish_is_immediately_actionable() -> None:
    progress = evaluate_training_progress(
        _metadata(), finalized_learner_turns=2, user_requested_finish=True
    )

    assert progress is not None
    assert progress["state"] == "ready_to_finish"
    assert progress["canFinish"] is True
    assert progress["shouldFinish"] is True
    assert progress["reasonCodes"] == ["user_requested_finish"]


def test_sufficient_structured_evidence_can_finish_after_minimum() -> None:
    progress = evaluate_training_progress(
        _metadata(), finalized_learner_turns=5, evidence=_complete_evidence()
    )

    assert progress is not None
    assert progress["state"] == "ready_to_finish"
    assert progress["reasonCodes"] == ["objective_coverage_complete"]
    assert progress["objectives"]["coveredCount"] == 5
    assert progress["objectives"]["totalCount"] == 5
    assert progress["evidence"]["coverageRatio"] == 1.0
    assert progress["evidence"]["sufficient"] is True


def test_insufficient_structured_evidence_extends_to_hard_cap() -> None:
    at_target = evaluate_training_progress(
        _metadata(), finalized_learner_turns=9, evidence={"evidenceCount": 1}
    )
    at_cap = evaluate_training_progress(
        _metadata(), finalized_learner_turns=12, evidence={"evidenceCount": 1}
    )

    assert at_target is not None
    assert at_target["state"] == "in_progress"
    assert at_target["evidence"]["sufficient"] is False
    assert at_target["canFinish"] is False
    assert at_cap is not None
    assert at_cap["state"] == "hard_limit_reached"
    assert at_cap["canFinish"] is True
    assert at_cap["shouldFinish"] is True
    assert at_cap["reasonCodes"] == ["hard_cap_reached"]


def test_completed_progress_is_terminal_without_requesting_another_finish() -> None:
    progress = evaluate_training_progress(
        _metadata(), finalized_learner_turns=6, completed=True
    )

    assert progress is not None
    assert progress["state"] == "completed"
    assert progress["canFinish"] is False
    assert progress["shouldFinish"] is False
    assert progress["reasonCodes"] == ["session_completed"]


def test_custom_plan_uses_explicit_turn_budget_then_question_count() -> None:
    metadata = _metadata(profile="custom")
    metadata["trainingPlan"]["length"] = {
        "profile": "custom",
        "turnBudget": 7,
    }
    progress = evaluate_training_progress(metadata, finalized_learner_turns=7)

    assert progress is not None
    assert progress["targetTurns"] == 7
    assert progress["minimumTurns"] == 5
    assert progress["hardCapTurns"] == 10


def test_training_source_alias_enables_policy() -> None:
    metadata = _metadata()
    metadata["training_source"] = metadata.pop("source")

    assert evaluate_training_progress(metadata, finalized_learner_turns=0) is not None


def test_negative_finalized_turn_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="finalized_learner_turns"):
        evaluate_training_progress(_metadata(), finalized_learner_turns=-1)
