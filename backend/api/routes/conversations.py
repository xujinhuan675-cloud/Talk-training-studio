# input: ConversationApplicationService dependency injection
# output: conversation, message, search, run, and AgentConfig HTTP endpoints
# owner: unknown
# pos: API routes - text conversation management and run/history query boundary; update this header and folder docs when changed
"""Conversation and AgentConfig CRUD routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.conversation_scope import (
    conversation_create_payload_for_user,
    conversation_metadata_for_current_user,
    require_conversation_access,
    user_can_access_conversation,
)
from api.dependencies import CurrentUser, get_conversation_service, require_system_roles
from application.dto import (
    AgentConfigDTO,
    ConversationDTO,
    CreateAgentConfigDTO,
    CreateConversationDTO,
    EditMessageDTO,
    ForkConversationDTO,
    ForkConversationResultDTO,
    MessageActionDTO,
    MessageActionResultDTO,
    MessageLocationDTO,
    MessageDTO_Agent,
    MessageSearchResultDTO,
    RetryMessageDTO,
    RunDTO,
    UpdateAgentConfigDTO,
    UpdateConversationDTO,
)
from application.services.conversation_service import ConversationApplicationService
from core.config import settings
from core.i18n import t
from core.response import PaginatedData
from core.response import Response as ApiResponse
from core.response import paginated_response, success_response

router = APIRouter(tags=["Conversations"])
_conversation_user = require_system_roles("admin", "leader", "staff")
_agent_config_user = require_system_roles("admin", "leader", "staff")


async def _get_accessible_conversation(
    service: ConversationApplicationService,
    conversation_id: int,
    current_user: CurrentUser,
) -> ConversationDTO:
    conv = await service.get_conversation(conversation_id)
    return require_conversation_access(conv, current_user)


# Conversations


@router.post(
    "/conversations",
    summary="Create conversation",
    response_model=ApiResponse[ConversationDTO],
)
async def create_conversation(
    payload: CreateConversationDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    payload = conversation_create_payload_for_user(payload, current_user)
    conv = await service.create_conversation(payload)
    return success_response(conv, message=t("ok"))


@router.get(
    "/conversations",
    summary="List conversations",
    response_model=ApiResponse[PaginatedData[ConversationDTO]],
)
async def list_conversations(
    page: int = Query(1, ge=1),
    size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status: Optional[str] = Query(default=None),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    skip = (page - 1) * size
    items, total = await service.list_conversations(status=status, skip=skip, limit=size)
    if not current_user.is_admin:
        items = [item for item in items if user_can_access_conversation(item, current_user)]
        total = len(items)
    return paginated_response(items=items, total=total, page=page, size=size)


@router.get(
    "/conversations/{conversation_id}",
    summary="Get conversation",
    response_model=ApiResponse[ConversationDTO],
)
async def get_conversation(
    conversation_id: int,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    conv = await service.get_conversation(conversation_id)
    require_conversation_access(conv, current_user)
    return success_response(conv, message=t("ok"))


@router.patch(
    "/conversations/{conversation_id}",
    summary="Update conversation",
    response_model=ApiResponse[ConversationDTO],
)
async def update_conversation(
    conversation_id: int,
    payload: UpdateConversationDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    conv = await service.update_conversation(conversation_id, payload)
    return success_response(conv, message=t("ok"))


@router.delete(
    "/conversations/{conversation_id}",
    summary="Soft delete conversation",
    response_model=ApiResponse[ConversationDTO],
)
async def delete_conversation(
    conversation_id: int,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    conv = await service.delete_conversation(conversation_id)
    return success_response(conv, message=t("ok"))


@router.get(
    "/conversations/{conversation_id}/messages",
    summary="List conversation messages",
    response_model=ApiResponse[PaginatedData[MessageDTO_Agent]],
)
async def list_messages(
    conversation_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(default=100, ge=1, le=500),
    branch_id: Optional[str] = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    skip = (page - 1) * size
    items, total = await service.list_messages(
        conversation_id,
        skip=skip,
        limit=size,
        branch_id=branch_id,
        statuses=statuses,
        include_deleted=include_deleted,
    )
    return paginated_response(items=items, total=total, page=page, size=size)


@router.get(
    "/conversations/{conversation_id}/messages/search",
    summary="Search conversation messages",
    response_model=ApiResponse[list[MessageSearchResultDTO]],
)
async def search_messages(
    conversation_id: int,
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    branch_id: Optional[str] = Query(default=None),
    roles: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    provider: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    include_path: bool = Query(default=True),
    context_before: int = Query(1, ge=0, le=20),
    context_after: int = Query(1, ge=0, le=20),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    items = await service.search_messages(
        conversation_id,
        q,
        skip=skip,
        limit=limit,
        branch_id=branch_id,
        roles=roles,
        statuses=statuses,
        provider=provider,
        model=model,
        include_path=include_path,
        context_before=context_before,
        context_after=context_after,
    )
    return success_response(items, message=t("ok"))


@router.post(
    "/conversations/{conversation_id}/messages/{message_public_id}/actions",
    summary="Apply controlled message tree action",
    response_model=ApiResponse[MessageActionResultDTO],
)
async def apply_message_action(
    conversation_id: int,
    message_public_id: str,
    payload: MessageActionDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    item = await service.apply_message_action(conversation_id, message_public_id, payload)
    return success_response(item, message=t("ok"))


@router.get(
    "/conversations/{conversation_id}/messages/{message_public_id}/path",
    summary="Message tree path",
    response_model=ApiResponse[list[MessageDTO_Agent]],
)
async def get_message_path(
    conversation_id: int,
    message_public_id: str,
    limit: int = Query(200, ge=1, le=500),
    include_deleted: bool = Query(default=False),
    statuses: list[str] | None = Query(default=None),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    items = await service.get_message_path(
        conversation_id,
        message_public_id,
        limit=limit,
        include_deleted=include_deleted,
        statuses=statuses,
    )
    return success_response(items, message=t("ok"))


@router.get(
    "/conversations/{conversation_id}/messages/{message_public_id}/locate",
    summary="Locate a conversation message in its branch",
    response_model=ApiResponse[MessageLocationDTO],
)
async def locate_message(
    conversation_id: int,
    message_public_id: str,
    before: int = Query(2, ge=0, le=50),
    after: int = Query(2, ge=0, le=50),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    item = await service.locate_message(
        conversation_id,
        message_public_id,
        before=before,
        after=after,
    )
    return success_response(item, message=t("ok"))


@router.get(
    "/conversations/{conversation_id}/messages/{message_public_id}/children",
    summary="Message tree children",
    response_model=ApiResponse[list[MessageDTO_Agent]],
)
async def list_message_children(
    conversation_id: int,
    message_public_id: str,
    statuses: list[str] | None = Query(default=None),
    include_deleted: bool = Query(default=False),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    items = await service.list_message_children(
        conversation_id,
        message_public_id,
        statuses=statuses,
        include_deleted=include_deleted,
    )
    return success_response(items, message=t("ok"))


@router.post(
    "/conversations/{conversation_id}/messages/{message_public_id}/fork",
    summary="Fork conversation from message",
    response_model=ApiResponse[ForkConversationResultDTO],
)
async def fork_conversation(
    conversation_id: int,
    message_public_id: str,
    payload: ForkConversationDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    source = await _get_accessible_conversation(service, conversation_id, current_user)
    payload = payload.model_copy(
        update={
            "metadata": conversation_metadata_for_current_user(
                payload.metadata,
                current_user,
                source_metadata=source.metadata,
            ),
        },
    )
    item = await service.fork_conversation(conversation_id, message_public_id, payload)
    return success_response(item, message=t("ok"))


@router.post(
    "/conversations/{conversation_id}/messages/{message_public_id}/edit",
    summary="Create edited message branch",
    response_model=ApiResponse[MessageDTO_Agent],
)
async def edit_message(
    conversation_id: int,
    message_public_id: str,
    payload: EditMessageDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    item = await service.edit_message(conversation_id, message_public_id, payload)
    return success_response(item, message=t("ok"))


@router.post(
    "/conversations/{conversation_id}/messages/{message_public_id}/retry",
    summary="Create retry message branch",
    response_model=ApiResponse[MessageDTO_Agent],
)
async def retry_message(
    conversation_id: int,
    message_public_id: str,
    payload: RetryMessageDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    item = await service.retry_message(conversation_id, message_public_id, payload)
    return success_response(item, message=t("ok"))


@router.get(
    "/conversations/{conversation_id}/runs",
    summary="List runs",
    response_model=ApiResponse[list[RunDTO]],
)
async def list_runs(
    conversation_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    provider: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    trigger_message_id: Optional[str] = Query(default=None),
    service: ConversationApplicationService = Depends(get_conversation_service),
    current_user: CurrentUser = Depends(_conversation_user),
):
    await _get_accessible_conversation(service, conversation_id, current_user)
    items = await service.list_runs(
        conversation_id,
        skip=skip,
        limit=limit,
        provider=provider,
        status=status,
        trigger_message_id=trigger_message_id,
    )
    return success_response(items, message=t("ok"))


# Agent Configs


@router.post(
    "/agent-configs",
    summary="Create agent config",
    response_model=ApiResponse[AgentConfigDTO],
)
async def create_agent_config(
    payload: CreateAgentConfigDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    _current_user: CurrentUser = Depends(_agent_config_user),
):
    config = await service.create_agent_config(payload)
    return success_response(config, message=t("ok"))


@router.get(
    "/agent-configs",
    summary="List agent configs",
    response_model=ApiResponse[PaginatedData[AgentConfigDTO]],
)
async def list_agent_configs(
    page: int = Query(1, ge=1),
    size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    service: ConversationApplicationService = Depends(get_conversation_service),
    _current_user: CurrentUser = Depends(_agent_config_user),
):
    skip = (page - 1) * size
    items, total = await service.list_agent_configs(skip=skip, limit=size)
    return paginated_response(items=items, total=total, page=page, size=size)


@router.get(
    "/agent-configs/{config_id}",
    summary="Get agent config",
    response_model=ApiResponse[AgentConfigDTO],
)
async def get_agent_config(
    config_id: int,
    service: ConversationApplicationService = Depends(get_conversation_service),
    _current_user: CurrentUser = Depends(_agent_config_user),
):
    config = await service.get_agent_config(config_id)
    return success_response(config, message=t("ok"))


@router.patch(
    "/agent-configs/{config_id}",
    summary="Update agent config",
    response_model=ApiResponse[AgentConfigDTO],
)
async def update_agent_config(
    config_id: int,
    payload: UpdateAgentConfigDTO,
    service: ConversationApplicationService = Depends(get_conversation_service),
    _current_user: CurrentUser = Depends(_agent_config_user),
):
    config = await service.update_agent_config(config_id, payload)
    return success_response(config, message=t("ok"))


@router.delete(
    "/agent-configs/{config_id}",
    summary="Delete agent config",
    response_model=ApiResponse[dict],
)
async def delete_agent_config(
    config_id: int,
    service: ConversationApplicationService = Depends(get_conversation_service),
    _current_user: CurrentUser = Depends(_agent_config_user),
):
    await service.delete_agent_config(config_id)
    return success_response({"deleted": True}, message=t("ok"))
