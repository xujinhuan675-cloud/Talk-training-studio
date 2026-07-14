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
    assert payload["metadata"] == {"source": "test_callback"}


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
        recent_turns=[{"speaker": "counterpart", "text": "What is your plan for pricing?"}],
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
