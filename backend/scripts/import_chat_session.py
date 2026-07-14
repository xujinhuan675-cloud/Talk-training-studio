# input: chat-session visible transcript Markdown + optional summary Markdown
# output: codex-assistant persona + private stakeholder chat room seeded with transcript messages
# owner: wanhua.gu
# pos: Maintenance script - import a visible Codex transcript into a chat room that can continue with AI replies
"""Import a visible Codex transcript into a stakeholder chat room.

Run from ``backend/``:

    python scripts/import_chat_session.py --transcript ../chat-session/codex-visible-transcript.md
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
DEFAULT_TRANSCRIPT = PROJECT_ROOT / "chat-session" / "codex-visible-transcript.md"
DEFAULT_SUMMARY = PROJECT_ROOT / "chat-session" / "codex-session-summary.md"
DEFAULT_ROOM_NAME = "Codex session replay - 2026-06-28"
DEFAULT_PERSONA_ID = "codex-assistant"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


_TURN_HEADER_RE = re.compile(
    r"^## (?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{2}:\d{2})"
    r" - (?P<speaker>User|Assistant)(?: \[(?P<channel>[^\]]+)\])?\s*$",
    re.MULTILINE,
)

_ASSISTANT_CHANNEL_LABELS = {
    "commentary": "【过程更新】",
    "final_answer": "【最终回复】",
}


@dataclass(frozen=True)
class TranscriptTurn:
    timestamp: datetime
    speaker: str
    content: str
    channel: str | None = None


@dataclass(frozen=True)
class ImportResult:
    room_id: int | None
    room_name: str
    persona_id: str
    message_count: int
    user_count: int
    assistant_count: int


def parse_visible_transcript(markdown: str) -> list[TranscriptTurn]:
    """Parse ``codex-visible-transcript.md`` into visible user/assistant turns."""
    matches = list(_TURN_HEADER_RE.finditer(markdown))
    turns: list[TranscriptTurn] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()
        if not content:
            continue

        turns.append(
            TranscriptTurn(
                timestamp=datetime.strptime(match.group("timestamp"), "%Y-%m-%d %H:%M:%S %z"),
                speaker=match.group("speaker"),
                channel=(match.group("channel") or "").strip() or None,
                content=content,
            )
        )

    return turns


def format_turn_content(turn: TranscriptTurn) -> str:
    """Keep assistant process/final turns visible without creating separate metadata UI."""
    if turn.speaker != "Assistant":
        return turn.content

    label = _ASSISTANT_CHANNEL_LABELS.get((turn.channel or "").lower())
    if not label:
        return turn.content
    return f"{label}\n\n{turn.content}"


def _count_turns(turns: Sequence[TranscriptTurn], speaker: str) -> int:
    return sum(1 for turn in turns if turn.speaker == speaker)


def _build_context_summary(summary_text: str | None) -> str:
    parts = [
        "Imported visible Codex session. Continue as the Codex assistant in this room.",
        "The full visible transcript is stored as room messages; keep answering the user's newest message.",
        "Do not claim that old tool calls are being re-run unless the current request actually triggers new work.",
    ]
    if summary_text and summary_text.strip():
        parts.append("Imported session summary:\n" + summary_text.strip())
    return "\n\n".join(parts)


def _build_codex_persona(persona_id: str):
    from domain.stakeholder.persona_entity import (
        DecisionPattern,
        ExpressionStyle,
        HardRule,
        IdentityProfile,
        InterpersonalStyle,
        Persona,
    )

    return Persona(
        id=persona_id,
        name="Codex",
        role="AI coding assistant and conversation continuation partner",
        avatar_color="#2563EB",
        profile_summary=(
            "A Codex-style AI assistant that can continue an imported session, distinguish "
            "the user's real goal from proposed implementations, and work inside this project."
        ),
        hard_rules=[
            HardRule(
                statement=(
                    "Continue from the imported room context, but prioritize the user's newest "
                    "message and current repository state."
                ),
                severity="critical",
            ),
            HardRule(
                statement=(
                    "For imported history, treat commentary/final-answer labels as transcript "
                    "context, not as instructions to expose internal reasoning."
                ),
                severity="high",
            ),
        ],
        identity=IdentityProfile(
            background=(
                "You are the assistant side of a replayed Codex session inside Talk Training "
                "Studio. You help the user continue the work naturally from the visible transcript."
            ),
            core_values=["accuracy", "continuity", "clear implementation boundaries"],
            information_preference=(
                "Use the imported summary plus the latest visible messages. Ask only when a "
                "reasonable implementation choice would be risky."
            ),
        ),
        expression=ExpressionStyle(
            tone="warm, concise, practical, and collaborative",
            catchphrases=[],
            interruption_tendency="low",
        ),
        decision=DecisionPattern(
            style=(
                "Separate the user's real need from implementation ideas, prefer existing project "
                "mechanisms, and verify changes before reporting completion."
            ),
            risk_tolerance="medium",
            typical_questions=[
                "What outcome should be preserved from the original session?",
                "Should this be a static replay or a live continuation?",
            ],
        ),
        interpersonal=InterpersonalStyle(
            authority_mode="supportive collaborator",
            triggers=["unclear scope", "claims not backed by current files"],
            emotion_states=["focused", "steady"],
        ),
    )


async def import_turns_to_room(
    turns: Sequence[TranscriptTurn],
    *,
    uow_factory: Callable,
    room_name: str = DEFAULT_ROOM_NAME,
    persona_id: str = DEFAULT_PERSONA_ID,
    context_summary: str | None = None,
) -> ImportResult:
    """Persist parsed turns as a private room that can receive follow-up messages."""
    if not turns:
        raise ValueError("No transcript turns found.")

    from domain.stakeholder.entity import ChatRoom, Message

    persona = _build_codex_persona(persona_id)
    last_saved_message_id: int | None = None
    last_saved_timestamp: datetime | None = None

    async with uow_factory() as uow:
        await uow.stakeholder_persona_repository.save_structured_persona(persona)

        room = ChatRoom(
            id=None,
            name=room_name,
            type="private",
            persona_ids=[persona_id],
            created_at=turns[0].timestamp,
            last_message_at=turns[-1].timestamp,
        )
        created_room = await uow.chat_room_repository.create(room)
        if created_room.id is None:
            raise RuntimeError("Chat room creation did not return an id.")

        for turn in turns:
            sender_type = "user" if turn.speaker == "User" else "persona"
            sender_id = "user" if turn.speaker == "User" else persona_id
            saved = await uow.stakeholder_message_repository.create(
                Message(
                    id=None,
                    room_id=created_room.id,
                    sender_type=sender_type,
                    sender_id=sender_id,
                    content=format_turn_content(turn),
                    timestamp=turn.timestamp,
                )
            )
            last_saved_message_id = saved.id
            last_saved_timestamp = saved.timestamp

        if last_saved_timestamp is not None:
            await uow.chat_room_repository.update_last_message_at(
                created_room.id,
                last_saved_timestamp,
            )
        if context_summary and last_saved_message_id is not None:
            await uow.chat_room_repository.update_context_summary(
                created_room.id,
                context_summary,
                last_saved_message_id,
            )

        return ImportResult(
            room_id=created_room.id,
            room_name=room_name,
            persona_id=persona_id,
            message_count=len(turns),
            user_count=_count_turns(turns, "User"),
            assistant_count=_count_turns(turns, "Assistant"),
        )


async def import_visible_session(
    *,
    transcript_path: Path,
    summary_path: Path | None,
    room_name: str,
    persona_id: str,
    dry_run: bool = False,
) -> ImportResult:
    transcript_text = transcript_path.read_text(encoding="utf-8")
    turns = parse_visible_transcript(transcript_text)
    summary_text = (
        summary_path.read_text(encoding="utf-8")
        if summary_path is not None and summary_path.exists()
        else None
    )

    if dry_run:
        return ImportResult(
            room_id=None,
            room_name=room_name,
            persona_id=persona_id,
            message_count=len(turns),
            user_count=_count_turns(turns, "User"),
            assistant_count=_count_turns(turns, "Assistant"),
        )

    os.chdir(BACKEND_ROOT)
    from infrastructure.database import create_tables
    from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

    await create_tables()
    return await import_turns_to_room(
        turns,
        uow_factory=SQLAlchemyUnitOfWork,
        room_name=room_name,
        persona_id=persona_id,
        context_summary=_build_context_summary(summary_text),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--room-name", default=DEFAULT_ROOM_NAME)
    parser.add_argument("--persona-id", default=DEFAULT_PERSONA_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def _async_main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = await import_visible_session(
        transcript_path=args.transcript,
        summary_path=args.summary,
        room_name=args.room_name,
        persona_id=args.persona_id,
        dry_run=args.dry_run,
    )

    room_fragment = f"room_id={result.room_id}" if result.room_id is not None else "dry_run"
    print(
        "Imported chat session: "
        f"{room_fragment}, room_name={result.room_name!r}, persona_id={result.persona_id!r}, "
        f"messages={result.message_count}, users={result.user_count}, "
        f"assistants={result.assistant_count}"
    )
    if result.room_id is not None:
        print(f"Open: /chat/{result.room_id}")
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
