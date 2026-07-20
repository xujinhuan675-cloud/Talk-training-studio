from __future__ import annotations

import base64
from types import SimpleNamespace
from threading import Event
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_chatroom_service, get_stakeholder_chat_service
from api.routes.stakeholder import router
from application.ports.stt import TranscriptionResult
from application.services.stakeholder.dto import MessageDTO
from domain.stakeholder.entity import ChatRoom


class _FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh",
        audio_format: str = "webm",
    ) -> TranscriptionResult:
        self.calls.append(
            {"audio": audio, "language": language, "audio_format": audio_format}
        )
        return TranscriptionResult(text=self.text, language=language)


class _FakeStakeholderChatService:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []
        self.reply_jobs: list[tuple[int, ChatRoom]] = []
        self.reply_started = Event()

    async def send_message(self, room_id: int, content: str) -> tuple[MessageDTO, ChatRoom]:
        self.sent_messages.append((room_id, content))
        room = ChatRoom(
            id=room_id,
            name="Voice Battle",
            type="battle_prep",
            persona_ids=["stakeholder"],
        )
        return (
            MessageDTO(
                id=1,
                room_id=room_id,
                sender_type="user",
                sender_id="user",
                content=content,
            ),
            room,
        )

    async def generate_replies(self, room_id: int, room: ChatRoom) -> None:
        self.reply_jobs.append((room_id, room))
        self.reply_started.set()


class _FakeChatRoomService:
    def __init__(self, *, room_type: str = "battle_prep", user_message_count: int = 0) -> None:
        self.room_type = room_type
        self.user_message_count = user_message_count

    async def get_room_detail(
        self,
        room_id: int,
        message_limit: int = 200,
        access_scope=None,
    ) -> SimpleNamespace:
        messages = [
            SimpleNamespace(sender_type="user")
            for _ in range(self.user_message_count)
        ]
        return SimpleNamespace(
            room=SimpleNamespace(id=room_id, type=self.room_type),
            messages=messages,
        )


def _make_client(
    fake_chat: _FakeStakeholderChatService,
    fake_rooms: _FakeChatRoomService | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stakeholder_chat_service] = lambda: fake_chat
    app.dependency_overrides[get_chatroom_service] = lambda: fake_rooms or _FakeChatRoomService()
    return TestClient(app)


def test_voice_websocket_transcription_auto_sends_chat_message(monkeypatch) -> None:
    fake_stt = _FakeSTT("Here is my spoken answer.")
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)

    client = _make_client(fake_chat)

    with client.websocket_connect("/api/v1/stakeholder/rooms/7/voice") as ws:
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(b"voice-bytes").decode("ascii"),
            }
        )
        ws.send_json({"type": "speech_end", "format": "webm"})
        transcription = ws.receive_json()
        message_sent = ws.receive_json()
        ws.close()

    assert transcription == {
        "type": "transcription",
        "text": "Here is my spoken answer.",
        "is_final": True,
    }
    assert fake_stt.calls == [
        {"audio": b"voice-bytes", "language": "zh", "audio_format": "webm"}
    ]
    assert fake_chat.sent_messages == [(7, "Here is my spoken answer.")]
    assert fake_chat.reply_started.wait(timeout=1)
    assert [(room_id, room.id) for room_id, room in fake_chat.reply_jobs] == [(7, 7)]
    assert message_sent["type"] == "message_sent"
    assert message_sent["message"]["sender_type"] == "user"
    assert message_sent["message"]["content"] == "Here is my spoken answer."


def test_voice_websocket_reports_missing_stt_configuration(monkeypatch) -> None:
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: None)
    client = _make_client(fake_chat)

    with client.websocket_connect("/api/v1/stakeholder/rooms/7/voice") as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["code"] == "stt_not_configured"
    assert error["message"] == "STT service not configured"
    assert "VOICE__STT_API_KEY" in error["details"]


def test_voice_websocket_ack_failure_does_not_block_reply_generation(monkeypatch) -> None:
    fake_stt = _FakeSTT("Continue the training turn.")
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module
    from starlette.websockets import WebSocket

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)
    original_send_json = WebSocket.send_json

    async def fail_message_sent_ack(
        self: WebSocket,
        data: Any,
        mode: str = "text",
    ) -> None:
        if isinstance(data, dict) and data.get("type") == "message_sent":
            raise RuntimeError("client closed before ack")
        await original_send_json(self, data, mode=mode)

    monkeypatch.setattr(WebSocket, "send_json", fail_message_sent_ack)
    client = _make_client(fake_chat)

    with client.websocket_connect("/api/v1/stakeholder/rooms/8/voice") as ws:
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(b"voice-bytes").decode("ascii"),
            }
        )
        ws.send_json({"type": "speech_end", "format": "webm"})
        transcription = ws.receive_json()

        assert transcription == {
            "type": "transcription",
            "text": "Continue the training turn.",
            "is_final": True,
        }
        assert fake_chat.reply_started.wait(timeout=1)
        ws.close()

    assert fake_chat.sent_messages == [(8, "Continue the training turn.")]
    assert [(room_id, room.id) for room_id, room in fake_chat.reply_jobs] == [(8, 8)]


def test_voice_websocket_respects_battle_prep_round_limit(monkeypatch) -> None:
    fake_stt = _FakeSTT("This should not be sent.")
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)
    client = _make_client(
        fake_chat,
        _FakeChatRoomService(room_type="battle_prep", user_message_count=12),
    )

    with client.websocket_connect("/api/v1/stakeholder/rooms/9/voice") as ws:
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(b"voice-bytes").decode("ascii"),
            }
        )
        ws.send_json({"type": "speech_end", "format": "webm"})
        error = ws.receive_json()
        ws.close()

    assert error["type"] == "error"
    assert "12" in error["message"]
    assert fake_stt.calls == []
    assert fake_chat.sent_messages == []
    assert fake_chat.reply_jobs == []
