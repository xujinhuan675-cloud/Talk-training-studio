"""Evidence and persistence regression tests for communication-core-v1."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.ports.llm import LLMProviderMetadata
from application.services.stakeholder.growth_service import GrowthService
from domain.stakeholder.competency_entity import COMPETENCY_DIMENSIONS
from domain.stakeholder.entity import AnalysisReport, ChatRoom, Message


def _dimension(
    *,
    opportunity_present: bool = True,
    rating: int | None = 3,
    evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "opportunity_present": opportunity_present,
        "rating": rating,
        "evidence": evidence or [],
        "reason": "只能基于可定位证据判断",
        "suggestion": "先澄清对方关切再给出方案",
    }


def _outcome(
    rating: int | None,
    evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "rating": rating,
        "evidence": evidence or [],
        "reason": "只能基于可定位证据判断",
    }


def _response(**overrides: dict[str, object]) -> dict[str, object]:
    competencies = {
        dimension: _dimension(
            evidence=[{"message_id": "11", "quote": "我先确认一下您的预算范围"}]
        )
        for dimension in COMPETENCY_DIMENSIONS
    }
    competencies.update(overrides)
    evidence = [{"message_id": "11", "quote": "我先确认一下您的预算范围"}]
    return {
        "effectiveness": _outcome(3, evidence),
        "appropriateness": _outcome(4, evidence),
        "competencies": competencies,
    }


class _Repository:
    def __init__(self, value=None) -> None:
        self.value = value

    async def get_by_report_id(self, _report_id: int):
        return self.value

    async def create(self, evaluation):
        evaluation.id = 901
        self.value = evaluation
        return evaluation


class _Uow:
    def __init__(self, state) -> None:
        self.competency_evaluation_repository = state.evaluations
        self.analysis_report_repository = SimpleNamespace(
            get_by_id=AsyncMock(return_value=state.report)
        )
        self.chat_room_repository = SimpleNamespace(get_by_id=AsyncMock(return_value=state.room))
        self.stakeholder_message_repository = SimpleNamespace(
            list_by_room_id=AsyncMock(return_value=state.messages)
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _UowFactory:
    def __init__(self, state) -> None:
        self.state = state

    def __call__(self, **_kwargs):
        return _Uow(self.state)


def _service(parsed: dict[str, object]):
    state = SimpleNamespace(
        evaluations=_Repository(),
        report=AnalysisReport(id=7, room_id=5, summary="report"),
        room=ChatRoom(id=5, name="budget", type="private", persona_ids=[]),
        messages=[
            Message(
                id=10,
                room_id=5,
                sender_type="persona",
                sender_id="customer",
                content="我的预算有限，这个价格超了。",
            ),
            Message(
                id=11,
                room_id=5,
                sender_type="user",
                sender_id="newapi:7",
                content="我先确认一下您的预算范围，再看适合的方案。",
            ),
            Message(
                id=12,
                room_id=5,
                sender_type="user",
                sender_id="newapi:7",
                content="如果预算必须控制，我可以先给您一个分阶段方案。",
            ),
        ],
    )
    llm = SimpleNamespace(
        generate_structured=AsyncMock(return_value=parsed),
        provider_metadata=LLMProviderMetadata(
            provider="openai",
            default_model="gpt-test",
        ),
    )
    return GrowthService(_UowFactory(state), llm, persona_loader=None), state, llm


@pytest.mark.asyncio
async def test_evaluation_persists_versioned_four_dimension_contract() -> None:
    service, _, llm = _service(_response())

    result = await service.evaluate_competency(
        7,
        evaluation_context={
            "task_goal": "回应预算异议并推动下一步",
            "observable_competencies": list(COMPETENCY_DIMENSIONS),
        },
        task_context={"difficulty": "hard"},
    )

    assert result is not None
    assert result.scores["rubric_version"] == "communication-core-v1"
    assert result.scores["judge_version"] == "evidence-anchored-v1"
    assert result.scores["judge_model"] == "openai:gpt-test"
    assert result.scores["status"] == "ready"
    assert set(result.scores["competencies"]) == set(COMPETENCY_DIMENSIONS)
    assert result.outcome_rating == 3.5
    assert result.scores["competencies"]["attentiveness"]["evidence"] == [
        {
            "message_id": 11,
            "quote": "我先确认一下您的预算范围",
        }
    ]
    prompt = llm.generate_structured.call_args.args[0][0].content
    assert "[用户消息 id=11]" in prompt
    assert "回应预算异议并推动下一步" in prompt
    assert "difficulty: hard" in prompt


@pytest.mark.asyncio
async def test_evaluation_context_can_bound_the_selected_message_path() -> None:
    service, _, llm = _service(_response())

    await service.evaluate_competency(
        7,
        evaluation_context={
            "messages": [
                {"message_id": "10"},
                {"message_id": "11"},
            ]
        },
    )

    prompt = llm.generate_structured.call_args.args[0][0].content
    assert "[用户消息 id=11]" in prompt
    assert "[用户消息 id=12]" not in prompt


@pytest.mark.asyncio
async def test_unverifiable_evidence_never_defaults_to_middle_score() -> None:
    response = _response(
        attentiveness=_dimension(
            rating=4,
            evidence=[{"message_id": "999", "quote": "不存在的对话证据"}],
        ),
        composure=_dimension(
            opportunity_present=False,
            rating=3,
            evidence=[],
        ),
    )
    service, _, _ = _service(response)

    result = await service.evaluate_competency(7)

    assert result is not None
    assert result.scores["competencies"]["attentiveness"]["rating"] is None
    assert result.scores["competencies"]["attentiveness"]["evidence"] == []
    assert result.scores["competencies"]["composure"]["rating"] is None


@pytest.mark.asyncio
async def test_five_requires_two_independent_verified_evidence_items() -> None:
    response = _response(
        expression=_dimension(
            rating=5,
            evidence=[{"message_id": "11", "quote": "再看适合的方案"}],
        )
    )
    service, _, _ = _service(response)

    result = await service.evaluate_competency(7)

    assert result is not None
    assert result.scores["competencies"]["expression"]["rating"] is None


@pytest.mark.asyncio
async def test_five_is_kept_with_two_independent_verified_user_messages() -> None:
    response = _response(
        expression=_dimension(
            rating=5,
            evidence=[
                {"message_id": "11", "quote": "再看适合的方案"},
                {"message_id": "12", "quote": "我可以先给您一个分阶段方案"},
            ],
        )
    )
    service, _, _ = _service(response)

    result = await service.evaluate_competency(7)

    assert result is not None
    assert result.scores["competencies"]["expression"]["rating"] == 5


@pytest.mark.asyncio
async def test_no_verified_competency_evidence_marks_evaluation_insufficient() -> None:
    response = {
        "effectiveness": _outcome(4),
        "appropriateness": _outcome(4),
        "competencies": {
            dimension: _dimension(opportunity_present=False, rating=None, evidence=[])
            for dimension in COMPETENCY_DIMENSIONS
        },
    }
    service, _, _ = _service(response)

    result = await service.evaluate_competency(7)

    assert result is not None
    assert result.scores["status"] == "insufficient_evidence"
    assert result.scores["effectiveness"]["rating"] is None
    assert result.scores["appropriateness"]["rating"] is None
    assert result.outcome_rating is None
