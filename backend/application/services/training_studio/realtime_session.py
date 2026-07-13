"""Pure application-layer realtime session state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4


class RealtimeSessionStatus(StrEnum):
    IDLE = "idle"
    PREPARING = "preparing"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    CLOSED = "closed"
    ERROR = "error"


class RealtimeEventType(StrEnum):
    SESSION_STARTED = "session.started"
    AUDIO_INPUT = "audio.input"
    AUDIO_COMMITTED = "audio.committed"
    TRANSCRIPT_DELTA = "transcript.delta"
    TRANSCRIPT_DONE = "transcript.done"
    AUDIO_OUTPUT = "audio.output"
    STATUS_CHANGED = "status.changed"
    ERROR = "error"
    SESSION_CLOSED = "session.closed"


@dataclass(frozen=True)
class RealtimeEvent:
    type: RealtimeEventType
    session_id: str
    status: RealtimeSessionStatus
    payload: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class RealtimeSessionStateError(ValueError):
    """Raised when a realtime session receives an invalid transition."""


class RealtimeSession:
    """Small state machine for future WebSocket/audio adapters.

    This class intentionally owns no database or network dependency. API routes
    and adapters can translate socket frames into these command methods.
    """

    _ALLOWED_TRANSITIONS: dict[RealtimeSessionStatus, set[RealtimeSessionStatus]] = {
        RealtimeSessionStatus.IDLE: {
            RealtimeSessionStatus.PREPARING,
            RealtimeSessionStatus.CLOSED,
            RealtimeSessionStatus.ERROR,
        },
        RealtimeSessionStatus.PREPARING: {
            RealtimeSessionStatus.LISTENING,
            RealtimeSessionStatus.PROCESSING,
            RealtimeSessionStatus.CLOSED,
            RealtimeSessionStatus.ERROR,
        },
        RealtimeSessionStatus.LISTENING: {
            RealtimeSessionStatus.PROCESSING,
            RealtimeSessionStatus.CLOSED,
            RealtimeSessionStatus.ERROR,
        },
        RealtimeSessionStatus.PROCESSING: {
            RealtimeSessionStatus.LISTENING,
            RealtimeSessionStatus.SPEAKING,
            RealtimeSessionStatus.CLOSED,
            RealtimeSessionStatus.ERROR,
        },
        RealtimeSessionStatus.SPEAKING: {
            RealtimeSessionStatus.LISTENING,
            RealtimeSessionStatus.PROCESSING,
            RealtimeSessionStatus.CLOSED,
            RealtimeSessionStatus.ERROR,
        },
        RealtimeSessionStatus.ERROR: {
            RealtimeSessionStatus.CLOSED,
        },
        RealtimeSessionStatus.CLOSED: set(),
    }

    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or str(uuid4())
        self.status = RealtimeSessionStatus.IDLE
        self.events: list[RealtimeEvent] = []
        self.input_sequence = 0
        self.output_sequence = 0

    def start(self, metadata: dict[str, object] | None = None) -> RealtimeEvent:
        self._transition(RealtimeSessionStatus.PREPARING)
        return self._record(RealtimeEventType.SESSION_STARTED, metadata or {})

    def listen(self) -> RealtimeEvent:
        self._transition(RealtimeSessionStatus.LISTENING)
        return self._record(RealtimeEventType.STATUS_CHANGED)

    def receive_audio(self, data: bytes, mime_type: str | None = None) -> RealtimeEvent:
        if self.status not in {RealtimeSessionStatus.PREPARING, RealtimeSessionStatus.LISTENING}:
            raise RealtimeSessionStateError(f"Cannot receive audio while {self.status.value}")
        if self.status == RealtimeSessionStatus.PREPARING:
            self._transition(RealtimeSessionStatus.LISTENING)
        self.input_sequence += 1
        return self._record(
            RealtimeEventType.AUDIO_INPUT,
            {
                "bytes": len(data),
                "mime_type": mime_type,
                "sequence": self.input_sequence,
            },
        )

    def commit_audio(self) -> RealtimeEvent:
        self._transition(RealtimeSessionStatus.PROCESSING)
        return self._record(RealtimeEventType.AUDIO_COMMITTED, {"sequence": self.input_sequence})

    def transcript_delta(self, text: str) -> RealtimeEvent:
        if self.status != RealtimeSessionStatus.PROCESSING:
            raise RealtimeSessionStateError(f"Cannot emit transcript delta while {self.status.value}")
        return self._record(RealtimeEventType.TRANSCRIPT_DELTA, {"text": text})

    def transcript_done(self, text: str) -> RealtimeEvent:
        if self.status != RealtimeSessionStatus.PROCESSING:
            raise RealtimeSessionStateError(f"Cannot finish transcript while {self.status.value}")
        return self._record(RealtimeEventType.TRANSCRIPT_DONE, {"text": text})

    def send_audio(self, data: bytes, mime_type: str | None = None) -> RealtimeEvent:
        if self.status == RealtimeSessionStatus.PROCESSING:
            self._transition(RealtimeSessionStatus.SPEAKING)
        elif self.status != RealtimeSessionStatus.SPEAKING:
            raise RealtimeSessionStateError(f"Cannot send audio while {self.status.value}")
        self.output_sequence += 1
        return self._record(
            RealtimeEventType.AUDIO_OUTPUT,
            {
                "bytes": len(data),
                "mime_type": mime_type,
                "sequence": self.output_sequence,
            },
        )

    def close(self, reason: str | None = None) -> RealtimeEvent:
        self._transition(RealtimeSessionStatus.CLOSED)
        return self._record(RealtimeEventType.SESSION_CLOSED, {"reason": reason})

    def fail(self, message: str, code: str | None = None) -> RealtimeEvent:
        self._transition(RealtimeSessionStatus.ERROR)
        return self._record(RealtimeEventType.ERROR, {"message": message, "code": code})

    def _transition(self, next_status: RealtimeSessionStatus) -> None:
        if next_status == self.status:
            return
        if next_status not in self._ALLOWED_TRANSITIONS[self.status]:
            raise RealtimeSessionStateError(
                f"Invalid realtime transition: {self.status.value} -> {next_status.value}"
            )
        self.status = next_status

    def _record(
        self,
        event_type: RealtimeEventType,
        payload: dict[str, object] | None = None,
    ) -> RealtimeEvent:
        event = RealtimeEvent(
            type=event_type,
            session_id=self.session_id,
            status=self.status,
            payload={key: value for key, value in (payload or {}).items() if value is not None},
        )
        self.events.append(event)
        return event
