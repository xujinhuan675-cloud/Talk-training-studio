# input: AbstractUnitOfWork, LLMPort, PersonaLoader
# output: communication-core-v1 证据评估 + 身份范围内 Dashboard 聚合 + 成长洞察服务 + 沟通力画像生成
# owner: wanhua.gu
# pos: 应用层服务 - 先证据后评级的 AI 沟通评估、Dashboard 数据聚合、跨 session 成长洞察；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Growth tracking service: competency evaluation, dashboard, and insights."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from statistics import median
from typing import Callable, Optional

from application.ports.llm import LLMMessage, LLMPort
from application.services.stakeholder.dto import (
    CompetencyEvaluationDTO,
    DimensionScoreDTO,
    DimensionTrendPointDTO,
    GrowthDashboardDTO,
    GrowthInsightDTO,
    GrowthOverviewDTO,
    OutcomeScoreDTO,
)
from application.services.stakeholder.room_access_policy import (
    StakeholderRoomAccessScope,
    require_stakeholder_room_access_scope,
    stakeholder_room_matches_access_scope,
)
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.competency_entity import (
    COMMUNICATION_JUDGE_VERSION,
    COMMUNICATION_RUBRIC_VERSION,
    COMPETENCY_DIMENSIONS,
    CompetencyEvaluation,
)
from domain.stakeholder.entity import ChatRoom

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM-as-Judge Rubric Prompt
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
你是基于对话行为证据的沟通评估员。你要先识别观察机会和可定位证据，再按固定锚点评级；不能凭整体印象补分。

## 参与角色

{persona_profiles}

## 对话记录

{conversation}

## 任务与观察上下文

{evaluation_context}

## 四项通用能力

- attentiveness（倾听关注）：识别、澄清并回应对方的观点与关切。
- expression（表达清晰）：清楚、具体、有结构地表达内容。
- coordination（互动协调）：管理话题、轮次、节奏并推动合理下一步。
- composure（沉着应对）：在压力、异议或冲突下保持稳定、尊重且建设性。

## 固定行为锚点

- 1：明显无效或造成负面影响。
- 2：表现不足，关键行为缺失或效果弱。
- 3：基本胜任，完成必要行为但不稳定或不充分。
- 4：在本次观察中稳定有效，有清晰正向证据。
- 5：在明确挑战条件下持续优秀，至少有两条独立正向证据。
- N/A：没有观察机会，或没有足够证据作出推断。

effectiveness 表示本次是否推动了沟通目标；appropriateness 表示方式是否符合角色、关系与情境。两项也必须返回可定位的用户消息证据；证据不足时 rating=null。

## 评分规则
- 先判断 opportunity_present，再判断 rating。
- evidence 只能引用上面标记为 [用户消息 id=...]的消息，message_id 必须原样返回，quote 必须是其中连续的原文片段。
- 有观察机会但用户回避、敷衍或未做出应有行为，可以评 1-2，并引用该回应作负向证据。
- 没有观察机会或证据不足时，opportunity_present=false 或 rating=null；绝对不能默认给 3。
- effectiveness 和 appropriateness 与四项能力分别判断，不能从能力分机械推导，也不能脱离各自证据直接给分。
- rating 必须是 1-5 整数或 null，suggestion 必须具体可操作。
"""

_EVIDENCE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "message_id": {"type": "string", "description": "被引用的用户消息ID"},
        "quote": {"type": "string", "description": "该消息中连续的原文片段"},
    },
    "required": ["message_id", "quote"],
}

_DIM_SCORE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "opportunity_present": {"type": "boolean"},
        "rating": {"type": ["integer", "null"], "description": "1-5 整数或 null"},
        "evidence": {"type": "array", "items": _EVIDENCE_SCHEMA},
        "reason": {"type": "string"},
        "suggestion": {"type": "string"},
    },
    "required": [
        "opportunity_present",
        "rating",
        "evidence",
        "reason",
        "suggestion",
    ],
}

_OUTCOME_SCORE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "rating": {"type": ["integer", "null"], "description": "1-5 整数或 null"},
        "evidence": {"type": "array", "items": _EVIDENCE_SCHEMA},
        "reason": {"type": "string"},
    },
    "required": ["rating", "evidence", "reason"],
}

_JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "effectiveness": _OUTCOME_SCORE_SCHEMA,
        "appropriateness": _OUTCOME_SCORE_SCHEMA,
        "competencies": {
            "type": "object",
            "properties": {dim: _DIM_SCORE_SCHEMA for dim in COMPETENCY_DIMENSIONS},
            "required": list(COMPETENCY_DIMENSIONS),
        },
    },
    "required": ["effectiveness", "appropriateness", "competencies"],
}

_INSIGHT_SYSTEM_PROMPT = """\
你是一位资深的沟通教练。请根据用户在多次利益相关者模拟对话中的能力评估数据，\
生成一份简洁的成长洞察分析（200-400 字）。

