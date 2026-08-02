import pytest
from unittest.mock import AsyncMock, MagicMock
from application.services.defense_prep_service import DefensePrepService
from application.services.defense_training_workspace_service import DefenseTrainingWorkspaceBinding
from application.services.training_studio.training_core import ConversationRef
from application.services.training_studio.training_core import TrainingTurn
from domain.defense_prep.entity import DefenseSession
from domain.defense_prep.value_objects import DocumentSummary, PlannedQuestion, QuestionStrategy
from domain.defense_prep.scenario import ScenarioType
from domain.defense_prep.repository import DefenseSessionAccessScope


def _workspace_service():
    service = AsyncMock()
    service.start_workspace.return_value = DefenseTrainingWorkspaceBinding(
        training_session_id="training-defense-7",
        conversation=ConversationRef(
            provider="talkwise-conversation",
            conversation_id="81",
            branch_tail_message_id="message-1",
        ),
    )
    return service


@pytest.fixture
def mock_deps():
    uow = AsyncMock()
    uow.__aenter__ = AsyncMock(return_value=uow)
    uow.__aexit__ = AsyncMock(return_value=False)
    uow.defense_session_repository = AsyncMock()
    uow.commit = AsyncMock()
    llm = AsyncMock()
    parser = AsyncMock()
    chatroom_svc = AsyncMock()
    persona_loader = MagicMock()
    return uow, llm, parser, chatroom_svc, persona_loader


