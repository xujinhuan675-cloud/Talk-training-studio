from __future__ import annotations

import pytest
from pydantic import ValidationError

from application.services.stakeholder.battle_prep_service import BattlePrepService
from application.services.stakeholder.dto import ChatRoomDTO, CreateChatRoomDTO, StartBattleDTO
from application.services.stakeholder.persona_editor_service import PersonaEditorService
from application.services.stakeholder.persona_loader import PersonaLoader
from application.services.training_studio.training_core import ConversationRef
from domain.stakeholder.persona_entity import Persona
from domain.training_studio.session import TrainingSession


def test_start_battle_dto_limits_manual_training_points_to_five() -> None:
    with pytest.raises(ValidationError):
        StartBattleDTO(
            persona_name="Interviewer",
            persona_role="AI product interviewer",
            persona_style="Structured and evidence-oriented.",
            scenario_context="A comprehensive AI product manager interview.",
            selected_training_points=[
                "Open with an AI Agent product narrative",
                "Explain XStable responsibilities and evidence",
                "Frame NOFX as local product adaptation",
                "Show OpenEvolve mechanism understanding",
                "Handle pressure follow-up questions",
                "Keep risk boundaries clear",
            ],
            difficulty="hard",
        )


class _StubChatRoomService:
    def __init__(self) -> None:
        self.created_rooms: list[CreateChatRoomDTO] = []

    async def create_room(self, dto: CreateChatRoomDTO, *, access_scope=None) -> ChatRoomDTO:
        self.created_rooms.append(dto)
        self.access_scope = access_scope
        return ChatRoomDTO(
            id=1,
            name=dto.name,
            type=dto.type,
            persona_ids=dto.persona_ids,
            scenario_id=dto.scenario_id,
        )


class _StubTrainingSessionService:
    def __init__(self) -> None:
        self.created_payloads = []
        self.started_scopes = []
        self.sessions: dict[str, TrainingSession] = {}

    async def create_session(self, payload):
        self.created_payloads.append(payload)
        session = TrainingSession(
            session_id=f"training-{len(self.created_payloads)}",
            task_config=payload.task_config.to_domain(),
            mode=payload.mode,
            user_id=payload.user_id,
            team_id=payload.team_id,
        )
        self.sessions[session.session_id] = session
        return session

    async def get_session(self, session_id, *, access_scope):
        self.started_scopes.append(access_scope)
        return self.sessions[session_id]

    async def start_session(self, session_id, room_id=None, *, metadata=None, access_scope):
        self.started_scopes.append(access_scope)
        session = self.sessions[session_id]
        session.task_config.metadata.update(dict(metadata or {}))
        session.start(room_id)
        return session

    async def fail_session(self, session_id, reason, *, access_scope):
        self.sessions[session_id].fail(reason)
        return self.sessions[session_id]


class _StubConversationAdapter:
    async def create_conversation(self, session):
        self.created_for = session
        return ConversationRef(
            provider="talkwise-conversation",
            conversation_id="conversation-1",
            metadata={
                "runtime": "conversation_message_tree",
                "trainingSessionId": session.session_id,
                "personaIds": list(session.task_config.metadata["persona_ids"]),
            },
        )

    async def append_turn(self, conversation, turn):
        return conversation

    async def recent_turns(self, conversation, *, limit):
        return []


@pytest.mark.asyncio
async def test_start_battle_creates_owned_persisted_persona(tmp_path) -> None:
    persona_dir = tmp_path / "missing" / "personas"
    loader = PersonaLoader(persona_dir=str(persona_dir))
    editor = PersonaEditorService(persona_dir=str(persona_dir), persona_loader=loader)
    chatroom_service = _StubChatRoomService()
    personas = {}

    class _PersonaRepository:
        async def save_structured_persona(self, persona):
            personas[persona.id] = persona
            return persona

    class _Uow:
        stakeholder_persona_repository = _PersonaRepository()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    service = BattlePrepService(
        uow_factory=_Uow,
        llm=None,  # start_battle does not call the LLM.
        chatroom_service=chatroom_service,
        persona_editor=editor,
        persona_loader=loader,
        persona_dir=str(persona_dir),
    )

    from application.services.stakeholder.room_access_policy import StakeholderRoomAccessScope

    room = await service.start_battle(
        StartBattleDTO(
            persona_name="Alex",
            persona_role="VP Sales",
            persona_style="Direct and skeptical, but willing to engage with clear facts.",
            scenario_context="A budget review meeting for a new training program.",
            selected_training_points=["Handle budget objections"],
            difficulty="normal",
            reply_language="en-US",
        ),
        access_scope=StakeholderRoomAccessScope(
            user_id="newapi:42",
            team_id="team-a",
            unrestricted=True,
        ),
    )

    assert len(personas) == 1
    persona = next(iter(personas.values()))
    assert room.type == "battle_prep"
    assert room.persona_ids == [persona.id]
    assert chatroom_service.created_rooms[0].persona_ids == [persona.id]
    assert persona.owner_user_id == "newapi:42"
    assert persona.owner_team_id == "team-a"
    assert persona.visibility == "private"
    assert "真实对手扮演守则" in persona.profile_summary
    assert "不是训练系统的讲解员" in persona.profile_summary
    assert "回复语言" in persona.profile_summary
    assert "English（en-US）" in persona.profile_summary
    assert "Handle budget objections" in persona.profile_summary

    loaded = loader.get_persona(persona.id)
    assert loaded is not None
    assert "Handle budget objections" in loaded.profile_summary
    assert len(loaded.profile_summary) > 200
    assert chatroom_service.access_scope.user_id == "newapi:42"
    assert chatroom_service.access_scope.unrestricted is False


