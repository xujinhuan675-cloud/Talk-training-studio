import json

import pytest

from application.ports.llm import LLMResponse
from application.services.training_studio.live_guidance_llm_adapter import LiveGuidanceLLMAdapter
from application.services.training_studio.live_guidance_service import (
    GuideEvent,
    GuideEventType,
    GuideSeverity,
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)


class _FakeLLM:
    def __init__(self, content: str) -> None:
        self.content = content
        self.messages = None
        self.kwargs = None

    async def generate(self, messages, **kwargs):
        self.messages = messages
        self.kwargs = kwargs
        return LLMResponse(content=self.content, model="fake")


def _event_types(events: list[GuideEvent]) -> set[str]:
    return {
        event.event_type.value if isinstance(event.event_type, GuideEventType) else event.event_type
        for event in events
    }


def _stable_payloads(events: list[GuideEvent]) -> list[dict[str, object]]:
    return [
        {key: value for key, value in event.to_sse_payload().items() if key != "created_at"}
        for event in events
    ]


def test_long_monologue_triggers_delivery_nudge():
    service = TrainingLiveGuidanceService(monologue_word_threshold=20)
    long_answer = " ".join(["I can explain the roadmap tradeoff clearly"] * 5)

    events = service.generate_guidance(
        training_session_id="training-1",
        task_goal="Practice concise PM interview answers",
        rubric={"delivery": 0.2},
        recent_turns=[TranscriptTurn(speaker=TranscriptSpeaker.USER, text=long_answer)],
    )

    delivery = next(event for event in events if event.event_type == GuideEventType.DELIVERY_NUDGE)
    assert delivery.severity == GuideSeverity.WARNING
    assert delivery.suggested_text
    assert delivery.metadata["word_count"] >= 20


def test_simulation_mode_has_no_in_conversation_guidance_events():
    service = TrainingLiveGuidanceService(monologue_word_threshold=1)

    events = service.generate_guidance(
        training_session_id="training-simulation",
        task_goal="Run the role-play",
        recent_turns=[TranscriptTurn(speaker=TranscriptSpeaker.USER, text="A long answer")],
        feedback_mode="simulation",
    )

    assert events == []


def test_drill_mode_emits_only_structured_correction_event_in_session_language():
    service = TrainingLiveGuidanceService()

    events = service.generate_guidance(
        training_session_id="training-drill",
        task_goal="Practice a concise answer",
        recent_turns=[
            TranscriptTurn(
                speaker=TranscriptSpeaker.USER,
                text="嗯我觉得这个方案大概就是这样",
                turn_id="turn-3",
            ),
        ],
        feedback_mode="drill",
        language="zh-CN",
    )

    assert len(events) == 1
    assert events[0].event_type == GuideEventType.CORRECTION
    assert events[0].metadata["targetTurnId"] == "turn-3"
    assert events[0].metadata["feedbackMode"] == "drill"
    assert events[0].title == "纠正上一句表达"
    assert events[0].message == "删掉开头的口头填充词，直接说出核心信息。"
    assert events[0].suggested_text == "我觉得这个方案大概就是这样"


def test_assisted_mode_localizes_side_guidance_from_session_language():
    service = TrainingLiveGuidanceService()

    events = service.generate_guidance(
        training_session_id="training-assisted-zh",
        task_goal="练习提问",
        recent_turns=[{"speaker": "user", "text": "嗯我觉得这个方案大概就是这样"}],
        feedback_mode="assisted",
        language="zh-CN",
    )

    next_reply = next(event for event in events if event.event_type == GuideEventType.NEXT_REPLY)
    assert next_reply.title == "下一句建议"
    assert next_reply.message == "根据当前有限对话窗口生成的简短下一步建议。"


def test_missing_question_triggers_ask_back_and_omission():
    service = TrainingLiveGuidanceService()

    events = service.generate_guidance(
        training_session_id="training-2",
        task_goal="Discover the stakeholder's constraints",
        rubric={"relevance": 0.3, "structure": 0.2},
        recent_turns=[
            TranscriptTurn(
                speaker=TranscriptSpeaker.USER,
                text="I would start by explaining the solution and then describe why the timeline is reasonable.",
            ),
            TranscriptTurn(
                speaker=TranscriptSpeaker.USER,
                text="The main benefit is that it aligns everyone and gives us a clean launch sequence.",
            ),
        ],
    )

    assert {GuideEventType.ASK_BACK, GuideEventType.OMISSION} <= {
        event.event_type for event in events
    }
    ask_back = next(event for event in events if event.event_type == GuideEventType.ASK_BACK)
    assert "?" in ask_back.suggested_text


