import pytest

from application.services.training_studio.catalog_service import (
    TrainingCatalogService,
    TrainingTaskConfigDTO,
)


def test_catalog_service_returns_catalog_options_and_default_weights():
    service = TrainingCatalogService()

    catalog = service.get_catalog()

    assert {item.value for item in catalog.categories} == {
        "interview",
        "sales",
        "negotiation",
        "workplace",
        "product_management",
    }
    assert {item.value for item in catalog.frameworks} == {"prep", "star", "scqa", "pyramid"}
    assert "interview-five-dimension-v1" in catalog.rubric_versions
    assert sum(catalog.default_rubric_weights["interview"].values()) == pytest.approx(1.0)
    assert {item.value for item in catalog.role_presets} >= {"core_pm", "growth_pm"}
    assert {item.value for item in catalog.role_presets} >= {
        "recruiter_screen",
        "hiring_manager",
        "product_case_interviewer",
    }
    assert {item.value for item in catalog.scenario_presets} >= {
        "roadmap_prioritization",
        "prd_review",
        "launch_risk_review",
    }
    assert {item.value for item in catalog.scenario_presets} >= {
        "self_intro_pitch",
        "resume_deep_dive",
        "product_sense_case",
    }


def test_catalog_service_normalizes_task_config_from_dict():
    service = TrainingCatalogService()

    dto = service.create_training_task_config(
        {
            "role": "Solutions Engineer",
            "level": "L5",
            "tech_stack": ["Python", "Cloud"],
            "question_type_ratios": {"behavioral": 3, "technical": 1},
            "question_count": 8,
            "framework": "prep",
            "difficulty": "medium",
            "category": "sales",
        }
    )

    assert isinstance(dto, TrainingTaskConfigDTO)
    assert dto.framework == "prep"
    assert dto.category == "sales"
    assert dto.question_type_ratios["behavioral"] == pytest.approx(0.75)
    assert sum(dto.rubric_weights.values()) == pytest.approx(1.0)


def test_catalog_service_returns_category_default_rubric_weights():
    service = TrainingCatalogService()

    weights = service.get_default_rubric_weights("product_management")

    assert weights.version == "interview-five-dimension-v1"
    assert weights.category == "product_management"
    assert set(weights.weights) == {
        "substance",
        "structure",
        "relevance",
        "credibility",
        "differentiation",
    }
