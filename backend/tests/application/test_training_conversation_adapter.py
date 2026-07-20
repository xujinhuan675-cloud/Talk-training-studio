from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from application.dto import EditMessageDTO, ForkConversationDTO, RetryMessageDTO
from application.services.conversation_service import ConversationApplicationService
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingSessionService,
)
from application.services.training_studio.training_core import (
    ConversationRef,
    TrainingCoreOrchestrator,
    TrainingTurn,
)
from domain.conversation.entity import Conversation as ConversationEntity
from domain.conversation.entity import Message as ConversationMessage
from domain.stakeholder.entity import ChatRoom, Message
from domain.training_studio.session_repository import TrainingSessionAccessScope
from infrastructure.adapters.training_conversation import (
    ConversationTrainingConversationAdapter,
    StakeholderRoomTrainingConversationAdapter,
)
from domain.conversation.repository import OwnedMetadataScope


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
    conversation_get_calls: list[dict[str, object]] = field(default_factory=list)
    conversation_update_calls: list[dict[str, object]] = field(default_factory=list)
    message_create_calls: list[ConversationMessage] = field(default_factory=list)
    message_list_calls: list[dict[str, object]] = field(default_factory=list)


def _conversation_scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


def _metadata_text(metadata: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _matches_conversation_scope(
    metadata: dict[str, object] | None,
    scope: OwnedMetadataScope | None,
) -> bool:
    if scope is None:
        return True
    metadata = dict(metadata or {})
    auth_scope = metadata.get("authScope") if isinstance(metadata.get("authScope"), dict) else {}
    owner_user_id = _metadata_text(auth_scope, "userId", "user_id") or _metadata_text(
        metadata,
        "ownerUserId",
        "owner_user_id",
        "createdByUserId",
        "created_by_user_id",
    )
    owner_team_id = _metadata_text(auth_scope, "teamId", "team_id") or _metadata_text(
        metadata,
        "teamId",
        "team_id",
        "ownerTeamId",
        "owner_team_id",
    )
    if owner_user_id and owner_user_id == scope.user_id:
        return True
    if scope.include_team_scope and owner_team_id and owner_team_id == scope.team_id:
        return True
    if not owner_user_id and owner_team_id and owner_team_id == scope.team_id:
        return True
    if not owner_user_id and not owner_team_id:
        return scope.allow_unscoped
    return False


class _ConversationRepository:
    def __init__(self, state: _ConversationState) -> None:
        self._state = state

    async def create(self, conversation: ConversationEntity) -> ConversationEntity:
        now = _utcnow()
        saved = ConversationEntity(
            id=len(self._state.conversations) + 1,
            title=conversation.title,
            system_prompt=conversation.system_prompt,
            model=conversation.model,
            status=conversation.status,
            metadata=conversation.metadata,
            created_at=conversation.created_at or now,
            updated_at=conversation.updated_at or now,
            deleted_at=conversation.deleted_at,
        )
        self._state.conversations[saved.id] = saved
        return saved

    async def get_by_id(
        self,
        conversation_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationEntity | None:
        self._state.conversation_get_calls.append(
            {"conversation_id": conversation_id, "metadata_scope": metadata_scope}
        )
        conversation = self._state.conversations.get(conversation_id)
        if conversation is None:
            return None
        if not _matches_conversation_scope(conversation.metadata, metadata_scope):
            return None
        return conversation

    async def update(
        self,
        conversation: ConversationEntity,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> ConversationEntity:
        self._state.conversation_update_calls.append(
            {"conversation_id": conversation.id, "metadata_scope": metadata_scope}
        )
        if conversation.id is None:
            raise AssertionError("Conversation id is required for update")
        if not _matches_conversation_scope(conversation.metadata, metadata_scope):
            raise AssertionError("Conversation is outside metadata scope")
        self._state.conversations[conversation.id] = conversation
        return conversation


class _ConversationMessageRepository:
    def __init__(self, state: _ConversationState) -> None:
        self._state = state

    async def create(self, message: ConversationMessage) -> ConversationMessage:
        self._state.message_create_calls.append(message)
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
            created_at=message.created_at or _utcnow(),
        )
        self._state.messages.append(saved)
        return saved

    async def get_by_public_id(self, public_id: str) -> ConversationMessage | None:
        return next(
            (message for message in self._state.messages if message.public_id == public_id),
            None,
        )

    async def update(self, message: ConversationMessage) -> ConversationMessage:
        for index, current in enumerate(self._state.messages):
            if current.public_id == message.public_id:
                self._state.messages[index] = message
                return message
        raise AssertionError(f"Message {message.public_id} was not seeded")

    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
        branch_id: str | None = None,
        statuses: list[str] | None = None,
        include_deleted: bool = False,
    ) -> list[ConversationMessage]:
        self._state.message_list_calls.append(
            {
                "conversation_id": conversation_id,
                "branch_id": branch_id,
                "limit": limit,
            }
        )
        allowed_statuses = set(statuses or [])
        messages = [
            message
            for message in self._state.messages
            if message.conversation_id == conversation_id
            and (branch_id is None or message.branch_id == branch_id)
            and (
                message.status in allowed_statuses
                if allowed_statuses
                else include_deleted or message.status != "deleted"
            )
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
            "dispatcher": {"strategy": "stakeholder_turns"},
            "evaluation": {"rubric_id": "sales-v1"},
            "growth_report": {"report_id": "growth-1"},
            "live_guidance": {"enabled": True},
        },
    )


