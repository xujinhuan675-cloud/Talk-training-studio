"""API tests for Training Studio realtime WebSocket."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.training_studio import router


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
