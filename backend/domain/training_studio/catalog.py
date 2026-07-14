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
    PRODUCT_MANAGEMENT = "product_management"


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
    ScenarioCategory.PRODUCT_MANAGEMENT: {
        RubricDimension.SUBSTANCE: 0.22,
        RubricDimension.STRUCTURE: 0.18,
        RubricDimension.RELEVANCE: 0.25,
        RubricDimension.CREDIBILITY: 0.20,
        RubricDimension.DIFFERENTIATION: 0.15,
    },
}


@dataclass(frozen=True)
class RolePreset:
    value: str
    category: ScenarioCategory
    label: str
    description: str
    default_level: str
    default_focus: list[str]
    default_question_type_ratios: dict[str, float]


@dataclass(frozen=True)
class ScenarioPreset:
    value: str
    category: ScenarioCategory
    label: str
    description: str
    counterpart_role: str
    context_prompt: str
    suggested_role_values: list[str]
    default_framework: ExpressionFramework
    default_difficulty: Difficulty
    default_question_type_ratios: dict[str, float]


PRODUCT_MANAGEMENT_ROLE_PRESETS: tuple[RolePreset, ...] = (
    RolePreset(
        value="core_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Product Manager",
        description="Owns discovery, roadmap trade-offs, and cross-functional alignment.",
        default_level="Mid-level",
        default_focus=["user research", "metrics", "roadmap", "PRD"],
        default_question_type_ratios={"behavioral": 30, "craft": 45, "pressure": 25},
    ),
    RolePreset(
        value="growth_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Growth Product Manager",
        description="Frames activation, retention, experiments, and funnel decisions.",
        default_level="Senior",
        default_focus=["activation", "retention", "experimentation", "funnel analytics"],
        default_question_type_ratios={"behavioral": 25, "craft": 50, "pressure": 25},
    ),
    RolePreset(
        value="platform_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Platform Product Manager",
        description="Balances developer experience, API contracts, reliability, and internal scale.",
        default_level="Senior",
        default_focus=["API platform", "developer experience", "reliability", "internal tools"],
        default_question_type_ratios={"behavioral": 25, "craft": 50, "pressure": 25},
    ),
    RolePreset(
        value="ai_pm",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="AI Product Manager",
        description="Turns model capability, evals, privacy, and cost into shippable product bets.",
        default_level="Senior",
        default_focus=["LLM features", "evaluation", "privacy", "model cost"],
        default_question_type_ratios={"behavioral": 25, "craft": 45, "pressure": 30},
    ),
)


INTERVIEW_ROLE_PRESETS: tuple[RolePreset, ...] = (
    RolePreset(
        value="recruiter_screen",
        category=ScenarioCategory.INTERVIEW,
        label="Recruiter screen",
        description="Checks motivation, fit, salary range, timeline, and concise career story.",
        default_level="Mid-level",
        default_focus=["career story", "motivation", "role fit", "salary expectations"],
        default_question_type_ratios={"behavioral": 55, "craft": 20, "pressure": 25},
    ),
    RolePreset(
        value="hiring_manager",
        category=ScenarioCategory.INTERVIEW,
        label="Hiring manager",
        description="Tests product judgment, ownership, impact, and team fit.",
        default_level="Senior",
        default_focus=["product judgment", "ownership", "impact", "team fit"],
        default_question_type_ratios={"behavioral": 35, "craft": 40, "pressure": 25},
    ),
    RolePreset(
        value="product_case_interviewer",
        category=ScenarioCategory.INTERVIEW,
        label="Product case interviewer",
        description="Runs product sense, prioritization, metrics, and structured problem-solving cases.",
        default_level="Senior",
        default_focus=["product sense", "prioritization", "metrics", "problem solving"],
        default_question_type_ratios={"behavioral": 15, "craft": 60, "pressure": 25},
    ),
    RolePreset(
        value="cross_functional_interviewer",
        category=ScenarioCategory.INTERVIEW,
        label="Cross-functional interviewer",
        description="Looks for collaboration with engineering, design, data, sales, and operations.",
        default_level="Senior",
        default_focus=["collaboration", "conflict resolution", "technical trade-offs", "influence"],
        default_question_type_ratios={"behavioral": 40, "craft": 35, "pressure": 25},
    ),
    RolePreset(
        value="bar_raiser",
        category=ScenarioCategory.INTERVIEW,
        label="Bar raiser",
        description="Applies high-pressure follow-ups on ambiguity, leadership, and evidence quality.",
        default_level="Senior",
        default_focus=["leadership", "ambiguity", "evidence quality", "decision reasoning"],
        default_question_type_ratios={"behavioral": 35, "craft": 30, "pressure": 35},
    ),
)


