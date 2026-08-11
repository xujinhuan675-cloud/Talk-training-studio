"""Deterministic completion policy shared by training runtimes.

The service deliberately does not inspect an LLM decision.  Callers provide
only finalized learner-turn counts and structured evidence coverage collected
by their runtime/evaluator.  This keeps the end condition auditable and lets
text, turn-based voice, and realtime voice use the same policy.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from math import ceil
from numbers import Real
from typing import Any

_TRAINING_SOURCES = {"scenario_training", "battle_prep"}
_PROFILE_LIMITS = {
    "quick": {"minimum": 3, "target": 6, "hard_cap": 8},
    "standard": {"minimum": 5, "target": 9, "hard_cap": 12},
    "complete": {"minimum": 7, "target": 12, "hard_cap": 16},
}
_DEFAULT_TARGET_TURNS = 9
_MINIMUM_TURN_RATIO = 2 / 3
_HARD_CAP_RATIO = 4 / 3
_MINIMUM_EVIDENCE_COUNT = 2
_COVERAGE_THRESHOLD = 0.75


def count_finalized_learner_turns(turns: Iterable[Mapping[str, Any]]) -> int:
    """Count learner turns explicitly marked finalized.

    Runtime adapters may pass transcript/event dictionaries here.  A turn is
    counted only when its role identifies the learner and one of the explicit
    finalized markers is truthy.  In-progress STT fragments and assistant
    turns are ignored.
    """

    count = 0
    for turn in turns:
        if not isinstance(turn, Mapping):
            continue
        role = _text(
            turn.get("role")
            or turn.get("speaker")
            or turn.get("senderType")
            or turn.get("sender_type")
        )
        if role not in {"user", "learner", "human"}:
            continue
        finalized = turn.get("finalized")
        status = _text(turn.get("status") or turn.get("state"))
        if finalized is True or status == "finalized":
            count += 1
    return count


def evaluate_training_progress(
    metadata: Mapping[str, Any] | None,
    *,
    finalized_learner_turns: int,
    evidence: Mapping[str, Any] | None = None,
    user_requested_finish: bool = False,
    completed: bool = False,
) -> dict[str, Any] | None:
    """Return persistable progress metadata for a supported training session.

    ``evidence`` is intentionally structured rather than free-form.  Accepted
    fields are ``coveredTrainingPoints``/``covered_training_points``,
    ``coveredRubric``/``covered_rubric``, and ``evidenceCount``/
    ``evidence_count``.  A caller can also provide a numeric ``coverageRatio``
    when the evaluator has already normalized coverage.  Scenario metadata may
    expose ``trainingPoints``/``training_points`` and ``rubric`` or
    ``dimensionWeights``/``dimension_weights`` as the required criteria.

    ``None`` means the policy is disabled for the metadata source. The returned object is the
    shared ``trainingProgress`` metadata contract.  A target turn count is
    enough to become ready even when no evaluator has supplied evidence;
    structured sufficient evidence can make a session ready after the
    minimum.  The hard cap is always actionable.
    """

    if not _is_supported_training(metadata):
        return None

    turn_count = _non_negative_int(finalized_learner_turns, "finalized_learner_turns")
    plan = _mapping(metadata.get("trainingPlan") or metadata.get("training_plan"))
    length = _mapping(plan.get("length"))
    completion = _mapping(plan.get("completion"))
    profile = (_text(length.get("profile") or length.get("lengthProfile")) or "").lower()
    minimum_turns, target_turns, hard_cap = _turn_limits(
        profile,
        plan,
        length,
        completion,
        metadata,
    )

    scenario = _mapping(metadata.get("scenario_training") or metadata.get("scenarioTraining"))
    required_points = _string_list(
        scenario.get("trainingPoints") or scenario.get("training_points")
    )
    required_rubric = _rubric_keys(
        scenario.get("rubric")
        or scenario.get("dimensionWeights")
        or scenario.get("dimension_weights")
    )
    coverage = _coverage_summary(
        evidence,
        required_points=required_points,
        required_rubric=required_rubric,
    )
    evidence_sufficient = _evidence_sufficient(evidence, coverage)
    covered_count = _matched_count(
        coverage["requiredTrainingPoints"], coverage["coveredTrainingPoints"]
    ) + _matched_count(coverage["requiredRubric"], coverage["coveredRubric"])
    total_count = len(coverage["requiredTrainingPoints"]) + len(
        coverage["requiredRubric"]
    )

    if completed:
        state = "completed"
        can_finish = False
        should_finish = False
        reason_codes = ["session_completed"]
    elif turn_count >= hard_cap:
        state = "hard_limit_reached"
        can_finish = True
        should_finish = True
        reason_codes = ["hard_cap_reached"]
    elif user_requested_finish:
        state = "ready_to_finish"
        can_finish = True
        should_finish = True
        reason_codes = ["user_requested_finish"]
    elif turn_count >= minimum_turns and evidence_sufficient is True:
        state = "ready_to_finish"
        can_finish = True
        should_finish = False
        reason_codes = ["objective_coverage_complete"]
    elif turn_count >= target_turns and evidence_sufficient is not False:
        state = "ready_to_finish"
        can_finish = True
        should_finish = False
        reason_codes = ["target_turns_reached"]
    else:
        state = "in_progress"
        can_finish = False
        should_finish = False
        reason_codes = (
            ["minimum_turns_not_reached"]
            if turn_count < minimum_turns
            else ["evidence_insufficient"]
        )

    return {
        "state": state,
        "learnerTurnCount": turn_count,
        "minimumTurns": minimum_turns,
        "targetTurns": target_turns,
        "hardCapTurns": hard_cap,
        "objectives": {
            "coveredCount": covered_count,
            "totalCount": total_count,
            "coveredTrainingPoints": coverage["coveredTrainingPoints"],
            "requiredTrainingPoints": coverage["requiredTrainingPoints"],
            "coveredRubric": coverage["coveredRubric"],
            "requiredRubric": coverage["requiredRubric"],
        },
        "evidence": {
            "sufficient": evidence_sufficient,
            "coverageRatio": coverage["coverageRatio"],
            "evidenceCount": coverage["evidenceCount"],
        },
        "canFinish": can_finish,
        "shouldFinish": should_finish,
        "reasonCodes": reason_codes,
    }


def _is_supported_training(metadata: Mapping[str, Any] | None) -> bool:
    if not isinstance(metadata, Mapping):
        return False
    return (
        _text(
            metadata.get("source")
            or metadata.get("trainingSource")
            or metadata.get("training_source")
        )
        in _TRAINING_SOURCES
    )


def _turn_limits(
    profile: str | None,
    plan: Mapping[str, Any],
    length: Mapping[str, Any],
    completion: Mapping[str, Any],
    metadata: Mapping[str, Any],
) -> tuple[int, int, int]:
    defaults = _PROFILE_LIMITS.get(profile or "")
    target = _first_positive(
        length,
        "targetTurns",
        "target_turns",
        "turnBudget",
        "turn_budget",
    )
    if target is None:
        target = _first_positive(plan, "targetTurns", "target_turns", "turnBudget", "turn_budget")
    if target is None:
        target = _first_positive(completion, "targetTurns", "target_turns")
    if target is None:
        target = (
            defaults["target"]
            if defaults is not None
            else _positive_int(
                metadata.get("question_count") or metadata.get("questionCount")
            )
            or _DEFAULT_TARGET_TURNS
        )

    minimum = _first_positive(
        length,
        "minimumTurns",
        "minimum_turns",
        "minTurns",
        "min_turns",
    )
    if minimum is None:
        minimum = _first_positive(
            plan,
            "minimumTurns",
            "minimum_turns",
            "minTurns",
            "min_turns",
        )
    if minimum is None:
        minimum = _first_positive(completion, "minimumTurns", "minimum_turns", "minTurns")
    if minimum is None:
        minimum = (
            defaults["minimum"]
            if defaults is not None
            else max(1, ceil(target * _MINIMUM_TURN_RATIO))
        )

    hard_cap = _first_positive(
        length,
        "hardCapTurns",
        "hard_cap_turns",
        "hardCap",
        "hard_cap",
    )
    if hard_cap is None:
        hard_cap = _first_positive(
            plan,
            "hardCapTurns",
            "hard_cap_turns",
            "hardCap",
            "hard_cap",
        )
    if hard_cap is None:
        hard_cap = _first_positive(
            completion,
            "hardCapTurns",
            "hard_cap_turns",
            "hardCap",
        )
    if hard_cap is None:
        hard_cap = (
            defaults["hard_cap"]
            if defaults is not None
            else max(target + 1, ceil(target * _HARD_CAP_RATIO))
        )

    return min(max(1, minimum), target), target, max(target, hard_cap)


def _first_positive(mapping: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = _positive_int(mapping.get(key))
        if value is not None:
            return value
    return None


def _coverage_summary(
    evidence: Mapping[str, Any] | None,
    *,
    required_points: Sequence[str],
    required_rubric: Sequence[str],
) -> dict[str, Any]:
    evidence = evidence if isinstance(evidence, Mapping) else {}
    covered_points = _string_list(
        evidence.get("coveredTrainingPoints") or evidence.get("covered_training_points")
    )
    covered_rubric = _string_list(
        evidence.get("coveredRubric") or evidence.get("covered_rubric")
    )

    # A normalized evaluator may provide a ratio directly.  Otherwise compute
    # it from independently declared training-point and rubric coverage.
    explicit_ratio = _ratio(
        evidence.get("coverageRatio")
        if evidence.get("coverageRatio") is not None
        else evidence.get("coverage_ratio")
    )
    ratios: list[float] = []
    if required_points:
        ratios.append(_set_coverage(required_points, covered_points))
    if required_rubric:
        ratios.append(_set_coverage(required_rubric, covered_rubric))
    coverage_ratio = explicit_ratio if explicit_ratio is not None else min(ratios, default=0.0)

    evidence_count = _positive_int(
        evidence.get("evidenceCount")
        if evidence.get("evidenceCount") is not None
        else evidence.get("evidence_count")
    )
    if evidence_count is None:
        items = evidence.get("items") or evidence.get("observations") or evidence.get("anchors")
        evidence_count = (
            len(items)
            if isinstance(items, Sequence) and not isinstance(items, (str, bytes))
            else 0
        )
    if evidence_count == 0:
        evidence_count = len(set(covered_points) | set(covered_rubric))

    return {
        "coverageRatio": round(min(max(coverage_ratio, 0.0), 1.0), 3),
        "coveredTrainingPoints": list(dict.fromkeys(covered_points)),
        "coveredRubric": list(dict.fromkeys(covered_rubric)),
        "requiredTrainingPoints": list(required_points),
        "requiredRubric": list(required_rubric),
        "evidenceCount": evidence_count,
    }


def _evidence_sufficient(
    evidence: Mapping[str, Any] | None,
    coverage: Mapping[str, Any],
) -> bool | None:
    if evidence is None:
        return None
    explicit = evidence.get("sufficient")
    if isinstance(explicit, bool):
        return explicit
    # A persisted progress snapshot always contains an evidence object.  An
    # empty snapshot is not an evaluator verdict and must remain unknown so a
    # target-turn recommendation can still be reached.
    if (
        coverage["evidenceCount"] == 0
        and coverage["coverageRatio"] == 0
        and not coverage["coveredTrainingPoints"]
        and not coverage["coveredRubric"]
    ):
        return None
    return bool(
        coverage["evidenceCount"] >= _MINIMUM_EVIDENCE_COUNT
        and coverage["coverageRatio"] >= _COVERAGE_THRESHOLD
    )


def _matched_count(required: Sequence[str], covered: Sequence[str]) -> int:
    required_set = {item.casefold() for item in required}
    covered_set = {item.casefold() for item in covered}
    return len(required_set & covered_set)


def _set_coverage(required: Sequence[str], covered: Sequence[str]) -> float:
    required_set = {item.casefold() for item in required}
    if not required_set:
        return 0.0
    covered_set = {item.casefold() for item in covered}
    return len(required_set & covered_set) / len(required_set)


def _rubric_keys(value: object) -> list[str]:
    if isinstance(value, Mapping):
        return _string_list(value.keys())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        keys: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                key = _text(
                    item.get("id")
                    or item.get("dimensionId")
                    or item.get("dimension_id")
                    or item.get("name")
                )
                if key:
                    keys.append(key)
            else:
                key = _text(item)
                if key:
                    keys.append(key)
        return keys
    return []


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    values: list[str] = []
    for item in value:
        text = _text(item)
        if text:
            values.append(text)
    return list(dict.fromkeys(values))


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Real):
        try:
            parsed = int(value)
        except (OverflowError, ValueError):
            return None
        if parsed == value and parsed > 0:
            return parsed
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    if isinstance(value, Real):
        try:
            parsed = int(value)
        except (OverflowError, ValueError):
            parsed = -1
        if parsed == value and parsed >= 0:
            return parsed
    if isinstance(value, str):
        try:
            parsed = int(value.strip())
        except ValueError:
            parsed = -1
        if parsed >= 0:
            return parsed
    raise ValueError(f"{field_name} must be a non-negative integer")


def _ratio(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return None
    return ratio if 0 <= ratio <= 1 else None
