"""SQLAlchemy helpers for owner/team metadata visibility filters."""

from __future__ import annotations

from sqlalchemy import and_, false, func, or_

from domain.conversation.repository import OwnedMetadataScope

_OWNER_USER_PATHS = (
    ("authScope", "userId"),
    ("authScope", "user_id"),
    ("ownerUserId",),
    ("owner_user_id",),
    ("createdByUserId",),
    ("created_by_user_id",),
)
_OWNER_TEAM_PATHS = (
    ("authScope", "teamId"),
    ("authScope", "team_id"),
    ("teamId",),
    ("team_id",),
    ("ownerTeamId",),
    ("owner_team_id",),
)


def apply_owned_metadata_scope(query, metadata_column, scope: OwnedMetadataScope | None):
    if scope is None:
        return query
    return query.where(owned_metadata_scope_condition(metadata_column, scope))


def owned_metadata_scope_condition(metadata_column, scope: OwnedMetadataScope):
    owner_user = _first_json_text(metadata_column, _OWNER_USER_PATHS)
    owner_team = _first_json_text(metadata_column, _OWNER_TEAM_PATHS)
    owner_user_missing = owner_user.is_(None)
    owner_team_missing = owner_team.is_(None)

    user_id = (scope.user_id or "").strip()
    team_id = (scope.team_id or "").strip()
    conditions = []
    if user_id:
        conditions.append(owner_user == user_id)
    if team_id:
        team_match = owner_team == team_id
        if scope.include_team_scope:
            conditions.append(team_match)
        else:
            conditions.append(and_(owner_user_missing, team_match))
    if scope.allow_unscoped:
        conditions.append(and_(owner_user_missing, owner_team_missing))
    if not conditions:
        return false()
    return or_(*conditions)


def _first_json_text(metadata_column, paths: tuple[tuple[str, ...], ...]):
    return func.coalesce(*(_json_text(metadata_column, *path) for path in paths))


def _json_text(metadata_column, *path: str):
    value = metadata_column
    for key in path:
        value = value[key]
    return func.nullif(func.trim(value.as_string()), "")