def _session_payload(mode: str = "text") -> CreateTrainingSessionDTO:
    return CreateTrainingSessionDTO(
        task_config=_task_config(),
        mode=mode,
        user_id="user-sales-001",
        team_id="team-revenue",
    )


def _session_scope() -> TrainingSessionAccessScope:
    return TrainingSessionAccessScope(
        user_id="user-sales-001",
        team_id="team-revenue",
    )


def _training_semantics(metadata: dict[str, object]) -> dict[str, object]:
    keys = (
        "runtime",
        "trainingSessionId",
        "mode",
        "category",
        "personaIds",
        "scenarioId",
        "dispatcher",
        "evaluation",
        "growthReport",
        "liveGuidance",
    )
    return {key: metadata[key] for key in keys}


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

    started = await orchestrator.start_session(_session_payload("voice"))
    updated = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Can we begin with a smaller pilot?",
            metadata={"source": "text"},
        ),
        access_scope=_session_scope(),
    )

    recent_turns = await adapter.recent_turns(updated, limit=5)

    assert started.session.room_id == "1"
    assert started.conversation.provider == "talkwise-stakeholder-room"
    assert started.conversation.metadata["runtime"] == "stakeholder_room"
    assert started.conversation.metadata["personaIds"] == ["customer-1"]
    assert started.conversation.metadata["scenarioId"] == 9
    assert started.conversation.metadata["dispatcher"] == {"strategy": "stakeholder_turns"}
    assert started.conversation.metadata["evaluation"] == {"rubric_id": "sales-v1"}
    assert started.conversation.metadata["growthReport"] == {"report_id": "growth-1"}
    assert started.conversation.metadata["liveGuidance"] == {"enabled": True}
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
    session = await session_service.create_session(_session_payload("text"))
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

    started = await orchestrator.start_session(_session_payload("text"))
    first_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Can we start with a smaller pilot?",
            metadata={"source": "text", "provider": "openai", "model": "gpt-test"},
        ),
        access_scope=_session_scope(),
    )
    second_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=ConversationRef(
            provider=first_ref.provider,
            conversation_id=first_ref.conversation_id,
            legacy_room_id=first_ref.legacy_room_id,
            metadata=first_ref.metadata,
        ),
        turn=TrainingTurn(
            speaker="assistant",
            text="Yes, if we define a measurable success metric first.",
            metadata={"source": "text"},
        ),
        access_scope=_session_scope(),
    )

    recent_turns = await adapter.recent_turns(second_ref, limit=5)

    assert started.session.room_id == "talkwise-conversation:1"
    assert state.conversations[1].title == "Renewal practice"
    assert state.conversations[1].model == "gpt-training"
    assert state.conversations[1].metadata["runtime"] == "conversation_message_tree"
    assert state.conversations[1].metadata["trainingSessionId"] == "training-text-1"
    assert state.conversations[1].metadata["personaIds"] == ["customer-1"]
    assert state.conversations[1].metadata["scenarioId"] == 9
    assert state.conversations[1].metadata["dispatcher"] == {"strategy": "stakeholder_turns"}
    assert state.conversations[1].metadata["evaluation"] == {"rubric_id": "sales-v1"}
    assert state.conversations[1].metadata["growthReport"] == {"report_id": "growth-1"}
    assert state.conversations[1].metadata["liveGuidance"] == {"enabled": True}
    assert state.conversations[1].metadata["branchId"] == "main"
    assert state.conversations[1].metadata["branchPolicy"]["selectedPathPurpose"] == (
        "training_replay_context"
    )
    assert state.conversations[1].metadata["selectedPath"] == {
        "branchId": "main",
        "tailMessageId": state.messages[1].public_id,
        "messageIds": [
            state.messages[0].public_id,
            state.messages[1].public_id,
        ],
        "purpose": "training_replay_context",
        "replayContextOnly": True,
        "affectsScoring": False,
        "affectsCompletion": False,
    }
    assert state.conversations[1].metadata["currentBranchTail"] == {
        "branchId": "main",
        "messageId": state.messages[1].public_id,
    }
    assert started.conversation.metadata["runtime"] == "conversation_message_tree"
    assert started.conversation.metadata["personaIds"] == ["customer-1"]
    assert started.conversation.metadata["branchId"] == "main"
    assert started.conversation.metadata["selectedPath"]["tailMessageId"] is None
    assert started.conversation.metadata["currentBranchTail"]["messageId"] is None
    assert [message.role for message in state.messages] == ["user", "assistant"]
    assert state.messages[0].parent_message_id is None
    assert state.messages[0].metadata["branch_id"] == "main"
    assert state.messages[0].provider == "openai"
    assert state.messages[0].model == "gpt-test"
    assert state.messages[1].parent_message_id == state.messages[0].public_id
    assert second_ref.provider == "talkwise-conversation"
    assert second_ref.branch_tail_message_id == state.messages[1].public_id
    assert second_ref.metadata["selectedPath"]["purpose"] == "training_replay_context"
    assert second_ref.metadata["selectedPath"]["affectsScoring"] is False
    assert second_ref.metadata["currentBranchTail"]["messageId"] == state.messages[1].public_id
    assert [turn.text for turn in recent_turns] == [
        "Can we start with a smaller pilot?",
        "Yes, if we define a measurable success metric first.",
    ]
    assert recent_turns[1].metadata["parent_message_id"] == state.messages[0].public_id
    assert [call["metadata_scope"].user_id for call in state.conversation_get_calls] == [
        "user-sales-001",
        "user-sales-001",
        "user-sales-001",
    ]
    assert [call["metadata_scope"].team_id for call in state.conversation_get_calls] == [
        "team-revenue",
        "team-revenue",
        "team-revenue",
    ]
    assert all(call["metadata_scope"].allow_unscoped is False for call in state.conversation_get_calls)
    assert all(
        call["metadata_scope"].allow_unscoped is False
        for call in state.conversation_update_calls
    )


