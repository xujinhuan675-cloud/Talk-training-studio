"""Model-backed emotion analysis for training counterpart messages."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from application.ports.llm import LLMMessage, LLMPort

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(
    r"\x60\x60\x60(?:json)?\s*(.*?)\s*\x60\x60\x60", re.IGNORECASE | re.DOTALL
)

_TRAINING_MESSAGE_EMOTION_SYSTEM_PROMPT = """You analyze the current emotional stance of an AI counterpart in a communication training scenario.
Use only the supplied counterpart utterance and context. Return JSON only in this shape:
{"score": -5, "label": "short label"}

The score is an integer from -5 to 5, where lower means more resistant and higher means more receptive.
Choose the label yourself from the meaning and tone of the input; do not use a fixed label list.
Do not add explanations, markdown, or fields other than score and label."""


async def analyze_training_opening_emotion(
    llm: LLMPort,
    *,
    content: str,
    context: Mapping[str, Any] | None = None,
) -> tuple[int, str | None] | None:
    """Backward-compatible entry point for scenario opening annotation."""

    return await analyze_training_message_emotion(
        llm,
        content=content,
        context=context,
    )


async def analyze_training_message_emotion(
    llm: LLMPort,
    *,
    content: str,
    context: Mapping[str, Any] | None = None,
) -> tuple[int, str | None] | None:
    """Ask the configured model to annotate a counterpart utterance.

    Analysis is best-effort: message persistence must remain available when the
    optional model client is unavailable or returns an invalid response.
    """

    utterance = content.strip()
    if not utterance:
        return None
    payload = {
        "counterpart_utterance": utterance,
        "context": dict(context or {}),
    }
    try:
        response = await llm.generate(
            [
                LLMMessage(role="system", content=_TRAINING_MESSAGE_EMOTION_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=json.dumps(payload, ensure_ascii=False, default=str),
                ),
            ],
            temperature=0.0,
            max_tokens=120,
        )
    except Exception:
        logger.exception("Training message emotion analysis failed")
        return None
    return parse_training_opening_emotion(response.content)


def parse_training_opening_emotion(content: str) -> tuple[int, str | None] | None:
    """Parse a model response without imposing semantic emotion categories."""

    text = content.strip()
    if not text:
        return None
    candidates = [text]
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    parsed: object | None = None
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    if not isinstance(parsed, dict):
        return None

    raw_score = parsed.get("score")
    if isinstance(raw_score, bool):
        return None
    try:
        score = max(-5, min(5, int(raw_score)))
    except (TypeError, ValueError):
        return None
    raw_label = parsed.get("label")
    label = str(raw_label).strip()[:20] if raw_label is not None else ""
    return score, label or None
