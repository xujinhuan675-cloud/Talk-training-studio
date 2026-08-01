from __future__ import annotations

import base64
from types import SimpleNamespace
from threading import Event
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketDenialResponse

import api.dependencies as dependency_module
from api.dependencies import (
    CurrentUser,
    get_chatroom_service,
    get_current_user,
    get_stakeholder_chat_service,
)
from api.routes.stakeholder import get_stakeholder_training_session_service, router
from application.ports.stt import TranscriptionResult
from application.services.stakeholder.dto import MessageDTO
from domain.stakeholder.entity import ChatRoom
from infrastructure.external.newapi_auth import NewAPIIdentity


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
        self.sent_metadata: list[dict[str, Any] | None] = []
        self.reply_jobs: list[tuple[int, ChatRoom]] = []
        self.reply_started = Event()

    async def send_message(
        self,
        room_id: int,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
        access_scope,
    ) -> tuple[MessageDTO, ChatRoom]:
        self.sent_messages.append((room_id, content))
        self.sent_metadata.append(metadata)
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
        self.access_scopes: list[Any] = []

    async def get_room_detail(
        self,
        room_id: int,
        message_limit: int = 200,
        access_scope=None,
    ) -> SimpleNamespace:
        self.access_scopes.append(access_scope)
        messages = [
            SimpleNamespace(sender_type="user")
            for _ in range(self.user_message_count)
        ]
        return SimpleNamespace(
            room=SimpleNamespace(id=room_id, type=self.room_type),
            messages=messages,
        )


class _FakeTrainingSessionService:
    def __init__(self, *, room_id: int, owner_user_id: str) -> None:
        self.room_id = room_id
        self.owner_user_id = owner_user_id
        self.access_scopes: list[Any] = []

    async def get_session(self, session_id: str, *, access_scope: Any) -> SimpleNamespace:
        self.access_scopes.append(access_scope)
        if access_scope.user_id != self.owner_user_id:
            raise PermissionError("Training session is outside current user scope")
        return SimpleNamespace(session_id=session_id, room_id=str(self.room_id))


def _make_client(
    fake_chat: _FakeStakeholderChatService,
    fake_rooms: _FakeChatRoomService | None = None,
    *,
    training_session_service: Any | None = None,
    use_current_user_override: bool = True,
) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_stakeholder_chat_service] = lambda: fake_chat
    app.dependency_overrides[get_chatroom_service] = lambda: fake_rooms or _FakeChatRoomService()
    if use_current_user_override:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="admin",
            username="admin",
            system_role="admin",
        )
    app.dependency_overrides[get_stakeholder_training_session_service] = (
        lambda: training_session_service or SimpleNamespace()
    )
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
    assert fake_chat.sent_metadata == [None]
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


def test_voice_websocket_forwards_message_metadata(monkeypatch) -> None:
    fake_stt = _FakeSTT("Answer with configured language.")
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)
    client = _make_client(fake_chat)

    metadata = {
        "replyLanguage": "en-US",
        "language": {"replyLanguage": "en-US"},
    }

    with client.websocket_connect("/api/v1/stakeholder/rooms/9/voice") as ws:
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(b"voice-bytes").decode("ascii"),
            }
        )
        ws.send_json({"type": "speech_end", "format": "webm", "metadata": metadata})
        assert ws.receive_json()["type"] == "transcription"
        assert ws.receive_json()["type"] == "message_sent"
        ws.close()

    assert fake_chat.sent_messages == [(9, "Answer with configured language.")]
    assert fake_chat.sent_metadata == [metadata]


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


def test_voice_websocket_rejects_invalid_audio_event_without_calling_stt(monkeypatch) -> None:
    fake_stt = _FakeSTT("This must not be transcribed.")
    fake_chat = _FakeStakeholderChatService()

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)
    client = _make_client(fake_chat)

    with client.websocket_connect("/api/v1/stakeholder/rooms/7/voice") as ws:
        ws.send_json({"type": "audio_chunk", "data": "not base64"})
        error = ws.receive_json()
        ws.close()

    assert error == {
        "type": "error",
        "code": "invalid_audio_chunk",
        "message": "Audio chunk data is not valid base64",
    }
    assert fake_stt.calls == []
    assert fake_chat.sent_messages == []


def test_voice_websocket_closes_oversized_recording(monkeypatch) -> None:
    fake_stt = _FakeSTT("This must not be transcribed.")
    fake_chat = _FakeStakeholderChatService()

    import api.routes.stakeholder as stakeholder_routes
    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: fake_stt)
    monkeypatch.setattr(stakeholder_routes, "_VOICE_MAX_AUDIO_BYTES", 4)
    client = _make_client(fake_chat)

    with client.websocket_connect("/api/v1/stakeholder/rooms/7/voice") as ws:
        ws.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(b"12345").decode("ascii"),
            }
        )
        error = ws.receive_json()

    assert error == {
        "type": "error",
        "code": "audio_too_large",
        "message": "Voice recording exceeds the supported size",
    }
    assert fake_stt.calls == []
    assert fake_chat.sent_messages == []


def test_voice_websocket_rejects_training_session_room_mismatch_before_accept() -> None:
    fake_chat = _FakeStakeholderChatService()
    fake_rooms = _FakeChatRoomService()
    training_sessions = _FakeTrainingSessionService(room_id=8, owner_user_id="admin")
    client = _make_client(
        fake_chat,
        fake_rooms,
        training_session_service=training_sessions,
    )

    with pytest.raises(WebSocketDenialResponse) as exc_info:
        with client.websocket_connect(
            "/api/v1/stakeholder/rooms/7/voice?trainingSessionId=session-1"
        ):
            pass

    assert exc_info.value.status_code == 403
    assert fake_rooms.access_scopes == []
    assert fake_chat.sent_messages == []


def test_voice_websocket_uses_newapi_bearer_identity_for_session_and_room_scope(
    monkeypatch,
) -> None:
    observed_tokens: list[str] = []

    async def fake_fetch_identity(
        access_token: str,
        *,
        base_url: str,
        timeout_seconds: float,
    ) -> NewAPIIdentity:
        observed_tokens.append(access_token)
        return NewAPIIdentity(
            id=73,
            username="voice-user",
            display_name="Voice User",
            role=1,
            team_id="team-revenue",
            team_name="Revenue",
        )

    monkeypatch.setattr(dependency_module.settings, "NEWAPI_AUTH_ENABLED", True)
    monkeypatch.setattr(dependency_module.settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", False)
    monkeypatch.setattr(dependency_module, "fetch_newapi_identity", fake_fetch_identity)

    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_stt_client", lambda: None)
    fake_chat = _FakeStakeholderChatService()
    fake_rooms = _FakeChatRoomService()
    training_sessions = _FakeTrainingSessionService(
        room_id=7,
        owner_user_id="newapi:73",
    )
    client = _make_client(
        fake_chat,
        fake_rooms,
        training_session_service=training_sessions,
        use_current_user_override=False,
    )

    with client.websocket_connect(
        "/api/v1/stakeholder/rooms/7/voice?trainingSessionId=session-1",
        headers={"Authorization": "Bearer voice-access-token"},
    ) as ws:
        error = ws.receive_json()

    assert error["code"] == "stt_not_configured"
    assert observed_tokens == ["voice-access-token"]
    assert training_sessions.access_scopes[0].user_id == "newapi:73"
    assert fake_rooms.access_scopes[0].guarded_by_training_session_id == "session-1"
    assert fake_rooms.access_scopes[0].guarded_room_id == "7"
    assert fake_rooms.access_scopes[0].unrestricted_reason == (
        "training_session:voice_stakeholder_room"
    )
