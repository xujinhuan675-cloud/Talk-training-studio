from __future__ import annotations

import pytest

from application.services.defense_training_workspace_service import (
    DefenseTrainingWorkspaceService,
)
from application.services.training_studio.training_core import ConversationRef, TrainingTurn
from domain.training_studio.session import TrainingSession, TrainingSessionMode


class FakeTrainingSessionService:
    def __init__(self) -> None:
        self.created_payload = None
        self.session: TrainingSession | None = None
        self.start_kwargs = None
        self.record_kwargs = None
        self.get_kwargs = None

    async def create_session(self, payload):
        self.created_payload = payload
        self.session = TrainingSession(
            session_id="training-defense-8",
            task_config=payload.task_config.to_domain(),
            mode=payload.mode,
            scenario_template_id=payload.scenario_template_id,
            user_id=payload.user_id,
            team_id=payload.team_id,
        )
        return self.session

    async def start_session(self, session_id, room_id, *, metadata, access_scope):
        assert self.session is not None
        self.start_kwargs = {
            "session_id": session_id,
            "room_id": room_id,
            "metadata": metadata,
            "access_scope": access_scope,
        }
        self.session.task_config.metadata.update(metadata)
        self.session.start(room_id)
        return self.session

    async def record_turns(self, session_id, count=1, *, access_scope):
        self.record_kwargs = {
            "session_id": session_id,
            "count": count,
            "access_scope": access_scope,
        }

    async def get_session(self, session_id, *, access_scope):
        self.get_kwargs = {"session_id": session_id, "access_scope": access_scope}
        assert self.session is not None
        return self.session


class FakeConversationAdapter:
    def __init__(self) -> None:
        self.created_session = None
        self.appended_turn = None
        self.recent_ref = None

    async def create_conversation(self, session):
        self.created_session = session
        return ConversationRef(
            provider="talkwise-conversation",
            conversation_id="55",
            metadata={"authScope": {"userId": session.user_id}, "branchId": "main"},
        )

    async def append_turn(self, conversation, turn):
        self.appended_turn = turn
        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id="opening-question",
            metadata=conversation.metadata,
        )

    async def recent_turns(self, conversation, *, limit):
        self.recent_ref = {"conversation": conversation, "limit": limit}
        return [
            TrainingTurn(speaker="assistant", text="What evidence supports this claim?"),
            TrainingTurn(speaker="user", text="The rollout retained 82% of users."),
        ]


@pytest.mark.asyncio
async def test_defense_workspace_binds_owner_scoped_session_and_frozen_snapshots():
    sessions = FakeTrainingSessionService()
    conversations = FakeConversationAdapter()
    service = DefenseTrainingWorkspaceService(
        session_service=sessions,
        conversation_adapter=conversations,
    )
    snapshots = [
        {
            "persona_id": "reviewer-1",
            "version": 3,
            "name": "Reviewer",
            "role": "Finance lead",
        }
    ]

    binding = await service.start_workspace(
        defense_session_id=8,
        owner_user_id="user-owner-001",
        owner_team_id="team-revenue",
        document_title="Q1 plan",
        document_text="Retention improved after onboarding changes.",
        scenario_name="Business review",
        dimensions=["evidence", "trade-offs"],
        persona_ids=["reviewer-1"],
        persona_snapshots=snapshots,
        opening_question="What evidence supports the retention claim?",
    )
    snapshots[0]["version"] = 99

    assert binding.training_session_id == "training-defense-8"
    assert binding.conversation_id == 55
    assert sessions.created_payload.mode == TrainingSessionMode.TEXT
    assert sessions.created_payload.user_id == "user-owner-001"
    assert sessions.created_payload.team_id == "team-revenue"
    assert sessions.created_payload.task_config.metadata["training_source"] == "defense_prep"
    assert sessions.created_payload.task_config.metadata["defense_session_id"] == 8
    assert sessions.created_payload.task_config.metadata["persona_snapshots"][0]["version"] == 3
    assert conversations.appended_turn.text == "What evidence supports the retention claim?"
    assert sessions.start_kwargs["access_scope"].user_id == "user-owner-001"

    turns = await service.recent_turns(
        defense_session_id=8,
        training_session_id=binding.training_session_id,
        conversation_id=binding.conversation_id,
        owner_user_id="user-owner-001",
        owner_team_id="team-revenue",
    )

    assert [turn.text for turn in turns] == [
        "What evidence supports this claim?",
        "The rollout retained 82% of users.",
    ]
    assert sessions.get_kwargs["access_scope"].user_id == "user-owner-001"
    assert conversations.recent_ref["conversation"].metadata["authScope"] == {
        "userId": "user-owner-001",
        "teamId": "team-revenue",
    }

    with pytest.raises(ValueError, match="does not match the Defense conversation"):
        await service.recent_turns(
            defense_session_id=8,
            training_session_id=binding.training_session_id,
            conversation_id=56,
            owner_user_id="user-owner-001",
            owner_team_id="team-revenue",
        )
