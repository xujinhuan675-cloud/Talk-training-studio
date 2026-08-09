from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from typing import Any

import pytest

from application.ports.realtime import (
    REALTIME_RUNTIME_VOLCENGINE_DOUBAO as PORT_REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    RealtimeSessionBinding,
    TrainingVoiceContext,
)
from infrastructure.external.voice.volcengine_realtime import (
    DEFAULT_VOLCENGINE_REALTIME_VOICE,
    REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
    VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
    VolcengineDoubaoRealtimeAdapter,
    VolcengineRealtimeError,
    classify_volcengine_realtime_error,
    encode_volcengine_realtime_event,
    iter_volcengine_realtime_events,
    map_volcengine_realtime_event,
    normalize_volcengine_realtime_url,
    parse_volcengine_realtime_frame,
)
from infrastructure.external.newapi_user_gateway import (
    bind_user_access_token,
    reset_user_access_token,
)
from core.config import settings


def test_volcengine_realtime_uses_public_runtime_identifier() -> None:
    assert REALTIME_RUNTIME_VOLCENGINE_DOUBAO == PORT_REALTIME_RUNTIME_VOLCENGINE_DOUBAO


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.incoming: asyncio.Queue[object] = asyncio.Queue()
        self.start_confirmations: list[object] = [
            json.dumps({"type": "session.created"}),
            json.dumps({"type": "session.updated"}),
        ]
        self.closed = False

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def recv(self) -> object:
        item = (
            self.start_confirmations.pop(0)
            if self.start_confirmations
            else await self.incoming.get()
        )
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self) -> None:
        self.closed = True


class _FakeWebSocketContext:
    def __init__(self, websocket: _FakeWebSocket) -> None:
        self.websocket = websocket
        self.entered = False
        self.exited = False

    async def __aenter__(self) -> _FakeWebSocket:
        self.entered = True
        return self.websocket

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.exited = True


def _voice_context() -> TrainingVoiceContext:
    return TrainingVoiceContext(
        binding=RealtimeSessionBinding(training_session_id="training-1", room_id=7),
        task_goal="Practice a renewal negotiation",
        rubric={"clarity": 1},
        recent_turns=({"role": "user", "content": "Can we renew?"},),
        metadata={"scenario": "renewal"},
    )


def _realtime_config(**overrides: Any) -> RealtimePipelineConfig:
    values: dict[str, Any] = {
        "provider": VOLCENGINE_DOUBAO_REALTIME_PROVIDER,
        "runtime": REALTIME_RUNTIME_VOLCENGINE_DOUBAO,
        "model": "1.2.1.1",
        "voice": "zh_female_vv_uranus_bigtts",
        "input_audio_format": "pcm16",
        "output_audio_format": "pcm16",
        "instructions": "Stay in role.",
        "metadata": {"inputSampleRate": 16000, "outputSampleRate": 24000},
    }
    values.update(overrides)
    return RealtimePipelineConfig(**values)


def _decode_sent(message: str) -> dict[str, Any]:
    return json.loads(message)


async def _next_event(adapter: VolcengineDoubaoRealtimeAdapter) -> dict[str, Any]:
    if not hasattr(adapter, "_test_events"):
        adapter._test_events = adapter.events()  # type: ignore[attr-defined]
    return await asyncio.wait_for(adapter._test_events.__anext__(), timeout=1)  # type: ignore[attr-defined]


async def _start_adapter(
    *,
    websocket: _FakeWebSocket | None = None,
    context: _FakeWebSocketContext | None = None,
) -> tuple[VolcengineDoubaoRealtimeAdapter, _FakeWebSocket, _FakeWebSocketContext, dict[str, Any]]:
    fake_ws = websocket or _FakeWebSocket()
    fake_context = context or _FakeWebSocketContext(fake_ws)
    captured: dict[str, Any] = {}

    def connector(url: str, *, headers: Mapping[str, str], timeout: float):
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["timeout"] = timeout
        return fake_context

    adapter = VolcengineDoubaoRealtimeAdapter(
        api_key="volc-secret",
        base_url="openspeech.bytedance.com",
        timeout=12.0,
        websocket_connector=connector,
        request_id_factory=lambda: "req-realtime-1",
    )
    await adapter.start(_voice_context(), _realtime_config())
    return adapter, fake_ws, fake_context, captured


