import asyncio
import base64
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from application.ports.realtime import (
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)
from infrastructure.external.pipecat.volcengine_realtime_service import (
    create_volcengine_realtime_service,
)


class _FrameProcessor:
    def __init__(self, name=None):
        self.name = name
        self.pushed = []
        self.broadcasts = []
        self.interruptions = 0
        self.errors = []

    async def process_frame(self, _frame, _direction):
        return None

    async def push_frame(self, frame, direction=None):
        self.pushed.append((frame, direction))

    async def broadcast_frame(self, frame_type, **kwargs):
        self.broadcasts.append(frame_type(**kwargs))

    async def broadcast_interruption(self):
        self.interruptions += 1

    async def push_error(self, message, exception=None, fatal=False):
        self.errors.append((message, exception, fatal))

    async def cleanup(self):
        return None


class _StartFrame:
    pass


class _EndFrame:
    pass


class _CancelFrame:
    pass


class _InterruptionFrame:
    pass


@dataclass
class _ErrorFrame:
    error: str
    fatal: bool = False
    processor: object | None = None
    exception: Exception | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class _InputAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int


@dataclass
class _TextFrame:
    text: str
    user_id: str
    timestamp: str
    finalized: bool = False


class _InterimTextFrame(_TextFrame):
    pass


@dataclass
class _AssistantTurnFrame:
    text: str
    timestamp: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class _TTSAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int
    context_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class _UserStartedSpeakingFrame:
    pass


class _UserStoppedSpeakingFrame:
    pass


class _BotStartedSpeakingFrame:
    pass


class _BotStoppedSpeakingFrame:
    pass


class _FakeAdapter:
    def __init__(self):
        self.started = None
        self.audio_chunks = []
        self.commits = 0
        self.cancel_reasons = []
        self.closed_reasons = []
        self.incoming = asyncio.Queue()

    async def start(self, context, config):
        self.started = (context, config)

    async def append_audio(self, chunk):
        self.audio_chunks.append(chunk)

    async def commit_audio(self):
        self.commits += 1

    async def cancel_response(self, reason=None):
        self.cancel_reasons.append(reason)

    async def events(self):
        while True:
            event = await self.incoming.get()
            if event is None:
                return
            yield event

    async def close(self, reason=None):
        self.closed_reasons.append(reason)


def _runtime():
    return SimpleNamespace(
        FrameProcessor=_FrameProcessor,
        StartFrame=_StartFrame,
        EndFrame=_EndFrame,
        CancelFrame=_CancelFrame,
        InterruptionFrame=_InterruptionFrame,
        ErrorFrame=_ErrorFrame,
        InputAudioRawFrame=_InputAudioRawFrame,
        InterimTranscriptionFrame=_InterimTextFrame,
        TranscriptionFrame=_TextFrame,
        LLMContextAssistantTurnFrame=_AssistantTurnFrame,
        TTSAudioRawFrame=_TTSAudioRawFrame,
        UserStartedSpeakingFrame=_UserStartedSpeakingFrame,
        UserStoppedSpeakingFrame=_UserStoppedSpeakingFrame,
        BotStartedSpeakingFrame=_BotStartedSpeakingFrame,
        BotStoppedSpeakingFrame=_BotStoppedSpeakingFrame,
    )


def _context():
    return TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-1", room_id=7)
    )


def _config():
    return RealtimePipelineConfig(
        provider="volcengine.doubao_realtime",
        runtime="pipecat",
        input_audio_format="pcm16",
        output_audio_format="pcm16",
    )


@pytest.mark.asyncio
async def test_service_uses_pipecat_lifecycle_for_provider_audio_and_commit():
    adapter = _FakeAdapter()
    service = create_volcengine_realtime_service(
        _runtime(),
        context=_context(),
        config=_config(),
        adapter_factory=lambda: adapter,
    )

    await service.process_frame(_StartFrame(), "downstream")
    await service.wait_until_ready()
    await service.process_frame(_InputAudioRawFrame(b"pcm", 16000, 1), "downstream")
    await service.commit_audio()
    await service.process_frame(_InterruptionFrame(), "downstream")

    assert adapter.started is not None
    assert adapter.audio_chunks[0].data == b"pcm"
    assert adapter.audio_chunks[0].metadata == {"sampleRate": 16000, "channels": 1}
    assert adapter.commits == 1
    assert adapter.cancel_reasons == ["pipecat_interruption"]

    await service.cleanup()
    assert adapter.closed_reasons == ["pipeline_cleanup"]


