"""Training conversation adapters backed by current TalkWise storage."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from application.services.training_studio.live_guidance_service import TranscriptSpeaker
from application.services.training_studio.training_core import (
    ConversationRef,
    TrainingTurn,
    training_core_metadata_for_session,
)
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.entity import Conversation as ConversationEntity
from domain.conversation.entity import Message as ConversationMessage
from domain.stakeholder.entity import ChatRoom
from domain.stakeholder.entity import Message as StakeholderMessage
from domain.training_studio.session import TrainingSession


class ConversationTrainingConversationAdapter:
    """Bridge TrainingCoreOrchestrator to the conversation/message tree runtime."""

    provider = "talkwise-conversation"

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        *,
        default_model: str = "training-core",
    ) -> None:
        self._uow_factory = uow_factory
        self._default_model = default_model

    async def create_conversation(self, session: TrainingSession) -> ConversationRef:
        async with self._uow_factory() as uow:
            conversation = await uow.conversation_repository.create(
                ConversationEntity(
                    id=None,
                    title=_conversation_title_for_session(session),
                    system_prompt=_metadata_text(session, "system_prompt", "instructions"),
                    model=_metadata_text(session, "model") or self._default_model,
                    metadata=_conversation_metadata_for_session(session),
                )
            )
        if conversation.id is None:
            raise ValueError("Persisted conversation must have an id")
        return ConversationRef(
            provider=self.provider,
            conversation_id=str(conversation.id),
            metadata={
                **training_core_metadata_for_session(
                    session,
                    runtime="conversation_message_tree",
                    extra={"branchId": "main"},
                ),
            },
        )

    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef:
        conversation_id = _require_conversation_id(conversation)
        metadata = {
            **dict(turn.metadata),
            "source": turn.metadata.get("source", "training_core"),
            "trainingConversationProvider": self.provider,
        }
        branch_id = str(
            metadata.get("branch_id") or conversation.metadata.get("branchId") or "main"
        )
        async with self._uow_factory() as uow:
            saved = await uow.message_repository.create(
                ConversationMessage(
                    id=None,
                    conversation_id=conversation_id,
                    role=_conversation_role_for_turn(turn),
                    content=turn.text,
                    parent_message_id=conversation.branch_tail_message_id,
                    branch_id=branch_id,
                    provider=_optional_metadata_text(metadata, "provider"),
                    model=_optional_metadata_text(metadata, "model"),
                    metadata=metadata,
                )
            )
        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id=saved.public_id,
            legacy_room_id=conversation.legacy_room_id,
            metadata={**dict(conversation.metadata), "branchId": branch_id},
        )

    async def recent_turns(
        self,
        conversation: ConversationRef,
        *,
        limit: int,
    ) -> Sequence[TrainingTurn]:
        conversation_id = _require_conversation_id(conversation)
        branch_id = str(conversation.metadata.get("branchId") or "main")
        async with self._uow_factory(readonly=True) as uow:
            messages = await uow.message_repository.list_by_conversation(
                conversation_id,
                branch_id=branch_id,
                limit=max(limit, 1) * 4,
            )
        return [_turn_for_conversation_message(message) for message in messages[-limit:]]


class StakeholderRoomTrainingConversationAdapter:
    """Bridge TrainingCoreOrchestrator to the existing stakeholder room runtime."""

    provider = "talkwise-stakeholder-room"

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        *,
        default_room_type: str = "battle_prep",
    ) -> None:
        self._uow_factory = uow_factory
        self._default_room_type = default_room_type

    async def create_conversation(self, session: TrainingSession) -> ConversationRef:
        existing_room_id = _coerce_room_id(session.room_id)
        async with self._uow_factory() as uow:
            if existing_room_id is not None:
                room = await uow.chat_room_repository.get_by_id(existing_room_id)
                if room is None:
                    raise ValueError(f"Chat room {existing_room_id} not found")
            else:
                room = await uow.chat_room_repository.create(
                    _room_for_session(session, default_room_type=self._default_room_type)
                )

        return _conversation_ref_for_room(room, session=session)

    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef:
        room_id = _require_room_id(conversation)
        sender_type, sender_id = _sender_for_turn(turn)
        async with self._uow_factory() as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            if room is None:
                raise ValueError(f"Chat room {room_id} not found")
            saved = await uow.stakeholder_message_repository.create(
                StakeholderMessage(
                    id=None,
                    room_id=room_id,
                    sender_type=sender_type,
                    sender_id=sender_id,
                    content=turn.text,
                    metadata={
                        **dict(turn.metadata),
                        "source": turn.metadata.get("source", "training_core"),
                        "trainingConversationProvider": self.provider,
                    },
                )
            )
            await uow.chat_room_repository.update_last_message_at(room_id, saved.timestamp)

        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id=str(saved.id),
            legacy_room_id=conversation.legacy_room_id,
            metadata=conversation.metadata,
        )

    async def recent_turns(
        self,
        conversation: ConversationRef,
        *,
        limit: int,
    ) -> Sequence[TrainingTurn]:
        room_id = _require_room_id(conversation)
        async with self._uow_factory(readonly=True) as uow:
            total = await uow.stakeholder_message_repository.count_by_room_id(room_id)
            messages = await uow.stakeholder_message_repository.list_by_room_id(
                room_id,
                skip=max(total - limit, 0),
                limit=limit,
            )
        return [_turn_for_message(message) for message in messages]


def _conversation_ref_for_room(room: ChatRoom, *, session: TrainingSession) -> ConversationRef:
    if room.id is None:
        raise ValueError("Persisted chat room must have an id")
    return ConversationRef(
        provider=StakeholderRoomTrainingConversationAdapter.provider,
        conversation_id=str(room.id),
        legacy_room_id=str(room.id),
        metadata=training_core_metadata_for_session(
            session,
            runtime="stakeholder_room",
        ),
    )


def _room_for_session(session: TrainingSession, *, default_room_type: str) -> ChatRoom:
    metadata = dict(session.task_config.metadata or {})
    persona_ids = metadata.get("persona_ids")
    scenario_id = metadata.get("scenario_id")
    return ChatRoom(
        id=None,
        name=str(metadata.get("room_name") or _room_name_for_session(session)),
        type=str(metadata.get("room_type") or default_room_type),
        persona_ids=_string_list(persona_ids),
        scenario_id=_optional_int(scenario_id),
    )


def _room_name_for_session(session: TrainingSession) -> str:
    category = session.task_config.category.value
    return f"{session.task_config.role} {category} training"


def _coerce_room_id(value: object | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError("room_id must be numeric for stakeholder room conversations") from exc


def _require_room_id(conversation: ConversationRef) -> int:
    room_id = _coerce_room_id(conversation.legacy_room_id or conversation.conversation_id)
    if room_id is None:
        raise ValueError("conversation must reference a stakeholder room id")
    return room_id


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def _sender_for_turn(turn: TrainingTurn) -> tuple[str, str]:
    speaker = (
        turn.speaker.value if isinstance(turn.speaker, TranscriptSpeaker) else str(turn.speaker)
    )
    metadata = dict(turn.metadata)
    if speaker in {"assistant", "counterpart", "persona"}:
        return "persona", str(metadata.get("sender_id") or "assistant")
    if speaker in {"coach", "system"}:
        return "system", str(metadata.get("sender_id") or "training_coach")
    return "user", str(metadata.get("sender_id") or "user")


def _turn_for_message(message: StakeholderMessage) -> TrainingTurn:
    metadata: dict[str, Any] = {
        **dict(message.metadata or {}),
        "message_id": message.id,
        "room_id": message.room_id,
        "sender_type": message.sender_type,
        "sender_id": message.sender_id,
    }
    return TrainingTurn(
        speaker=_speaker_for_message(message),
        text=message.content,
        turn_id=str(message.id) if message.id is not None else None,
        metadata=metadata,
    )


def _speaker_for_message(message: StakeholderMessage) -> TranscriptSpeaker:
    if message.sender_type == "persona":
        return TranscriptSpeaker.COUNTERPART
    if message.sender_type == "system":
        return TranscriptSpeaker.SYSTEM
    return TranscriptSpeaker.USER


def _conversation_title_for_session(session: TrainingSession) -> str:
    return str(
        _metadata_text(session, "conversation_title", "room_name")
        or _room_name_for_session(session)
    )


def _conversation_metadata_for_session(session: TrainingSession) -> dict[str, object]:
    return {
        **dict(session.task_config.metadata or {}),
        **training_core_metadata_for_session(
            session,
            runtime="conversation_message_tree",
        ),
    }


def _metadata_text(session: TrainingSession, *keys: str) -> str | None:
    metadata = dict(session.task_config.metadata or {})
    for key in keys:
        value = metadata.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _optional_metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _require_conversation_id(conversation: ConversationRef) -> int:
    try:
        return int(conversation.conversation_id)
    except ValueError as exc:
        raise ValueError("conversation_id must be numeric for message-tree conversations") from exc


def _conversation_role_for_turn(turn: TrainingTurn) -> str:
    speaker = (
        turn.speaker.value if isinstance(turn.speaker, TranscriptSpeaker) else str(turn.speaker)
    )
    if speaker in {"assistant", "counterpart", "persona"}:
        return "assistant"
    if speaker in {"coach", "system"}:
        return "system"
    return "user"


def _turn_for_conversation_message(message: ConversationMessage) -> TrainingTurn:
    metadata: dict[str, Any] = {
        **dict(message.metadata or {}),
        "message_id": message.id,
        "public_id": message.public_id,
        "parent_message_id": message.parent_message_id,
        "branch_id": message.branch_id,
        "role": message.role,
    }
    return TrainingTurn(
        speaker=_speaker_for_conversation_message(message),
        text=message.content,
        turn_id=message.public_id,
        metadata=metadata,
    )


def _speaker_for_conversation_message(message: ConversationMessage) -> TranscriptSpeaker:
    if message.role == "assistant":
        return TranscriptSpeaker.COUNTERPART
    if message.role == "system":
        return TranscriptSpeaker.SYSTEM
    return TranscriptSpeaker.USER


__all__ = [
    "ConversationTrainingConversationAdapter",
    "StakeholderRoomTrainingConversationAdapter",
]
