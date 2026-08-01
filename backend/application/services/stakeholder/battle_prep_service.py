# input: AbstractUnitOfWork, LLMPort, ChatRoomApplicationService, PersonaEditorService, PersonaLoader
# output: BattlePrepService 备战模式编排服务
# owner: wanhua.gu
# pos: 应用层服务 - 紧急备战模式（角色生成、对话启动、话术纸条）；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Battle Prep service: pre-meeting quick simulation workflow."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Callable, Mapping

from application.ports.llm import LLMMessage, LLMPort
from application.services.stakeholder.dto import (
    BattlePrepResultDTO,
    CheatSheetDTO,
    ChatRoomDTO,
    CreateChatRoomDTO,
    StartBattleDTO,
    TacticItem,
)
from application.services.stakeholder.chatroom_service import ChatRoomApplicationService
from application.services.stakeholder.persona_loader import PersonaLoader
from application.services.stakeholder.room_access_policy import (
    StakeholderRoomAccessScope,
    require_stakeholder_room_access_scope,
)
from application.services.training_studio.catalog_service import TrainingTaskConfigDTO
from application.services.training_studio.session_service import (
    CreateTrainingSessionDTO,
    TrainingSessionService,
)
from application.services.training_studio.training_core import (
    ConversationRef,
    StartedTrainingSession,
    TrainingConversationAdapter,
    TrainingCoreOrchestrator,
)
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.persona_entity import Persona
from domain.training_studio.session_repository import TrainingSessionAccessScope

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BattleTrainingLaunch:
    """The stable hand-off from a battle launch to the text conversation runtime."""

    room: ChatRoomDTO
    started: StartedTrainingSession
    persona_snapshot: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        conversation = self.started.conversation
        session = self.started.session
        conversation_payload = _conversation_ref_payload(conversation)
        return {
            "training_session": {
                "session_id": session.session_id,
                "mode": session.mode.value,
                "status": session.status.value,
                "room_id": session.room_id,
                "conversation": conversation_payload,
            },
            "training_session_id": session.session_id,
            "conversation_id": conversation.conversation_id,
            "room_id": self.room.id,
            "persona_snapshot": dict(self.persona_snapshot),
            "conversation": conversation_payload,
            "room": self.room.model_dump(mode="json"),
        }


class _BattleConversationMetadataAdapter:
    """Attach the concrete conversation id to the session metadata without changing TrainingCore."""

    def __init__(self, delegate: TrainingConversationAdapter) -> None:
        self._delegate = delegate

    async def create_conversation(self, session) -> ConversationRef:
        conversation = await self._delegate.create_conversation(session)
        return ConversationRef(
            provider=conversation.provider,
            conversation_id=conversation.conversation_id,
            branch_tail_message_id=conversation.branch_tail_message_id,
            legacy_room_id=conversation.legacy_room_id,
            metadata={
                **dict(conversation.metadata),
                "conversationId": conversation.conversation_id,
            },
        )

    async def append_turn(self, conversation: ConversationRef, turn):
        return await self._delegate.append_turn(conversation, turn)

    async def recent_turns(self, conversation: ConversationRef, *, limit: int):
        return await self._delegate.recent_turns(conversation, limit=limit)


def _conversation_ref_payload(conversation: ConversationRef) -> dict[str, object]:
    return {
        "provider": conversation.provider,
        "conversationId": conversation.conversation_id,
        "branchTailMessageId": conversation.branch_tail_message_id,
        "legacyRoomId": conversation.legacy_room_id,
        "metadata": dict(conversation.metadata),
    }


