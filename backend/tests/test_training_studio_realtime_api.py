"""API tests for Training Studio realtime WebSocket."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import training_studio as training_studio_routes
from api.routes.training_studio import (
    get_training_realtime_openai_factory,
    get_training_realtime_pipeline_factory,
    get_training_realtime_uow_factory,
    get_training_session_service,
    router,
)
from application.ports.realtime import (
    REALTIME_RUNTIME_OPENAI,
    REALTIME_RUNTIME_PIPECAT,
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    TrainingVoiceContext,
)
from application.services.stakeholder.sse import room_event_bus
from application.services.training_studio.session_service import TrainingSessionService
from core.config import settings
from domain.stakeholder.entity import ChatRoom, Message


def _session_payload(
    mode: str = "realtime",
    *,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict:
    payload = {
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
    if user_id is not None:
        payload["user_id"] = user_id
    if team_id is not None:
        payload["team_id"] = team_id
    return payload


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

    async def list_by_room_id(
        self, room_id: int, *, skip: int = 0, limit: int = 50
    ) -> list[Message]:
        messages = [message for message in self._state.messages if message.room_id == room_id]
        messages.sort(key=lambda message: message.timestamp)
        return messages[skip : skip + limit]

    async def count_by_room_id(self, room_id: int) -> int:
        return sum(1 for message in self._state.messages if message.room_id == room_id)


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


class _FakeRealtimePipelineAdapter:
    def __init__(self) -> None:
        self.started_context: TrainingVoiceContext | None = None
        self.started_config: RealtimePipelineConfig | None = None
        self.audio_chunks: list[RealtimeAudioChunk] = []
        self.commits = 0
        self.closed = False
        self.start_error: Exception | None = None
        self.events_on_commit: list[Mapping[str, Any]] = []
        self._events: asyncio.Queue[Mapping[str, Any] | None] = asyncio.Queue()

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        self.started_context = context
        self.started_config = config
        if self.start_error is not None:
            raise self.start_error

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        self.audio_chunks.append(chunk)

    async def commit_audio(self) -> None:
        self.commits += 1
        for event in self.events_on_commit:
            await self._events.put(event)

    async def events(self) -> AsyncIterator[Mapping[str, Any]]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        self.closed = True
        await self._events.put(None)


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

    async def post(
        self, url: str, *, data=None, files=None, headers=None, **_kwargs
    ) -> httpx.Response:
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


def _make_bound_app(
    *,
    active: bool = True,
    session_payload: dict | None = None,
) -> tuple[FastAPI, _RealtimeRoomState]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    session = asyncio.run(session_service.create_session(session_payload or _session_payload()))
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


def _make_realtime_capability_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _fake_pipecat_adapter(capability, snapshot: dict | None = None):
    calls: dict[str, object] = {}
    adapter = SimpleNamespace()

    def get_pipecat_capability(*, require_websocket: bool = False):
        calls["require_websocket"] = require_websocket
        return capability

    def pipecat_source_snapshot():
        return snapshot or {"checkedAt": "test", "coreEntrypoints": ("pipecat.Pipeline",)}

    def pipecat_realtime_capability_response(
        *,
        require_websocket: bool = True,
        openai_api_key_available: bool | None = None,
        include_source_snapshot: bool = True,
    ):
        from infrastructure.external.pipecat import realtime_pipeline as pipecat_adapter

        calls["require_websocket"] = require_websocket
        calls["openai_api_key_available"] = openai_api_key_available
        data = {
            "runtime": "pipecat",
            "provider": "pipecat",
            "available": bool(capability.available),
            "coreAvailable": bool(capability.core_available),
            "websocketAvailable": bool(capability.websocket_available),
            "vadAvailable": bool(getattr(capability, "vad_available", False)),
            "sttAvailable": bool(getattr(capability, "stt_available", False)),
            "ttsAvailable": bool(getattr(capability, "tts_available", False)),
            "llmAvailable": bool(getattr(capability, "llm_available", False)),
            "turnDetectionAvailable": bool(
                getattr(capability, "turn_detection_available", False)
            ),
            "missingModules": [str(module) for module in capability.missing_modules],
            "optionalMissingModules": [
                str(module)
                for module in getattr(capability, "optional_missing_modules", ())
            ],
            "error": capability.error,
        }
        readiness = pipecat_adapter.pipecat_realtime_readiness(
            capability,
            require_websocket=require_websocket,
            openai_api_key_available=openai_api_key_available,
        ).to_dict()
        data["readyForCall"] = readiness["ready"]
        data["readiness"] = readiness
        data["errors"] = readiness["blockingReasons"]
        if include_source_snapshot:
            try:
                data["sourceSnapshot"] = dict(adapter.pipecat_source_snapshot())
            except Exception:
                pass
        return data

    adapter.calls = calls
    adapter.get_pipecat_capability = get_pipecat_capability
    adapter.pipecat_source_snapshot = pipecat_source_snapshot
    adapter.pipecat_realtime_capability_response = pipecat_realtime_capability_response
    return adapter


def test_realtime_capabilities_reports_openai_and_available_pipecat(monkeypatch) -> None:
    capability = SimpleNamespace(
        available=True,
        core_available=True,
        websocket_available=True,
        vad_available=True,
        stt_available=True,
        tts_available=True,
        llm_available=True,
        turn_detection_available=True,
        missing_modules=(),
        optional_missing_modules=(),
        error=None,
    )
    adapter = _fake_pipecat_adapter(
        capability,
        snapshot={
            "checkedAt": "test",
            "coreEntrypoints": ("pipecat.pipeline.pipeline.Pipeline",),
            "vadEntrypoint": "pipecat.audio.vad.silero.SileroVADAnalyzer",
            "vadProcessorEntrypoint": "pipecat.processors.audio.vad_processor.VADProcessor",
            "turnDetectionEntrypoint": "pipecat.turns.user_turn_processor.UserTurnProcessor",
        },
    )
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: adapter,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", "sk-realtime-capability")
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "REALTIME_OPENAI_MODEL", "gpt-realtime-test")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "marin-test")
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["openaiRealtime"]["configured"] is True
    assert data["openaiRealtime"]["effectiveKey"] is True
    assert data["openaiRealtime"]["runtime"] == REALTIME_RUNTIME_OPENAI
    assert data["openaiRealtime"]["model"] == "gpt-realtime-test"
    assert data["openaiRealtime"]["voice"] == "marin-test"
    assert data["openaiRealtime"]["readyForCall"] is True
    assert data["openaiRealtime"]["readiness"]["status"] == "ready"
    assert data["openaiRealtime"]["readiness"]["blockingReasons"] == []
    assert data["openaiRealtime"]["errors"] == []
    assert "sk-realtime-capability" not in response.text
    assert data["pipecat"]["available"] is True
    assert data["pipecat"]["provider"] == "pipecat"
    assert data["pipecat"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert data["pipecat"]["coreAvailable"] is True
    assert data["pipecat"]["websocketAvailable"] is True
    assert data["pipecat"]["vadAvailable"] is True
    assert data["pipecat"]["sttAvailable"] is True
    assert data["pipecat"]["ttsAvailable"] is True
    assert data["pipecat"]["llmAvailable"] is True
    assert data["pipecat"]["turnDetectionAvailable"] is True
    assert data["pipecat"]["missingModules"] == []
    assert data["pipecat"]["optionalMissingModules"] == []
    assert data["pipecat"]["error"] is None
    assert data["pipecat"]["readyForCall"] is True
    assert data["pipecat"]["readiness"]["ready"] is True
    assert data["pipecat"]["readiness"]["status"] == "ready"
    assert data["pipecat"]["readiness"]["blockingReasons"] == []
    assert data["pipecat"]["readiness"]["required"]["features"] == {
        "stt": "openai",
        "tts": "openai",
        "llm": "openai",
        "vad": "silero",
        "turnDetection": "pipecat",
    }
    assert data["pipecat"]["errors"] == []
    assert data["pipecat"]["sourceSnapshot"]["coreEntrypoints"] == [
        "pipecat.pipeline.pipeline.Pipeline"
    ]
    assert (
        data["pipecat"]["sourceSnapshot"]["vadEntrypoint"]
        == "pipecat.audio.vad.silero.SileroVADAnalyzer"
    )
    assert (
        data["pipecat"]["sourceSnapshot"]["vadProcessorEntrypoint"]
        == "pipecat.processors.audio.vad_processor.VADProcessor"
    )
    assert (
        data["pipecat"]["sourceSnapshot"]["turnDetectionEntrypoint"]
        == "pipecat.turns.user_turn_processor.UserTurnProcessor"
    )
    assert adapter.calls["require_websocket"] is True
    assert adapter.calls["openai_api_key_available"] is True


def test_realtime_capabilities_reports_missing_pipecat_without_error(monkeypatch) -> None:
    capability = SimpleNamespace(
        available=False,
        core_available=False,
        websocket_available=False,
        vad_available=False,
        stt_available=False,
        tts_available=False,
        llm_available=False,
        turn_detection_available=False,
        missing_modules=("pipecat.pipeline.pipeline", "pipecat.frames.frames"),
        optional_missing_modules=("onnxruntime",),
        error="Missing optional Pipecat module(s)",
    )
    adapter = _fake_pipecat_adapter(capability)
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: adapter,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "api_key", "sk-llm-fallback")
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["openaiRealtime"]["configured"] is True
    assert data["openaiRealtime"]["effectiveKey"] is True
    assert data["openaiRealtime"]["runtime"] == REALTIME_RUNTIME_OPENAI
    assert data["openaiRealtime"]["readyForCall"] is True
    assert data["openaiRealtime"]["readiness"]["status"] == "ready"
    assert "sk-llm-fallback" not in response.text
    assert data["pipecat"]["available"] is False
    assert data["pipecat"]["provider"] == "pipecat"
    assert data["pipecat"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert data["pipecat"]["coreAvailable"] is False
    assert data["pipecat"]["websocketAvailable"] is False
    assert data["pipecat"]["llmAvailable"] is False
    assert data["pipecat"]["turnDetectionAvailable"] is False
    assert data["pipecat"]["missingModules"] == [
        "pipecat.pipeline.pipeline",
        "pipecat.frames.frames",
    ]
    assert data["pipecat"]["optionalMissingModules"] == ["onnxruntime"]
    assert data["pipecat"]["error"] == "Missing optional Pipecat module(s)"
    assert data["pipecat"]["readyForCall"] is False
    assert data["pipecat"]["readiness"]["ready"] is False
    assert data["pipecat"]["readiness"]["status"] == "blocked"
    assert data["pipecat"]["errors"][0]["code"] == "PIPECAT_MODULE_UNAVAILABLE"
    assert data["pipecat"]["errors"][0]["phase"] == "capability_check"
    assert data["pipecat"]["errors"][0]["modules"] == [
        "pipecat.pipeline.pipeline",
        "pipecat.frames.frames",
    ]
    assert adapter.calls["require_websocket"] is True


def test_realtime_capabilities_reports_pipecat_adapter_import_failure(monkeypatch) -> None:
    def _raise_import_failure():
        raise RuntimeError("Pipecat adapter import failed")

    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        _raise_import_failure,
    )
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]["pipecat"]
    assert data["provider"] == "pipecat"
    assert data["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert data["available"] is False
    assert data["coreAvailable"] is False
    assert data["websocketAvailable"] is False
    assert data["missingModules"] == ["infrastructure.external.pipecat"]
    assert data["error"] == "Pipecat adapter import failed"
    assert data["readyForCall"] is False
    assert data["errors"][0]["code"] == "PIPECAT_MODULE_UNAVAILABLE"
    assert data["errors"][0]["modules"] == ["infrastructure.external.pipecat"]


def test_realtime_capabilities_reports_pipecat_capability_exception(monkeypatch) -> None:
    def _raise_capability_failure(**_kwargs):
        raise RuntimeError("Pipecat capability crashed")

    adapter = SimpleNamespace(pipecat_realtime_capability_response=_raise_capability_failure)
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: adapter,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", "sk-realtime-snapshot")
    monkeypatch.setattr(settings.llm, "api_key", None)
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]["pipecat"]
    assert data["provider"] == "pipecat"
    assert data["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert data["available"] is False
    assert data["coreAvailable"] is False
    assert data["websocketAvailable"] is False
    assert data["missingModules"] == []
    assert data["error"] == "Pipecat capability check failed: Pipecat capability crashed"
    assert data["readyForCall"] is False
    assert data["errors"][0]["code"] == "PIPECAT_CAPABILITY_ERROR"
    assert data["errors"][0]["phase"] == "capability_check"


def test_realtime_capabilities_omits_pipecat_source_snapshot_when_snapshot_fails(
    monkeypatch,
) -> None:
    capability = SimpleNamespace(
        available=True,
        core_available=True,
        websocket_available=True,
        vad_available=True,
        stt_available=True,
        tts_available=True,
        llm_available=True,
        turn_detection_available=True,
        missing_modules=(),
        optional_missing_modules=(),
        error=None,
    )
    adapter = _fake_pipecat_adapter(capability)

    def _raise_snapshot_failure():
        raise RuntimeError("Pipecat source snapshot failed")

    adapter.pipecat_source_snapshot = _raise_snapshot_failure
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: adapter,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", "sk-realtime-snapshot")
    monkeypatch.setattr(settings.llm, "api_key", None)
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    payload = response.json()["data"]
    openai = payload["openaiRealtime"]
    data = payload["pipecat"]
    assert openai["readyForCall"] is True
    assert openai["readiness"]["status"] == "ready"
    assert openai["errors"] == []
    assert data["available"] is True
    assert data["coreAvailable"] is True
    assert data["websocketAvailable"] is True
    assert data["missingModules"] == []
    assert data["optionalMissingModules"] == []
    assert data["error"] is None
    assert data["readyForCall"] is True
    assert data["errors"] == []
    assert "sourceSnapshot" not in data
    assert "Pipecat source snapshot failed" not in response.text
    assert adapter.calls["require_websocket"] is True


def test_realtime_capabilities_reports_missing_openai_key_for_pipecat_readiness(
    monkeypatch,
) -> None:
    capability = SimpleNamespace(
        available=True,
        core_available=True,
        websocket_available=True,
        vad_available=True,
        stt_available=True,
        tts_available=True,
        llm_available=True,
        turn_detection_available=True,
        missing_modules=(),
        optional_missing_modules=(),
        error=None,
    )
    adapter = _fake_pipecat_adapter(capability)
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: adapter,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    payload = response.json()["data"]
    openai = payload["openaiRealtime"]
    data = payload["pipecat"]
    assert openai["readyForCall"] is False
    assert openai["readiness"]["status"] == "blocked"
    assert openai["errors"][0]["code"] == "MISSING_OPENAI_API_KEY"
    assert openai["errors"][0]["provider"] == "openaiRealtime"
    assert data["available"] is True
    assert data["readyForCall"] is False
    assert data["errors"] == [
        {
            "code": "MISSING_OPENAI_API_KEY",
            "message": (
                "Set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY "
                "before starting Pipecat realtime calls"
            ),
            "phase": "configuration",
            "provider": "pipecat",
            "missingEnv": ["REALTIME_OPENAI_API_KEY", "LLM__API_KEY", "OPENAI_API_KEY"],
        }
    ]


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
                    "metadata": {
                        "source": "live_coach_realtime_voice",
                        "trainingProfile": "live_coach",
                        "sourceLanguage": "zh-CN",
                        "targetLanguage": "en-US",
                        "translationStrategy": "text_first_mvp",
                        "translation": {
                            "mode": "text_first_mvp",
                            "sourceLanguage": "zh-CN",
                            "targetLanguage": "en-US",
                            "preserveTone": True,
                            "extensionPoints": ["virtual_microphone"],
                        },
                    },
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
    for index, message in enumerate(state.messages):
        assert message.metadata["source"] == (
            "live_coach_realtime_voice" if index == 0 else "realtime_voice"
        )
        assert message.metadata["trainingMode"] == "voice"
        assert message.metadata["interactionMode"] == "realtime"
        assert message.metadata["realtime"]["trainingSessionId"] == "session-1"
        assert message.metadata["realtime"]["roomId"] == 42
    assert state.messages[0].metadata["trainingProfile"] == "live_coach"
    assert state.messages[0].metadata["sourceLanguage"] == "zh-CN"
    assert state.messages[0].metadata["targetLanguage"] == "en-US"
    assert state.messages[0].metadata["translationStrategy"] == "text_first_mvp"
    assert state.messages[0].metadata["translation"] == {
        "mode": "text_first_mvp",
        "sourceLanguage": "zh-CN",
        "targetLanguage": "en-US",
        "preserveTone": True,
    }
    assert state.messages[0].metadata["realtime"]["sourceLanguage"] == "zh-CN"
    assert state.messages[0].metadata["realtime"]["targetLanguage"] == "en-US"
    assert state.messages[0].metadata["realtime"]["translationIntent"] == "text_first_mvp"
    session_response = client.get("/api/v1/training-studio/sessions/session-1")
    assert session_response.status_code == 200
    assert session_response.json()["data"]["message_count"] == 2


def test_realtime_transcript_persistence_rejects_other_mock_user_binding() -> None:
    app, state = _make_bound_app(
        session_payload=_session_payload(
            user_id="user-cs-001",
            team_id="team-service",
        )
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/training-studio/realtime/transcripts",
        headers={"X-Mock-User": "sales"},
        json={
            "session_id": "session-1",
            "room_id": 42,
            "messages": [
                {
                    "role": "user",
                    "content": "This transcript must not cross user boundaries.",
                }
            ],
        },
    )

    assert response.status_code == 403
    assert "current user scope" in _response_error_message(response)
    assert state.messages == []


def test_guidance_event_persistence_endpoint_stores_system_coach_messages_without_turn_count() -> (
    None
):
    app, state = _make_bound_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/training-studio/sessions/session-1/guidance-events",
        json={
            "reason": "session_complete",
            "source": "client",
            "window_size": 2,
            "total_turn_count": 2,
            "events": [
                {
                    "event_type": "risk",
                    "severity": "warning",
                    "title": "Objection surfaced",
                    "message": "The counterpart just signaled resistance.",
                    "suggested_text": "That concern makes sense.",
                    "metadata": {"risk_type": "objection"},
                    "created_at": "2026-07-15T12:00:00Z",
                }
            ],
            "metadata": {
                "trainingProfile": "live_coach",
                "sourceLanguage": "zh-CN",
                "targetLanguage": "en-US",
            },
        },
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["saved_count"] == 1
    assert data["messages"][0]["sender_type"] == "system"
    assert data["messages"][0]["sender_id"] == "training_coach"
    assert "Objection surfaced" in data["messages"][0]["content"]
    assert state.messages[0].sender_type == "system"
    assert state.messages[0].sender_id == "training_coach"
    assert state.messages[0].metadata["source"] == "training_live_guidance"
    assert state.messages[0].metadata["eventKind"] == "guidance"
    assert state.messages[0].metadata["trainingSessionId"] == "session-1"
    assert state.messages[0].metadata["roomId"] == 42
    assert state.messages[0].metadata["guidance"]["event_type"] == "risk"
    assert state.messages[0].metadata["guidance"]["metadata"]["risk_type"] == "objection"
    assert state.messages[0].metadata["clientMetadata"]["trainingProfile"] == "live_coach"
    session_response = client.get("/api/v1/training-studio/sessions/session-1")
    assert session_response.status_code == 200
    assert session_response.json()["data"]["message_count"] == 0


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
            assert (
                persisted["payload"]["message"]["content"] == "We can start with a low-risk pilot."
            )

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

        ws.send_json(
            {
                "type": "transcript.done",
                "text": "Configured binding path.",
                "metadata": {
                    "trainingProfile": "live_coach",
                    "sourceLanguage": "ja",
                    "targetLanguage": "en-US",
                    "translationIntent": "text_first_mvp",
                },
            }
        )
        persisted = ws.receive_json()
        assert persisted["type"] == "transcript.persisted"
        assert persisted["payload"]["message"]["content"] == "Configured binding path."

    assert [message.content for message in state.messages] == ["Configured binding path."]
    assert state.messages[0].metadata["realtime"]["eventType"] == "transcript.done"
    assert state.messages[0].metadata["trainingProfile"] == "live_coach"
    assert state.messages[0].metadata["sourceLanguage"] == "ja"
    assert state.messages[0].metadata["targetLanguage"] == "en-US"
    assert state.messages[0].metadata["realtime"]["translationIntent"] == "text_first_mvp"


def test_realtime_websocket_pipecat_provider_configure_binding_starts_pipeline() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect("/api/v1/training-studio/realtime?provider=pipecat") as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["provider"] == "pipecat"
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
        assert "trainingSessionId" not in started["payload"]
        assert listening["status"] == "listening"
        assert adapter.started_context is None

        ws.send_json({"type": "session.configure", "sessionId": "session-1", "roomId": 42})
        configured = ws.receive_json()
        assert configured["type"] == "session.configured"
        assert configured["payload"] == {
            "bound": True,
            "trainingSessionId": "session-1",
            "roomId": 42,
        }

        ws.send_json({"type": "session.close", "reason": "configured"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.started_context is not None
    assert adapter.started_context.binding.training_session_id == "session-1"
    assert adapter.started_context.binding.room_id == 42
    assert adapter.started_context.metadata["runtime"] == "realtime_voice"
    assert adapter.started_context.metadata["provider"] == "pipecat"
    assert adapter.started_context.metadata["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_config is not None
    assert adapter.started_config.provider == "pipecat"
    assert adapter.started_config.runtime == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_config.metadata["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_config.metadata["talkwise"] == {
        "trainingSessionId": "session-1",
        "roomId": 42,
        "provider": "pipecat",
        "runtime": "realtime_voice",
        "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
        "transport": "websocket",
    }
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_injects_recent_room_turns() -> None:
    app, state = _make_bound_app()
    state.messages.extend(
        [
            Message(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="user",
                content="Can we discuss renewal risk?",
                metadata={"source": "realtime_voice"},
            ),
            Message(
                id=2,
                room_id=42,
                sender_type="system",
                sender_id="training_coach",
                content="Ask one sharper follow-up.",
                metadata={"source": "training_live_guidance"},
            ),
            Message(
                id=3,
                room_id=42,
                sender_type="persona",
                sender_id="buyer",
                content="I am worried the rollout is risky.",
                metadata={"source": "realtime_voice"},
            ),
        ]
    )
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"type": "session.close", "reason": "context"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.started_context is not None
    assert [
        (turn["speaker"], turn["text"]) for turn in adapter.started_context.recent_turns
    ] == [
        ("user", "Can we discuss renewal risk?"),
        ("counterpart", "I am worried the rollout is risky."),
    ]
    assert adapter.started_context.recent_turns[0]["metadata"]["message_id"] == 1
    assert adapter.started_context.recent_turns[1]["metadata"]["sender_id"] == "buyer"
    assert adapter.closed is True


def test_realtime_websocket_binding_requires_active_training_session() -> None:
    app, _ = _make_bound_app(active=False)
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42"
    ) as ws:
        error = ws.receive_json()
        assert error["type"] == "error"
        assert "active" in error["payload"]["message"]


def test_realtime_websocket_query_binding_rejects_other_mock_user() -> None:
    app, state = _make_bound_app(
        session_payload=_session_payload(
            user_id="user-cs-001",
            team_id="team-service",
        )
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&mock_user=sales"
    ) as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "BINDING_ERROR"
    assert error["payload"]["phase"] == "binding"
    assert "current user scope" in error["payload"]["message"]
    assert "trainingSessionId" not in error["payload"]
    assert "roomId" not in error["payload"]
    assert state.messages == []


def test_realtime_websocket_configure_binding_rejects_other_mock_user() -> None:
    app, state = _make_bound_app(
        session_payload=_session_payload(
            user_id="user-cs-001",
            team_id="team-service",
        )
    )
    client = TestClient(app)

    with client.websocket_connect("/api/v1/training-studio/realtime?mock_user=sales") as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["type"] == "session.started"
        assert listening["status"] == "listening"

        ws.send_json({"type": "session.configure", "sessionId": "session-1", "roomId": 42})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "BINDING_ERROR"
    assert error["payload"]["phase"] == "binding"
    assert "current user scope" in error["payload"]["message"]
    assert "trainingSessionId" not in error["payload"]
    assert "roomId" not in error["payload"]
    assert state.messages == []


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
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_OPENAI
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
    assert state.messages[0].metadata["realtime"]["runtime"] == REALTIME_RUNTIME_OPENAI
    assert state.messages[0].metadata["realtime"]["provider"] == "openai"
    assert state.messages[0].metadata["realtime"]["eventId"] == "evt_test"
    assert state.messages[0].metadata["realtime"]["itemId"] == "item_test"


def test_realtime_websocket_pipecat_provider_persists_provider_neutral_assistant_turn() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        started = ws.receive_json()
        ws.receive_json()
        assert started["payload"]["provider"] == "pipecat"
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT

        ws.send_json(
            {
                "type": "response.audio_transcript.done",
                "text": "That works if we define the pilot metric first.",
                "response_id": "response_pipecat_1",
                "source": "pipecat",
            }
        )
        persisted = ws.receive_json()

    assert persisted["type"] == "transcript.persisted"
    assert persisted["payload"]["message"]["content"] == (
        "That works if we define the pilot metric first."
    )
    assert state.messages[0].sender_type == "persona"
    assert state.messages[0].sender_id == "assistant"
    assert state.messages[0].metadata["source"] == "pipecat"
    assert state.messages[0].metadata["trainingMode"] == "voice"
    assert state.messages[0].metadata["interactionMode"] == "realtime"
    assert state.messages[0].metadata["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert state.messages[0].metadata["realtime"]["provider"] == "pipecat"
    assert state.messages[0].metadata["realtime"]["role"] == "assistant"
    assert state.messages[0].metadata["realtime"]["responseId"] == "response_pipecat_1"


def test_realtime_websocket_pipecat_provider_relays_audio_output_and_persists_final_transcript() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    output_audio = b"\x10\x20\x30"
    adapter.events_on_commit.extend(
        [
            {
                "type": "audio.output",
                "runtime": REALTIME_RUNTIME_PIPECAT,
                "provider": "pipecat",
                "audio": output_audio,
                "mimeType": "audio/pcm",
                "sequence": 99,
                "metadata": {"providerFrame": "tts"},
            },
            {
                "type": "response.audio_transcript.done",
                "runtime": REALTIME_RUNTIME_PIPECAT,
                "text": "Let's define the pilot metric before we begin.",
                "response_id": "response_pipecat_2",
                "source": "pipecat",
            },
        ]
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["provider"] == "pipecat"
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
        assert listening["status"] == "listening"

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        events = [ws.receive_json() for _ in range(4)]

        assert committed["status"] == "processing"
        audio_output = next(event for event in events if event["type"] == "audio.output")
        persisted = next(event for event in events if event["type"] == "transcript.persisted")
        guidance_trigger = next(
            event for event in events if event["type"] == "training.live_guidance.triggered"
        )
        assert any(
            event["type"] == "status.changed" and event["status"] == "listening"
            for event in events
        )
        assert audio_output["status"] == "speaking"
        assert audio_output["payload"]["audio"] == base64.b64encode(output_audio).decode("ascii")
        assert audio_output["payload"]["bytes"] == len(output_audio)
        assert audio_output["payload"]["mimeType"] == "audio/pcm"
        assert audio_output["payload"]["mime_type"] == "audio/pcm"
        assert audio_output["payload"]["sequence"] == 1
        assert audio_output["payload"]["runtime"] == REALTIME_RUNTIME_PIPECAT
        assert audio_output["payload"]["provider"] == "pipecat"
        assert audio_output["payload"]["metadata"] == {"providerFrame": "tts"}
        assert persisted["payload"]["message"]["content"] == (
            "Let's define the pilot metric before we begin."
        )
        assert guidance_trigger["payload"]["reason"] == "final_transcript"
        assert guidance_trigger["payload"]["runtime"] == REALTIME_RUNTIME_PIPECAT
        assert guidance_trigger["payload"]["provider"] == "pipecat"
        assert guidance_trigger["payload"]["trainingSessionId"] == "session-1"
        assert guidance_trigger["payload"]["roomId"] == 42
        assert guidance_trigger["payload"]["transcript"] == {
            "text": "Let's define the pilot metric before we begin.",
            "role": "assistant",
            "eventType": "response.audio_transcript.done",
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "responseId": "response_pipecat_2",
        }

        ws.send_json({"type": "session.close", "reason": "audio-output"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.commits == 1
    assert adapter.closed is True
    assert [message.content for message in state.messages] == [
        "Let's define the pilot metric before we begin."
    ]
    assert state.messages[0].sender_type == "persona"
    assert state.messages[0].sender_id == "assistant"
    assert state.messages[0].metadata["source"] == "pipecat"
    assert state.messages[0].metadata["trainingMode"] == "voice"
    assert state.messages[0].metadata["interactionMode"] == "realtime"
    assert state.messages[0].metadata["realtime"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert state.messages[0].metadata["realtime"]["provider"] == "pipecat"
    assert state.messages[0].metadata["realtime"]["responseId"] == "response_pipecat_2"


def test_realtime_websocket_pipecat_provider_forwards_audio_to_pipeline() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)
    audio = b"\x01\x02\x03"

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["provider"] == "pipecat"
        assert listening["status"] == "listening"

        ws.send_json(
            {
                "type": "audio.input",
                "audio": base64.b64encode(audio).decode("ascii"),
                "mimeType": "audio/pcm",
            }
        )
        audio_event = ws.receive_json()
        assert audio_event["type"] == "audio.input"

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        back_to_listening = ws.receive_json()
        assert committed["status"] == "processing"
        assert back_to_listening["status"] == "listening"

        ws.send_json({"type": "session.close", "reason": "test"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.started_context is not None
    assert adapter.started_context.binding.training_session_id == "session-1"
    assert adapter.started_context.binding.room_id == 42
    assert "Sales Associate" in str(adapter.started_context.task_goal)
    assert isinstance(adapter.started_context.rubric, dict)
    assert adapter.started_context.metadata["runtime"] == "realtime_voice"
    assert adapter.started_context.metadata["trainingSessionId"] == "session-1"
    assert adapter.started_context.metadata["provider"] == "pipecat"
    assert adapter.started_context.metadata["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_context.metadata["transport"] == "websocket"
    assert adapter.started_context.metadata["roomId"] == 42
    assert adapter.started_config is not None
    assert adapter.started_config.provider == "pipecat"
    assert adapter.started_config.runtime == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_config.instructions
    assert adapter.started_config.metadata["transport"] == "websocket"
    assert adapter.started_config.metadata["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
    stt_metadata = adapter.started_config.metadata["stt"]
    assert isinstance(stt_metadata, dict)
    assert stt_metadata["provider"] == "openai"
    assert stt_metadata["turnDetection"] == "disabled"
    if settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL:
        assert stt_metadata["model"] == settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL
    assert adapter.started_config.metadata["tts"] == {"provider": "openai"}
    assert adapter.started_config.metadata["llm"]["provider"] == "openai"
    assert adapter.started_config.metadata["llm"]["model"] == settings.llm.default_model
    assert adapter.started_config.metadata["context"] == {
        "provider": "pipecat",
        "realtimeServiceMode": False,
    }
    assert adapter.started_config.metadata["vad"] == {
        "provider": "silero",
        "source": "pipecat",
        "sampleRate": 16000,
    }
    assert adapter.started_config.metadata["turnDetection"] == {
        "provider": "pipecat",
        "source": "pipecat",
    }
    assert adapter.started_config.metadata["talkwise"] == {
        "trainingSessionId": "session-1",
        "roomId": 42,
        "provider": "pipecat",
        "runtime": "realtime_voice",
        "realtimeRuntime": REALTIME_RUNTIME_PIPECAT,
        "transport": "websocket",
    }
    assert adapter.audio_chunks == [
        RealtimeAudioChunk(data=audio, mime_type="audio/pcm", sequence=1)
    ]
    assert adapter.commits == 1
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_forwards_binary_audio_to_pipeline() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)
    audio = b"\x09\x08\x07"

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["provider"] == "pipecat"
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
        assert listening["status"] == "listening"

        ws.send_bytes(audio)
        audio_event = ws.receive_json()
        assert audio_event["type"] == "audio.input"

        ws.send_json({"type": "session.close", "reason": "binary"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.audio_chunks == [
        RealtimeAudioChunk(data=audio, mime_type="audio/pcm", sequence=1)
    ]
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_rejects_invalid_base64_audio() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "audio.input", "audio": "not-base64!"})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "INVALID_AUDIO"
    assert "Invalid base64 audio frame" in error["payload"]["message"]
    assert adapter.audio_chunks == []


def test_realtime_websocket_pipecat_provider_surfaces_pipeline_error_on_commit() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "pipeline.error",
            "error": {"message": "Pipecat provider disconnected"},
        }
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        error = ws.receive_json()

    assert committed["status"] == "processing"
    assert error["type"] == "error"
    assert error["payload"]["code"] == "PIPECAT_PROVIDER_ERROR"
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "provider_event"
    assert error["payload"]["eventType"] == "pipeline.error"
    assert error["payload"]["trainingSessionId"] == "session-1"
    assert error["payload"]["roomId"] == 42
    assert "Pipecat provider disconnected" in error["payload"]["message"]
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_surfaces_pipeline_start_error() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.start_error = RuntimeError("Pipecat OpenAI realtime STT service is unavailable")
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "PIPECAT_FEATURE_UNAVAILABLE"
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "pipeline_start"
    assert error["payload"]["feature"] == "stt:openai"
    assert error["payload"]["trainingSessionId"] == "session-1"
    assert error["payload"]["roomId"] == 42
    assert "Pipecat OpenAI realtime STT service is unavailable" in error["payload"]["message"]
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_surfaces_missing_api_key_start_error() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.start_error = RuntimeError("OpenAI API key is required for Pipecat OpenAI STT")
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "MISSING_OPENAI_API_KEY"
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "configuration"
    assert error["payload"]["feature"] == "stt:openai"
    assert error["payload"]["missingEnv"] == [
        "REALTIME_OPENAI_API_KEY",
        "LLM__API_KEY",
        "OPENAI_API_KEY",
    ]
    assert error["payload"]["trainingSessionId"] == "session-1"
    assert error["payload"]["roomId"] == 42
    assert "OpenAI API key is required" in error["payload"]["message"]
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_requires_pipeline_adapter() -> None:
    app, _state = _make_bound_app()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: None
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=pipecat"
    ) as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "PIPECAT_PIPELINE_UNAVAILABLE"
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "pipeline_factory"
    assert "Pipecat realtime pipeline is not available" in error["payload"]["message"]


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
