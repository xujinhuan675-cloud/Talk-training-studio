"""Application-owned realtime voice pipeline ports."""

from __future__ import annotations

import re
import base64
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

REALTIME_EVENT_SCHEMA_VERSION = 1
REALTIME_RUNTIME_PIPECAT = "pipecat"
REALTIME_RUNTIME_OPENAI = "openai_realtime"
REALTIME_RUNTIME_TALKWISE_LOCAL = "talkwise_local"
OPENAI_REALTIME_API_KEY_ENV_KEYS = ("REALTIME_OPENAI_API_KEY", "LLM__API_KEY", "OPENAI_API_KEY")
OPENAI_REALTIME_MODEL_ENV_KEYS = ("REALTIME_OPENAI_MODEL",)
OPENAI_REALTIME_VOICE_ENV_KEYS = ("REALTIME_OPENAI_VOICE",)
OPENAI_REALTIME_INPUT_AUDIO_FORMAT_ENV_KEYS = ("REALTIME_OPENAI_INPUT_AUDIO_FORMAT",)
_SENSITIVE_REALTIME_METADATA_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "auth_header",
    "authtoken",
    "auth_token",
    "bearer_token",
    "bearertoken",
    "client_secret",
    "clientsecret",
    "credential",
    "credentials",
    "default_headers",
    "openai_api_key",
    "openaiapikey",
    "password",
    "private_key",
    "privatekey",
    "proxy_authorization",
    "refresh_token",
    "refreshtoken",
    "secret",
    "token",
}
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)(\bbearer\s+)[^\s,;}\]]+"),
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{3,}\b"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|apikey|openaiapikey|authorization|password|secret|token)"
        r"\s*[:=]\s*)[^\s,;}\]]+"
    ),
)


def _normalized_realtime_name(value: object | None) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def realtime_runtime_for_provider(provider: object | None) -> str:
    """Return the public realtime runtime family for a provider alias."""

    normalized = _normalized_realtime_name(provider)
    if normalized in {"pipecat", "pipecat_pipeline"}:
        return REALTIME_RUNTIME_PIPECAT
    if normalized in {"openai", "openai_realtime", "openai_webrtc"}:
        return REALTIME_RUNTIME_OPENAI
    if normalized in {"", "local", "talkwise", "talkwise_local"}:
        return REALTIME_RUNTIME_TALKWISE_LOCAL
    return normalized


def normalize_realtime_runtime(
    runtime: object | None,
    *,
    provider: object | None = None,
) -> str:
    """Normalize a runtime value, falling back to the provider family."""

    normalized = _normalized_realtime_name(runtime)
    if normalized in {"realtime_voice", "voice", "training_voice"}:
        return realtime_runtime_for_provider(provider)
    return normalized or realtime_runtime_for_provider(provider)


def _metadata_key_forms(key: object) -> tuple[str, str]:
    lowered = str(key).lower()
    snake = "".join(ch if ch.isalnum() else "_" for ch in lowered).strip("_")
    compact = "".join(ch for ch in lowered if ch.isalnum())
    return snake, compact


def is_sensitive_realtime_metadata_key(key: object) -> bool:
    """Return whether a public realtime payload key would expose credentials."""

    snake, compact = _metadata_key_forms(key)
    if snake in _SENSITIVE_REALTIME_METADATA_KEYS or compact in _SENSITIVE_REALTIME_METADATA_KEYS:
        return True
    return snake.endswith(("_api_key", "_authorization", "_password", "_secret", "_token")) or (
        compact.endswith(("apikey", "authorization", "password", "secret", "token"))
    )


def redact_realtime_secret_text(value: str) -> str:
    """Redact common credential shapes embedded in provider messages."""

    redacted = value
    redacted = _SECRET_TEXT_PATTERNS[0].sub(r"\1***", redacted)
    redacted = _SECRET_TEXT_PATTERNS[1].sub("sk-***", redacted)
    redacted = _SECRET_TEXT_PATTERNS[2].sub(r"\1***", redacted)
    return redacted


