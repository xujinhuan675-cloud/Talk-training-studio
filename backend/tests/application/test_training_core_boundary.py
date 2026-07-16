import pytest

from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import TrainingSessionService
from application.services.training_studio.training_core import (
    ConversationRef,
    TrainingCoreOrchestrator,
    TrainingTurn,
)
from domain.training_studio.session import TrainingSession


class FakeConversationAdapter:
    def __init__(self) -> None:
        self.turns: list[TrainingTurn] = []

    async def create_conversation(self, session: TrainingSession) -> ConversationRef:
        return ConversationRef(
            provider="talkwise-text",
            conversation_id=f"conversation-{session.session_id}",
            legacy_room_id="42",
        )

    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef:
        self.turns.append(turn)
        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id=turn.turn_id,
            legacy_room_id=conversation.legacy_room_id,
            metadata=conversation.metadata,
        )

    async def recent_turns(self, conversation: ConversationRef, *, limit: int):
        return self.turns[-limit:]


def _task_config() -> TrainingTaskConfigDTO:
    return TrainingTaskConfigDTO(
        role="Product Manager",
        level="Senior",
        tech_stack=["Roadmap", "Metrics"],
        question_type_ratios={"behavioral": 2, "craft": 1},
        question_count=6,
    )


@pytest.mark.asyncio
async def test_training_core_starts_session_with_runtime_conversation_binding():
    adapter = FakeConversationAdapter()
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "session-1"),
        conversation_adapter=adapter,
    )

    result = await orchestrator.start_session(_task_config())

    assert result.session.session_id == "session-1"
    assert result.session.room_id == "42"
    assert result.conversation.provider == "talkwise-text"
    assert result.conversation.conversation_id == "conversation-session-1"


@pytest.mark.asyncio
async def test_training_core_records_turns_and_preserves_branch_tail():
    adapter = FakeConversationAdapter()
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
    )
    started = await orchestrator.start_session(_task_config())

    updated = await orchestrator.record_turn(
        training_session_id="session-1",
        conversation=started.conversation,
        turn=TrainingTurn(speaker="user", text="The price feels high.", turn_id="msg-user-1"),
    )

    session = await session_service.get_session("session-1")
    assert session.message_count == 1
    assert updated.branch_tail_message_id == "msg-user-1"


@pytest.mark.asyncio
async def test_training_core_guidance_reads_recent_turns_from_adapter():
    adapter = FakeConversationAdapter()
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
    )
    started = await orchestrator.start_session(_task_config())
    await orchestrator.record_turn(
        training_session_id="session-1",
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="This may be a concern because the budget is tight.",
            turn_id="msg-user-1",
        ),
    )

    events = await orchestrator.generate_guidance(
        training_session_id="session-1",
        conversation=started.conversation,
        task_goal="Handle pricing pushback",
        rubric={"clarity": 0.4},
    )

    assert events
    assert {event.event_type for event in events}
