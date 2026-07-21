from types import SimpleNamespace

import pytest

from application.ports.realtime import (
    REALTIME_RUNTIME_PIPECAT,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)
from application.services.training_studio.realtime_pipeline import (
    MemoryTrainingTranscriptSink,
    RealtimeTranscriptPersistenceSink,
    StaticTrainingContextInjector,
    build_realtime_transcript,
    extract_final_transcript,
    transcript_to_message_metadata,
)
from application.services.training_studio.realtime_pipeline_runner import (
    RealtimePipelineProviderError,
)
from core.config import LLMSettings, settings
from domain.stakeholder.entity import ChatRoom, Message
from domain.training_studio.session_repository import TrainingSessionAccessScope
from infrastructure.external.pipecat import realtime_pipeline as pipecat_adapter


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
    def __init__(self, *, room_id: str | None = None) -> None:
        self.calls: list[tuple[str, int]] = []
        self.room_id = room_id

    async def get_session(self, session_id: str, *, access_scope):
        self.calls.append((f"get:{session_id}", int(access_scope is not None)))
        return SimpleNamespace(session_id=session_id, room_id=self.room_id)

    async def record_turns(self, session_id: str, count: int = 1, *, access_scope):
        assert access_scope is not None
        self.calls.append((session_id, count))
        return None


class _FakePipecatService:
    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeOpenAIRealtimeSTTService(_FakePipecatService):
    pass


class _FakeOpenAITTSService(_FakePipecatService):
    pass


class _FakeOpenRouterLLMService(_FakePipecatService):
    pass


class _FakeVADAnalyzer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeVADProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeLLMContext:
    def __init__(self, messages=None, **kwargs):
        self.messages = messages or []
        self.kwargs = kwargs


class _FakeLLMUserAggregatorParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeLLMAssistantAggregatorParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeLLMUserAggregator:
    def __init__(self, context, params):
        self.context = context
        self.params = params


class _FakeLLMAssistantAggregator:
    def __init__(self, context, params):
        self.context = context
        self.params = params


class _FakeLLMContextAggregatorPair:
    def __init__(
        self,
        context,
        *,
        user_params=None,
        assistant_params=None,
        realtime_service_mode=None,
    ):
        self.context = context
        self.user_params = user_params
        self.assistant_params = assistant_params
        self.realtime_service_mode = realtime_service_mode
        self.user_aggregator = _FakeLLMUserAggregator(context, user_params)
        self.assistant_aggregator = _FakeLLMAssistantAggregator(context, assistant_params)

    def __iter__(self):
        return iter((self.user_aggregator, self.assistant_aggregator))


class _FakeUserTurnProcessor:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeUserTurnStrategies:
    pass


class _FakeUserTurnCompletionConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _fake_pipecat_runtime() -> pipecat_adapter.PipecatRuntime:
    return pipecat_adapter.PipecatRuntime(
        Pipeline=object,
        PipelineParams=object,
        PipelineWorker=object,
        WorkerParams=object,
        WorkerRunner=object,
        InputAudioRawFrame=object,
        EndFrame=object,
        TextFrame=object,
        TranscriptionFrame=object,
        LLMContextAssistantTurnFrame=object,
        TTSAudioRawFrame=object,
        FrameProcessor=object,
        FrameDirection=object,
        SileroVADAnalyzer=_FakeVADAnalyzer,
        VADProcessor=_FakeVADProcessor,
        OpenAIRealtimeSTTService=_FakeOpenAIRealtimeSTTService,
        OpenAITTSService=_FakeOpenAITTSService,
        OpenAILLMService=_FakePipecatService,
        OpenRouterLLMService=_FakeOpenRouterLLMService,
        LLMContext=_FakeLLMContext,
        LLMContextAggregatorPair=_FakeLLMContextAggregatorPair,
        LLMUserAggregatorParams=_FakeLLMUserAggregatorParams,
        LLMAssistantAggregatorParams=_FakeLLMAssistantAggregatorParams,
        UserTurnProcessor=_FakeUserTurnProcessor,
        UserTurnStrategies=_FakeUserTurnStrategies,
        ExternalUserTurnStrategies=_FakeUserTurnStrategies,
        FilterIncompleteUserTurnStrategies=_FakeUserTurnStrategies,
        UserTurnCompletionConfig=_FakeUserTurnCompletionConfig,
    )