def sanitize_realtime_public_value(value: object) -> object | None:
    """Return a JSON-safe public realtime value with credential-bearing keys removed."""

    if isinstance(value, str):
        return redact_realtime_secret_text(value)
    if isinstance(value, int | float | bool):
        return value
    if value is None:
        return None
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for raw_key, nested_value in value.items():
            if is_sensitive_realtime_metadata_key(raw_key):
                continue
            safe_value = sanitize_realtime_public_value(nested_value)
            if safe_value is not None:
                sanitized[str(raw_key)] = safe_value
        return sanitized or None
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        sanitized_items = [
            safe_item
            for item in value
            if (safe_item := sanitize_realtime_public_value(item)) is not None
        ]
        return sanitized_items or None
    return None


@dataclass(frozen=True)
class RealtimeReadinessIssue:
    """Structured, public-safe reason a realtime provider cannot start a call."""

    code: str
    message: str
    phase: str
    provider: str | None = None
    feature: str | None = None
    modules: Sequence[str] = field(default_factory=tuple)
    missing_env: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "message": redact_realtime_secret_text(self.message),
            "phase": self.phase,
        }
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.feature is not None:
            payload["feature"] = self.feature
        if self.modules:
            payload["modules"] = [str(module) for module in self.modules]
        if self.missing_env:
            payload["missingEnv"] = [str(key) for key in self.missing_env]
        safe_metadata = sanitize_realtime_public_value(dict(self.metadata))
        if isinstance(safe_metadata, dict) and safe_metadata:
            payload["metadata"] = safe_metadata
        return payload


@dataclass(frozen=True)
class RealtimeProviderReadiness:
    """Provider-neutral readiness block for capability responses."""

    ready: bool
    status: str
    runtime: str | None = None
    required: Mapping[str, object] = field(default_factory=dict)
    blocking_reasons: Sequence[RealtimeReadinessIssue | Mapping[str, object]] = field(
        default_factory=tuple
    )
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "ready": self.ready,
            "status": self.status,
            "checkedAt": self.checked_at.isoformat(),
            "required": dict(sanitize_realtime_public_value(dict(self.required)) or {}),
            "blockingReasons": [
                _readiness_issue_payload(issue) for issue in self.blocking_reasons
            ],
        }
        if self.runtime is not None:
            payload["runtime"] = self.runtime
        return payload


def build_realtime_readiness(
    *,
    required: Mapping[str, object],
    blocking_reasons: Sequence[RealtimeReadinessIssue | Mapping[str, object]] = (),
    runtime: str | None = None,
) -> RealtimeProviderReadiness:
    blockers = tuple(blocking_reasons)
    return RealtimeProviderReadiness(
        ready=not blockers,
        status="ready" if not blockers else "blocked",
        runtime=runtime,
        required=dict(required),
        blocking_reasons=blockers,
    )