## 评估数据

{evaluation_data}

## 要求

1. 识别用户最强和最弱的维度
2. 发现跨 session 的趋势（进步、退步、停滞）
3. 识别反复出现的模式（如"一被质疑就防守性回答"）
4. 给出 1-2 条最重要的下次练习建议
5. 必须引用具体分数变化，不允许编造数据
6. 语气鼓励但直接，不要空洞的表扬

直接输出分析文本，不要输出 JSON 或 Markdown 标题。
"""

_PROFILE_CARD_PROMPT = """\
你是一个职场沟通分析师。请根据用户的多次沟通能力评估数据，生成一句证据导向的成长摘要。

## 评估数据

{evaluation_data}

## 规则
- summary 语气正向但诚实，不要空洞表扬
- 只描述有评分和证据支持的行为，不推断性格、人格或固定风格
- 必须基于具体分数，不允许编造数据
"""

_PROFILE_CARD_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "一句话点评（20-40字）",
        },
    },
    "required": ["summary"],
}


# ---------------------------------------------------------------------------
# Helpers (reuse patterns from analysis_service)
# ---------------------------------------------------------------------------


def _build_conversation_text(history: list[dict], persona_loader) -> str:
    lines: list[str] = []
    for msg in history:
        sender_type = msg["sender_type"]
        if sender_type == "system":
            continue
        sender_id = msg["sender_id"]
        content = msg["content"]
        emotion = ""
        if msg.get("emotion_score") is not None:
            emotion = f" [情绪: {msg.get('emotion_label', '未知')}({msg['emotion_score']})]"
        if sender_type == "user":
            lines.append(f"[用户消息 id={msg.get('message_id')}]{emotion}: {content}")
        elif sender_type == "persona":
            p = persona_loader.get_persona(sender_id) if persona_loader else None
            name = p.name if p else sender_id
            lines.append(f"[角色消息 id={msg.get('message_id')} {name}]{emotion}: {content}")
    return "\n\n".join(lines)


def _build_persona_profiles(persona_ids: list[str], persona_loader) -> str:
    profiles: list[str] = []
    for pid in persona_ids:
        p = persona_loader.get_persona(pid)
        if p:
            profiles.append(f"- **{p.name}** ({pid}): {p.role}")
    return "\n".join(profiles) if profiles else "（无角色信息）"


def _evaluation_message_id(message: object) -> str:
    metadata = getattr(message, "metadata", None)
    metadata = metadata if isinstance(metadata, Mapping) else {}
    return str(metadata.get("sourceMessageId") or getattr(message, "id", ""))


def _bounded_evaluation_messages(
    messages: list[object],
    evaluation_context: Mapping[str, object] | None,
) -> list[object]:
    context_messages = (evaluation_context or {}).get("messages")
    if not isinstance(context_messages, list):
        return messages
    allowed_ids = {
        str(item.get("message_id", "")).strip()
        for item in context_messages
        if isinstance(item, Mapping) and str(item.get("message_id", "")).strip()
    }
    if not allowed_ids:
        return messages
    return [message for message in messages if _evaluation_message_id(message) in allowed_ids]


def _format_evaluation_context(
    evaluation_context: Mapping[str, object] | None,
    task_context: Mapping[str, object] | None,
) -> str:
    """Render bounded caller-owned context without making it part of the score schema."""
    context = dict(evaluation_context or {})
    for key, value in dict(task_context or {}).items():
        context.setdefault(key, value)
    if not context:
        return "（未提供额外任务上下文；只评估对话中真实出现的观察机会）"
    lines: list[str] = []
    for key in (
        "task_goal",
        "scenario",
        "difficulty",
        "observable_competencies",
        "challenge_competencies",
        "task_objectives",
        "training_goals",
        "scenario_id",
        "category",
        "learner_role",
    ):
        value = context.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"- {key}: {value}")
    return "\n".join(lines) or "（未提供可用的额外任务上下文）"


def _coerce_rating(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        rating = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return rating if 1 <= rating <= 5 else None


def _verified_evidence(
    raw_evidence: object,
    *,
    user_messages: Mapping[str, str],
) -> list[dict[str, object]]:
    """Keep only citations that can be located in an original user message."""
    if not isinstance(raw_evidence, list):
        return []
    verified: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_evidence:
        if not isinstance(item, Mapping):
            continue
        message_id = str(item.get("message_id", "")).strip()
        quote = str(item.get("quote", "")).strip()
        source = user_messages.get(message_id)
        if not source or not quote:
            continue
        if quote not in source:
            continue
        key = (message_id, quote)
        if key in seen:
            continue
        seen.add(key)
        verified.append(
            {
                "message_id": int(message_id) if message_id.isdigit() else message_id,
                "quote": quote,
            }
        )
    return verified


def _build_assessment_payload(
    parsed: object,
    *,
    user_messages: Mapping[str, str],
    judge_model: str | None = None,
) -> tuple[dict[str, object], float | None]:
    """Validate the judge response and derive the optional session outcome score."""
    root = parsed if isinstance(parsed, Mapping) else {}
    raw_competencies = root.get("competencies", {})
    competency_map = raw_competencies if isinstance(raw_competencies, Mapping) else {}
    competencies: dict[str, dict[str, object]] = {}
    for dimension in COMPETENCY_DIMENSIONS:
        raw_dimension = competency_map.get(dimension, {})
        dimension_data = raw_dimension if isinstance(raw_dimension, Mapping) else {}
        opportunity_present = dimension_data.get("opportunity_present") is True
        evidence = _verified_evidence(
            dimension_data.get("evidence"),
            user_messages=user_messages,
        )
        rating = _coerce_rating(dimension_data.get("rating"))
        if not opportunity_present or not evidence:
            rating = None
        evidence_message_ids = {str(item["message_id"]) for item in evidence}
        if rating == 5 and len(evidence_message_ids) < 2:
            rating = None
        competencies[dimension] = {
            "opportunity_present": opportunity_present,
            "rating": rating,
            "evidence": evidence,
            "reason": str(dimension_data.get("reason", "")).strip(),
            "suggestion": str(dimension_data.get("suggestion", "")).strip(),
        }

    has_valid_competency = any(
        item["rating"] is not None for item in competencies.values()
    )
    outcomes: dict[str, dict[str, object]] = {}
    for outcome_id in ("effectiveness", "appropriateness"):
        raw_outcome = root.get(outcome_id, {})
        outcome_data = raw_outcome if isinstance(raw_outcome, Mapping) else {}
        evidence = _verified_evidence(
            outcome_data.get("evidence"),
            user_messages=user_messages,
        )
        rating = _coerce_rating(outcome_data.get("rating"))
        if not evidence:
            rating = None
        if rating == 5 and len({str(item["message_id"]) for item in evidence}) < 2:
            rating = None
        outcomes[outcome_id] = {
            "rating": rating,
            "evidence": evidence,
            "reason": str(outcome_data.get("reason", "")).strip(),
        }
    outcome_scores = [
        score
        for score in (
            outcomes["effectiveness"]["rating"],
            outcomes["appropriateness"]["rating"],
        )
        if isinstance(score, int)
    ]
    outcome_rating = (
        round(sum(outcome_scores) / len(outcome_scores), 2)
        if len(outcome_scores) == 2
        else None
    )
    status = (
        "ready"
        if has_valid_competency or outcome_scores
        else "insufficient_evidence"
    )
    return (
        {
            "rubric_version": COMMUNICATION_RUBRIC_VERSION,
            "judge_version": COMMUNICATION_JUDGE_VERSION,
            "judge_model": judge_model,
            "status": status,
            "effectiveness": outcomes["effectiveness"],
            "appropriateness": outcomes["appropriateness"],
            "competencies": competencies,
        },
        outcome_rating,
    )


def _competencies_from_scores(scores: object) -> Mapping[str, object]:
    if not isinstance(scores, Mapping):
        return {}
    competencies = scores.get("competencies")
    return competencies if isinstance(competencies, Mapping) else {}


def _is_current_observed_evaluation(evaluation: CompetencyEvaluation) -> bool:
    scores = evaluation.scores
    if not isinstance(scores, Mapping):
        return False
    if scores.get("rubric_version") != COMMUNICATION_RUBRIC_VERSION:
        return False
    if scores.get("status") != "ready":
        return False
    return any(
        isinstance(value, Mapping)
        and value.get("opportunity_present") is True
        and _coerce_rating(value.get("rating")) is not None
        and isinstance(value.get("evidence"), list)
        and bool(value.get("evidence"))
        for value in _competencies_from_scores(scores).values()
    )


def _judge_model_identity(llm: LLMPort) -> str | None:
    metadata = getattr(llm, "provider_metadata", None)
    provider = str(getattr(metadata, "provider", "") or "").strip()
    model = str(getattr(metadata, "default_model", "") or "").strip()
    if provider and model:
        return f"{provider}:{model}"
    return model or provider or None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GrowthService:
    """Competency evaluation, dashboard aggregation, and growth insights."""

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        llm: Optional[LLMPort],
        persona_loader,
    ) -> None:
        self._uow_factory = uow_factory
        self._llm = llm
        self._persona_loader = persona_loader

    @property
    def has_llm(self) -> bool:
        return self._llm is not None

    async def _load_scoped_growth_data(
        self,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> tuple[list[ChatRoom], list[CompetencyEvaluation]]:
        """Load only rooms and evaluations visible to the authenticated caller."""
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="read_growth_data",
        )
        async with self._uow_factory(readonly=True) as uow:
            rooms = await uow.chat_room_repository.list_rooms(limit=500)
            evaluations = await uow.competency_evaluation_repository.list_all(limit=500)

        visible_rooms = [
            room
            for room in rooms
            if stakeholder_room_matches_access_scope(
                room,
                scope,
                self._persona_loader,
                operation="read_growth_data",
            )
        ]
        visible_room_ids = {room.id for room in visible_rooms if room.id is not None}
        visible_evaluations = [
            evaluation
            for evaluation in evaluations
            if evaluation.room_id in visible_room_ids
        ]
        return visible_rooms, visible_evaluations

    # ------------------------------------------------------------------
    # 1. Competency Evaluation (LLM-as-Judge)
    # ------------------------------------------------------------------

    async def evaluate_competency(
        self,
        report_id: int,
        evaluation_context: Mapping[str, object] | None = None,
        task_context: Mapping[str, object] | None = None,
    ) -> Optional[CompetencyEvaluation]:
        """Evaluate user competency for a given analysis report.

        Idempotent: skips if evaluation already exists for report_id.
        """
        if self._llm is None:
            logger.warning(
                "Skipping competency evaluation for report %d: stakeholder LLM is not configured",
                report_id,
            )
            return None

        # Check idempotency
        async with self._uow_factory(readonly=True) as uow:
            existing = await uow.competency_evaluation_repository.get_by_report_id(report_id)
            if existing:
                logger.info(
                    "Competency evaluation already exists for report %d, skipping", report_id
                )
                return existing

        # Load report + room + messages
        async with self._uow_factory(readonly=True) as uow:
            report = await uow.analysis_report_repository.get_by_id(report_id)
            if report is None:
                logger.error("Report %d not found for competency evaluation", report_id)
                return None

            room = await uow.chat_room_repository.get_by_id(report.room_id)
            if room is None:
                logger.error("Room %d not found for competency evaluation", report.room_id)
                return None

            messages = await uow.stakeholder_message_repository.list_by_room_id(
                report.room_id, limit=200
            )

        if not messages:
            logger.warning("No messages in room %d for competency evaluation", report.room_id)
            return None

        # Build prompt
        bounded_messages = _bounded_evaluation_messages(
            messages,
            evaluation_context or task_context,
        )
        history = [
            {
                "message_id": _evaluation_message_id(message),
                "sender_type": message.sender_type,
                "sender_id": message.sender_id,
                "content": message.content,
                "emotion_score": message.emotion_score,
                "emotion_label": message.emotion_label,
            }
            for message in bounded_messages
        ]

        conversation_text = _build_conversation_text(history, self._persona_loader)
        persona_profiles = _build_persona_profiles(room.persona_ids, self._persona_loader)

        prompt = _JUDGE_SYSTEM_PROMPT.format(
            persona_profiles=persona_profiles,
            conversation=conversation_text,
            evaluation_context=_format_evaluation_context(evaluation_context, task_context),
        )

        # Call LLM with structured output
        llm_messages = [LLMMessage(role="user", content=prompt)]
        try:
            parsed = await self._llm.generate_structured(
                llm_messages,
                schema=_JUDGE_SCHEMA,
                schema_name="evaluate_competency",
                schema_description="communication-core-v1 证据锚定沟通评估",
                temperature=0.2,
            )
        except Exception as exc:
            logger.error("LLM call failed for competency eval: %s", exc)
            return None

        user_messages = {
            _evaluation_message_id(message): message.content
            for message in bounded_messages
            if message.sender_type == "user"
        }
        scores, outcome_rating = _build_assessment_payload(
            parsed,
            user_messages=user_messages,
            judge_model=_judge_model_identity(self._llm),
        )

        # Persist
        evaluation = CompetencyEvaluation(
            id=None,
            report_id=report_id,
            room_id=report.room_id,
            scores=scores,
            outcome_rating=outcome_rating,
        )

        async with self._uow_factory() as uow:
            saved = await uow.competency_evaluation_repository.create(evaluation)

        logger.info(
            "Competency evaluation created for report %d, outcome_score=%s, status=%s",
            report_id,
            outcome_rating,
            scores["status"],
        )
        return saved

    # ------------------------------------------------------------------
    # 2. Dashboard Aggregation
    # ------------------------------------------------------------------

    async def get_dashboard(
        self,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> GrowthDashboardDTO:
        """Aggregate competency evaluations visible to the caller."""
        rooms, evaluations = await self._load_scoped_growth_data(access_scope=access_scope)

        room_map = {r.id: r.name for r in rooms}

        # Build evaluation DTOs
        eval_dtos: list[CompetencyEvaluationDTO] = []
        for ev in evaluations:
            assessment = ev.scores if isinstance(ev.scores, Mapping) else {}
            dim_scores: dict[str, DimensionScoreDTO] = {}
            for dim_key, dim_val in _competencies_from_scores(assessment).items():
                if isinstance(dim_val, dict):
                    dim_scores[dim_key] = DimensionScoreDTO(
                        opportunity_present=dim_val.get("opportunity_present") is True,
                        rating=_coerce_rating(dim_val.get("rating")),
                        evidence=dim_val.get("evidence", []),
                        reason=str(dim_val.get("reason", "")),
                        suggestion=dim_val.get("suggestion", ""),
                    )
            eval_dtos.append(
                CompetencyEvaluationDTO(
                    id=ev.id,
                    report_id=ev.report_id,
                    room_id=ev.room_id,
                    room_name=room_map.get(ev.room_id, ""),
                    rubric_version=str(
                        assessment.get("rubric_version", COMMUNICATION_RUBRIC_VERSION)
                    ),
                    judge_version=str(
                        assessment.get("judge_version", COMMUNICATION_JUDGE_VERSION)
                    ),
                    judge_model=(
                        str(assessment.get("judge_model")).strip()
                        if assessment.get("judge_model")
                        else None
                    ),
                    status=str(assessment.get("status", "insufficient_evidence")),
                    effectiveness=OutcomeScoreDTO(
                        **(
                            assessment.get("effectiveness")
                            if isinstance(assessment.get("effectiveness"), Mapping)
                            else {}
                        )
                    ),
                    appropriateness=OutcomeScoreDTO(
                        **(
                            assessment.get("appropriateness")
                            if isinstance(assessment.get("appropriateness"), Mapping)
                            else {}
                        )
                    ),
                    competencies=dim_scores,
                    outcome_rating=ev.outcome_rating,
                    created_at=ev.created_at,
                )
            )

        # Overview
        total_evaluations = len(eval_dtos)
        outcome_scores = [
            evaluation.outcome_rating
            for evaluation in eval_dtos
            if evaluation.outcome_rating is not None
        ]
        avg_score = (
            round(sum(outcome_scores) / len(outcome_scores), 2) if outcome_scores else None
        )
        latest_outcome_rating = next(
            (
                evaluation.outcome_rating
                for evaluation in reversed(eval_dtos)
                if evaluation.outcome_rating is not None
            ),
            None,
        )

        overview = GrowthOverviewDTO(
            total_sessions=len(rooms),
            total_evaluations=total_evaluations,
            avg_outcome_rating=avg_score,
            latest_outcome_rating=latest_outcome_rating,
        )

        # Dimension trends
        dimension_trends: dict[str, list[DimensionTrendPointDTO]] = {}
        for dim in COMPETENCY_DIMENSIONS:
            points: list[DimensionTrendPointDTO] = []
            for source_evaluation, ev in zip(evaluations, eval_dtos, strict=True):
                if not _is_current_observed_evaluation(source_evaluation):
                    continue
                dim_dto = ev.competencies.get(dim)
                if dim_dto and dim_dto.rating is not None:
                    points.append(
                        DimensionTrendPointDTO(date=ev.created_at, score=dim_dto.rating)
                    )
            dimension_trends[dim] = points

        return GrowthDashboardDTO(
            overview=overview,
            evaluations=eval_dtos,
            dimension_trends=dimension_trends,
        )

    # ------------------------------------------------------------------
    # 3. Growth Insight (cross-session LLM analysis)
    # ------------------------------------------------------------------

    async def generate_insight(
        self,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> GrowthInsightDTO:
        """Generate LLM-powered cross-session growth insight."""
        rooms, evaluations = await self._load_scoped_growth_data(access_scope=access_scope)
        evaluations = [
            evaluation
            for evaluation in evaluations
            if _is_current_observed_evaluation(evaluation)
        ]

        if len(evaluations) < 2:
            return GrowthInsightDTO(
                insight="练习次数还不够，至少完成 2 次对话分析后才能生成成长洞察。继续练习吧！"
            )

        room_map = {r.id: r.name for r in rooms}

        # Build evaluation data summary for prompt
        lines: list[str] = []
        for i, ev in enumerate(evaluations, 1):
            room_name = room_map.get(ev.room_id, f"Room {ev.room_id}")
            date_str = ev.created_at.strftime("%Y-%m-%d %H:%M") if ev.created_at else "unknown"
            lines.append(f"### 第 {i} 次评估 ({room_name}, {date_str})")
            lines.append(f"本次任务表现: {ev.outcome_rating if ev.outcome_rating is not None else 'N/A'}")
            competencies = _competencies_from_scores(ev.scores)
            for dim in COMPETENCY_DIMENSIONS:
                dim_data = competencies.get(dim, {})
                score = (
                    dim_data.get("rating") or "N/A"
                    if isinstance(dim_data, Mapping)
                    else "N/A"
                )
                evidence = dim_data.get("evidence", []) if isinstance(dim_data, Mapping) else []
                suggestion = (
                    dim_data.get("suggestion", "") if isinstance(dim_data, Mapping) else ""
                )
                dim_label = {
                    "attentiveness": "倾听关注",
                    "expression": "表达清晰",
                    "coordination": "互动协调",
                    "composure": "沉着应对",
                }.get(dim, dim)
                lines.append(f"- {dim_label}: {score}/5")
                # Include evidence/suggestion only for recent 3 evaluations
                if i > len(evaluations) - 3:
                    if evidence:
                        quotes = [
                            str(item.get("quote", ""))
                            for item in evidence
                            if isinstance(item, Mapping) and item.get("quote")
                        ]
                        if quotes:
                            lines.append(f"  证据: {'；'.join(quotes)}")
                    if suggestion:
                        lines.append(f"  建议: {suggestion}")
            lines.append("")

        evaluation_data = "\n".join(lines)
        prompt = _INSIGHT_SYSTEM_PROMPT.format(evaluation_data=evaluation_data)

        llm_messages = [LLMMessage(role="user", content=prompt)]
        if self._llm is None:
            return GrowthInsightDTO(
                insight=(
                    "当前未配置 Stakeholder LLM，无法生成跨 session 成长洞察。"
                    "请启用 NewAPI 用户计费并在网关中配置模型后重启服务。"
                )
            )
        response = await self._llm.generate(llm_messages, temperature=0.4)

        return GrowthInsightDTO(insight=response.content.strip())

    # ------------------------------------------------------------------
    # 4. Profile Card Generation
    # ------------------------------------------------------------------

    async def generate_profile_card(
        self,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ):
        """Generate a profile card from historical competency data."""
        from application.services.stakeholder.dto import ProfileCardDTO

        _, evaluations = await self._load_scoped_growth_data(access_scope=access_scope)
        evaluations = [
            evaluation
            for evaluation in evaluations
            if _is_current_observed_evaluation(evaluation)
        ]

        if len(evaluations) < 2:
            return ProfileCardDTO(
                summary="有效观察还不够，至少完成 2 次有证据的沟通评估后才能生成沟通力名片。",
                scores={},
            )

        if self._llm is None:
            return ProfileCardDTO(
                summary=(
                    "当前未配置 Stakeholder LLM，无法生成沟通力名片。"
                    "请启用 NewAPI 用户计费并在网关中配置模型后重启服务。"
                ),
                scores={},
            )

        # Keep the profile contract aligned with the radar: latest five valid
        # observations per dimension, summarized by median.
        dim_totals: dict[str, list[float]] = {}
        for ev in reversed(evaluations):
            competencies = _competencies_from_scores(ev.scores)
            for dim in COMPETENCY_DIMENSIONS:
                values = dim_totals.setdefault(dim, [])
                if len(values) >= 5:
                    continue
                dim_data = competencies.get(dim, {})
                score = (
                    _coerce_rating(dim_data.get("rating"))
                    if isinstance(dim_data, Mapping)
                    else None
                )
                if score is not None:
                    values.append(float(score))

        avg_scores: dict[str, float] = {}
        for dim in COMPETENCY_DIMENSIONS:
            vals = dim_totals.get(dim, [])
            if vals:
                avg_scores[dim] = round(float(median(vals)), 1)

        # Build evaluation summary for LLM
        dim_labels = {
            "attentiveness": "倾听关注",
            "expression": "表达清晰",
            "coordination": "互动协调",
            "composure": "沉着应对",
        }

        lines = [f"共 {len(evaluations)} 次评估\n"]
        for dim in COMPETENCY_DIMENSIONS:
            label = dim_labels.get(dim, dim)
            avg = avg_scores.get(dim)
            vals = dim_totals.get(dim, [])
            lines.append(
                f"- {label}: "
                f"{f'最近有效观察中位数 {avg}/5，共 {len(vals)} 个观察' if avg is not None else 'N/A'}"
            )

        # Include evidence from recent evaluations
        recent_evals = evaluations[-3:]
        for i, ev in enumerate(recent_evals, 1):
            lines.append(f"\n### 最近第 {i} 次评估")
            competencies = _competencies_from_scores(ev.scores)
            for dim in COMPETENCY_DIMENSIONS:
                dim_data = competencies.get(dim, {})
                if isinstance(dim_data, Mapping):
                    evidence = dim_data.get("evidence", [])
                    if evidence:
                        quotes = [
                            str(item.get("quote", ""))
                            for item in evidence
                            if isinstance(item, Mapping) and item.get("quote")
                        ]
                        if quotes:
                            lines.append(
                                f"- {dim_labels.get(dim, dim)}: {'；'.join(quotes)}"
                            )

        evaluation_data = "\n".join(lines)
        prompt = _PROFILE_CARD_PROMPT.format(evaluation_data=evaluation_data)

        llm_messages = [LLMMessage(role="user", content=prompt)]
        try:
            parsed = await self._llm.generate_structured(
                llm_messages,
                schema=_PROFILE_CARD_SCHEMA,
                schema_name="generate_profile_card",
                schema_description="生成沟通力画像",
                temperature=0.4,
            )
        except Exception as exc:
            logger.error("LLM call failed for profile card: %s", exc)
            return None

        return ProfileCardDTO(
            summary=parsed.get("summary", ""),
            scores=avg_scores,
        )
