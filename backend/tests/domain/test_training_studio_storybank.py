import pytest

from domain.common.exceptions import DomainValidationException
from domain.training_studio.catalog import ScenarioCategory
from domain.training_studio.storybank import JsonFileStoryBankStore, StoryBankService


def test_storybank_extracts_and_registers_story_entry():
    service = StoryBankService()

    entry = service.extract_and_register(
        "I led a team migration from a legacy API to FastAPI. "
        "We reduced latency by 35% and improved release confidence.",
        scenario_category="interview",
    )

    assert entry.id
    assert entry.title.startswith("I led a team migration")
    assert "technical" in entry.tags
    assert "impact" in entry.tags
    assert service.get(entry.id) == entry
    assert service.list_entries(scenario_category=ScenarioCategory.INTERVIEW) == [entry]


def test_storybank_rejects_too_short_answer():
    service = StoryBankService()

    with pytest.raises(DomainValidationException) as exc:
        service.extract_and_register("Too short")

    assert exc.value.field == "answer_text"


def test_storybank_persists_to_json_file(tmp_path):
    path = tmp_path / "storybank.json"
    service = StoryBankService(JsonFileStoryBankStore(path))
    entry = service.extract_and_register(
        "I led a team through a platform migration and improved latency by 40 percent.",
        tags=["impact"],
    )

    reloaded = StoryBankService(JsonFileStoryBankStore(path))

    assert reloaded.get(entry.id) is not None
    assert reloaded.get(entry.id).title == entry.title