def build_openai_realtime_capability_response(
    *,
    configured: bool,
    effective_key: bool,
    model: str | None,
    voice: str | None,
    input_audio_format: str | None = None,
) -> dict[str, object]:
    """Build the public OpenAI Realtime capability/readiness response shape."""

    resolved_model = _clean_realtime_text(model)
    resolved_voice = _clean_realtime_text(voice)
    resolved_input_audio_format = _clean_realtime_text(input_audio_format)

    blockers: list[RealtimeReadinessIssue] = []
    if not effective_key:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_API_KEY",
                message=(
                    "Set REALTIME_OPENAI_API_KEY, LLM__API_KEY, or OPENAI_API_KEY "
                    "before starting OpenAI realtime calls"
                ),
                phase="configuration",
                provider="openaiRealtime",
                missing_env=OPENAI_REALTIME_API_KEY_ENV_KEYS,
            )
        )
    if not resolved_model:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_MODEL",
                message="Configure REALTIME_OPENAI_MODEL before starting OpenAI realtime calls",
                phase="configuration",
                provider="openaiRealtime",
                feature="model",
                missing_env=OPENAI_REALTIME_MODEL_ENV_KEYS,
            )
        )
    if not resolved_voice:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_VOICE",
                message="Configure REALTIME_OPENAI_VOICE before starting OpenAI realtime calls",
                phase="configuration",
                provider="openaiRealtime",
                feature="voice",
                missing_env=OPENAI_REALTIME_VOICE_ENV_KEYS,
            )
        )
    if not resolved_input_audio_format:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_AUDIO_FORMAT",
                message=(
                    "Configure REALTIME_OPENAI_INPUT_AUDIO_FORMAT before starting "
                    "OpenAI realtime calls"
                ),
                phase="configuration",
                provider="openaiRealtime",
                feature="audioFormat",
                missing_env=OPENAI_REALTIME_INPUT_AUDIO_FORMAT_ENV_KEYS,
            )
        )
    readiness = build_realtime_readiness(
        required={
            "env": OPENAI_REALTIME_API_KEY_ENV_KEYS,
            "model": resolved_model,
            "voice": resolved_voice,
            "inputAudioFormat": resolved_input_audio_format,
        },
        blocking_reasons=blockers,
        runtime=REALTIME_RUNTIME_OPENAI,
    ).to_dict()
    return {
        "runtime": REALTIME_RUNTIME_OPENAI,
        "configured": bool(configured and resolved_input_audio_format),
        "effectiveKey": effective_key,
        "model": resolved_model,
        "voice": resolved_voice,
        "inputAudioFormat": resolved_input_audio_format,
        "readyForCall": readiness["ready"],
        "readiness": readiness,
        "errors": readiness["blockingReasons"],
    }


def _clean_realtime_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _readiness_issue_payload(
    issue: RealtimeReadinessIssue | Mapping[str, object],
) -> dict[str, object]:
    if isinstance(issue, RealtimeReadinessIssue):
        return issue.to_dict()
    safe_issue = sanitize_realtime_public_value(dict(issue))
    return dict(safe_issue) if isinstance(safe_issue, dict) else {}


@dataclass(frozen=True)
class RealtimeSessionBinding:
    """Training session and chat room binding for a realtime voice call."""

    training_session_id: str
    room_id: int


@dataclass(frozen=True)
class TrainingVoiceContext:
    """Context injected into a realtime pipeline before live media starts."""

    binding: RealtimeSessionBinding
    task_goal: str | None = None
    rubric: Mapping[str, object] = field(default_factory=dict)
    recent_turns: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RealtimePipelineConfig:
    """Provider-neutral configuration for a realtime voice pipeline."""

    provider: str
    runtime: str | None = None
    model: str | None = None
    voice: str | None = None
    input_audio_format: str | None = None
    output_audio_format: str | None = None
    instructions: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RealtimePipelineCapability:
    """Declared capability boundary for a realtime voice pipeline provider."""

    provider: str
    core_available: bool
    media_transport: str
    runtime: str = REALTIME_RUNTIME_PIPECAT
    stt: str | None = None
    tts: str | None = None
    vad: str | None = None
    turn_detection: str | None = None
    missing_features: Sequence[str] = field(default_factory=tuple)
    ready_for_call: bool | None = None
    readiness: RealtimeProviderReadiness | Mapping[str, object] | None = None
    errors: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)

    def readiness_payload(self) -> dict[str, object] | None:
        if isinstance(self.readiness, RealtimeProviderReadiness):
            return self.readiness.to_dict()
        if isinstance(self.readiness, Mapping):
            safe_value = sanitize_realtime_public_value(dict(self.readiness))
            return dict(safe_value) if isinstance(safe_value, dict) else None
        return None


