"""Message-tree completion adapter for Training Studio sessions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, NoReturn, Protocol

from application.dto import ConversationDTO, MessageDTO_Agent
from application.ports.realtime import redact_realtime_secret_text
from application.services.conversation_service import ConversationApplicationService
from application.services.stakeholder.analysis_service import AnalysisService
from application.services.stakeholder.dto import AnalysisReportDTO
from application.services.stakeholder.room_access_policy import (
    legacy_training_session_room_scope,
)
from application.services.training_studio.session_service import TrainingSessionService
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.conversation.repository import OwnedMetadataScope
from domain.stakeholder.entity import ChatRoom, Message
from domain.stakeholder.competency_entity import CompetencyEvaluation
from domain.training_studio.session import TrainingSession, TrainingSessionStatus
from domain.training_studio.session_repository import TrainingSessionAccessScope


_MESSAGE_TREE_ROOM_PREFIX = "talkwise-conversation:"
_GUIDANCE_MESSAGE_SOURCE = "training_live_guidance"
_MAX_PATH_MESSAGES = 200
_MAX_EVIDENCE_CONTENT_LENGTH = 2_000


class MessageTreeCompletionConflict(ValueError):
    """The requested completion cannot be applied to the current session."""


class MessageTreeReportGenerationError(RuntimeError):
    """Report generation failed after the selected path was validated."""

    def __init__(self, message: str, *, metadata: Mapping[str, object]) -> None:
        super().__init__(message)
        self.metadata = dict(metadata)


class CompetencyEvaluator(Protocol):
    async def evaluate_competency(
        self,
        report_id: int,
    ) -> CompetencyEvaluation | None: ...


@dataclass(frozen=True)
class MessageTreeCompletionResult:
    session: TrainingSession
    report: object | None
    idempotent: bool


class MessageTreeTrainingCompletionService:
    """Project one selected message path into the mature report/growth pipeline."""

    def __init__(
        self,
        *,
        uow_factory: Callable[..., AbstractUnitOfWork],
        session_service: TrainingSessionService,
        conversation_service: ConversationApplicationService,
        analysis_service: AnalysisService,
        growth_service: CompetencyEvaluator,
    ) -> None:
        self._uow_factory = uow_factory
        self._session_service = session_service
        self._conversation_service = conversation_service
        self._analysis_service = analysis_service
        self._growth_service = growth_service

    async def complete(
        self,
        session_id: str,
        *,
        selected_tail_message_id: str,
        session_access_scope: TrainingSessionAccessScope,
        conversation_metadata_scope: OwnedMetadataScope,
    ) -> MessageTreeCompletionResult:
        tail_id = _required_text(selected_tail_message_id, "selected_tail_message_id")
        session = await self._session_service.get_session(
            session_id,
            access_scope=session_access_scope,
        )
        conversation_id = _message_tree_conversation_id(session)
        existing_result = _active_or_idempotent_result(session, tail_id=tail_id)
        if existing_result is not None:
            return existing_result

        conversation = await self._conversation_service.get_conversation(
            conversation_id,
            metadata_scope=conversation_metadata_scope,
        )
        _require_session_binding(conversation, session_id)
        path = await self._conversation_service.get_message_path(
            conversation_id,
            tail_id,
            limit=_MAX_PATH_MESSAGES,
            statuses=["active"],
            metadata_scope=conversation_metadata_scope,
        )
        evaluation_path = _evaluation_messages(path)
        _validate_evaluation_path(evaluation_path, tail_id=tail_id)

        projection_room_id = await self._prepare_projection(
            session,
            conversation,
            evaluation_path,
            conversation_id=conversation_id,
            tail_id=tail_id,
            access_scope=session_access_scope,
        )
        report = await self._generate_report(
            session_id,
            projection_room_id=projection_room_id,
            conversation_id=conversation_id,
            tail_id=tail_id,
            access_scope=session_access_scope,
        )
        evaluation, evaluation_metadata = await self._evaluate_report(report)
        completion_metadata = _completion_ready_metadata(
            report_id=report.id,
            projection_room_id=projection_room_id,
            conversation_id=conversation_id,
            selected_tail_message_id=tail_id,
            path=evaluation_path,
            evaluation=evaluation,
            evaluation_metadata=evaluation_metadata,
        )
        score_id = _optional_text(evaluation.id if evaluation is not None else None)

        return await self._persist_completion(
            session_id,
            report=report,
            score_id=score_id,
            completion_metadata=completion_metadata,
            projection_room_id=projection_room_id,
            conversation_id=conversation_id,
            tail_id=tail_id,
            access_scope=session_access_scope,
        )

    async def _prepare_projection(
        self,
        session: TrainingSession,
        conversation: ConversationDTO,
        path: Sequence[MessageDTO_Agent],
        *,
        conversation_id: int,
        tail_id: str,
        access_scope: TrainingSessionAccessScope,
    ) -> int:
        try:
            return await self._create_evaluation_projection(
                session,
                conversation,
                path,
                access_scope=access_scope,
            )
        except Exception as exc:
            await self._raise_pipeline_error(
                session.session_id,
                exc,
                phase="prepare_evidence",
                conversation_id=conversation_id,
                tail_id=tail_id,
                access_scope=access_scope,
            )

    async def _generate_report(
        self,
        session_id: str,
        *,
        projection_room_id: int,
        conversation_id: int,
        tail_id: str,
        access_scope: TrainingSessionAccessScope,
    ) -> AnalysisReportDTO:
        report_scope = legacy_training_session_room_scope(
            training_session_id=session_id,
            room_id=projection_room_id,
            operation="message_tree_generate_report",
        )
        try:
            return await self._analysis_service.generate_report(
                projection_room_id,
                access_scope=report_scope,
            )
        except Exception as exc:
            await self._raise_pipeline_error(
                session_id,
                exc,
                phase="generate_report",
                conversation_id=conversation_id,
                tail_id=tail_id,
                access_scope=access_scope,
                cleanup_room_id=projection_room_id,
            )

    async def _persist_completion(
        self,
        session_id: str,
        *,
        report: AnalysisReportDTO,
        score_id: str | None,
        completion_metadata: Mapping[str, object],
        projection_room_id: int,
        conversation_id: int,
        tail_id: str,
        access_scope: TrainingSessionAccessScope,
    ) -> MessageTreeCompletionResult:
        try:
            completed = await self._session_service.complete_session(
                session_id,
                report_id=str(report.id),
                score_id=score_id,
                metadata=completion_metadata,
                access_scope=access_scope,
            )
        except Exception as exc:
            await self._delete_projection(projection_room_id)
            current = await self._session_service.get_session(
                session_id,
                access_scope=access_scope,
            )
            idempotent = _completed_result_for_tail(current, tail_id=tail_id)
            if idempotent is not None:
                return idempotent
            await self._raise_pipeline_error(
                session_id,
                exc,
                phase="complete_session",
                conversation_id=conversation_id,
                tail_id=tail_id,
                access_scope=access_scope,
            )
        return MessageTreeCompletionResult(session=completed, report=report, idempotent=False)

    async def _raise_pipeline_error(
        self,
        session_id: str,
        exc: Exception,
        *,
        phase: str,
        conversation_id: int,
        tail_id: str,
        access_scope: TrainingSessionAccessScope,
        cleanup_room_id: int | None = None,
    ) -> NoReturn:
        if cleanup_room_id is not None:
            await self._delete_projection(cleanup_room_id)
        failure_metadata = _completion_failure_metadata(
            exc,
            phase=phase,
            conversation_id=conversation_id,
            selected_tail_message_id=tail_id,
        )
        await self._record_attempt_metadata(
            session_id,
            failure_metadata,
            access_scope=access_scope,
        )
        raise MessageTreeReportGenerationError(
            str(failure_metadata["message"]),
            metadata=failure_metadata,
        ) from exc

    async def _create_evaluation_projection(
        self,
        session: TrainingSession,
        conversation: ConversationDTO,
        path: Sequence[MessageDTO_Agent],
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> int:
        persona_ids = _persona_ids(session, conversation)
        room = ChatRoom(
            id=None,
            name=f"Training evaluation: {session.session_id}",
            type="battle_prep",
            persona_ids=persona_ids,
            scenario_id=_optional_int(
                conversation.metadata.get("scenarioId")
                or conversation.metadata.get("scenario_id")
                or session.task_config.metadata.get("scenario_id")
            ),
            owner_user_id=_optional_text(session.user_id or access_scope.user_id),
            owner_team_id=_optional_text(session.team_id or access_scope.team_id),
        )
        async with self._uow_factory() as uow:
            room_repository = uow.get_repository("chat_room_repository")
            message_repository = uow.get_repository("stakeholder_message_repository")
            if room_repository is None or message_repository is None:
                raise RuntimeError("Evaluation projection repositories are unavailable")
            saved_room = await room_repository.create(room)
            if saved_room.id is None:
                raise RuntimeError("Evaluation projection room did not receive an id")
            last_message_id: int | None = None
            for source_message in path:
                projected = await message_repository.create(
                    _projected_message(
                        saved_room.id,
                        source_message,
                        session=session,
                        persona_ids=persona_ids,
                    )
                )
                last_message_id = projected.id
            if last_message_id is not None:
                await room_repository.update_context_summary(
                    saved_room.id,
                    f"Evaluation projection for {session.session_id}",
                    last_message_id,
                )
            return int(saved_room.id)

    async def _evaluate_report(
        self,
        report: AnalysisReportDTO,
    ) -> tuple[CompetencyEvaluation | None, dict[str, object]]:
        report_id = int(report.id)
        try:
            evaluation = await self._growth_service.evaluate_competency(report_id)
        except Exception as exc:
            return None, {
                "status": "failed",
                "errorType": type(exc).__name__,
                "message": _safe_error_message(exc, fallback="Competency evaluation failed"),
                "retryable": True,
            }
        if evaluation is None:
            return None, {
                "status": "unavailable",
                "message": "Competency evaluation is not configured or produced no result",
                "retryable": True,
            }
        return evaluation, {
            "status": "ready",
            "evaluationId": _optional_text(evaluation.id),
            "overallScore": evaluation.overall_score,
            "retryable": False,
        }

    async def _record_attempt_metadata(
        self,
        session_id: str,
        completion_report: Mapping[str, object],
        *,
        access_scope: TrainingSessionAccessScope,
    ) -> None:
        try:
            await self._session_service.record_session_metadata(
                session_id,
                metadata={"completionReport": dict(completion_report)},
                access_scope=access_scope,
            )
        except Exception:
            # Preserve the original report error; metadata persistence is diagnostic only.
            return

    async def _delete_projection(self, room_id: int) -> None:
        try:
            async with self._uow_factory() as uow:
                room_repository = uow.get_repository("chat_room_repository")
                if room_repository is not None:
                    await room_repository.delete(room_id)
        except Exception:
            return


def message_tree_analysis_room_id(session: TrainingSession) -> int | None:
    report_metadata = _completion_report_metadata(session)
    if report_metadata.get("runtime") != "message_tree":
        return None
    try:
        bound_conversation_id = _message_tree_conversation_id(session)
    except MessageTreeCompletionConflict:
        return None
    evidence = report_metadata.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    metadata_conversation_id = _optional_int(
        report_metadata.get("conversationId") or evidence.get("conversationId")
    )
    if metadata_conversation_id != bound_conversation_id:
        return None
    analysis_room_id = _optional_int(report_metadata.get("analysisRoomId"))
    return analysis_room_id if analysis_room_id and analysis_room_id > 0 else None


def _active_or_idempotent_result(
    session: TrainingSession,
    *,
    tail_id: str,
) -> MessageTreeCompletionResult | None:
    if session.status == TrainingSessionStatus.COMPLETED:
        result = _completed_result_for_tail(session, tail_id=tail_id)
        if result is None:
            raise MessageTreeCompletionConflict(
                "Training session was already completed with a different selected path"
            )
        return result
    if session.status == TrainingSessionStatus.ACTIVE:
        return None
    status_text = (
        session.status.value
        if isinstance(session.status, TrainingSessionStatus)
        else str(session.status)
    )
    raise MessageTreeCompletionConflict(
        f"Training session must be active before completion (current: {status_text})"
    )


def _completed_result_for_tail(
    session: TrainingSession,
    *,
    tail_id: str,
) -> MessageTreeCompletionResult | None:
    if (
        session.status != TrainingSessionStatus.COMPLETED
        or _completed_tail_message_id(session) != tail_id
    ):
        return None
    return MessageTreeCompletionResult(session=session, report=None, idempotent=True)


def message_tree_completion_report_metadata(session: TrainingSession) -> dict[str, object]:
    return dict(_completion_report_metadata(session))


def _message_tree_conversation_id(session: TrainingSession) -> int:
    room_id = _required_text(session.room_id, "room_id")
    if not room_id.startswith(_MESSAGE_TREE_ROOM_PREFIX):
        raise MessageTreeCompletionConflict(
            "Training session is not bound to the message-tree conversation runtime"
        )
    try:
        return int(room_id.removeprefix(_MESSAGE_TREE_ROOM_PREFIX))
    except ValueError as exc:
        raise MessageTreeCompletionConflict(
            "Training session has an invalid message-tree conversation binding"
        ) from exc


def _require_session_binding(conversation: ConversationDTO, session_id: str) -> None:
    bound_session_id = _optional_text(
        conversation.metadata.get("trainingSessionId")
        or conversation.metadata.get("training_session_id")
    )
    if bound_session_id != session_id:
        raise MessageTreeCompletionConflict(
            "Conversation is not bound to the requested training session"
        )


def _evaluation_messages(path: Sequence[MessageDTO_Agent]) -> list[MessageDTO_Agent]:
    return [
        message
        for message in path
        if message.content.strip()
        and (message.metadata or {}).get("source") != _GUIDANCE_MESSAGE_SOURCE
    ]


def _validate_evaluation_path(
    path: Sequence[MessageDTO_Agent],
    *,
    tail_id: str,
) -> None:
    if not path or path[-1].public_id != tail_id:
        raise MessageTreeCompletionConflict(
            "Selected message tail is not an active conversation path"
        )
    participant_messages = [message for message in path if message.role in {"user", "assistant"}]
    if len(participant_messages) < 2 or not any(
        message.role == "user" for message in participant_messages
    ):
        raise MessageTreeCompletionConflict(
            "Selected path does not contain enough participant turns for evaluation"
        )


def _projected_message(
    room_id: int,
    source: MessageDTO_Agent,
    *,
    session: TrainingSession,
    persona_ids: Sequence[str],
) -> Message:
    role = source.role.strip().lower()
    if role == "user":
        sender_type = "user"
        sender_id = _optional_text(session.user_id) or "training_user"
    elif role == "assistant":
        sender_type = "persona"
        sender_id = (
            _optional_text((source.metadata or {}).get("sender_id"))
            or (persona_ids[0] if persona_ids else None)
            or "training_counterpart"
        )
    else:
        sender_type = "system"
        sender_id = "training_system"
    return Message(
        id=None,
        room_id=room_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=source.content,
        timestamp=source.created_at,
        metadata={
            "source": "message_tree_evaluation_projection",
            "sourceConversationId": source.conversation_id,
            "sourceMessageId": source.public_id,
            "sourceParentMessageId": source.parent_message_id,
            "sourceBranchId": source.branch_id,
            "trainingSessionId": session.session_id,
        },
    )


def _completion_ready_metadata(
    *,
    report_id: object,
    projection_room_id: int,
    conversation_id: int,
    selected_tail_message_id: str,
    path: Sequence[MessageDTO_Agent],
    evaluation: object | None,
    evaluation_metadata: Mapping[str, object],
) -> dict[str, object]:
    evidence_path = [_path_evidence(message) for message in path]
    selected_message_ids = [
        message.public_id for message in path if _optional_text(message.public_id)
    ]
    selected_path = {
        "branchId": _optional_text(path[-1].branch_id),
        "tailMessageId": selected_tail_message_id,
        "messageIds": selected_message_ids,
        "purpose": "completion_evaluation_context",
        "source": "server_selected_root_to_tail",
        "replayContextOnly": False,
        "affectsScoring": True,
        "affectsCompletion": True,
    }
    return {
        "completionReport": {
            "status": "ready",
            "phase": "complete",
            "generation": "sync",
            "runtime": "message_tree",
            "reportId": str(report_id),
            "analysisRoomId": projection_room_id,
            "conversationId": str(conversation_id),
            "selectedTailMessageId": selected_tail_message_id,
            "completedWithoutReport": False,
            "evidence": {
                "source": "server_selected_root_to_tail",
                "conversationId": str(conversation_id),
                "selectedMessageIds": selected_message_ids,
                "messageCount": len(path),
            },
            "evaluation": dict(evaluation_metadata),
            "capabilities": {
                "reportRead": True,
                "evaluation": evaluation is not None,
                "backgroundGeneration": False,
                "retry": False,
            },
            "recordedAt": datetime.now(UTC).isoformat(),
        },
        "messageTreeSelection": {
            "provider": "talkwise-conversation",
            "conversationId": str(conversation_id),
            "selectedMessageId": selected_tail_message_id,
            "branchId": _optional_text(path[-1].branch_id),
            "path": evidence_path,
            **selected_path,
        },
        "selectedPath": selected_path,
        "currentBranchTail": {
            "branchId": _optional_text(path[-1].branch_id),
            "messageId": selected_tail_message_id,
        },
    }


def _completion_failure_metadata(
    exc: Exception,
    *,
    phase: str,
    conversation_id: int,
    selected_tail_message_id: str,
) -> dict[str, object]:
    return {
        "status": "failed",
        "phase": phase,
        "runtime": "message_tree",
        "errorType": type(exc).__name__,
        "message": _safe_error_message(exc, fallback="Report generation failed"),
        "retryable": True,
        "completedWithoutReport": False,
        "conversationId": str(conversation_id),
        "selectedTailMessageId": selected_tail_message_id,
        "capabilities": {
            "reportRead": False,
            "evaluation": False,
            "backgroundGeneration": False,
            "retry": True,
        },
        "recordedAt": datetime.now(UTC).isoformat(),
    }


def _path_evidence(message: MessageDTO_Agent) -> dict[str, object]:
    content = message.content
    truncated = len(content) > _MAX_EVIDENCE_CONTENT_LENGTH
    if truncated:
        content = f"{content[:_MAX_EVIDENCE_CONTENT_LENGTH].rstrip()}..."
    return {
        "publicId": message.public_id,
        "role": message.role,
        "content": content,
        "contentTruncated": truncated,
        "branchId": message.branch_id,
        "parentMessageId": message.parent_message_id,
        "createdAt": message.created_at.isoformat(),
    }


def _persona_ids(
    session: TrainingSession,
    conversation: ConversationDTO,
) -> list[str]:
    for value in (
        conversation.metadata.get("personaIds"),
        conversation.metadata.get("persona_ids"),
        session.task_config.metadata.get("persona_ids"),
        session.task_config.metadata.get("personaIds"),
    ):
        values = _text_list(value)
        if values:
            return values
    for value in (
        conversation.metadata.get("personaId"),
        conversation.metadata.get("persona_id"),
        session.task_config.metadata.get("persona_id"),
        session.task_config.metadata.get("personaId"),
    ):
        text = _optional_text(value)
        if text:
            return [text]
    return []


def _completed_tail_message_id(session: TrainingSession) -> str | None:
    report_metadata = _completion_report_metadata(session)
    return _optional_text(report_metadata.get("selectedTailMessageId"))


def _completion_report_metadata(session: TrainingSession) -> Mapping[str, Any]:
    metadata = session.task_config.metadata or {}
    value = metadata.get("completionReport")
    return value if isinstance(value, Mapping) else {}


def _safe_error_message(exc: Exception, *, fallback: str) -> str:
    message = redact_realtime_secret_text(
        str(getattr(exc, "message", None) or str(exc) or fallback).strip()
    )
    if len(message) > 500:
        message = f"{message[:500].rstrip()}..."
    return message or fallback


def _required_text(value: object | None, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise MessageTreeCompletionConflict(f"{field} is required")
    return text


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object | None) -> int | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _text_list(value: object | None) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [text for item in value if (text := _optional_text(item))]
