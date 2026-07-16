from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingSessionService,
)
from application.services.training_studio.training_core import (
    TrainingCoreOrchestrator,
    TrainingTurn,
)
from domain.conversation.entity import Conversation as ConversationEntity
from domain.conversation.entity import Message as ConversationMessage
from domain.stakeholder.entity import ChatRoom, Message
from infrastructure.adapters.training_conversation import (
    ConversationTrainingConversationAdapter,
    StakeholderRoomTrainingConversationAdapter,
)


@dataclass
class _State:
    rooms: dict[int, ChatRoom] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)


class _RoomRepository:
    def __init__(self, state: _State) -> None:
        self._state = state

    async def create(self, room: ChatRoom) -> ChatRoom:
        saved = ChatRoom(
            id=len(self._state.rooms) + 1,
            name=room.name,
            type=room.type,
            persona_ids=room.persona_ids,
            scenario_id=room.scenario_id,
            created_at=room.created_at,
            last_message_at=room.last_message_at,
        )
        self._state.rooms[saved.id] = saved
        return saved

    async def get_by_id(self, room_id: int) -> ChatRoom | None:
        return self._state.rooms.get(room_id)

    async def update_last_message_at(self, room_id: int, timestamp) -> None:
        self._state.rooms[room_id].last_message_at = timestamp


class _MessageRepository:
    def __init__(self, state: _State) -> None:
        self._state = state

    async def create(self, message: Message) -> Message:
        saved = Message(
            id=len(self._state.messages) + 1,
            room_id=message.room_id,
            sender_type=message.sender_type,
            sender_id=message.sender_id,
            content=message.content,
            timestamp=message.timestamp,
            metadata=message.metadata,
        )
        self._state.messages.append(saved)
        return saved

    async def list_by_room_id(
        self,
        room_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Message]:
        messages = [message for message in self._state.messages if message.room_id == room_id]
        return messages[skip : skip + limit]

    async def count_by_room_id(self, room_id: int) -> int:
        return len([message for message in self._state.messages if message.room_id == room_id])


class _UnitOfWork:
    def __init__(self, state: _State, *, readonly: bool = False) -> None:
        self._state = state
        self._readonly = readonly
        self.chat_room_repository = _RoomRepository(state)
        self.stakeholder_message_repository = _MessageRepository(state)

    async def __aenter__(self) -> "_UnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@dataclass
class _ConversationState:
    conversations: dict[int, ConversationEntity] = field(default_factory=dict)
    messages: list[ConversationMessage] = field(default_factory=list)


class _ConversationRepository:
    def __init__(self, state: _ConversationState) -> None:
        self._state = state

    async def create(self, conversation: ConversationEntity) -> ConversationEntity:
        saved = ConversationEntity(
            id=len(self._state.conversations) + 1,
            title=conversation.title,
            system_prompt=conversation.system_prompt,
            model=conversation.model,
            status=conversation.status,
            metadata=conversation.metadata,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            deleted_at=conversation.deleted_at,
        )
        self._state.conversations[saved.id] = saved
        return saved


class _ConversationMessageRepository:
    def __init__(self, state: _ConversationState) -> None:
        self._state = state

    async def create(self, message: ConversationMessage) -> ConversationMessage:
        saved = ConversationMessage(
            id=len(self._state.messages) + 1,
            conversation_id=message.conversation_id,
            role=message.role,
            content=message.content,
            public_id=message.public_id,
            parent_message_id=message.parent_message_id,
            branch_id=message.branch_id,
            status=message.status,
            finish_reason=message.finish_reason,
            provider=message.provider,
            model=message.model,
            content_parts=message.content_parts,
            run_id=message.run_id,
            token_count=message.token_count,
            metadata=message.metadata,
            created_at=message.created_at,
        )
        self._state.messages.append(saved)
        return saved

    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        branch_id: str | None = None,
    ) -> list[ConversationMessage]:
        messages = [
            message
            for message in self._state.messages
            if message.conversation_id == conversation_id
            and (branch_id is None or message.branch_id == branch_id)
        ]
        return messages[skip : skip + limit]


