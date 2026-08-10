"""Application service for Training Studio scenario configuration state."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from application.ports.tts import (
    DEFAULT_TRAINING_VOICE_ID,
    REFINED_MALE_TRAINING_VOICE_ID,
    STEADY_MALE_TRAINING_VOICE_ID,
    WARM_FEMALE_TRAINING_VOICE_ID,
    normalize_training_voice_id,
)

from domain.training_studio.catalog import (
    DEFAULT_RUBRIC_WEIGHTS,
    RubricDimension,
    SCENARIO_TRAINING_TEMPLATES,
    ScenarioCategory,
)

_DEFAULT_UPDATED_AT = "2026-01-01T00:00:00.000Z"
_CATEGORY_WEIGHT_ALIASES = {
    "customer_service": ScenarioCategory.WORKPLACE,
}
_SCENARIO_DEFAULT_VOICE_IDS = {
    "daily-upward-results-report": STEADY_MALE_TRAINING_VOICE_ID,
    "new-customer-discount": WARM_FEMALE_TRAINING_VOICE_ID,
    "enterprise-demo-objection": REFINED_MALE_TRAINING_VOICE_ID,
    "refund-service-recovery": STEADY_MALE_TRAINING_VOICE_ID,
    "renewal-price-negotiation": STEADY_MALE_TRAINING_VOICE_ID,
    "recruiter-sales-interview": DEFAULT_TRAINING_VOICE_ID,
    "ai-web3-agent-pm-comprehensive-interview": REFINED_MALE_TRAINING_VOICE_ID,
    "angry-vip-priority": STEADY_MALE_TRAINING_VOICE_ID,
    "budget-freeze-expansion": STEADY_MALE_TRAINING_VOICE_ID,
    "cross-team-roadmap-tradeoff": REFINED_MALE_TRAINING_VOICE_ID,
    "project-scope-creep-boundary": REFINED_MALE_TRAINING_VOICE_ID,
    "service-apology-retention": WARM_FEMALE_TRAINING_VOICE_ID,
    "daily-spoken-clarity": DEFAULT_TRAINING_VOICE_ID,
}
_DIMENSION_LABELS: dict[str, tuple[str, str]] = {
    RubricDimension.SUBSTANCE.value: (
        "Substance",
        "Addresses the real issue with concrete information, trade-offs, and useful next steps.",
    ),
    RubricDimension.STRUCTURE.value: (
        "Structure",
        "Keeps the response easy to follow with an appropriate framework and clear flow.",
    ),
    RubricDimension.RELEVANCE.value: (
        "Relevance",
        "Responds to the counterpart's actual need or objection instead of using generic scripts.",
    ),
    RubricDimension.CREDIBILITY.value: (
        "Credibility",
        "Supports claims with evidence, examples, limitations, or a believable plan.",
    ),
    RubricDimension.DIFFERENTIATION.value: (
        "Differentiation",
        "Creates a clear point of view, contrast, or differentiated value.",
    ),
}


def default_scenario_voice_id(scenario_id: str) -> str:
    """Return the validated built-in voice selected for a scenario."""
    return _SCENARIO_DEFAULT_VOICE_IDS.get(scenario_id, DEFAULT_TRAINING_VOICE_ID)


class ScenarioDimensionDefinitionDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    enabled: bool = True
    updated_at: str = Field(default=_DEFAULT_UPDATED_AT, alias="updatedAt")
    source: str | None = "default"


class ScenarioDimensionWeightDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dimension_id: str = Field(alias="dimensionId", min_length=1)
    weight: float = Field(ge=0)


class ScenarioConfigPersonaDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    persona_id: str | None = Field(default=None, alias="personaId")
    name: str = ""
    role: str = ""
    style: str = ""
    # None means inherit the bound asset or the built-in scenario voice.
    voice_id: str | None = Field(default=None, alias="voiceId")
    voice_speed: float = Field(default=1.0, ge=0.1, le=2.0, alias="voiceSpeed")
    voice_loudness: float = Field(default=1.0, ge=0.5, le=2.0, alias="voiceLoudness")
    voice_emotion: str | None = Field(default=None, max_length=80, alias="voiceEmotion")
    voice_emotion_scale: float = Field(
        default=1.0,
        ge=0.0,
        le=2.0,
        alias="voiceEmotionScale",
    )
    voice_style: str | None = Field(default=None, max_length=500, alias="voiceStyle")

    @field_validator("voice_id")
    @classmethod
    def validate_voice_id(cls, value: str | None) -> str | None:
        return normalize_training_voice_id(value)


class ScenarioConfigDraftDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = ""
    customer_profile: str = Field(default="", alias="customerProfile")
    difficulty: str = "medium"
    category: str = "interview"
    required: bool = False
    enabled: bool = True
    opening_line: str = Field(default="", alias="openingLine")
    persona: ScenarioConfigPersonaDTO = Field(default_factory=ScenarioConfigPersonaDTO)
    learner_role: str = Field(default="Salesperson", alias="learnerRole")
    framework: str = "star"
    training_points: list[str] = Field(default_factory=list, alias="trainingPoints")
    dimension_weights: list[ScenarioDimensionWeightDTO] = Field(
        default_factory=list,
        alias="dimensionWeights",
    )
    source_scenario_id: str | None = Field(default=None, alias="sourceScenarioId")
    updated_at: str = Field(default=_DEFAULT_UPDATED_AT, alias="updatedAt")


class ScenarioConfigStateDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    dimensions: list[ScenarioDimensionDefinitionDTO] = Field(default_factory=list)
    scenarios: list[ScenarioConfigDraftDTO] = Field(default_factory=list)
    selected_scenario_id: str | None = Field(default=None, alias="selectedScenarioId")
    selected_dimension_id: str | None = Field(default=None, alias="selectedDimensionId")
    updated_at: str = Field(default=_DEFAULT_UPDATED_AT, alias="updatedAt")


class JsonFileScenarioConfigStore:
    """Small JSON-file store for local MVP persistence."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Scenario config file must contain an object")
        return raw

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        self.path.write_text(f"{payload}\n", encoding="utf-8")


