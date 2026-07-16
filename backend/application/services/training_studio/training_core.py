"""Training-core boundary shared by text, voice, and future video runtimes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
        provider = self.provider.strip()
        conversation_id = self.conversation_id.strip()
        if not provider:
            raise ValueError("provider cannot be empty")
        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "conversation_id", conversation_id)
        object.__setattr__(
            self,
            "branch_tail_message_id",
            self.branch_tail_message_id.strip() if self.branch_tail_message_id else None,
        )
        object.__setattr__(
            self,
            "legacy_room_id",
            self.legacy_room_id.strip() if self.legacy_room_id else None,
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

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
        text = self.text.strip()
        if not text:
            raise ValueError("text cannot be empty")
        object.__setattr__(self, "text", text)
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def to_transcript_turn(self) -> TranscriptTurn:
        return TranscriptTurn(
            speaker=self.speaker,
            text=self.text,
            turn_id=self.turn_id,
            metadata=dict(self.metadata),
        )


@dataclass(frozen=True)
class StartedTrainingSession:
    """Result returned when a training session is bound to a conversation runtime."""

    session: TrainingSession
    conversation: ConversationRef


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
        self._conversation_adapter = conversation_adapter
        self._guidance_service = guidance_service or TrainingLiveGuidanceService()

    async def start_session(
        self,
        payload: CreateTrainingSessionDTO | TrainingTaskConfigDTO | dict,
    ) -> StartedTrainingSession:
        session = await self._session_service.create_session(payload)
        conversation = await self._conversation_adapter.create_conversation(session)
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
        updated = await self._conversation_adapter.append_turn(conversation, turn)
        await self._session_service.record_turns(training_session_id)
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
        recent_turns = await self._conversation_adapter.recent_turns(
            conversation,
            limit=limit or self._guidance_service.window_size,
        )
        return await self._guidance_service.generate_guidance_async(
            training_session_id=training_session_id,
            task_goal=task_goal,
            rubric=dict(rubric or {}),
            recent_turns=[turn.to_transcript_turn() for turn in recent_turns],
        )
