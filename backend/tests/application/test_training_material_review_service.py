from __future__ import annotations

import json
from copy import deepcopy

import pytest

from application.ports.llm import LLMResponse
from application.services.training_studio.material_review_llm_adapter import (
    MaterialReviewLLMAdapter,
)
from application.services.training_studio.material_review_service import (
    MaterialReviewReplayContext,
    MaterialReviewReportContext,
    TrainingMaterialReviewService,
    normalize_material_review_ids,
)
from application.services.training_studio.training_material_tool_service import (
    TrainingMaterialAssetSummaryDTO,
)
from domain.training_studio.catalog import TrainingTaskConfig
from domain.training_studio.session import TrainingSession, TrainingSessionStatus


def _session() -> TrainingSession:
    return TrainingSession(
        session_id="training-1",
        task_config=TrainingTaskConfig(
            role="Account Executive",
            level="Senior",
            tech_stack=["renewal", "enterprise"],
            question_type_ratios={"scenario": 1},
            question_count=3,
            framework="prep",
            difficulty="medium",
            category="sales",
            metadata={
                "messageTreeSelection": {"affectsScoring": False},
                "growthReport": {"status": "existing"},
            },
        ),
        mode="text",
        scenario_template_id="enterprise-renewal",
        user_id="user-sales-001",
        team_id="team-revenue",
        status=TrainingSessionStatus.COMPLETED,
        room_id="42",
        report_id="9",
        score_id="score-1",
        message_count=4,
    )


