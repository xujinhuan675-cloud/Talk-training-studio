"""Shared feedback-mode contract for every Training Studio runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class TrainingFeedbackMode(StrEnum):
    SIMULATION = "simulation"
    ASSISTED = "assisted"
    DRILL = "drill"


@dataclass(frozen=True)
class TrainingFeedbackContract:
    mode: TrainingFeedbackMode
    reply_language: str

    @property
    def guidance_enabled(self) -> bool:
        return self.mode != TrainingFeedbackMode.SIMULATION

    @property
    def correction_only(self) -> bool:
        return self.mode == TrainingFeedbackMode.DRILL


def resolve_training_feedback_contract(
    metadata: Mapping[str, object] | None,
    *,
    default_mode: TrainingFeedbackMode | str = TrainingFeedbackMode.SIMULATION,
    default_language: str = "en-US",
) -> TrainingFeedbackContract:
    metadata = metadata if isinstance(metadata, Mapping) else {}
    scenario = _mapping(metadata.get("scenario_training") or metadata.get("scenarioTraining"))
    policy = _mapping(metadata.get("feedbackPolicy") or metadata.get("feedback_policy"))
    mode = _feedback_mode(
        metadata.get("feedbackMode")
        or metadata.get("feedback_mode")
        or metadata.get("trainingFeedbackMode")
        or metadata.get("training_feedback_mode")
        or policy.get("mode")
        or scenario.get("feedbackMode")
        or scenario.get("feedback_mode"),
        default=default_mode,
    )
    language = _reply_language(metadata, scenario=scenario) or _clean_text(default_language)
    return TrainingFeedbackContract(
        mode=mode,
        reply_language=language or "en-US",
    )


def counterpart_feedback_instruction(mode: TrainingFeedbackMode | str) -> str:
    resolved = _feedback_mode(mode, default=TrainingFeedbackMode.SIMULATION)
    common = (
        "Stay fully in the scenario counterpart role and keep the visible reply natural. "
        "Never put coaching labels, scores, correction explanations, or suggested rewrites "
        "inside the counterpart reply."
    )
    if resolved == TrainingFeedbackMode.SIMULATION:
        return (
            f"{common} Do not correct the learner during the conversation; reserve all critique "
            "for the post-session review."
        )
    if resolved == TrainingFeedbackMode.ASSISTED:
        return (
            f"{common} Side coaching is generated through a separate product event channel; "
            "do not mention or imitate that guidance."
        )
    return (
        f"{common} Per-turn correction and retry guidance is generated as separate structured "
        "data; answer only as the counterpart."
    )


def reply_language_instruction(language: str | None) -> str | None:
    normalized = _clean_text(language)
    if not normalized:
        return None
    return (
        f"Reply in the training session language {normalized}. Preserve names, product terms, "
        "and quoted learner text in their original language when appropriate."
    )


def localized_guidance_text(language: str, *, english: str, chinese: str) -> str:
    return chinese if language.lower().startswith("zh") else english


def _feedback_mode(
    value: object,
    *,
    default: TrainingFeedbackMode | str,
) -> TrainingFeedbackMode:
    if isinstance(value, TrainingFeedbackMode):
        return value
    normalized = _clean_text(value)
    if normalized:
        try:
            return TrainingFeedbackMode(normalized.lower())
        except ValueError:
            pass
    if isinstance(default, TrainingFeedbackMode):
        return default
    try:
        return TrainingFeedbackMode(str(default).strip().lower())
    except ValueError:
        return TrainingFeedbackMode.SIMULATION


def _reply_language(
    metadata: Mapping[str, object],
    *,
    scenario: Mapping[str, object],
) -> str | None:
    nested = _mapping(metadata.get("language"))
    return _first_text(
        nested.get("replyLanguage"),
        nested.get("reply_language"),
        nested.get("locale"),
        metadata.get("replyLanguage"),
        metadata.get("reply_language"),
        metadata.get("trainingReplyLanguage"),
        metadata.get("training_reply_language"),
        metadata.get("locale"),
        scenario.get("replyLanguage"),
        scenario.get("reply_language"),
        scenario.get("language"),
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _first_text(*values: object) -> str | None:
    for value in values:
        if text := _clean_text(value):
            return text
    return None


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


__all__ = [
    "TrainingFeedbackContract",
    "TrainingFeedbackMode",
    "counterpart_feedback_instruction",
    "localized_guidance_text",
    "reply_language_instruction",
    "resolve_training_feedback_contract",
]
