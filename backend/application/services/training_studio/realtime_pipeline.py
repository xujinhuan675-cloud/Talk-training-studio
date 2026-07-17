"""Provider-neutral realtime transcript mapping for Training Studio."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from application.ports.realtime import (
    PersistedRealtimeTranscript,
    RealtimeSessionBinding,
    RealtimeTranscript,
    TrainingTranscriptSink,
    TrainingVoiceContext,
    normalize_realtime_runtime,
)
from application.services.stakeholder.dto import MessageDTO
from application.services.training_studio.session_service import TrainingSessionService
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import Message


FINAL_TRANSCRIPT_EVENT_TYPES = {
    "transcript.done",
    "input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.completed",
    "response.audio_transcript.done",
    "response.output_audio_transcript.done",
}


def wire_value(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return value
    nested = payload.get("payload")
    if isinstance(nested, dict):
        for key in keys:
            value = nested.get(key)
            if value is not None:
                return value
    return None


def extract_final_transcript(payload: dict[str, object]) -> str | None:
    if payload.get("type") not in FINAL_TRANSCRIPT_EVENT_TYPES:
        return None
    value = wire_value(payload, "text", "transcript")
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def realtime_role_for_event(payload: dict[str, object]) -> str:
    event_type = str(payload.get("type") or "")
    if event_type.startswith("response."):
        return "assistant"
    return "user"


def build_realtime_transcript(
    payload: dict[str, object],
    *,
    binding: RealtimeSessionBinding,
    provider: str,
    realtime_session_id: str,
    runtime: str | None = None,
) -> RealtimeTranscript | None:
    """Normalize a provider event into a final transcript DTO."""

    text = extract_final_transcript(payload)
    if text is None:
        return None

    role = realtime_role_for_event(payload)
    resolved_runtime = normalize_realtime_runtime(
        runtime or _metadata_text(payload, "runtime", "realtimeRuntime", "realtime_runtime"),
        provider=provider,
    )
    return RealtimeTranscript(
        text=text,
        role=role,
        binding=binding,
        provider=provider,
        realtime_session_id=realtime_session_id,
        event_type=str(payload.get("type") or ""),
        runtime=resolved_runtime,
        event_id=_metadata_text(payload, "event_id", "eventId"),
        item_id=_metadata_text(payload, "item_id", "itemId", "item"),
        response_id=_metadata_text(payload, "response_id", "responseId", "response"),
        metadata=_metadata_from_event(
            payload,
            binding=binding,
            provider=provider,
            runtime=resolved_runtime,
            role=role,
        ),
    )


def transcript_to_message_metadata(transcript: RealtimeTranscript) -> dict[str, object]:
    """Return the persisted message metadata shape used by existing realtime routes."""

    runtime = normalize_realtime_runtime(transcript.runtime, provider=transcript.provider)
    realtime: dict[str, object] = {
        "schemaVersion": 1,
        "runtime": runtime,
        "provider": transcript.provider,
        "eventType": transcript.event_type,
        "role": transcript.role,
        "trainingSessionId": transcript.binding.training_session_id,
        "roomId": transcript.binding.room_id,
        "realtimeSessionId": transcript.realtime_session_id,
        "isFinal": transcript.is_final,
        "receivedAt": transcript.received_at.isoformat(),
    }
    for output_key, value in {
        "eventId": transcript.event_id,
        "itemId": transcript.item_id,
        "responseId": transcript.response_id,
    }.items():
        if value is not None:
            realtime[output_key] = value

    metadata = dict(transcript.metadata)
    metadata.setdefault("source", "realtime_voice")
    metadata.setdefault("runtime", runtime)
    metadata.setdefault("trainingMode", "voice")
    metadata.setdefault("interactionMode", "realtime")
    metadata["realtime"] = {**realtime, **dict(metadata.get("realtime") or {})}
    return metadata


@dataclass
class StaticTrainingContextInjector:
    """First-phase context injector for tests and future pipeline bootstrap."""

    task_goal: str | None = None
    rubric: dict[str, object] = field(default_factory=dict)
    recent_turns: list[dict[str, object]] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    async def build_context(self, binding: RealtimeSessionBinding) -> TrainingVoiceContext:
        return TrainingVoiceContext(
            binding=binding,
            task_goal=self.task_goal,
            rubric=dict(self.rubric),
            recent_turns=tuple(dict(turn) for turn in self.recent_turns),
            metadata=dict(self.metadata),
        )


class MemoryTrainingTranscriptSink(TrainingTranscriptSink):
    """Transport-independent transcript sink useful before DB wiring."""

    def __init__(self) -> None:
        self.persisted: list[RealtimeTranscript] = []

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
        self.persisted.append(transcript)
        return PersistedRealtimeTranscript(
            transcript=transcript,
            message_id=len(self.persisted),
            payload={
                "content": transcript.text,
                "sender_type": "persona" if transcript.role == "assistant" else "user",
                "sender_id": "assistant" if transcript.role == "assistant" else "user",
                "metadata": transcript_to_message_metadata(transcript),
            },
        )


RoomMessagePublisher = Callable[[int, MessageDTO], Awaitable[None]]


class RealtimeTranscriptPersistenceSink(TrainingTranscriptSink):
    """Persist realtime transcripts through the current TalkWise room storage."""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., AbstractUnitOfWork],
        session_service: TrainingSessionService | None = None,
        publish_message: RoomMessagePublisher | None = None,
        record_training_turns: bool = True,
    ) -> None:
        self._uow_factory = uow_factory
        self._session_service = session_service
        self._publish_message = publish_message
        self._record_training_turns = record_training_turns

    async def persist(self, transcript: RealtimeTranscript) -> PersistedRealtimeTranscript:
        metadata = transcript_to_message_metadata(transcript)
        sender_type, sender_id = _sender_for_transcript(transcript)
        room_id = transcript.binding.room_id

        async with self._uow_factory() as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            if room is None:
                raise ValueError(f"Chat room {room_id} not found")
            saved = await uow.stakeholder_message_repository.create(
                Message(
                    id=None,
                    room_id=room_id,
                    sender_type=sender_type,
                    sender_id=sender_id,
                    content=transcript.text,
                    metadata=metadata,
                )
            )
            await uow.chat_room_repository.update_last_message_at(room_id, saved.timestamp)
            message = MessageDTO.model_validate(saved)

        if self._publish_message is not None:
            await self._publish_message(room_id, message)

        if self._record_training_turns and self._session_service is not None:
            await self._session_service.record_turns(transcript.binding.training_session_id)

        payload = {
            "trainingSessionId": transcript.binding.training_session_id,
            "roomId": room_id,
            "message": message.model_dump(mode="json"),
        }
        return PersistedRealtimeTranscript(
            transcript=transcript,
            message_id=message.id,
            payload=payload,
        )


def _sender_for_transcript(transcript: RealtimeTranscript) -> tuple[str, str]:
    metadata = dict(transcript.metadata or {})
    sender_id = metadata.get("sender_id") or metadata.get("senderId")
    if transcript.role == "assistant":
        return "persona", str(sender_id or "assistant")
    if transcript.role == "system":
        return "system", str(sender_id or "training_coach")
    return "user", str(sender_id or "user")


def _metadata_text(payload: dict[str, object], *keys: str) -> str | None:
    value = _metadata_value(payload, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metadata_value(payload: dict[str, object], *keys: str) -> object | None:
    value = wire_value(payload, *keys)
    if value is not None:
        return value
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for key in keys:
            value = metadata.get(key)
            if value is not None:
                return value
    return None


def _metadata_scalar(value: object | None) -> object | None:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return None


def _metadata_scalar_mapping(value: object | None) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        scalar = _metadata_scalar(item)
        if scalar is not None:
            result[str(key)] = scalar
    return result or None


def _metadata_from_event(
    payload: dict[str, object],
    *,
    binding: RealtimeSessionBinding,
    provider: str,
    runtime: str | None = None,
    role: str,
) -> dict[str, object]:
    resolved_runtime = normalize_realtime_runtime(runtime, provider=provider)
    realtime: dict[str, object] = {
        "runtime": resolved_runtime,
        "provider": provider,
        "eventType": payload.get("type"),
        "role": role,
        "trainingSessionId": binding.training_session_id,
        "roomId": binding.room_id,
        "isFinal": True,
        "receivedAt": datetime.now(UTC).isoformat(),
    }
    for output_key, input_keys in {
        "contentIndex": ("content_index", "contentIndex"),
        "language": ("language", "lang"),
        "confidence": ("confidence",),
        "sequence": ("sequence",),
        "sourceLanguage": ("sourceLanguage", "source_language", "sourceLang"),
        "targetLanguage": ("targetLanguage", "target_language", "targetLang"),
        "translationIntent": (
            "translationIntent",
            "translation_intent",
            "translationStrategy",
            "translationMode",
        ),
    }.items():
        value = _metadata_scalar(_metadata_value(payload, *input_keys))
        if value is not None:
            realtime[output_key] = value

    metadata: dict[str, object] = {
        "source": _metadata_scalar(_metadata_value(payload, "source")) or "realtime_voice",
        "runtime": resolved_runtime,
        "trainingMode": "voice",
        "interactionMode": "realtime",
        "realtime": realtime,
    }
    for output_key, input_keys in {
        "sender_id": ("sender_id", "senderId", "user_id", "userId"),
        "trainingProfile": ("trainingProfile", "training_profile"),
        "sourceLanguage": ("sourceLanguage", "source_language", "sourceLang"),
        "targetLanguage": ("targetLanguage", "target_language", "targetLang"),
        "translationStrategy": ("translationStrategy", "translationMode", "translation_intent"),
    }.items():
        value = _metadata_scalar(_metadata_value(payload, *input_keys))
        if value is not None:
            metadata[output_key] = value
    for output_key in ("translation", "liveCoach"):
        value = _metadata_scalar_mapping(_metadata_value(payload, output_key))
        if value is not None:
            metadata[output_key] = value
    return metadata


__all__ = [
    "FINAL_TRANSCRIPT_EVENT_TYPES",
    "MemoryTrainingTranscriptSink",
    "RealtimeTranscriptPersistenceSink",
    "RoomMessagePublisher",
    "StaticTrainingContextInjector",
    "build_realtime_transcript",
    "extract_final_transcript",
    "realtime_role_for_event",
    "transcript_to_message_metadata",
    "wire_value",
]
