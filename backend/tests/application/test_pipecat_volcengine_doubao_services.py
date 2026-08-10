from __future__ import annotations

import asyncio
import io
import wave

import httpx
import pytest
from pipecat.clocks.system_clock import SystemClock
from pipecat.frames.frames import (
    CancelFrame,
    ErrorFrame,
    InputAudioRawFrame,
    InterimTranscriptionFrame,
    InterruptionFrame,
    StartFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.utils.asyncio.task_manager import TaskManager

from infrastructure.external.pipecat.volcengine_doubao_services import (
    DoubaoVoiceServiceError,
    VolcengineDoubaoSTTService,
    VolcengineDoubaoTTSService,
    classify_doubao_voice_error,
    validate_doubao_service_config,
)


class FakeHTTPClient:
    def __init__(self, responses: list["FakeStreamingResponse"] | None = None) -> None:
        self.responses = list(responses or [])
        self.closed = False
        self.requests: list[dict[str, object]] = []

    def stream(self, method: str, url: str, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.responses.pop(0)

    async def aclose(self) -> None:
        self.closed = True


class FakeStreamingResponse:
    def __init__(
        self,
        chunks: list[bytes],
        status_code: int = 200,
        payload: object | None = None,
    ) -> None:
        self.chunks = chunks
        self.status_code = status_code
        self.payload = payload
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.closed = True

    async def aiter_bytes(self, chunk_size: int):
        for chunk in self.chunks:
            await asyncio.sleep(0)
            yield chunk

    async def aread(self) -> bytes:
        return b""

    def json(self) -> object:
        if self.payload is None:
            raise ValueError("response is not JSON")
        return self.payload


def processor_setup() -> FrameProcessorSetup:
    return FrameProcessorSetup(
        clock=SystemClock(),
        task_manager=TaskManager(),
        pipeline_worker=object(),
    )


@pytest.mark.asyncio
async def test_doubao_stt_waits_for_vad_stop_before_transcribing() -> None:
    calls: list[bytes] = []

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        calls.append(audio)
        assert audio.startswith(b"RIFF")
        assert model == "volc.bigasr.sauc.duration"
        assert language == "zh"
        return "complete utterance"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    assert calls == []
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.commit_audio()

    final = [frame for frame in pushed if isinstance(frame, TranscriptionFrame)]
    assert [frame.text for frame in final] == ["complete utterance"]
    assert final[0].finalized is True
    assert len(calls) == 1

    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_previews_and_coalesces_vad_segments_within_speech_timeout() -> None:
    calls: list[bytes] = []

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        calls.append(audio)
        return "晚上睡不着。" if len(calls) == 1 else "晚上睡不着，早上起不来。"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        vad_segment_settle_seconds=60.0,
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))

    first_segment = b"\x01\x00" * 4800
    second_segment = b"\x02\x00" * 4800
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(first_segment, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(calls) == 1
    assert [
        frame.text for frame in pushed if isinstance(frame, InterimTranscriptionFrame)
    ] == ["晚上睡不着。"]

    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(second_segment, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    await asyncio.wait_for(service.commit_audio(), timeout=0.2)

    assert len(calls) == 2
    with wave.open(io.BytesIO(calls[1]), "rb") as audio:
        assert audio.readframes(audio.getnframes()) == first_segment + second_segment
    assert [frame.text for frame in pushed if isinstance(frame, TranscriptionFrame)] == [
        "晚上睡不着，早上起不来。"
    ]
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_settle_window_finalizes_without_manual_commit() -> None:
    transcription_started = asyncio.Event()

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        transcription_started.set()
        return "settled turn"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        vad_segment_settle_seconds=0.01,
        transcribe_request=transcribe,
    )
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    await asyncio.wait_for(transcription_started.wait(), timeout=0.2)
    await service.commit_audio()
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_commit_preserves_preview_request_after_settle_expires() -> None:
    transcription_started = asyncio.Event()
    release_transcription = asyncio.Event()
    calls = 0

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        nonlocal calls
        calls += 1
        transcription_started.set()
        await release_transcription.wait()
        return "晚上睡不着，早上起不来。"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        vad_segment_settle_seconds=0.01,
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    await asyncio.wait_for(transcription_started.wait(), timeout=0.2)
    commit_task = asyncio.create_task(service.commit_audio())
    await asyncio.sleep(0)
    assert commit_task.done() is False

    release_transcription.set()
    await asyncio.wait_for(commit_task, timeout=0.2)

    assert calls == 1
    assert [frame.text for frame in pushed if isinstance(frame, TranscriptionFrame)] == [
        "晚上睡不着，早上起不来。"
    ]
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_manual_commit_finalizes_audio_without_vad_stop() -> None:
    calls: list[bytes] = []

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        calls.append(audio)
        assert audio.startswith(b"RIFF")
        return "manual commit transcript"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 8000, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )

    assert calls == []
    await service.commit_audio()
    await service.commit_audio()

    final = [frame for frame in pushed if isinstance(frame, TranscriptionFrame)]
    assert [frame.text for frame in final] == ["manual commit transcript"]
    assert len(calls) == 1
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_commit_ignores_trailing_silence_after_vad_turn() -> None:
    calls: list[bytes] = []

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        calls.append(audio)
        return "completed turn"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.commit_audio()
    assert len(calls) == 1

    await service.process_frame(
        InputAudioRawFrame(b"\x00\x00" * 8000, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.commit_audio()
    await service.commit_audio()

    assert len(calls) == 1
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_commit_reports_pure_silence_as_input_audio_error() -> None:
    async def transcribe(audio: bytes, model: str, language: str) -> str:
        assert audio.startswith(b"RIFF")
        return ""

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(
        InputAudioRawFrame(b"\x00\x00" * 8000, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )

    await service.commit_audio()

    errors = [frame for frame in pushed if isinstance(frame, ErrorFrame)]
    assert len(errors) == 1
    assert errors[0].metadata["providerError"]["code"] == "DOUBAO_VOICE_TRANSCRIPT_EMPTY"
    assert errors[0].metadata["providerError"]["errorCategory"] == "input_audio"
    assert errors[0].metadata["providerError"]["retryable"] is True
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_empty_completed_turn_is_a_retryable_input_error() -> None:
    async def transcribe(audio: bytes, model: str, language: str) -> str:
        return ""

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[tuple[object, FrameDirection]] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append((frame, direction))

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.commit_audio()

    errors = [
        (frame, direction)
        for frame, direction in pushed
        if isinstance(frame, ErrorFrame)
    ]
    assert len(errors) == 1
    error, direction = errors[0]
    assert direction is FrameDirection.DOWNSTREAM
    assert error.fatal is False
    assert error.exception is None
    assert error.metadata["providerError"] == {
        "code": "DOUBAO_VOICE_TRANSCRIPT_EMPTY",
        "message": "No clear speech was recognized. Move closer to the microphone and try again.",
        "phase": "provider_response",
        "provider": "volcengine.doubao",
        "feature": "stt:volcengine.doubao",
        "errorCategory": "input_audio",
        "retryable": True,
        "fatal": False,
    }
    assert not any(isinstance(frame, TranscriptionFrame) for frame, _direction in pushed)
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_does_not_block_resumed_vad_frames() -> None:
    transcription_started = asyncio.Event()
    release_transcription = asyncio.Event()

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        transcription_started.set()
        await release_transcription.wait()
        return "first segment"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))
    await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    await service.process_frame(
        InputAudioRawFrame(b"\x01\x00" * 4800, 16000, 1),
        FrameDirection.DOWNSTREAM,
    )

    await asyncio.wait_for(
        service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM),
        timeout=0.2,
    )
    await asyncio.wait_for(transcription_started.wait(), timeout=0.2)
    assert not any(isinstance(frame, TranscriptionFrame) for frame in pushed)

    await asyncio.wait_for(
        service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM),
        timeout=0.2,
    )
    await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    assert sum(isinstance(frame, VADUserStartedSpeakingFrame) for frame in pushed) == 2

    release_transcription.set()
    await service.commit_audio()
    assert [frame.text for frame in pushed if isinstance(frame, TranscriptionFrame)] == [
        "first segment"
    ]
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_stt_publishes_concurrent_segments_in_order_with_one_final() -> None:
    started = [asyncio.Event(), asyncio.Event()]
    releases = [asyncio.Event(), asyncio.Event()]
    calls = 0

    async def transcribe(audio: bytes, model: str, language: str) -> str:
        nonlocal calls
        index = calls
        calls += 1
        started[index].set()
        await releases[index].wait()
        return f"segment {index + 1}"

    service = VolcengineDoubaoSTTService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="volc.bigasr.sauc.duration",
        transcribe_request=transcribe,
    )
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    service.push_frame = capture  # type: ignore[method-assign]
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_in_sample_rate=16000))

    for sample in (b"\x01\x00", b"\x02\x00"):
        await service.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
        await service.process_frame(
            InputAudioRawFrame(sample * 4800, 16000, 1),
            FrameDirection.DOWNSTREAM,
        )
        await service.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM)

    await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started)), timeout=0.2)
    releases[1].set()
    await asyncio.sleep(0)
    assert not any(isinstance(frame, TranscriptionFrame) for frame in pushed)

    releases[0].set()
    await service.commit_audio()
    transcripts = [frame for frame in pushed if isinstance(frame, TranscriptionFrame)]
    assert [frame.text for frame in transcripts] == ["segment 1", "segment 2"]
    assert [frame.finalized for frame in transcripts] == [False, True]
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_tts_streams_pcm_and_stops_current_response_on_interruption() -> None:
    response = FakeStreamingResponse([b"first", b"second"])
    client = FakeHTTPClient([response])
    service = VolcengineDoubaoTTSService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="seed-tts-2.0",
        voice="zh_female_vv_uranus_bigtts",
        http_client=client,
    )

    await service.setup(processor_setup())
    await service.start(StartFrame(audio_out_sample_rate=24000))
    output = service.run_tts("你好", "context-1")
    first = await anext(output)
    assert isinstance(first, TTSAudioRawFrame)
    assert first.audio == b"first"
    assert first.sample_rate == 24000
    assert first.context_id == "context-1"

    await service.process_frame(InterruptionFrame(), FrameDirection.DOWNSTREAM)
    with pytest.raises(StopAsyncIteration):
        await anext(output)
    assert response.closed is True
    assert client.requests[0]["json"] == {
        "model": "seed-tts-2.0",
        "input": "你好",
        "voice": "zh_female_vv_uranus_bigtts",
        "response_format": "pcm",
        "speed": 1.0,
    }

    await service.cleanup()
    assert client.closed is True


