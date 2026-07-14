"""Application service for training studio catalog and task configuration."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from domain.training_studio.catalog import (
    DEFAULT_RUBRIC_VERSION,
    DEFAULT_RUBRIC_WEIGHTS,
    Difficulty,
    ExpressionFramework,
    INTERVIEW_ROLE_PRESETS,
    INTERVIEW_SCENARIO_PRESETS,
    PRODUCT_MANAGEMENT_ROLE_PRESETS,
    PRODUCT_MANAGEMENT_SCENARIO_PRESETS,
    RubricDimension,
    ScenarioCategory,
    TrainingTaskConfig,
    normalize_training_task_config,
)


class CatalogOptionDTO(BaseModel):
    value: str
    label: str


class RubricWeightsDTO(BaseModel):
    version: str
    category: str
    weights: dict[str, float]


class RolePresetDTO(BaseModel):
    value: str
    category: str
    label: str
    description: str
    default_level: str
    default_focus: list[str]
    default_question_type_ratios: dict[str, float]


class ScenarioPresetDTO(BaseModel):
    value: str
    category: str
    label: str
    description: str
    counterpart_role: str
    context_prompt: str
    suggested_role_values: list[str]
    default_framework: str
    default_difficulty: str
    default_question_type_ratios: dict[str, float]


class TrainingCatalogDTO(BaseModel):
    categories: list[CatalogOptionDTO]
    difficulties: list[CatalogOptionDTO]
    frameworks: list[CatalogOptionDTO]
    rubric_versions: list[str]
    default_rubric_weights: dict[str, dict[str, float]]
    role_presets: list[RolePresetDTO]
    scenario_presets: list[ScenarioPresetDTO]


class TrainingTaskConfigDTO(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    role: str = Field(min_length=1)
    level: str = Field(min_length=1)
    tech_stack: list[str] = Field(min_length=1)
    question_type_ratios: dict[str, float] = Field(min_length=1)
    question_count: int = Field(ge=1, le=100)
    framework: ExpressionFramework | str = ExpressionFramework.STAR
    difficulty: Difficulty | str = Difficulty.MEDIUM
    category: ScenarioCategory | str = ScenarioCategory.INTERVIEW
    rubric_version: str = DEFAULT_RUBRIC_VERSION
    rubric_weights: dict[RubricDimension | str, float] = Field(default_factory=dict)

    @classmethod
    def from_domain(cls, config: TrainingTaskConfig) -> "TrainingTaskConfigDTO":
        return cls(
            role=config.role,
            level=config.level,
            tech_stack=config.tech_stack,
            question_type_ratios=config.question_type_ratios,
            question_count=config.question_count,
            framework=config.framework.value,
            difficulty=config.difficulty.value,
            category=config.category.value,
            rubric_version=config.rubric_version,
            rubric_weights={dimension.value: weight for dimension, weight in config.rubric_weights.items()},
        )

    def to_domain(self) -> TrainingTaskConfig:
        return TrainingTaskConfig(
            role=self.role,
            level=self.level,
            tech_stack=list(self.tech_stack),
            question_type_ratios=dict(self.question_type_ratios),
            question_count=self.question_count,
            framework=self.framework,
            difficulty=self.difficulty,
            category=self.category,
            rubric_version=self.rubric_version,
            rubric_weights=dict(self.rubric_weights),
        )


class TrainingCatalogService:
    """Read-only catalog plus task configuration normalization."""

    def get_catalog(self) -> TrainingCatalogDTO:
        return TrainingCatalogDTO(
            categories=[self._option(item) for item in ScenarioCategory],
            difficulties=[self._option(item) for item in Difficulty],
            frameworks=[self._option(item) for item in ExpressionFramework],
            rubric_versions=[DEFAULT_RUBRIC_VERSION],
            default_rubric_weights={
                category.value: {
                    dimension.value: weight for dimension, weight in weights.items()
                }
                for category, weights in DEFAULT_RUBRIC_WEIGHTS.items()
            },
            role_presets=[
                RolePresetDTO(
                    value=preset.value,
                    category=preset.category.value,
                    label=preset.label,
                    description=preset.description,
                    default_level=preset.default_level,
                    default_focus=list(preset.default_focus),
                    default_question_type_ratios=dict(preset.default_question_type_ratios),
                )
                for preset in (*INTERVIEW_ROLE_PRESETS, *PRODUCT_MANAGEMENT_ROLE_PRESETS)
            ],
            scenario_presets=[
                ScenarioPresetDTO(
                    value=preset.value,
                    category=preset.category.value,
                    label=preset.label,
                    description=preset.description,
                    counterpart_role=preset.counterpart_role,
                    context_prompt=preset.context_prompt,
                    suggested_role_values=list(preset.suggested_role_values),
                    default_framework=preset.default_framework.value,
                    default_difficulty=preset.default_difficulty.value,
                    default_question_type_ratios=dict(preset.default_question_type_ratios),
                )
                for preset in (*INTERVIEW_SCENARIO_PRESETS, *PRODUCT_MANAGEMENT_SCENARIO_PRESETS)
            ],
        )

    def get_default_rubric_weights(
        self,
        category: ScenarioCategory | str = ScenarioCategory.INTERVIEW,
    ) -> RubricWeightsDTO:
        domain_category = (
            category if isinstance(category, ScenarioCategory) else ScenarioCategory(category.strip().lower())
        )
        return RubricWeightsDTO(
            version=DEFAULT_RUBRIC_VERSION,
            category=domain_category.value,
            weights={
                dimension.value: weight
                for dimension, weight in DEFAULT_RUBRIC_WEIGHTS[domain_category].items()
            },
        )

    def create_training_task_config(
        self,
        payload: TrainingTaskConfigDTO | dict,
    ) -> TrainingTaskConfigDTO:
        dto = payload if isinstance(payload, TrainingTaskConfigDTO) else TrainingTaskConfigDTO(**payload)
        normalized = normalize_training_task_config(dto.to_domain())
        return TrainingTaskConfigDTO.from_domain(normalized)

    def _option(self, value: ScenarioCategory | Difficulty | ExpressionFramework) -> CatalogOptionDTO:
        return CatalogOptionDTO(value=value.value, label=value.value.replace("_", " ").title())
