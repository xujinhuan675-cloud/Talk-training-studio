"""OpenAI Realtime transcription relay client."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import websockets


@dataclass(frozen=True)
class OpenAIRealtimeConfig:
    api_key: str
    model: str = "gpt-realtime"
    websocket_url: str | None = None
    transcription_model: str | None = None
    input_audio_format: str = "pcm16"
    instructions: str | None = None


class OpenAIRealtimeTranscriptionClient:
    """Tiny websocket adapter for OpenAI Realtime transcription sessions."""

    def __init__(self, config: OpenAIRealtimeConfig) -> None:
        self._config = config
        self._ws: Any | None = None

    async def connect(self) -> None:
        url = self._resolve_url()
        headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        self._ws = await websockets.connect(url, additional_headers=headers)
        await self._send_session_update()

    async def append_audio(self, audio: bytes) -> None:
        if not audio:
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(audio).decode("ascii"),
            }
        )

    async def commit_audio(self) -> None:
        await self._send({"type": "input_audio_buffer.commit"})

    async def receive_event(self) -> dict[str, Any] | None:
        if self._ws is None:
            return None
        raw = await self._ws.recv()
        if isinstance(raw, bytes):
            return None
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return {"type": "error", "message": "Invalid OpenAI realtime event"}
        return event if isinstance(event, dict) else None

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    def _resolve_url(self) -> str:
        if self._config.websocket_url:
            return self._config.websocket_url
        query = urlencode({"model": self._config.model})
        return f"wss://api.openai.com/v1/realtime?{query}"

    async def _send_session_update(self) -> None:
        turn_detection = None
        transcription: dict[str, object] | None = None
        if self._config.transcription_model:
            transcription = {"model": self._config.transcription_model}
        session: dict[str, object] = {
            "type": "transcription",
            "input_audio_format": self._config.input_audio_format,
            "turn_detection": turn_detection,
        }
        if transcription is not None:
            session["input_audio_transcription"] = transcription
        if self._config.instructions:
            session["instructions"] = self._config.instructions
        await self._send({"type": "session.update", "session": session})

    async def _send(self, payload: dict[str, object]) -> None:
        if self._ws is None:
            raise RuntimeError("OpenAI realtime websocket is not connected")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