@pytest.mark.asyncio
async def test_volcengine_realtime_start_sends_session_create_frame() -> None:
    adapter, websocket, fake_context, captured = await _start_adapter()

    assert normalize_volcengine_realtime_url("gateway.example.com") == (
        "wss://gateway.example.com/pg/realtime"
    )
    assert fake_context.entered is True
    assert captured == {
        "url": "wss://openspeech.bytedance.com/pg/realtime?model=1.2.1.1",
        "headers": {
            "Authorization": "Bearer volc-secret",
            "X-Request-Id": "req-realtime-1",
        },
        "timeout": 12.0,
    }
    assert [_decode_sent(item)["type"] for item in websocket.sent] == ["session.update"]

    start_frame = _decode_sent(websocket.sent[0])
    assert start_frame["session"]["voice"] == DEFAULT_VOLCENGINE_REALTIME_VOICE
    assert start_frame["session"]["input_audio_format"] == "pcm16"
    assert start_frame["session"]["output_audio_format"] == "pcm16"
    assert "Stay in role." in start_frame["session"]["instructions"]
    assert "Practice a renewal negotiation" in start_frame["session"]["instructions"]
    assert "payload" not in start_frame

    ready = await _next_event(adapter)
    configured = await _next_event(adapter)
    assert ready["type"] == "session.ready"
    assert ready["runtime"] == REALTIME_RUNTIME_VOLCENGINE_DOUBAO
    assert configured["type"] == "session.configured"
    assert configured["payload"]["model"] == "1.2.1.1"
    assert configured["payload"]["voice"] == DEFAULT_VOLCENGINE_REALTIME_VOICE

    await adapter.close()


@pytest.mark.asyncio
async def test_volcengine_realtime_start_waits_for_upstream_confirmation() -> None:
    websocket = _FakeWebSocket()
    websocket.start_confirmations = [json.dumps({"type": "session.created"})]
    fake_context = _FakeWebSocketContext(websocket)

    def connector(url: str, *, headers: Mapping[str, str], timeout: float):
        return fake_context

    adapter = VolcengineDoubaoRealtimeAdapter(
        api_key="volc-secret",
        timeout=1,
        websocket_connector=connector,
    )
    start_task = asyncio.create_task(adapter.start(_voice_context(), _realtime_config()))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert start_task.done() is False

    await websocket.incoming.put(json.dumps({"type": "session.updated"}))
    await start_task

    assert (await _next_event(adapter))["type"] == "session.ready"
    assert (await _next_event(adapter))["type"] == "session.configured"
    await adapter.close()


@pytest.mark.asyncio
async def test_volcengine_realtime_start_surfaces_provider_failure() -> None:
    websocket = _FakeWebSocket()
    websocket.start_confirmations = [
        json.dumps({"type": "session.created"}),
        json.dumps(
            {
                "type": "error",
                "status": 400,
                "code": "InvalidParameter",
                "message": "voice is not available",
            }
        ),
    ]
    fake_context = _FakeWebSocketContext(websocket)

    def connector(url: str, *, headers: Mapping[str, str], timeout: float):
        return fake_context

    adapter = VolcengineDoubaoRealtimeAdapter(
        api_key="volc-secret",
        websocket_connector=connector,
    )

    with pytest.raises(VolcengineRealtimeError, match="voice is not available") as exc_info:
        await adapter.start(_voice_context(), _realtime_config())

    assert exc_info.value.phase == "session_start"
    assert exc_info.value.code == "REALTIME_PROVIDER_BAD_REQUEST"
    assert websocket.closed is True


@pytest.mark.asyncio
async def test_volcengine_realtime_start_replaces_placeholder_voice_with_default() -> None:
    fake_ws = _FakeWebSocket()
    fake_context = _FakeWebSocketContext(fake_ws)

    def connector(url: str, *, headers: Mapping[str, str], timeout: float):
        return fake_context

    adapter = VolcengineDoubaoRealtimeAdapter(
        api_key="volc-secret",
        voice="marin",
        websocket_connector=connector,
        request_id_factory=lambda: "req-realtime-1",
    )
    await adapter.start(
        _voice_context(),
        _realtime_config(voice="your-volcengine-voice"),
    )

    start_frame = _decode_sent(fake_ws.sent[0])
    assert start_frame["session"]["voice"] == DEFAULT_VOLCENGINE_REALTIME_VOICE

    await adapter.close()


@pytest.mark.asyncio
async def test_volcengine_realtime_audio_commit_cancel_and_close_send_provider_frames() -> None:
    adapter, websocket, fake_context, _captured = await _start_adapter()
    await _next_event(adapter)
    await _next_event(adapter)

    await adapter.append_audio(
        RealtimeAudioChunk(
            data=b"pcm-audio",
            mime_type="audio/pcm",
            sequence=4,
            metadata={"sampleRate": 16000, "channels": 1},
        )
    )
    await adapter.commit_audio()
    await adapter.cancel_response("barge_in")
    await adapter.close("finished")

    sent = [_decode_sent(item) for item in websocket.sent]
    assert [item["type"] for item in sent] == [
        "session.update",
        "input_audio_buffer.append",
        "input_audio_buffer.commit",
        "response.cancel",
    ]
    assert sent[1]["audio"] == base64.b64encode(b"pcm-audio").decode("ascii")
    assert "payload" not in sent[1]
    assert "sequence" not in sent[2]
    assert "reason" not in sent[3]
    assert websocket.closed is True
    assert fake_context.exited is True

    closed = await _next_event(adapter)
    assert closed["type"] == "session.closed"
    assert closed["payload"]["reason"] == "finished"