@pytest.mark.asyncio
async def test_launch_battle_training_binds_owned_session_to_message_tree(tmp_path) -> None:
    persona_dir = tmp_path / "missing" / "personas"
    loader = PersonaLoader(persona_dir=str(persona_dir))
    editor = PersonaEditorService(persona_dir=str(persona_dir), persona_loader=loader)
    chatroom_service = _StubChatRoomService()
    training_session_service = _StubTrainingSessionService()
    conversation_adapter = _StubConversationAdapter()
    personas = {}

    class _PersonaRepository:
        async def save_structured_persona(self, persona):
            personas[persona.id] = persona
            return persona

    class _Uow:
        stakeholder_persona_repository = _PersonaRepository()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            return None

    service = BattlePrepService(
        uow_factory=_Uow,
        llm=None,
        chatroom_service=chatroom_service,
        persona_editor=editor,
        persona_loader=loader,
        persona_dir=str(persona_dir),
    )
    from application.services.stakeholder.room_access_policy import StakeholderRoomAccessScope

    launch = await service.launch_battle_training(
        StartBattleDTO(
            persona_name="Alex",
            persona_role="VP Sales",
            persona_style="Direct and skeptical.",
            scenario_context="Budget review for a training program.",
            selected_training_points=["Handle budget objections"],
            difficulty="hard",
        ),
        access_scope=StakeholderRoomAccessScope(
            user_id="newapi:42",
            team_id="team-a",
            unrestricted=True,
        ),
        training_session_service=training_session_service,
        conversation_adapter=conversation_adapter,
    )

    payload = training_session_service.created_payloads[0]
    session = launch.started.session
    response = launch.to_dict()

    assert payload.mode == "text"
    assert payload.user_id == "newapi:42"
    assert payload.team_id == "team-a"
    assert chatroom_service.access_scope.unrestricted is False
    assert payload.task_config.metadata["runtime"] == "conversation_message_tree"
    assert payload.task_config.metadata["legacy_room_id"] == launch.room.id
    assert payload.task_config.metadata["persona_snapshot"]["persona_id"] == launch.room.persona_ids[0]
    assert session.room_id == "talkwise-conversation:conversation-1"
    assert session.task_config.metadata["runtime"] == "conversation_message_tree"
    assert session.task_config.metadata["conversationId"] == "conversation-1"
    assert conversation_adapter.created_for.session_id == session.session_id
    assert training_session_service.started_scopes[0].user_id == "newapi:42"
    assert response["training_session"]["session_id"] == session.session_id
    assert response["training_session"]["conversation"]["conversationId"] == "conversation-1"
    assert response["conversation_id"] == "conversation-1"
    assert response["room_id"] == launch.room.id
    assert response["persona_snapshot"]["persona_id"] in personas


@pytest.mark.asyncio
async def test_launch_persona_training_preserves_persona_builder_snapshot(tmp_path) -> None:
    persona_dir = tmp_path / "missing" / "personas"
    loader = PersonaLoader(persona_dir=str(persona_dir))
    persona = Persona(
        id="persona-builder-1",
        name="Morgan",
        role="Procurement Director",
        profile_summary="Needs a defensible supplier comparison and clear risk controls.",
        user_context="Challenge unsupported commercial claims and require evidence.",
        owner_user_id="newapi:42",
        owner_team_id="team-a",
        visibility="private",
        version=3,
    )
    loader._v2_by_id[persona.id] = persona
    chatroom_service = _StubChatRoomService()
    training_session_service = _StubTrainingSessionService()

    service = BattlePrepService(
        uow_factory=object,
        llm=None,
        chatroom_service=chatroom_service,
        persona_editor=None,
        persona_loader=loader,
        persona_dir=str(persona_dir),
    )
    from application.services.stakeholder.room_access_policy import StakeholderRoomAccessScope

    launch = await service.launch_persona_training(
        persona.id,
        access_scope=StakeholderRoomAccessScope(user_id="newapi:42", team_id="team-a"),
        training_session_service=training_session_service,
        conversation_adapter=_StubConversationAdapter(),
    )

    payload = training_session_service.created_payloads[0]
    assert launch.persona_snapshot["persona_id"] == persona.id
    assert launch.persona_snapshot["version"] == 3
    assert payload.task_config.metadata["training_source"] == "persona_builder"
    assert payload.task_config.metadata["persona_snapshot"]["version"] == 3
    assert payload.task_config.metadata["persona_ids"] == [persona.id]
    assert launch.started.session.room_id == "talkwise-conversation:conversation-1"