class TrainingScenarioConfigService:
    """Reads and saves the global scenario configuration state."""

    def __init__(self, store: JsonFileScenarioConfigStore | None = None) -> None:
        self._store = store

    def get_config(self) -> ScenarioConfigStateDTO:
        if self._store is None:
            return self.default_config()
        raw = self._store.load()
        if raw is None:
            return self.default_config()
        return ScenarioConfigStateDTO.model_validate(raw)

    def save_config(
        self,
        payload: ScenarioConfigStateDTO | dict,
    ) -> ScenarioConfigStateDTO:
        state = (
            payload
            if isinstance(payload, ScenarioConfigStateDTO)
            else ScenarioConfigStateDTO.model_validate(payload)
        )
        if self._store is not None:
            self._store.save(state.model_dump(mode="json", by_alias=True, exclude_none=True))
        return state

    def default_config(self) -> ScenarioConfigStateDTO:
        dimensions = [
            ScenarioDimensionDefinitionDTO(
                id=dimension.value,
                name=_DIMENSION_LABELS[dimension.value][0],
                description=_DIMENSION_LABELS[dimension.value][1],
                enabled=True,
                source="default",
                updated_at=_DEFAULT_UPDATED_AT,
            )
            for dimension in RubricDimension
        ]
        scenarios = [
            ScenarioConfigDraftDTO(
                id=template.id,
                title=template.title,
                description=template.description,
                customer_profile=template.customer_profile,
                difficulty=str(template.difficulty),
                category=str(template.category),
                required=template.required,
                enabled=True,
                opening_line=template.opening_line,
                persona=ScenarioConfigPersonaDTO(
                    name=template.persona.name,
                    role=template.persona.role,
                    style=template.persona.style,
                    voice_id=default_scenario_voice_id(template.id),
                ),
                learner_role=template.learner_role,
                framework=template.framework.value,
                training_points=list(template.training_points),
                dimension_weights=self._default_dimension_weights(template.category),
                source_scenario_id=template.id,
                updated_at=_DEFAULT_UPDATED_AT,
            )
            for template in SCENARIO_TRAINING_TEMPLATES
        ]
        return ScenarioConfigStateDTO(
            version=1,
            dimensions=dimensions,
            scenarios=scenarios,
            selected_scenario_id=scenarios[0].id if scenarios else None,
            selected_dimension_id=dimensions[0].id if dimensions else None,
            updated_at=_DEFAULT_UPDATED_AT,
        )

    def _default_dimension_weights(self, category: str) -> list[ScenarioDimensionWeightDTO]:
        rubric_category = self._rubric_category_for(category)
        weights = DEFAULT_RUBRIC_WEIGHTS[rubric_category]
        return [
            ScenarioDimensionWeightDTO(
                dimension_id=dimension.value,
                weight=round(weight * 100, 4),
            )
            for dimension, weight in weights.items()
        ]

    def _rubric_category_for(self, category: str) -> ScenarioCategory:
        normalized = str(category).strip().lower()
        if normalized in _CATEGORY_WEIGHT_ALIASES:
            return _CATEGORY_WEIGHT_ALIASES[normalized]
        try:
            return ScenarioCategory(normalized)
        except ValueError:
            return ScenarioCategory.INTERVIEW
