from __future__ import annotations

from copy import deepcopy

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
