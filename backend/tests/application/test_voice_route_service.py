from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes.training_studio import (
    _training_opening_voice_id,
    _voice_route_snapshot_for_task,
)
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import CreateTrainingSessionDTO
from application.services.training_studio.voice_route_service import (
    JsonFileVoiceRouteStore,
    TrainingVoiceRouteService,
    VoiceRouteConfigDTO,
    VoiceRouteDTO,
    voice_route_catalog_readiness,
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


def test_cascade_interaction_capability_is_explicit_not_inferred_from_mode() -> None:
    route = VoiceRouteDTO.model_validate(
        {**_cascade_route(), "interactionModes": ["turn_based"]}
    )

    assert route.supports_interaction_mode("turn_based") is True
    assert route.supports_interaction_mode("realtime") is False
    assert route.to_public_dict()["presetGroup"] == "cascade"


def test_voice_route_rejects_a_preset_group_that_conflicts_with_its_contract() -> None:
    with pytest.raises(ValueError, match="belong to cascade"):
        VoiceRouteDTO.model_validate(
            {
                **_cascade_route(),
                "adapterStatus": "inventory_only",
                "presetGroup": "realtime",
            }
        )


def _session_request(
    voice_route_id: str | None,
    *,
    mode: str = "voice",
    interaction_mode: str = "realtime",
) -> CreateTrainingSessionDTO:
    metadata: dict[str, object] = {"interactionMode": interaction_mode}
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


def test_legacy_realtime_mode_still_reads_and_snapshots_a_supported_route(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    service.save_config({"routes": [_cascade_route()]})

    request = _voice_route_snapshot_for_task(
        _session_request("standard-cascade", mode="realtime"),
        service,
    )

    assert request.mode == "realtime"
    assert request.task_config.metadata["interactionMode"] == "realtime"
    assert request.task_config.metadata["voiceRoute"]["id"] == "standard-cascade"


def test_realtime_session_rejects_missing_voice_route() -> None:
    with pytest.raises(HTTPException, match="voiceRouteId is required") as exc_info:
        _voice_route_snapshot_for_task(_session_request(None), TrainingVoiceRouteService())

    assert exc_info.value.status_code == 422


def test_turn_based_voice_session_snapshots_the_complete_cascade(tmp_path) -> None:
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    service.save_config({"routes": [_cascade_route()]})

    request = _voice_route_snapshot_for_task(
        _session_request("standard-cascade", interaction_mode="turn_based"),
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
            _session_request("native-realtime", interaction_mode="turn_based"),
            service,
        )

    assert exc_info.value.status_code == 422


def test_default_catalog_contains_only_four_integrated_routes_and_curated_demos() -> None:
    path = Path(__file__).resolve().parents[2] / "data" / "training_studio" / "voice_routes.json"
    routes = TrainingVoiceRouteService(JsonFileVoiceRouteStore(path)).get_config().routes

    curated_demo_ids = {
        "pipecat-soniox-openai-gradium",
        "pipecat-gradium-openai-gradium",
        "pipecat-soniox-openai-cartesia",
        "pipecat-aws-nova-sonic",
        "pipecat-deepgram-gemini3-google-chirp3",
        "pipecat-deepgram-google-google-chirp3",
        "pipecat-speechmatics-nova-pro-elevenlabs",
        "pipecat-gemini-live",
    }

    assert len(routes) == 12
    assert {route.id for route in routes if route.adapter_status == "runtime_integrated"} == {
        "openai-cascade-standard",
        "openai-realtime-standard",
        "doubao-realtime-standard",
        "openai-llm-doubao-voice",
    }
    assert {
        route.id for route in routes if route.adapter_status == "inventory_only"
    } == curated_demo_ids
    assert {
        group: sum(route.resolved_preset_group() == group for route in routes)
        for group in ("cascade", "realtime")
    } == {"cascade": 8, "realtime": 4}
    assert {
        route.id
        for route in routes
        if route.adapter_status == "inventory_only" and route.mode == "cascade"
    } == {
        "pipecat-soniox-openai-gradium",
        "pipecat-gradium-openai-gradium",
        "pipecat-soniox-openai-cartesia",
        "pipecat-deepgram-gemini3-google-chirp3",
        "pipecat-deepgram-google-google-chirp3",
        "pipecat-speechmatics-nova-pro-elevenlabs",
    }
    assert {
        route.id
        for route in routes
        if route.adapter_status == "inventory_only" and route.mode == "speech_to_speech"
    } == {"pipecat-aws-nova-sonic", "pipecat-gemini-live"}
    assert next(
        route for route in routes if route.id == "openai-llm-doubao-voice"
    ).resolved_interaction_modes() == ("turn_based", "realtime")
    assert next(
        route for route in routes if route.id == "openai-cascade-standard"
    ).resolved_interaction_modes() == ("turn_based", "realtime")

    default_route = next(route for route in routes if route.default)
    assert default_route.id == "openai-llm-doubao-voice"
    assert default_route.revision == 5
    assert default_route.llm is not None
    assert default_route.llm.model == "doubao-seed-2-0-mini-260428"
    assert voice_route_catalog_readiness(default_route, environment={})["ready"] is True

    for route in routes:
        assert route.preset_group == route.resolved_preset_group()
        assert route.to_public_dict()["presetGroup"] == route.resolved_preset_group()

    for route_id in ("openai-realtime-standard", "doubao-realtime-standard"):
        route = next(route for route in routes if route.id == route_id)
        assert route.opening_tts is not None
        assert route.realtime is not None
        assert route.opening_tts.voice == route.realtime.voice
        assert _training_opening_voice_id(route, {}) == route.realtime.voice


def test_inventory_only_demo_is_published_but_cannot_start(tmp_path) -> None:
    demo = {
        "id": "pipecat-soniox-openai-gradium",
        "name": "Soniox + OpenAI + Gradium",
        "mode": "cascade",
        "enabled": True,
        "adapterStatus": "inventory_only",
        "interactionModes": ["realtime"],
        "credentialEnv": ["SONIOX_API_KEY", "GRADIUM_API_KEY"],
        "stt": {"provider": "soniox", "model": "stt"},
        "llm": {"provider": "openai", "model": "gpt"},
        "tts": {"provider": "gradium", "model": "tts"},
    }
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(tmp_path / "voice-routes.json"))
    service.save_config({"routes": [demo]})
    route = service.get_published(demo["id"])

    readiness = voice_route_catalog_readiness(route, environment={})
    assert readiness["ready"] is False
    assert readiness["code"] == "VOICE_ROUTE_ADAPTER_NOT_INTEGRATED"
    assert readiness["missingCredentials"] == ["SONIOX_API_KEY", "GRADIUM_API_KEY"]
    configured_readiness = voice_route_catalog_readiness(
        route,
        environment={"SONIOX_API_KEY": "configured", "GRADIUM_API_KEY": "configured"},
    )
    assert configured_readiness["ready"] is False
    assert configured_readiness["missingCredentials"] == []
    with pytest.raises(HTTPException, match="not yet connected") as exc_info:
        _voice_route_snapshot_for_task(_session_request(demo["id"]), service)
    assert exc_info.value.status_code == 422