def _battle_training_session_payload(
    *,
    room: ChatRoomDTO,
    persona: Persona,
    persona_snapshot: Mapping[str, object],
    user_id: str | None,
    team_id: str | None,
    scenario_context: str,
    training_points: list[str],
    difficulty: str,
    source: str,
) -> CreateTrainingSessionDTO:
    normalized_points = [str(point).strip() for point in training_points if str(point).strip()]
    normalized_context = str(scenario_context or "").strip()
    if not normalized_context:
        normalized_context = f"Practice a realistic conversation with {persona.name}."
    normalized_difficulty = {
        "easy": "easy",
        "hard": "hard",
    }.get(str(difficulty).strip().lower(), "medium")
    system_prompt = (persona.user_context or persona.profile_summary or normalized_context).strip()
    metadata: dict[str, object] = {
        "runtime": "conversation_message_tree",
        "training_source": source,
        "persona_ids": [persona.id],
        "persona_snapshot": dict(persona_snapshot),
        "scenario_context": normalized_context,
        "training_points": normalized_points,
        "legacy_room_id": room.id,
        "room_name": room.name,
        "room_type": room.type,
        "conversation_title": room.name,
        "system_prompt": system_prompt,
    }
    return CreateTrainingSessionDTO(
        task_config=TrainingTaskConfigDTO(
            role=f"Conversation with {persona.role}",
            level="practice",
            tech_stack=["communication"],
            question_type_ratios={"simulation": 1.0},
            question_count=12,
            framework="prep",
            difficulty=normalized_difficulty,
            category="negotiation",
            metadata=metadata,
        ),
        mode="text",
        user_id=(user_id or "").strip() or None,
        team_id=(team_id or "").strip() or None,
    )


def _owned_battle_room_scope(
    access_scope: StakeholderRoomAccessScope,
    *,
    operation: str,
) -> StakeholderRoomAccessScope:
    """Keep admin read authority from producing an ownerless battle resource."""

    scope = require_stakeholder_room_access_scope(access_scope, operation=operation)
    return StakeholderRoomAccessScope(
        user_id=scope.user_id,
        team_id=scope.team_id,
        include_team_scope=scope.include_team_scope,
        allowed_persona_ids=scope.allowed_persona_ids,
        allowed_team_ids=scope.allowed_team_ids,
        allowed_organization_ids=scope.allowed_organization_ids,
        unrestricted=False,
    )

_GENERATE_PROMPT = """\
你是一个职场沟通模拟助手。用户即将参加一个重要会议，请根据用户的描述，生成模拟对话所需的角色和场景。

## 用户描述

{description}

## 规则
- persona_style 要具体，不要泛泛描述，要像真人一样有个性
- training_points 必须 2-3 个，每个是一个具体的沟通挑战（如"如何应对对方用预算紧张来拒绝"）
- scenario_context 要包含冲突焦点
"""

_GENERATE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "persona_name": {
            "type": "string",
            "description": "对方的称呼（如：张总、李经理）",
        },
        "persona_role": {
            "type": "string",
            "description": "对方的职位（如：技术副总裁）",
        },
        "persona_style": {
            "type": "string",
            "description": "对方的沟通风格描述（100-200字，包含性格特点、决策偏好、常见反应模式）",
        },
        "scenario_context": {
            "type": "string",
            "description": "对话场景背景（100-200字，包含会议目的、核心矛盾点、双方立场）",
        },
        "training_points": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-3个训练重点，每个是具体的沟通挑战",
        },
    },
    "required": [
        "persona_name",
        "persona_role",
        "persona_style",
        "scenario_context",
        "training_points",
    ],
}

_CHEAT_SHEET_PROMPT = """\
你是一个职场沟通教练。用户刚完成了一场模拟对话练习，请根据对话记录生成一份简洁实用的"话术纸条"，用户可以带进真实会议。

## 对话场景

{scenario_context}

## 训练重点

{training_points}

## 对话记录

{conversation}

## 规则
- opening 必须是直接能说出口的话，不是抽象建议
- key_tactics 针对每个训练重点至少 1 条，每条 response 是直接可用的话术
- pitfalls 从对话中用户的实际失误提炼，2-4 条
- bottom_line 要具体可操作
"""

_CHEAT_SHEET_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "opening": {
            "type": "string",
            "description": "建议的开场白（1-2句话，直接可用）",
        },
        "key_tactics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "situation": {"type": "string", "description": "对方可能说/做的事"},
                    "response": {
                        "type": "string",
                        "description": "你应该这样回应（直接可用的话术）",
                    },
                },
                "required": ["situation", "response"],
            },
            "description": "关键话术列表",
        },
        "pitfalls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "避免说的话或做的事（2-4条）",
        },
        "bottom_line": {
            "type": "string",
            "description": "如果主要目标达不成，退而求其次的策略",
        },
    },
    "required": ["opening", "key_tactics", "pitfalls", "bottom_line"],
}

_DIFFICULTY_PROMPTS = {
    "easy": "你态度相对友好，愿意倾听，但会提出合理的质疑。",
    "normal": "你按照画像正常沟通，会质疑不充分的论点，但不会刻意刁难。",
    "hard": "你非常强势，会频繁打断、质疑数据来源、用情绪施压。",
}