def _voice_context() -> TrainingVoiceContext:
    return TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-openrouter", room_id=42),
        task_goal="Practice renewal risk discovery.",
        rubric={"clarity": 1},
        recent_turns=({"speaker": "user", "text": "Can we discuss renewal risk?"},),
        metadata={"scenarioId": "renewal-risk"},
    )


def _scope() -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id="user-sales-001",
        team_id="team-revenue",
    )


def test_pipecat_voice_config_allows_openrouter_llm_with_openai_stt_tts_and_local_vad():
    pipecat_adapter.validate_pipecat_voice_config(
        RealtimePipelineConfig(
            provider="pipecat",
            metadata={
                "stt": {"provider": "openai", "turnDetection": "disabled"},
                "tts": {"provider": "openai"},
                "llm": {"provider": "openrouter", "temperature": 0.4},
                "vad": {"provider": "silero", "sampleRate": 16000},
                "turnDetection": {"provider": "pipecat"},
            },
        )
    )


def test_pipecat_voice_processors_build_openrouter_llm_with_openai_stt_tts():
    config = RealtimePipelineConfig(
        provider="pipecat",
        model="fallback-model",
        voice="alloy",
        instructions="Stay in role as the counterpart.",
        metadata={
            "openaiApiKey": "sk-openai-test",
            "stt": {"provider": "openai", "turnDetection": "disabled"},
            "tts": {"provider": "openai"},
            "llm": {
                "provider": "openrouter",
                "apiKey": "sk-openrouter-test",
                "model": "openai/gpt-4o-mini",
                "temperature": 0.4,
            },
            "vad": {"provider": "silero", "sampleRate": 16000},
            "turnDetection": {"provider": "pipecat"},
            "context": {"provider": "pipecat", "realtimeServiceMode": False},
        },
    )

    processors = pipecat_adapter.build_pipecat_voice_processors(
        _fake_pipecat_runtime(),
        config,
        context=_voice_context(),
    )

    assert [type(processor) for processor in processors] == [
        _FakeVADProcessor,
        _FakeOpenAIRealtimeSTTService,
        _FakeLLMUserAggregator,
        _FakeOpenRouterLLMService,
        _FakeOpenAITTSService,
        _FakeLLMAssistantAggregator,
    ]
    assert not any(isinstance(processor, _FakeUserTurnProcessor) for processor in processors)
    assert processors[1].kwargs["api_key"] == "sk-openai-test"
    assert processors[4].kwargs["api_key"] == "sk-openai-test"

    llm = processors[3]
    assert llm.kwargs["api_key"] == "sk-openrouter-test"
    assert llm.kwargs["base_url"] == pipecat_adapter.OPENROUTER_LLM_BASE_URL
    llm_settings = llm.kwargs["settings"].kwargs
    assert llm_settings["model"] == "openai/gpt-4o-mini"
    assert llm_settings["temperature"] == 0.4
    assert "Stay in role as the counterpart." in llm_settings["system_instruction"]
    assert "Practice renewal risk discovery." in llm_settings["system_instruction"]
    assert processors[2].context.messages == [
        {"role": "user", "content": "Can we discuss renewal risk?"}
    ]


def test_pipecat_pipeline_capability_reports_openrouter_llm_readiness(monkeypatch):
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: pipecat_adapter.PipecatCapability(
            available=True,
            core_available=True,
            websocket_available=require_websocket,
            stt_available=True,
            tts_available=True,
            llm_available=True,
            openrouter_llm_available=False,
            vad_available=True,
            turn_detection_available=True,
            optional_missing_modules=(pipecat_adapter.OPENROUTER_LLM_PIPECAT_MODULE,),
        ),
    )

    capability = pipecat_adapter.pipecat_pipeline_capability(
        runtime=_fake_pipecat_runtime(),
        config=RealtimePipelineConfig(
            provider="pipecat",
            model="gpt-realtime",
            voice="alloy",
            input_audio_format="pcm16",
            metadata={
                "openaiApiKey": "sk-openai-test",
                "stt": {"provider": "openai", "turnDetection": "disabled"},
                "tts": {"provider": "openai"},
                "llm": {
                    "provider": "openrouter",
                    "apiKey": "sk-openrouter-test",
                    "model": "openai/gpt-4o-mini",
                },
                "vad": {"provider": "silero", "sampleRate": 16000},
                "turnDetection": {"provider": "pipecat"},
            },
        ),
    )

    assert capability.missing_features == ("llm:openrouter",)
    assert capability.llm == "openrouter"
    assert capability.metadata["requestedFeatures"] == {
        "stt": "openai",
        "tts": "openai",
        "llm": "openrouter",
        "vad": "silero",
        "turnDetection": "pipecat",
    }
    assert capability.metadata["llmService"] == {
        "provider": "openrouter",
        "service": "openrouter",
        "baseUrl": pipecat_adapter.OPENROUTER_LLM_BASE_URL,
        "entrypoint": pipecat_adapter.OPENROUTER_LLM_PIPECAT_MODULE,
    }
    assert capability.ready_for_call is False
    assert capability.errors[0]["feature"] == "llm:openrouter"
    assert capability.errors[0]["modules"] == [pipecat_adapter.OPENROUTER_LLM_PIPECAT_MODULE]