PRODUCT_MANAGEMENT_SCENARIO_PRESETS: tuple[ScenarioPreset, ...] = (
    ScenarioPreset(
        value="roadmap_prioritization",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Roadmap prioritization",
        description="Say no, defend sequencing, and keep stakeholders aligned.",
        counterpart_role="Head of Sales pushing for a large enterprise request",
        context_prompt=(
            "The stakeholder wants a high-revenue customer request moved above committed roadmap "
            "items. Practice explaining prioritization criteria, trade-offs, and next steps."
        ),
        suggested_role_values=["core_pm", "growth_pm"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 25, "craft": 45, "pressure": 30},
    ),
    ScenarioPreset(
        value="prd_review",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="PRD review",
        description="Clarify scope, acceptance criteria, and engineering trade-offs.",
        counterpart_role="Engineering lead challenging feasibility and edge cases",
        context_prompt=(
            "A PRD is ready for review, but engineering is concerned about ambiguous scope, "
            "dependency risk, and missing acceptance criteria."
        ),
        suggested_role_values=["core_pm", "platform_pm", "ai_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 20, "craft": 55, "pressure": 25},
    ),
    ScenarioPreset(
        value="launch_risk_review",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Launch risk review",
        description="Make a go/no-go recommendation under imperfect information.",
        counterpart_role="Executive sponsor asking whether to launch this week",
        context_prompt=(
            "The release is close, but quality signals and operational readiness are mixed. "
            "Practice a crisp go/no-go recommendation with risks, mitigations, and ownership."
        ),
        suggested_role_values=["core_pm", "ai_pm", "platform_pm"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 20, "craft": 45, "pressure": 35},
    ),
    ScenarioPreset(
        value="user_feedback_triage",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="User feedback triage",
        description="Separate signal from anecdotes and turn feedback into action.",
        counterpart_role="Customer success lead escalating urgent user complaints",
        context_prompt=(
            "Customer success brings urgent feedback from several accounts. Practice asking "
            "diagnostic questions, separating severity from frequency, and proposing a follow-up plan."
        ),
        suggested_role_values=["core_pm", "growth_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 30, "craft": 45, "pressure": 25},
    ),
    ScenarioPreset(
        value="executive_update",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Executive update",
        description="Communicate progress, risk, asks, and decision options clearly.",
        counterpart_role="CEO asking for impact, risk, and why the plan changed",
        context_prompt=(
            "You need to update leadership on a product initiative whose timeline and scope have "
            "changed. Practice leading with the decision needed, evidence, and trade-off options."
        ),
        suggested_role_values=["core_pm", "growth_pm", "ai_pm"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 20, "craft": 40, "pressure": 40},
    ),
    ScenarioPreset(
        value="stakeholder_conflict",
        category=ScenarioCategory.PRODUCT_MANAGEMENT,
        label="Stakeholder conflict",
        description="Align design, engineering, and business when incentives diverge.",
        counterpart_role="Cross-functional stakeholder panel with conflicting priorities",
        context_prompt=(
            "Design wants quality, engineering wants scope control, and business wants speed. "
            "Practice reframing the shared goal, exposing constraints, and landing a decision."
        ),
        suggested_role_values=["core_pm", "platform_pm"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 35, "craft": 35, "pressure": 30},
    ),
)


INTERVIEW_SCENARIO_PRESETS: tuple[ScenarioPreset, ...] = (
    ScenarioPreset(
        value="self_intro_pitch",
        category=ScenarioCategory.INTERVIEW,
        label="Self-introduction pitch",
        description="Open with a crisp career story tailored to a PM role.",
        counterpart_role="Recruiter checking role fit, motivation, and communication clarity",
        context_prompt=(
            "Practice a 60-90 second product manager self-introduction. The interviewer should "
            "test motivation, role fit, career transitions, and whether the story is concise."
        ),
        suggested_role_values=["recruiter_screen", "hiring_manager"],
        default_framework=ExpressionFramework.PYRAMID,
        default_difficulty=Difficulty.EASY,
        default_question_type_ratios={"behavioral": 60, "craft": 15, "pressure": 25},
    ),
    ScenarioPreset(
        value="resume_deep_dive",
        category=ScenarioCategory.INTERVIEW,
        label="Resume deep dive",
        description="Defend project impact, scope, metrics, and your exact contribution.",
        counterpart_role="Hiring manager probing resume claims and product ownership",
        context_prompt=(
            "The interviewer picks one product project from the resume and drills into context, "
            "your role, trade-offs, impact metrics, and what you would do differently."
        ),
        suggested_role_values=["hiring_manager", "bar_raiser"],
        default_framework=ExpressionFramework.STAR,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 40, "craft": 35, "pressure": 25},
    ),
    ScenarioPreset(
        value="product_sense_case",
        category=ScenarioCategory.INTERVIEW,
        label="Product sense case",
        description="Structure a product design or improvement case from user to metrics.",
        counterpart_role="Product case interviewer testing user insight, prioritization, and metrics",
        context_prompt=(
            "Run a product sense case for a PM candidate. Push for target users, problem framing, "
            "solution options, prioritization, success metrics, and risks."
        ),
        suggested_role_values=["product_case_interviewer", "hiring_manager"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 15, "craft": 60, "pressure": 25},
    ),
    ScenarioPreset(
        value="metrics_growth_case",
        category=ScenarioCategory.INTERVIEW,
        label="Metrics and growth case",
        description="Diagnose metric movement and propose experiments with trade-offs.",
        counterpart_role="Growth-oriented product interviewer testing data reasoning",
        context_prompt=(
            "The interviewer gives a product metric change or growth problem. Practice clarifying "
            "the metric tree, diagnosing causes, proposing experiments, and naming guardrails."
        ),
        suggested_role_values=["product_case_interviewer", "bar_raiser"],
        default_framework=ExpressionFramework.SCQA,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 10, "craft": 65, "pressure": 25},
    ),
    ScenarioPreset(
        value="behavioral_leadership",
        category=ScenarioCategory.INTERVIEW,
        label="Behavioral leadership",
        description="Answer conflict, failure, influence, and ambiguity questions with STAR evidence.",
        counterpart_role="Bar raiser testing leadership, ownership, and evidence quality",
        context_prompt=(
            "Run a behavioral PM interview covering conflict, failure, influence without authority, "
            "ambiguity, and learning. Require concrete examples, metrics, and reflection."
        ),
        suggested_role_values=["bar_raiser", "cross_functional_interviewer"],
        default_framework=ExpressionFramework.STAR,
        default_difficulty=Difficulty.HARD,
        default_question_type_ratios={"behavioral": 65, "craft": 10, "pressure": 25},
    ),
    ScenarioPreset(
        value="cross_functional_round",
        category=ScenarioCategory.INTERVIEW,
        label="Cross-functional round",
        description="Show how you work with engineering, design, data, and business teams.",
        counterpart_role="Engineering and design interviewers testing collaboration patterns",
        context_prompt=(
            "Simulate a cross-functional PM round. Ask about technical trade-offs, design conflict, "
            "data uncertainty, stakeholder pressure, and how the candidate drives alignment."
        ),
        suggested_role_values=["cross_functional_interviewer", "hiring_manager"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 45, "craft": 30, "pressure": 25},
    ),
    ScenarioPreset(
        value="offer_negotiation",
        category=ScenarioCategory.INTERVIEW,
        label="Offer negotiation",
        description="Discuss compensation, level, scope, and timeline without losing goodwill.",
        counterpart_role="Recruiter negotiating compensation, level, and decision timeline",
        context_prompt=(
            "Practice an offer-stage conversation. The interviewer should probe salary expectations, "
            "competing processes, level concerns, timeline, and how the candidate frames requests."
        ),
        suggested_role_values=["recruiter_screen"],
        default_framework=ExpressionFramework.PREP,
        default_difficulty=Difficulty.MEDIUM,
        default_question_type_ratios={"behavioral": 35, "craft": 15, "pressure": 50},
    ),
)


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
