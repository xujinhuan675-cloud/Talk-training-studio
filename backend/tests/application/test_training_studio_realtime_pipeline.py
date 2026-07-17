import pytest

from application.ports.realtime import RealtimeSessionBinding
from application.services.training_studio.realtime_pipeline import (
    MemoryTrainingTranscriptSink,
    RealtimeTranscriptPersistenceSink,
    StaticTrainingContextInjector,
    build_realtime_transcript,
    extract_final_transcript,
    transcript_to_message_metadata,
)
from domain.stakeholder.entity import ChatRoom, Message


class _RoomRepository:
    def __init__(self, room: ChatRoom) -> None:
        self.room = room

    async def get_by_id(self, room_id: int) -> ChatRoom | None:
        if self.room.id == room_id:
            return self.room
        return None

    async def update_last_message_at(self, room_id: int, timestamp) -> None:
        if self.room.id == room_id:
            self.room.last_message_at = timestamp


class _MessageRepository:
    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def create(self, message: Message) -> Message:
        saved = Message(
            id=len(self.messages) + 1,
            room_id=message.room_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            content=message.content,
            metadata=message.metadata,
            timestamp=message.timestamp,
        )
        self.messages.append(saved)
        return saved


class _RealtimePersistenceUoW:
    def __init__(self, room: ChatRoom, messages: _MessageRepository) -> None:
        self.chat_room_repository = _RoomRepository(room)
        self.stakeholder_message_repository = messages

    async def __aenter__(self) -> "_RealtimePersistenceUoW":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _TrainingSessionRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def record_turns(self, session_id: str, count: int = 1):
        self.calls.append((session_id, count))
        return None


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


def test_build_realtime_transcript_maps_pipecat_user_id_to_sender_metadata():
    transcript = build_realtime_transcript(
        {
            "type": "transcript.done",
            "text": "I can start with the user problem.",
            "user_id": "participant-7",
            "source": "pipecat",
        },
        binding=RealtimeSessionBinding(training_session_id="training-7", room_id=17),
        provider="pipecat",
        realtime_session_id="rt-7",
    )

    assert transcript is not None
    assert transcript.metadata["sender_id"] == "participant-7"
    metadata = transcript_to_message_metadata(transcript)
    assert metadata["sender_id"] == "participant-7"
    assert metadata["realtime"]["provider"] == "pipecat"


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
async def test_persistence_sink_writes_room_message_publishes_and_records_turn():
    room = ChatRoom(id=12, name="Realtime room", type="battle_prep")
    messages = _MessageRepository()
    recorder = _TrainingSessionRecorder()
    published = []
    transcript = build_realtime_transcript(
        {
            "type": "response.audio_transcript.done",
            "text": "We can define the pilot metric first.",
            "metadata": {"sender_id": "customer-ai", "source": "pipecat"},
        },
        binding=RealtimeSessionBinding(training_session_id="training-6", room_id=12),
        provider="pipecat",
        realtime_session_id="rt-6",
    )
    assert transcript is not None

    async def publish(room_id, message):
        published.append((room_id, message))

    sink = RealtimeTranscriptPersistenceSink(
        uow_factory=lambda **_kwargs: _RealtimePersistenceUoW(room, messages),
        session_service=recorder,
        publish_message=publish,
    )

    persisted = await sink.persist(transcript)

    assert persisted.message_id == 1
    assert persisted.payload["trainingSessionId"] == "training-6"
    assert persisted.payload["roomId"] == 12
    assert persisted.payload["message"]["content"] == "We can define the pilot metric first."
    assert messages.messages[0].sender_type == "persona"
    assert messages.messages[0].sender_id == "customer-ai"
    assert messages.messages[0].metadata["source"] == "pipecat"
    assert messages.messages[0].metadata["trainingMode"] == "voice"
    assert room.last_message_at == messages.messages[0].timestamp
    assert published[0][0] == 12
    assert published[0][1].content == "We can define the pilot metric first."
    assert recorder.calls == [("training-6", 1)]


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