_REPLY_LANGUAGE_LABELS = {
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "en-US": "English",
    "ja": "日本語",
    "ko": "한국어",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
}


def _reply_language_instruction(reply_language: str) -> str:
    code = (reply_language or "zh-CN").strip() or "zh-CN"
    label = _REPLY_LANGUAGE_LABELS.get(code, code)
    return (
        "## 回复语言\n\n"
        f"- 你的所有对手回复必须使用 {label}（{code}）。\n"
        "- 除非用户明确要求切换语言，否则不要混用其他语言。\n"
    )


_REALISTIC_COUNTERPART_RULES = """\
## 真实对手扮演守则（最高优先级）

- 你不是训练系统的讲解员，也不是来配合用户演示的。你是一个有自身利益、戒备心和决策门槛的真实对话对象。
- 只输出你这一轮会说的话，不要写“客户：”“对方：”等前缀，不要解释评分规则，不要给用户建议，不要使用 markdown 列点。
- 用第一人称、口语化短句回应。单轮通常 30-120 个中文字符；可以偶尔加入简短动作或情绪括号，例如“（皱眉）”“（停顿一下）”，但不要写成剧本。
- 不要一次性暴露所有需求、预算、顾虑和底线。按对话节奏零星透露，用户问得好才多给信息。
- 保留防御心：用户说得空泛、强推、夸大、回避问题或急于成交时，你要追问依据、反问、压价、转移话题或表达不满。
- 用户做得好时可以逐步松动，表现为语气变软、愿意多问细节、愿意考虑下一步；不要轻易直接成交或完全认同。
- 用户做得差时要按画像正面拒绝、提高门槛、结束话题，或把压力转回给用户。
- 你要推动用户暴露真实沟通能力，而不是替用户总结价值、替用户推进成交、替用户完成训练目标。
"""


