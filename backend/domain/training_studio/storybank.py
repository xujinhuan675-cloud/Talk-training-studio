"""In-memory story bank domain service for reusable interview stories."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from domain.common.exceptions import DomainValidationException
from domain.training_studio.catalog import ScenarioCategory


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StoryBankEntry:
    id: str
    title: str
    summary: str
    raw_answer: str
    tags: list[str] = field(default_factory=list)
    scenario_category: ScenarioCategory = ScenarioCategory.INTERVIEW
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.title = self.title.strip()
        self.summary = self.summary.strip()
        self.raw_answer = self.raw_answer.strip()
        self.tags = [tag.strip().lower() for tag in self.tags if tag and tag.strip()]
        if isinstance(self.scenario_category, str):
            self.scenario_category = ScenarioCategory(self.scenario_category.strip().lower())
        if not self.title:
            raise DomainValidationException("Story title cannot be empty", field="title")
        if not self.summary:
            raise DomainValidationException("Story summary cannot be empty", field="summary")
        if not self.raw_answer:
            raise DomainValidationException("Story raw_answer cannot be empty", field="raw_answer")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "raw_answer": self.raw_answer,
            "tags": list(self.tags),
            "scenario_category": self.scenario_category.value,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StoryBankEntry":
        created_at = data.get("created_at")
        parsed_created_at = (
            datetime.fromisoformat(created_at) if isinstance(created_at, str) else _utcnow()
        )
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            summary=str(data["summary"]),
            raw_answer=str(data["raw_answer"]),
            tags=list(data.get("tags") or []),
            scenario_category=data.get("scenario_category", ScenarioCategory.INTERVIEW.value),
            created_at=parsed_created_at,
        )


class JsonFileStoryBankStore:
    """Small JSON-file store for local MVP persistence."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> list[StoryBankEntry]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise DomainValidationException("Storybank file must contain a list", field="storybank")
        return [StoryBankEntry.from_dict(item) for item in raw if isinstance(item, dict)]

    def save(self, entries: list[StoryBankEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.to_dict() for entry in entries]
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class StoryBankService:
    """Story bank service with optional local-file persistence."""

    def __init__(self, store: JsonFileStoryBankStore | None = None) -> None:
        self._store = store
        self._entries: dict[str, StoryBankEntry] = {}
        if self._store:
            for entry in self._store.load():
                self._entries[entry.id] = entry

    def extract_and_register(
        self,
        answer_text: str,
        *,
        scenario_category: ScenarioCategory | str = ScenarioCategory.INTERVIEW,
        tags: list[str] | None = None,
    ) -> StoryBankEntry:
        answer = answer_text.strip()
        if len(answer) < 20:
            raise DomainValidationException(
                "answer_text is too short to register as a story",
                field="answer_text",
                details={"minimum_chars": 20},
            )
        entry = StoryBankEntry(
            id=str(uuid4()),
            title=self._derive_title(answer),
            summary=self._derive_summary(answer),
            raw_answer=answer,
            tags=tags or self._derive_tags(answer),
            scenario_category=scenario_category,
        )
        self._entries[entry.id] = entry
        self._persist()
        return entry

    def get(self, entry_id: str) -> StoryBankEntry | None:
        return self._entries.get(entry_id)

    def list_entries(
        self,
        *,
        scenario_category: ScenarioCategory | str | None = None,
    ) -> list[StoryBankEntry]:
        entries = list(self._entries.values())
        if scenario_category is None:
            return entries
        category = (
            scenario_category
            if isinstance(scenario_category, ScenarioCategory)
            else ScenarioCategory(scenario_category.strip().lower())
        )
        return [entry for entry in entries if entry.scenario_category == category]

    def _persist(self) -> None:
        if self._store:
            self._store.save(list(self._entries.values()))

    def _derive_title(self, answer: str) -> str:
        first_sentence = self._sentences(answer)[0]
        return first_sentence[:80].rstrip(" ,.;:")

    def _derive_summary(self, answer: str) -> str:
        sentences = self._sentences(answer)
        summary = " ".join(sentences[:2])
        return summary[:360].strip()

    def _derive_tags(self, answer: str) -> list[str]:
        lower = answer.lower()
        tags: list[str] = []
        keyword_tags = {
            "leadership": ["led", "lead", "mentor", "manager", "team"],
            "impact": ["revenue", "growth", "saved", "reduced", "increased", "%"],
            "conflict": ["conflict", "disagree", "escalat", "negotiate"],
            "technical": ["system", "architecture", "python", "react", "api", "database"],
        }
        for tag, keywords in keyword_tags.items():
            if any(keyword in lower for keyword in keywords):
                tags.append(tag)
        return tags or ["general"]

    def _sentences(self, answer: str) -> list[str]:
        normalized = answer.replace("\n", " ")
        parts = [part.strip() for part in normalized.replace("!", ".").replace("?", ".").split(".")]
        return [part for part in parts if part]
