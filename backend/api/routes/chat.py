# input: ChatApplicationService 依赖注入
# output: SSE 流式聊天端点 + 同步聊天端点
# owner: unknown
# pos: 表示层路由 - 聊天 API（SSE 流式 + 同步）；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Chat routes with SSE streaming support."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from api.conversation_scope import owned_metadata_scope_for_current_user
from api.dependencies import (
    CurrentUser,
    get_chat_service,
    get_conversation_service,
    require_system_roles,
    training_scope_for,
)
from application.dto import ChatRequestDTO
from application.services.chat_service import ChatApplicationService
from application.services.conversation_service import ConversationApplicationService
from application.services.training_studio.session_service import TrainingSessionService
from core.i18n import t
from core.response import Response as ApiResponse, success_response
from domain.training_studio.session_repository import TrainingSessionAccessScope
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork

# TODO: Add authentication dependency when user/auth module is implemented.
# The chat endpoint invokes paid LLM API calls and MUST be auth-gated
# before exposing to non-internal traffic.
router = APIRouter(tags=["聊天"])


logger = logging.getLogger(__name__)
_chat_user = require_system_roles("admin", "staff")
_training_session_service = TrainingSessionService(uow_factory=SQLAlchemyUnitOfWork)


def get_chat_training_session_service() -> TrainingSessionService:
    return _training_session_service


def _training_access_scope(current_user: CurrentUser) -> TrainingSessionAccessScope:
    scope = training_scope_for(current_user)
    return TrainingSessionAccessScope(
        user_id=scope.user_id,
        team_id=scope.team_id,
        include_team_scope=current_user.can_manage_team,
    )


def _training_session_id_from_metadata(metadata: object) -> str | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("trainingSessionId") or metadata.get("training_session_id")
    text = str(value or "").strip()
    return text or None


@router.post(
    "/conversations/{conversation_id}/chat",
    summary="发送消息（支持 SSE 流式）",
)
async def chat(
    conversation_id: int,
    payload: ChatRequestDTO,
    service: ChatApplicationService = Depends(get_chat_service),
    conversation_service: ConversationApplicationService = Depends(get_conversation_service),
    training_session_service: TrainingSessionService = Depends(
        get_chat_training_session_service
    ),
    current_user: CurrentUser = Depends(_chat_user),
):
    metadata_scope = owned_metadata_scope_for_current_user(
        current_user,
    )
    conversation = await conversation_service.get_conversation(
        conversation_id,
        metadata_scope=metadata_scope,
    )

    training_session_id = _training_session_id_from_metadata(conversation.metadata)
    training_scope = _training_access_scope(current_user)
    if training_session_id:
        try:
            await training_session_service.guard_before_finalized_learner_turn(
                training_session_id,
                access_scope=training_scope,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def record_training_turn(_message) -> None:
        if not training_session_id:
            return
        try:
            await training_session_service.record_finalized_learner_turn(
                training_session_id,
                access_scope=training_scope,
            )
        except Exception:
            # The chat message is already committed. Preserve the conversation
            # while surfacing a failed progress update in server diagnostics.
            logger.exception(
                "Failed to record learner progress for training session %s",
                training_session_id,
            )

    if payload.stream:
        return StreamingResponse(
            service.send_message_stream(
                conversation_id,
                payload,
                metadata_scope=metadata_scope,
                on_user_message_persisted=record_training_turn,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await service.send_message_sync(
        conversation_id,
        payload,
        metadata_scope=metadata_scope,
        on_user_message_persisted=record_training_turn,
    )
    return success_response(result, message=t("ok"))
