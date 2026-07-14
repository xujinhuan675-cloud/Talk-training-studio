from application.services.training_studio.live_guidance_service import (
    GuideEvent,
    GuideEventType,
    GuideSeverity,
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)


def _event_types(events: list[GuideEvent]) -> set[str]:
    return {
        event.event_type.value if isinstance(event.event_type, GuideEventType) else event.event_type
        for event in events
    }


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