@pytest.mark.asyncio
async def test_volcengine_realtime_uses_current_user_newapi_gateway(monkeypatch) -> None:
    fake_ws = _FakeWebSocket()
    fake_context = _FakeWebSocketContext(fake_ws)
    captured: dict[str, Any] = {}

    def connector(url: str, *, headers: Mapping[str, str], timeout: float):
        captured.update(url=url, headers=dict(headers), timeout=timeout)
        return fake_context

    monkeypatch.setattr(settings, "NEWAPI_USER_BILLING_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "NEWAPI_USER_RELAY_REALTIME_URL",
        "wss://gateway.example.com/pg/realtime",
    )
    context_token = bind_user_access_token("dashboard-user-token")
    try:
        adapter = VolcengineDoubaoRealtimeAdapter(
            api_key="must-not-be-used",
            websocket_connector=connector,
            request_id_factory=lambda: "req-gateway-1",
        )
        await adapter.start(_voice_context(), _realtime_config())
        assert captured["url"] == ("wss://gateway.example.com/pg/realtime?model=1.2.1.1")
        assert captured["headers"] == {"Authorization": "Bearer dashboard-user-token"}
        assert "must-not-be-used" not in json.dumps(captured)
        await adapter.close()
    finally:
        reset_user_access_token(context_token)


@pytest.mark.asyncio
async def test_volcengine_realtime_receive_loop_maps_provider_events() -> None:
    websocket = _FakeWebSocket()
    events = [
        {
            "type": "conversation.item.input_audio_transcription.delta",
            "text": "hello",
            "language": "en",
        },
        {"type": "conversation.item.input_audio_transcription.completed", "text": "hello world"},
        {
            "type": "response.output_audio.delta",
            "audio": base64.b64encode(b"assistant-pcm").decode("ascii"),
            "sequence": 2,
        },
        {"type": "input_audio_buffer.speech_started", "participant": "user"},
        {"type": "input_audio_buffer.speech_stopped", "participant": "user"},
        {"type": "response.interrupted", "reason": "barge_in"},
        {"type": "response.cancel.done", "reason": "barge_in"},
        {"type": "response.audio_transcript.done", "text": "assistant reply"},
    ]
    for event in events:
        await websocket.incoming.put(json.dumps(event))

    adapter, _websocket, _fake_context, _captured = await _start_adapter(websocket=websocket)
    observed = [await _next_event(adapter) for _ in range(2 + len(events))]

    assert [event["type"] for event in observed] == [
        "session.ready",
        "session.configured",
        "transcript.delta",
        "transcript.done",
        "audio.output",
        "user_turn.started",
        "user_turn.stopped",
        "interrupted",
        "interruption.ended",
        "response.audio_transcript.done",
    ]
    assert observed[2]["text"] == "hello"
    assert observed[3]["text"] == "hello world"
    assert observed[4]["audio"] == base64.b64encode(b"assistant-pcm").decode("ascii")
    assert observed[4]["sampleRate"] == 24000
    assert observed[5]["payload"]["participant"] == "user"
    assert observed[7]["payload"]["reason"] == "barge_in"
    assert observed[9]["role"] == "assistant"
    assert observed[9]["text"] == "assistant reply"

    await adapter.close()


@pytest.mark.asyncio
async def test_volcengine_realtime_terminal_events_do_not_deadlock_full_bounded_queue() -> None:
    adapter, websocket, _fake_context, _captured = await _start_adapter()
    await _next_event(adapter)
    await _next_event(adapter)

    for sequence in range(adapter._events.maxsize):
        adapter._events.put_nowait({"type": "queued", "sequence": sequence})

    await websocket.incoming.put(ConnectionError("provider disconnected"))
    assert adapter._receive_task is not None
    await asyncio.wait_for(asyncio.shield(adapter._receive_task), timeout=1)

    queued = []
    while not adapter._events.empty():
        queued.append(adapter._events.get_nowait())
    event_types = [item.get("type") for item in queued if isinstance(item, Mapping)]
    assert event_types == ["error", "session.closed"]
    assert len(queued) == 3
    assert not isinstance(queued[-1], Mapping)
    assert adapter._closed is True

    for sequence in range(adapter._events.maxsize):
        adapter._events.put_nowait({"type": "queued", "sequence": sequence})
    await asyncio.wait_for(adapter.close("test_cleanup"), timeout=1)
    assert adapter._events.maxsize == 256