@pytest.mark.asyncio
async def test_conversation_adapter_stamps_session_auth_metadata_over_task_metadata() -> None:
    state = _ConversationState()
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "training-text-auth"),
        conversation_adapter=adapter,
    )
    base_task_config = _task_config()
    task_config = base_task_config.model_copy(
        update={
            "metadata": {
                **base_task_config.metadata,
                "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                "ownerUserId": "user-cs-001",
                "owner_user_id": "user-cs-002",
                "createdByUserId": "user-cs-003",
                "created_by_user_id": "user-cs-004",
                "teamId": "team-service",
                "team_id": "team-cs-002",
                "ownerTeamId": "team-cs-003",
                "owner_team_id": "team-cs-004",
            },
        }
    )

    started = await orchestrator.start_session(
        CreateTrainingSessionDTO(
            task_config=task_config,
            mode="text",
            user_id=" user-sales-001 ",
            team_id=" team-revenue ",
        )
    )

    metadata = state.conversations[1].metadata
    assert metadata["ownerUserId"] == "user-sales-001"
    assert metadata["teamId"] == "team-revenue"
    assert metadata["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }
    assert started.conversation.metadata["ownerUserId"] == "user-sales-001"
    assert started.conversation.metadata["teamId"] == "team-revenue"
    assert started.conversation.metadata["authScope"] == metadata["authScope"]
    assert metadata["runtime"] == "conversation_message_tree"
    assert metadata["branchId"] == "main"
    assert metadata["branchPolicy"]["owner"] == "training_core"
    assert metadata["room_name"] == "Renewal practice"
    for key in (
        "owner_user_id",
        "createdByUserId",
        "created_by_user_id",
        "team_id",
        "ownerTeamId",
        "owner_team_id",
    ):
        assert key not in metadata


@pytest.mark.asyncio
async def test_conversation_adapter_rejects_message_tree_session_without_auth_scope() -> None:
    state = _ConversationState()
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    session_service = TrainingSessionService(id_factory=lambda: "training-text-no-auth")
    session = await session_service.create_session(
        CreateTrainingSessionDTO(task_config=_task_config(), mode="text")
    )

    with pytest.raises(ValueError, match="metadata auth scope is required"):
        await adapter.create_conversation(session)

    assert state.conversations == {}


@pytest.mark.asyncio
async def test_conversation_adapter_model_selection_metadata_cannot_shadow_training_semantics(
) -> None:
    state = _ConversationState()
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "training-text-shadow"),
        conversation_adapter=adapter,
    )
    task_config = TrainingTaskConfigDTO(
        role="Account Manager",
        level="Senior",
        tech_stack=["renewal"],
        question_type_ratios={"craft": 1},
        question_count=3,
        category="sales",
        metadata={
            "room_name": "Renewal practice",
            "persona_ids": ["customer-1"],
            "scenario_id": 9,
            "dispatcher": {"strategy": "stakeholder_turns"},
            "evaluation": {"rubric_id": "sales-v1"},
            "growth_report": {"report_id": "growth-1"},
            "report": {"report_id": "generic-chat-report"},
            "live_guidance": {"enabled": True},
            "guidance": {"enabled": False},
            "personaIds": ["generic-chat-persona"],
            "scenarioId": 404,
            "growthReport": {"report_id": "generic-chat-growth"},
            "liveGuidance": {"enabled": False},
            "branchId": "generic-chat-branch",
            "branchPolicy": {"owner": "generic-chat"},
            "selectedPath": {"branchId": "generic-chat-branch", "affectsScoring": True},
            "currentBranchTail": {"branchId": "generic-chat-branch", "messageId": "shadow"},
            "provider": "openai",
            "model": "gpt-selected",
            "model_registry": {"default": "openai"},
            "model_spec": {"id": "gpt-selected"},
        },
    )

    started = await orchestrator.start_session(
        CreateTrainingSessionDTO(
            task_config=task_config,
            mode="text",
            user_id="user-sales-001",
            team_id="team-revenue",
        )
    )

    assert state.conversations[1].model == "gpt-selected"
    assert state.conversations[1].metadata["provider"] == "openai"
    assert state.conversations[1].metadata["model"] == "gpt-selected"
    assert state.conversations[1].metadata["model_registry"] == {"default": "openai"}
    assert state.conversations[1].metadata["model_spec"] == {"id": "gpt-selected"}
    assert state.conversations[1].metadata["personaIds"] == ["customer-1"]
    assert state.conversations[1].metadata["scenarioId"] == 9
    assert state.conversations[1].metadata["dispatcher"] == {"strategy": "stakeholder_turns"}
    assert state.conversations[1].metadata["evaluation"] == {"rubric_id": "sales-v1"}
    assert state.conversations[1].metadata["growthReport"] == {"report_id": "growth-1"}
    assert state.conversations[1].metadata["liveGuidance"] == {"enabled": True}
    assert state.conversations[1].metadata["branchId"] == "main"
    assert state.conversations[1].metadata["branchPolicy"]["owner"] == "training_core"
    assert state.conversations[1].metadata["selectedPath"]["affectsScoring"] is False
    assert state.conversations[1].metadata["currentBranchTail"]["messageId"] is None
    assert started.conversation.metadata["personaIds"] == ["customer-1"]
    assert started.conversation.metadata["scenarioId"] == 9
    assert started.conversation.metadata["growthReport"] == {"report_id": "growth-1"}
    assert started.conversation.metadata["liveGuidance"] == {"enabled": True}
    assert started.conversation.metadata["branchId"] == "main"
    assert started.conversation.metadata["branchPolicy"]["owner"] == "training_core"


