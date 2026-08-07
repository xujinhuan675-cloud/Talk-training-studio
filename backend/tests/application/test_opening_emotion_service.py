"""Focused tests for model-backed scenario opening emotion metadata."""

from __future__ import annotations

import pytest

from application.ports.llm import LLMResponse
from application.services.training_studio.opening_emotion_service import (
    analyze_training_opening_emotion,
    parse_training_opening_emotion,
)


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = None
        self.kwargs = None

    async def generate(self, messages, **kwargs) -> LLMResponse:
        self.messages = messages
        self.kwargs = kwargs
        return LLMResponse(content=self.content, model="fake-opening-model")


class _FailingLLM:
    async def generate(self, messages, **kwargs) -> LLMResponse:
        raise RuntimeError("provider unavailable")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('{"score": 3, "label": "谨慎感兴趣"}', (3, "谨慎感兴趣")),
        ('```json\n{"score": 9, "label": "  model-chosen  "}\n```', (5, "model-chosen")),
        ('结果：{"score": -9, "label": "暂不接受"}', (-5, "暂不接受")),
    ],
)
def test_parse_training_opening_emotion_accepts_model_json_and_clamps_score(
    content: str,
    expected: tuple[int, str],
) -> None:
    assert parse_training_opening_emotion(content) == expected


def test_parse_training_opening_emotion_rejects_invalid_payload() -> None:
    assert parse_training_opening_emotion("not json") is None
    assert parse_training_opening_emotion('{"score": true, "label": "x"}') is None


@pytest.mark.asyncio
async def test_analyze_training_opening_emotion_uses_configured_model() -> None:
    llm = _FakeLLM('{"score": 2, "label": "愿意了解"}')

    result = await analyze_training_opening_emotion(
        llm,
        content="你好，我看到你们门口说有新客优惠，能介绍一下吗？",
        context={"role": "Salesperson", "scenario": "new customer"},
    )

    assert result == (2, "愿意了解")
    assert llm.messages[0].role == "system"
    assert "fixed label list" in llm.messages[0].content
    assert "new customer" in llm.messages[1].content
    assert llm.kwargs == {"temperature": 0.0, "max_tokens": 120}


@pytest.mark.asyncio
async def test_analyze_training_opening_emotion_is_best_effort() -> None:
    assert (
        await analyze_training_opening_emotion(
            _FailingLLM(),
            content="开场白",
        )
        is None
    )
