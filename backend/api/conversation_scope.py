"""Conversation ownership helpers for route-level access checks."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from api.dependencies import CurrentUser
from application.dto import ConversationDTO, CreateConversationDTO


_OWNER_USER_KEYS = ("ownerUserId", "owner_user_id", "createdByUserId", "created_by_user_id")
_OWNER_TEAM_KEYS = ("teamId", "team_id", "ownerTeamId", "owner_team_id")


def _as_mapping(value: object | None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metadata_text(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _conversation_owner_user_id(metadata: dict[str, Any]) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "userId", "user_id") or _metadata_text(metadata, *_OWNER_USER_KEYS)


def _conversation_owner_team_id(metadata: dict[str, Any]) -> str | None:
    scope = _as_mapping(metadata.get("authScope"))
    return _metadata_text(scope, "teamId", "team_id") or _metadata_text(metadata, *_OWNER_TEAM_KEYS)


def conversation_metadata_for_current_user(
    metadata: dict[str, Any] | None,
    current_user: CurrentUser,
    *,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return metadata with immutable owner/team fields set for route-created conversations."""

    source = _as_mapping(source_metadata)
    next_metadata: dict[str, Any] = dict(metadata or {})
    owner_user_id = _conversation_owner_user_id(source) or current_user.user_id
    owner_team_id = _conversation_owner_team_id(source) or current_user.team_id
    next_metadata["ownerUserId"] = owner_user_id
    if owner_team_id:
        next_metadata["teamId"] = owner_team_id
    next_metadata["authScope"] = {
        **_as_mapping(next_metadata.get("authScope")),
        "userId": owner_user_id,
        "teamId": owner_team_id,
    }
    return next_metadata


def conversation_create_payload_for_user(
    payload: CreateConversationDTO,
    current_user: CurrentUser,
) -> CreateConversationDTO:
    return payload.model_copy(
        update={
            "metadata": conversation_metadata_for_current_user(payload.metadata, current_user),
        },
    )


def user_can_access_conversation(conversation: ConversationDTO, current_user: CurrentUser) -> bool:
    if current_user.is_admin:
        return True

    metadata = _as_mapping(conversation.metadata)
    owner_user_id = _conversation_owner_user_id(metadata)
    owner_team_id = _conversation_owner_team_id(metadata)

    if not owner_user_id and not owner_team_id:
        return True
    if owner_user_id and owner_user_id == current_user.user_id:
        return True
    if current_user.is_leader and owner_team_id and owner_team_id == current_user.team_id:
        return True
    if not owner_user_id and owner_team_id and owner_team_id == current_user.team_id:
        return True
    return False


def require_conversation_access(
    conversation: ConversationDTO,
    current_user: CurrentUser,
) -> ConversationDTO:
    if not user_can_access_conversation(conversation, current_user):
        raise HTTPException(status_code=403, detail="Conversation is outside current user scope")
    return conversation