@dataclass(frozen=True)
class RealtimeAudioChunk:
    """Audio chunk accepted by a realtime transport or pipeline."""

    data: bytes
    mime_type: str | None = None
    sequence: int | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RealtimeOutputAudio:
    """Provider-neutral audio chunk emitted by a realtime runtime."""

    data: bytes
    provider: str
    runtime: str | None = None
    mime_type: str | None = None
    sequence: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    context_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_event(self) -> dict[str, object]:
        resolved_runtime = normalize_realtime_runtime(self.runtime, provider=self.provider)
        encoded = base64.b64encode(self.data).decode("ascii")
        payload: dict[str, object] = {
            "schemaVersion": REALTIME_EVENT_SCHEMA_VERSION,
            "runtime": resolved_runtime,
            "provider": self.provider,
            "audio": encoded,
            "encoding": "base64",
            "bytes": len(self.data),
        }
        if self.mime_type is not None:
            payload["mimeType"] = self.mime_type
        if self.sample_rate is not None:
            payload["sampleRate"] = self.sample_rate
        if self.channels is not None:
            payload["channels"] = self.channels
        if self.sequence is not None:
            payload["sequence"] = self.sequence
        if self.context_id is not None:
            payload["contextId"] = self.context_id
        safe_metadata = sanitize_realtime_public_value(dict(self.metadata))
        if isinstance(safe_metadata, dict) and safe_metadata:
            payload["metadata"] = safe_metadata

        event: dict[str, object] = {
            "type": "audio.output",
            "schemaVersion": REALTIME_EVENT_SCHEMA_VERSION,
            "runtime": resolved_runtime,
            "provider": self.provider,
            "source": resolved_runtime,
            "payload": payload,
            "audio": encoded,
            "encoding": "base64",
            "bytes": len(self.data),
        }
        for key in ("mimeType", "sampleRate", "channels", "sequence", "contextId", "metadata"):
            if key in payload:
                event[key] = payload[key]
        return event


@dataclass(frozen=True)
class RealtimeTranscript:
    """Final transcript event normalized across realtime providers."""

    text: str
    role: str
    binding: RealtimeSessionBinding
    provider: str
    realtime_session_id: str
    event_type: str
    runtime: str | None = None
    event_id: str | None = None
    item_id: str | None = None
    response_id: str | None = None
    is_final: bool = True
    metadata: Mapping[str, object] = field(default_factory=dict)
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class PersistedRealtimeTranscript:
    """Result returned by transcript sinks after durable persistence."""

    transcript: RealtimeTranscript
    message_id: str | int | None = None
    payload: Mapping[str, object] = field(default_factory=dict)


@runtime_checkable
class RealtimeTransportAdapter(Protocol):
    """Low-level bidirectional media transport adapter.

    Existing OpenAI Realtime websocket clients can satisfy this protocol
    directly. Pipecat pipelines can sit above it or replace it behind the
    RealtimePipelineAdapter protocol.
    """

    async def connect(self) -> None:
        ...

    async def append_audio(self, audio: bytes) -> None:
        ...

    async def commit_audio(self) -> None:
        ...

    async def receive_event(self) -> Mapping[str, Any] | None:
        ...

    async def close(self) -> None:
        ...


@runtime_checkable
class RealtimePipelineAdapter(Protocol):
    """Provider-neutral realtime voice pipeline boundary."""

    async def start(self, context: TrainingVoiceContext, config: RealtimePipelineConfig) -> None:
        ...

    async def append_audio(self, chunk: RealtimeAudioChunk) -> None:
        ...

    async def commit_audio(self) -> None:
        ...

    def events(self) -> AsyncIterator[Mapping[str, Any]]:
        ...

    async def close(self) -> None:
        ...


@runtime_checkable
class TrainingContextInjector(Protocol):
    """Build training context for a realtime voice pipeline."""

    async def build_context(self, binding: RealtimeSessionBinding) -> TrainingVoiceContext:
        ...


@runtime_checkable
class TrainingTranscriptSink(Protocol):
    """Persist normalized transcripts without depending on a transport."""

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
        ...
