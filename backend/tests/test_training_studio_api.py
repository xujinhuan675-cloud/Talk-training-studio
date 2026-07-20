"""API tests for Training Studio catalog and storybank endpoints."""

from __future__ import annotations

import asyncio
import json
import os
from itertools import count
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from api.dependencies import (
    get_analysis_reader_service,
    get_analysis_service,
    get_chatroom_service,
    get_growth_service,
    reset_ai_rate_limit_state,
)
import api.routes.training_studio as training_studio_routes
from api.routes.training_studio import (
    get_live_guidance_service,
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
from core.config import VoiceSettings, settings
from core.exceptions import register_exception_handlers
from domain.training_studio.storybank import StoryBankService


class FakeReport(BaseModel):
    id: int
    room_id: int
    summary: str = "Good practice report"
    content: dict = Field(default_factory=dict)


class FakeAnalysisService:
    def __init__(self) -> None:
        self.generated_for: list[int] = []

    async def generate_report(self, room_id: int) -> FakeReport:
        self.generated_for.append(room_id)
        return FakeReport(id=501, room_id=room_id)


class FakeAnalysisReaderService:
    def __init__(self) -> None:
        self.reports: dict[int, FakeReport] = {}
        self.requested_ids: list[int] = []

    async def get_report(self, report_id: int) -> FakeReport | None:
        self.requested_ids.append(report_id)
        return self.reports.get(report_id)


class FakeGrowthService:
    def __init__(self) -> None:
        self.evaluated: list[int] = []

    async def evaluate_competency(self, report_id: int) -> None:
        self.evaluated.append(report_id)


class FakeChatroomService:
    def __init__(self) -> None:
        self.created_rooms: list[object] = []
        self.details: dict[int, ChatRoomDetailDTO] = {}
        self.detail_calls: list[tuple[int, int]] = []

    async def create_room(self, dto):
        self.created_rooms.append(dto)
        return SimpleNamespace(id=701)

    async def get_room_detail(self, room_id: int, *, message_limit: int = 50) -> ChatRoomDetailDTO:
        self.detail_calls.append((room_id, message_limit))
        return self.details[room_id]


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


class FakeTrainingRuntimeUnitOfWork:
    def __init__(self, state, **kwargs) -> None:
        self._state = state
        self._kwargs = kwargs
        self.conversation_repository = FakeTrainingRuntimeConversationRepository(state)

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
    runtime_state = SimpleNamespace(created_conversations=[])
    analysis_service = FakeAnalysisService()
    reader_service = FakeAnalysisReaderService()
    growth_service = FakeGrowthService()
    chatroom_service = FakeChatroomService()
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
    test_app.state.scenario_config_service = scenario_config_service
    test_app.state.training_session_service = session_service
    test_app.state.guidance_service = guidance_service
    test_app.state.analysis_service = analysis_service
    test_app.state.analysis_reader_service = reader_service
    test_app.state.growth_service = growth_service
    test_app.state.chatroom_service = chatroom_service
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
    new_customer = by_id["new-customer-discount"]
    assert new_customer["title"]
    assert new_customer["category"] == "sales"
    assert new_customer["difficulty"] == "easy"
    assert new_customer["required"] is True
    assert new_customer["status"] == "not_started"
    assert new_customer["opening_line"]
    assert new_customer["persona"]["name"]
    assert len(new_customer["training_points"]) >= 1

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
async def test_scenario_config_admin_and_leader_can_save(client: AsyncClient) -> None:
    for mock_user in ("admin", "leader"):
        payload = await read_scenario_config_state(client)
        payload["scenarios"][0]["dimensionWeights"] = scenario_dimension_weights()

        resp = await client.put(
            "/api/v1/training-studio/scenario-config",
            headers={"X-Mock-User": mock_user},
            json=payload,
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["scenarios"][0]["dimensionWeights"] == scenario_dimension_weights()


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
async def test_voice_config_save_writes_env_and_reloads_clients(
    client: AsyncClient,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\nVOICE__TTS_PROVIDER=minimax\n", encoding="utf-8")
    voice_env_keys = [
        "VOICE__TTS_PROVIDER",
        "VOICE__TTS_BASE_URL",
        "VOICE__TTS_MODEL",
        "VOICE__TTS_API_KEY",
        "VOICE__STT_PROVIDER",
        "VOICE__STT_BASE_URL",
        "VOICE__STT_MODEL",
        "VOICE__STT_API_KEY",
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
        monkeypatch.setattr(training_studio_routes, "_settings_env_file_path", lambda: env_file)
        monkeypatch.setattr(training_studio_routes, "_reload_voice_clients", fake_reload_voice_clients)
        monkeypatch.setattr(training_studio_routes, "_reload_llm_client", fake_reload_llm_client)
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
        settings.REALTIME_OPENAI_MODEL = "gpt-realtime"
        settings.REALTIME_OPENAI_VOICE = "marin"
        settings.REALTIME_OPENAI_TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

        resp = await client.put(
            "/api/v1/training-studio/voice-config",
            headers={"X-Mock-User": "admin"},
            json={
                "llm_base_url": "https://ai.flowguide.cc",
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
                "realtime_api_key": "sk-realtime-5678",
                "realtime_model": "gpt-realtime",
                "realtime_voice": "marin",
                "realtime_transcription_model": "gpt-realtime-whisper",
            },
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_base_url"] == "https://ai.flowguide.cc"
        assert data["llm_default_model"] == "gpt-5.5"
        assert data["llm_api_key_preview"] == "***9999"
        assert data["tts_provider"] == "openrouter"
        assert data["tts_api_key_preview"] == "***1234"
        assert data["stt_api_key_source"] == "tts"
        assert data["realtime_api_key_preview"] == "***5678"
        assert "sk-openrouter-1234" not in resp.text
        assert "sk-realtime-5678" not in resp.text
        assert "sk-flowguide-9999" not in resp.text
        assert reloads == [True, True]

        env_text = env_file.read_text(encoding="utf-8")
        assert "LLM__BASE_URL=https://ai.flowguide.cc" in env_text
        assert "LLM__DEFAULT_MODEL=gpt-5.5" in env_text
        assert "LLM__WIRE_API=responses" in env_text
        assert "LLM__API_KEY=sk-flowguide-9999" in env_text
        assert "VOICE__TTS_PROVIDER=openrouter" in env_text
        assert "VOICE__TTS_API_KEY=sk-openrouter-1234" in env_text
        assert "VOICE__STT_API_KEY=" in env_text
        assert "REALTIME_OPENAI_API_KEY=sk-realtime-5678" in env_text
        assert settings.llm.api_key == "sk-flowguide-9999"
        assert settings.llm.base_url == "https://ai.flowguide.cc"
        assert settings.llm.default_model == "gpt-5.5"
        assert settings.voice.tts_provider == "openrouter"
        assert settings.voice.stt_api_key == "sk-openrouter-1234"
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


def admin_team_headers(team_id: str) -> dict[str, str]:
    return {
        "X-User-Id": "user-admin-001",
        "X-System-Role": "admin",
        "X-Team-Id": team_id,
    }


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
async def test_leader_scenario_progress_is_limited_to_own_team(client: AsyncClient) -> None:
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
    assert [item["team_id"] for item in data] == ["team-revenue"]
    assert [item["scenario_id"] for item in data] == ["revenue-scenario"]


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

    app.state.analysis_reader_service.reports[501] = FakeReport(id=501, room_id=42)
    report_resp = await client.get(f"/api/v1/training-studio/sessions/{session_id}/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["data"]["id"] == 501


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
    stored = await app.state.training_session_service.get_session(session_id)
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
    stored = await app.state.training_session_service.get_session(session_id)
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
        session = await app.state.training_session_service.get_session(session_id)
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