def test_pipecat_pipeline_capability_requires_openrouter_key_separately(monkeypatch):
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: pipecat_adapter.PipecatCapability(
            available=True,
            core_available=True,
            websocket_available=require_websocket,
            stt_available=True,
            tts_available=True,
            llm_available=True,
            openrouter_llm_available=True,
            vad_available=True,
            turn_detection_available=True,
        ),
    )

    capability = pipecat_adapter.pipecat_pipeline_capability(
        runtime=_fake_pipecat_runtime(),
        config=RealtimePipelineConfig(
            provider="pipecat",
            model="gpt-realtime",
            voice="alloy",
            input_audio_format="pcm16",
            metadata={
                "openaiApiKey": "sk-openai-test",
                "stt": {"provider": "openai", "turnDetection": "disabled"},
                "tts": {"provider": "openai"},
                "llm": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                "vad": {"provider": "silero", "sampleRate": 16000},
                "turnDetection": {"provider": "pipecat"},
            },
        ),
    )

    assert capability.ready_for_call is False
    assert [error["code"] for error in capability.errors] == ["MISSING_OPENROUTER_API_KEY"]
    assert capability.errors[0]["feature"] == "llm:openrouter"
    assert capability.errors[0]["missingEnv"] == [
        "REALTIME_OPENROUTER_API_KEY",
        "OPENROUTER_API_KEY",
        "LLM__API_KEY",
    ]


def test_pipecat_pipeline_capability_accepts_openrouter_key_from_settings_base_url(
    monkeypatch,
):
    monkeypatch.setattr(
        pipecat_adapter,
        "get_pipecat_capability",
        lambda require_websocket=False: pipecat_adapter.PipecatCapability(
            available=True,
            core_available=True,
            websocket_available=require_websocket,
            stt_available=True,
            tts_available=True,
            llm_available=True,
            openrouter_llm_available=True,
            vad_available=True,
            turn_detection_available=True,
        ),
    )
    monkeypatch.setattr(
        settings,
        "llm",
        LLMSettings(
            provider="openai",
            api_key="sk-openrouter-settings",
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
        ),
    )

    capability = pipecat_adapter.pipecat_pipeline_capability(
        runtime=_fake_pipecat_runtime(),
        config=RealtimePipelineConfig(
            provider="pipecat",
            model="gpt-realtime",
            voice="alloy",
            input_audio_format="pcm16",
            metadata={
                "openaiApiKey": "sk-openai-test",
                "stt": {"provider": "openai", "turnDetection": "disabled"},
                "tts": {"provider": "openai"},
                "llm": {"provider": "openrouter", "model": "openai/gpt-4o-mini"},
                "vad": {"provider": "silero", "sampleRate": 16000},
                "turnDetection": {"provider": "pipecat"},
            },
        ),
    )

    assert capability.ready_for_call is True
    assert capability.errors == ()
    assert capability.metadata["llmService"] == {
        "provider": "openrouter",
        "service": "openrouter",
        "baseUrl": "https://openrouter.ai/api/v1",
        "entrypoint": pipecat_adapter.OPENROUTER_LLM_PIPECAT_MODULE,
    }


