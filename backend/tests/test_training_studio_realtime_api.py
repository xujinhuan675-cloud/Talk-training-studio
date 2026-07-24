"""API tests for Training Studio realtime WebSocket."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import training_studio as training_studio_routes
from api.routes.training_studio import (
    get_training_realtime_pipeline_factory,
    get_training_realtime_uow_factory,
    get_training_session_service,
    router,
)
from application.ports.realtime import (
    REALTIME_RUNTIME_PIPECAT,
    RealtimeAudioChunk,
    RealtimePipelineConfig,
    TrainingVoiceContext,
)
from application.services.stakeholder.sse import room_event_bus
from application.services.training_studio.session_service import TrainingSessionService
from core.config import LLMSettings, settings
from domain.stakeholder.entity import ChatRoom, Message
from domain.training_studio.session_repository import TrainingSessionAccessScope


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


def _session_scope_from_payload(payload: dict) -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id=payload.get("user_id") if isinstance(payload.get("user_id"), str) else None,
        team_id=payload.get("team_id") if isinstance(payload.get("team_id"), str) else None,
        include_team_scope=True,
    )


def _llm_settings(
    *,
    provider: str = "openai",
    base_url: str | None = None,
    default_model: str = "gpt-4o-mini",
    wire_api: str = "chat_completions",
) -> LLMSettings:
    return LLMSettings(
        provider=provider,
        api_key="sk-test-llm",
        base_url=base_url,
        wire_api=wire_api,
        default_model=default_model,
    )


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


def _make_bound_app(
    *,
    active: bool = True,
    session_payload: dict | None = None,
) -> tuple[FastAPI, _RealtimeRoomState]:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    resolved_payload = session_payload or _session_payload(
        user_id="user-admin-001",
        team_id="team-ops",
    )
    session = asyncio.run(session_service.create_session(resolved_payload))
    if active:
        asyncio.run(
            session_service.start_session(
                session.session_id,
                room_id="42",
                access_scope=_session_scope_from_payload(resolved_payload),
            )
        )
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
            "turnDetectionAvailable": bool(getattr(capability, "turn_detection_available", False)),
            "missingModules": [str(module) for module in capability.missing_modules],
            "optionalMissingModules": [
                str(module) for module in getattr(capability, "optional_missing_modules", ())
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
        smoke = pipecat_adapter.pipecat_realtime_smoke_contract(
            ready_for_call=readiness["ready"],
            require_websocket=require_websocket,
        )
        data["smoke"] = smoke
        production_readiness = smoke["productionReadiness"]
        if isinstance(production_readiness, Mapping):
            data["productionReady"] = bool(production_readiness["readyForProduction"])
            data["productionReadiness"] = dict(production_readiness)
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


def test_realtime_capabilities_reports_available_pipecat_only(monkeypatch) -> None:
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
        "build_pipecat_realtime_capability_response",
        adapter.pipecat_realtime_capability_response,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", "sk-realtime-capability")
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "REALTIME_OPENAI_MODEL", "gpt-realtime-test")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "marin-test")
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "openaiRealtime" not in data
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
    assert data["pipecat"]["productionReady"] is False
    profiles = data["pipecat"]["profiles"]
    assert profiles["default"] == "cascade"
    assert profiles["cascade"]["contract"]["latencyProfile"] == "near_realtime"
    assert profiles["cascade"]["audioContract"]["input"]["sampleRate"] == 16000
    assert profiles["speech_to_speech"]["contract"]["latencyProfile"] == "true_realtime"
    assert profiles["speech_to_speech"]["audioContract"]["input"]["sampleRate"] == 24000
    assert profiles["speech_to_speech"]["contract"]["turnDetection"]["provider"] == (
        "openai_realtime"
    )
    assert data["pipecat"]["productionReadiness"]["status"] == ("browser_e2e_verification_required")
    assert data["pipecat"]["productionReadiness"]["blockingReasons"][0]["code"] == (
        "BROWSER_AUDIO_E2E_NOT_VERIFIED"
    )
    assert data["pipecat"]["smoke"]["verificationLevel"] == "dependency_and_event_contract"
    assert data["pipecat"]["smoke"]["localRuntimeReady"] is True
    assert data["pipecat"]["smoke"]["browserE2EVerified"] is False
    assert data["pipecat"]["smoke"]["productionReady"] is False
    assert data["pipecat"]["smoke"]["productionReadiness"]["status"] == (
        "browser_e2e_verification_required"
    )
    assert data["pipecat"]["smoke"]["requiresExplicitMediaPermission"] is True
    assert data["pipecat"]["smoke"]["transport"] == "websocket"
    assert data["pipecat"]["smoke"]["inputAudioFormat"] == "pcm16"
    assert data["pipecat"]["smoke"]["defaultInputSampleRate"] == 16000
    assert {
        "session.started",
        "audio.input",
        "audio.output",
        "transcript.done",
        "transcript.persisted",
        "training.live_guidance.triggered",
        "user_turn.started",
        "user_turn.stopped",
        "assistant_speaking.started",
        "assistant_speaking.stopped",
        "interrupted",
        "silence_timeout",
    }.issubset(set(data["pipecat"]["smoke"]["contractEvents"]))
    assert {
        "status.changed",
        "session.configured",
        "session.closed",
        "error",
    }.issubset(set(data["pipecat"]["smoke"]["contractEvents"]))
    assert data["pipecat"]["smoke"]["eventOrder"]["finalTranscript"] == [
        "transcript.done",
        "transcript.persisted",
        "training.live_guidance.triggered",
    ]
    assert (
        data["pipecat"]["smoke"]["contractCoverage"]["providerNeutralAudioOutput"]["eventType"]
        == "audio.output"
    )
    assert data["pipecat"]["smoke"]["contractCoverage"]["browserAudioE2E"]["verified"] is False
    assert data["pipecat"]["smoke"]["contractCoverage"]["metrics"]["metadataKey"] == (
        "realtimeMetrics"
    )
    assert data["pipecat"]["smoke"]["errorTaxonomy"][0] == {
        "code": "REALTIME_PROVIDER_AUTHENTICATION",
        "errorCategory": "authentication",
        "retryable": False,
        "fatal": True,
    }
    assert data["pipecat"]["smoke"]["readinessAssertions"] == {
        "readyForCallImpliesLocalRuntimeReady": True,
        "browserE2EVerified": False,
        "requiresExplicitMediaPermission": True,
    }
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
        "build_pipecat_realtime_capability_response",
        adapter.pipecat_realtime_capability_response,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "api_key", "sk-llm-fallback")
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    data = response.json()["data"]
    assert "openaiRealtime" not in data
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
    assert data["pipecat"]["smoke"]["localRuntimeReady"] is False
    assert data["pipecat"]["smoke"]["browserE2EVerified"] is False
    assert data["pipecat"]["readiness"]["ready"] is False
    assert data["pipecat"]["readiness"]["status"] == "blocked"
    assert data["pipecat"]["errors"][0]["code"] == "PIPECAT_MODULE_UNAVAILABLE"
    assert data["pipecat"]["errors"][0]["phase"] == "capability_check"
    assert data["pipecat"]["errors"][0]["modules"] == [
        "pipecat.pipeline.pipeline",
        "pipecat.frames.frames",
    ]
    assert adapter.calls["require_websocket"] is True


def test_realtime_capabilities_reports_pipecat_helper_failure(monkeypatch) -> None:
    def _raise_helper_failure(**_kwargs):
        raise RuntimeError("Pipecat capability crashed")

    monkeypatch.setattr(
        training_studio_routes,
        "build_pipecat_realtime_capability_response",
        _raise_helper_failure,
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
    assert data["missingModules"] == []
    assert data["error"] == "Pipecat capability check failed: Pipecat capability crashed"
    assert data["readyForCall"] is False
    assert data["smoke"]["localRuntimeReady"] is False
    assert data["smoke"]["browserE2EVerified"] is False
    assert data["smoke"]["contractEvents"]
    assert data["errors"][0]["code"] == "PIPECAT_CAPABILITY_ERROR"
    assert data["errors"][0]["phase"] == "capability_check"


def test_realtime_capabilities_reports_pipecat_capability_exception(monkeypatch) -> None:
    def _raise_capability_failure(**_kwargs):
        raise RuntimeError("Pipecat capability crashed")

    monkeypatch.setattr(
        training_studio_routes,
        "build_pipecat_realtime_capability_response",
        _raise_capability_failure,
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
    assert data["smoke"]["localRuntimeReady"] is False
    assert data["smoke"]["browserE2EVerified"] is False
    assert data["errors"][0]["code"] == "PIPECAT_CAPABILITY_ERROR"
    assert data["errors"][0]["phase"] == "capability_check"


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
        "build_pipecat_realtime_capability_response",
        adapter.pipecat_realtime_capability_response,
    )
    monkeypatch.setattr(settings, "REALTIME_OPENAI_API_KEY", None)
    monkeypatch.setattr(settings.llm, "api_key", None)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)
    client = TestClient(_make_realtime_capability_app())

    response = client.get("/api/v1/training-studio/realtime/capabilities")

    assert response.status_code == 200
    payload = response.json()["data"]
    data = payload["pipecat"]
    assert "openaiRealtime" not in payload
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


def test_realtime_sdp_proxy_route_is_removed() -> None:
    app, state = _make_bound_app()
    client = TestClient(app)

    response = client.post(
        "/api/v1/training-studio/realtime/sdp?session_id=session-1&room_id=42",
        content="v=0\r\ns=Local browser offer\r\n",
        headers={"content-type": "application/sdp"},
    )

    assert response.status_code == 404
    assert state.messages == []


def test_realtime_transcript_persistence_endpoint_is_removed() -> None:
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

    assert response.status_code == 404
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


def test_realtime_websocket_defaults_to_pipecat_and_requires_binding_before_audio() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)

    with client.websocket_connect("/api/v1/training-studio/realtime") as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["type"] == "session.started"
        assert started["payload"]["provider"] == "pipecat"
        assert started["payload"]["realtimeRuntime"] == REALTIME_RUNTIME_PIPECAT
        assert listening["status"] == "listening"

        ws.send_json({"type": "audio.input", "audio": "", "mimeType": "audio/webm"})
        error = ws.receive_json()
        assert error["type"] == "error"
        assert error["payload"]["code"] == "BINDING_ERROR"
        assert "must be bound before audio input" in error["payload"]["message"]


def test_realtime_websocket_query_binding_persists_final_transcript() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": " We can start with a low-risk pilot. ",
            "source": "pipecat",
        }
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
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

            ws.send_json({"type": "audio.commit"})
            committed = ws.receive_json()
            events = [ws.receive_json() for _ in range(4)]
            transcript_done = next(event for event in events if event["type"] == "transcript.done")
            persisted = next(event for event in events if event["type"] == "transcript.persisted")
            guidance_trigger = next(
                event for event in events if event["type"] == "training.live_guidance.triggered"
            )
            assert committed["status"] == "processing"
            assert transcript_done["type"] == "transcript.done"
            assert persisted["type"] == "transcript.persisted"
            assert guidance_trigger["payload"]["reason"] == "final_transcript"
            assert any(event["status"] == "listening" for event in events if "status" in event)
            assert (
                persisted["payload"]["message"]["content"] == "We can start with a low-risk pilot."
            )

            assert len(state.messages) == 1
            assert state.messages[0].sender_type == "user"
            assert state.messages[0].sender_id == "user"
            assert state.messages[0].metadata["source"] == "pipecat"
            assert state.messages[0].metadata["trainingMode"] == "voice"
            assert state.messages[0].metadata["interactionMode"] == "realtime"
            assert state.messages[0].metadata["realtime"]["trainingSessionId"] == "session-1"

            event, data = queue.get_nowait()
            assert event == "message"
            assert data["content"] == "We can start with a low-risk pilot."
            assert data["metadata"]["source"] == "pipecat"
            assert data["metadata"]["trainingMode"] == "voice"
            assert data["metadata"]["interactionMode"] == "realtime"
    finally:
        room_event_bus.unsubscribe(42, queue)
    assert adapter.closed is True


def test_realtime_websocket_rejects_client_transcript_events() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42"
    ) as ws:
        ws.receive_json()
        ws.receive_json()

        ws.send_json({"type": "transcript.done", "text": "Client should not persist this."})
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "UNSUPPORTED_EVENT"
    assert "Pipecat realtime pipeline" in error["payload"]["message"]
    assert state.messages == []
    assert adapter.closed is True


def test_realtime_websocket_configure_binding_persists_final_transcript() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "transcript.done",
            "text": "Configured binding path.",
            "metadata": {
                "trainingProfile": "live_coach",
                "sourceLanguage": "ja",
                "targetLanguage": "en-US",
                "translationIntent": "text_first_mvp",
                "source": "pipecat",
            },
        }
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
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

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        events = [ws.receive_json() for _ in range(4)]
        transcript_done = next(event for event in events if event["type"] == "transcript.done")
        persisted = next(event for event in events if event["type"] == "transcript.persisted")
        assert committed["status"] == "processing"
        assert transcript_done["type"] == "transcript.done"
        assert persisted["type"] == "transcript.persisted"
        assert persisted["payload"]["message"]["content"] == "Configured binding path."

    assert [message.content for message in state.messages] == ["Configured binding path."]
    assert state.messages[0].metadata["realtime"]["eventType"] == "transcript.done"
    assert state.messages[0].metadata["trainingProfile"] == "live_coach"
    assert state.messages[0].metadata["sourceLanguage"] == "ja"
    assert state.messages[0].metadata["targetLanguage"] == "en-US"
    assert state.messages[0].metadata["realtime"]["translationIntent"] == "text_first_mvp"
    assert adapter.closed is True


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


def test_realtime_websocket_pipecat_provider_uses_openrouter_llm_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        _llm_settings(
            provider="openrouter",
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
            wire_api="responses",
        ),
    )
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
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

        ws.send_json({"type": "session.close", "reason": "openrouter-config"})
        closed = ws.receive_json()
        assert closed["type"] == "session.closed"

    assert adapter.started_config is not None
    assert adapter.started_config.provider == "pipecat"
    assert adapter.started_config.runtime == REALTIME_RUNTIME_PIPECAT
    assert adapter.started_config.metadata["stt"]["provider"] == "openai"
    assert adapter.started_config.metadata["tts"] == {"provider": "openai"}
    assert adapter.started_config.metadata["llm"] == {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "baseUrl": "https://openrouter.ai/api/v1",
    }
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_speech_to_speech_profile_metadata() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime"
        "?session_id=session-1&room_id=42&provider=pipecat&profile=speech_to_speech"
    ) as ws:
        started = ws.receive_json()
        listening = ws.receive_json()
        assert started["payload"]["realtimeProfile"] == "speech_to_speech"
        assert started["payload"]["inputSampleRate"] == 24000
        assert started["payload"]["audioContract"]["input"]["sampleRate"] == 24000
        assert started["payload"]["profileContract"]["latencyProfile"] == "true_realtime"
        assert listening["status"] == "listening"
        ws.send_bytes(b"\x01\x02")
        audio_event = ws.receive_json()
        assert audio_event["type"] == "audio.input"
        ws.send_json({"type": "session.close", "reason": "done"})
        assert ws.receive_json()["type"] == "session.closed"

    assert adapter.started_context is not None
    assert adapter.started_context.metadata["realtimeProfile"] == "speech_to_speech"
    assert adapter.started_config is not None
    metadata = adapter.started_config.metadata
    assert metadata["profile"] == "speech_to_speech"
    assert metadata["realtimeProfile"] == "speech_to_speech"
    assert metadata["inputSampleRate"] == 24000
    assert metadata["outputSampleRate"] == 24000
    assert "stt" not in metadata
    assert "tts" not in metadata
    assert "llm" not in metadata
    assert "vad" not in metadata
    assert metadata["context"] == {"provider": "pipecat", "realtimeServiceMode": True}
    assert metadata["turnDetection"] == {
        "provider": "openai",
        "source": "openai_realtime",
        "mode": "semantic_vad",
    }
    realtime_llm = metadata["realtimeLlm"]
    assert isinstance(realtime_llm, dict)
    assert realtime_llm["provider"] == "openai"
    assert realtime_llm["model"] == settings.REALTIME_OPENAI_MODEL
    assert realtime_llm["voice"] == settings.REALTIME_OPENAI_VOICE
    assert realtime_llm["outputModalities"] == ["audio"]
    assert metadata["profileContract"]["latencyProfile"] == "true_realtime"
    assert metadata["audioContract"]["input"]["sampleRate"] == 24000
    assert adapter.audio_chunks[0].metadata["realtimeProfile"] == "speech_to_speech"
    assert adapter.audio_chunks[0].metadata["sampleRate"] == 24000


def test_pipecat_realtime_llm_provider_detects_openrouter_compatible_base_url(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "llm",
        _llm_settings(
            provider="openai",
            base_url="https://openrouter.ai/api/v1",
            default_model="openai/gpt-4o-mini",
        ),
    )

    assert training_studio_routes._pipecat_realtime_llm_provider() == "openrouter"


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
    assert [(turn["speaker"], turn["text"]) for turn in adapter.started_context.recent_turns] == [
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


def test_realtime_websocket_rejects_openai_provider() -> None:
    app, state = _make_bound_app()
    client = TestClient(app)

    with client.websocket_connect(
        "/api/v1/training-studio/realtime?session_id=session-1&room_id=42&provider=openai"
    ) as ws:
        error = ws.receive_json()

    assert error["type"] == "error"
    assert error["payload"]["code"] == "UNSUPPORTED_REALTIME_PROVIDER"
    assert error["payload"]["phase"] == "provider"
    assert error["payload"]["provider"] == "openai"
    assert "Pipecat only" in error["payload"]["message"]
    assert state.messages == []


def test_realtime_websocket_pipecat_provider_persists_provider_neutral_assistant_turn() -> None:
    app, state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "response.audio_transcript.done",
            "text": "That works if we define the pilot metric first.",
            "response_id": "response_pipecat_1",
            "source": "pipecat",
        }
    )
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

        ws.send_json({"type": "audio.commit"})
        committed = ws.receive_json()
        events = [ws.receive_json() for _ in range(4)]
        transcript_done = next(event for event in events if event["type"] == "transcript.done")
        persisted = next(event for event in events if event["type"] == "transcript.persisted")

    assert committed["status"] == "processing"
    assert transcript_done["type"] == "transcript.done"
    assert transcript_done["payload"] == {
        "text": "That works if we define the pilot metric first.",
        "role": "assistant",
        "eventType": "response.audio_transcript.done",
        "runtime": REALTIME_RUNTIME_PIPECAT,
        "provider": "pipecat",
        "trainingSessionId": "session-1",
        "roomId": 42,
        "realtimeSessionId": "session-1",
        "responseId": "response_pipecat_1",
    }
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


def test_realtime_websocket_pipecat_provider_relays_audio_output_and_persists_final_transcript() -> (
    None
):
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
        events = [ws.receive_json() for _ in range(5)]

        assert committed["status"] == "processing"
        audio_output = next(event for event in events if event["type"] == "audio.output")
        transcript_done = next(event for event in events if event["type"] == "transcript.done")
        persisted = next(event for event in events if event["type"] == "transcript.persisted")
        guidance_trigger = next(
            event for event in events if event["type"] == "training.live_guidance.triggered"
        )
        event_types = [event["type"] for event in events]
        assert event_types.index("audio.output") < event_types.index("transcript.done")
        assert event_types.index("transcript.done") < event_types.index("transcript.persisted")
        assert event_types.index("transcript.persisted") < event_types.index(
            "training.live_guidance.triggered"
        )
        assert any(
            event["type"] == "status.changed" and event["status"] == "listening" for event in events
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
        assert transcript_done["payload"] == {
            "text": "Let's define the pilot metric before we begin.",
            "role": "assistant",
            "eventType": "response.audio_transcript.done",
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "provider": "pipecat",
            "trainingSessionId": "session-1",
            "roomId": 42,
            "realtimeSessionId": "session-1",
            "responseId": "response_pipecat_2",
        }
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


def test_realtime_websocket_relays_pipecat_turn_events() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "user_turn.stopped",
            "runtime": REALTIME_RUNTIME_PIPECAT,
            "provider": "pipecat",
            "source": "pipecat",
            "participant": "user",
            "state": "stopped",
            "payload": {
                "signal": "vad",
                "silenceSeconds": 0.8,
                "secret": "sk-should-not-leak",
            },
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
        events = [ws.receive_json() for _ in range(2)]

    turn_event = next(event for event in events if event["type"] == "user_turn.stopped")
    assert committed["status"] == "processing"
    assert turn_event["status"] == "processing"
    assert turn_event["payload"]["runtime"] == REALTIME_RUNTIME_PIPECAT
    assert turn_event["payload"]["provider"] == "pipecat"
    assert turn_event["payload"]["participant"] == "user"
    assert turn_event["payload"]["state"] == "stopped"
    assert turn_event["payload"]["payload"] == {"signal": "vad", "silenceSeconds": 0.8}


def test_realtime_websocket_pipecat_provider_forwards_audio_to_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm", _llm_settings())
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
    assert len(adapter.audio_chunks) == 1
    audio_chunk = adapter.audio_chunks[0]
    assert audio_chunk.data == audio
    assert audio_chunk.mime_type == "audio/pcm"
    assert audio_chunk.sequence == 1
    assert audio_chunk.metadata["realtimeProfile"] == "cascade"
    assert audio_chunk.metadata["sampleRate"] == 16000
    assert audio_chunk.metadata["audioContract"]["input"]["sampleRate"] == 16000
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

    assert len(adapter.audio_chunks) == 1
    audio_chunk = adapter.audio_chunks[0]
    assert audio_chunk.data == audio
    assert audio_chunk.mime_type == "audio/pcm"
    assert audio_chunk.sequence == 1
    assert audio_chunk.metadata["realtimeProfile"] == "cascade"
    assert audio_chunk.metadata["sampleRate"] == 16000
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
    assert error["payload"]["code"] == "REALTIME_PROVIDER_UNAVAILABLE"
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "provider_event"
    assert error["payload"]["eventType"] == "pipeline.error"
    assert error["payload"]["errorCategory"] == "provider_unavailable"
    assert error["payload"]["retryable"] is True
    assert error["payload"]["fatal"] is True
    assert error["payload"]["trainingSessionId"] == "session-1"
    assert error["payload"]["roomId"] == 42
    assert "Pipecat provider disconnected" in error["payload"]["message"]
    assert adapter.closed is True


def test_realtime_websocket_pipecat_provider_forwards_nonfatal_provider_error() -> None:
    app, _state = _make_bound_app()
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "error",
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Provider rate limit exceeded",
                "status": 429,
            },
            "metadata": {"requestId": "req-rate-limit", "apiKey": "sk-should-not-leak"},
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
        listening = ws.receive_json()

        ws.send_json({"type": "session.close", "reason": "nonfatal-error"})
        closed = ws.receive_json()

    assert committed["status"] == "processing"
    assert error["type"] == "error"
    assert error["status"] == "processing"
    assert error["payload"]["code"] == "REALTIME_PROVIDER_RATE_LIMIT"
    assert error["payload"]["sourceCode"] == "rate_limit_exceeded"
    assert error["payload"]["errorCategory"] == "rate_limit"
    assert error["payload"]["retryable"] is True
    assert error["payload"]["fatal"] is False
    assert error["payload"]["provider"] == "pipecat"
    assert error["payload"]["phase"] == "provider_event"
    assert error["payload"]["metadata"] == {"requestId": "req-rate-limit", "statusCode": 429}
    assert "sk-should-not-leak" not in str(error)
    assert listening["type"] == "status.changed"
    assert listening["status"] == "listening"
    assert closed["type"] == "session.closed"
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
    adapter = _FakeRealtimePipelineAdapter()
    adapter.events_on_commit.append(
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "The demo voice turn is now persisted.",
            "source": "pipecat",
        }
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda _provider: adapter
    )
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
            ws.send_json({"type": "audio.commit"})
            committed = ws.receive_json()
            events = [ws.receive_json() for _ in range(4)]
            transcript_done = next(event for event in events if event["type"] == "transcript.done")
            persisted = next(event for event in events if event["type"] == "transcript.persisted")
            assert committed["status"] == "processing"
            assert transcript_done["type"] == "transcript.done"
            assert persisted["type"] == "transcript.persisted"

        assert [message.content for message in state.messages] == [
            "The demo voice turn is now persisted."
        ]
        event, data = queue.get_nowait()
        assert event == "message"
        assert data["content"] == "The demo voice turn is now persisted."
        assert data["metadata"]["source"] == "pipecat"
        assert data["metadata"]["trainingMode"] == "voice"
        assert data["metadata"]["interactionMode"] == "realtime"
        assert adapter.closed is True
    finally:
        room_event_bus.unsubscribe(42, queue)