@pytest.mark.asyncio
async def test_conversation_adapter_preserves_training_semantics_across_tree_edit_retry_fork(
) -> None:
    state = _ConversationState()
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "training-text-2"),
        conversation_adapter=adapter,
    )
    message_tree = ConversationApplicationService(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs)
    )

    started = await orchestrator.start_session(_session_payload("text"))
    user_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Can we restart from the risk objection?",
            metadata={
                "source": "text",
                "branch_id": "branch-risk",
                "provider": "openai",
                "model": "gpt-test",
                "status": "draft",
            },
        ),
        access_scope=_session_scope(),
    )
    assistant_ref = await orchestrator.record_turn(
        training_session_id=started.session.session_id,
        conversation=user_ref,
        turn=TrainingTurn(
            speaker="assistant",
            text="Yes, frame the pilot as a reversible decision.",
            metadata={"source": "text", "branch_id": "branch-risk"},
        ),
        access_scope=_session_scope(),
    )
    original_user = state.messages[0]
    original_assistant = state.messages[1]
    expected_semantics = _training_semantics(state.conversations[1].metadata)

    assert assistant_ref.metadata["branchId"] == "branch-risk"
    assert assistant_ref.metadata["selectedPath"]["messageIds"] == [
        original_user.public_id,
        original_assistant.public_id,
    ]
    assert assistant_ref.metadata["currentBranchTail"]["messageId"] == (
        original_assistant.public_id
    )
    assert state.conversations[1].metadata["selectedPath"]["purpose"] == (
        "training_replay_context"
    )
    assert state.conversations[1].metadata["selectedPath"]["affectsCompletion"] is False

    edited = await message_tree.edit_message(
        1,
        original_user.public_id,
        EditMessageDTO(
            content="Can we restart from the budget objection?",
            metadata={"reason": "clarity", "message_tree_status": "edited"},
        ),
        metadata_scope=_conversation_scope(),
    )
    retry = await message_tree.retry_message(
        1,
        original_assistant.public_id,
        RetryMessageDTO(
            content="Retry the counterpart answer with a sharper metric.",
            metadata={"temperature": 0.1, "message_tree_status": "retry"},
        ),
        metadata_scope=_conversation_scope(),
    )
    forked = await message_tree.fork_conversation(
        1,
        retry.public_id,
        ForkConversationDTO(
            title="Risk objection review",
            option="directPath",
            statuses=["active", "superseded"],
            metadata={
                "fork_reason": "manager review",
                "message_tree_status": "forked",
                "status": "review-draft",
            },
        ),
        metadata_scope=_conversation_scope(),
    )

    assert _training_semantics(state.conversations[1].metadata) == expected_semantics
    assert _training_semantics(started.conversation.metadata) == expected_semantics
    assert _training_semantics(assistant_ref.metadata) == expected_semantics
    assert state.messages[0].status == "superseded"
    assert state.messages[1].status == "superseded"
    assert edited.metadata["edit_of"] == original_user.public_id
    assert retry.metadata["retry_of"] == original_assistant.public_id
    assert state.messages[0].metadata["status"] == "draft"
    assert state.messages[0].status != state.messages[0].metadata["status"]

    assert _training_semantics(forked.conversation.metadata) == expected_semantics
    assert forked.conversation.metadata["forked_from_conversation_id"] == 1
    assert forked.conversation.metadata["forked_from_message_id"] == retry.public_id
    assert forked.conversation.metadata["fork_reason"] == "manager review"
    assert forked.conversation.metadata["message_tree_status"] == "forked"
    assert forked.conversation.metadata["status"] == "review-draft"
    assert forked.conversation.metadata["selectedPath"]["purpose"] == (
        "training_replay_context"
    )
    assert forked.conversation.metadata["selectedPath"]["affectsScoring"] is False
    assert forked.conversation.status == "active"
    assert forked.messages[-1].metadata["forked_from_message_id"] == retry.public_id


