"""LLMPort adapter for Training Studio live guidance."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from application.ports.llm import LLMMessage, LLMPort
from application.services.training_studio.live_guidance_service import (
    GuidanceState,
    GuideEvent,
    GuideEventType,
    GuideSeverity,
    TranscriptTurn,
)

logger = logging.getLogger(__name__)

_GUIDANCE_SYSTEM_PROMPT = """You are a concise live communication coach.
Read the bounded Training Studio transcript state and return only extra guidance
that is useful right now. Do not repeat obvious rule-based hints.

Return JSON in this shape:
{
  "events": [
    {
      "event_type": "next_reply|risk|omission|ask_back|delivery_nudge",
      "severity": "info|warning|critical",
      "title": "short label",
      "message": "why this matters now",
      "suggested_text": "optional exact wording the trainee can say",
      "metadata": {"reason": "optional"}
    }
  ]
}

Return {"events": []} when no extra guidance is needed. Keep events short."""

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.IGNORECASE | re.DOTALL)
_MAX_TEXT_EVENT_CHARS = 500


class LiveGuidanceLLMAdapter:
    """Convert GuidanceState to LLM messages and LLM output to GuideEvent objects."""

    def __init__(
        self,
        llm: LLMPort,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 500,
    ) -> None:
        self._llm = llm
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def __call__(self, state: GuidanceState) -> list[GuideEvent]:
        try:
            response = await self._llm.generate(
                self.build_messages(state),
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except Exception:
            logger.exception("Training live guidance LLM call failed")
            return []
        return self.parse_response(response.content, state)

    def build_messages(self, state: GuidanceState) -> list[LLMMessage]:
        return [
            LLMMessage(role="system", content=_GUIDANCE_SYSTEM_PROMPT),
            LLMMessage(
                role="user",
                content=json.dumps(self._state_payload(state), ensure_ascii=False, default=str),
            ),
        ]

    def parse_response(self, content: str, state: GuidanceState) -> list[GuideEvent]:
        text = content.strip()
        if not text:
            return []

        parsed = _parse_json_value(text)
        if parsed is None:
            if _looks_like_structured_response(text):
                logger.warning("Ignoring invalid structured live guidance LLM response: %s", text[:200])
                return []
            return [self._text_fallback_event(text, state)]

        if isinstance(parsed, str):
            return [self._text_fallback_event(parsed, state)]

        raw_events = _extract_event_items(parsed)
        events: list[GuideEvent] = []
        for item in raw_events:
            event = self._event_from_mapping(item, state)
            if event is not None:
                events.append(event)
        return events

    def _event_from_mapping(self, item: dict[str, Any], state: GuidanceState) -> GuideEvent | None:
        message = _first_text(item, "message", "rationale", "reason")
        suggested_text = _first_text(item, "suggested_text", "suggestion", "next_reply")
        if not message and not suggested_text:
            return None
        if not message:
            message = "LLM supplied a suggested next move."

        metadata = item.get("metadata")
        clean_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        clean_metadata.setdefault("source", "llm")
        clean_metadata.setdefault("training_session_id", state.training_session_id)

        event_type = _coerce_event_type(item.get("event_type") or item.get("type"))
        return GuideEvent(
            event_type=event_type,
            severity=_coerce_severity(item.get("severity")),
            title=_first_text(item, "title") or _default_title(event_type),
            message=message,
            suggested_text=suggested_text or None,
            metadata=clean_metadata,
        )

    def _text_fallback_event(self, text: str, state: GuidanceState) -> GuideEvent:
        compact_text = _compact_text(text)
        return GuideEvent(
            event_type=GuideEventType.NEXT_REPLY,
            severity=GuideSeverity.INFO,
            title="LLM guidance",
            message="LLM returned unstructured guidance; surfaced as a next reply candidate.",
            suggested_text=compact_text,
            metadata={
                "source": "llm",
                "format": "text",
                "training_session_id": state.training_session_id,
            },
        )

    @staticmethod
    def _state_payload(state: GuidanceState) -> dict[str, Any]:
        return {
            "training_session_id": state.training_session_id,
            "task_goal": state.task_goal,
            "rubric": state.rubric,
            "window_size": state.window_size,
            "total_turn_count": state.total_turn_count,
            "recent_turns": [_turn_payload(turn) for turn in state.recent_turns],
        }


def _turn_payload(turn: TranscriptTurn) -> dict[str, Any]:
    return {
        "speaker": turn.normalized_speaker,
        "text": turn.text,
        "turn_id": turn.turn_id,
        "created_at": turn.created_at.isoformat() if turn.created_at else None,
        "metadata": turn.metadata,
    }


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

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
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


def _looks_like_structured_response(text: str) -> bool:
    stripped = text.lstrip()
    return stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("```")


def _extract_event_items(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if not isinstance(parsed, dict):
        return []
    events = parsed.get("events")
    if isinstance(events, list):
        return [item for item in events if isinstance(item, dict)]
    if "event_type" in parsed or "type" in parsed:
        return [parsed]
    return []


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _coerce_event_type(value: Any) -> GuideEventType:
    raw = str(value or "").strip().lower()
    aliases = {
        "next": GuideEventType.NEXT_REPLY,
        "next_reply": GuideEventType.NEXT_REPLY,
        "reply": GuideEventType.NEXT_REPLY,
        "suggestion": GuideEventType.NEXT_REPLY,
        "risk": GuideEventType.RISK,
        "objection": GuideEventType.RISK,
        "omission": GuideEventType.OMISSION,
        "gap": GuideEventType.OMISSION,
        "ask": GuideEventType.ASK_BACK,
        "ask_back": GuideEventType.ASK_BACK,
        "question": GuideEventType.ASK_BACK,
        "delivery": GuideEventType.DELIVERY_NUDGE,
        "delivery_nudge": GuideEventType.DELIVERY_NUDGE,
    }
    return aliases.get(raw, GuideEventType.NEXT_REPLY)


def _coerce_severity(value: Any) -> GuideSeverity:
    raw = str(value or "").strip().lower()
    aliases = {
        "info": GuideSeverity.INFO,
        "low": GuideSeverity.INFO,
        "warning": GuideSeverity.WARNING,
        "warn": GuideSeverity.WARNING,
        "medium": GuideSeverity.WARNING,
        "critical": GuideSeverity.CRITICAL,
        "high": GuideSeverity.CRITICAL,
        "error": GuideSeverity.CRITICAL,
    }
    return aliases.get(raw, GuideSeverity.INFO)


def _default_title(event_type: GuideEventType) -> str:
    titles = {
        GuideEventType.NEXT_REPLY: "Next reply candidate",
        GuideEventType.RISK: "Risk surfaced",
        GuideEventType.OMISSION: "Discovery gap",
        GuideEventType.ASK_BACK: "Ask a calibration question",
        GuideEventType.DELIVERY_NUDGE: "Delivery nudge",
    }
    return titles[event_type]


def _compact_text(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _MAX_TEXT_EVENT_CHARS:
        return compact
    return compact[: _MAX_TEXT_EVENT_CHARS - 3].rstrip() + "..."


__all__ = ["LiveGuidanceLLMAdapter"]
