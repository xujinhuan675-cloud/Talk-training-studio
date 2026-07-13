from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from application.ports.llm import LLMResponse
from application.services.stakeholder.analysis_service import AnalysisService
from domain.stakeholder.entity import AnalysisReport, ChatRoom, Message


@dataclass
class _Persona:
    id: str
    name: str
    role: str


class _PersonaLoader:
    def __init__(self):
        self._personas = {"cfo": _Persona(id="cfo", name="CFO", role="Finance")}

    def get_persona(self, persona_id: str):
        return self._personas.get(persona_id)


class _FakeLLM:
    def __init__(self, content: str):
        self.content = content
        self.messages = []

    async def generate(self, messages, **kwargs):
        self.messages = messages
        return LLMResponse(content=self.content, model="fake")


class _RoomRepo:
    def __init__(self, room):
        self.room = room

    async def get_by_id(self, room_id: int):
        return self.room if self.room.id == room_id else None


class _MessageRepo:
    def __init__(self, messages):
        self.messages = messages

    async def list_by_room_id(self, room_id: int, *, skip: int = 0, limit: int = 50):
        return [m for m in self.messages if m.room_id == room_id][skip : skip + limit]


class _ReportRepo:
    def __init__(self):
        self.created: AnalysisReport | None = None

    async def create(self, report: AnalysisReport):
        report.id = 900
        report.created_at = datetime.now(timezone.utc)
        self.created = report
        return report


class _FakeUow:
    def __init__(self, state):
        self.chat_room_repository = _RoomRepo(state.room)
        self.stakeholder_message_repository = _MessageRepo(state.messages)
        self.analysis_report_repository = state.report_repo
        self.organization_repository = SimpleNamespace(get_by_id=lambda org_id: None)
        self.persona_relationship_repository = SimpleNamespace(list_by_organization=lambda org_id: [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _uow_factory(state):
    def factory(**kwargs):
        return _FakeUow(state)

    return factory


def _state():
    return SimpleNamespace(
        room=ChatRoom(id=1, name="room", type="group", persona_ids=["cfo"]),
        messages=[
            Message(
                id=101,
                room_id=1,
                sender_type="user",
                sender_id="user",
                content="We can reduce risk with a phased rollout.",
            ),
            Message(
                id=102,
                room_id=1,
                sender_type="persona",
                sender_id="cfo",
                content="I still need a budget cap before approving.",
                emotion_score=-2,
                emotion_label="skeptical",
            ),
        ],
        report_repo=_ReportRepo(),
    )


@pytest.mark.asyncio
async def test_generate_report_adds_anchors_and_enhanced_sections():
    payload = {
        "summary": "Budget concern remained but the phased rollout helped.",
        "resistance_ranking": {
            "persona_id": "cfo",
            "persona_name": "CFO",
            "score": "-2",
            "reason": "Needs budget cap.",
            "message_indices": ["#2"],
        },
        "effective_arguments": [
            {
                "argument": "phased rollout",
                "target_persona": "CFO",
                "effectiveness": "Reduced perceived risk.",
                "message_indices": [1, 2],
            }
        ],
        "communication_suggestions": [
            {"persona_id": "cfo", "persona_name": "CFO", "suggestion": "Lead with cap."}
        ],
        "evidence_reviews": [
            {
                "claim": "The CFO asked for a concrete constraint.",
                "evidence": "budget cap",
                "insight": "Approval depends on downside control.",
                "message_indices": [2],
            }
        ],
        "alternative_phrasings": "wrong type",
        "rewrite_demos": [
            {
                "original": "We can reduce risk.",
                "rewritten": "We will cap spend and phase the rollout.",
                "principle": "Make risk control explicit.",
                "message_indices": [1],
            }
        ],
        "micro_drills": [
            {
                "title": "Budget cap drill",
                "goal": "Answer finance resistance",
                "prompt": "Respond with one cap and one validation metric.",
                "practice_steps": ["State cap", "Name checkpoint"],
                "success_criteria": ["Specific cap", "Clear metric"],
                "target_persona": "CFO",
                "message_indices": [2],
            }
        ],
        "high_signal_moments": [
            {
                "title": "Approval blocker",
                "moment_type": "resistance",
                "why_it_matters": "It names the decision gate.",
                "recommendation": "Return with budget ceiling.",
                "message_indices": [2],
            }
        ],
    }
    state = _state()
    llm = _FakeLLM("preface\n```json\n" + json.dumps(payload) + "\n```\npostscript")
    service = AnalysisService(_uow_factory(state), llm=llm, persona_loader=_PersonaLoader())

    report = await service.generate_report(1)

    assert "evidence_reviews" in llm.messages[0].content
    assert report.content.resistance_ranking[0].message_ids == [102]
    assert report.content.resistance_ranking[0].message_anchors[0].quote.startswith("I still need")
    assert report.content.effective_arguments[0].message_ids == [101, 102]
    assert report.content.communication_suggestions[0].priority == "medium"
    assert report.content.evidence_reviews[0].message_ids == [102]
    assert report.content.rewrite_demos[0].message_anchors[0].speaker == "user"
    assert report.content.micro_drills[0].message_anchors[0].speaker == "CFO"
    assert report.content.high_signal_moments[0].message_ids == [102]
    assert report.content.alternative_phrasings == []
    assert state.report_repo.created is not None
    assert state.report_repo.created.content["message_id_map"] == {"1": 101, "2": 102}


@pytest.mark.asyncio
async def test_generate_report_keeps_legacy_fields_when_enhanced_fields_missing():
    state = _state()
    llm = _FakeLLM(
        json.dumps(
            {
                "summary": "Legacy report",
                "resistance_ranking": [],
                "effective_arguments": [],
                "communication_suggestions": [],
            }
        )
    )
    service = AnalysisService(_uow_factory(state), llm=llm, persona_loader=_PersonaLoader())

    report = await service.generate_report(1)

    assert report.summary == "Legacy report"
    assert report.content.evidence_reviews == []
    assert report.content.message_anchors[0].message_id == 101
