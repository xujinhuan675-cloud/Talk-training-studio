"""Evidence and N/A rules for communication-core-v1 evaluation."""

from application.services.stakeholder.growth_service import (
    _bounded_evaluation_messages,
    _build_assessment_payload,
    _evaluation_message_id,
)
from domain.stakeholder.entity import Message


def _dimension(rating, evidence, *, opportunity=True):
    return {
        "opportunity_present": opportunity,
        "rating": rating,
        "evidence": evidence,
        "reason": "observed",
        "suggestion": "try a specific follow-up",
    }


def _outcome(rating, evidence):
    return {"rating": rating, "evidence": evidence, "reason": "observed"}


def _parsed(**overrides):
    empty = _dimension(None, [], opportunity=False)
    competencies = {
        "attentiveness": dict(empty),
        "expression": dict(empty),
        "coordination": dict(empty),
        "composure": dict(empty),
    }
    competencies.update(overrides)
    evidence = [{"message_id": "msg-1", "quote": "I understand the budget concern"}]
    return {
        "effectiveness": _outcome(4, evidence),
        "appropriateness": _outcome(4, evidence),
        "competencies": competencies,
    }


def test_missing_or_unverifiable_evidence_is_na_instead_of_default_three():
    payload, outcome = _build_assessment_payload(
        _parsed(
            expression=_dimension(
                3,
                [{"message_id": "msg-user", "quote": "a quote that was never said"}],
            )
        ),
        user_messages={"msg-user": "The real learner response."},
    )

    assert payload["status"] == "insufficient_evidence"
    assert payload["competencies"]["expression"]["rating"] is None
    assert payload["effectiveness"]["rating"] is None
    assert payload["appropriateness"]["rating"] is None
    assert outcome is None


def test_rating_five_requires_two_independent_verified_evidence_items():
    one_evidence = [{"message_id": "msg-1", "quote": "I understand the budget concern"}]
    payload, outcome = _build_assessment_payload(
        _parsed(attentiveness=_dimension(5, one_evidence)),
        user_messages={"msg-1": "I understand the budget concern."},
    )
    assert payload["competencies"]["attentiveness"]["rating"] is None
    assert payload["effectiveness"]["rating"] == 4
    assert payload["appropriateness"]["rating"] == 4
    assert outcome == 4.0

    two_evidence = one_evidence + [
        {"message_id": "msg-2", "quote": "which part creates the most risk"}
    ]
    payload, outcome = _build_assessment_payload(
        _parsed(attentiveness=_dimension(5, two_evidence)),
        user_messages={
            "msg-1": "I understand the budget concern.",
            "msg-2": "which part creates the most risk for your team?",
        },
    )
    assert payload["competencies"]["attentiveness"]["rating"] == 5
    assert outcome == 4.0


def test_rating_five_cannot_reuse_two_quotes_from_the_same_message():
    payload, _ = _build_assessment_payload(
        _parsed(
            expression=_dimension(
                5,
                [
                    {"message_id": "msg-1", "quote": "The pilot is limited"},
                    {"message_id": "msg-1", "quote": "we will review it Friday"},
                ],
            )
        ),
        user_messages={
            "msg-1": "The pilot is limited to one team, and we will review it Friday."
        },
    )

    assert payload["competencies"]["expression"]["rating"] is None


def test_task_outcomes_require_their_own_verified_evidence():
    parsed = _parsed(
        expression=_dimension(
            3,
            [{"message_id": "msg-1", "quote": "I understand the budget concern"}],
        )
    )
    parsed["effectiveness"] = _outcome(
        5,
        [{"message_id": "msg-1", "quote": "a result that was never said"}],
    )
    parsed["appropriateness"] = _outcome(
        4,
        [{"message_id": "msg-1", "quote": "I understand the budget concern"}],
    )

    payload, outcome = _build_assessment_payload(
        parsed,
        user_messages={"msg-1": "I understand the budget concern."},
    )

    assert payload["effectiveness"]["rating"] is None
    assert payload["appropriateness"]["rating"] == 4
    assert outcome is None


def test_selected_path_context_limits_messages_and_preserves_public_ids():
    selected = Message(
        id=11,
        room_id=3,
        sender_type="user",
        sender_id="learner",
        content="Selected branch answer",
        metadata={"sourceMessageId": "msg-selected"},
    )
    other = Message(
        id=12,
        room_id=3,
        sender_type="user",
        sender_id="learner",
        content="Other branch answer",
        metadata={"sourceMessageId": "msg-other"},
    )

    bounded = _bounded_evaluation_messages(
        [selected, other],
        {"messages": [{"message_id": "msg-selected"}]},
    )

    assert bounded == [selected]
    assert _evaluation_message_id(selected) == "msg-selected"
