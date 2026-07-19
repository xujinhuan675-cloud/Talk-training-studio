"""LLMPort adapter for Training Studio material review."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from application.ports.llm import LLMMessage, LLMPort
from application.services.training_studio.material_review_service import (
    MaterialReviewLLMState,
    MaterialReviewPatchDTO,
    MaterialReviewPointDTO,
)

logger = logging.getLogger(__name__)

_MAX_LLM_POINTS = 6
_MAX_LLM_POINT_CHARS = 360
_MAX_LLM_EVIDENCE_CHARS = 220
_MAX_LLM_SUGGESTION_CHARS = 220
_MAX_LLM_REPORT_SUMMARY_CHARS = 2000
_MAX_LLM_REPORT_VALUE_CHARS = 800
_MAX_LLM_REPORT_ITEMS = 5
_MAX_LLM_REPORT_KEYS = 8
_MAX_LLM_REPLAY_TURN_CHARS = 800
_MAX_LLM_MATERIAL_SNIPPET_CHARS = 4000
_SUGGESTION_LIMIT = 3
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)

_MATERIAL_REVIEW_SYSTEM_PROMPT = """You are a Training Studio review assistant.
Compare the bounded training session context against the selected training materials.

Return JSON only in this exact shape:
{
  "matched_points": [
    {"material_id": 7, "point": "material point covered by the learner", "evidence": "short report or replay evidence"}
  ],
  "missed_points": [
    {"material_id": 7, "point": "material point the learner missed", "evidence": null}
  ],
  "suggested_rewrites": [
    "Next drill: concrete sentence or move the learner can practice."
  ]
}

