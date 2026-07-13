"""Pure domain models for the communication training studio catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from domain.common.exceptions import DomainValidationException


class ScenarioCategory(StrEnum):
    INTERVIEW = "interview"
    SALES = "sales"
    NEGOTIATION = "negotiation"
    WORKPLACE = "workplace"


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class ExpressionFramework(StrEnum):
    PREP = "prep"
    STAR = "star"
    SCQA = "scqa"
    PYRAMID = "pyramid"


class RubricDimension(StrEnum):
    SUBSTANCE = "substance"
    STRUCTURE = "structure"
    RELEVANCE = "relevance"
    CREDIBILITY = "credibility"
    DIFFERENTIATION = "differentiation"


DEFAULT_RUBRIC_VERSION = "interview-five-dimension-v1"

DEFAULT_RUBRIC_WEIGHTS: dict[ScenarioCategory, dict[RubricDimension, float]] = {
    ScenarioCategory.INTERVIEW: {
        RubricDimension.SUBSTANCE: 0.30,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.20,
        RubricDimension.CREDIBILITY: 0.15,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.SALES: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.15,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.NEGOTIATION: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.20,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
    ScenarioCategory.WORKPLACE: {
        RubricDimension.SUBSTANCE: 0.25,
        RubricDimension.STRUCTURE: 0.20,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.10,
    },
}


def _coerce_enum(enum_type: type[StrEnum], value: StrEnum | str, field_name: str) -> StrEnum:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(str(value).strip().lower())
    except ValueError as exc:
        raise DomainValidationException(
            f"Invalid {field_name}: {value}",
            field=field_name,
            details={"allowed": [item.value for item in enum_type]},
        ) from exc


def _normalize_strings(values: list[str], field_name: str) -> list[str]:
    normalized = [value.strip() for value in values if value and value.strip()]
    if not normalized:
        raise DomainValidationException(f"{field_name} cannot be empty", field=field_name)
    return normalized


@dataclass
class TrainingTaskConfig:
    role: str
    level: str
    tech_stack: list[str]
    question_type_ratios: dict[str, float]
    question_count: int
    framework: ExpressionFramework | str = ExpressionFramework.STAR
    difficulty: Difficulty | str = Difficulty.MEDIUM
    category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    rubric_version: str = DEFAULT_RUBRIC_VERSION
    rubric_weights: dict[RubricDimension | str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.role = self.role.strip()
        self.level = self.level.strip()
        if not self.role:
            raise DomainValidationException("role cannot be empty", field="role")
        if not self.level:
            raise DomainValidationException("level cannot be empty", field="level")
        if self.question_count < 1 or self.question_count > 100:
            raise DomainValidationException(
                "question_count must be between 1 and 100",
                field="question_count",
                details={"minimum": 1, "maximum": 100, "got": self.question_count},
            )

        self.category = _coerce_enum(ScenarioCategory, self.category, "category")
        self.difficulty = _coerce_enum(Difficulty, self.difficulty, "difficulty")
        self.framework = _coerce_enum(ExpressionFramework, self.framework, "framework")
        self.tech_stack = _normalize_strings(self.tech_stack, "tech_stack")
        self.question_type_ratios = self._normalize_ratios(self.question_type_ratios)

        weights = self.rubric_weights or DEFAULT_RUBRIC_WEIGHTS[self.category]
        self.rubric_weights = self._normalize_weights(weights)
        self.rubric_version = self.rubric_version.strip() or DEFAULT_RUBRIC_VERSION

    def _normalize_ratios(self, ratios: dict[str, float]) -> dict[str, float]:
        cleaned = {key.strip(): float(value) for key, value in ratios.items() if key.strip()}
        if not cleaned:
            raise DomainValidationException(
                "question_type_ratios cannot be empty",
                field="question_type_ratios",
            )
        if any(value < 0 for value in cleaned.values()):
            raise DomainValidationException(
                "question_type_ratios cannot contain negative values",
                field="question_type_ratios",
            )
        total = sum(cleaned.values())
        if total <= 0:
            raise DomainValidationException(
                "question_type_ratios total must be greater than 0",
                field="question_type_ratios",
            )
        return {key: value / total for key, value in cleaned.items()}

    def _normalize_weights(
        self,
        weights: dict[RubricDimension | str, float],
    ) -> dict[RubricDimension, float]:
        cleaned: dict[RubricDimension, float] = {}
        for key, value in weights.items():
            dimension = _coerce_enum(RubricDimension, key, "rubric_weights")
            cleaned[dimension] = float(value)
        missing = [dimension for dimension in RubricDimension if dimension not in cleaned]
        if missing:
            raise DomainValidationException(
                "rubric_weights must include all rubric dimensions",
                field="rubric_weights",
                details={"missing": [dimension.value for dimension in missing]},
            )
        if any(value < 0 for value in cleaned.values()):
            raise DomainValidationException(
                "rubric_weights cannot contain negative values",
                field="rubric_weights",
            )
        total = sum(cleaned.values())
        if total <= 0:
            raise DomainValidationException(
                "rubric_weights total must be greater than 0",
                field="rubric_weights",
            )
        return {dimension: value / total for dimension, value in cleaned.items()}


def normalize_training_task_config(config: TrainingTaskConfig) -> TrainingTaskConfig:
    """Return a freshly validated config with normalized ratios and weights."""

    return TrainingTaskConfig(
        role=config.role,
        level=config.level,
        tech_stack=list(config.tech_stack),
        question_type_ratios=dict(config.question_type_ratios),
        question_count=config.question_count,
        framework=config.framework,
        difficulty=config.difficulty,
        category=config.category,
        rubric_version=config.rubric_version,
        rubric_weights=dict(config.rubric_weights),
    )