class BattlePrepService:
    """Orchestrates the battle prep workflow: generate -> start -> cheat sheet."""

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        llm: LLMPort,
        chatroom_service: ChatRoomApplicationService,
        persona_editor,
        persona_loader: PersonaLoader,
        persona_dir: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._llm = llm
        self._chatroom_service = chatroom_service
        self._persona_editor = persona_editor  # Compatibility injection; battle assets use the DB.
        self._persona_loader = persona_loader
        self._persona_dir = persona_dir

    async def generate_prep(self, description: str) -> BattlePrepResultDTO:
        """Step 1->2: User description -> LLM generates persona + scenario + training points."""
        prompt = _GENERATE_PROMPT.format(description=description)
        messages = [LLMMessage(role="user", content=prompt)]
        try:
            parsed = await self._llm.generate_structured(
                messages,
                schema=_GENERATE_SCHEMA,
                schema_name="generate_battle_prep",
                schema_description="生成模拟对话所需的角色和场景",
                temperature=0.4,
            )
        except Exception as exc:
            logger.error("LLM call failed for battle prep: %s", exc)
            raise ValueError("AI 服务暂时不可用，请稍后重试") from exc

        points = parsed.get("training_points", [])
        if len(points) < 2:
            defaults = ["如何有效开场", "如何应对对方质疑"]
            points = points + defaults[: 2 - len(points)]

        return BattlePrepResultDTO(
            persona_name=parsed.get("persona_name", "对方"),
            persona_role=parsed.get("persona_role", "管理者"),
            persona_style=parsed.get("persona_style", ""),
            scenario_context=parsed.get("scenario_context", ""),
            training_points=points[:5],
        )

    async def start_battle(
        self,
        dto: StartBattleDTO,
        *,
        access_scope: StakeholderRoomAccessScope,
    ) -> ChatRoomDTO:
        """Create the owned compatibility room used by legacy battle callers."""
        room, _ = await self._create_generated_battle_room(
            dto,
            access_scope=access_scope,
        )
        return room

    async def launch_battle_training(
        self,
        dto: StartBattleDTO,
        *,
        access_scope: StakeholderRoomAccessScope,
        training_session_service: TrainingSessionService,
        conversation_adapter: TrainingConversationAdapter,
    ) -> BattleTrainingLaunch:
        """Start Battle in the message-tree runtime, retaining the scoped room as context."""
        room, persona = await self._create_generated_battle_room(
            dto,
            access_scope=access_scope,
        )
        return await self._launch_persona_training(
            room=room,
            persona=persona,
            access_scope=access_scope,
            training_session_service=training_session_service,
            conversation_adapter=conversation_adapter,
            scenario_context=dto.scenario_context,
            training_points=dto.selected_training_points,
            difficulty=dto.difficulty,
            source="battle_prep",
        )

    async def _create_generated_battle_room(
        self,
        dto: StartBattleDTO,
        *,
        access_scope: StakeholderRoomAccessScope,
    ) -> tuple[ChatRoomDTO, Persona]:
        """Persist a generated Persona asset, then create its owned compatibility room."""
        scope = _owned_battle_room_scope(
            access_scope,
            operation="start_battle",
        )

        persona_id = f"bp-{uuid.uuid4().hex[:8]}"
        difficulty_instruction = _DIFFICULTY_PROMPTS.get(
            dto.difficulty, _DIFFICULTY_PROMPTS["normal"]
        )

        persona_content = (
            f"# {dto.persona_name}\n\n"
            f"**职位**: {dto.persona_role}\n\n"
            f"## 沟通风格\n\n{dto.persona_style}\n\n"
            f"## 对话场景\n\n{dto.scenario_context}\n\n"
            f"## 难度指令\n\n{difficulty_instruction}\n\n"
            f"{_reply_language_instruction(dto.reply_language)}\n"
            f"## 训练重点\n\n"
            f"用户选择了以下训练重点，请在对话中重点围绕这些方面施压和互动：\n"
        )
        for point in dto.selected_training_points:
            persona_content += f"- {point}\n"

        persona_content += f"\n{_REALISTIC_COUNTERPART_RULES}\n"

        persona_content += (
            "\n## 备战模式特殊指令\n\n"
            "这是一场限时备战练习（最多12轮）。"
            "当你认为所有训练重点都已经充分讨论过（通常在第6轮之后），"
            "你可以自然地结束对话（如'我觉得这个方案基本可以，我们就这么定了'）。"
            "但如果用户还有明显未覆盖的训练重点，继续施压。"
        )

        persona = Persona(
            id=persona_id,
            name=dto.persona_name,
            role=dto.persona_role,
            profile_summary=persona_content,
            user_context=persona_content,
            owner_user_id=scope.user_id,
            owner_team_id=scope.team_id,
            visibility="private",
            version=1,
        )
        async with self._uow_factory() as uow:
            persona = await uow.stakeholder_persona_repository.save_structured_persona(persona)
            await uow.commit()

        # This service and the room creator share a request-scoped loader. Make
        # the just-persisted persona available before the next request refresh.
        self._persona_loader._v2_by_id[persona.id] = persona
        self._persona_loader.reload()

        room = await self._chatroom_service.create_room(
            CreateChatRoomDTO(
                name=f"备战: {dto.persona_name}",
                type="battle_prep",
                persona_ids=[persona_id],
            ),
            access_scope=scope,
        )

        return room, persona

    async def create_room_from_persona(
        self,
        persona_id: str,
        *,
        access_scope: StakeholderRoomAccessScope,
    ) -> ChatRoomDTO:
        """Story 2.8 (AC1): create a private chatroom using an existing persona.

        Unlike start_battle (which creates a brand new temp bp-* persona), this
        reuses an already-persisted persona (v1 markdown or v2 DB). Called from
        the Persona Editor page's "开始演练" button.
        """
        room, _ = await self._create_room_from_persona(
            persona_id,
            access_scope=access_scope,
        )
        return room

    async def launch_persona_training(
        self,
        persona_id: str,
        *,
        access_scope: StakeholderRoomAccessScope,
        training_session_service: TrainingSessionService,
        conversation_adapter: TrainingConversationAdapter,
    ) -> BattleTrainingLaunch:
        """Turn an owned Persona Builder asset into a scoped message-tree training session."""
        room, persona = await self._create_room_from_persona(
            persona_id,
            access_scope=access_scope,
        )
        return await self._launch_persona_training(
            room=room,
            persona=persona,
            access_scope=access_scope,
            training_session_service=training_session_service,
            conversation_adapter=conversation_adapter,
            scenario_context=persona.profile_summary or persona.user_context,
            training_points=[],
            difficulty="normal",
            source="persona_builder",
        )

    async def _create_room_from_persona(
        self,
        persona_id: str,
        *,
        access_scope: StakeholderRoomAccessScope,
    ) -> tuple[ChatRoomDTO, Persona]:
        scope = _owned_battle_room_scope(
            access_scope,
            operation="start_persona_training",
        )
        persona = self._persona_loader.get_persona(persona_id)
        if persona is None:
            raise ValueError(f"Persona {persona_id} not found")
        room = await self._chatroom_service.create_room(
            CreateChatRoomDTO(
                name=f"演练: {persona.name}",
                type="private",
                persona_ids=[persona_id],
            ),
            access_scope=scope,
        )
        return room, persona

    async def _launch_persona_training(
        self,
        *,
        room: ChatRoomDTO,
        persona: Persona,
        access_scope: StakeholderRoomAccessScope,
        training_session_service: TrainingSessionService,
        conversation_adapter: TrainingConversationAdapter,
        scenario_context: str,
        training_points: list[str],
        difficulty: str,
        source: str,
    ) -> BattleTrainingLaunch:
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="launch_battle_training",
        )
        snapshot = persona.training_snapshot()
        session_scope = TrainingSessionAccessScope(
            user_id=scope.user_id,
            team_id=scope.team_id,
            include_team_scope=False,
        )
        payload = _battle_training_session_payload(
            room=room,
            persona=persona,
            persona_snapshot=snapshot,
            user_id=scope.user_id,
            team_id=scope.team_id,
            scenario_context=scenario_context,
            training_points=training_points,
            difficulty=difficulty,
            source=source,
        )
        session = await training_session_service.create_session(payload)
        orchestrator = TrainingCoreOrchestrator(
            session_service=training_session_service,
            conversation_adapter=_BattleConversationMetadataAdapter(conversation_adapter),
        )
        try:
            started = await orchestrator.start_existing_session(
                session.session_id,
                access_scope=session_scope,
            )
        except Exception:
            try:
                await training_session_service.fail_session(
                    session.session_id,
                    "Unable to initialize the battle conversation runtime",
                    access_scope=session_scope,
                )
            except Exception:
                logger.exception(
                    "battle_training_session_failure_cleanup_failed",
                    extra={"training_session_id": session.session_id},
                )
            raise
        return BattleTrainingLaunch(
            room=room,
            started=started,
            persona_snapshot=snapshot,
        )

    async def generate_cheat_sheet(
        self,
        room_id: int,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> CheatSheetDTO:
        """Post-conversation: generate cheat sheet from conversation history."""
        detail = await self._chatroom_service.get_room_detail(
            room_id,
            message_limit=200,
            access_scope=access_scope,
        )
        room = detail.room
        messages = detail.messages

        if not messages:
            raise ValueError("对话记录为空，无法生成话术纸条")

        lines: list[str] = []
        for msg in messages:
            if msg.sender_type == "system":
                continue
            if msg.sender_type == "user":
                lines.append(f"[用户]: {msg.content}")
            else:
                p = self._persona_loader.get_persona(msg.sender_id)
                name = p.name if p else msg.sender_id
                lines.append(f"[{name}]: {msg.content}")

        conversation_text = "\n\n".join(lines)

        persona_id = room.persona_ids[0] if room.persona_ids else ""
        persona = self._persona_loader.get_persona(persona_id)
        scenario_context = ""
        training_points = ""
        if persona:
            scenario_context = f"与 {persona.name}（{persona.role}）的备战对话"

        prompt = _CHEAT_SHEET_PROMPT.format(
            scenario_context=scenario_context,
            training_points=training_points or "（未指定）",
            conversation=conversation_text,
        )

        llm_messages = [LLMMessage(role="user", content=prompt)]
        try:
            parsed = await self._llm.generate_structured(
                llm_messages,
                schema=_CHEAT_SHEET_SCHEMA,
                schema_name="generate_cheat_sheet",
                schema_description="生成话术纸条",
                temperature=0.3,
            )
        except Exception as exc:
            logger.error("LLM call failed for cheat sheet: %s", exc)
            raise ValueError("话术纸条生成失败，请重试") from exc

        tactics = []
        for t in parsed.get("key_tactics", []):
            if isinstance(t, dict):
                tactics.append(
                    TacticItem(
                        situation=t.get("situation", ""),
                        response=t.get("response", ""),
                    )
                )

        return CheatSheetDTO(
            opening=parsed.get("opening", ""),
            key_tactics=tactics,
            pitfalls=parsed.get("pitfalls", []),
            bottom_line=parsed.get("bottom_line", ""),
        )