def _material(
    *,
    material_id: int = 7,
    summary: str = "Ask about success criteria and show ROI proof before proposing discounts.",
    snippet: str | None = "Discovery question: What changed since rollout?\nConfirm the buying committee.",
    truncated: bool = False,
) -> TrainingMaterialAssetSummaryDTO:
    return TrainingMaterialAssetSummaryDTO(
        id=material_id,
        key=f"training_material/{material_id}.md",
        name="renewal-playbook.md",
        content_type="text/markdown",
        metadata_excerpt={
            "title": "Renewal playbook",
            "summary": summary,
            "tags": ["renewal", "enterprise"],
        },
        content_excerpt=snippet,
        content_excerpt_truncated=truncated,
    )


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    async def generate(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return LLMResponse(content=self.content, model="fake-review-model")


def test_material_review_matches_and_misses_against_report_replay() -> None:
    service = TrainingMaterialReviewService()

    result = service.build_review(
        session=_session(),
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(
            summary="The learner used ROI proof but did not lock success criteria.",
            content={
                "communication_suggestions": [
                    {"suggestion": "Lead with quantified ROI before discussing discounting."}
                ]
            },
        ),
        replay=MaterialReviewReplayContext(
            turns=[
                "User: We can prove ROI with the activation metrics from last quarter.",
                "Counterpart: I still need a clear owner.",
            ]
        ),
    )

    assert result.session_id == "training-1"
    assert result.source_state.report_used is True
    assert result.source_state.replay_used is True
    assert result.source_state.material_snippet_used is True
    assert result.source_state.llm_used is False
    assert any("ROI proof" in item.point for item in result.matched_points)
    assert result.missed_points
    assert 1 <= len(result.suggested_rewrites) <= 3
    assert result.referenced_materials[0].content_excerpt is not None


@pytest.mark.asyncio
async def test_material_review_llm_adapter_refines_fallback_without_overriding_limits() -> None:
    llm = _FakeLLM(
        json.dumps(
            {
                "matched_points": [
                    {
                        "material_id": 7,
                        "point": "Confirmed success criteria before discount discussion.",
                        "evidence": "The report says the learner locked success criteria.",
                    },
                    {
                        "material_id": 999,
                        "point": "Invalid material id should be ignored.",
                    },
                ],
                "missed_points": [
                    {
                        "material_id": 7,
                        "point": "Ask who owns renewal approval next.",
                        "evidence": None,
                    }
                ],
                "suggested_rewrites": [
                    "Next drill: ask for the renewal owner before proposing price movement.",
                    "Next drill: pair ROI proof with a success metric.",
                ],
            }
        )
    )

    result = await TrainingMaterialReviewService().build_review_async(
        session=_session(),
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(
            summary="The learner locked success criteria and used ROI proof.",
        ),
        replay=MaterialReviewReplayContext(turns=["User: What success metric should we lock first?"]),
        async_llm_callback=MaterialReviewLLMAdapter(llm),
    )

    assert result.source_state.strategy == "llm_adapter"
    assert result.source_state.llm_used is True
    assert result.limits.material_count == 1
    assert result.referenced_materials[0].id == 7
    assert [item.material_id for item in result.matched_points] == [7]
    assert "success criteria" in result.matched_points[0].point
    assert result.missed_points[0].material_title == "Renewal playbook"
    assert len(result.suggested_rewrites) == 2

    payload = json.loads(llm.calls[0]["messages"][1].content)
    assert payload["materials"][0]["content_excerpt"].startswith("Discovery question")
    assert payload["deterministic_fallback"]["suggested_rewrites"]


@pytest.mark.asyncio
async def test_material_review_llm_adapter_falls_back_on_invalid_response() -> None:
    fallback = await TrainingMaterialReviewService().build_review_async(
        session=_session(),
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(summary="The learner used ROI proof."),
        replay=MaterialReviewReplayContext(turns=[]),
        async_llm_callback=MaterialReviewLLMAdapter(_FakeLLM("not json")),
    )

    assert fallback.source_state.strategy == "deterministic_fallback"
    assert fallback.source_state.llm_used is False
    assert fallback.missed_points
    assert fallback.suggested_rewrites


@pytest.mark.asyncio
async def test_material_review_llm_adapter_preserves_fallback_on_empty_result() -> None:
    result = await TrainingMaterialReviewService().build_review_async(
        session=_session(),
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(summary="The learner used ROI proof."),
        replay=MaterialReviewReplayContext(turns=[]),
        async_llm_callback=MaterialReviewLLMAdapter(
            _FakeLLM(
                json.dumps(
                    {
                        "matched_points": [],
                        "missed_points": [],
                        "suggested_rewrites": [],
                    }
                )
            )
        ),
    )

    assert result.source_state.strategy == "deterministic_fallback"
    assert result.source_state.llm_used is False
    assert result.matched_points or result.missed_points
    assert result.suggested_rewrites


@pytest.mark.asyncio
async def test_material_review_llm_adapter_preserves_fallback_when_structured_points_filter_empty() -> None:
    result = await TrainingMaterialReviewService().build_review_async(
        session=_session(),
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(summary="The learner used ROI proof."),
        replay=MaterialReviewReplayContext(turns=[]),
        async_llm_callback=MaterialReviewLLMAdapter(
            _FakeLLM(
                json.dumps(
                    {
                        "matched_points": [
                            {
                                "material_id": 999,
                                "point": "This invalid material should not clear fallback.",
                            }
                        ],
                        "missed_points": [{"material_id": 7, "point": ""}],
                        "suggested_rewrites": [""],
                    }
                )
            )
        ),
    )

    assert result.source_state.strategy == "deterministic_fallback"
    assert result.source_state.llm_used is False
    assert result.matched_points or result.missed_points
    assert result.suggested_rewrites


@pytest.mark.asyncio
async def test_material_review_llm_payload_bounds_report_replay_and_snippets() -> None:
    llm = _FakeLLM(
        json.dumps(
            {
                "suggested_rewrites": [
                    "Next drill: state the approval owner and one success metric."
                ]
            }
        )
    )
    long_text = "x" * 5000

    await TrainingMaterialReviewService().build_review_async(
        session=_session(),
        materials=[_material(snippet=long_text)],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(
            summary=long_text,
            content={
                "communication_suggestions": [
                    {"suggestion": f"{index}-{long_text}"} for index in range(10)
                ],
                "unsupported_key": long_text,
            },
        ),
        replay=MaterialReviewReplayContext(turns=[long_text]),
        async_llm_callback=MaterialReviewLLMAdapter(llm),
    )

    payload = json.loads(llm.calls[0]["messages"][1].content)
    assert len(payload["report"]["summary"]) <= 2003
    assert len(payload["report"]["content"]["communication_suggestions"]) == 5
    first_suggestion = payload["report"]["content"]["communication_suggestions"][0]["suggestion"]
    assert len(first_suggestion) <= 803
    assert "unsupported_key" not in payload["report"]["content"]
    assert len(payload["replay"]["turns"][0]) <= 803
    assert len(payload["materials"][0]["content_excerpt"]) <= 4003


def test_material_review_falls_back_without_report_or_replay() -> None:
    result = TrainingMaterialReviewService().build_review(
        session=_session(),
        materials=[_material(snippet=None)],
        requested_material_ids=[7],
        report=None,
        replay=None,
    )

    assert result.matched_points == []
    assert result.missed_points
    assert result.source_state.report_used is False
    assert result.source_state.replay_used is False
    assert result.source_state.material_snippet_used is False
    assert result.source_state.strategy == "deterministic_fallback"
    assert result.limits.material_count == 1


def test_material_review_does_not_mutate_scoring_growth_or_completion_metadata() -> None:
    session = _session()
    before = {
        "metadata": deepcopy(session.task_config.metadata),
        "status": session.status,
        "report_id": session.report_id,
        "score_id": session.score_id,
        "completed_at": session.completed_at,
        "message_count": session.message_count,
    }

    TrainingMaterialReviewService().build_review(
        session=session,
        materials=[_material()],
        requested_material_ids=[7],
        report=MaterialReviewReportContext(summary="No matching context."),
        replay=MaterialReviewReplayContext(turns=[]),
    )

    assert session.task_config.metadata == before["metadata"]
    assert session.status == before["status"]
    assert session.report_id == before["report_id"]
    assert session.score_id == before["score_id"]
    assert session.completed_at == before["completed_at"]
    assert session.message_count == before["message_count"]


def test_normalize_material_review_ids_accepts_legacy_selected_material_ids() -> None:
    assert normalize_material_review_ids([], [7, 7, 0, -1, 8]) == [7, 8]
    assert normalize_material_review_ids([9], [7]) == [9]