@pytest.mark.asyncio
async def test_conversation_adapter_scoped_miss_does_not_create_message() -> None:
    state = _ConversationState(
        conversations={
            1: ConversationEntity(
                id=1,
                title="Other owner",
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                    "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                },
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        }
    )
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    conversation = ConversationRef(
        provider="talkwise-conversation",
        conversation_id="1",
        metadata={
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
            "branchId": "main",
        },
    )

    with pytest.raises(ValueError, match="Conversation 1 not found"):
        await adapter.append_turn(
            conversation,
            TrainingTurn(speaker="user", text="This should not be persisted."),
        )

    assert state.message_create_calls == []
    assert state.messages == []
    assert state.conversation_get_calls[0]["metadata_scope"].user_id == "user-sales-001"
    assert state.conversation_update_calls == []


@pytest.mark.asyncio
async def test_conversation_adapter_scoped_miss_does_not_read_messages() -> None:
    state = _ConversationState(
        conversations={
            1: ConversationEntity(
                id=1,
                title="Other owner",
                metadata={
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                    "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                },
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
        },
        messages=[
            ConversationMessage(
                id=1,
                conversation_id=1,
                role="user",
                content="Hidden",
                branch_id="main",
            )
        ],
    )
    adapter = ConversationTrainingConversationAdapter(
        lambda **kwargs: _ConversationUnitOfWork(state, **kwargs),
        default_model="gpt-training",
    )
    conversation = ConversationRef(
        provider="talkwise-conversation",
        conversation_id="1",
        metadata={
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
            "branchId": "main",
        },
    )

    with pytest.raises(ValueError, match="Conversation 1 not found"):
        await adapter.recent_turns(conversation, limit=5)

    assert state.message_list_calls == []
