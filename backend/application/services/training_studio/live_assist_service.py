"""Application service for the first live meeting-assist loop.

The MVP deliberately keeps media transport outside this service. A browser or
phone adapter can send either a completed transcript or one encoded audio
segment. The service normalizes the speaker, persists a bounded transcript on
the owned training session, and invokes the existing live-guidance engine.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from application.ports.stt import STTPort
from application.services.training_studio.live_guidance_service import (
    GuideEvent,
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)
from domain.training_studio.session import TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope

LIVE_ASSIST_METADATA_KEY = "liveAssist"
LIVE_ASSIST_SCHEMA_VERSION = 1
LIVE_ASSIST_MAX_TURNS = 100
LIVE_ASSIST_MAX_AUDIO_BYTES = 15 * 1024 * 1024


class LiveAssistError(ValueError):
    """A safe, client-facing validation or runtime error for the assist loop."""

    def __init__(self, message: str, *, code: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class _TrainingSessionService(Protocol):
    async def get_session(
        self,
        session_id: str,
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> Any: ...

    async def record_session_metadata(
        self,
        session_id: str,
        *,
        metadata: Mapping[str, object],
        access_scope: TrainingSessionAccessScope,
    ) -> Any: ...


class LiveAssistService:
    """Turn-level meeting assist orchestration shared by HTTP and future WS adapters."""

    def __init__(
        self,
        *,
        stt: STTPort | None,
        guidance: TrainingLiveGuidanceService,
        max_turns: int = LIVE_ASSIST_MAX_TURNS,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self._stt = stt
        self._guidance = guidance
        self._max_turns = max_turns

    async def process_turn(
        self,
        session_id: str,
        *,
        user_id: str,
        session_service: _TrainingSessionService,
        access_scope: TrainingSessionAccessScope,
        text: str | None = None,
        audio: bytes | None = None,
        audio_format: str = "webm",
        language: str = "zh",
        speaker_source: str = "microphone",
        speaker_hint: str | None = None,
        client_metadata: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        """Process one completed meeting turn and return its guidance snapshot."""

        session = await session_service.get_session(session_id, access_scope=access_scope)
        if session.status != TrainingSessionStatus.ACTIVE:
            raise LiveAssistError(
                "Training session must be active before using live assist",
                code="training_session_not_active",
                status_code=400,
            )

        normalized_text, transcribed = await self._resolve_text(
            text=text,
            audio=audio,
            audio_format=audio_format,
            language=language,
        )
        speaker = normalize_live_assist_speaker(
            speaker_source=speaker_source,
            speaker_hint=speaker_hint,
        )
        created_at = datetime.now(UTC)
        turn = TranscriptTurn(
            speaker=speaker,
            text=normalized_text,
            turn_id=f"live-assist-{uuid4().hex}",
            created_at=created_at,
            metadata={
                "source": "live_assist",
                "speakerSource": speaker_source,
                "speakerHint": speaker_hint,
                "transcribed": transcribed,
                "language": language,
                "audioFormat": audio_format if audio is not None else None,
                "userId": user_id,
                **dict(client_metadata or {}),
            },
        )

        previous_turns = _turns_from_session_metadata(
            getattr(session.task_config, "metadata", None)
        )
        transcript = (*previous_turns, turn)[-self._max_turns :]
        task_goal = _task_goal_for_guidance(session)
        rubric = _rubric_for_guidance(session)
        state = self._guidance.build_state(
            training_session_id=session_id,
            task_goal=task_goal,
            rubric=rubric,
            recent_turns=transcript,
        )
        events = await self._guidance.generate_guidance_async(
            training_session_id=session_id,
            task_goal=state.task_goal,
            rubric=state.rubric,
            recent_turns=transcript,
        )

        await session_service.record_session_metadata(
            session_id,
            metadata={
                LIVE_ASSIST_METADATA_KEY: {
                    "schemaVersion": LIVE_ASSIST_SCHEMA_VERSION,
                    "updatedAt": created_at.isoformat(),
                    "lastSpeaker": speaker.value,
                    "turns": [_turn_to_metadata(item) for item in transcript],
                }
            },
            access_scope=access_scope,
        )
        return {
            "session_id": session_id,
            "user_id": user_id,
            "turn": _turn_to_wire(turn),
            "guidance": [event.to_sse_payload() for event in events],
            "transcript_turn_count": len(transcript),
            "speaker_resolution": {
                "speaker": speaker.value,
                "speaker_source": speaker_source,
                "speaker_hint": speaker_hint,
            },
        }

    async def _resolve_text(
        self,
        *,
        text: str | None,
        audio: bytes | None,
        audio_format: str,
        language: str,
    ) -> tuple[str, bool]:
        normalized_text = str(text or "").strip()
        if normalized_text:
            return normalized_text, False
        if not audio:
            raise LiveAssistError(
                "Provide a transcript or audio segment",
                code="turn_input_required",
                status_code=422,
            )
        if len(audio) > LIVE_ASSIST_MAX_AUDIO_BYTES:
            raise LiveAssistError(
                "Audio segment exceeds the supported size",
                code="audio_too_large",
                status_code=413,
            )
        if self._stt is None:
            raise LiveAssistError(
                "STT service not configured",
                code="stt_not_configured",
                status_code=503,
            )
        result = await self._stt.transcribe(
            audio,
            language=language,
            audio_format=audio_format,
        )
        normalized_text = str(getattr(result, "text", result) or "").strip()
        if not normalized_text:
            raise LiveAssistError(
                "STT returned an empty transcript",
                code="empty_transcript",
                status_code=422,
            )
        return normalized_text, True


def normalize_live_assist_speaker(*, speaker_source: str, speaker_hint: str | None) -> TranscriptSpeaker:
    """Resolve browser capture metadata to the two training speakers."""

    hint = str(speaker_hint or "").strip().lower().replace("_", "-")
    if hint in {
        "user",
        "me",
        "self",
        "learner",
        "mic",
        "microphone",
        "local",
        "speaker-1",
    }:
        return TranscriptSpeaker.USER
    if hint in {
        "counterpart",
        "other",
        "them",
        "remote",
        "system",
        "participant",
        "speaker-2",
    }:
        return TranscriptSpeaker.COUNTERPART

    source = str(speaker_source or "").strip().lower()
    if source == "system":
        return TranscriptSpeaker.COUNTERPART
    # Mixed capture cannot be diarized safely in this MVP; microphone is the
    # conservative default and the raw hint/source remain in turn metadata.
    return TranscriptSpeaker.USER


def decode_audio_base64(value: str) -> bytes:
    """Decode plain or data-URL base64 without accepting malformed payloads."""

    encoded = str(value or "").strip()
    if "," in encoded and encoded.lower().startswith("data:"):
        encoded = encoded.split(",", 1)[1]
    try:
        audio = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise LiveAssistError(
            "Audio is not valid base64",
            code="invalid_audio",
            status_code=422,
        ) from exc
    if not audio:
        raise LiveAssistError("Audio segment is empty", code="empty_audio", status_code=422)
    return audio


def _task_goal_for_guidance(session: Any) -> str:
    config = session.task_config
    framework = getattr(config.framework, "value", config.framework)
    category = getattr(config.category, "value", config.category)
    focus = ", ".join(config.tech_stack[:3]) if config.tech_stack else category
    return f"{config.level} {config.role} {category} practice using {framework}; focus: {focus}"


def _rubric_for_guidance(session: Any) -> dict[str, object]:
    return {
        key.value if hasattr(key, "value") else str(key): value
        for key, value in dict(session.task_config.rubric_weights or {}).items()
    }


def _turn_to_metadata(turn: TranscriptTurn) -> dict[str, object]:
    return _turn_to_wire(turn)


def _turn_to_wire(turn: TranscriptTurn) -> dict[str, object]:
    return {
        "speaker": turn.normalized_speaker,
        "text": turn.text,
        "turn_id": turn.turn_id,
        "created_at": turn.created_at.isoformat() if turn.created_at else None,
        "metadata": dict(turn.metadata),
    }


def _turns_from_session_metadata(metadata: object) -> tuple[TranscriptTurn, ...]:
    if not isinstance(metadata, Mapping):
        return ()
    assist = metadata.get(LIVE_ASSIST_METADATA_KEY)
    if not isinstance(assist, Mapping):
        return ()
    raw_turns = assist.get("turns")
    if not isinstance(raw_turns, list):
        return ()
    turns: list[TranscriptTurn] = []
    for item in raw_turns:
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker = item.get("speaker", TranscriptSpeaker.USER)
        if str(speaker) not in {
            TranscriptSpeaker.USER.value,
            TranscriptSpeaker.COUNTERPART.value,
        }:
            speaker = TranscriptSpeaker.USER
        created_at = None
        raw_created_at = item.get("created_at")
        if isinstance(raw_created_at, str):
            try:
                created_at = datetime.fromisoformat(raw_created_at)
            except ValueError:
                created_at = None
        turns.append(
            TranscriptTurn(
                speaker=speaker,
                text=text,
                turn_id=str(item["turn_id"]) if item.get("turn_id") else None,
                created_at=created_at,
                metadata=dict(item.get("metadata") or {}),
            )
        )
    return tuple(turns[-LIVE_ASSIST_MAX_TURNS:])


__all__ = [
    "LIVE_ASSIST_METADATA_KEY",
    "LiveAssistError",
    "LiveAssistService",
    "decode_audio_base64",
    "normalize_live_assist_speaker",
]
