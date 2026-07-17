import ast
import inspect

import pytest

import application.services.training_studio.training_core as training_core_module
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.live_guidance_service import (
    TrainingLiveGuidanceService,
)
from application.services.training_studio.session_service import TrainingSessionService
from application.services.training_studio.training_core import (
    ConversationRef,
    TrainingCoreOrchestrator,
    TrainingTurn,
    training_core_metadata_for_session,
)
from domain.training_studio.session import TrainingSession


class FakeConversationAdapter:
    def __init__(
        self,
        *,
        provider: str = "talkwise-text",
        conversation_id_prefix: str = "conversation",
        legacy_room_id: str | None = "42",
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.turns: list[TrainingTurn] = []
        self.appended_conversations: list[ConversationRef] = []
        self.recent_turn_conversations: list[ConversationRef] = []
        self.recent_turn_limits: list[int] = []
        self.provider = provider
        self.conversation_id_prefix = conversation_id_prefix
        self.legacy_room_id = legacy_room_id
        self.metadata = dict(metadata or {})

    async def create_conversation(self, session: TrainingSession) -> ConversationRef:
        return ConversationRef(
            provider=self.provider,
            conversation_id=f"{self.conversation_id_prefix}-{session.session_id}",
            legacy_room_id=self.legacy_room_id,
            metadata=self.metadata,
        )

    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ) -> ConversationRef:
        self.appended_conversations.append(conversation)
        self.turns.append(turn)
        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id=turn.turn_id,
            legacy_room_id=conversation.legacy_room_id,
            metadata=conversation.metadata,
        )

    async def recent_turns(self, conversation: ConversationRef, *, limit: int):
        self.recent_turn_conversations.append(conversation)
        self.recent_turn_limits.append(limit)
        return self.turns[-limit:]


class InvalidConversationAdapter(FakeConversationAdapter):
    async def create_conversation(self, session: TrainingSession):
        return {"provider": "not-a-conversation-ref"}


class InvalidAppendConversationAdapter(FakeConversationAdapter):
    async def append_turn(
        self,
        conversation: ConversationRef,
        turn: TrainingTurn,
    ):
        return {"provider": conversation.provider}


class InvalidRecentTurnsConversationAdapter(FakeConversationAdapter):
    async def recent_turns(self, conversation: ConversationRef, *, limit: int):
        return [{"speaker": "user", "text": "not-a-training-turn"}]


def _task_config() -> TrainingTaskConfigDTO:
    return TrainingTaskConfigDTO(
        role="Product Manager",
        level="Senior",
        tech_stack=["Roadmap", "Metrics"],
        question_type_ratios={"behavioral": 2, "craft": 1},
        question_count=6,
    )


