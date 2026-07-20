# input: AbstractUnitOfWork, LLMPort, PersonaLoader
# output: AnalysisService 对话分析报告生成服务, AnalysisReaderService 只读报告查询服务
# output-update: Training Studio video-answer markers are sanitized into report input with content/camera review placeholders.
# owner: wanhua.gu
# pos: 应用层服务 - 利益相关者对话分析（AnalysisService=LLM 生成, AnalysisReaderService=只读查询）；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Application service for generating stakeholder conversation analysis reports.

Uses LLM to analyze the full conversation history and produce structured insights:
- Resistance ranking: who opposed the most and why
- Effective arguments: which user arguments shifted attitudes
- Communication suggestions: actionable advice per persona
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Optional

from application.ports.llm import LLMMessage, LLMPort
from application.services.stakeholder.prompt_builder import build_org_context
from application.services.stakeholder.dto import (
    AnalysisContentDTO,
    AnalysisReportDTO,
    AnalysisReportSummaryDTO,
)
from application.services.stakeholder.room_access_policy import (
    StakeholderRoomAccessScope,
    StakeholderRoomAction,
    require_stakeholder_room_access,
    require_stakeholder_room_access_scope,
)
from domain.common.exceptions import BusinessException
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.stakeholder.entity import AnalysisReport
from shared.codes import BusinessCode

logger = logging.getLogger(__name__)

_ANALYSIS_SYSTEM_PROMPT = """\
你是一位专业的沟通策略分析师。请分析以下利益相关者模拟对话，输出严格 JSON 格式的分析报告。

## 参与角色

{persona_profiles}

## 对话记录

{conversation}

## 输出要求

请从三个维度分析，并输出以下 JSON 结构（不要输出其他内容，只输出 JSON）：

```json
{{
  "summary": "一段 50-100 字的整体分析摘要",
  "resistance_ranking": [
    {{
      "persona_id": "角色ID",
      "persona_name": "角色名称",
      "score": -5到5的整数（-5=强烈反对, 0=中立, 5=强烈支持）,
      "reason": "该角色为什么持这个态度，基于对话中的具体表现",
      "message_indices": [1, 3, 7]
    }}
  ],
  "effective_arguments": [
    {{
      "argument": "用户使用的具体论点",
      "target_persona": "这个论点主要影响了哪个角色",
      "effectiveness": "为什么这个论点有效，对方态度有什么变化",
      "message_indices": [5, 6]
    }}
  ],
  "communication_suggestions": [
    {{
      "persona_id": "角色ID",
      "persona_name": "角色名称",
      "suggestion": "针对这个角色的具体沟通建议",
      "priority": "high/medium/low"
    }}
  ]
}}
```

分析要点：
- resistance_ranking 按阻力从大到小排序（score 从低到高）
- effective_arguments 只列出确实产生了效果的论点，如果没有则为空数组
- communication_suggestions 要具体可操作，不要笼统的建议
- 基于对话中的情绪变化（emotion_score）和实际发言内容做判断
- message_indices 必须引用对话记录中 [#N] 的序号，列出支撑该结论的关键消息（通常 1-3 条最相关的）
"""

_ANALYSIS_ENHANCEMENT_PROMPT = """

Additional report requirements:
- Keep the legacy fields resistance_ranking, effective_arguments, and
  communication_suggestions exactly as JSON arrays.
- Every conclusion must cite conversation message_indices using the [#N]
  numbers shown above. Prefer 1-3 precise indices per item.
- Also output these arrays:
  - evidence_reviews: evidence-based debrief items with claim, evidence,
    insight, and message_indices.
  - alternative_phrasings: situation, original, alternative, rationale,
    and message_indices.
  - rewrite_demos: original, rewritten, principle, and message_indices.
  - micro_drills: title, goal, prompt, practice_steps, success_criteria,
    target_persona, and message_indices.
  - high_signal_moments: title, moment_type, why_it_matters,
    recommendation, and message_indices.
- If the conversation includes a "[Training Studio video answer]" marker, also
  output:
  - content_delivery: score 0-100, label, rationale, evidence, suggestions,
    status, and message_indices. Assess only the user's communication content,
    structure, clarity, evidence, and delivery described in the transcript.
  - camera_presence: score, label, rationale, evidence, suggestions, status,
    and message_indices. If no actual visual metrics are available, set
    score to null, status to "placeholder", and do not invent eye contact,
    posture, facial expression, nervousness, or reading-from-notes findings.
- Do not invent message IDs. Use message_indices only; the system resolves IDs.
"""

