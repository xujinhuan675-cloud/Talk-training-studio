from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from application.ports.realtime import REALTIME_RUNTIME_PIPECAT
from application.ports.turn_based_voice import TurnBasedVoiceSynthesisConfig
from infrastructure.external.pipecat.realtime_pipeline import PipecatRuntime
from infrastructure.external.pipecat.turn_based_cascade import PipecatTurnBasedCascadePipeline


class _CapturingTTS:
    def __init__(self) -> None:
        self.requests = []

    async def synthesize_stream(self, text, config):
        self.requests.append((text, config))
        yield b"mp3-"
        yield b"audio"


class _NativeFrameProcessor:
    def __init__(self, name=None):
        self.name = name
        self.pushed = []

    async def process_frame(self, frame, direction):
        return None

    async def push_frame(self, frame, direction=None):
        self.pushed.append((frame, direction))


class _NativeFrameDirection:
    DOWNSTREAM = "downstream"


@dataclass
class _NativeTextFrame:
    text: str


@dataclass
class _NativeTTSAudioRawFrame:
    audio: bytes
    sample_rate: int
    num_channels: int
    context_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    id: int = 77
    name: str = "NativeTTSAudioRawFrame"
    pts: int | None = None


class _NativeEndFrame:
    pass


class _NativeOpenAITTSService:
    instances = []

    class Settings:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.instances.append(self)


class _NativePipeline:
    def __init__(self, processors):
        self.processors = processors


class _NativePipelineParams:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _NativePipelineWorker:
    instances = []

    def __init__(self, pipeline, **kwargs):
        self.pipeline = pipeline
        self.kwargs = kwargs
        self.queued_frames = []
        self.flushed = False
        self.ended = False
        self.__class__.instances.append(self)

    async def queue_frame(self, frame):
        self.queued_frames.append(frame)
        if isinstance(frame, _NativeTextFrame):
            for processor in self.pipeline.processors:
                if not hasattr(processor, "process_frame"):
                    continue
                await processor.process_frame(
                    _NativeTTSAudioRawFrame(
                        audio=b"\x01\x00",
                        sample_rate=24000,
                        num_channels=1,
                        context_id="native-context",
                        metadata={"nativeFrame": "first"},
                    ),
                    _NativeFrameDirection.DOWNSTREAM,
                )
                await processor.process_frame(
                    _NativeTTSAudioRawFrame(
                        audio=b"\x02\x00",
                        sample_rate=24000,
                        num_channels=1,
                        context_id="native-context",
                        metadata={"nativeFrame": "second"},
                    ),
                    _NativeFrameDirection.DOWNSTREAM,
                )

    async def flush_pipeline(self):
        self.flushed = True

    async def end(self):
        self.ended = True


class _NativeWorkerRunner:
    def __init__(self):
        self.workers = []

    async def add_workers(self, worker):
        self.workers.append(worker)

    async def run(self):
        return None


def _native_runtime(*, openai_tts: bool = True) -> PipecatRuntime:
    return PipecatRuntime(
        Pipeline=_NativePipeline,
        PipelineParams=_NativePipelineParams,
        PipelineWorker=_NativePipelineWorker,
        WorkerParams=object,
        WorkerRunner=_NativeWorkerRunner,
        InputAudioRawFrame=object,
        EndFrame=_NativeEndFrame,
        TextFrame=_NativeTextFrame,
        TranscriptionFrame=object,
        LLMContextAssistantTurnFrame=object,
        TTSAudioRawFrame=_NativeTTSAudioRawFrame,
        FrameProcessor=_NativeFrameProcessor,
        FrameDirection=_NativeFrameDirection,
        OpenAITTSService=_NativeOpenAITTSService if openai_tts else None,
    )