def test_clear_objection_triggers_risk_objection_event():
    service = TrainingLiveGuidanceService()

    events = service.generate_guidance(
        training_session_id="training-3",
        task_goal="Handle stakeholder objections",
        rubric={"credibility": 0.25},
        recent_turns=[
            TranscriptTurn(speaker=TranscriptSpeaker.USER, text="I recommend we launch this quarter."),
            TranscriptTurn(
                speaker=TranscriptSpeaker.COUNTERPART,
                text="I am not convinced. The cost feels too expensive and risky for this team.",
            ),
        ],
    )

    risk = next(event for event in events if event.event_type == GuideEventType.RISK)
    assert risk.metadata["risk_type"] == "objection"
    assert risk.metadata["matched_phrase"] in {
        "not convinced",
        "cost",
        "too expensive",
        "risk",
        "risky",
    }


def test_window_strategy_only_uses_recent_turns():
    service = TrainingLiveGuidanceService(window_size=2)

    state = service.build_state(
        training_session_id="training-4",
        task_goal="Stay bounded",
        rubric={},
        recent_turns=[
            TranscriptTurn(speaker=TranscriptSpeaker.COUNTERPART, text="I have a concern."),
            TranscriptTurn(speaker=TranscriptSpeaker.USER, text="Thanks, I will address it."),
            TranscriptTurn(speaker=TranscriptSpeaker.USER, text="Here is the concise answer."),
        ],
    )
    events = service.generate_guidance(
        training_session_id=state.training_session_id,
        task_goal=state.task_goal,
        rubric=state.rubric,
        recent_turns=state.recent_turns,
    )

    assert len(state.recent_turns) == 2
    assert state.total_turn_count == 3
    assert GuideEventType.RISK.value not in _event_types(events)


def test_llm_callback_can_add_sse_ready_event_without_network_dependency():
    def callback(state):
        assert state.window_size == 8
        return [
            {
                "event_type": "omission",
                "severity": "info",
                "title": "LLM note",
                "message": "Callback supplied guidance.",
                "suggested_text": "Ask for the acceptance criteria.",
                "metadata": {"source": "test_callback"},
            }
        ]

    service = TrainingLiveGuidanceService(llm_callback=callback)

    events = service.generate_guidance(
        training_session_id="training-5",
        task_goal="Use injected guidance",
        rubric={},
        recent_turns=[{"speaker": "counterpart", "text": "Tell me your plan."}],
    )

    payload = events[-1].to_sse_payload()
    assert payload["event_type"] == "omission"
    assert payload["metadata"] == {
        "source": "test_callback",
        "feedbackMode": "assisted",
        "language": "en-US",
        "channel": "side_event",
    }


@pytest.mark.asyncio
async def test_async_guidance_without_llm_matches_deterministic_fallback():
    service = TrainingLiveGuidanceService(monologue_word_threshold=20)
    kwargs = {
        "training_session_id": "training-no-llm",
        "task_goal": "Keep fallback deterministic",
        "rubric": {"delivery": 0.2},
        "recent_turns": [
            TranscriptTurn(
                speaker=TranscriptSpeaker.USER,
                text=" ".join(["This answer keeps going without a pause"] * 5),
            )
        ],
    }

    sync_events = service.generate_guidance(**kwargs)
    async_events = await service.generate_guidance_async(**kwargs)

    assert _stable_payloads(async_events) == _stable_payloads(sync_events)


@pytest.mark.asyncio
async def test_llm_adapter_json_response_adds_guide_event():
    llm = _FakeLLM(
        json.dumps(
            {
                "events": [
                    {
                        "event_type": "risk",
                        "severity": "warning",
                        "title": "Pricing risk",
                        "message": "The counterpart is asking for commercial reassurance.",
                        "suggested_text": "Let me separate price from implementation risk first.",
                        "metadata": {"reason": "commercial"},
                    }
                ]
            }
        )
    )
    service = TrainingLiveGuidanceService(async_llm_callback=LiveGuidanceLLMAdapter(llm))

    events = await service.generate_guidance_async(
        training_session_id="training-llm-json",
        task_goal="Handle price pressure",
        rubric={"discovery": 0.4},
        recent_turns=[
            {
                "speaker": "counterpart",
                "text": "What is your plan for pricing?",
                "metadata": {
                    "trainingProfile": "live_coach",
                    "sourceLanguage": "zh-CN",
                    "targetLanguage": "en-US",
                    "translationStrategy": "text_first_mvp",
                },
            }
        ],
    )

    llm_event = next(event for event in events if event.metadata.get("source") == "llm")
    assert llm_event.event_type == GuideEventType.RISK
    assert llm_event.severity == GuideSeverity.WARNING
    assert llm_event.title == "Pricing risk"
    assert llm_event.suggested_text == "Let me separate price from implementation risk first."
    assert llm_event.metadata["training_session_id"] == "training-llm-json"
    assert llm.messages[0].role == "system"
    prompt_payload = json.loads(llm.messages[1].content)
    assert prompt_payload["task_goal"] == "Handle price pressure"
    assert prompt_payload["recent_turns"][0]["speaker"] == "counterpart"
    assert prompt_payload["recent_turns"][0]["metadata"]["trainingProfile"] == "live_coach"
    assert prompt_payload["recent_turns"][0]["metadata"]["sourceLanguage"] == "zh-CN"
    assert prompt_payload["recent_turns"][0]["metadata"]["targetLanguage"] == "en-US"
    assert prompt_payload["recent_turns"][0]["metadata"]["translationStrategy"] == "text_first_mvp"


