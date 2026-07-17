"""Application-owned realtime voice pipeline ports."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable


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
    metadata: Mapping[str, object] = field(default_factory=dict)


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