def test_training_core_module_does_not_own_conversation_or_voice_runtimes():
    tree = ast.parse(inspect.getsource(training_core_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert not any(module.startswith("domain.conversation") for module in imported_modules)
    assert not any(module.startswith("domain.stakeholder") for module in imported_modules)
    assert not any(module.startswith("infrastructure.adapters") for module in imported_modules)
    assert not any(module.lower().startswith("pipecat") for module in imported_modules)
    assert not any(module.lower().startswith("librechat") for module in imported_modules)


@pytest.mark.asyncio
async def test_training_core_metadata_keeps_talkwise_semantics_inside_core_boundary():
    session_service = TrainingSessionService(id_factory=lambda: "session-semantic-1")
    session = await session_service.create_session(
        {
            "role": "Product Manager",
            "level": "Senior",
            "tech_stack": ["Roadmap"],
            "question_type_ratios": {"craft": 1},
            "question_count": 3,
            "category": "sales",
            "scenario_template_id": "enterprise-renewal",
            "metadata": {
                "persona_ids": ["buyer", " cfo "],
                "scenario_id": 9,
                "dispatcher": {"policy": "round_robin"},
                "evaluation": {"rubric_id": "sales-v1"},
                "growth_report": {"report_id": "growth-1"},
                "live_guidance": {"enabled": True},
            },
        }
    )

    metadata = training_core_metadata_for_session(
        session,
        runtime="conversation_message_tree",
        extra={"branchId": "main"},
    )

    assert metadata == {
        "runtime": "conversation_message_tree",
        "trainingSessionId": "session-semantic-1",
        "mode": "text",
        "scenarioTemplateId": "enterprise-renewal",
        "category": "sales",
        "personaIds": ["buyer", "cfo"],
        "scenarioId": 9,
        "dispatcher": {"policy": "round_robin"},
        "evaluation": {"rubric_id": "sales-v1"},
        "growthReport": {"report_id": "growth-1"},
        "liveGuidance": {"enabled": True},
        "branchId": "main",
    }


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


@pytest.mark.parametrize(
    ("provider", "legacy_room_id", "expected_room_id", "metadata"),
    [
        (
            "talkwise-conversation",
            None,
            "talkwise-conversation:conversation-session-1",
            {"runtime": "conversation_message_tree", "branchId": "main"},
        ),
        (
            "pipecat-realtime",
            None,
            "pipecat-realtime:conversation-session-1",
            {"runtime": "voice_pipeline", "transport": "webrtc"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_training_core_contract_accepts_text_and_voice_conversation_refs(
    provider,
    legacy_room_id,
    expected_room_id,
    metadata,
):
    adapter = FakeConversationAdapter(
        provider=provider,
        legacy_room_id=legacy_room_id,
        metadata=metadata,
    )
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
    )
    turn = TrainingTurn(
        speaker="user",
        text="Can we define success before choosing a plan?",
        turn_id="turn-1",
        metadata={"source": "contract-test", "channel": "shared-training-core"},
    )

    started = await orchestrator.start_session(_task_config())
    updated = await orchestrator.record_turn(
        training_session_id=" session-1 ",
        conversation=started.conversation,
        turn=turn,
    )

    session = await session_service.get_session("session-1")
    assert session.room_id == expected_room_id
    assert adapter.turns[0] is turn
    assert adapter.appended_conversations[0] == started.conversation
    assert updated.provider == provider
    assert updated.branch_tail_message_id == "turn-1"
    assert updated.metadata == metadata


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
async def test_training_core_keeps_message_tree_metadata_out_of_training_semantics():
    training_metadata = {
        "runtime": "conversation_message_tree",
        "trainingSessionId": "session-1",
        "mode": "text",
        "personaIds": ["buyer", "cfo"],
        "scenarioId": 9,
        "dispatcher": {"policy": "stakeholder_turns"},
        "evaluation": {"rubric_id": "sales-v1"},
        "growthReport": {"report_id": "growth-1"},
        "liveGuidance": {"enabled": True},
        "branchId": "main",
    }
    adapter = FakeConversationAdapter(
        provider="talkwise-conversation",
        legacy_room_id=None,
        metadata=training_metadata,
    )
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
    )
    started = await orchestrator.start_session(_task_config())

    updated = await orchestrator.record_turn(
        training_session_id="session-1",
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="user",
            text="Let's retry this from the pricing branch.",
            turn_id="msg-training-edit-1",
            metadata={
                "branch_id": "branch-pricing",
                "edit_of": "msg-original",
                "retry_of": "msg-failed",
                "forked_from_message_id": "msg-fork-source",
                "status": "superseded",
                "personaIds": ["message-tree-shadow"],
                "scenarioId": 404,
                "dispatcher": {"policy": "generic-chat"},
                "evaluation": {"rubric_id": "generic"},
                "growthReport": {"report_id": "generic"},
                "liveGuidance": {"enabled": False},
            },
        ),
    )

    assert updated.metadata == training_metadata
    assert adapter.appended_conversations[0].metadata == training_metadata
    assert adapter.turns[0].metadata["branch_id"] == "branch-pricing"
    assert adapter.turns[0].metadata["personaIds"] == ["message-tree-shadow"]


@pytest.mark.asyncio
async def test_training_core_guidance_preserves_turn_metadata_for_shared_evaluation():
    captured_states = []

    async def capture_state(state):
        captured_states.append(state)
        return []

    adapter = FakeConversationAdapter(
        metadata={"runtime": "voice_pipeline", "transport": "websocket"}
    )
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
        guidance_service=TrainingLiveGuidanceService(
            window_size=2,
            async_llm_callback=capture_state,
        ),
    )
    started = await orchestrator.start_session(_task_config())
    await orchestrator.record_turn(
        training_session_id="session-1",
        conversation=started.conversation,
        turn=TrainingTurn(
            speaker="counterpart",
            text="I am worried this plan creates too much risk.",
            turn_id="voice-turn-1",
            metadata={"source": "realtime_voice", "provider_event_id": "evt-1"},
        ),
    )

    await orchestrator.generate_guidance(
        training_session_id=" session-1 ",
        conversation=started.conversation,
        task_goal=" Reduce implementation risk ",
        rubric={"risk": 1.0},
        limit=1,
    )

    assert adapter.recent_turn_conversations[0] == started.conversation
    assert adapter.recent_turn_limits == [1]
    assert captured_states[0].training_session_id == "session-1"
    assert captured_states[0].task_goal == "Reduce implementation risk"
    assert captured_states[0].recent_turns[0].metadata == {
        "source": "realtime_voice",
        "provider_event_id": "evt-1",
    }


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


@pytest.mark.asyncio
async def test_training_core_guidance_reads_default_window_from_adapter():
    adapter = FakeConversationAdapter()
    session_service = TrainingSessionService(id_factory=lambda: "session-1")
    orchestrator = TrainingCoreOrchestrator(
        session_service=session_service,
        conversation_adapter=adapter,
        guidance_service=TrainingLiveGuidanceService(window_size=3),
    )
    started = await orchestrator.start_session(_task_config())
    for index in range(4):
        await orchestrator.record_turn(
            training_session_id="session-1",
            conversation=started.conversation,
            turn=TrainingTurn(
                speaker="user",
                text=f"Turn {index}",
                turn_id=f"msg-{index}",
            ),
        )

    await orchestrator.generate_guidance(
        training_session_id="session-1",
        conversation=started.conversation,
        task_goal="Handle pricing pushback",
    )

    assert adapter.recent_turn_limits == [3]


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: ConversationRef(provider=" ", conversation_id="conversation-1"), "provider"),
        (lambda: ConversationRef(provider="talkwise-text", conversation_id=" "), "conversation_id"),
        (lambda: TrainingTurn(speaker=" ", text="hello"), "speaker"),
        (lambda: TrainingTurn(speaker="user", text=" "), "text"),
    ],
)
def test_training_core_contract_rejects_empty_required_fields(factory, match):
    with pytest.raises(ValueError, match=match):
        factory()


