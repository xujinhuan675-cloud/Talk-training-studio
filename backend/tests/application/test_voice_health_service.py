import json
from types import SimpleNamespace

from application.services.training_studio.voice_health_service import build_voice_health_report


def _voice_config() -> dict:
    return {
        "version": 1,
        "routes": [
            {
                "id": "default-cascade",
                "name": "Default cascade",
                "description": "",
                "mode": "cascade",
                "enabled": True,
                "default": True,
                "revision": 1,
                "stt": {"provider": "openai", "model": "stt-model"},
                "llm": {"provider": "openai", "model": "llm-model"},
                "tts": {"provider": "openai", "model": "tts-model", "voice": "voice"},
                "inputSampleRate": 16000,
                "outputSampleRate": 24000,
            }
        ],
        "updatedAt": "2026-08-08T00:00:00Z",
    }


def _capability(**overrides):
    values = {
        "core_available": True,
        "websocket_available": True,
        "stt_available": True,
        "tts_available": True,
        "llm_available": True,
        "openai_realtime_llm_available": True,
        "vad_available": True,
        "turn_detection_available": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_voice_health_reports_default_route_ready(tmp_path) -> None:
    path = tmp_path / "voice_routes.json"
    path.write_text(json.dumps(_voice_config()), encoding="utf-8")

    report = build_voice_health_report(
        config_path=path,
        pipecat_capability_loader=lambda **_: _capability(),
    )

    assert report["status"] == "ready"
    assert report["ready"] is True
    assert report["selectedRouteId"] == "default-cascade"
    assert report["routes"][0]["ready"] is True
    assert report["providerConnectivityCheck"] == "not_performed"


def test_voice_health_blocks_when_default_route_dependency_is_missing(tmp_path) -> None:
    path = tmp_path / "voice_routes.json"
    path.write_text(json.dumps(_voice_config()), encoding="utf-8")

    report = build_voice_health_report(
        config_path=path,
        pipecat_capability_loader=lambda **_: _capability(tts_available=False),
    )

    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["routes"][0]["missingDependencies"] == ["pipecat.tts"]


def test_voice_health_blocks_when_no_route_is_enabled(tmp_path) -> None:
    config = _voice_config()
    config["routes"][0]["enabled"] = False
    path = tmp_path / "voice_routes.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    report = build_voice_health_report(config_path=path)

    assert report["status"] == "blocked"
    assert report["error"] == "No enabled voice route is configured"