Rules:
- Use only the provided material IDs and bounded snippets.
- Do not invent material content, scores, completion state, or growth metadata.
- Keep matched_points and missed_points to at most 6 each.
- Keep suggested_rewrites to 2-3 concrete practice moves.
- Evidence must come from the provided report or replay context."""


class MaterialReviewLLMAdapter:
    """Refine fallback material review lists without owning training state."""

    def __init__(
        self,
        llm: LLMPort,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 900,
    ) -> None:
        self._llm = llm
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def __call__(self, state: MaterialReviewLLMState) -> MaterialReviewPatchDTO | None:
        try:
            response = await self._llm.generate(
                self.build_messages(state),
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception:
            logger.exception("Training material review LLM call failed")
            return None
        return self.parse_response(response.content, state)

    def build_messages(self, state: MaterialReviewLLMState) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=_MATERIAL_REVIEW_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=json.dumps(_llm_payload(state), ensure_ascii=False, default=str),
            ),
        ]

    def parse_response(
        self,
        content: str,
        state: MaterialReviewLLMState,
    ) -> MaterialReviewPatchDTO | None:
        parsed = _parse_json_value(content.strip())
        if not isinstance(parsed, dict):
            logger.warning("Ignoring invalid material review LLM response: %s", content[:200])
            return None

        material_titles = {material.id: _material_title(material) for material in state.materials}
        matched = _llm_points_field(parsed, "matched_points", material_titles)
        missed = _llm_points_field(parsed, "missed_points", material_titles)
        suggestions = _llm_suggestions_field(parsed, "suggested_rewrites")
        if matched is None and missed is None and suggestions is None:
            return None

        return MaterialReviewPatchDTO(
            matched_points=matched,
            missed_points=missed,
            suggested_rewrites=suggestions,
        )


def _llm_payload(state: MaterialReviewLLMState) -> dict[str, Any]:
    fallback = state.fallback
    max_replay_turns = max(0, fallback.limits.max_replay_turns)
    return {
        "session": {
            "session_id": state.session.session_id,
            "mode": str(getattr(state.session.mode, "value", state.session.mode)),
            "scenario_template_id": state.session.scenario_template_id,
            "role": state.session.task_config.role,
            "difficulty": state.session.task_config.difficulty,
            "category": state.session.task_config.category,
        },
        "source_state": fallback.source_state.model_dump(mode="json"),
        "limits": fallback.limits.model_dump(mode="json"),
        "report": {
            "summary": _limit_text(state.report.summary, _MAX_LLM_REPORT_SUMMARY_CHARS),
            "content": _llm_report_content(state.report.content or {}),
            "truncated": state.report.truncated,
        },
        "replay": {
            "turns": [
                _limit_text(turn, _MAX_LLM_REPLAY_TURN_CHARS)
                for turn in state.replay.turns[:max_replay_turns]
            ],
            "truncated": state.replay.truncated,
        },
        "materials": [
            {
                "id": material.id,
                "title": _material_title(material),
                "metadata_excerpt": material.metadata_excerpt,
                "content_excerpt": _limit_text(
                    material.content_excerpt or "",
                    _MAX_LLM_MATERIAL_SNIPPET_CHARS,
                ),
                "content_excerpt_truncated": material.content_excerpt_truncated,
            }
            for material in state.materials
        ],
        "deterministic_fallback": {
            "matched_points": [
                point.model_dump(mode="json") for point in fallback.matched_points
            ],
            "missed_points": [
                point.model_dump(mode="json") for point in fallback.missed_points
            ],
            "suggested_rewrites": list(fallback.suggested_rewrites),
        },
    }


def _llm_report_content(content: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = (
        "communication_suggestions",
        "micro_drills",
        "rewrite_demos",
        "effective_arguments",
        "evidence_reviews",
        "high_signal_moments",
    )
    result: dict[str, Any] = {}
    for key in allowed_keys:
        if key in content:
            result[key] = _bounded_report_value(content[key])
    return result


def _bounded_report_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _limit_text(value, _MAX_LLM_REPORT_VALUE_CHARS)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [
            _bounded_report_value(item, depth=depth + 1)
            for item in value[:_MAX_LLM_REPORT_ITEMS]
        ]
    if isinstance(value, dict):
        if depth >= 2:
            return _limit_text(
                json.dumps(value, ensure_ascii=False, default=str),
                _MAX_LLM_REPORT_VALUE_CHARS,
            )
        result: dict[str, Any] = {}
        for index, (raw_key, raw_item) in enumerate(value.items()):
            if index >= _MAX_LLM_REPORT_KEYS:
                break
            key = _limit_text(_compact(raw_key), 80)
            if key:
                result[key] = _bounded_report_value(raw_item, depth=depth + 1)
        return result
    return _limit_text(str(value), _MAX_LLM_REPORT_VALUE_CHARS)


def _parse_json_value(text: str) -> Any | None:
    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.append(fenced.group(1).strip())
    candidates.append(text)

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    seen: set[str] = set()
    unique: list[str] = []
    for candidate in candidates:
        clean = candidate.strip()
        if clean and clean not in seen:
            unique.append(clean)
            seen.add(clean)
    return unique


def _llm_points_field(
    parsed: dict[str, Any],
    key: str,
    material_titles: dict[int, str],
) -> list[MaterialReviewPointDTO] | None:
    if key not in parsed:
        return None
    value = parsed.get(key)
    if not isinstance(value, list):
        return None
    points: list[MaterialReviewPointDTO] = []
    seen: set[tuple[int, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        material_id = _positive_int(item.get("material_id"))
        if material_id is None or material_id not in material_titles:
            continue
        point = _compact(item.get("point"))
        if not point:
            continue
        dedupe_key = (material_id, point.lower())
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        evidence = _limit_text(_compact(item.get("evidence")), _MAX_LLM_EVIDENCE_CHARS) or None
        points.append(
            MaterialReviewPointDTO(
                material_id=material_id,
                material_title=material_titles[material_id],
                point=_limit_text(point, _MAX_LLM_POINT_CHARS),
                evidence=evidence,
            )
        )
        if len(points) >= _MAX_LLM_POINTS:
            break
    return points or None


def _llm_suggestions_field(parsed: dict[str, Any], key: str) -> list[str] | None:
    if key not in parsed:
        return None
    value = parsed.get(key)
    if not isinstance(value, list):
        return None
    suggestions: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _limit_text(_compact(item), _MAX_LLM_SUGGESTION_CHARS)
        dedupe_key = text.lower()
        if text and dedupe_key not in seen:
            suggestions.append(text)
            seen.add(dedupe_key)
        if len(suggestions) >= _SUGGESTION_LIMIT:
            break
    return suggestions or None


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _material_title(material) -> str:
    metadata = material.metadata_excerpt or {}
    return (
        _compact(metadata.get("title"))
        or _compact(metadata.get("name"))
        or material.name
        or f"material-{material.id}"
    )


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


__all__ = ["MaterialReviewLLMAdapter"]
