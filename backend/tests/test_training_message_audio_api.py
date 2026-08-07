from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import (
    CurrentUser,
    get_current_user,
    get_optional_turn_based_voice_pipeline,
    get_training_audio_service,
)
from api.routes.stakeholder import get_stakeholder_training_session_service, router


class _TrainingSessions:
    async def get_session(self, session_id: str, *, access_scope):
        if session_id == "outside-session":
            raise PermissionError("Training session is outside current user scope")
        return SimpleNamespace(session_id=session_id, room_id="42")


class _TrainingAudio:
    def __init__(self) -> None:
        self.contexts = []
        self.synthesized = False

    async def get_manifest(self, message_id: int, *, context):
        self.contexts.append(context)
        if message_id != 7:
            return None
        return {
            "available": True,
            "original": not self.synthesized,
            "provenance": (
                "server_resynthesis" if self.synthesized else "generated_for_message"
            ),
            "messageId": 7,
            "roomId": 42,
            "trainingSessionId": "session-1",
            "segmentCount": 1,
            "segments": [{"index": 0, "mimeType": "audio/wav", "size": 4}],
        }

    async def get_segment(self, message_id: int, segment_index: int, *, context):
        self.contexts.append(context)
        if (message_id, segment_index) != (7, 0):
            return None
        return SimpleNamespace(key="private.wav", mime_type="audio/wav", size=4)

    async def synthesize_and_attach(self, message_id: int, *, context, voice_pipeline, original):
        self.contexts.append(context)
        if message_id != 7 or original is not False:
            return None
        self.synthesized = True
        return SimpleNamespace(id=message_id)

    async def stream_segment(self, download):
        yield b"RIFF"


def _client(audio: _TrainingAudio) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="101",
        username="owner",
        system_role="user",
        team_id="team-9",
    )
    app.dependency_overrides[get_stakeholder_training_session_service] = _TrainingSessions
    app.dependency_overrides[get_training_audio_service] = lambda: audio
    app.dependency_overrides[get_optional_turn_based_voice_pipeline] = lambda: SimpleNamespace()
    return TestClient(app)


def test_training_message_audio_requires_session_room_and_message_binding():
    audio = _TrainingAudio()
    client = _client(audio)

    response = client.get(
        "/api/v1/stakeholder/rooms/42/messages/7/audio",
        params={"trainingSessionId": "session-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["segments"] == [{"index": 0, "mimeType": "audio/wav", "size": 4}]
    assert audio.contexts[0].user_id == "101"
    assert audio.contexts[0].team_id == "team-9"

    wrong_room = client.get(
        "/api/v1/stakeholder/rooms/41/messages/7/audio",
        params={"trainingSessionId": "session-1"},
    )
    assert wrong_room.status_code == 403

    outside_session = client.get(
        "/api/v1/stakeholder/rooms/42/messages/7/audio",
        params={"trainingSessionId": "outside-session"},
    )
    assert outside_session.status_code == 403


def test_training_message_audio_segment_is_private_and_not_addressable_by_asset_url():
    client = _client(_TrainingAudio())

    response = client.get(
        "/api/v1/stakeholder/rooms/42/messages/7/audio/0",
        params={"trainingSessionId": "session-1"},
    )

    assert response.status_code == 200
    assert response.content == b"RIFF"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith("audio/wav")

    missing = client.get(
        "/api/v1/stakeholder/rooms/42/messages/7/audio/1",
        params={"trainingSessionId": "session-1"},
    )
    assert missing.status_code == 404


def test_historical_audio_synthesis_stays_scoped_and_is_marked_non_original():
    audio = _TrainingAudio()
    client = _client(audio)

    response = client.post(
        "/api/v1/stakeholder/rooms/42/messages/7/audio/synthesize",
        params={"trainingSessionId": "session-1"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["original"] is False
    assert response.json()["data"]["provenance"] == "server_resynthesis"
    assert audio.contexts[0].user_id == "101"
    assert audio.contexts[0].training_session_id == "session-1"


def test_historical_audio_synthesis_reports_upstream_voice_mismatch():
    audio = _TrainingAudio()

    async def fail_synthesis(*args, **kwargs):
        raise RuntimeError("NewAPI TTS request failed with status 502")

    audio.synthesize_and_attach = fail_synthesis
    client = _client(audio)

    response = client.post(
        "/api/v1/stakeholder/rooms/42/messages/7/audio/synthesize",
        params={"trainingSessionId": "session-1"},
    )

    assert response.status_code == 502
    assert "resource and selected voice are compatible" in response.json()["detail"]
