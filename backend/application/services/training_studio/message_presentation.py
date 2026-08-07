"""Shared training-message presentation, emotion, and speech contracts."""

from __future__ import annotations

import json
import re
from typing import Any

_EMOTION_RE = re.compile(r"\s*<!--emotion:\s*(\{.*?\})\s*-->\s*$", re.DOTALL)
_EMOTION_MARKER = "<!--emotion:"
_EMOTION_COMPLETE_RE = re.compile(r"<!--emotion:\s*\{.*?\}\s*-->", re.DOTALL)
_EMOTION_PARTIAL_RE = re.compile(r"<!--emotion:.*$", re.DOTALL | re.IGNORECASE)
_PARENTHETICAL_RE = re.compile(r"[（(]([^（）()\n]*)[）)]")
_PARENTHETICAL_PARTIAL_RE = re.compile(r"[（(][^（）()\n]*$")


def extract_emotion(content: str) -> tuple[str, int | None, str | None]:
    """Remove a trailing private emotion marker and return its validated values."""

    match = _EMOTION_RE.search(content)
    if not match:
        return content, None, None
    try:
        data = json.loads(match.group(1))
        score = int(data.get("score", 0))
        score = max(-5, min(5, score))
        label = str(data.get("label", ""))[:20].strip() or None
    except (json.JSONDecodeError, TypeError, ValueError):
        return content[: match.start()].rstrip(), None, None
    return content[: match.start()].rstrip(), score, label


def strip_emotion_markers(content: str) -> str:
    """Remove complete or partial private markers from text sent to users or TTS."""

    return _EMOTION_PARTIAL_RE.sub("", _EMOTION_COMPLETE_RE.sub("", content)).strip()


def split_visible_stream_delta(buffer: str) -> tuple[str, str]:
    """Keep a trailing private marker in a buffer while exposing visible text."""

    lower = buffer.lower()
    marker_index = lower.find(_EMOTION_MARKER)
    if marker_index >= 0:
        return buffer[:marker_index], buffer[marker_index:]

    max_prefix = min(len(buffer), len(_EMOTION_MARKER) - 1)
    for size in range(max_prefix, 0, -1):
        if _EMOTION_MARKER.startswith(lower[-size:]):
            return buffer[:-size], buffer[-size:]
    return buffer, ""


def strip_parenthetical_cues_for_speech(content: str) -> str:
    """Remove all parenthetical material before speech synthesis.

    Parentheses are a display channel for actions, expressions, and asides;
    providers should receive only text that is safe to speak verbatim.
    """

    content = _PARENTHETICAL_RE.sub("", content)
    return _PARENTHETICAL_PARTIAL_RE.sub("", content).strip()


def training_reply_instruction() -> str:
    """Prompt contract for text training runtimes."""

    return (
        "\n\n## 训练回复格式（必须遵守）\n"
        "像真实对话对象一样简短回应。需要表达动作、神态或停顿时，可以在正文中自行决定是否使用括号内容；"
        "这些括号内容只用于界面呈现，不要写成长篇剧本。\n"
        "回复最后另起一行输出私有情绪标记，格式严格为：\n"
        '<!--emotion:{"score":X,"label":"Y"}-->\n'
        "score 为 -5 到 +5 的整数，label 为 2-4 个字的当前情绪。该标记不会展示给用户。"
    )


def emotion_metadata(
    score: int | None,
    label: str | None,
) -> dict[str, Any] | None:
    """Build the stable metadata payload used by the conversation-tree client."""

    if score is None and not label:
        return None
    return {
        "source": "model",
        "score": score,
        "label": label,
        "version": 1,
    }
