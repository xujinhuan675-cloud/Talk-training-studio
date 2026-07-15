from __future__ import annotations

import pytest

from application.services.stakeholder.battle_prep_service import BattlePrepService
from application.services.stakeholder.dto import ChatRoomDTO, CreateChatRoomDTO, StartBattleDTO
from application.services.stakeholder.persona_editor_service import PersonaEditorService
from application.services.stakeholder.persona_loader import PersonaLoader


class _StubChatRoomService:
    def __init__(self) -> None:
        self.created_rooms: list[CreateChatRoomDTO] = []

    async def create_room(self, dto: CreateChatRoomDTO) -> ChatRoomDTO:
        self.created_rooms.append(dto)
        return ChatRoomDTO(
            id=1,
            name=dto.name,
            type=dto.type,
            persona_ids=dto.persona_ids,
            scenario_id=dto.scenario_id,
        )


@pytest.mark.asyncio
async def test_start_battle_creates_missing_persona_dir(tmp_path) -> None:
    persona_dir = tmp_path / "missing" / "personas"
    loader = PersonaLoader(persona_dir=str(persona_dir))
    editor = PersonaEditorService(persona_dir=str(persona_dir), persona_loader=loader)
    chatroom_service = _StubChatRoomService()
    service = BattlePrepService(
        uow_factory=lambda: None,
        llm=None,  # start_battle does not call the LLM.
        chatroom_service=chatroom_service,
        persona_editor=editor,
        persona_loader=loader,
        persona_dir=str(persona_dir),
    )

    room = await service.start_battle(
        StartBattleDTO(
            persona_name="Alex",
            persona_role="VP Sales",
            persona_style="Direct and skeptical, but willing to engage with clear facts.",
            scenario_context="A budget review meeting for a new training program.",
            selected_training_points=["Handle budget objections"],
            difficulty="normal",
        )
    )

    persona_files = list(persona_dir.glob("bp-*.md"))
    assert persona_dir.is_dir()
    assert len(persona_files) == 1
    persona_text = persona_files[0].read_text(encoding="utf-8")
    assert room.type == "battle_prep"
    assert room.persona_ids == [persona_files[0].stem]
    assert chatroom_service.created_rooms[0].persona_ids == [persona_files[0].stem]
    assert persona_text.count("---") == 2
    assert "temporary: true" in persona_text
    assert "真实对手扮演守则" in persona_text
    assert "不是训练系统的讲解员" in persona_text
    assert "Handle budget objections" in persona_text

    loaded = loader.get_persona(persona_files[0].stem)
    assert loaded is not None
    assert "Handle budget objections" in loaded.profile_summary
    assert len(loaded.profile_summary) > 200