@pytest.mark.asyncio
async def test_doubao_tts_cancel_releases_client_and_invalidates_active_stream() -> None:
    response = FakeStreamingResponse([b"first", b"second"])
    client = FakeHTTPClient([response])
    service = VolcengineDoubaoTTSService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="seed-tts-2.0",
        voice="zh_female_vv_uranus_bigtts",
        http_client=client,
    )
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_out_sample_rate=24000))
    output = service.run_tts("你好", "context-1")
    assert isinstance(await anext(output), TTSAudioRawFrame)

    await service.cancel(CancelFrame(reason="session_closed"))
    with pytest.raises(StopAsyncIteration):
        await anext(output)
    assert response.closed is True
    assert client.closed is True
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_tts_auth_failure_is_a_structured_error_frame() -> None:
    service = VolcengineDoubaoTTSService(
        api_key="gateway-token",
        base_url="http://newapi.test/pg",
        model="seed-tts-2.0",
        voice="zh_female_vv_uranus_bigtts",
        http_client=FakeHTTPClient([FakeStreamingResponse([], status_code=401)]),
    )
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_out_sample_rate=24000))

    frames = [frame async for frame in service.run_tts("你好", "context-1")]

    assert len(frames) == 1
    assert isinstance(frames[0], ErrorFrame)
    error = frames[0].exception
    assert isinstance(error, DoubaoVoiceServiceError)
    assert error.to_realtime_error() == {
        "code": "DOUBAO_VOICE_AUTHENTICATION_FAILED",
        "message": "Doubao voice authentication failed",
        "phase": "provider_request",
        "provider": "volcengine.doubao",
        "feature": "tts:volcengine.doubao",
        "errorCategory": "authentication",
        "retryable": False,
        "fatal": True,
        "statusCode": 401,
    }
    assert "gateway-token" not in str(frames[0])
    await service.cleanup()


