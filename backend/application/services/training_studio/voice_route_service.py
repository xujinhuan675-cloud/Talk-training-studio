"""Platform-managed voice route presets."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VoiceRouteMode = Literal["cascade", "speech_to_speech"]
VoiceRouteAdapterStatus = Literal["runtime_integrated", "inventory_only"]
VoiceRouteInteractionMode = Literal["turn_based", "realtime"]
VoiceRoutePresetGroup = Literal["cascade", "native_voice", "curated_demo"]

_RUNTIME_CASCADE_STT_PROVIDERS = {"openai", "volcengine.doubao"}
_RUNTIME_CASCADE_LLM_PROVIDERS = {"openai", "openrouter"}
_RUNTIME_CASCADE_TTS_PROVIDERS = {"openai", "volcengine.doubao"}
_RUNTIME_NATIVE_PROVIDERS = {"openai", "volcengine.doubao_realtime"}


class VoiceRouteServiceDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=160)
    voice: str | None = Field(default=None, max_length=160)


class VoiceRouteDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    mode: VoiceRouteMode
    enabled: bool = True
    default: bool = False
    revision: int = Field(default=1, ge=1)
    adapter_status: VoiceRouteAdapterStatus = Field(
        default="runtime_integrated", alias="adapterStatus"
    )
    interaction_modes: list[VoiceRouteInteractionMode] = Field(
        default_factory=list, alias="interactionModes"
    )
    preset_group: VoiceRoutePresetGroup | None = Field(default=None, alias="presetGroup")
    credential_env: list[str] = Field(default_factory=list, alias="credentialEnv")
    stt: VoiceRouteServiceDTO | None = None
    llm: VoiceRouteServiceDTO | None = None
    tts: VoiceRouteServiceDTO | None = None
    realtime: VoiceRouteServiceDTO | None = None
    opening_tts: VoiceRouteServiceDTO | None = Field(default=None, alias="openingTts")
    input_sample_rate: int = Field(default=16000, alias="inputSampleRate", ge=8000, le=48000)
    output_sample_rate: int = Field(default=24000, alias="outputSampleRate", ge=8000, le=48000)
    latency_profile: str = Field(default="near_realtime", alias="latencyProfile", max_length=60)
    cost_profile: str = Field(default="configured", alias="costProfile", max_length=80)

    @model_validator(mode="after")
    def validate_pipeline_shape(self) -> "VoiceRouteDTO":
        if self.mode == "cascade":
            if not (self.stt and self.llm and self.tts):
                raise ValueError("cascade voice routes require stt, llm, and tts")
            if self.realtime is not None:
                raise ValueError("cascade voice routes cannot define realtime")
            if self.adapter_status == "runtime_integrated":
                if self.stt.provider not in _RUNTIME_CASCADE_STT_PROVIDERS:
                    raise ValueError("the selected cascade STT provider is not runtime integrated")
                if self.tts.provider not in _RUNTIME_CASCADE_TTS_PROVIDERS:
                    raise ValueError("the selected cascade TTS provider is not runtime integrated")
                if self.llm.provider not in _RUNTIME_CASCADE_LLM_PROVIDERS:
                    raise ValueError("the selected cascade LLM provider is not runtime integrated")
        else:
            if self.realtime is None:
                raise ValueError("speech_to_speech voice routes require realtime")
            if any(item is not None for item in (self.stt, self.llm, self.tts)):
                raise ValueError("speech_to_speech voice routes use one realtime service")
            if (
                self.adapter_status == "runtime_integrated"
                and self.realtime.provider not in _RUNTIME_NATIVE_PROVIDERS
            ):
                raise ValueError("unsupported native realtime provider")
        allowed_modes = set(self.resolved_interaction_modes())
        if not allowed_modes:
            raise ValueError("voice routes require at least one interaction mode")
        if self.mode == "speech_to_speech" and allowed_modes != {"realtime"}:
            raise ValueError("speech-to-speech voice routes only support realtime interaction")
        expected_group = self.resolved_preset_group()
        if self.preset_group is not None and self.preset_group != expected_group:
            raise ValueError(
                f"{self.adapter_status} {self.mode} voice routes belong to {expected_group}"
            )
        return self

    def resolved_interaction_modes(self) -> tuple[VoiceRouteInteractionMode, ...]:
        if self.interaction_modes:
            return tuple(dict.fromkeys(self.interaction_modes))
        if self.mode == "speech_to_speech":
            return ("realtime",)
        return ("turn_based", "realtime")

    def supports_interaction_mode(self, mode: str) -> bool:
        return mode in self.resolved_interaction_modes()

    def resolved_preset_group(self) -> VoiceRoutePresetGroup:
        if self.adapter_status == "inventory_only":
            return "curated_demo"
        return "cascade" if self.mode == "cascade" else "native_voice"

    def to_public_dict(
        self,
        *,
        readiness: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        payload["interactionModes"] = list(self.resolved_interaction_modes())
        payload["presetGroup"] = self.resolved_preset_group()
        if readiness is not None:
            payload["readiness"] = dict(readiness)
        return payload


class VoiceRouteConfigDTO(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = Field(default=1, ge=1)
    routes: list[VoiceRouteDTO] = Field(default_factory=list)
    updated_at: str = Field(default="2026-01-01T00:00:00.000Z", alias="updatedAt")

    @model_validator(mode="after")
    def validate_routes(self) -> "VoiceRouteConfigDTO":
        ids = [route.id for route in self.routes]
        if len(ids) != len(set(ids)):
            raise ValueError("voice route ids must be unique")
        if sum(route.default and route.enabled for route in self.routes) > 1:
            raise ValueError("only one enabled voice route may be default")
        return self


class JsonFileVoiceRouteStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def load(self) -> dict | None:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Voice route config file must contain an object")
        return raw

    def save(self, state: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state, ensure_ascii=False, indent=2)
        self.path.write_text(f"{payload}\n", encoding="utf-8")


class TrainingVoiceRouteService:
    def __init__(self, store: JsonFileVoiceRouteStore | None = None) -> None:
        self._store = store

    def get_config(self) -> VoiceRouteConfigDTO:
        if self._store is None:
            return VoiceRouteConfigDTO()
        raw = self._store.load()
        return VoiceRouteConfigDTO.model_validate(raw) if raw is not None else VoiceRouteConfigDTO()

    def save_config(self, payload: VoiceRouteConfigDTO | dict) -> VoiceRouteConfigDTO:
        requested = (
            payload
            if isinstance(payload, VoiceRouteConfigDTO)
            else VoiceRouteConfigDTO.model_validate(payload)
        )
        current = self.get_config()
        previous_by_id = {route.id: route for route in current.routes}
        routes: list[VoiceRouteDTO] = []
        for route in requested.routes:
            previous = previous_by_id.get(route.id)
            if previous is None:
                revision = max(1, route.revision)
            else:
                previous_shape = previous.model_dump(exclude={"revision"})
                requested_shape = route.model_dump(exclude={"revision"})
                revision = (
                    previous.revision + 1
                    if previous_shape != requested_shape
                    else previous.revision
                )
            routes.append(route.model_copy(update={"revision": revision}))
        state = requested.model_copy(
            update={
                "version": max(current.version, requested.version) + 1,
                "routes": routes,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        if self._store is not None:
            self._store.save(state.model_dump(mode="json", by_alias=True, exclude_none=True))
        return state

    def list_published(self) -> list[VoiceRouteDTO]:
        return [route for route in self.get_config().routes if route.enabled]

    def get_published(self, route_id: str) -> VoiceRouteDTO:
        normalized = route_id.strip()
        route = next((item for item in self.list_published() if item.id == normalized), None)
        if route is None:
            raise KeyError(normalized)
        return route


def voice_route_snapshot_from_metadata(
    metadata: Mapping[str, object] | None,
) -> VoiceRouteDTO | None:
    """Validate the immutable voice route snapshot stored on a session."""

    payload = metadata.get("voiceRoute") if metadata is not None else None
    if not isinstance(payload, Mapping):
        return None
    try:
        return VoiceRouteDTO.model_validate(payload)
    except ValueError:
        return None


def voice_route_catalog_readiness(
    route: VoiceRouteDTO,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return secret-free catalog readiness for a published preset."""

    env = os.environ if environment is None else environment
    missing_credentials = [
        name for name in route.credential_env if not str(env.get(name) or "").strip()
    ]
    if route.adapter_status != "runtime_integrated":
        return {
            "status": "blocked",
            "ready": False,
            "code": "VOICE_ROUTE_ADAPTER_NOT_INTEGRATED",
            "reason": "This curated Pipecat demo is not yet connected to the TalkWise runtime.",
            "missingCredentials": missing_credentials,
            "missingDependencies": ["talkwise.runtime_adapter"],
        }
    if missing_credentials:
        return {
            "status": "blocked",
            "ready": False,
            "code": "VOICE_ROUTE_CREDENTIALS_MISSING",
            "reason": "Required provider credentials are not configured.",
            "missingCredentials": missing_credentials,
            "missingDependencies": [],
        }
    return {
        "status": "ready",
        "ready": True,
        "code": None,
        "reason": None,
        "missingCredentials": [],
        "missingDependencies": [],
    }
