import asyncio
import json

import pytest

from infrastructure.external.pipecat.volcengine_doubao_streaming_stt import (
    DoubaoStreamingSTTGatewayError,
    VolcengineDoubaoStreamingSTTService,
    build_doubao_streaming_stt_audio_event,
    build_doubao_streaming_stt_session_event,
    create_volcengine_doubao_streaming_stt_service,
    normalize_doubao_streaming_stt_url,
)
from pipecat.frames.frames import (
    EndFrame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    VADUserStoppedSpeakingFrame,
)


_CLOSED = object()


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self.messages: asyncio.Queue[object] = asyncio.Queue()

    async def send(self, message: str) -> None:
        if self.closed:
            raise ConnectionError("closed")
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True
        self.messages.put_nowait(_CLOSED)

    async def ping(self) -> None:
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.messages.get()
        if message is _CLOSED:
            raise StopAsyncIteration
        return message


async def _eventually(predicate, *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition was not met")
        await asyncio.sleep(0)


def test_gateway_url_and_provider_neutral_events() -> None:
    assert normalize_doubao_streaming_stt_url(
        "https://newapi.example/pg",
        model="volc.bigasr.sauc.duration",
    ) == (
        "wss://newapi.example/pg/realtime?model=volc.bigasr.sauc.duration"
    )
    assert build_doubao_streaming_stt_session_event(
        model="volc.bigasr.sauc.duration",
        language="zh",
        sample_rate=16000,
    ) == {
        "type": "session.update",
        "session": {
            "modalities": ["text"],
            "input_audio_format": "pcm16",
            "input_audio_transcription": {
                "model": "volc.bigasr.sauc.duration",
                "language": "zh",
            },
            "turn_detection": None,
            "metadata": {"sample_rate": 16000, "channels": 1},
        },
    }
    assert build_doubao_streaming_stt_audio_event(b"\x00\x01") == {
        "type": "input_audio_buffer.append",
        "audio": "AAE=",
    }


def test_service_rejects_raw_provider_credentials() -> None:
    with pytest.raises(DoubaoStreamingSTTGatewayError) as exc_info:
        VolcengineDoubaoStreamingSTTService(
            api_key="newapi-user-token",
            ws_url="ws://newapi.example/pg/realtime",
            app_key="must-not-enter-talkwise",
        )

    assert exc_info.value.code == "DOUBAO_STREAMING_STT_DIRECT_CREDENTIAL_REJECTED"
    assert "must-not-enter-talkwise" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_streaming_service_lifecycle_audio_commit_and_transcript_frames() -> None:
    websocket = FakeWebSocket()
    connection_calls: list[tuple[str, dict[str, str], float]] = []

    async def connect(url: str, *, headers: dict[str, str], timeout: float):
        connection_calls.append((url, headers, timeout))
        return websocket

    fallback_factory = lambda: object()
    service = create_volcengine_doubao_streaming_stt_service(
        api_key="newapi-user-token",
        ws_url="ws://newapi.example/pg/realtime",
        model="volc.bigasr.sauc.duration",
        language="zh",
        sample_rate=16000,
        websocket_connector=connect,
        request_id_factory=lambda: "request-1",
        fallback_factory=fallback_factory,
        app_key=None,
        resource_id=None,
        ttfs_p99_latency=0.75,
    )
    pushed: list[object] = []
    original_push_frame = service.push_frame

    async def capture(frame, direction=None):
        pushed.append(frame)
        await original_push_frame(frame, direction)

    service.push_frame = capture  # type: ignore[method-assign]

    await service.start(StartFrame(audio_in_sample_rate=16000))
    assert service.fallback_factory is fallback_factory
    assert connection_calls == [
        (
            "ws://newapi.example/pg/realtime?model=volc.bigasr.sauc.duration",
            {
                "Authorization": "Bearer newapi-user-token",
                "X-Request-Id": "request-1",
            },
            10.0,
        )
    ]
    assert json.loads(websocket.sent[0])["type"] == "session.update"

    assert [item async for item in service.run_stt(b"\x01\x02")] == [None]
    assert json.loads(websocket.sent[1]) == {
        "type": "input_audio_buffer.append",
        "audio": "AQI=",
    }

    await service._handle_vad_user_stopped_speaking(
        VADUserStoppedSpeakingFrame(stop_secs=0.0, timestamp=0.0)
    )
    assert json.loads(websocket.sent[2]) == {"type": "input_audio_buffer.commit"}

    websocket.messages.put_nowait(
        json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "delta": "\u4f60",
            }
        )
    )
    websocket.messages.put_nowait(
        json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.delta",
                "delta": "\u597d",
            }
        )
    )
    websocket.messages.put_nowait(
        json.dumps(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "\u4f60\u597d",
            }
        )
    )
    await _eventually(
        lambda: any(isinstance(frame, TranscriptionFrame) for frame in pushed)
    )

    interims = [frame for frame in pushed if isinstance(frame, InterimTranscriptionFrame)]
    finals = [frame for frame in pushed if isinstance(frame, TranscriptionFrame)]
    assert [frame.text for frame in interims] == ["\u4f60", "\u4f60\u597d"]
    assert [frame.text for frame in finals] == ["\u4f60\u597d"]
    assert finals[0].finalized is True
    assert service.service_metadata_frame().ttfs_p99_latency == 0.75

    await service.stop(EndFrame())
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_gateway_connect_failure_is_structured_and_does_not_create_fallback() -> None:
    fallback_calls = 0

    def fallback_factory():
        nonlocal fallback_calls
        fallback_calls += 1
        return object()

    async def connect(*args, **kwargs):
        raise OSError("provider credential should not leak")

    service = VolcengineDoubaoStreamingSTTService(
        api_key="newapi-user-token",
        gateway_ws_url="ws://newapi.example/pg/realtime",
        websocket_connector=connect,
        fallback_factory=fallback_factory,
    )

    with pytest.raises(DoubaoStreamingSTTGatewayError) as exc_info:
        await service.start(StartFrame(audio_in_sample_rate=16000))

    assert exc_info.value.code == "DOUBAO_STREAMING_STT_GATEWAY_CONNECT_FAILED"
    assert exc_info.value.retryable is True
    assert exc_info.value.fatal is False
    assert fallback_calls == 0