@pytest.mark.asyncio
async def test_doubao_tts_distinguishes_expired_user_session_from_provider_auth() -> None:
    service = VolcengineDoubaoTTSService(
        api_key="expired-gateway-token",
        base_url="http://newapi.test/pg",
        model="seed-tts-2.0",
        voice="zh_female_vv_uranus_bigtts",
        http_client=FakeHTTPClient(
            [
                FakeStreamingResponse(
                    [],
                    status_code=401,
                    payload={"success": False, "code": "AUTH_TOKEN_EXPIRED"},
                )
            ]
        ),
    )
    await service.setup(processor_setup())
    await service.start(StartFrame(audio_out_sample_rate=24000))

    frames = [frame async for frame in service.run_tts("hello", "context-1")]

    assert len(frames) == 1
    error = frames[0].exception
    assert isinstance(error, DoubaoVoiceServiceError)
    assert error.code == "TALKWISE_SESSION_AUTHENTICATION_FAILED"
    assert error.phase == "gateway_authentication"
    assert error.retryable is True
    assert "expired-gateway-token" not in str(frames[0])
    await service.cleanup()


def test_doubao_readiness_distinguishes_missing_and_invalid_configuration() -> None:
    with pytest.raises(DoubaoVoiceServiceError) as missing:
        validate_doubao_service_config(
            api_key=None,
            base_url="http://newapi.test/pg",
            stt_model="volc.bigasr.sauc.duration",
        )
    assert missing.value.code == "MISSING_DOUBAO_VOICE_CREDENTIAL"
    assert missing.value.category == "configuration"

    with pytest.raises(DoubaoVoiceServiceError) as invalid:
        validate_doubao_service_config(
            api_key="gateway-token",
            base_url="not-a-url",
            tts_model="seed-tts-2.0",
            voice="zh_female_vv_uranus_bigtts",
        )
    assert invalid.value.code == "DOUBAO_VOICE_CONFIG_INVALID"


def test_doubao_error_classification_distinguishes_network_and_provider_status() -> None:
    request = httpx.Request("POST", "http://newapi.test/pg/audio/speech")
    network = classify_doubao_voice_error(
        httpx.ConnectError("credential=secret", request=request),
        feature="tts:volcengine.doubao",
    )
    unavailable = classify_doubao_voice_error(
        status_code=503,
        feature="stt:volcengine.doubao",
    )

    assert network.code == "DOUBAO_VOICE_NETWORK_FAILED"
    assert network.category == "network"
    assert network.retryable is True
    assert "secret" not in str(network)
    assert unavailable.code == "DOUBAO_VOICE_PROVIDER_UNAVAILABLE"
    assert unavailable.category == "provider_unavailable"
    assert unavailable.status_code == 503
