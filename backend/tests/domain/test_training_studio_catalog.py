import pytest

from domain.common.exceptions import DomainValidationException
from domain.training_studio.catalog import (
    DEFAULT_RUBRIC_VERSION,
    Difficulty,
    ExpressionFramework,
    RubricDimension,
    ScenarioCategory,
    TrainingTaskConfig,
)


def test_training_task_config_normalizes_ratios_and_defaults():
    config = TrainingTaskConfig(
        role=" Backend Engineer ",
        level="Senior",
        tech_stack=[" Python ", "FastAPI"],
        question_type_ratios={"behavioral": 2, "system_design": 1},
        question_count=6,
        framework="star",
        difficulty="hard",
    )

    assert config.role == "Backend Engineer"
    assert config.category == ScenarioCategory.INTERVIEW
    assert config.framework == ExpressionFramework.STAR
    assert config.difficulty == Difficulty.HARD
    assert config.rubric_version == DEFAULT_RUBRIC_VERSION
    assert config.tech_stack == ["Python", "FastAPI"]
    assert config.question_type_ratios == {
        "behavioral": pytest.approx(2 / 3),
        "system_design": pytest.approx(1 / 3),
    }
    assert set(config.rubric_weights) == set(RubricDimension)
    assert sum(config.rubric_weights.values()) == pytest.approx(1.0)


def test_product_management_category_uses_pm_default_rubric_weights():
    config = TrainingTaskConfig(
        role="Product Manager",
        level="Mid-level",
        tech_stack=["Roadmap", "User research", "Metrics"],
        question_type_ratios={"behavioral": 30, "craft": 45, "pressure": 25},
        question_count=8,
        framework="scqa",
        difficulty="medium",
        category="product_management",
    )

    assert config.category == ScenarioCategory.PRODUCT_MANAGEMENT
    assert config.question_type_ratios["craft"] == pytest.approx(0.45)
    assert config.rubric_weights[RubricDimension.RELEVANCE] == pytest.approx(0.25)


def test_training_task_config_rejects_missing_rubric_dimension():
    with pytest.raises(DomainValidationException) as exc:
        TrainingTaskConfig(
            role="AE",
            level="L4",
            tech_stack=["CRM"],
            question_type_ratios={"objection": 1},
            question_count=5,
            category="sales",
            rubric_weights={
                "substance": 0.4,
                "structure": 0.2,
                "relevance": 0.2,
                "credibility": 0.2,
            },
        )

    assert exc.value.field == "rubric_weights"


def test_training_task_config_rejects_empty_question_ratios():
    with pytest.raises(DomainValidationException):
        TrainingTaskConfig(
            role="PM",
            level="L5",
            tech_stack=["Roadmap"],
            question_type_ratios={},
            question_count=5,
        )
