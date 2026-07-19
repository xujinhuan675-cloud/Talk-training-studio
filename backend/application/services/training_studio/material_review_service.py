"""Read-only material comparison for the Training Studio review assistant."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from application.services.training_studio.training_material_tool_service import (
    TrainingMaterialAssetSummaryDTO,
)
from domain.training_studio.session import TrainingSession

logger = logging.getLogger(__name__)

_MAX_MATERIALS = 5
_MAX_MATERIAL_POINTS = 3
_MAX_REPLAY_TURNS = 40
_MAX_CONTEXT_CHARS = 12000
_POINT_TEXT_LIMIT = 360
_SUGGESTION_LIMIT = 3
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'-]{2,}|[\u4e00-\u9fff]{2,}")


@dataclass(frozen=True)
class MaterialReviewReportContext:
    summary: str = ""
    content: dict[str, Any] | None = None
    truncated: bool = False


@dataclass(frozen=True)
class MaterialReviewReplayContext:
    turns: list[str]
    truncated: bool = False


class MaterialReviewPointDTO(BaseModel):
    material_id: int
    material_title: str
    point: str
    evidence: str | None = None


class MaterialReviewSourceStateDTO(BaseModel):
    strategy: str = "deterministic_fallback"
    llm_used: bool = False
    report_used: bool = False
    replay_used: bool = False
    material_snippet_used: bool = False
    selected_material_ids: list[int] = Field(default_factory=list)


class MaterialReviewLimitsDTO(BaseModel):
    max_materials: int = _MAX_MATERIALS
    max_replay_turns: int = _MAX_REPLAY_TURNS
    material_count: int = 0
    requested_material_count: int = 0
    material_selection_truncated: bool = False
    material_snippets_truncated: bool = False
    report_context_truncated: bool = False
    replay_transcript_truncated: bool = False


class MaterialReviewDTO(BaseModel):
    session_id: str
    matched_points: list[MaterialReviewPointDTO] = Field(default_factory=list)
    missed_points: list[MaterialReviewPointDTO] = Field(default_factory=list)
    suggested_rewrites: list[str] = Field(default_factory=list)
    referenced_materials: list[TrainingMaterialAssetSummaryDTO] = Field(default_factory=list)
    source_state: MaterialReviewSourceStateDTO
    limits: MaterialReviewLimitsDTO


class MaterialReviewPatchDTO(BaseModel):
    matched_points: list[MaterialReviewPointDTO] | None = None
    missed_points: list[MaterialReviewPointDTO] | None = None
    suggested_rewrites: list[str] | None = None


@dataclass(frozen=True)
class MaterialReviewLLMState:
    session: TrainingSession
    materials: list[TrainingMaterialAssetSummaryDTO]
    requested_material_ids: list[int]
    report: MaterialReviewReportContext
    replay: MaterialReviewReplayContext
    fallback: MaterialReviewDTO


AsyncMaterialReviewCallback = Callable[[MaterialReviewLLMState], Awaitable[MaterialReviewPatchDTO | None]]


class TrainingMaterialReviewService:
    """Build a bounded, deterministic comparison without updating session state."""

    def build_review(
        self,
        *,
        session: TrainingSession,
        materials: list[TrainingMaterialAssetSummaryDTO],
        requested_material_ids: list[int],
        report: MaterialReviewReportContext | None = None,
        replay: MaterialReviewReplayContext | None = None,
    ) -> MaterialReviewDTO:
        selected_materials = materials[:_MAX_MATERIALS]
        report_context = report or MaterialReviewReportContext()
        replay_context = replay or MaterialReviewReplayContext(turns=[])
        context_text, report_truncated = _review_context_text(report_context, replay_context)
        matched: list[MaterialReviewPointDTO] = []
        missed: list[MaterialReviewPointDTO] = []

        for material in selected_materials:
            material_title = _material_title(material)
            for point in _material_points(material):
                item = MaterialReviewPointDTO(
                    material_id=material.id,
                    material_title=material_title,
                    point=point,
                    evidence=_matched_evidence(point, context_text),
                )
                if item.evidence:
                    matched.append(item)
                else:
                    missed.append(item)

        return MaterialReviewDTO(
            session_id=session.session_id,
            matched_points=matched[:6],
            missed_points=missed[:6],
            suggested_rewrites=_suggested_rewrites(
                missed=missed,
                report=report_context,
                session=session,
            ),
            referenced_materials=selected_materials,
            source_state=MaterialReviewSourceStateDTO(
                report_used=bool(_report_text(report_context)),
                replay_used=bool(replay_context.turns),
                material_snippet_used=any(_material_snippet(material) for material in selected_materials),
                selected_material_ids=[material.id for material in selected_materials],
            ),
            limits=MaterialReviewLimitsDTO(
                material_count=len(selected_materials),
                requested_material_count=len(requested_material_ids),
                material_selection_truncated=len(requested_material_ids) > len(selected_materials),
                material_snippets_truncated=any(
                    material.content_excerpt_truncated for material in selected_materials
                ),
                report_context_truncated=report_context.truncated or report_truncated,
                replay_transcript_truncated=replay_context.truncated,
            ),
        )

    async def build_review_async(
        self,
        *,
        session: TrainingSession,
        materials: list[TrainingMaterialAssetSummaryDTO],
        requested_material_ids: list[int],
        report: MaterialReviewReportContext | None = None,
        replay: MaterialReviewReplayContext | None = None,
        async_llm_callback: AsyncMaterialReviewCallback | None = None,
    ) -> MaterialReviewDTO:
        report_context = report or MaterialReviewReportContext()
        replay_context = replay or MaterialReviewReplayContext(turns=[])
        fallback = self.build_review(
            session=session,
            materials=materials,
            requested_material_ids=requested_material_ids,
            report=report_context,
            replay=replay_context,
        )
        if async_llm_callback is None:
            return fallback
        try:
            llm_patch = await async_llm_callback(
                MaterialReviewLLMState(
                    session=session,
                    materials=materials[:_MAX_MATERIALS],
                    requested_material_ids=requested_material_ids,
                    report=report_context,
                    replay=replay_context,
                    fallback=fallback,
                )
            )
        except Exception:
            logger.exception("Training material review LLM callback failed")
            return fallback
        if llm_patch is None:
            return fallback
        source_state = fallback.source_state.model_copy(
            update={
                "strategy": "llm_adapter",
                "llm_used": True,
            }
        )
        return fallback.model_copy(
            update={
                "matched_points": (
                    fallback.matched_points
                    if llm_patch.matched_points is None
                    else llm_patch.matched_points
                ),
                "missed_points": (
                    fallback.missed_points
                    if llm_patch.missed_points is None
                    else llm_patch.missed_points
                ),
                "suggested_rewrites": (
                    fallback.suggested_rewrites
                    if llm_patch.suggested_rewrites is None
                    else llm_patch.suggested_rewrites
                ),
                "source_state": source_state,
            }
        )


def normalize_material_review_ids(
    material_ids: list[int] | None,
    selected_material_ids: list[int] | None = None,
) -> list[int]:
    raw_ids = material_ids if material_ids else selected_material_ids
    seen: set[int] = set()
    result: list[int] = []
    for raw_id in raw_ids or []:
        material_id = int(raw_id)
        if material_id <= 0 or material_id in seen:
            continue
        seen.add(material_id)
        result.append(material_id)
    return result


def _review_context_text(
    report: MaterialReviewReportContext,
    replay: MaterialReviewReplayContext,
) -> tuple[str, bool]:
    parts = [_report_text(report), "\n".join(replay.turns[:_MAX_REPLAY_TURNS])]
    text = "\n\n".join(part for part in parts if part).strip()
    if len(text) <= _MAX_CONTEXT_CHARS:
        return text, False
    return text[:_MAX_CONTEXT_CHARS].rstrip(), True


def _report_text(report: MaterialReviewReportContext) -> str:
    content = report.content or {}
    parts = [report.summary]
    for key in (
        "communication_suggestions",
        "micro_drills",
        "rewrite_demos",
        "effective_arguments",
        "evidence_reviews",
        "high_signal_moments",
    ):
        value = content.get(key)
        if isinstance(value, list):
            parts.extend(_string_values(item) for item in value[:5])
    return "\n".join(part for part in parts if part).strip()


def _string_values(value: Any) -> str:
    if isinstance(value, str):
        return _compact(value)
    if isinstance(value, dict):
        parts = []
        for key in (
            "suggestion",
            "prompt",
            "rewritten",
            "argument",
            "effectiveness",
            "claim",
            "insight",
            "recommendation",
            "why_it_matters",
            "title",
        ):
            text = _compact(value.get(key))
            if text:
                parts.append(text)
        return " ".join(parts)
    return ""


def _material_points(material: TrainingMaterialAssetSummaryDTO) -> list[str]:
    candidates: list[str] = []
    metadata = material.metadata_excerpt or {}
    for key in ("summary", "description", "title"):
        text = _compact(metadata.get(key))
        if text:
            candidates.append(text)
    snippet = _material_snippet(material)
    if snippet:
        candidates.extend(_split_points(snippet))

    points: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        point = _compact(candidate)
        if not point or len(point) < 12:
            continue
        key = point.lower()
        if key in seen:
            continue
        seen.add(key)
        points.append(_limit_text(point, _POINT_TEXT_LIMIT))
        if len(points) >= _MAX_MATERIAL_POINTS:
            break
    return points or [_material_title(material)]


def _split_points(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n+|(?<=[.!?。！？])\s+", normalized)
    return [_compact(chunk) for chunk in chunks if _compact(chunk)]


def _matched_evidence(point: str, context_text: str) -> str | None:
    if not context_text:
        return None
    point_tokens = _tokens(point)
    context_tokens = _tokens(context_text)
    if not point_tokens or not context_tokens:
        return None
    overlap = point_tokens & context_tokens
    score = len(overlap) / max(1, len(point_tokens))
    if score < 0.24 and not _phrase_hint(point, context_text):
        return None
    return _evidence_window(context_text, overlap)


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _WORD_RE.finditer(text)}


def _phrase_hint(point: str, context_text: str) -> bool:
    lowered_context = context_text.lower()
    for chunk in _split_points(point):
        lowered = chunk.lower()
        if len(lowered) >= 18 and lowered in lowered_context:
            return True
    return False


def _evidence_window(context_text: str, overlap: set[str]) -> str:
    lines = [_compact(line) for line in context_text.splitlines() if _compact(line)]
    for line in lines:
        line_tokens = _tokens(line)
        if line_tokens & overlap:
            return _limit_text(line, 220)
    return _limit_text(context_text, 220)


def _suggested_rewrites(
    *,
    missed: list[MaterialReviewPointDTO],
    report: MaterialReviewReportContext,
    session: TrainingSession,
) -> list[str]:
    suggestions: list[str] = []
    for item in missed[:_SUGGESTION_LIMIT]:
        suggestions.append(
            f"Next drill: explicitly cover \"{_limit_text(item.point, 120)}\" before moving to trade-offs."
        )
    if len(suggestions) < 2:
        suggestions.extend(_report_suggestions(report.content or {}))
    if len(suggestions) < 2:
        role = session.task_config.role or "your role"
        suggestions.append(
            f"Practice a tighter {role} answer: state the claim, give one proof point, then ask for the next constraint."
        )
    return _dedupe(suggestions)[:_SUGGESTION_LIMIT]


def _report_suggestions(content: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    for key in ("communication_suggestions", "micro_drills", "rewrite_demos"):
        value = content.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            text = _string_values(item)
            if text:
                suggestions.append(_limit_text(text, 180))
    return suggestions


def _material_title(material: TrainingMaterialAssetSummaryDTO) -> str:
    metadata = material.metadata_excerpt or {}
    return (
        _compact(metadata.get("title"))
        or _compact(metadata.get("name"))
        or material.name
        or f"material-{material.id}"
    )


def _material_snippet(material: TrainingMaterialAssetSummaryDTO) -> str:
    return _compact(material.content_excerpt)


def _compact(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()


def _limit_text(text: str, limit: int) -> str:
    compact = _compact(text)
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = _compact(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result
