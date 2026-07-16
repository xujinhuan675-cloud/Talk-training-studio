import pytest

from application.ports.realtime import RealtimeSessionBinding
from application.services.training_studio.realtime_pipeline import (
    MemoryTrainingTranscriptSink,
    StaticTrainingContextInjector,
    build_realtime_transcript,
    extract_final_transcript,
    transcript_to_message_metadata,
)


def test_build_realtime_transcript_maps_openai_user_event_to_provider_neutral_dto():
    binding = RealtimeSessionBinding(training_session_id="training-1", room_id=42)

    transcript = build_realtime_transcript(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "evt_1",
            "item_id": "item_1",
            "transcript": "  We can start with a pilot.  ",
            "metadata": {
                "trainingProfile": "live_coach",
                "sourceLanguage": "zh-CN",
                "targetLanguage": "en-US",
                "translationStrategy": "text_first_mvp",
                "translation": {
                    "mode": "text_first_mvp",
                    "sourceLanguage": "zh-CN",
                    "targetLanguage": "en-US",
                    "preserveTone": True,
                    "nested": {"drop": True},
                },
            },
        },
        binding=binding,
        provider="openai",
        realtime_session_id="rt-1",
    )

    assert transcript is not None
    assert transcript.text == "We can start with a pilot."
    assert transcript.role == "user"
    assert transcript.binding == binding
    assert transcript.provider == "openai"
    assert transcript.event_id == "evt_1"
    assert transcript.item_id == "item_1"
    assert transcript.metadata["trainingProfile"] == "live_coach"
    assert transcript.metadata["translation"] == {
        "mode": "text_first_mvp",
        "sourceLanguage": "zh-CN",
        "targetLanguage": "en-US",
        "preserveTone": True,
    }
    assert transcript.metadata["realtime"]["translationIntent"] == "text_first_mvp"


def test_build_realtime_transcript_maps_response_events_to_assistant_role():
    transcript = build_realtime_transcript(
        {
            "type": "response.audio_transcript.done",
            "eventId": "evt_assistant",
            "response": "response_1",
            "text": "That works if the metric is clear.",
        },
        binding=RealtimeSessionBinding(training_session_id="training-2", room_id=7),
        provider="pipecat",
        realtime_session_id="rt-2",
    )

    assert transcript is not None
    assert transcript.role == "assistant"
    assert transcript.response_id == "response_1"
    metadata = transcript_to_message_metadata(transcript)
    assert metadata["source"] == "realtime_voice"
    assert metadata["trainingMode"] == "voice"
    assert metadata["interactionMode"] == "realtime"
    assert metadata["realtime"]["provider"] == "pipecat"
    assert metadata["realtime"]["role"] == "assistant"
    assert metadata["realtime"]["trainingSessionId"] == "training-2"
    assert metadata["realtime"]["roomId"] == 7


def test_non_final_or_empty_transcript_events_are_ignored():
    assert extract_final_transcript({"type": "response.created", "text": "draft"}) is None
    assert extract_final_transcript({"type": "transcript.done", "text": "   "}) is None
    assert (
        build_realtime_transcript(
            {"type": "response.created", "text": "draft"},
            binding=RealtimeSessionBinding(training_session_id="training-3", room_id=9),
            provider="openai",
            realtime_session_id="rt-3",
        )
        is None
    )


@pytest.mark.asyncio
async def test_transcript_sink_persists_without_transport_dependency():
    binding = RealtimeSessionBinding(training_session_id="training-4", room_id=11)
    transcript = build_realtime_transcript(
        {
            "type": "response.output_audio_transcript.done",
            "text": "I can clarify the acceptance criteria first.",
        },
        binding=binding,
        provider="pipecat",
        realtime_session_id="rt-4",
    )
    assert transcript is not None

    sink = MemoryTrainingTranscriptSink()
    persisted = await sink.persist(transcript)

    assert persisted.message_id == 1
    assert sink.persisted == [transcript]
    assert persisted.payload["content"] == "I can clarify the acceptance criteria first."
    assert persisted.payload["sender_type"] == "persona"
    assert persisted.payload["sender_id"] == "assistant"
    assert persisted.payload["metadata"]["realtime"]["provider"] == "pipecat"


@pytest.mark.asyncio
async def test_static_context_injector_builds_pipeline_context():
    binding = RealtimeSessionBinding(training_session_id="training-5", room_id=12)
    injector = StaticTrainingContextInjector(
        task_goal="Practice discovery",
        rubric={"discovery": 0.4},
        recent_turns=[{"speaker": "counterpart", "text": "What is your plan?"}],
        metadata={"scenario": "sales"},
    )

    context = await injector.build_context(binding)

    assert context.binding == binding
    assert context.task_goal == "Practice discovery"
    assert context.rubric == {"discovery": 0.4}
    assert context.recent_turns == ({"speaker": "counterpart", "text": "What is your plan?"},)
    assert context.metadata == {"scenario": "sales"}
