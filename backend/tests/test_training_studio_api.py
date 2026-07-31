"""API tests for Training Studio catalog and storybank endpoints."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from itertools import count
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_growth_service,
    get_persona_editor_service,
    reset_ai_rate_limit_state,
)
import api.routes.training_studio as training_studio_routes
from api.routes.training_studio import (
    get_live_guidance_service,
    get_training_realtime_pipeline_factory,
    get_training_realtime_uow_factory,
    get_training_runtime_uow_factory,
    get_training_scenario_config_service,
    get_storybank_service,
    get_training_session_service,
    router,
)
from application.services.stakeholder.dto import ChatRoomDTO, ChatRoomDetailDTO, MessageDTO
from application.services.training_studio.live_guidance_service import TrainingLiveGuidanceService
from application.services.training_studio.scenario_config_service import (
    JsonFileScenarioConfigStore,
    TrainingScenarioConfigService,
)
from application.services.training_studio.session_service import TrainingSessionService
from core.config import LLMSettings, VoiceSettings, settings
from core.exceptions import register_exception_handlers
from domain.training_studio.session_repository import TrainingSessionAccessScope
from domain.training_studio.storybank import StoryBankService


class FakeReport(BaseModel):
    id: int
    room_id: int
    summary: str = "Good practice report"
    content: dict = Field(default_factory=dict)


class FakeAnalysisService:
    def __init__(self) -> None:
        self.generated_for: list[int] = []
        self.generated_scopes: list[object] = []

    async def generate_report(self, room_id: int, *, access_scope) -> FakeReport:
        self.generated_for.append(room_id)
        self.generated_scopes.append(access_scope)
        return FakeReport(id=501, room_id=room_id)


class FakeAnalysisReaderService:
    def __init__(self) -> None:
        self.reports: dict[int, FakeReport] = {}
        self.requested_ids: list[int] = []
        self.requested_scopes: list[object] = []

    async def get_report(self, report_id: int, *, room_id: int, access_scope) -> FakeReport | None:
        self.requested_ids.append(report_id)
        self.requested_scopes.append(access_scope)
        return self.reports.get(report_id)


class FakeGrowthService:
    def __init__(self) -> None:
        self.evaluated: list[int] = []

    async def evaluate_competency(self, report_id: int) -> None:
        self.evaluated.append(report_id)


class FakeChatroomService:
    def __init__(self, runtime_state=None) -> None:
        self._runtime_state = runtime_state
        self.created_rooms: list[object] = []
        self.create_scopes: list[object] = []
        self.details: dict[int, ChatRoomDetailDTO] = {}
        self.detail_calls: list[tuple[int, int]] = []
        self.detail_scopes: list[object] = []

    async def create_room(self, dto, *, access_scope=None):
        self.created_rooms.append(dto)
        self.create_scopes.append(access_scope)
        room = SimpleNamespace(
            id=701,
            name=dto.name,
            type=dto.type,
            persona_ids=list(dto.persona_ids),
            scenario_id=dto.scenario_id,
        )
        if self._runtime_state is not None:
            self._runtime_state.rooms[room.id] = room
        return room

    async def get_room_detail(
        self,
        room_id: int,
        *,
        message_limit: int = 50,
        access_scope=None,
    ) -> ChatRoomDetailDTO:
        self.detail_calls.append((room_id, message_limit))
        self.detail_scopes.append(access_scope)
        return self.details[room_id]


class FakePersonaEditor:
    def __init__(self) -> None:
        self.created_personas: list[object] = []

    def create_persona(self, dto) -> None:
        self.created_personas.append(dto)


class FakeTrainingRuntimeConversationRepository:
    def __init__(self, state) -> None:
        self._state = state

    async def create(self, conversation):
        saved = SimpleNamespace(
            id=len(self._state.created_conversations) + 1,
            title=conversation.title,
            system_prompt=conversation.system_prompt,
            model=conversation.model,
            metadata=dict(conversation.metadata),
        )
        self._state.created_conversations.append(saved)
        return saved


class FakeTrainingRuntimeChatRoomRepository:
    def __init__(self, state) -> None:
        self._state = state

    async def get_by_id(self, room_id: int):
        return self._state.rooms.get(room_id)

    async def update_last_message_at(self, room_id: int, timestamp) -> None:
        self._state.last_message_updates.append((room_id, timestamp))


class FakeTrainingRuntimeMessageRepository:
    def __init__(self, state) -> None:
        self._state = state

    async def create(self, message):
        saved = SimpleNamespace(
            id=len(self._state.messages) + 1,
            room_id=message.room_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            content=message.content,
            timestamp=message.timestamp,
            emotion_score=message.emotion_score,
            emotion_label=message.emotion_label,
            metadata=dict(message.metadata),
        )
        self._state.messages.append(saved)
        return saved

    async def list_by_room_id(
        self, room_id: int, *, skip: int = 0, limit: int = 50
    ) -> list[SimpleNamespace]:
        messages = [message for message in self._state.messages if message.room_id == room_id]
        return messages[skip : skip + limit]

    async def count_by_room_id(self, room_id: int) -> int:
        return sum(1 for message in self._state.messages if message.room_id == room_id)


class FakeTrainingRuntimeUnitOfWork:
    def __init__(self, state, **kwargs) -> None:
        self._state = state
        self._kwargs = kwargs
        self.conversation_repository = FakeTrainingRuntimeConversationRepository(state)
        self.chat_room_repository = FakeTrainingRuntimeChatRoomRepository(state)
        self.stakeholder_message_repository = FakeTrainingRuntimeMessageRepository(state)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.fixture
def app(tmp_path):
    reset_ai_rate_limit_state()
    test_app = FastAPI()
    register_exception_handlers(test_app)
    test_app.include_router(router, prefix="/api/v1")
    storybank = StoryBankService()
    scenario_config_service = TrainingScenarioConfigService(
        JsonFileScenarioConfigStore(tmp_path / "scenario_config.json")
    )
    session_ids = count(1)
    session_service = TrainingSessionService(id_factory=lambda: f"session-{next(session_ids)}")
    runtime_state = SimpleNamespace(
        created_conversations=[],
        rooms={},
        messages=[],
        last_message_updates=[],
    )
    analysis_service = FakeAnalysisService()
    reader_service = FakeAnalysisReaderService()
    growth_service = FakeGrowthService()
    chatroom_service = FakeChatroomService(runtime_state)
    persona_editor = FakePersonaEditor()
    guidance_service = TrainingLiveGuidanceService(monologue_word_threshold=20)
    test_app.dependency_overrides[get_training_runtime_uow_factory] = (
        lambda: (lambda **kwargs: FakeTrainingRuntimeUnitOfWork(runtime_state, **kwargs))
    )
    test_app.dependency_overrides[get_storybank_service] = lambda: storybank
    test_app.dependency_overrides[get_training_scenario_config_service] = lambda: scenario_config_service
    test_app.dependency_overrides[get_training_session_service] = lambda: session_service
    test_app.dependency_overrides[get_live_guidance_service] = lambda: guidance_service
    test_app.dependency_overrides[get_analysis_service] = lambda: analysis_service
    test_app.dependency_overrides[get_analysis_reader_service] = lambda: reader_service
    test_app.dependency_overrides[get_growth_service] = lambda: growth_service
    test_app.dependency_overrides[get_chatroom_service] = lambda: chatroom_service
    test_app.dependency_overrides[get_persona_editor_service] = lambda: persona_editor
    test_app.state.scenario_config_service = scenario_config_service
    test_app.state.training_session_service = session_service
    test_app.state.guidance_service = guidance_service
    test_app.state.analysis_service = analysis_service
    test_app.state.analysis_reader_service = reader_service
    test_app.state.growth_service = growth_service
    test_app.state.chatroom_service = chatroom_service
    test_app.state.persona_editor = persona_editor
    test_app.state.training_runtime_state = runtime_state
    return test_app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_catalog_exposes_training_dimensions(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/training-studio/catalog")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert {item["value"] for item in data["categories"]} == {
        "interview",
        "sales",
        "negotiation",
        "workplace",
        "product_management",
    }
    assert {item["value"] for item in data["frameworks"]} == {"prep", "star", "scqa", "pyramid"}
    assert "interview-five-dimension-v1" in data["rubric_versions"]
    assert any(item["value"] == "core_pm" for item in data["role_presets"])
    assert any(item["value"] == "hiring_manager" for item in data["role_presets"])
    assert any(item["value"] == "prd_review" for item in data["scenario_presets"])
    assert any(item["value"] == "product_sense_case" for item in data["scenario_presets"])


@pytest.mark.asyncio
async def test_scenario_templates_expose_business_training_cards(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/training-studio/scenario-templates")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 6

    by_id = {item["id"]: item for item in data}
    assert {
        "daily-upward-results-report",
        "budget-freeze-expansion",
        "cross-team-roadmap-tradeoff",
        "project-scope-creep-boundary",
        "service-apology-retention",
    }.issubset(by_id)
    new_customer = by_id["new-customer-discount"]
    assert new_customer["title"]
    assert new_customer["category"] == "sales"
    assert new_customer["difficulty"] == "easy"
    assert new_customer["required"] is True
    assert new_customer["status"] == "not_started"
    assert new_customer["opening_line"]
    assert new_customer["persona"]["name"]
    assert len(new_customer["training_points"]) >= 1
    assert sum(item["weight"] for item in new_customer["dimension_weights"]) == pytest.approx(100)

    assert any(item["category"] == "customer_service" for item in data)
    assert by_id["renewal-price-negotiation"]["difficulty"] == "expert"


async def read_scenario_config_state(client: AsyncClient, headers: dict | None = None) -> dict:
    resp = await client.get("/api/v1/training-studio/scenario-config", headers=headers)
    assert resp.status_code == 200
    return resp.json()["data"]


def scenario_dimension_weights() -> list[dict]:
    return [
        {"dimensionId": "substance", "weight": 40},
        {"dimensionId": "structure", "weight": 20},
        {"dimensionId": "relevance", "weight": 20},
        {"dimensionId": "credibility", "weight": 10},
        {"dimensionId": "differentiation", "weight": 10},
    ]


@pytest.mark.asyncio
async def test_scenario_config_reads_default_state(client: AsyncClient) -> None:
    data = await read_scenario_config_state(client, headers={"X-Mock-User": "sales"})

    assert data["version"] == 1
    assert len(data["dimensions"]) >= 5
    assert {item["id"] for item in data["dimensions"]} >= {
        "substance",
        "structure",
        "relevance",
        "credibility",
        "differentiation",
    }
    by_id = {item["id"]: item for item in data["scenarios"]}
    assert "new-customer-discount" in by_id
    assert by_id["new-customer-discount"]["sourceScenarioId"] == "new-customer-discount"
    assert sum(item["weight"] for item in by_id["new-customer-discount"]["dimensionWeights"]) == pytest.approx(100)


@pytest.mark.asyncio
async def test_scenario_config_only_admin_can_save(client: AsyncClient) -> None:
    payload = await read_scenario_config_state(client)
    payload["scenarios"][0]["dimensionWeights"] = scenario_dimension_weights()

    admin_response = await client.put(
        "/api/v1/training-studio/scenario-config",
        headers={"X-Mock-User": "admin"},
        json=payload,
    )

    assert admin_response.status_code == 200
    assert admin_response.json()["data"]["scenarios"][0]["dimensionWeights"] == scenario_dimension_weights()

    leader_response = await client.put(
        "/api/v1/training-studio/scenario-config",
        headers={"X-Mock-User": "leader"},
        json=payload,
    )

    assert leader_response.status_code == 403


@pytest.mark.asyncio
async def test_scenario_config_staff_cannot_save(client: AsyncClient) -> None:
    payload = await read_scenario_config_state(client)

    resp = await client.put(
        "/api/v1/training-studio/scenario-config",
        headers={"X-Mock-User": "sales"},
        json=payload,
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_scenario_config_persists_dimension_weights(client: AsyncClient) -> None:
    payload = await read_scenario_config_state(client)
    scenario_id = payload["scenarios"][0]["id"]
    payload["scenarios"][0]["dimensionWeights"] = scenario_dimension_weights()

    save_resp = await client.put(
        "/api/v1/training-studio/scenario-config",
        headers={"X-Mock-User": "admin"},
        json=payload,
    )
    assert save_resp.status_code == 200

    data = await read_scenario_config_state(client, headers={"X-Mock-User": "leader"})
    saved = next(item for item in data["scenarios"] if item["id"] == scenario_id)
    assert saved["dimensionWeights"] == scenario_dimension_weights()


@pytest.mark.asyncio
async def test_scenario_templates_use_saved_scenario_config(client: AsyncClient) -> None:
    payload = await read_scenario_config_state(client)
    scenario_id = payload["scenarios"][0]["id"]
    disabled_id = payload["scenarios"][1]["id"]
    payload["scenarios"][0]["title"] = "Configured training template"
    payload["scenarios"][0]["required"] = False
    payload["scenarios"][0]["dimensionWeights"] = scenario_dimension_weights()
    payload["scenarios"][1]["enabled"] = False

    save_resp = await client.put(
        "/api/v1/training-studio/scenario-config",
        headers={"X-Mock-User": "admin"},
        json=payload,
    )
    assert save_resp.status_code == 200

    resp = await client.get("/api/v1/training-studio/scenario-templates")

    assert resp.status_code == 200
    data = resp.json()["data"]
    by_id = {item["id"]: item for item in data}
    assert disabled_id not in by_id
    assert by_id[scenario_id]["title"] == "Configured training template"
    assert by_id[scenario_id]["required"] is False
    assert by_id[scenario_id]["dimension_weights"] == [
        {"dimension_id": item["dimensionId"], "weight": item["weight"]}
        for item in scenario_dimension_weights()
    ]


@pytest.mark.asyncio
async def test_voice_config_save_writes_env_and_reloads_clients(
    client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\nVOICE__TTS_PROVIDER=minimax\n", encoding="utf-8")
    voice_env_keys = [
        "LLM__PROVIDER",
        "LLM__BASE_URL",
        "LLM__DEFAULT_MODEL",
        "LLM__WIRE_API",
        "LLM__API_KEY",
        "VOICE__TTS_PROVIDER",
        "VOICE__TTS_BASE_URL",
        "VOICE__TTS_MODEL",
        "VOICE__TTS_API_KEY",
        "VOICE__STT_PROVIDER",
        "VOICE__STT_BASE_URL",
        "VOICE__STT_MODEL",
        "VOICE__STT_API_KEY",
        "REALTIME_PROVIDER",
        "REALTIME_API_KEY",
        "REALTIME_BASE_URL",
        "REALTIME_OPENAI_API_KEY",
        "REALTIME_OPENAI_MODEL",
        "REALTIME_OPENAI_VOICE",
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL",
    ]
    old_env = {key: os.environ.get(key) for key in voice_env_keys}
    original_llm = settings.llm.model_copy(deep=True)
    original_voice = settings.voice.model_copy(deep=True)
    original_realtime = {
        "REALTIME_OPENAI_API_KEY": settings.REALTIME_OPENAI_API_KEY,
        "REALTIME_PROVIDER": settings.REALTIME_PROVIDER,
        "REALTIME_API_KEY": settings.REALTIME_API_KEY,
        "REALTIME_BASE_URL": settings.REALTIME_BASE_URL,
        "REALTIME_OPENAI_MODEL": settings.REALTIME_OPENAI_MODEL,
        "REALTIME_OPENAI_VOICE": settings.REALTIME_OPENAI_VOICE,
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
    }
    reloads: list[bool] = []

    async def fake_reload_voice_clients() -> None:
        reloads.append(True)

    async def fake_reload_llm_client() -> None:
        reloads.append(True)

    try:
        monkeypatch.setattr(settings, "NEWAPI_AUTH_ENABLED", False)
        monkeypatch.setattr(settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", True)
        monkeypatch.setattr(
            training_studio_routes,
            "_settings_env_file_path",
            lambda: env_file,
        )
        monkeypatch.setattr(
            training_studio_routes,
            "_reload_voice_clients",
            fake_reload_voice_clients,
        )
        monkeypatch.setattr(
            training_studio_routes,
            "_reload_llm_client",
            fake_reload_llm_client,
        )
        settings.llm.api_key = "sk-llm-old"
        settings.llm.base_url = "https://old-llm.example.com/v1"
        settings.llm.default_model = "old-model"
        settings.llm.wire_api = "chat_completions"
        settings.voice = VoiceSettings(
            tts_provider="minimax",
            tts_api_key=None,
            tts_base_url=None,
            tts_model="speech-2.8-hd",
            stt_provider="whisper",
            stt_api_key=None,
            stt_base_url=None,
            stt_model="whisper-1",
        )
        settings.REALTIME_OPENAI_API_KEY = None
        settings.REALTIME_OPENAI_MODEL = "gpt-realtime-2.1"
        settings.REALTIME_OPENAI_VOICE = "marin"
        settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

        resp = await client.put(
            "/api/v1/training-studio/voice-config",
            headers={"X-Mock-User": "admin"},
            json={
                "llm_base_url": "https://ai.flowguide.cc",
                "llm_provider": "flowguide",
                "llm_default_model": "gpt-5.5",
                "llm_wire_api": "responses",
                "llm_api_key": "sk-flowguide-9999",
                "tts_provider": "openrouter",
                "tts_base_url": "https://openrouter.ai/api/v1",
                "tts_model": "mistralai/voxtral-mini-tts-2603",
                "tts_api_key": "sk-openrouter-1234",
                "stt_provider": "whisper",
                "stt_base_url": "https://openrouter.ai/api/v1",
                "stt_model": "openai/whisper-1",
                "stt_use_tts_api_key": True,
                "realtime_provider": "openai",
                "realtime_base_url": "https://api.openai.com/v1/realtime/calls",
                "realtime_api_key": "sk-realtime-5678",
                "realtime_model": "gpt-realtime-2.1",
                "realtime_voice": "marin",
                "realtime_transcription_model": "gpt-realtime-whisper",
            },
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_provider"] == "flowguide"
        assert data["llm_base_url"] == "https://ai.flowguide.cc"
        assert data["llm_default_model"] == "gpt-5.5"
        assert data["llm_api_key_preview"] == "***9999"
        assert data["tts_provider"] == "openrouter"
        assert data["tts_api_key_preview"] == "***1234"
        assert data["stt_api_key_source"] == "tts"
        assert data["realtime_provider"] == "openai"
        assert data["realtime_base_url"] == "https://api.openai.com/v1/realtime/calls"
        assert data["realtime_api_key_preview"] == "***5678"
        assert "sk-openrouter-1234" not in resp.text
        assert "sk-realtime-5678" not in resp.text
        assert "sk-flowguide-9999" not in resp.text
        assert reloads == [True, True]

        env_text = env_file.read_text(encoding="utf-8")
        assert "LLM__PROVIDER=flowguide" in env_text
        assert "LLM__BASE_URL=https://ai.flowguide.cc" in env_text
        assert "LLM__DEFAULT_MODEL=gpt-5.5" in env_text
        assert "LLM__WIRE_API=responses" in env_text
        assert "LLM__API_KEY=sk-flowguide-9999" in env_text
        assert "VOICE__TTS_PROVIDER=openrouter" in env_text
        assert "VOICE__TTS_API_KEY=sk-openrouter-1234" in env_text
        assert "VOICE__STT_API_KEY=" in env_text
        assert "REALTIME_PROVIDER=openai" in env_text
        assert "REALTIME_BASE_URL=https://api.openai.com/v1/realtime/calls" in env_text
        assert "REALTIME_OPENAI_API_KEY=sk-realtime-5678" in env_text
        assert settings.llm.api_key == "sk-flowguide-9999"
        assert settings.llm.provider == "flowguide"
        assert settings.llm.base_url == "https://ai.flowguide.cc"
        assert settings.llm.default_model == "gpt-5.5"
        assert settings.voice.tts_provider == "openrouter"
        assert settings.voice.stt_api_key == "sk-openrouter-1234"
        assert settings.REALTIME_PROVIDER == "openai"
        assert settings.REALTIME_BASE_URL == "https://api.openai.com/v1/realtime/calls"
        assert settings.REALTIME_OPENAI_API_KEY == "sk-realtime-5678"
    finally:
        settings.llm = original_llm
        settings.voice = original_voice
        for key, value in original_realtime.items():
            setattr(settings, key, value)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.mark.asyncio
async def test_voice_config_save_accepts_volcengine_presets(
    client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\n", encoding="utf-8")
    voice_env_keys = [
        "LLM__PROVIDER",
        "LLM__BASE_URL",
        "LLM__DEFAULT_MODEL",
        "LLM__WIRE_API",
        "LLM__API_KEY",
        "VOICE__TTS_PROVIDER",
        "VOICE__TTS_BASE_URL",
        "VOICE__TTS_MODEL",
        "VOICE__TTS_API_KEY",
        "VOICE__STT_PROVIDER",
        "VOICE__STT_BASE_URL",
        "VOICE__STT_MODEL",
        "VOICE__STT_API_KEY",
        "REALTIME_PROVIDER",
        "REALTIME_API_KEY",
        "REALTIME_BASE_URL",
        "REALTIME_OPENAI_API_KEY",
        "REALTIME_OPENAI_MODEL",
        "REALTIME_OPENAI_VOICE",
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL",
    ]
    old_env = {key: os.environ.get(key) for key in voice_env_keys}
    original_llm = settings.llm.model_copy(deep=True)
    original_voice = settings.voice.model_copy(deep=True)
    original_realtime = {
        "REALTIME_OPENAI_API_KEY": settings.REALTIME_OPENAI_API_KEY,
        "REALTIME_PROVIDER": settings.REALTIME_PROVIDER,
        "REALTIME_API_KEY": settings.REALTIME_API_KEY,
        "REALTIME_BASE_URL": settings.REALTIME_BASE_URL,
        "REALTIME_OPENAI_MODEL": settings.REALTIME_OPENAI_MODEL,
        "REALTIME_OPENAI_VOICE": settings.REALTIME_OPENAI_VOICE,
        "REALTIME_OPENAI_TRANSCRIPTION_MODEL": settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL,
    }

    async def fake_reload_voice_clients() -> None:
        return None

    async def fake_reload_llm_client() -> None:
        return None

    try:
        monkeypatch.setattr(settings, "NEWAPI_AUTH_ENABLED", False)
        monkeypatch.setattr(settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", True)
        monkeypatch.setattr(
            training_studio_routes,
            "_settings_env_file_path",
            lambda: env_file,
        )
        monkeypatch.setattr(
            training_studio_routes,
            "_reload_voice_clients",
            fake_reload_voice_clients,
        )
        monkeypatch.setattr(
            training_studio_routes,
            "_reload_llm_client",
            fake_reload_llm_client,
        )
        settings.llm = LLMSettings(
            provider="openai",
            api_key="sk-old-llm",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        )
        settings.voice = VoiceSettings(
            tts_provider="minimax",
            tts_api_key=None,
            tts_base_url=None,
            tts_model="speech-2.8-hd",
            stt_provider="whisper",
            stt_api_key=None,
            stt_base_url=None,
            stt_model="whisper-1",
        )
        settings.REALTIME_OPENAI_API_KEY = None
        settings.REALTIME_API_KEY = None
        settings.REALTIME_PROVIDER = "openai"
        settings.REALTIME_BASE_URL = "https://api.openai.com/v1/realtime/calls"
        settings.REALTIME_OPENAI_MODEL = "gpt-realtime-2.1"
        settings.REALTIME_OPENAI_VOICE = "marin"
        settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

        resp = await client.put(
            "/api/v1/training-studio/voice-config",
            headers={"X-Mock-User": "admin"},
            json={
                "llm_provider": "volcengine",
                "llm_base_url": "https://ark.cn-beijing.volces.com/api/v3",
                "llm_default_model": "doubao-seed-1-6-250615",
                "llm_wire_api": "chat_completions",
                "llm_api_key": "sk-volc-ark",
                "tts_provider": "volcengine",
                "tts_base_url": "https://openspeech.bytedance.com/api/v3/tts/unidirectional",
                "tts_model": "seed-tts-2.0",
                "tts_api_key": "sk-volc-speech-tts",
                "stt_provider": "volcengine",
                "stt_base_url": "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
                "stt_model": "volc.bigasr.sauc.duration",
                "stt_api_key": "sk-volc-speech-stt",
                "realtime_provider": "volcengine.doubao_realtime",
                "realtime_base_url": (
                    "wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue"
                ),
                "realtime_api_key": "sk-volc-realtime",
                "realtime_model": "seed-duplex",
                "realtime_voice": "your-volcengine-voice",
                "realtime_transcription_model": "volcengine-realtime-transcript",
            },
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_provider"] == "volcengine"
        assert data["tts_provider"] == "volcengine"
        assert data["stt_provider"] == "volcengine"
        assert data["stt_api_key_source"] == "stt"
        assert data["realtime_provider"] == "volcengine.doubao_realtime"
        assert data["realtime_api_key_source"] == "realtime"
        assert settings.voice.stt_api_key == "sk-volc-speech-stt"
        assert settings.REALTIME_API_KEY == "sk-volc-realtime"
        assert settings.REALTIME_OPENAI_API_KEY is None

        env_text = env_file.read_text(encoding="utf-8")
        assert "LLM__PROVIDER=volcengine" in env_text
        assert "VOICE__TTS_PROVIDER=volcengine" in env_text
        assert "VOICE__STT_PROVIDER=volcengine" in env_text
        assert "REALTIME_PROVIDER=volcengine.doubao_realtime" in env_text
        assert "REALTIME_API_KEY=sk-volc-realtime" in env_text
    finally:
        settings.llm = original_llm
        settings.voice = original_voice
        for key, value in original_realtime.items():
            setattr(settings, key, value)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_voice_config_reports_openrouter_tts_reusing_openrouter_llm_key() -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-openrouter-reused",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="openrouter",
        tts_api_key=None,
        tts_base_url="https://openrouter.ai/api/v1",
        tts_model="mistralai/voxtral-mini-tts-2603",
        stt_provider="whisper",
        stt_api_key=None,
        stt_base_url="https://openrouter.ai/api/v1",
        stt_model="openai/whisper-1",
    )

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.tts_api_key_configured is True
        assert dto.tts_api_key_preview == "***used"
        assert dto.stt_api_key_source == "llm"
    finally:
        settings.llm = original_llm
        settings.voice = original_voice


def test_voice_config_reports_tts_runtime_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    import infrastructure.external.voice as voice_module

    monkeypatch.setattr(voice_module, "get_tts_client", lambda: None)
    original_llm = settings.llm
    original_voice = settings.voice
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-openrouter-reused",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="openrouter",
        tts_api_key=None,
        tts_base_url="https://openrouter.ai/api/v1",
        tts_model="mistralai/voxtral-mini-tts-2603",
        stt_provider="whisper",
        stt_api_key=None,
        stt_base_url="https://openrouter.ai/api/v1",
        stt_model="openai/whisper-1",
    )

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.tts_api_key_configured is True
        assert dto.tts_runtime_available is False
        assert dto.tts_runtime_status == "not_initialized"
        assert "TTS client" in dto.tts_runtime_message
    finally:
        settings.llm = original_llm
        settings.voice = original_voice


def test_voice_config_does_not_reuse_llm_key_for_inventory_stt_provider() -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-llm-shared",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="openrouter",
        tts_api_key=None,
        tts_base_url="https://openrouter.ai/api/v1",
        tts_model="mistralai/voxtral-mini-tts-2603",
        stt_provider="deepgram",
        stt_api_key=None,
        stt_base_url="https://api.deepgram.com/v1",
        stt_model="nova-3",
    )

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.stt_provider == "deepgram"
        assert dto.stt_api_key_configured is False
        assert dto.stt_api_key_source == "missing"
        assert dto.stt_use_tts_api_key is False
    finally:
        settings.llm = original_llm
        settings.voice = original_voice


def test_voice_config_reports_volcengine_dedicated_stt_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    monkeypatch.delenv("VOICE__STT_API_KEY", raising=False)
    monkeypatch.setattr(training_studio_routes, "_read_env_file_values", lambda path=None: {})
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-llm-shared",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="volcengine",
        tts_api_key="sk-volc-tts",
        tts_base_url="https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        tts_model="seed-tts-2.0",
        stt_provider="volcengine",
        stt_api_key="sk-volc-stt",
        stt_base_url="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
        stt_model="volc.bigasr.sauc.duration",
    )

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.stt_provider == "volcengine"
        assert dto.stt_api_key_configured is True
        assert dto.stt_api_key_preview == "***-stt"
        assert dto.stt_api_key_source == "stt"
        assert dto.stt_use_tts_api_key is False
    finally:
        settings.llm = original_llm
        settings.voice = original_voice


def test_voice_config_reports_volcengine_stt_reusing_tts_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_llm = settings.llm
    original_voice = settings.voice
    monkeypatch.delenv("VOICE__STT_API_KEY", raising=False)
    monkeypatch.setattr(training_studio_routes, "_read_env_file_values", lambda path=None: {})
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-llm-shared",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    )
    settings.voice = VoiceSettings(
        tts_provider="volcengine",
        tts_api_key="sk-volc-speech",
        tts_base_url="https://openspeech.bytedance.com/api/v3/tts/unidirectional",
        tts_model="seed-tts-2.0",
        stt_provider="volcengine",
        stt_api_key=None,
        stt_base_url="wss://openspeech.bytedance.com/api/v3/sauc/bigmodel",
        stt_model="volc.bigasr.sauc.duration",
    )

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.stt_provider == "volcengine"
        assert dto.stt_api_key_configured is True
        assert dto.stt_api_key_preview == "***eech"
        assert dto.stt_api_key_source == "tts"
        assert dto.stt_use_tts_api_key is True
    finally:
        settings.llm = original_llm
        settings.voice = original_voice


def test_voice_config_reports_generic_realtime_provider_key() -> None:
    original_llm = settings.llm
    original_realtime = {
        "REALTIME_PROVIDER": settings.REALTIME_PROVIDER,
        "REALTIME_API_KEY": settings.REALTIME_API_KEY,
        "REALTIME_BASE_URL": settings.REALTIME_BASE_URL,
        "REALTIME_OPENAI_API_KEY": settings.REALTIME_OPENAI_API_KEY,
    }
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-llm-fallback",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    )
    settings.REALTIME_PROVIDER = "google.gemini_live"
    settings.REALTIME_API_KEY = "sk-gemini-live"
    settings.REALTIME_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    settings.REALTIME_OPENAI_API_KEY = None

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.realtime_provider == "google.gemini_live"
        assert dto.realtime_base_url == "https://generativelanguage.googleapis.com/v1beta"
        assert dto.realtime_api_key_configured is True
        assert dto.realtime_effective_api_key_configured is True
        assert dto.realtime_api_key_preview == "***live"
        assert dto.realtime_api_key_source == "realtime"
    finally:
        settings.llm = original_llm
        for key, value in original_realtime.items():
            setattr(settings, key, value)


def test_voice_config_does_not_reuse_llm_key_for_non_openai_realtime_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_llm = settings.llm
    original_realtime = {
        "REALTIME_PROVIDER": settings.REALTIME_PROVIDER,
        "REALTIME_API_KEY": settings.REALTIME_API_KEY,
        "REALTIME_BASE_URL": settings.REALTIME_BASE_URL,
        "REALTIME_OPENAI_API_KEY": settings.REALTIME_OPENAI_API_KEY,
    }
    monkeypatch.delenv("REALTIME_API_KEY", raising=False)
    monkeypatch.setattr(training_studio_routes, "_read_env_file_values", lambda path=None: {})
    settings.llm = LLMSettings(
        provider="openai",
        api_key="sk-llm-fallback",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
    )
    settings.REALTIME_PROVIDER = "xai.realtime"
    settings.REALTIME_API_KEY = None
    settings.REALTIME_BASE_URL = "https://api.x.ai/v1"
    settings.REALTIME_OPENAI_API_KEY = None

    try:
        dto = training_studio_routes._voice_config_response()

        assert dto.realtime_provider == "xai.realtime"
        assert dto.realtime_api_key_configured is False
        assert dto.realtime_effective_api_key_configured is False
        assert dto.realtime_api_key_preview is None
        assert dto.realtime_api_key_source == "missing"
    finally:
        settings.llm = original_llm
        for key, value in original_realtime.items():
            setattr(settings, key, value)


def test_openai_realtime_key_accepts_generic_key_for_openai_provider() -> None:
    original_llm = settings.llm
    original_realtime = {
        "REALTIME_PROVIDER": settings.REALTIME_PROVIDER,
        "REALTIME_API_KEY": settings.REALTIME_API_KEY,
        "REALTIME_OPENAI_API_KEY": settings.REALTIME_OPENAI_API_KEY,
    }
    settings.llm = LLMSettings(provider="openai", api_key=None, default_model="gpt-4o-mini")
    settings.REALTIME_PROVIDER = "openai"
    settings.REALTIME_API_KEY = "sk-generic-openai"
    settings.REALTIME_OPENAI_API_KEY = None

    try:
        assert training_studio_routes._openai_realtime_api_key() == "sk-generic-openai"
    finally:
        settings.llm = original_llm
        for key, value in original_realtime.items():
            setattr(settings, key, value)


def test_realtime_capabilities_include_volcengine_doubao_runtime_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REALTIME_PROVIDER", "volcengine.doubao_realtime")
    monkeypatch.setattr(settings, "REALTIME_API_KEY", "sk-volcengine-realtime")
    monkeypatch.setattr(settings, "REALTIME_BASE_URL", "wss://example.test/doubao/realtime")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_MODEL", "seed-duplex-test")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "voice-test")

    data = training_studio_routes._realtime_capabilities_response()
    volcengine = find_provider_capability(data, "volcengine.doubao_realtime")

    assert volcengine is not None
    assert volcengine["provider"] == "volcengine.doubao_realtime"
    assert volcengine["runtime"] == "volcengine.doubao_realtime"
    assert volcengine.get("readyForCall") is True
    assert "sk-volcengine-realtime" not in json.dumps(data, default=str)
    assert find_provider_capability(data, "pipecat") is not None


def test_realtime_pipeline_factory_keeps_pipecat_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_adapter = object()
    fake_module = SimpleNamespace(create_pipecat_realtime_pipeline=lambda: fake_adapter)
    monkeypatch.setattr(
        training_studio_routes,
        "_load_pipecat_realtime_adapter",
        lambda: fake_module,
    )

    factory = training_studio_routes.get_training_realtime_pipeline_factory()

    assert factory("pipecat") is fake_adapter
    assert factory("pipecat_pipeline") is fake_adapter


def test_realtime_pipeline_factory_routes_volcengine_doubao_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "REALTIME_PROVIDER", "volcengine.doubao_realtime")
    monkeypatch.setattr(settings, "REALTIME_API_KEY", "sk-volcengine-realtime")
    monkeypatch.setattr(settings, "REALTIME_BASE_URL", "wss://example.test/doubao/realtime")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_MODEL", "seed-duplex-test")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "voice-test")

    factory = training_studio_routes.get_training_realtime_pipeline_factory()

    assert factory("volcengine.doubao_realtime") is not None


def test_realtime_pipeline_factory_uses_volcengine_default_for_placeholder_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_adapter = object()
    fake_module = SimpleNamespace(
        create_volcengine_doubao_realtime_adapter=lambda **kwargs: (
            captured.update(kwargs) or fake_adapter
        )
    )
    monkeypatch.setattr(
        training_studio_routes,
        "_load_volcengine_doubao_realtime_adapter",
        lambda: fake_module,
    )
    monkeypatch.setattr(settings, "REALTIME_API_KEY", "sk-volcengine-realtime")
    monkeypatch.setattr(settings, "REALTIME_BASE_URL", "wss://example.test/doubao/realtime")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_MODEL", "seed-duplex-test")
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "your-volcengine-voice")

    factory = training_studio_routes.get_training_realtime_pipeline_factory()

    assert factory("volcengine.doubao_realtime") is fake_adapter
    assert captured["voice"] == "zh_female_vv_uranus_bigtts"


def test_realtime_websocket_routes_volcengine_provider_without_pipecat_rejection(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRealtimePipelineAdapter:
        def __init__(self) -> None:
            self.started_context = None
            self.started_config = None
            self.closed = False

        async def start(self, context, config) -> None:
            self.started_context = context
            self.started_config = config

        async def append_audio(self, chunk) -> None:
            return None

        async def commit_audio(self) -> None:
            return None

        async def events(self):
            if False:
                yield {}

        async def close(self) -> None:
            self.closed = True

    async def create_bound_session() -> str:
        session = await app.state.training_session_service.create_session(
            session_payload(
                "realtime",
                user_id="user-admin-001",
                team_id="team-ops",
            )
        )
        await app.state.training_session_service.start_session(
            session.session_id,
            room_id="42",
            access_scope=training_session_scope(),
        )
        return session.session_id

    adapter = FakeRealtimePipelineAdapter()
    monkeypatch.setattr(settings, "NEWAPI_AUTH_ENABLED", False)
    monkeypatch.setattr(settings, "NEWAPI_AUTH_ALLOW_MOCK_FALLBACK", True)
    monkeypatch.setattr(settings, "REALTIME_OPENAI_VOICE", "your-volcengine-voice")
    session_id = asyncio.run(create_bound_session())
    app.state.training_runtime_state.rooms[42] = SimpleNamespace(id=42, name="Realtime Room")
    app.dependency_overrides[get_training_realtime_uow_factory] = (
        app.dependency_overrides[get_training_runtime_uow_factory]
    )
    app.dependency_overrides[get_training_realtime_pipeline_factory] = (
        lambda: lambda provider: adapter
        if provider == "volcengine.doubao_realtime"
        else None
    )
    client = TestClient(app)

    with client.websocket_connect(
        f"/api/v1/training-studio/realtime?session_id={session_id}&room_id=42"
        "&provider=volcengine.doubao_realtime",
        headers={"X-Mock-User": "admin"},
    ) as ws:
        started = ws.receive_json()
        assert started["type"] == "session.started", started
        listening = ws.receive_json()
        ws.send_json({"type": "session.close", "reason": "done"})
        closed = ws.receive_json()

    assert started["payload"]["provider"] == "volcengine.doubao_realtime"
    assert started["payload"]["realtimeRuntime"] == "volcengine.doubao_realtime"
    assert listening["status"] == "listening"
    assert closed["type"] == "session.closed"
    assert adapter.started_context is not None
    assert adapter.started_context.metadata["provider"] == "volcengine.doubao_realtime"
    assert adapter.started_context.metadata["realtimeRuntime"] == "volcengine.doubao_realtime"
    assert adapter.started_config is not None
    assert adapter.started_config.provider == "volcengine.doubao_realtime"
    assert adapter.started_config.runtime == "volcengine.doubao_realtime"
    assert adapter.started_config.voice == "zh_female_vv_uranus_bigtts"
    assert adapter.started_config.metadata["realtimeLlm"]["voice"] == (
        "zh_female_vv_uranus_bigtts"
    )
    assert adapter.closed is True


@pytest.mark.asyncio
async def test_task_config_normalizes_ratios_and_rubric_weights(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/training-studio/task-config",
        json={
            "role": "Backend Engineer",
            "level": "Senior",
            "tech_stack": ["Python", "FastAPI"],
            "question_type_ratios": {"behavioral": 30, "technical": 60, "pressure": 10},
            "question_count": 8,
            "framework": "star",
            "difficulty": "medium",
            "category": "interview",
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["difficulty"] == "medium"
    assert round(sum(data["question_type_ratios"].values()), 5) == 1
    assert round(sum(data["rubric_weights"].values()), 5) == 1


def session_payload(
    mode: str = "voice",
    metadata: dict | None = None,
    scenario_template_id: str | None = None,
    user_id: str | None = None,
    team_id: str | None = None,
) -> dict:
    return {
        "mode": mode,
        "scenario_template_id": scenario_template_id,
        "user_id": user_id,
        "team_id": team_id,
        "task_config": {
            "role": "Sales Associate",
            "level": "Senior",
            "tech_stack": ["discovery", "objection handling"],
            "question_type_ratios": {"behavioral": 30, "craft": 50, "pressure": 20},
            "question_count": 6,
            "framework": "prep",
            "difficulty": "medium",
            "category": "sales",
            "metadata": metadata or {},
        },
    }


def chat_detail(room_id: int, messages: list[MessageDTO]) -> ChatRoomDetailDTO:
    return ChatRoomDetailDTO(
        room=ChatRoomDTO(
            id=room_id,
            name=f"Room {room_id}",
            type="battle_prep",
            persona_ids=["customer-1"],
        ),
        messages=messages,
    )


def parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.strip().split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: ") :])
        if data_lines:
            events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def find_provider_capability(payload: object, provider: str) -> Mapping[str, object] | None:
    if isinstance(payload, Mapping):
        if payload.get("provider") == provider or payload.get("id") == provider:
            return payload
        for value in payload.values():
            found = find_provider_capability(value, provider)
            if found is not None:
                return found
    if isinstance(payload, (list, tuple)):
        for item in payload:
            found = find_provider_capability(item, provider)
            if found is not None:
                return found
    return None


def admin_team_headers(team_id: str) -> dict[str, str]:
    return {
        "X-User-Id": "user-admin-001",
        "X-System-Role": "admin",
        "X-Team-Id": team_id,
    }


def training_session_scope(
    user_id: str = "user-admin-001",
    team_id: str = "team-ops",
    *,
    include_team_scope: bool = True,
) -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id=user_id,
        team_id=team_id,
        include_team_scope=include_team_scope,
    )


def assert_training_session_legacy_room_scope(
    scope: object,
    *,
    session_id: str,
    room_id: int,
    operation: str,
) -> None:
    assert getattr(scope, "unrestricted", False) is True
    assert getattr(scope, "unrestricted_reason", None) == f"training_session:{operation}"
    assert getattr(scope, "guarded_by_training_session_id", None) == session_id
    assert getattr(scope, "guarded_room_id", None) == str(room_id)


def test_legacy_training_room_scope_requires_current_user_session_access() -> None:
    session = SimpleNamespace(
        session_id="session-guarded",
        user_id="user-cs-001",
        team_id="team-service",
        room_id="42",
    )
    current_user = training_studio_routes.CurrentUser(
        user_id="user-sales-001",
        system_role="staff",
        team_id="team-revenue",
    )

    with pytest.raises(HTTPException) as exc_info:
        training_studio_routes._legacy_room_scope_for_accessible_training_session(
            session,
            current_user,
            room_id=42,
            operation="unit_guard",
        )

    assert exc_info.value.status_code == 403
    assert "outside current user scope" in exc_info.value.detail


def test_legacy_training_room_scope_requires_bound_room_id() -> None:
    session = SimpleNamespace(
        session_id="session-guarded",
        user_id="user-sales-001",
        team_id="team-revenue",
        room_id="42",
    )
    current_user = training_studio_routes.CurrentUser(
        user_id="user-sales-001",
        system_role="staff",
        team_id="team-revenue",
    )

    with pytest.raises(HTTPException) as exc_info:
        training_studio_routes._legacy_room_scope_for_accessible_training_session(
            session,
            current_user,
            room_id=43,
            operation="unit_guard",
        )

    assert exc_info.value.status_code == 403
    assert "room_id does not match" in exc_info.value.detail


def test_training_guidance_turn_preserves_message_metadata() -> None:
    from api.routes.training_studio import _message_to_guidance_turn

    turn = _message_to_guidance_turn(
        MessageDTO(
            id=9,
            room_id=42,
            sender_type="user",
            sender_id="me",
            content="This was spoken through realtime voice.",
            metadata={
                "source": "realtime_voice",
                "trainingMode": "voice",
                "interactionMode": "realtime",
                "realtime": {"provider": "openai", "eventId": "evt_1"},
            },
        )
    )

    assert turn.metadata["source"] == "realtime_voice"
    assert turn.metadata["trainingMode"] == "voice"
    assert turn.metadata["interactionMode"] == "realtime"
    assert turn.metadata["realtime"] == {"provider": "openai", "eventId": "evt_1"}
    assert turn.metadata["message_id"] == 9


@pytest.mark.asyncio
async def test_training_session_create_list_and_get(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(metadata={"source": "api-test"}),
    )

    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["session_id"] == "session-1"
    assert created["status"] == "created"
    assert created["mode"] == "voice"
    assert created["scenario_template_id"] is None
    assert created["task_config"]["category"] == "sales"
    assert created["task_config"]["metadata"] == {"source": "api-test"}
    assert round(sum(created["task_config"]["question_type_ratios"].values()), 5) == 1

    list_resp = await client.get("/api/v1/training-studio/sessions")
    assert list_resp.status_code == 200
    assert [item["session_id"] for item in list_resp.json()["data"]] == ["session-1"]

    get_resp = await client.get("/api/v1/training-studio/sessions/session-1")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["session_id"] == "session-1"


@pytest.mark.asyncio
async def test_scenario_training_progress_aggregates_sessions(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    revenue_admin = admin_team_headers("team-revenue")
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            metadata={
                "scenario_training": {
                    "title": "New customer discount",
                    "score": 84,
                }
            },
            scenario_template_id="new-customer-discount",
            user_id="user-sales-001",
            team_id="team-revenue",
        ),
        headers=revenue_admin,
    )
    created = create_resp.json()["data"]
    session_id = created["session_id"]
    assert created["scenario_template_id"] == "new-customer-discount"
    assert created["user_id"] == "user-sales-001"
    assert created["team_id"] == "team-revenue"
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
        headers=revenue_admin,
    )
    app.state.analysis_reader_service.reports[9001] = FakeReport(id=9001, room_id=42)
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": "9001", "score_id": "score-9001", "generate_report": False},
        headers=revenue_admin,
    )
    other_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "voice",
            scenario_template_id="new-customer-discount",
            user_id="admin",
            team_id="team-revenue",
        ),
        headers=revenue_admin,
    )
    other_session_id = other_resp.json()["data"]["session_id"]

    progress_resp = await client.get(
        "/api/v1/training-studio/scenario-progress",
        params={"user_id": "user-sales-001", "team_id": "team-revenue"},
        headers=revenue_admin,
    )

    assert progress_resp.status_code == 200
    data = progress_resp.json()["data"]
    assert data == [
        {
            "scenario_id": "new-customer-discount",
            "user_id": "user-sales-001",
            "team_id": "team-revenue",
            "status": "completed",
            "failure_reason": None,
            "score": None,
            "score_status": "pending",
            "overall_score": None,
            "evaluation_id": None,
            "last_practiced_at": data[0]["last_practiced_at"],
            "training_session_id": session_id,
            "report_id": "9001",
            "score_id": "score-9001",
        }
    ]
    assert data[0]["last_practiced_at"]

    admin_progress_resp = await client.get(
        "/api/v1/training-studio/scenario-progress",
        params={"user_id": "admin", "team_id": "team-revenue"},
        headers=revenue_admin,
    )
    assert admin_progress_resp.status_code == 200
    assert admin_progress_resp.json()["data"][0]["training_session_id"] == other_session_id


@pytest.mark.asyncio
async def test_scenario_training_progress_reports_failed_session_reason(client: AsyncClient) -> None:
    revenue_admin = admin_team_headers("team-revenue")
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            scenario_template_id="new-customer-discount",
            user_id="user-sales-001",
            team_id="team-revenue",
        ),
        headers=revenue_admin,
    )
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
        headers=revenue_admin,
    )
    fail_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/fail",
        json={"reason": "analysis service unavailable"},
        headers=revenue_admin,
    )
    assert fail_resp.status_code == 200

    progress_resp = await client.get(
        "/api/v1/training-studio/scenario-progress",
        params={"user_id": "user-sales-001", "team_id": "team-revenue"},
        headers=revenue_admin,
    )

    assert progress_resp.status_code == 200
    data = progress_resp.json()["data"]
    assert data[0]["training_session_id"] == session_id
    assert data[0]["status"] == "failed"
    assert data[0]["failure_reason"] == "analysis service unavailable"
    assert data[0]["score_status"] == "pending"


@pytest.mark.asyncio
async def test_training_session_list_supports_skip_and_limit(client: AsyncClient) -> None:
    for mode in ["text", "voice", "video"]:
        create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload(mode))
        assert create_resp.status_code == 201

    list_resp = await client.get("/api/v1/training-studio/sessions", params={"skip": 1, "limit": 1})

    assert list_resp.status_code == 200
    data = list_resp.json()["data"]
    assert [item["session_id"] for item in data] == ["session-2"]
    assert list_resp.headers["x-total-count"] == "3"


@pytest.mark.asyncio
async def test_training_session_delete_respects_current_user_scope(client: AsyncClient) -> None:
    sales_headers = {"X-Mock-User": "sales"}
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            user_id="user-sales-001",
            team_id="team-revenue",
        ),
        headers=sales_headers,
    )
    session_id = create_resp.json()["data"]["session_id"]

    forbidden_resp = await client.delete(
        f"/api/v1/training-studio/sessions/{session_id}",
        headers={"X-Mock-User": "customer_service"},
    )
    assert forbidden_resp.status_code == 403

    deleted_resp = await client.delete(
        f"/api/v1/training-studio/sessions/{session_id}",
        headers=sales_headers,
    )
    assert deleted_resp.status_code == 200
    assert deleted_resp.json()["data"] == {
        "session_id": session_id,
        "deleted": True,
    }

    missing_resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}",
        headers=sales_headers,
    )
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_scenario_progress_pagination_exposes_total_and_summary(client: AsyncClient) -> None:
    for scenario_template_id in ["renewal", "discovery"]:
        create_resp = await client.post(
            "/api/v1/training-studio/sessions",
            json=session_payload(
                "text",
                scenario_template_id=scenario_template_id,
            ),
        )
        assert create_resp.status_code == 201

    progress_resp = await client.get(
        "/api/v1/training-studio/scenario-progress",
        params={"skip": 1, "limit": 1},
    )
    summary_resp = await client.get(
        "/api/v1/training-studio/scenario-progress/summary"
    )

    assert progress_resp.status_code == 200
    assert len(progress_resp.json()["data"]) == 1
    assert progress_resp.headers["x-total-count"] == "2"
    assert summary_resp.status_code == 200
    assert summary_resp.json()["data"] == {
        "tracked_scenarios": 2,
        "completed_scenarios": 0,
        "scored_scenarios": 0,
        "average_score": None,
        "completion_percentage": 0,
    }


@pytest.mark.asyncio
async def test_staff_session_list_ignores_forged_user_filter(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-sales-001", team_id="team-revenue"),
        headers={"X-Mock-User": "sales"},
    )
    await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
        headers={"X-Mock-User": "customer_service"},
    )

    resp = await client.get(
        "/api/v1/training-studio/sessions",
        params={"user_id": "user-cs-001"},
        headers={"X-Mock-User": "sales"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["user_id"] for item in data] == ["user-sales-001"]


@pytest.mark.asyncio
async def test_legacy_leader_scenario_progress_is_limited_to_own_user(client: AsyncClient) -> None:
    revenue_admin = admin_team_headers("team-revenue")
    service_admin = admin_team_headers("team-service")
    revenue_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            scenario_template_id="revenue-scenario",
            user_id="user-sales-001",
            team_id="team-revenue",
        ),
        headers=revenue_admin,
    )
    service_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            scenario_template_id="service-scenario",
            user_id="user-cs-001",
            team_id="team-service",
        ),
        headers=service_admin,
    )
    await client.post(
        f"/api/v1/training-studio/sessions/{revenue_resp.json()['data']['session_id']}/start",
        json={"room_id": 201},
        headers=revenue_admin,
    )
    await client.post(
        f"/api/v1/training-studio/sessions/{service_resp.json()['data']['session_id']}/start",
        json={"room_id": 202},
        headers=service_admin,
    )

    resp = await client.get(
        "/api/v1/training-studio/scenario-progress",
        params={"team_id": "team-service"},
        headers={"X-Mock-User": "leader"},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == []


@pytest.mark.asyncio
async def test_admin_session_list_can_filter_by_user_and_team(client: AsyncClient) -> None:
    ops_admin = admin_team_headers("team-ops")
    service_admin = admin_team_headers("team-service")
    await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-admin-001", team_id="team-ops"),
        headers=ops_admin,
    )
    await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
        headers=service_admin,
    )

    resp = await client.get(
        "/api/v1/training-studio/sessions",
        params={"user_id": "user-admin-001", "team_id": "team-service"},
        headers=ops_admin,
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert [item["user_id"] for item in data] == ["user-admin-001"]
    assert [item["team_id"] for item in data] == ["team-ops"]

    outside_resp = await client.get(
        "/api/v1/training-studio/sessions",
        params={"user_id": "user-cs-001", "team_id": "team-service"},
        headers=ops_admin,
    )

    assert outside_resp.status_code == 200
    assert outside_resp.json()["data"] == []


@pytest.mark.asyncio
async def test_staff_create_session_uses_current_user_scope(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
        headers={"X-Mock-User": "sales"},
    )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["user_id"] == "user-sales-001"
    assert data["team_id"] == "team-revenue"


@pytest.mark.asyncio
async def test_staff_cannot_access_other_user_training_session(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
    )
    session_id = create_resp.json()["data"]["session_id"]

    get_resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}",
        headers={"X-Mock-User": "sales"},
    )
    fail_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/fail",
        json={"reason": "should not be allowed"},
        headers={"X-Mock-User": "sales"},
    )

    assert get_resp.status_code == 403
    assert fail_resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_cannot_mutate_other_user_training_session_boundaries(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
    )
    session_id = create_resp.json()["data"]["session_id"]
    staff_headers = {"X-Mock-User": "sales"}

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"persona_ids": ["customer-1"], "room_name": "Forged room"},
        headers=staff_headers,
    )
    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": 777, "generate_report": False},
        headers=staff_headers,
    )
    report_resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}/report",
        headers=staff_headers,
    )
    guidance_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        json={"recent_turns": [{"speaker": "user", "text": "Please coach this answer."}]},
        headers=staff_headers,
    )
    guidance_events_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance-events",
        json={
            "events": [
                {
                    "event_type": "risk",
                    "severity": "warning",
                    "title": "Blocked",
                    "message": "This should not be persisted.",
                }
            ]
        },
        headers=staff_headers,
    )

    assert start_resp.status_code == 403
    assert complete_resp.status_code == 403
    assert report_resp.status_code == 403
    assert guidance_resp.status_code == 403
    assert guidance_events_resp.status_code == 403
    assert app.state.chatroom_service.created_rooms == []
    assert app.state.analysis_service.generated_for == []
    assert app.state.growth_service.evaluated == []
    assert app.state.chatroom_service.detail_calls == []


@pytest.mark.asyncio
async def test_staff_cannot_start_own_session_with_arbitrary_existing_room_id(
    client: AsyncClient,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("realtime"),
        headers={"X-Mock-User": "sales"},
    )
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
        headers={"X-Mock-User": "sales"},
    )

    assert start_resp.status_code == 403
    assert "Only admins can bind an existing room" in start_resp.json()["message"]


@pytest.mark.asyncio
async def test_leader_cannot_read_other_team_training_session(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-cs-001", team_id="team-service"),
    )
    session_id = create_resp.json()["data"]["session_id"]

    resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}",
        headers={"X-Mock-User": "leader"},
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_training_session_start_with_explicit_room_id(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "42"

    duplicate_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 43},
    )
    assert duplicate_resp.status_code == 400


@pytest.mark.asyncio
async def test_training_session_start_can_create_room(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("video"))
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"persona_ids": ["customer-1"], "room_name": "Sales practice"},
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "701"


@pytest.mark.asyncio
async def test_training_session_start_can_create_runtime_persona(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("voice", scenario_template_id="ai-web3-agent-pm-comprehensive-interview"),
    )
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={
            "room_name": "AI Agent PM interview training",
            "room_type": "battle_prep",
            "runtime_persona": {
                "name": "Hiring Panel",
                "role": "AI Agent product interviewer",
                "style": "Probe evidence, product judgment, and technical fluency.",
                "scenario_context": "Full AI/Web3 Agent PM interview simulation.",
                "training_points": [
                    "Problem framing",
                    "Agent architecture",
                    "Web3 risk",
                    "Execution metrics",
                    "Stakeholder tradeoff",
                    "Roadmap prioritization",
                ],
                "difficulty": "hard",
            },
        },
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "701"

    created_persona = app.state.persona_editor.created_personas[0]
    assert created_persona.id.startswith("ts-")
    assert created_persona.temporary is True
    assert created_persona.name == "Hiring Panel"
    assert "Full AI/Web3 Agent PM interview simulation." in created_persona.content
    assert "Roadmap prioritization" in created_persona.content
    assert "strong pressure" in created_persona.content

    created_room = app.state.chatroom_service.created_rooms[0]
    assert created_room.name == "AI Agent PM interview training"
    assert created_room.type == "battle_prep"
    assert created_room.persona_ids == [created_persona.id]


@pytest.mark.asyncio
async def test_training_session_start_persists_runtime_persona_opening_message(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("voice", scenario_template_id="new-customer-discount"),
    )
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={
            "room_name": "New customer discount",
            "room_type": "battle_prep",
            "runtime_persona": {
                "name": "Customer",
                "role": "Discount-sensitive walk-in customer",
                "style": "Ask concise price questions and test trust.",
                "scenario_context": "New customer discount consult.",
                "training_points": ["Clarify need", "Explain offer boundary"],
                "difficulty": "normal",
            },
            "opening_message": {
                "content": "你好，我看到你们门口说有新客优惠，能介绍一下吗？",
                "metadata": {
                    "source": "scenario_training_opening",
                    "scenarioTrainingId": "new-customer-discount",
                },
            },
        },
    )

    assert start_resp.status_code == 200
    created_persona = app.state.persona_editor.created_personas[0]
    assert len(app.state.training_runtime_state.messages) == 1
    opening = app.state.training_runtime_state.messages[0]
    assert opening.room_id == 701
    assert opening.sender_type == "persona"
    assert opening.sender_id == created_persona.id
    assert opening.content == "你好，我看到你们门口说有新客优惠，能介绍一下吗？"
    assert opening.metadata["source"] == "scenario_training_opening"
    assert opening.metadata["eventKind"] == "scenario_opening"
    assert opening.metadata["trainingSessionId"] == session_id
    assert app.state.training_runtime_state.last_message_updates[0][0] == 701


@pytest.mark.asyncio
async def test_training_session_start_can_bind_message_tree_runtime(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            metadata={
                "persona_ids": ["customer-1"],
                "scenario_id": 9,
                "ownerUserId": "forged-user",
                "teamId": "forged-team",
                "authScope": {"userId": "forged-user", "teamId": "forged-team"},
            },
            user_id="user-sales-001",
            team_id="team-revenue",
        ),
        headers={"X-Mock-User": "sales"},
    )
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"runtime": "conversation_message_tree"},
        headers={"X-Mock-User": "sales"},
    )

    assert start_resp.status_code == 200
    started = start_resp.json()["data"]
    assert started["status"] == "active"
    assert started["room_id"] == "talkwise-conversation:1"
    assert started["conversation"]["provider"] == "talkwise-conversation"
    assert started["conversation"]["metadata"]["runtime"] == "conversation_message_tree"
    assert started["conversation"]["metadata"]["ownerUserId"] == "user-sales-001"
    assert started["conversation"]["metadata"]["teamId"] == "team-revenue"
    assert started["conversation"]["metadata"]["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }
    assert started["task_config"]["metadata"]["runtime"] == "conversation_message_tree"
    assert started["task_config"]["metadata"]["ownerUserId"] == "user-sales-001"
    assert started["task_config"]["metadata"]["teamId"] == "team-revenue"
    assert started["task_config"]["metadata"]["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }
    assert app.state.chatroom_service.created_rooms == []
    assert app.state.training_runtime_state.created_conversations[0].metadata["ownerUserId"] == (
        "user-sales-001"
    )
    assert app.state.training_runtime_state.created_conversations[0].metadata["teamId"] == (
        "team-revenue"
    )


@pytest.mark.asyncio
async def test_training_session_start_rejects_room_id_for_message_tree_runtime(
    client: AsyncClient,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]

    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"runtime": "conversation_message_tree", "room_id": 42},
    )

    assert start_resp.status_code == 422
    assert "room_id cannot be provided when starting a conversation_message_tree session" in (
        start_resp.json()["message"]
    )


@pytest.mark.asyncio
async def test_training_session_fail_endpoint(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]

    fail_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/fail",
        json={"reason": "user stopped the practice"},
    )

    assert fail_resp.status_code == 200
    failed = fail_resp.json()["data"]
    assert failed["status"] == "failed"
    assert failed["failure_reason"] == "user stopped the practice"
    assert failed["completed_at"] is not None


@pytest.mark.asyncio
async def test_training_session_complete_and_report(client: AsyncClient, app: FastAPI) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={},
    )

    assert complete_resp.status_code == 200
    completed = complete_resp.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "501"
    assert app.state.analysis_service.generated_for == [42]
    assert_training_session_legacy_room_scope(
        app.state.analysis_service.generated_scopes[0],
        session_id=session_id,
        room_id=42,
        operation="generate_report",
    )

    app.state.analysis_reader_service.reports[501] = FakeReport(id=501, room_id=42)
    report_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["id"] == 501
    assert_training_session_legacy_room_scope(
        app.state.analysis_reader_service.requested_scopes[-1],
        session_id=session_id,
        room_id=42,
        operation="session_report",
    )


@pytest.mark.asyncio
async def test_training_session_complete_can_generate_report_in_background(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_generation": "background"},
    )

    assert complete_resp.status_code == 200
    completed = complete_resp.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] is None
    assert completed["task_config"]["metadata"]["completionReport"]["status"] == "pending"
    assert completed["task_config"]["metadata"]["completionReport"]["generation"] == "background"

    session_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}")
    assert session_resp.status_code == 200
    session = session_resp.json()["data"]
    assert session["report_id"] == "501"
    completion_report = session["task_config"]["metadata"]["completionReport"]
    assert completion_report["status"] == "ready"
    assert completion_report["reportId"] == "501"
    assert app.state.analysis_service.generated_for == [42]
    assert app.state.growth_service.evaluated == [501]
    assert_training_session_legacy_room_scope(
        app.state.analysis_service.generated_scopes[0],
        session_id=session_id,
        room_id=42,
        operation="generate_report",
    )

    app.state.analysis_reader_service.reports[501] = FakeReport(id=501, room_id=42)
    report_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["id"] == 501


@pytest.mark.asyncio
async def test_training_session_complete_does_not_fail_when_report_generation_fails(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    class FailingAnalysisService(FakeAnalysisService):
        async def generate_report(self, room_id: int, *, access_scope) -> FakeReport:
            self.generated_for.append(room_id)
            self.generated_scopes.append(access_scope)
            raise RuntimeError("provider returned 500")

    failing_analysis = FailingAnalysisService()
    app.dependency_overrides[get_analysis_service] = lambda: failing_analysis
    app.state.analysis_service = failing_analysis

    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={},
    )

    assert complete_resp.status_code == 200
    completed = complete_resp.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] is None
    assert failing_analysis.generated_for == [42]
    assert app.state.growth_service.evaluated == []
    completion_report = completed["task_config"]["metadata"]["completionReport"]
    assert completion_report["status"] == "failed"
    assert completion_report["phase"] == "generate_report"
    assert completion_report["completedWithoutReport"] is True
    assert completion_report["errorType"] == "RuntimeError"


@pytest.mark.asyncio
async def test_training_session_complete_with_explicit_report_id_skips_generation(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.analysis_reader_service.reports[777] = FakeReport(id=777, room_id=42)

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": 777, "generate_report": False},
    )

    assert complete_resp.status_code == 200
    completed = complete_resp.json()["data"]
    assert completed["status"] == "completed"
    assert completed["report_id"] == "777"
    assert app.state.analysis_service.generated_for == []
    assert app.state.growth_service.evaluated == []
    assert_training_session_legacy_room_scope(
        app.state.analysis_reader_service.requested_scopes[0],
        session_id=session_id,
        room_id=42,
        operation="explicit_report_lookup",
    )

    report_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["id"] == 777


@pytest.mark.asyncio
async def test_training_session_complete_persists_message_tree_branch_metadata(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload(
            "text",
            metadata={"source": "scenario_training"},
            scenario_template_id="new-customer-discount",
        ),
    )
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.analysis_reader_service.reports[777] = FakeReport(id=777, room_id=42)
    branch_metadata = {
        "messageTreeSelection": {
            "provider": "talkwise-conversation",
            "conversationId": "7",
            "selectedMessageId": "msg-tail",
            "branchId": "branch-review",
            "path": [
                {"publicId": "msg-root", "role": "user", "content": "Can we revisit pricing?"},
                {
                    "publicId": "msg-tail",
                    "role": "assistant",
                    "content": "Use a measurable pilot.",
                    "branchId": "branch-review",
                },
            ],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "selectedPath": {
            "branchId": "branch-review",
            "tailMessageId": "msg-tail",
            "messageIds": ["msg-root", "msg-tail"],
            "purpose": "training_replay_context",
            "replayContextOnly": True,
            "affectsScoring": False,
            "affectsCompletion": False,
        },
        "currentBranchTail": {
            "branchId": "branch-review",
            "messageId": "msg-tail",
        },
    }

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": 777, "generate_report": False, "metadata": branch_metadata},
    )

    assert complete_resp.status_code == 200
    completed_metadata = complete_resp.json()["data"]["task_config"]["metadata"]
    assert completed_metadata["source"] == "scenario_training"
    assert completed_metadata["messageTreeSelection"]["selectedMessageId"] == "msg-tail"
    assert completed_metadata["messageTreeSelection"]["affectsScoring"] is False
    assert completed_metadata["selectedPath"]["affectsCompletion"] is False
    get_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}")
    assert get_resp.status_code == 200
    persisted_metadata = get_resp.json()["data"]["task_config"]["metadata"]
    assert persisted_metadata["messageTreeSelection"]["path"][1]["publicId"] == "msg-tail"


@pytest.mark.asyncio
async def test_training_session_complete_rejects_unowned_explicit_report_id(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.analysis_reader_service.reports[777] = FakeReport(id=777, room_id=43)
    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": "777", "generate_report": False},
    )

    assert complete_resp.status_code == 404
    assert "report not found" in complete_resp.json()["message"]
    stored = await app.state.training_session_service.get_session(
        session_id,
        access_scope=training_session_scope(),
    )
    assert stored.report_id is None


@pytest.mark.asyncio
async def test_training_session_complete_rejects_non_numeric_explicit_report_id(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"report_id": "report-777", "generate_report": False},
    )

    assert complete_resp.status_code == 404
    assert app.state.analysis_reader_service.requested_ids == []
    stored = await app.state.training_session_service.get_session(
        session_id,
        access_scope=training_session_scope(),
    )
    assert stored.report_id is None


@pytest.mark.asyncio
async def test_training_session_complete_requires_numeric_room_id_when_generating_report(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": "room-42"},
    )

    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={},
    )

    assert complete_resp.status_code == 400
    assert "room_id must be numeric" in complete_resp.json()["message"]
    assert app.state.analysis_service.generated_for == []
    assert app.state.growth_service.evaluated == []


@pytest.mark.asyncio
async def test_training_session_guidance_reads_bound_room_messages(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.chatroom_service.details[42] = chat_detail(
        42,
        [
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="me",
                content="We can support your team with a pilot.",
            ),
            MessageDTO(
                id=2,
                room_id=42,
                sender_type="persona",
                sender_id="customer-1",
                content="I am not convinced because this feels too expensive for our budget.",
            ),
        ],
    )

    resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        params={"message_limit": 12},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    event_types = {event["event_type"] for event in data["events"]}
    assert data["source"] == "room"
    assert data["total_turn_count"] == 2
    assert {"risk", "next_reply"}.issubset(event_types)
    assert app.state.chatroom_service.detail_calls == [(42, 12)]
    assert_training_session_legacy_room_scope(
        app.state.chatroom_service.detail_scopes[0],
        session_id=session_id,
        room_id=42,
        operation="guidance_context",
    )


@pytest.mark.asyncio
async def test_training_session_guidance_accepts_request_turns(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    long_answer = " ".join(["This answer keeps going without a pause"] * 5)

    resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        json={
            "task_goal": "Sales objection handling",
            "rubric": {"discovery": 0.4},
            "recent_turns": [
                {"speaker": "user", "text": long_answer, "turn_id": "client-1"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "request"
    assert any(event["event_type"] == "delivery_nudge" for event in data["events"])


@pytest.mark.asyncio
async def test_training_guidance_rate_limit_returns_429(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_ai_rate_limit_state()
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 1)
    headers = {"X-Mock-User": "customer_service"}
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text"),
        headers=headers,
    )
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"persona_ids": ["customer-1"], "room_name": "Support practice"},
        headers=headers,
    )
    payload = {
        "recent_turns": [
            {"speaker": "user", "text": "This is a long enough practice answer to coach."},
        ],
    }

    first_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        json=payload,
        headers=headers,
    )
    second_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        json=payload,
        headers=headers,
    )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 429


@pytest.mark.asyncio
async def test_training_session_guidance_parses_video_answer_marker(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    captured_turns = []

    class CapturingGuidanceService(TrainingLiveGuidanceService):
        async def generate_guidance_async(self, **kwargs):
            captured_turns.extend(kwargs["recent_turns"])
            return []

    app.dependency_overrides[get_live_guidance_service] = lambda: CapturingGuidanceService()
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("video"))
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    video_attachment = {
        "url": "/api/v1/training-studio/video-answers/answer.webm",
        "mimeType": "video/webm",
        "durationMs": 42000,
        "recordedAt": "2026-07-14T09:00:00Z",
        "trainingEvent": {
            "type": "video_answer_submitted",
            "trainingMode": "video",
            "schemaVersion": 1,
            "reportDimensions": ["content_delivery", "camera_presence"],
            "cameraPresenceStatus": "placeholder",
        },
    }
    app.state.chatroom_service.details[42] = chat_detail(
        42,
        [
            MessageDTO(
                id=9,
                room_id=42,
                sender_type="user",
                sender_id="me",
                content="Here is my product demo answer.\n\n[video-answer]" + json.dumps(video_attachment),
            ),
        ],
    )

    resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/guidance")

    assert resp.status_code == 200
    assert len(captured_turns) == 1
    turn = captured_turns[0]
    assert turn.text == "Here is my product demo answer."
    assert "[video-answer]" not in turn.text
    assert turn.metadata["source"] == "video_answer"
    assert turn.metadata["videoUrl"] == video_attachment["url"]
    assert turn.metadata["trainingEvent"] == video_attachment["trainingEvent"]


@pytest.mark.asyncio
async def test_training_guidance_accepts_eventsource_mock_user_scope(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text", user_id="user-sales-001", team_id="team-revenue"),
    )
    session_id = create_resp.json()["data"]["session_id"]
    room_id = 42
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": room_id},
    )
    app.state.chatroom_service.details[room_id] = chat_detail(
        room_id,
        [
            MessageDTO(
                id=1,
                room_id=room_id,
                sender_type="user",
                sender_id="me",
                content="Can we start with a low-risk pilot?",
            ),
        ],
    )

    own_resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        params={"mock_user": "sales"},
    )
    other_resp = await client.get(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        params={"mock_user": "customer_service"},
    )

    assert own_resp.status_code == 200
    assert other_resp.status_code == 403


@pytest.mark.asyncio
async def test_training_session_guidance_stream_emits_initial_guidance(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.chatroom_service.details[42] = chat_detail(
        42,
        [
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="me",
                content="Can we start with a low-risk pilot?",
            ),
            MessageDTO(
                id=2,
                room_id=42,
                sender_type="persona",
                sender_id="customer-1",
                content="I am worried that the budget will not work.",
            ),
        ],
    )

    async with client.stream(
        "GET",
        f"/api/v1/training-studio/sessions/{session_id}/guidance/stream",
        params={"message_limit": 12, "max_events": 1},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = (await resp.aread()).decode()

    events = parse_sse_events(body)
    assert events[0][0] == "guidance_snapshot"
    data = events[0][1]
    event_types = {event["event_type"] for event in data["events"]}
    assert data["session_id"] == session_id
    assert data["source"] == "room"
    assert data["total_turn_count"] == 2
    assert {"risk", "next_reply"}.issubset(event_types)
    assert app.state.chatroom_service.detail_calls == [(42, 12)]


@pytest.mark.asyncio
async def test_training_session_guidance_stream_follows_room_message_events(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    from application.services.stakeholder.sse import room_event_bus

    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": 42},
    )
    app.state.chatroom_service.details[42] = chat_detail(
        42,
        [
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="me",
                content="We can start with a small pilot.",
            ),
        ],
    )

    async def publish_room_message() -> None:
        await asyncio.sleep(0.05)
        app.state.chatroom_service.details[42] = chat_detail(
            42,
            [
                MessageDTO(
                    id=1,
                    room_id=42,
                    sender_type="user",
                    sender_id="me",
                    content="We can start with a small pilot.",
                ),
                MessageDTO(
                    id=2,
                    room_id=42,
                    sender_type="persona",
                    sender_id="customer-1",
                    content="I am not convinced because the cost is risky.",
                ),
            ],
        )
        await room_event_bus.publish(
            42,
            "message",
            {"id": 2, "room_id": 42, "sender_type": "persona", "sender_id": "customer-1"},
        )

    publish_task = asyncio.create_task(publish_room_message())
    async with client.stream(
        "GET",
        f"/api/v1/training-studio/sessions/{session_id}/guidance/stream",
        params={"message_limit": 12, "max_events": 2},
    ) as resp:
        assert resp.status_code == 200
        body = (await resp.aread()).decode()
    await publish_task

    events = parse_sse_events(body)
    assert [event for event, _ in events] == ["guidance_snapshot", "guidance_snapshot"]
    assert events[0][1]["reason"] == "initial"
    assert events[1][1]["reason"] == "room_message"
    assert events[1][1]["trigger"]["message_id"] == 2
    event_types = {event["event_type"] for event in events[1][1]["events"]}
    assert "risk" in event_types
    assert app.state.chatroom_service.detail_calls == [(42, 12), (42, 12)]


@pytest.mark.asyncio
async def test_training_guidance_stream_refresh_preserves_current_user_scope(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    from application.services.stakeholder.sse import room_event_bus

    headers = {"X-Mock-User": "sales"}
    create_resp = await client.post(
        "/api/v1/training-studio/sessions",
        json=session_payload("text"),
        headers=headers,
    )
    session_id = create_resp.json()["data"]["session_id"]
    start_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"persona_ids": ["customer-1"], "room_name": "Scoped room"},
        headers=headers,
    )
    assert start_resp.status_code == 200
    room_id = int(start_resp.json()["data"]["room_id"])
    app.state.chatroom_service.details[room_id] = chat_detail(
        room_id,
        [
            MessageDTO(
                id=1,
                room_id=42,
                sender_type="user",
                sender_id="me",
                content="Can we start with a low-risk pilot?",
            ),
        ],
    )

    async def move_session_out_of_scope_and_publish() -> None:
        await asyncio.sleep(0.05)
        session = await app.state.training_session_service.get_session(
            session_id,
            access_scope=training_session_scope(
                user_id="user-sales-001",
                team_id="team-revenue",
                include_team_scope=False,
            ),
        )
        session.user_id = "user-cs-001"
        session.team_id = "team-service"
        app.state.chatroom_service.details[room_id] = chat_detail(
            room_id,
            [
                MessageDTO(
                    id=1,
                    room_id=room_id,
                    sender_type="user",
                    sender_id="me",
                    content="Can we start with a low-risk pilot?",
                ),
                MessageDTO(
                    id=2,
                    room_id=room_id,
                    sender_type="persona",
                    sender_id="customer-1",
                    content="I am worried the budget still does not work.",
                ),
            ],
        )
        await room_event_bus.publish(
            room_id,
            "message",
            {"id": 2, "room_id": room_id, "sender_type": "persona", "sender_id": "customer-1"},
        )

    publish_task = asyncio.create_task(move_session_out_of_scope_and_publish())
    async with client.stream(
        "GET",
        f"/api/v1/training-studio/sessions/{session_id}/guidance/stream",
        params={"message_limit": 12, "max_events": 2},
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        body = (await resp.aread()).decode()
    await publish_task

    events = parse_sse_events(body)
    assert [event for event, _ in events] == ["guidance_snapshot", "guidance_error"]
    assert events[1][1]["status_code"] == 403
    assert "current user scope" in events[1][1]["detail"]


@pytest.mark.asyncio
async def test_training_session_guidance_requires_active_session(client: AsyncClient) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]

    resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/guidance",
        json={"recent_turns": [{"speaker": "user", "text": "hello"}]},
    )

    assert resp.status_code == 400
    assert "must be active" in resp.json()["message"]


@pytest.mark.asyncio
async def test_training_session_guidance_requires_numeric_room_id(
    client: AsyncClient,
    app: FastAPI,
) -> None:
    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload("text"))
    session_id = create_resp.json()["data"]["session_id"]
    await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/start",
        json={"room_id": "room-42"},
    )

    resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/guidance")

    assert resp.status_code == 400
    assert "room_id must be numeric" in resp.json()["message"]
    assert app.state.chatroom_service.detail_calls == []


@pytest.mark.asyncio
async def test_training_session_guidance_returns_404_for_missing_session(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/training-studio/sessions/missing/guidance")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_training_session_errors(client: AsyncClient) -> None:
    missing_resp = await client.post(
        "/api/v1/training-studio/sessions/missing/start",
        json={"room_id": 1},
    )
    assert missing_resp.status_code == 404

    create_resp = await client.post("/api/v1/training-studio/sessions", json=session_payload())
    session_id = create_resp.json()["data"]["session_id"]
    complete_resp = await client.post(
        f"/api/v1/training-studio/sessions/{session_id}/complete",
        json={"generate_report": False},
    )
    assert complete_resp.status_code == 400


@pytest.mark.asyncio
async def test_storybank_register_and_list(client: AsyncClient) -> None:
    answer = (
        "I led a small platform migration team through a difficult API rewrite. "
        "We reduced latency by 35 percent and recovered trust with two key stakeholders."
    )
    create_resp = await client.post(
        "/api/v1/training-studio/storybank/entries",
        json={"answer_text": answer, "scenario_category": "interview", "tags": ["Impact"]},
    )

    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    assert created["scenario_category"] == "interview"
    assert created["tags"] == ["impact"]

    list_resp = await client.get("/api/v1/training-studio/storybank/entries")
    assert list_resp.status_code == 200
    entries = list_resp.json()["data"]
    assert len(entries) == 1
    assert entries[0]["id"] == created["id"]