@pytest.mark.asyncio
async def test_turn_based_cascade_wraps_tts_provider_as_pipecat_audio_output() -> None:
    tts = _CapturingTTS()
    pipeline = PipecatTurnBasedCascadePipeline(
        tts,
        tts_provider="openrouter",
        tts_model="mistralai/voxtral-mini-tts-2603",
    )

    outputs = [
        output
        async for output in pipeline.synthesize_stream(
            "Continue the negotiation in Chinese.",
            TurnBasedVoiceSynthesisConfig(
                persona_id="customer",
                voice_id="zh_voice",
                voice_speed=1.2,
                style_instruction="Use natural Mandarin pronunciation.",
                language="zh-CN",
                audio_sequence=3,
                metadata={
                    "replyId": "reply-7",
                    "sentenceIndex": 3,
                    "api_key": "secret",
                    "unsafe": object(),
                },
            ),
        )
    ]

    assert len(outputs) == 1
    assert outputs[0].data == b"mp3-audio"
    assert outputs[0].provider == "pipecat"
    assert outputs[0].runtime == REALTIME_RUNTIME_PIPECAT
    assert outputs[0].mime_type == "audio/mpeg"
    assert outputs[0].sequence == 3
    assert outputs[0].context_id == "reply-7:3"
    assert outputs[0].metadata["pipeline"] == {
        "profile": "cascade",
        "mode": "turn_based",
        "transport": "talkwise.audio_chunks",
    }
    assert outputs[0].metadata["tts"] == {
        "provider": "openrouter",
        "model": "mistralai/voxtral-mini-tts-2603",
        "voice": "zh_voice",
        "language": "zh-CN",
    }
    assert outputs[0].metadata["replyId"] == "reply-7"
    assert outputs[0].metadata["sentenceIndex"] == 3
    assert "api_key" not in outputs[0].metadata
    assert "unsafe" not in outputs[0].metadata

    assert len(tts.requests) == 1
    text, config = tts.requests[0]
    assert text == "Continue the negotiation in Chinese."
    assert config.voice_id == "zh_voice"
    assert config.speed == 1.2
    assert config.style_instruction == "Use natural Mandarin pronunciation."
    assert config.language == "zh-CN"


@pytest.mark.asyncio
async def test_turn_based_cascade_uses_native_pipecat_openai_tts_runtime() -> None:
    _NativeOpenAITTSService.instances = []
    _NativePipelineWorker.instances = []
    pipeline = PipecatTurnBasedCascadePipeline(
        tts=None,
        tts_provider="openai",
        tts_model="gpt-4o-mini-tts",
        tts_api_key="sk-test",
        tts_base_url="https://api.openai.test/v1",
        native_runtime=_native_runtime(),
        native_idle_timeout_seconds=0.01,
    )

    outputs = [
        output
        async for output in pipeline.synthesize_stream(
            "Native TTS please.",
            TurnBasedVoiceSynthesisConfig(
                persona_id="coach",
                voice_id="alloy",
                voice_speed=1.15,
                style_instruction="Speak clearly.",
                audio_sequence=2,
                metadata={"replyId": "reply-native", "apiKey": "should-not-leak"},
            ),
        )
    ]

    assert len(outputs) == 1
    assert outputs[0].data.startswith(b"RIFF")
    assert outputs[0].mime_type == "audio/wav"
    assert outputs[0].runtime == REALTIME_RUNTIME_PIPECAT
    assert outputs[0].sample_rate == 24000
    assert outputs[0].channels == 1
    assert outputs[0].sequence == 2
    assert outputs[0].context_id == "reply-native:2"
    assert outputs[0].metadata["pipeline"] == {
        "profile": "cascade",
        "mode": "turn_based",
        "transport": "talkwise.audio_chunks",
        "runtime": "pipecat_native_frame_processor",
    }
    assert outputs[0].metadata["tts"] == {
        "provider": "openai",
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "language": None,
    }
    assert outputs[0].metadata["nativeFrame"] == "second"
    assert "apiKey" not in outputs[0].metadata

    assert len(_NativeOpenAITTSService.instances) == 1
    tts_service = _NativeOpenAITTSService.instances[0]
    assert tts_service.kwargs["api_key"] == "sk-test"
    assert tts_service.kwargs["base_url"] == "https://api.openai.test/v1"
    assert tts_service.kwargs["sample_rate"] == 24000
    assert tts_service.kwargs["settings"].kwargs == {
        "model": "gpt-4o-mini-tts",
        "voice": "alloy",
        "instructions": "Speak clearly.",
        "speed": 1.15,
    }
    worker = _NativePipelineWorker.instances[0]
    assert isinstance(worker.queued_frames[0], _NativeTextFrame)
    assert worker.queued_frames[0].text == "Native TTS please."
    assert worker.flushed is True
    assert worker.ended is True


@pytest.mark.asyncio
async def test_turn_based_cascade_falls_back_when_native_tts_is_unavailable() -> None:
    tts = _CapturingTTS()
    pipeline = PipecatTurnBasedCascadePipeline(
        tts,
        tts_provider="openai",
        tts_model="gpt-4o-mini-tts",
        tts_api_key="sk-test",
        native_runtime=_native_runtime(openai_tts=False),
        native_idle_timeout_seconds=0.01,
    )

    outputs = [
        output
        async for output in pipeline.synthesize_stream(
            "Fallback please.",
            TurnBasedVoiceSynthesisConfig(
                persona_id="coach",
                voice_id="alloy",
                audio_sequence=4,
                metadata={"replyId": "reply-fallback"},
            ),
        )
    ]

    assert len(outputs) == 1
    assert outputs[0].data == b"mp3-audio"
    assert outputs[0].mime_type == "audio/mpeg"
    assert outputs[0].context_id == "reply-fallback:4"
    assert tts.requests[0][0] == "Fallback please."