@pytest.mark.asyncio
async def test_llm_adapter_text_response_degrades_to_next_reply_event():
    text = "Acknowledge the concern, ask which risk matters most, then answer in one sentence."
    llm = _FakeLLM(text)
    service = TrainingLiveGuidanceService(async_llm_callback=LiveGuidanceLLMAdapter(llm))

    events = await service.generate_guidance_async(
        training_session_id="training-llm-text",
        task_goal="Handle a risk objection",
        rubric={},
        recent_turns=[
            {"speaker": "counterpart", "text": "I am worried this is too risky for the team."}
        ],
    )

    llm_event = next(event for event in events if event.metadata.get("source") == "llm")
    assert llm_event.event_type == GuideEventType.NEXT_REPLY
    assert llm_event.severity == GuideSeverity.INFO
    assert llm_event.suggested_text == text
    assert llm_event.metadata["format"] == "text"


@pytest.mark.asyncio
async def test_drill_llm_adapter_returns_correction_in_requested_language():
    llm = _FakeLLM(
        json.dumps(
            {
                "events": [
                    {
                        "event_type": "correction",
                        "severity": "info",
                        "message": "先说结论，再补充原因。",
                        "suggested_text": "我的结论是先保留方案，原因是风险可控。",
                    },
                    {
                        "event_type": "next_reply",
                        "message": "This must be filtered in drill mode.",
                    },
                ]
            }
        )
    )
    service = TrainingLiveGuidanceService(async_llm_callback=LiveGuidanceLLMAdapter(llm))

    events = await service.generate_guidance_async(
        training_session_id="training-drill-llm",
        task_goal="Practice a concise answer",
        recent_turns=[
            {"speaker": "user", "text": "我觉得可以这样做", "turn_id": "turn-4"}
        ],
        feedback_mode="drill",
        language="zh-CN",
    )

    assert len(events) == 1
    assert events[0].event_type == GuideEventType.CORRECTION
    assert events[0].suggested_text == "我的结论是先保留方案，原因是风险可控。"
    assert events[0].metadata["targetTurnId"] == "turn-4"
    assert "drill" in llm.messages[0].content
    assert "zh-CN" in llm.messages[0].content


def test_llm_adapter_localizes_suggestion_only_fallback_fields():
    state = TrainingLiveGuidanceService().build_state(
        training_session_id="training-guidance-zh",
        task_goal="练习表达",
        rubric=None,
        recent_turns=[{"speaker": "user", "text": "我想先说明结论。"}],
        feedback_mode="assisted",
        language="zh-CN",
    )
    adapter = LiveGuidanceLLMAdapter(_FakeLLM("unused"))

    structured = adapter.parse_response(
        json.dumps({"events": [{"event_type": "risk", "suggested_text": "先确认风险。"}]}),
        state,
    )
    unstructured = adapter.parse_response("先说结论，再补充原因。", state)

    assert structured[0].title == "风险提示"
    assert structured[0].message == "模型生成了一条下一步表达建议。"
    assert unstructured[0].title == "模型建议"
    assert unstructured[0].message == "模型返回了非结构化建议，已作为下一句候选展示。"


@pytest.mark.asyncio
async def test_llm_adapter_invalid_json_is_ignored_without_changing_fallback():
    kwargs = {
        "training_session_id": "training-llm-invalid",
        "task_goal": "Ignore malformed LLM output",
        "rubric": {},
        "recent_turns": [{"speaker": "counterpart", "text": "Tell me more."}],
    }
    fallback_service = TrainingLiveGuidanceService()
    service = TrainingLiveGuidanceService(
        async_llm_callback=LiveGuidanceLLMAdapter(_FakeLLM('{"events": ['))
    )

    fallback_events = await fallback_service.generate_guidance_async(**kwargs)
    events = await service.generate_guidance_async(**kwargs)

    assert _stable_payloads(events) == _stable_payloads(fallback_events)