def test_build_realtime_transcript_maps_pipecat_openai_stt_event_to_provider_neutral_dto():
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
        provider="pipecat",
        realtime_session_id="rt-1",
    )

    assert transcript is not None
    assert transcript.text == "We can start with a pilot."
    assert transcript.role == "user"
    assert transcript.binding == binding
    assert transcript.provider == "pipecat"
    assert transcript.runtime == REALTIME_RUNTIME_PIPECAT
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
    assert transcript.runtime == REALTIME_RUNTIME_PIPECAT
    assert transcript.response_id == "response_1"
    metadata = transcript_to_message_metadata(transcript)
    assert metadata["source"] == "realtime_voice"
    assert metadata["trainingMode"] == "voice"
    assert metadata["interactionMode"] == "realtime"
    assert metadata["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert metadata["realtime"]["provider"] == "pipecat"
    assert metadata["realtime"]["role"] == "assistant"
    assert metadata["realtime"]["trainingSessionId"] == "training-2"
    assert metadata["realtime"]["roomId"] == 7


def test_build_realtime_transcript_maps_pipecat_user_id_to_sender_metadata():
    transcript = build_realtime_transcript(
        {
            "type": "transcript.done",
            "runtime": "realtime_voice",
            "text": "I can start with the user problem.",
            "user_id": "participant-7",
            "source": "pipecat",
        },
        binding=RealtimeSessionBinding(training_session_id="training-7", room_id=17),
        provider="pipecat",
        realtime_session_id="rt-7",
    )

    assert transcript is not None
    assert transcript.runtime == REALTIME_RUNTIME_PIPECAT
    assert transcript.metadata["sender_id"] == "participant-7"
    metadata = transcript_to_message_metadata(transcript)
    assert metadata["sender_id"] == "participant-7"
    assert metadata["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT
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


def test_provider_error_event_uses_provider_neutral_taxonomy():
    error = RealtimePipelineProviderError(
        {
            "type": "error",
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Provider rate limit exceeded",
                "status": 429,
            },
            "processor": "OpenAIRealtimeSTTService",
            "metadata": {"requestId": "req-123", "apiKey": "sk-should-not-leak"},
        },
        provider="pipecat",
    )

    payload = error.to_realtime_error()

    assert payload["code"] == "REALTIME_PROVIDER_RATE_LIMIT"
    assert payload["sourceCode"] == "rate_limit_exceeded"
    assert payload["errorCategory"] == "rate_limit"
    assert payload["retryable"] is True
    assert payload["fatal"] is False
    assert payload["provider"] == "pipecat"
    assert payload["phase"] == "provider_event"
    assert payload["eventType"] == "error"
    assert payload["processor"] == "OpenAIRealtimeSTTService"
    assert payload["metadata"] == {"requestId": "req-123", "statusCode": 429}


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
    assert persisted.payload["metadata"]["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT


@pytest.mark.asyncio
async def test_persistence_sink_writes_room_message_publishes_and_records_turn():
    room = ChatRoom(id=12, name="Realtime room", type="battle_prep")
    messages = _MessageRepository()
    recorder = _TrainingSessionRecorder(room_id="12")
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
        access_scope=_scope(),
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
    assert messages.messages[0].metadata["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert room.last_message_at == messages.messages[0].timestamp
    assert published[0][0] == 12
    assert published[0][1].content == "We can define the pilot metric first."
    assert recorder.calls == [("get:training-6", 1), ("training-6", 1)]


@pytest.mark.asyncio
async def test_persistence_sink_rejects_transcript_when_session_room_does_not_match_binding():
    room = ChatRoom(id=12, name="Realtime room", type="battle_prep")
    messages = _MessageRepository()
    recorder = _TrainingSessionRecorder(room_id="99")
    transcript = build_realtime_transcript(
        {
            "type": "transcript.done",
            "text": "This should not be persisted.",
        },
        binding=RealtimeSessionBinding(training_session_id="training-6", room_id=12),
        provider="pipecat",
        realtime_session_id="rt-6",
    )
    assert transcript is not None

    sink = RealtimeTranscriptPersistenceSink(
        uow_factory=lambda **_kwargs: _RealtimePersistenceUoW(room, messages),
        session_service=recorder,
        access_scope=_scope(),
    )

    with pytest.raises(PermissionError):
        await sink.persist(transcript)

    assert messages.messages == []
    assert recorder.calls == [("get:training-6", 1)]
    assert room.last_message_at is None


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