def test_volcengine_realtime_mapping_classifies_and_redacts_provider_errors() -> None:
    config = _realtime_config()
    mapped = map_volcengine_realtime_event(
        {
            "type": "error",
            "status": 401,
            "code": "invalid_api_key",
            "message": "api_key=sk-secret is invalid",
            "metadata": {"Authorization": "Bearer secret", "requestId": "req-1"},
        },
        config=config,
        context=_voice_context(),
    )

    assert len(mapped) == 1
    event = mapped[0]
    assert event["type"] == "error"
    assert event["payload"]["code"] == "REALTIME_PROVIDER_AUTHENTICATION"
    assert event["payload"]["errorCategory"] == "authentication"
    serialized = json.dumps(event)
    assert "sk-secret" not in serialized
    assert "Bearer secret" not in serialized
    assert "Authorization" not in serialized

    classified = classify_volcengine_realtime_error({"status": 429, "message": "rate limit"})
    assert classified["code"] == "REALTIME_PROVIDER_RATE_LIMIT"
    assert classified["retryable"] is True


def test_volcengine_realtime_mapping_preserves_provider_response_identity() -> None:
    config = _realtime_config()
    identity = {
        "response_id": "reply-2",
        "provider_response_id": "reply-2",
        "provider_question_id": "question-2",
    }

    audio_event = map_volcengine_realtime_event(
        {
            "type": "response.audio.delta",
            "audio": base64.b64encode(b"assistant-pcm").decode("ascii"),
            **identity,
        },
        config=config,
    )[0]
    transcript_event = map_volcengine_realtime_event(
        {
            "type": "response.audio_transcript.done",
            "text": "new response",
            **identity,
        },
        config=config,
    )[0]
    desync = classify_volcengine_realtime_error(
        {
            "code": "REALTIME_TURN_DESYNC",
            "message": "Realtime response identity became ambiguous",
        }
    )

    assert audio_event["contextId"] == "reply-2"
    assert audio_event["metadata"]["responseId"] == "reply-2"
    assert audio_event["metadata"]["providerResponseId"] == "reply-2"
    assert audio_event["metadata"]["providerQuestionId"] == "question-2"
    assert transcript_event["response_id"] == "reply-2"
    assert transcript_event["metadata"]["providerResponseId"] == "reply-2"
    assert transcript_event["metadata"]["providerQuestionId"] == "question-2"
    assert desync == {
        "errorCategory": "protocol_desync",
        "code": "REALTIME_TURN_DESYNC",
        "retryable": False,
        "fatal": True,
        "sourceCode": "REALTIME_TURN_DESYNC",
    }


@pytest.mark.parametrize(
    ("audio", "detected_mime_type"),
    [
        (b"OggS\x00\x02" + b"\x00" * 22 + b"OpusHead", "audio/ogg"),
        (b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 16, "audio/wav"),
    ],
)
def test_volcengine_realtime_mapping_rejects_container_audio_for_pcm_contract(
    audio: bytes,
    detected_mime_type: str,
) -> None:
    mapped = map_volcengine_realtime_event(
        {
            "type": "response.audio.delta",
            "audio": base64.b64encode(audio).decode("ascii"),
            "mimeType": "audio/pcm",
        },
        config=_realtime_config(),
        context=_voice_context(),
    )

    assert len(mapped) == 1
    assert mapped[0]["type"] == "error"
    assert mapped[0]["payload"]["code"] == "REALTIME_PROVIDER_BAD_REQUEST"
    assert mapped[0]["payload"]["sourceCode"] == ("VOLCENGINE_REALTIME_AUDIO_FORMAT_UNSUPPORTED")
    assert mapped[0]["payload"]["errorCategory"] == "bad_request"
    assert mapped[0]["payload"]["fatal"] is True
    assert mapped[0]["payload"]["metadata"]["detectedMimeType"] == detected_mime_type


def test_volcengine_realtime_protocol_helpers_parse_batch_and_reject_binary() -> None:
    encoded = encode_volcengine_realtime_event(
        "input_audio_buffer.commit",
        {"sequence": 3, "apiKey": "secret-removed"},
        event_id="event-1",
    )
    parsed = parse_volcengine_realtime_frame(encoded)

    assert parsed == {
        "type": "input_audio_buffer.commit",
        "event_id": "event-1",
        "sequence": 3,
    }
    assert iter_volcengine_realtime_events(
        json.dumps({"events": [{"type": "session.ready"}, {"type": "session.configured"}]})
    ) == ({"type": "session.ready"}, {"type": "session.configured"})

    with pytest.raises(Exception, match="official binary parser is not wired"):
        parse_volcengine_realtime_frame(b"\xff\x00")