_LIST_FIELDS = {
    "resistance_ranking",
    "effective_arguments",
    "communication_suggestions",
    "evidence_reviews",
    "alternative_phrasings",
    "rewrite_demos",
    "micro_drills",
    "high_signal_moments",
}

_ANCHOR_SECTION_FIELDS = {
    "resistance_ranking",
    "effective_arguments",
    "evidence_reviews",
    "alternative_phrasings",
    "rewrite_demos",
    "micro_drills",
    "high_signal_moments",
}

_TRAINING_DIMENSION_FIELDS = {"content_delivery", "camera_presence"}
_VIDEO_ANSWER_MARKER = "[video-answer]"


def _split_video_answer_content(content: str) -> tuple[str, dict[str, Any] | None]:
    """Return a clean caption plus parsed local video-answer metadata, if present."""
    if _VIDEO_ANSWER_MARKER not in content:
        return content, None

    marker_index = content.index(_VIDEO_ANSWER_MARKER)
    caption = content[:marker_index].strip()
    raw = content[marker_index + len(_VIDEO_ANSWER_MARKER) :].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return caption or content, None
    if not isinstance(parsed, dict):
        return caption or content, None
    return caption, parsed


def _format_duration_ms(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    try:
        total_seconds = max(0, int(value) // 1000)
    except (TypeError, ValueError):
        return ""
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}:{seconds:02d}"


def _format_video_answer_for_analysis(content: str) -> tuple[str, bool]:
    caption, attachment = _split_video_answer_content(content)
    if not attachment:
        return content, False

    details = ["type=video_answer_submitted"]
    duration = _format_duration_ms(attachment.get("durationMs"))
    if duration:
        details.append(f"duration={duration}")
    mime_type = _text(attachment.get("mimeType"))
    if mime_type:
        details.append(f"mime_type={mime_type}")
    recorded_at = _text(attachment.get("recordedAt"))
    if recorded_at:
        details.append(f"recorded_at={recorded_at}")

    training_event = attachment.get("trainingEvent")
    if isinstance(training_event, dict):
        dimensions = training_event.get("reportDimensions")
        if isinstance(dimensions, list):
            clean_dimensions = [str(item) for item in dimensions if isinstance(item, str)]
            if clean_dimensions:
                details.append(f"report_dimensions={','.join(clean_dimensions)}")
        camera_status = _text(training_event.get("cameraPresenceStatus"))
        if camera_status:
            details.append(f"camera_presence_status={camera_status}")

    readable_caption = caption or _text(attachment.get("title")) or "Video answer submitted"
    note = (
        "[Training Studio video answer: "
        + "; ".join(details)
        + "; visual_metrics=not_computed_yet]"
    )
    return f"{readable_caption}\n{note}", True


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Extract a JSON object from a lenient LLM response."""
    text = raw_text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    elif not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]

    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("analysis JSON root must be an object", text, 0)
    return parsed


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _coerce_message_indices(value: Any) -> list[int]:
    values = value if isinstance(value, list) else [value]
    indices: list[int] = []
    for item in values:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            idx = item
        elif isinstance(item, str):
            match = re.search(r"\d+", item)
            if not match:
                continue
            idx = int(match.group(0))
        else:
            continue
        if idx > 0 and idx not in indices:
            indices.append(idx)
    return indices


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _coerce_score(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(-5, min(5, score))


def _coerce_optional_percentage(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, min(100, score))


def _string_list(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [item for item in items if isinstance(item, str) and item.strip()]


def _sanitize_analysis_item(field: str, item: dict[str, Any]) -> dict[str, Any]:
    if field == "resistance_ranking":
        item["persona_id"] = _text(item.get("persona_id"))
        item["persona_name"] = _text(item.get("persona_name"))
        item["score"] = _coerce_score(item.get("score"))
        item["reason"] = _text(item.get("reason"))
    elif field == "effective_arguments":
        item["argument"] = _text(item.get("argument"))
        item["target_persona"] = _text(item.get("target_persona"))
        item["effectiveness"] = _text(item.get("effectiveness"))
    elif field == "communication_suggestions":
        item["persona_id"] = _text(item.get("persona_id"))
        item["persona_name"] = _text(item.get("persona_name"))
        item["suggestion"] = _text(item.get("suggestion"))
        if item.get("priority") not in {"high", "medium", "low"}:
            item["priority"] = "medium"
    return item


def _normalize_training_dimension(
    value: Any,
    message_id_map: dict[int, int],
    anchor_map: dict[int, dict[str, Any]],
    *,
    include_placeholder: bool,
    fallback_label: str,
    fallback_rationale: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        if not include_placeholder:
            return None
        value = {}

    item = dict(value)
    score = _coerce_optional_percentage(item.get("score"))
    status = item.get("status")
    if status not in {"observed", "placeholder", "not_applicable"}:
        status = "observed" if score is not None else "placeholder"

    indices = _coerce_message_indices(item.get("message_indices"))
    return {
        "score": score,
        "label": _text(item.get("label")) or fallback_label,
        "rationale": _text(item.get("rationale")) or fallback_rationale,
        "evidence": _string_list(item.get("evidence")),
        "suggestions": _string_list(item.get("suggestions")),
        "status": status,
        "message_indices": indices,
        "message_ids": [message_id_map[i] for i in indices if i in message_id_map],
        "message_anchors": [anchor_map[i] for i in indices if i in anchor_map],
    }


def _build_message_anchors(history: list[dict], persona_loader) -> dict[int, dict[str, Any]]:
    anchors: dict[int, dict[str, Any]] = {}
    seq = 0
    for msg in history:
        sender_type = msg["sender_type"]
        if sender_type == "system":
            continue
        seq += 1
        sender_id = msg["sender_id"]
        speaker = "user"
        if sender_type == "persona":
            p = persona_loader.get_persona(sender_id) if persona_loader else None
            speaker = p.name if p else sender_id
        quote, _ = _format_video_answer_for_analysis(msg.get("content", ""))
        anchors[seq] = {
            "message_index": seq,
            "message_id": msg.get("id"),
            "sender_type": sender_type,
            "sender_id": sender_id,
            "speaker": speaker,
            "quote": quote,
            "emotion_score": msg.get("emotion_score"),
            "emotion_label": msg.get("emotion_label"),
        }
    return anchors


def _normalize_analysis_payload(
    parsed: dict[str, Any],
    message_id_map: dict[int, int],
    anchor_map: dict[int, dict[str, Any]],
    *,
    has_video_answers: bool = False,
) -> dict[str, Any]:
    normalized: dict[str, Any] = {"summary": str(parsed.get("summary") or "分析完成")}
    for field in _LIST_FIELDS:
        normalized[field] = _as_list(parsed.get(field))

    normalized["message_id_map"] = {str(k): v for k, v in message_id_map.items()}
    normalized["message_anchors"] = list(anchor_map.values())

    for field in _ANCHOR_SECTION_FIELDS:
        items: list[dict[str, Any]] = []
        for raw_item in normalized[field]:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            item = _sanitize_analysis_item(field, item)
            indices = _coerce_message_indices(item.get("message_indices"))
            item["message_indices"] = indices
            item["message_ids"] = [message_id_map[i] for i in indices if i in message_id_map]
            item["message_anchors"] = [anchor_map[i] for i in indices if i in anchor_map]
            items.append(item)
        normalized[field] = items

    normalized["communication_suggestions"] = [
        _sanitize_analysis_item("communication_suggestions", dict(item))
        for item in normalized["communication_suggestions"]
        if isinstance(item, dict)
    ]

    normalized["content_delivery"] = _normalize_training_dimension(
        parsed.get("content_delivery"),
        message_id_map,
        anchor_map,
        include_placeholder=has_video_answers,
        fallback_label="Content delivery pending",
        fallback_rationale="Video answer was captured, but no structured content-delivery assessment was returned.",
    )
    normalized["camera_presence"] = _normalize_training_dimension(
        parsed.get("camera_presence"),
        message_id_map,
        anchor_map,
        include_placeholder=has_video_answers,
        fallback_label="Camera presence placeholder",
        fallback_rationale=(
            "Video answer metadata is available, but eye contact, facial expression, posture, "
            "and nervousness metrics have not been computed yet."
        ),
    )

    return normalized


def _build_conversation_text(history: list[dict], persona_loader) -> tuple[str, dict[int, int]]:
    """Format conversation history into readable text for LLM analysis.

    Returns:
        Tuple of (conversation_text, message_id_map) where message_id_map
        maps 1-based sequence numbers to database message IDs.
    """
    lines: list[str] = []
    message_id_map: dict[int, int] = {}
    seq = 0
    for msg in history:
        sender_type = msg["sender_type"]
        if sender_type == "system":
            continue

        seq += 1
        msg_id = msg.get("id")
        if msg_id is not None:
            message_id_map[seq] = msg_id

        sender_id = msg["sender_id"]
        content, _has_video = _format_video_answer_for_analysis(msg["content"])
        emotion = ""
        if msg.get("emotion_score") is not None:
            emotion = f" [情绪: {msg.get('emotion_label', '未知')}({msg['emotion_score']})]"

        if sender_type == "user":
            lines.append(f"[#{seq}] [用户]{emotion}: {content}")
        elif sender_type == "persona":
            p = persona_loader.get_persona(sender_id) if persona_loader else None
            name = p.name if p else sender_id
            lines.append(f"[#{seq}] [{name}]{emotion}: {content}")

    return "\n\n".join(lines), message_id_map


def _has_video_answers(history: list[dict]) -> bool:
    return any(
        msg.get("sender_type") == "user"
        and _format_video_answer_for_analysis(msg.get("content", ""))[1]
        for msg in history
    )


def _build_persona_profiles(persona_ids: list[str], persona_loader, org_context: str = "") -> str:
    """Build persona profile summaries for the analysis prompt."""
    profiles: list[str] = []
    for pid in persona_ids:
        p = persona_loader.get_persona(pid)
        if p:
            profiles.append(f"- **{p.name}** ({pid}): {p.role}")
    text = "\n".join(profiles) if profiles else "（无角色信息）"
    if org_context:
        text += f"\n\n{org_context}"
    return text


class AnalysisService:
    """Generates and persists LLM-powered conversation analysis reports."""

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        llm: LLMPort,
        persona_loader,
    ) -> None:
        self._uow_factory = uow_factory
        self._llm = llm
        self._persona_loader = persona_loader

    async def generate_report(
        self,
        room_id: int,
        *,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> AnalysisReportDTO:
        """Generate a new analysis report for the given room."""

        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="generate_analysis_report",
        )
        # 1. Load room and messages
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            room = require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            ).room

            messages = await uow.stakeholder_message_repository.list_by_room_id(room_id, limit=200)

        if not messages:
            raise BusinessException(
                code=BusinessCode.ANALYSIS_NO_MESSAGES,
                message="No messages to analyze",
                error_type="NoMessages",
                details={"room_id": room_id},
            )

        # 2. Build analysis prompt
        history = [
            {
                "id": m.id,
                "sender_type": m.sender_type,
                "sender_id": m.sender_id,
                "content": m.content,
                "emotion_score": m.emotion_score,
                "emotion_label": m.emotion_label,
            }
            for m in messages
        ]

        conversation_text, message_id_map = _build_conversation_text(history, self._persona_loader)
        anchor_map = _build_message_anchors(history, self._persona_loader)
        has_video_answers = _has_video_answers(history)

        # Build org context for analysis if any persona belongs to an org
        org_ctx = ""
        for pid in room.persona_ids:
            p = self._persona_loader.get_persona(pid)
            p_org_id = getattr(p, "organization_id", None) if p else None
            if p_org_id:
                async with self._uow_factory(readonly=True) as uow:
                    org = await uow.organization_repository.get_by_id(p_org_id)
                    if org:
                        rels = await uow.persona_relationship_repository.list_by_organization(
                            p.organization_id
                        )
                        rel_dicts = []
                        for r in rels:
                            fp = self._persona_loader.get_persona(r.from_persona_id)
                            tp = self._persona_loader.get_persona(r.to_persona_id)
                            rel_dicts.append(
                                {
                                    "persona_name": f"{fp.name if fp else r.from_persona_id} → {tp.name if tp else r.to_persona_id}",
                                    "relationship_type": r.relationship_type,
                                    "description": r.description,
                                }
                            )
                        org_ctx = build_org_context(
                            org_name=org.name,
                            org_context_prompt=org.context_prompt,
                            relationships=rel_dicts if rel_dicts else None,
                        )
                break

        persona_profiles = _build_persona_profiles(room.persona_ids, self._persona_loader, org_ctx)

        system_prompt = _ANALYSIS_SYSTEM_PROMPT.format(
            persona_profiles=persona_profiles,
            conversation=conversation_text,
        ) + _ANALYSIS_ENHANCEMENT_PROMPT

        # 3. Call LLM
        llm_messages = [LLMMessage(role="user", content=system_prompt)]
        response = await self._llm.generate(llm_messages, temperature=0.3)

        # 4. Parse response
        raw_text = response.content.strip()
        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines)

        try:
            parsed = _extract_json_object(response.content)
        except json.JSONDecodeError:
            logger.error("LLM returned invalid JSON for analysis: %s", response.content[:500])
            raise BusinessException(
                code=BusinessCode.ANALYSIS_PARSE_ERROR,
                message="Failed to parse analysis report from LLM",
                error_type="AnalysisParseError",
                details={"room_id": room_id},
            )

        summary = parsed.get("summary", "分析完成")
        content_data = {
            "resistance_ranking": parsed.get("resistance_ranking", []),
            "effective_arguments": parsed.get("effective_arguments", []),
            "communication_suggestions": parsed.get("communication_suggestions", []),
            "message_id_map": {str(k): v for k, v in message_id_map.items()},
        }

        normalized = _normalize_analysis_payload(
            parsed,
            message_id_map,
            anchor_map,
            has_video_answers=has_video_answers,
        )
        summary = normalized.pop("summary")
        content_data = normalized

        # 5. Validate with Pydantic (lenient: drop invalid items)
        try:
            content_dto = AnalysisContentDTO.model_validate(content_data)
        except Exception:
            logger.warning("Partial validation failure, using raw content")
            content_dto = AnalysisContentDTO(
                resistance_ranking=[],
                effective_arguments=[],
                communication_suggestions=[],
            )

        # 6. Persist
        report = AnalysisReport(
            id=None,
            room_id=room_id,
            summary=summary,
            content=content_dto.model_dump(),
        )

        async with self._uow_factory() as uow:
            saved = await uow.analysis_report_repository.create(report)

        return AnalysisReportDTO(
            id=saved.id,
            room_id=saved.room_id,
            summary=saved.summary,
            content=content_dto,
            created_at=saved.created_at,
        )

    async def get_report(
        self,
        report_id: int,
        *,
        room_id: int,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> Optional[AnalysisReportDTO]:
        """Get a single analysis report by ID."""
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="read_analysis_report",
        )
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            )
            report = await uow.analysis_report_repository.get_by_id(report_id)

        if report is None:
            return None
        if report.room_id != room_id:
            return None

        content_dto = AnalysisContentDTO.model_validate(report.content)
        return AnalysisReportDTO(
            id=report.id,
            room_id=report.room_id,
            summary=report.summary,
            content=content_dto,
            created_at=report.created_at,
        )

    async def list_reports(
        self,
        room_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> list[AnalysisReportSummaryDTO]:
        """List analysis reports for a room (summary only)."""
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="list_analysis_reports",
        )
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            )
            reports = await uow.analysis_report_repository.list_by_room_id(
                room_id, skip=skip, limit=limit
            )

        return [
            AnalysisReportSummaryDTO(
                id=r.id,
                room_id=r.room_id,
                summary=r.summary,
                created_at=r.created_at,
            )
            for r in reports
        ]


class AnalysisReaderService:
    """Read-only service for querying existing analysis reports.

    Unlike AnalysisService, this does NOT require LLM. It still needs the
    PersonaLoader because report reads are room-scoped.
    """

    def __init__(
        self,
        uow_factory: Callable[..., AbstractUnitOfWork],
        persona_loader,
    ) -> None:
        self._uow_factory = uow_factory
        self._persona_loader = persona_loader

    async def get_report(
        self,
        report_id: int,
        *,
        room_id: int,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> Optional[AnalysisReportDTO]:
        """Get a single analysis report by ID."""
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="read_analysis_report",
        )
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            )
            report = await uow.analysis_report_repository.get_by_id(report_id)

        if report is None:
            return None
        if report.room_id != room_id:
            return None

        content_dto = AnalysisContentDTO.model_validate(report.content)
        return AnalysisReportDTO(
            id=report.id,
            room_id=report.room_id,
            summary=report.summary,
            content=content_dto,
            created_at=report.created_at,
        )

    async def list_reports(
        self,
        room_id: int,
        *,
        skip: int = 0,
        limit: int = 50,
        access_scope: StakeholderRoomAccessScope | None,
    ) -> list[AnalysisReportSummaryDTO]:
        """List analysis reports for a room (summary only)."""
        scope = require_stakeholder_room_access_scope(
            access_scope,
            operation="list_analysis_reports",
        )
        async with self._uow_factory(readonly=True) as uow:
            room = await uow.chat_room_repository.get_by_id(room_id)
            require_stakeholder_room_access(
                room,
                room_id=room_id,
                access_scope=scope,
                persona_loader=self._persona_loader,
                action=StakeholderRoomAction.READ,
            )
            reports = await uow.analysis_report_repository.list_by_room_id(
                room_id, skip=skip, limit=limit
            )

        return [
            AnalysisReportSummaryDTO(
                id=r.id,
                room_id=r.room_id,
                summary=r.summary,
                created_at=r.created_at,
            )
            for r in reports
        ]
