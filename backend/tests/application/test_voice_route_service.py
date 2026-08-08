import pytest
from fastapi import HTTPException

from api.routes.training_studio import _voice_route_snapshot_for_task
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import CreateTrainingSessionDTO
from application.services.training_studio.voice_route_service import (
    JsonFileVoiceRouteStore,
    TrainingVoiceRouteService,
    VoiceRouteConfigDTO,
)


def _cascade_route() -> dict[str, object]:
    return {
        "id": "standard-cascade",
        "name": "Standard cascade",
        "description": "Balanced realtime training route",
        "mode": "cascade",
        "enabled": True,
        "default": True,
        "stt": {"provider": "openai", "model": "gpt-4o-mini-transcribe"},
        "llm": {"provider": "openai", "model": "gpt-4.1-mini"},
        "tts": {
            "provider": "openai",
            "model": "gpt-4o-mini-tts",
            "voice": "marin",
        },
        "inputSampleRate": 16000,
        "outputSampleRate": 24000,
    }


def test_voice_route_service_publishes_only_enabled_routes(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    disabled = {**_cascade_route(), "id": "disabled-route", "default": False, "enabled": False}

    saved = service.save_config({"routes": [_cascade_route(), disabled]})

    assert saved.version == 2
    assert [route.id for route in service.list_published()] == ["standard-cascade"]
    assert service.get_published("standard-cascade").llm.model == "gpt-4.1-mini"


def test_voice_route_service_increments_revision_when_a_route_changes(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    first = service.save_config(VoiceRouteConfigDTO.model_validate({"routes": [_cascade_route()]}))
    unchanged = service.save_config(first)
    changed_payload = unchanged.model_dump(mode="json", by_alias=True)
    changed_payload["routes"][0]["llm"]["model"] = "gpt-4.1"

    changed = service.save_config(changed_payload)

    assert first.routes[0].revision == 1
    assert unchanged.routes[0].revision == 1
    assert changed.routes[0].revision == 2
    assert changed.routes[0].llm.model == "gpt-4.1"


def _session_request(
    voice_route_id: str | None,
    *,
    mode: str = "realtime",
) -> CreateTrainingSessionDTO:
    metadata: dict[str, object] = {
        "interactionMode": "realtime" if mode == "realtime" else "turn_based"
    }
    if voice_route_id is not None:
        metadata["voiceRouteId"] = voice_route_id
    return CreateTrainingSessionDTO(
        mode=mode,
        task_config=TrainingTaskConfigDTO(
            role="Learner",
            level="standard",
            tech_stack=["communication"],
            question_type_ratios={"delivery": 1},
            question_count=6,
            framework="prep",
            difficulty="medium",
            category="workplace",
            metadata=metadata,
        ),
    )


def test_realtime_session_snapshots_the_published_voice_route(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    saved = service.save_config({"routes": [_cascade_route()]})

    request = _voice_route_snapshot_for_task(_session_request("standard-cascade"), service)

    assert request.task_config.metadata["voiceRouteRevision"] == saved.routes[0].revision
    assert request.task_config.metadata["voiceRoute"]["llm"]["model"] == "gpt-4.1-mini"
    assert request.task_config.metadata["realtimeProfile"] == "cascade"


def test_realtime_session_rejects_missing_voice_route() -> None:
    with pytest.raises(HTTPException, match="voiceRouteId is required") as exc_info:
        _voice_route_snapshot_for_task(_session_request(None), TrainingVoiceRouteService())

    assert exc_info.value.status_code == 422


def test_turn_based_voice_session_snapshots_the_complete_cascade(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    service.save_config({"routes": [_cascade_route()]})

    request = _voice_route_snapshot_for_task(
        _session_request("standard-cascade", mode="voice"),
        service,
    )

    assert request.task_config.metadata["voiceRouteMode"] == "cascade"
    assert request.task_config.metadata["llmModel"] == "gpt-4.1-mini"
    assert request.task_config.metadata["voiceRoute"]["stt"]["model"] == "gpt-4o-mini-transcribe"
    assert request.task_config.metadata["voiceRoute"]["tts"]["model"] == "gpt-4o-mini-tts"
    assert "realtimeProfile" not in request.task_config.metadata


def test_turn_based_voice_session_rejects_native_speech_to_speech_route(tmp_path) -> None:
    native_route = {
        "id": "native-realtime",
        "name": "Native realtime",
        "mode": "speech_to_speech",
        "enabled": True,
        "realtime": {
            "provider": "openai",
            "model": "gpt-realtime",
            "voice": "marin",
        },
    }
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    service.save_config({"routes": [native_route]})

    with pytest.raises(HTTPException, match="require a cascade voice route") as exc_info:
        _voice_route_snapshot_for_task(
            _session_request("native-realtime", mode="voice"),
            service,
        )

    assert exc_info.value.status_code == 422
