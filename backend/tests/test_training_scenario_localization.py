"""Built-in scenario language variants preserve authored and scoring data."""

from __future__ import annotations

import re

import pytest

from api.routes.training_studio import _scenario_templates_from_config
from application.services.training_studio.scenario_config_service import TrainingScenarioConfigService


@pytest.mark.parametrize("locale", ["en", "en-US", "en-GB"])
def test_english_scenario_content_has_no_chinese_defaults(locale: str) -> None:
    config = TrainingScenarioConfigService().default_config()
    originals = _scenario_templates_from_config(config)
    localized = _scenario_templates_from_config(config, locale=locale)

    assert len(localized) == 13
    for original, english in zip(originals, localized, strict=True):
        assert english.id == original.id
        assert english.category == original.category
        assert english.difficulty == original.difficulty
        assert english.framework == original.framework
        assert english.dimension_weights == original.dimension_weights
        assert english.persona.voice_id == original.persona.voice_id
        content = " ".join([
            english.title,
            english.description,
            english.customer_profile,
            english.opening_line,
            english.persona.name,
            english.persona.role,
            english.persona.style,
            *english.training_points,
        ])
        assert not re.search(r"[\u4e00-\u9fff]", content), english.id
    assert config.scenarios[1].title == originals[1].title


@pytest.mark.parametrize("locale", [None, "zh", "zh-CN", "zh-TW"])
def test_chinese_and_default_requests_keep_the_canonical_scenarios(locale: str | None) -> None:
    config = TrainingScenarioConfigService().default_config()
    assert _scenario_templates_from_config(config, locale=locale) == _scenario_templates_from_config(config)


def test_english_localization_preserves_custom_fields_and_bound_personas() -> None:
    config = TrainingScenarioConfigService().default_config()
    original = config.scenarios[1]
    custom_point = "Custom product knowledge"
    changed = original.model_copy(update={
        "title": "My authored title",
        "opening_line": "My authored opening",
        "training_points": [original.training_points[0], custom_point],
        "persona": original.persona.model_copy(update={"persona_id": "asset-123"}),
    })
    copied = original.model_copy(update={"id": "copied-scenario"})
    config = config.model_copy(update={"scenarios": [changed, copied]})
    localized, copied_localized = _scenario_templates_from_config(config, locale="en-US")

    assert localized.title == changed.title
    assert localized.opening_line == changed.opening_line
    assert localized.description != changed.description
    assert localized.persona.name == changed.persona.name
    assert localized.persona.role == changed.persona.role
    assert localized.persona.style == changed.persona.style
    assert localized.training_points == ["Build trust quickly", custom_point]
    assert copied_localized.title == copied.title
    assert copied_localized.opening_line == copied.opening_line


def test_english_localization_is_read_only_and_can_switch_back_to_chinese() -> None:
    config = TrainingScenarioConfigService().default_config()
    snapshot = config.model_dump()
    english = _scenario_templates_from_config(config, locale="en-US")[1]
    chinese = _scenario_templates_from_config(config, locale="zh-CN")[1]

    assert english.title == "New customer discount inquiry"
    assert english.persona.name == "Ms. Li"
    assert english.opening_line.startswith("Hi, I saw")
    assert chinese.title == config.scenarios[1].title
    assert config.model_dump() == snapshot
