"""Training-core boundary shared by text, voice, and future video runtimes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from domain.training_studio.session import TrainingSession

from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.live_guidance_service import (
    GuideEvent,
    TrainingLiveGuidanceService,
    TranscriptSpeaker,
    TranscriptTurn,
)
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingSessionService,
)


@dataclass(frozen=True)
class ConversationRef:
    """Stable reference to whichever runtime owns the visible conversation."""

    provider: str
    conversation_id: str
    branch_tail_message_id: str | None = None
    legacy_room_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        provider = _normalize_required_text(self.provider, "provider")
        conversation_id = _normalize_required_text(self.conversation_id, "conversation_id")
        if not provider:
            raise ValueError("provider cannot be empty")
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "conversation_id", conversation_id)
        object.__setattr__(
            self,
            "branch_tail_message_id",
            _normalize_optional_text(self.branch_tail_message_id),
        )
        object.__setattr__(
            self,
            "legacy_room_id",
            _normalize_optional_text(self.legacy_room_id),
        )
        object.__setattr__(self, "metadata", _copy_metadata(self.metadata))

    @property
    def session_room_id(self) -> str:
        """Return the current TrainingSession-compatible room binding."""

        return self.legacy_room_id or f"{self.provider}:{self.conversation_id}"


@dataclass(frozen=True)
class TrainingTurn:
    """A product-level turn independent of text, voice, or video transport details."""

    speaker: TranscriptSpeaker | str
    text: str
    turn_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "speaker", _normalize_speaker(self.speaker))
        object.__setattr__(self, "text", _normalize_required_text(self.text, "text"))
        object.__setattr__(self, "turn_id", _normalize_optional_text(self.turn_id))
        object.__setattr__(self, "metadata", _copy_metadata(self.metadata))

    def to_transcript_turn(self) -> TranscriptTurn:
        return TranscriptTurn(
            speaker=self.speaker,
            text=self.text,
            turn_id=self.turn_id,
            metadata=_copy_metadata(self.metadata),
        )


@dataclass(frozen=True)
class StartedTrainingSession:
    """Result returned when a training session is bound to a conversation runtime."""

    session: TrainingSession
    conversation: ConversationRef


def training_core_metadata_for_session(
    session: TrainingSession,
    *,
    runtime: str,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the TalkWise-owned training semantic metadata shared by adapters."""

    source = dict(session.task_config.metadata or {})
    metadata: dict[str, object] = {
        "runtime": _normalize_required_text(runtime, "runtime"),
        "trainingSessionId": session.session_id,
        "mode": session.mode.value,
        "scenarioTemplateId": session.scenario_template_id,
        "category": session.task_config.category.value,
        "personaIds": _normalize_text_list(source.get("persona_ids")),
        "scenarioId": _copy_metadata_value(source.get("scenario_id")),
        "dispatcher": _copy_metadata_value(
            source.get("dispatcher") or source.get("dispatcher_state")
        ),
        "evaluation": _copy_metadata_value(
            source.get("evaluation") or source.get("rubric")
        ),
        "growthReport": _copy_metadata_value(
            source.get("growth_report") or source.get("report")
        ),
        "liveGuidance": _copy_metadata_value(
            source.get("live_guidance") or source.get("guidance")
        ),
    }
    metadata.update(dict(extra or {}))
    return {key: value for key, value in metadata.items() if _metadata_value_present(value)}


@runtime_checkable
class TrainingConversationAdapter(Protocol):
    """Adapter implemented by current rooms, LibreChat-style text, or Pipecat sinks."""

    async def create_conversation(self, session: TrainingSession) -> ConversationRef: ...

    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef: ...

    async def recent_turns(
        self,
        conversation: ConversationRef,
        *,
        limit: int,
    ) -> Sequence[TrainingTurn]: ...


class TrainingCoreOrchestrator:
    """Coordinates TalkWise training semantics without owning a chat runtime."""

    def __init__(
        self,
        *,
        session_service: TrainingSessionService,
        conversation_adapter: TrainingConversationAdapter,
        guidance_service: TrainingLiveGuidanceService | None = None,
    ) -> None:
        self._session_service = session_service
        self._conversation_adapter = _require_conversation_adapter(conversation_adapter)
        self._guidance_service = guidance_service or TrainingLiveGuidanceService()

    async def start_session(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | dict,
    ) -> StartedTrainingSession:
        session = await self._session_service.create_session(payload)
        conversation = _require_conversation_ref(
            await self._conversation_adapter.create_conversation(session)
        )
        started = await self._session_service.start_session(
            session.session_id,
            room_id=conversation.session_room_id,
        )
        return StartedTrainingSession(session=started, conversation=conversation)

    async def record_turn(
        self,
        *,
        training_session_id: str,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef:
        session_id = _normalize_required_text(training_session_id, "training_session_id")
        conversation = _require_conversation_ref(conversation)
        turn = _require_training_turn(turn)
        updated = _require_conversation_ref(
            await self._conversation_adapter.append_turn(conversation, turn)
        )
        await self._session_service.record_turns(session_id)
        return updated

    async def generate_guidance(
        self,
        *,
        training_session_id: str,
        conversation: ConversationRef,
        task_goal: str,
        rubric: Mapping[str, object] | None = None,
        limit: int | None = None,
    ) -> list[GuideEvent]:
        session_id = _normalize_required_text(training_session_id, "training_session_id")
        task_goal = _normalize_required_text(task_goal, "task_goal")
        conversation = _require_conversation_ref(conversation)
        if limit is not None and limit < 1:
            raise ValueError("limit must be at least 1")
        recent_turns = await self._conversation_adapter.recent_turns(
            conversation,
            limit=limit or self._guidance_service.window_size,
        )
        return await self._guidance_service.generate_guidance_async(
            training_session_id=session_id,
            task_goal=task_goal,
            rubric=dict(rubric or {}),
            recent_turns=[
                _require_training_turn(turn).to_transcript_turn() for turn in recent_turns
            ],
        )


def _normalize_required_text(value: object, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field_name} cannot be empty")
    return text


def _normalize_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_speaker(speaker: TranscriptSpeaker | str) -> TranscriptSpeaker | str:
    if isinstance(speaker, TranscriptSpeaker):
        return speaker
    return _normalize_required_text(speaker, "speaker")


def _copy_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    return deepcopy(dict(metadata or {}))


def _copy_metadata_value(value: object) -> object:
    return deepcopy(value)


def _normalize_text_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [text for item in value if (text := str(item).strip())]


def _metadata_value_present(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _require_conversation_ref(value: object) -> ConversationRef:
    if not isinstance(value, ConversationRef):
        raise TypeError("conversation adapter must return ConversationRef")
    return value


def _require_conversation_adapter(value: object) -> TrainingConversationAdapter:
    if not isinstance(value, TrainingConversationAdapter):
        raise TypeError("conversation_adapter must implement TrainingConversationAdapter")
    return value


def _require_training_turn(value: object) -> TrainingTurn:
    if not isinstance(value, TrainingTurn):
        raise TypeError("turn must be TrainingTurn")
    return value