def test_training_core_rejects_adapter_missing_contract():
    with pytest.raises(TypeError, match="TrainingConversationAdapter"):
        TrainingCoreOrchestrator(
            session_service=TrainingSessionService(id_factory=lambda: "session-1"),
            conversation_adapter=object(),
        )


def test_training_core_contract_normalizes_optional_ids_and_copies_metadata():
    metadata = {"runtime": {"name": "conversation_message_tree"}}
    turn_metadata = {"source": {"channel": "text"}}
    ref = ConversationRef(
        provider=" talkwise-conversation ",
        conversation_id=" 7 ",
        branch_tail_message_id=" ",
        legacy_room_id=" ",
        metadata=metadata,
    )
    turn = TrainingTurn(
        speaker=" user ",
        text=" Hello. ",
        turn_id=" ",
        metadata=turn_metadata,
    )
    metadata["runtime"]["name"] = "mutated"
    turn_metadata["source"]["channel"] = "mutated"
    transcript_turn = turn.to_transcript_turn()
    transcript_turn.metadata["source"]["channel"] = "mutated-again"

    assert ref.provider == "talkwise-conversation"
    assert ref.conversation_id == "7"
    assert ref.branch_tail_message_id is None
    assert ref.legacy_room_id is None
    assert ref.metadata == {"runtime": {"name": "conversation_message_tree"}}
    assert turn.speaker == "user"
    assert turn.text == "Hello."
    assert turn.turn_id is None
    assert turn.metadata == {"source": {"channel": "text"}}


@pytest.mark.asyncio
async def test_training_core_rejects_adapter_results_outside_conversation_ref_contract():
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "session-1"),
        conversation_adapter=InvalidConversationAdapter(),
    )

    with pytest.raises(TypeError, match="ConversationRef"):
        await orchestrator.start_session(_task_config())


@pytest.mark.asyncio
async def test_training_core_rejects_append_results_outside_conversation_ref_contract():
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "session-1"),
        conversation_adapter=InvalidAppendConversationAdapter(),
    )
    started = await orchestrator.start_session(_task_config())

    with pytest.raises(TypeError, match="ConversationRef"):
        await orchestrator.record_turn(
            training_session_id="session-1",
            conversation=started.conversation,
            turn=TrainingTurn(speaker="user", text="Hello."),
        )


@pytest.mark.asyncio
async def test_training_core_rejects_recent_turns_outside_training_turn_contract():
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "session-1"),
        conversation_adapter=InvalidRecentTurnsConversationAdapter(),
    )
    started = await orchestrator.start_session(_task_config())

    with pytest.raises(TypeError, match="TrainingTurn"):
        await orchestrator.generate_guidance(
            training_session_id="session-1",
            conversation=started.conversation,
            task_goal="Handle pricing pushback",
        )


@pytest.mark.asyncio
async def test_training_core_guidance_rejects_non_positive_limit():
    adapter = FakeConversationAdapter()
    orchestrator = TrainingCoreOrchestrator(
        session_service=TrainingSessionService(id_factory=lambda: "session-1"),
        conversation_adapter=adapter,
    )
    started = await orchestrator.start_session(_task_config())

    with pytest.raises(ValueError, match="limit"):
        await orchestrator.generate_guidance(
            training_session_id="session-1",
            conversation=started.conversation,
            task_goal="Handle pricing pushback",
            limit=0,
        )
