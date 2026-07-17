"""Application-owned realtime voice pipeline ports."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

OPENAI_REALTIME_API_KEY_ENV_KEYS = ("REALTIME_OPENAI_API_KEY", "LLM__API_KEY", "OPENAI_API_KEY")
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
    required: Mapping[str, object] = field(default_factory=dict)
    blocking_reasons: Sequence[RealtimeReadinessIssue | Mapping[str, object]] = field(
        default_factory=tuple
    )
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "status": self.status,
            "checkedAt": self.checked_at.isoformat(),
            "required": dict(sanitize_realtime_public_value(dict(self.required)) or {}),
            "blockingReasons": [
                _readiness_issue_payload(issue) for issue in self.blocking_reasons
            ],
        }


def build_realtime_readiness(
    *,
    required: Mapping[str, object],
    blocking_reasons: Sequence[RealtimeReadinessIssue | Mapping[str, object]] = (),
) -> RealtimeProviderReadiness:
    blockers = tuple(blocking_reasons)
    return RealtimeProviderReadiness(
        ready=not blockers,
        status="ready" if not blockers else "blocked",
        required=dict(required),
        blocking_reasons=blockers,
    )


def build_openai_realtime_capability_response(
    *,
    configured: bool,
    effective_key: bool,
    model: str | None,
    voice: str | None,
) -> dict[str, object]:
    """Build the public OpenAI Realtime capability/readiness response shape."""

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
    if not model:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_MODEL",
                message="Configure REALTIME_OPENAI_MODEL before starting OpenAI realtime calls",
                phase="configuration",
                provider="openaiRealtime",
                feature="model",
            )
        )
    if not voice:
        blockers.append(
            RealtimeReadinessIssue(
                code="MISSING_OPENAI_REALTIME_VOICE",
                message="Configure REALTIME_OPENAI_VOICE before starting OpenAI realtime calls",
                phase="configuration",
                provider="openaiRealtime",
                feature="voice",
            )
        )
    readiness = build_realtime_readiness(
        required={"env": OPENAI_REALTIME_API_KEY_ENV_KEYS},
        blocking_reasons=blockers,
    ).to_dict()
    return {
        "configured": configured,
        "effectiveKey": effective_key,
        "model": model,
        "voice": voice,
        "readyForCall": readiness["ready"],
        "readiness": readiness,
        "errors": readiness["blockingReasons"],
    }


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
class RealtimeTranscript:
    """Final transcript event normalized across realtime providers."""

    text: str
    role: str
    binding: RealtimeSessionBinding
    provider: str
    realtime_session_id: str
    event_type: str
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
