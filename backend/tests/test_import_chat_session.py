# input: scripts.import_chat_session parser/import helpers
# output: tests for visible Codex transcript parsing and room import
# owner: wanhua.gu
# pos: Tests - chat-session replay importer
"""Tests for importing a visible Codex transcript as a chat room."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork
from scripts.import_chat_session import (
    DEFAULT_PERSONA_ID,
    TranscriptTurn,
    format_turn_content,
    import_turns_to_room,
    parse_visible_transcript,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSCRIPT_PATH = PROJECT_ROOT / "chat-session" / "codex-visible-transcript.md"


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _uow_factory(session_factory):
    def factory(**kwargs):
        return SQLAlchemyUnitOfWork(session_factory=session_factory, **kwargs)

    return factory


def test_parse_real_visible_transcript_counts_visible_turns() -> None:
    turns = parse_visible_transcript(TRANSCRIPT_PATH.read_text(encoding="utf-8"))

    assert len(turns) == 35
    assert sum(1 for turn in turns if turn.speaker == "User") == 7
    assert sum(1 for turn in turns if turn.speaker == "Assistant") == 28
    assert turns[0].speaker == "User"
    assert "My request for Codex" in turns[0].content
    assert turns[-1].speaker == "Assistant"
    assert turns[-1].channel == "final_answer"


def test_format_turn_content_labels_assistant_channels() -> None:
    turns = parse_visible_transcript(TRANSCRIPT_PATH.read_text(encoding="utf-8"))
    commentary = next(turn for turn in turns if turn.channel == "commentary")
    final = next(turn for turn in turns if turn.channel == "final_answer")
    user = next(turn for turn in turns if turn.speaker == "User")

    assert format_turn_content(commentary).startswith("【过程更新】")
    assert format_turn_content(final).startswith("【最终回复】")
    assert format_turn_content(user) == user.content


@pytest.mark.asyncio
async def test_import_turns_creates_continueable_private_room(session_factory) -> None:
    turns = [
        TranscriptTurn(
            timestamp=parse_visible_transcript(TRANSCRIPT_PATH.read_text(encoding="utf-8"))[
                0
            ].timestamp,
            speaker="User",
            content="hello",
        ),
        TranscriptTurn(
            timestamp=parse_visible_transcript(TRANSCRIPT_PATH.read_text(encoding="utf-8"))[
                1
            ].timestamp,
            speaker="Assistant",
            channel="final_answer",
            content="hi",
        ),
    ]

    result = await import_turns_to_room(
        turns,
        uow_factory=_uow_factory(session_factory),
        room_name="Imported test room",
        context_summary="summary",
    )

    assert result.room_id is not None
    assert result.message_count == 2

    async with SQLAlchemyUnitOfWork(session_factory=session_factory, readonly=True) as uow:
        room = await uow.chat_room_repository.get_by_id(result.room_id)
        persona = await uow.stakeholder_persona_repository.get_by_id(DEFAULT_PERSONA_ID)
        messages = await uow.stakeholder_message_repository.list_by_room_id(result.room_id)

    assert room is not None
    assert room.type == "private"
    assert room.persona_ids == [DEFAULT_PERSONA_ID]
    assert room.context_summary == "summary"
    assert room.last_message_at == messages[-1].timestamp
    assert persona is not None
    assert persona.name == "Codex"
    assert [message.sender_type for message in messages] == ["user", "persona"]
    assert messages[1].content.startswith("【最终回复】")
