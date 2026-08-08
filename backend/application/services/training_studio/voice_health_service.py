"""Secret-free readiness summary for configured TalkWise voice routes."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from application.services.training_studio.voice_route_service import (
    JsonFileVoiceRouteStore,
    TrainingVoiceRouteService,
    VoiceRouteDTO,
)

_DEFAULT_VOICE_ROUTE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "training_studio" / "voice_routes.json"
)


def _pipecat_route_readiness(
    route: VoiceRouteDTO,
    capability: Any,
) -> tuple[bool, list[str]]:
    required = {
        "pipecat.core": bool(capability.core_available),
        "pipecat.websocket": bool(capability.websocket_available),
    }
    if route.mode == "cascade":
        required.update(
            {
                "pipecat.stt": bool(capability.stt_available),
                "pipecat.tts": bool(capability.tts_available),
                "pipecat.llm": bool(capability.llm_available),
            }
        )
    else:
        required.update(
            {
                "pipecat.realtime_llm": bool(capability.openai_realtime_llm_available),
                "pipecat.vad": bool(capability.vad_available),
                "pipecat.turn_detection": bool(capability.turn_detection_available),
            }
        )
    missing = [name for name, available in required.items() if not available]
    return not missing, missing


def _route_provider(route: VoiceRouteDTO) -> str:
    if route.realtime is not None:
        return route.realtime.provider
    return "pipecat.cascade"


def build_voice_health_report(
    *,
    config_path: Path | str | None = None,
    pipecat_capability_loader: Callable[..., Any] | None = None,
) -> dict[str, object]:
    """Check route configuration and local runtime dependencies without billable calls."""

    path = Path(config_path) if config_path is not None else _DEFAULT_VOICE_ROUTE_PATH
    service = TrainingVoiceRouteService(JsonFileVoiceRouteStore(path))
    try:
        routes = service.list_published()
    except Exception as exc:
        return {
            "status": "blocked",
            "ready": False,
            "verificationLevel": "configuration_and_local_runtime",
            "selectedRouteId": None,
            "routes": [],
            "error": f"Voice route configuration is invalid: {exc.__class__.__name__}",
        }

    if not routes:
        return {
            "status": "blocked",
            "ready": False,
            "verificationLevel": "configuration_and_local_runtime",
            "selectedRouteId": None,
            "routes": [],
            "error": "No enabled voice route is configured",
        }

    selected = next((route for route in routes if route.default), routes[0])
    capability_loader = pipecat_capability_loader
    pipecat_capability: Any | None = None
    checks: list[dict[str, object]] = []

    for route in routes:
        provider = _route_provider(route)
        missing: list[str] = []
        if provider == "volcengine.doubao_realtime":
            ready = importlib.util.find_spec("websockets") is not None
            if not ready:
                missing.append("websockets")
        else:
            if pipecat_capability is None and capability_loader is not None:
                try:
                    pipecat_capability = capability_loader(require_websocket=True)
                except Exception:
                    pipecat_capability = None
            if pipecat_capability is None:
                ready = False
                missing.append("pipecat.runtime")
            else:
                ready, missing = _pipecat_route_readiness(route, pipecat_capability)

        checks.append(
            {
                "id": route.id,
                "name": route.name,
                "mode": route.mode,
                "provider": provider,
                "default": route.default,
                "ready": ready,
                "missingDependencies": missing,
            }
        )

    selected_check = next(check for check in checks if check["id"] == selected.id)
    ready = bool(selected_check["ready"])
    return {
        "status": "ready" if ready else "blocked",
        "ready": ready,
        "verificationLevel": "configuration_and_local_runtime",
        "selectedRouteId": selected.id,
        "routes": checks,
        "credentialCheck": "deferred_to_authenticated_request",
        "providerConnectivityCheck": "not_performed",
        "error": None if ready else "The selected voice route is not locally ready",
    }