class _ConversationUnitOfWork:
    def __init__(self, state: _ConversationState, *, readonly: bool = False) -> None:
        self._state = state
        self._readonly = readonly
        self.conversation_repository = _ConversationRepository(state)
        self.message_repository = _ConversationMessageRepository(state)

    async def __aenter__(self) -> "_ConversationUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _task_config() -> TrainingTaskConfigDTO:
    return TrainingTaskConfigDTO(
        role="Account Manager",
        level="Senior",
        tech_stack=["renewal", "objection handling"],
        question_type_ratios={"behavioral": 30, "craft": 50, "pressure": 20},
        question_count=6,
        category="sales",
        metadata={
            "room_name": "Renewal practice",
            "persona_ids": ["customer-1"],
            "scenario_id": 9,
        },
    )


@pytest.mark.asyncio
async def test_stakeholder_room_adapter_binds_training_core_to_current_room_runtime() -> None:
    state = _State()
    adapter = StakeholderRoomTrainingConversationAdapter(
        lambda **kwargs: _UnitOfWork(state, **kwargs)
    )
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "training-1"),
        conversation_adapter=adapter,
    )

    started = await orchestrator.start_session(
        CreateTrainingSessionDTO(task_config=_task_config(), mode="voice")
    )
    updated = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Can we begin with a smaller pilot?",
            metadata={"source": "text"},
        ),
    )

    recent_turns = await adapter.recent_turns(updated, limit=5)

    assert started.session.room_id == "1"
    assert started.conversation.provider == "talkwise-stakeholder-room"
    assert state.rooms[1].name == "Renewal practice"
    assert state.rooms[1].persona_ids == ["customer-1"]
    assert state.rooms[1].scenario_id == 9
    assert state.messages[0].sender_type == "user"
    assert state.messages[0].metadata["source"] == "text"
    assert state.messages[0].metadata["trainingConversationProvider"] == (
        "talkwise-stakeholder-room"
    )
    assert updated.branch_tail_message_id == "1"
    assert recent_turns[0].text == "Can we begin with a smaller pilot?"
    assert recent_turns[0].metadata["message_id"] == 1


@pytest.mark.asyncio
async def test_stakeholder_room_adapter_reuses_existing_training_room_binding() -> None:
    state = _State(
        rooms={
            7: ChatRoom(
                id=7,
                name="Existing room",
                type="battle_prep",
                persona_ids=["customer-2"],
            )
        }
    )
    adapter = StakeholderRoomTrainingConversationAdapter(
        lambda **kwargs: _UnitOfWork(state, **kwargs)
    )
    session_service = TrainingSessionService(id_factory=lambda: "training-2")
    session = await session_service.create_session(
        CreateTrainingSessionDTO(task_config=_task_config(), mode="text")
    )
    session.room_id = "7"

    conversation = await adapter.create_conversation(session)

    assert conversation.conversation_id == "7"
    assert conversation.legacy_room_id == "7"
    assert len(state.rooms) == 1


@pytest.mark.asyncio
async def test_conversation_adapter_binds_training_core_to_message_tree_runtime() -> None:
    state = _ConversationState()
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "training-text-1"),
        conversation_adapter=adapter,
    )

    started = await orchestrator.start_session(
        CreateTrainingSessionDTO(task_config=_task_config(), mode="text")
    )
    first_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Can we start with a smaller pilot?",
            metadata={"source": "text", "provider": "openai", "model": "gpt-test"},
        ),
    )
    second_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=first_ref,
        turn=TrainingTurn(
            speaker="assistant",
            text="Yes, if we define a measurable success metric first.",
            metadata={"source": "text"},
        ),
    )

    recent_turns = await adapter.recent_turns(second_ref, limit=5)

    assert started.session.room_id == "talkwise-conversation:1"
    assert state.conversations[1].title == "Renewal practice"
    assert state.conversations[1].model == "gpt-training"
    assert state.conversations[1].metadata["runtime"] == "conversation_message_tree"
    assert state.conversations[1].metadata["trainingSessionId"] == "training-text-1"
    assert [message.role for message in state.messages] == ["user", "assistant"]
    assert state.messages[0].parent_message_id is None
    assert state.messages[0].provider == "openai"
    assert state.messages[0].model == "gpt-test"
    assert state.messages[1].parent_message_id == state.messages[0].public_id
    assert second_ref.provider == "talkwise-conversation"
    assert second_ref.branch_tail_message_id == state.messages[1].public_id
    assert [turn.text for turn in recent_turns] == [
        "Can we start with a smaller pilot?",
        "Yes, if we define a measurable success metric first.",
    ]
    assert recent_turns[1].metadata["parent_message_id"] == state.messages[0].public_id
