# input: ChatApplicationService 依赖注入
# output: SSE 流式聊天端点 + 同步聊天端点
# owner: unknown
# pos: 表示层路由 - 聊天 API（SSE 流式 + 同步）；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""Chat routes with SSE streaming support."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from api.conversation_scope import owned_metadata_scope_for_current_user
from api.dependencies import (
    CurrentUser,
    get_chat_service,
    get_conversation_service,
    require_system_roles,
)
from application.dto import ChatRequestDTO
from application.services.chat_service import ChatApplicationService
from application.services.conversation_service import ConversationApplicationService
from core.i18n import t
from core.response import Response as ApiResponse, success_response

# TODO: Add authentication dependency when user/auth module is implemented.
# The chat endpoint invokes paid LLM API calls and MUST be auth-gated
# before exposing to non-internal traffic.
router = APIRouter(tags=["聊天"])


_chat_user = require_system_roles("admin", "leader", "staff")


@router.post(
    "/conversations/{conversation_id}/chat",
    summary="发送消息（支持 SSE 流式）",
)
async def chat(
    conversation_id: int,
    payload: ChatRequestDTO,
    service: ChatApplicationService = Depends(get_chat_service),
    conversation_service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_chat_user),
):
    await conversation_service.get_conversation(
        conversation_id,
        metadata_scope=owned_metadata_scope_for_current_user(
            current_user,
            allow_unscoped=True,
        ),
    )

    if payload.stream:
        return StreamingResponse(
            service.send_message_stream(conversation_id, payload),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    result = await service.send_message_sync(conversation_id, payload)
    return success_response(result, message=t("ok"))