@pytest.mark.asyncio
async def test_service_maps_provider_barge_in_to_one_pipecat_interruption_and_drops_tail():
    adapter = _FakeAdapter()
    runtime = _runtime()
    service = create_volcengine_realtime_service(
        runtime,
        context=_context(),
        config=_config(),
        adapter_factory=lambda: adapter,
    )
    pcm = base64.b64encode(b"assistant-pcm").decode("ascii")

    await service._handle_provider_event(
        {"type": "audio.output", "audio": pcm, "sampleRate": 24000, "channels": 1}
    )
    await service._handle_provider_event({"type": "user.turn.started"})
    await service._handle_provider_event({"type": "interrupted"})
    pushed_before_tail = len(service.pushed)
    await service._handle_provider_event({"type": "audio.output", "audio": pcm})

    assert isinstance(service.pushed[0][0], _BotStartedSpeakingFrame)
    assert isinstance(service.pushed[1][0], _TTSAudioRawFrame)
    assert isinstance(service.broadcasts[0], _UserStartedSpeakingFrame)
    assert service.interruptions == 1
    assert len(service.pushed) == pushed_before_tail

    await service._handle_provider_event({"type": "interruption.ended"})
    await service._handle_provider_event({"type": "audio.output", "audio": pcm})
    assert any(isinstance(frame, _BotStoppedSpeakingFrame) for frame, _ in service.pushed)
    assert len(service.pushed) == pushed_before_tail + 1

    await service._handle_provider_event({"type": "transcript.done", "text": "new user turn"})
    await service._handle_provider_event({"type": "audio.output", "audio": pcm})
    assert isinstance(service.pushed[-2][0], _BotStartedSpeakingFrame)
    assert isinstance(service.pushed[-1][0], _TTSAudioRawFrame)

    await service._handle_provider_event(
        {"type": "response.audio_transcript.done", "text": "new response"}
    )
    assert isinstance(service.pushed[-1][0], _AssistantTurnFrame)

    await service._handle_provider_event(
        {"type": "error", "error": {"message": "provider disconnected"}, "fatal": True}
    )
    error_frame = service.pushed[-1][0]
    assert isinstance(error_frame, _ErrorFrame)
    assert error_frame.error == "provider disconnected"
    assert error_frame.fatal is True


@pytest.mark.asyncio
async def test_service_rejects_container_audio_instead_of_pushing_pcm_frame():
    adapter = _FakeAdapter()
    service = create_volcengine_realtime_service(
        _runtime(),
        context=_context(),
        config=_config(),
        adapter_factory=lambda: adapter,
    )
    ogg = base64.b64encode(b"OggS\x00\x02" + b"\x00" * 22 + b"OpusHead").decode("ascii")

    await service._handle_provider_event(
        {"type": "audio.output", "audio": ogg, "mimeType": "audio/pcm"}
    )

    assert len(service.pushed) == 1
    error_frame = service.pushed[0][0]
    assert isinstance(error_frame, _ErrorFrame)
    assert error_frame.fatal is True
    assert "non-PCM audio" in error_frame.error


@pytest.mark.asyncio
async def test_service_preserves_provider_response_identity_on_pipecat_frames():
    adapter = _FakeAdapter()
    service = create_volcengine_realtime_service(
        _runtime(),
        context=_context(),
        config=_config(),
        adapter_factory=lambda: adapter,
    )
    pcm = base64.b64encode(b"assistant-pcm").decode("ascii")
    identity = {
        "responseId": "reply-2",
        "providerResponseId": "reply-2",
        "providerQuestionId": "question-2",
    }

    await service._handle_provider_event({"type": "audio.output", "audio": pcm, **identity})
    await service._handle_provider_event(
        {
            "type": "response.audio_transcript.done",
            "text": "new response",
            **identity,
        }
    )
    await service._handle_provider_event(
        {
            "type": "error",
            "payload": {
                "message": "Realtime response identity became ambiguous",
                "code": "REALTIME_TURN_DESYNC",
                "sourceCode": "REALTIME_TURN_DESYNC",
                "errorCategory": "protocol_desync",
                "retryable": False,
                "fatal": True,
            },
        }
    )

    audio_frame = next(frame for frame, _ in service.pushed if isinstance(frame, _TTSAudioRawFrame))
    transcript_frame = next(
        frame for frame, _ in service.pushed if isinstance(frame, _AssistantTurnFrame)
    )
    error_frame = next(frame for frame, _ in service.pushed if isinstance(frame, _ErrorFrame))
    assert audio_frame.context_id == "reply-2"
    assert audio_frame.metadata == identity
    assert transcript_frame.metadata == identity
    assert error_frame.metadata["providerError"] == {
        "code": "REALTIME_TURN_DESYNC",
        "sourceCode": "REALTIME_TURN_DESYNC",
        "errorCategory": "protocol_desync",
        "retryable": False,
        "fatal": True,
    }