class TestDefensePrepService:
    @pytest.mark.asyncio
    async def test_create_session_parses_doc_and_persists(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        parser.parse.return_value = DocumentSummary(
            title="Q1报告", sections=[], key_data=["30%"], raw_text="full text"
        )
        uow.defense_session_repository.create.side_effect = lambda s: setattr(s, "id", 1) or s

        workspace_svc = _workspace_service()
        service = DefensePrepService(
            uow_factory=lambda: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=workspace_svc,
        )
        session = await service.create_session(
            file_content=b"fake pptx bytes",
            filename="Q1报告.pptx",
            persona_ids=["persona-001", "persona-002"],
            scenario_type=ScenarioType.PERFORMANCE_REVIEW,
            owner_user_id="user-sales-001",
            owner_team_id="team-revenue",
            access_scope=DefenseSessionAccessScope(
                user_id="user-sales-001",
                team_id="team-revenue",
            ),
        )
        parser.parse.assert_called_once_with(b"fake pptx bytes", "Q1报告.pptx")
        uow.defense_session_repository.create.assert_called_once()
        assert session.id == 1
        assert session.persona_ids == ["persona-001", "persona-002"]
        assert session.status == "preparing"
        assert session.owner_user_id == "user-sales-001"
        assert session.owner_team_id == "team-revenue"

    @pytest.mark.asyncio
    async def test_prepare_questions_persists_strategy_before_start(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        session = DefenseSession(
            id=7,
            persona_ids=["persona-001"],
            scenario_type=ScenarioType.GENERAL,
            document_summary=DocumentSummary(title="Plan", raw_text="content"),
            owner_user_id="user-owner-001",
        )
        uow.defense_session_repository.get_by_id.return_value = session
        service = DefensePrepService(
            uow_factory=lambda *args, **kwargs: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=_workspace_service(),
        )
        service._generate_strategy = AsyncMock(
            return_value=QuestionStrategy(
                questions=[PlannedQuestion(question="Q1", dimension="evidence")]
            )
        )

        prepared = await service.prepare_questions(
            7,
            access_scope=DefenseSessionAccessScope(user_id="user-owner-001"),
        )

        assert prepared.question_strategy.questions[0].question == "Q1"
        uow.defense_session_repository.update.assert_awaited_once_with(session)

    def test_selected_strategy_preserves_confirmed_order_and_rejects_invalid_indexes(self):
        strategy = QuestionStrategy(
            questions=[
                PlannedQuestion(question="Q1", dimension="a"),
                PlannedQuestion(question="Q2", dimension="b"),
                PlannedQuestion(question="Q3", dimension="c"),
            ]
        )

        selected = DefensePrepService._selected_strategy(
            strategy, selected_question_indexes=[2, 0, 2]
        )

        assert [question.question for question in selected.questions] == ["Q3", "Q1"]
        with pytest.raises(ValueError, match="does not belong"):
            DefensePrepService._selected_strategy(
                strategy, selected_question_indexes=[3]
            )

    @pytest.mark.asyncio
    async def test_start_session_keeps_room_owned_by_session_creator(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        session = DefenseSession(
            id=7,
            persona_ids=["persona-001"],
            scenario_type=ScenarioType.PERFORMANCE_REVIEW,
            document_summary=DocumentSummary(title="Q1", sections=[], key_data=[], raw_text="text"),
            owner_user_id="user-owner-001",
            owner_team_id="team-revenue",
        )
        uow.defense_session_repository.get_by_id.return_value = session
        uow.scenario_repository = AsyncMock()
        uow.scenario_repository.create.return_value = MagicMock(id=31)
        uow.stakeholder_message_repository = AsyncMock()
        chatroom_svc.create_room.return_value = MagicMock(id=41)
        persona = MagicMock()
        persona.name = "答辩官"
        persona_loader.get_persona.return_value = persona

        workspace_svc = _workspace_service()
        service = DefensePrepService(
            uow_factory=lambda *args, **kwargs: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=workspace_svc,
        )
        service._generate_strategy = AsyncMock(
            return_value=QuestionStrategy(
                questions=[PlannedQuestion(question="问题", dimension="业务", asked_by="persona-001")]
            )
        )

        await service.start_session(
            7,
            access_scope=DefenseSessionAccessScope(
                user_id="user-admin-001",
                team_id="team-revenue",
                include_team_scope=True,
                unrestricted=True,
            ),
        )

        room_scope = chatroom_svc.create_room.call_args.kwargs["access_scope"]
        assert room_scope.user_id == "user-owner-001"
        assert room_scope.team_id == "team-revenue"
        assert not room_scope.include_team_scope
        assert not room_scope.unrestricted
        assert session.training_session_id == "training-defense-7"
        assert session.conversation_id == 81
        workspace_svc.start_workspace.assert_awaited_once()
        assert (
            workspace_svc.start_workspace.call_args.kwargs["persona_snapshots"][0]["persona_id"]
            == "persona-001"
        )

        repeated = await service.start_session(
            7,
            access_scope=DefenseSessionAccessScope(
                user_id="user-owner-001", team_id="team-revenue"
            ),
        )

        assert repeated.training_session_id == "training-defense-7"
        workspace_svc.start_workspace.assert_awaited_once()
        chatroom_svc.create_room.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_generate_report_prefers_bound_native_message_tree(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        session = DefenseSession(
            id=8,
            persona_ids=["persona-001"],
            scenario_type=ScenarioType.PERFORMANCE_REVIEW,
            document_summary=DocumentSummary(title="Q1", sections=[], key_data=[], raw_text="text"),
            room_id=41,
            training_session_id="training-defense-8",
            conversation_id=55,
            status="in_progress",
            owner_user_id="user-owner-001",
            owner_team_id="team-revenue",
        )
        uow.defense_session_repository.get_by_id.return_value = session
        workspace_svc = _workspace_service()
        workspace_svc.recent_turns.return_value = [
            TrainingTurn(speaker="assistant", text="What evidence supports this?"),
            TrainingTurn(speaker="user", text="The cohort retained 82%."),
        ]
        llm.generate_structured.return_value = {"overall_score": 4.0}
        service = DefensePrepService(
            uow_factory=lambda *args, **kwargs: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=workspace_svc,
        )

        report = await service.generate_report(
            8,
            access_scope=DefenseSessionAccessScope(
                user_id="user-owner-001", team_id="team-revenue"
            ),
        )

        assert report == {"overall_score": 4.0}
        workspace_svc.recent_turns.assert_awaited_once_with(
            defense_session_id=8,
            training_session_id="training-defense-8",
            conversation_id=55,
            owner_user_id="user-owner-001",
            owner_team_id="team-revenue",
        )
        report_prompt = llm.generate_structured.call_args.args[0][0].content
        assert "What evidence supports this?" in report_prompt
        assert "The cohort retained 82%." in report_prompt
        chatroom_svc.get_room_detail.assert_not_awaited()


def test_defense_session_scope_rejects_legacy_and_foreign_sessions():
    from domain.defense_prep.entity import DefenseSession
    from domain.defense_prep.value_objects import DocumentSummary
    from domain.defense_prep.repository import defense_session_matches_access_scope

    scope = DefenseSessionAccessScope(
        user_id="user-sales-001", team_id="team-revenue"
    )
    legacy = DefenseSession(
        id=1,
        persona_ids=["persona-001"],
        scenario_type=ScenarioType.PERFORMANCE_REVIEW,
        document_summary=DocumentSummary(title="legacy", sections=[], key_data=[], raw_text=""),
    )
    foreign = DefenseSession(
        id=2,
        persona_ids=["persona-001"],
        scenario_type=ScenarioType.PERFORMANCE_REVIEW,
        document_summary=DocumentSummary(title="foreign", sections=[], key_data=[], raw_text=""),
        owner_user_id="user-cs-001",
        owner_team_id="team-service",
    )
    own = DefenseSession(
        id=3,
        persona_ids=["persona-001"],
        scenario_type=ScenarioType.PERFORMANCE_REVIEW,
        document_summary=DocumentSummary(title="own", sections=[], key_data=[], raw_text=""),
        owner_user_id="user-sales-001",
        owner_team_id="team-revenue",
    )

    assert not defense_session_matches_access_scope(legacy, scope)
    assert not defense_session_matches_access_scope(foreign, scope)
    assert defense_session_matches_access_scope(own, scope)
    assert defense_session_matches_access_scope(
        legacy, DefenseSessionAccessScope(unrestricted=True)
    )


class TestInterleaveByDimension:
    def test_interleaves_questions_by_dimension(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        service = DefensePrepService(
            uow_factory=lambda: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=_workspace_service(),
        )
        questions = [
            PlannedQuestion(question="Q1", dimension="business", asked_by="p1"),
            PlannedQuestion(question="Q2", dimension="tech", asked_by="p1"),
            PlannedQuestion(question="Q3", dimension="business", asked_by="p2"),
            PlannedQuestion(question="Q4", dimension="tech", asked_by="p2"),
        ]
        result = service._interleave_by_dimension(questions)
        assert result[0].question == "Q1"
        assert result[1].question == "Q3"
        assert result[2].question == "Q2"
        assert result[3].question == "Q4"

    def test_handles_single_persona(self, mock_deps):
        uow, llm, parser, chatroom_svc, persona_loader = mock_deps
        service = DefensePrepService(
            uow_factory=lambda: uow,
            llm=llm,
            document_parser=parser,
            chatroom_service=chatroom_svc,
            persona_loader=persona_loader,
            training_workspace_service=_workspace_service(),
        )
        questions = [
            PlannedQuestion(question="Q1", dimension="a", asked_by="p1"),
            PlannedQuestion(question="Q2", dimension="b", asked_by="p1"),
        ]
        result = service._interleave_by_dimension(questions)
        assert len(result) == 2
