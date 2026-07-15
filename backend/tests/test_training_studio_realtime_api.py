"""API tests for Training Studio realtime WebSocket."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.training_studio import (
    get_training_realtime_openai_factory,
    get_training_realtime_uow_factory,
    get_training_session_service,
    router,
)
from application.services.stakeholder.sse import room_event_bus
from application.services.training_studio.session_service import TrainingSessionService
from core.config import settings
from domain.stakeholder.entity import ChatRoom, Message


def _session_payload(mode: str = "realtime") -> dict:
    return {
        "mode": mode,
        "task_config": {
            "role": "Sales Associate",
            "level": "Senior",
            "tech_stack": ["discovery", "objection handling"],
            "question_type_ratios": {"behavioral": 30, "craft": 50, "pressure": 20},
            "question_count": 6,
            "framework": "prep",
            "difficulty": "medium",
            "category": "sales",
        },
    }


@dataclass
class _RealtimeRoomState:
    rooms: dict[int, ChatRoom]
    messages: list[Message] = field(default_factory=list)


class _FakeRoomRepository:
    def __init__(self, state: _RealtimeRoomState) -> None:
        self._state = state

    async def get_by_id(self, room_id: int) -> ChatRoom | None:
        return self._state.rooms.get(room_id)

    async def update_last_message_at(self, room_id: int, timestamp) -> None:
        room = self._state.rooms[room_id]
        room.last_message_at = timestamp


class _FakeMessageRepository:
    def __init__(self, state: _RealtimeRoomState) -> None:
        self._state = state

    async def create(self, message: Message) -> Message:
        saved = Message(
            id=len(self._state.messages) + 1,
            room_id=message.room_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            content=message.content,
            timestamp=message.timestamp,
            emotion_score=message.emotion_score,
            emotion_label=message.emotion_label,
            metadata=message.metadata,
        )
        self._state.messages.append(saved)
        return saved


class _FakeUoW:
    def __init__(self, state: _RealtimeRoomState, *, readonly: bool = False) -> None:
        self._state = state
        self._readonly = readonly
        self.chat_room_repository = _FakeRoomRepository(state)
        self.stakeholder_message_repository = _FakeMessageRepository(state)

    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeOpenAIRealtimeClient:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False
        self.audio_chunks: list[bytes] = []
        self.commits = 0
        self._events: asyncio.Queue[dict | None] = asyncio.Queue()

    async def connect(self) -> None:
        self.connected = True

    async def append_audio(self, audio: bytes) -> None:
        self.audio_chunks.append(audio)

    async def commit_audio(self) -> None:
        self.commits += 1
        await self._events.put(
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "event_id": "evt_test",
                "item_id": "item_test",
                "transcript": "OpenAI realtime transcript.",
            }
        )

    async def receive_event(self) -> dict | None:
        return await self._events.get()

    async def close(self) -> None:
        self.closed = True


@dataclass
class _CapturedSDPRequest:
    url: str
    data: dict | None
    files: dict | None
    headers: dict[str, str]


class _FakeSDPAsyncClient:
    captured_requests: list[_CapturedSDPRequest] = []

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self) -> "_FakeSDPAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, data=None, files=None, headers=None, **_kwargs) -> httpx.Response:
        self.captured_requests.append(
            _CapturedSDPRequest(
                url=url,
                data=data,
                files=files,
                headers=dict(headers or {}),
            )
        )
        return httpx.Response(
            200,
            text="v=0\r\ns=OpenAI realtime answer\r\n",
            headers={"content-type": "application/sdp"},
            request=httpx.Request("POST", url),
        )


def _response_error_message(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    return str(body.get("message") or body.get("detail") or body)


def _make_bound_app(*, active: bool = True) -> tuple[FastAPI, _RealtimeRoomState]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    session = asyncio.run(session_service.create_session(_session_payload()))
    if active:
        asyncio.run(session_service.start_session(session.session_id, room_id="42"))
    state = _RealtimeRoomState(
        rooms={
            42: ChatRoom(
                id=42,
                name="Training Room",
                type="battle_prep",
                persona_ids=["customer-1"],
            )
        }
    )

    def _uow_factory(**kwargs) -> _FakeUoW:
        return _FakeUoW(state, **kwargs)

    app.dependency_overrides[get_training_session_service] = lambda: session_service
    app.dependency_overrides[get_training_realtime_uow_factory] = lambda: _uow_factory
    return app, state


def test_realtime_sdp_proxy_returns_sdp_answer_when_openai_call_succeeds(monkeypatch) -> None:
    app, _ = _make_bound_app()
    client = TestClient(app)
    offer_sdp = "v=0\r\ns=Local browser offer\r\n"
    _FakeSDPAsyncClient.captured_requests.clear()
    monkeypatch.setattr(settings.llm, "api_key", "test-openai-key")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeSDPAsyncClient)

    response = client.post(
        "/api/v1/training-studio/realtime/sdp",
        content=offer_sdp,
        headers={"content-type": "application/sdp"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/sdp")
    assert response.text == "v=0\r\ns=OpenAI realtime answer\r\n"
    assert _FakeSDPAsyncClient.captured_requests
    captured = _FakeSDPAsyncClient.captured_requests[0]
    assert captured.files["sdp"] == ("offer.sdp", offer_sdp.strip(), "application/sdp")
    assert captured.data and "session" in captured.data
    assert '"type": "realtime"' in captured.data["session"]
    assert "Bearer test-openai-key" in captured.headers.values()


def test_realtime_sdp_proxy_missing_api_key_returns_clear_error(monkeypatch) -> None:
    app, _ = _make_bound_app()
    client = TestClient(app)
    monkeypatch.setattr(settings.llm, "api_key", None)

    response = client.post(
        "/api/v1/training-studio/realtime/sdp",
        content="v=0\r\ns=Local browser offer\r\n",
        headers={"content-type": "application/sdp"},
    )

    assert response.status_code == 503
    assert "OpenAI Realtime is not configured" in _response_error_message(response)


def test_realtime_transcript_persistence_endpoint_stores_voice_realtime_messages() -> None:
    app, state = _make_bound_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/training-studio/realtime/transcripts",
        json={
            "session_id": "session-1",
            "room_id": 42,
            "messages": [
                {
                    "role": "user",
                    "content": "Can we start with a low-risk pilot?",
                    "event_id": "evt_user_1",
                },
                {
                    "role": "assistant",
                    "content": "That could work if the success metric is clear.",
                    "event_id": "evt_assistant_1",
                },
            ],
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert [item["content"] for item in data["messages"]] == [
        "Can we start with a low-risk pilot?",
        "That could work if the success metric is clear.",
    ]

    assert [message.content for message in state.messages] == [
        "Can we start with a low-risk pilot?",
        "That could work if the success metric is clear.",
    ]
    assert state.messages[0].sender_type == "user"
    assert state.messages[0].sender_id == "user"
    assert state.messages[1].sender_type == "persona"
    assert state.messages[1].sender_id == "assistant"
    for message in state.messages:
        assert message.metadata["source"] == "realtime_voice"
        assert message.metadata["trainingMode"] == "voice"
        assert message.metadata["interactionMode"] == "realtime"
        assert message.metadata["realtime"]["trainingSessionId"] == "session-1"
        assert message.metadata["realtime"]["roomId"] == 42


def test_realtime_websocket_accepts_audio_lifecycle() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    with client.websocket_connect("/api/v1/training-studio/realtime") as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["type"] == "session.started"
        assert listening["status"] == "listening"

        ws.send_json({"type": "audio.input", "audio": "", "mimeType": "audio/webm"})
        audio_event = ws.receive_json()
        assert audio_event["type"] == "audio.input"

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        transcript_delta = ws.receive_json()
        transcript_done = ws.receive_json()
        audio_output = ws.receive_json()
        back_to_listening = ws.receive_json()
        assert committed["status"] == "processing"
        assert transcript_delta["type"] == "transcript.delta"
        assert transcript_done["type"] == "transcript.done"
        assert audio_output["type"] == "audio.output"
        assert back_to_listening["status"] == "listening"

        ws.send_json({"type": "session.close", "reason": "test"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"


def test_realtime_websocket_query_binding_persists_final_transcript() -> None:
    app, state = _make_bound_app()
    client = TestClient(app)
    queue = room_event_bus.subscribe(42)
    try:
        with client.websocket_connect(
            "/api/v1/training-studio/realtime?session_id=session-1&room_id=42"
        ) as ws:
            started = ws.receive_json()
            listening = ws.receive_json()
            assert started["payload"]["trainingSessionId"] == "session-1"
            assert started["payload"]["roomId"] == 42
            assert listening["status"] == "listening"

            ws.send_json(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": " We can start with a low-risk pilot. ",
                }
            )
            persisted = ws.receive_json()
            assert persisted["type"] == "transcript.persisted"
            assert persisted["payload"]["message"]["content"] == "We can start with a low-risk pilot."

            assert len(state.messages) == 1
            assert state.messages[0].sender_type == "user"
            assert state.messages[0].sender_id == "user"
            assert state.messages[0].metadata["source"] == "realtime_voice"
            assert state.messages[0].metadata["trainingMode"] == "voice"
            assert state.messages[0].metadata["interactionMode"] == "realtime"
            assert state.messages[0].metadata["realtime"]["trainingSessionId"] == "session-1"

            event, data = queue.get_nowait()
            assert event == "message"
            assert data["content"] == "We can start with a low-risk pilot."
            assert data["metadata"]["source"] == "realtime_voice"
            assert data["metadata"]["trainingMode"] == "voice"
            assert data["metadata"]["interactionMode"] == "realtime"
    finally:
        room_event_bus.unsubscribe(42, queue)


def test_realtime_websocket_configure_binding_persists_final_transcript() -> None:
    app, state = _make_bound_app()
    client = TestClient(app)

    with client.websocket_connect("/api/v1/training-studio/realtime") as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "session.configure", "sessionId": "session-1", "roomId": 42})
        configured = ws.receive_json()
        assert configured["type"] == "session.configured"
        assert configured["payload"] == {
            "bound": True,
            "trainingSessionId": "session-1",
            "roomId": 42,
        }

        ws.send_json({"type": "transcript.done", "text": "Configured binding path."})
        persisted = ws.receive_json()
        assert persisted["type"] == "transcript.persisted"
        assert persisted["payload"]["message"]["content"] == "Configured binding path."

    assert [message.content for message in state.messages] == ["Configured binding path."]
    assert state.messages[0].metadata["realtime"]["eventType"] == "transcript.done"


def test_realtime_websocket_binding_requires_active_training_session() -> None:
    app, _ = _make_bound_app(active=False)
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42"
    ) as ws:
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "active" in error["payload"]["message"]


def test_openai_realtime_provider_relays_audio_and_persists_metadata() -> None:
    app, state = _make_bound_app()
    fake_openai = _FakeOpenAIRealtimeClient()
    app.dependency_overrides[get_training_realtime_openai_factory] = lambda: lambda: fake_openai
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=openai"
    ) as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["provider"] == "openai"
        assert listening["status"] == "listening"

        ws.send_bytes(b"\x01\x02\x03")
        audio_event = ws.receive_json()
        assert audio_event["type"] == "audio.input"

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        transcript_done = ws.receive_json()
        persisted = ws.receive_json()

        assert committed["status"] == "processing"
        assert transcript_done["type"] == "transcript.done"
        assert persisted["type"] == "transcript.persisted"
        assert persisted["payload"]["message"]["content"] == "OpenAI realtime transcript."

    assert fake_openai.connected is True
    assert fake_openai.audio_chunks == [b"\x01\x02\x03"]
    assert fake_openai.commits == 1
    assert fake_openai.closed is True
    assert state.messages[0].metadata["trainingMode"] == "voice"
    assert state.messages[0].metadata["interactionMode"] == "realtime"
    assert state.messages[0].metadata["realtime"]["provider"] == "openai"
    assert state.messages[0].metadata["realtime"]["eventId"] == "evt_test"
    assert state.messages[0].metadata["realtime"]["itemId"] == "item_test"


def test_realtime_demo_vertical_slice_creates_session_starts_room_and_persists_turn() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    session_service = TrainingSessionService(id_factory=lambda: "session-demo")
    state = _RealtimeRoomState(
        rooms={
            42: ChatRoom(
                id=42,
                name="Training Room",
                type="battle_prep",
                persona_ids=["customer-1"],
            )
        }
    )

    def _uow_factory(**kwargs) -> _FakeUoW:
        return _FakeUoW(state, **kwargs)

    app.dependency_overrides[get_training_session_service] = lambda: session_service
    app.dependency_overrides[get_training_realtime_uow_factory] = lambda: _uow_factory
    client = TestClient(app)
    queue = room_event_bus.subscribe(42)
    try:
        created = client.post("/api/v1/training-studio/sessions", json=_session_payload())
        assert created.status_code == 201
        session_id = created.json()["data"]["session_id"]

        started = client.post(
            f"/api/v1/training-studio/sessions/{session_id}/start",
            json={"room_id": 42},
        )
        assert started.status_code == 200
        assert started.json()["data"]["status"] == "active"

        with client.websocket_connect(
            f"/api/v1/training-studio/realtime?session_id={session_id}&room_id=42"
        ) as ws:
            ws.receive_json()
            ws.receive_json()
            ws.send_json(
                {
                    "type": "conversation.item.input_audio_transcription.completed",
                    "transcript": "The demo voice turn is now persisted.",
                }
            )
            persisted = ws.receive_json()
            assert persisted["type"] == "transcript.persisted"

        assert [message.content for message in state.messages] == [
            "The demo voice turn is now persisted."
        ]
        event, data = queue.get_nowait()
        assert event == "message"
        assert data["content"] == "The demo voice turn is now persisted."
        assert data["metadata"]["source"] == "realtime_voice"
        assert data["metadata"]["trainingMode"] == "voice"
        assert data["metadata"]["interactionMode"] == "realtime"
    finally:
        room_event_bus.unsubscribe(42, queue)
