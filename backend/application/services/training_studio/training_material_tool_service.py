"""Scoped training-material lookup for narrow tool consumers."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Protocol

from pydantic import BaseModel, Field

from application.dto import FileAssetDTO
from domain.common.exceptions import DomainValidationException, FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset.entity import FileAsset

TRAINING_MATERIAL_KIND = "training_material"
TRAINING_MATERIAL_STATUS = "active"

_MAX_LIMIT = 100
_METADATA_STRING_LIMIT = 240
_METADATA_LIST_LIMIT = 8
_METADATA_DICT_LIMIT = 12

_SAFE_METADATA_KEYS = frozenset(
    {
        "createdBy",
        "description",
        "expected_size",
        "filename",
        "language",
        "labels",
        "materialType",
        "material_type",
        "name",
        "personaId",
        "persona_id",
        "scenarioId",
        "scenario_id",
        "source",
        "sourceType",
        "sourceUrl",
        "stakeholderId",
        "stakeholder_id",
        "summary",
        "tags",
        "title",
        "trainingGoalId",
        "training_goal_id",
        "upload_source",
        "uploadedBy",
        "usageScope",
        "usage_scope",
    }
)

_BLOCKED_METADATA_KEY_PARTS = (
    "api_key",
    "apikey",
    "auth",
    "body",
    "chunk",
    "content",
    "embedding",
    "owner",
    "password",
    "raw",
    "secret",
    "team",
    "text",
    "token",
    "transcript",
)


class TrainingMaterialAssetSummaryDTO(BaseModel):
    """File asset fields that are safe for training tool planning."""

    id: int
    key: str
    name: str
    content_type: str | None = None
    metadata_excerpt: dict[str, Any] = Field(default_factory=dict)


class TrainingMaterialAssetListDTO(BaseModel):
    """Paged training material summaries."""

    items: list[TrainingMaterialAssetSummaryDTO]
    total: int
    skip: int
    limit: int


class TrainingMaterialFileAssetReader(Protocol):
    """Subset of FileAssetApplicationService used by this narrow consumer."""

    async def list_assets(
        self,
        *,
        owner_id: int | None,
        kind: str | None,
        status: str | None,
        skip: int,
        limit: int,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> tuple[list[FileAssetDTO], int]: ...

    async def get_asset(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> FileAssetDTO: ...

    async def get_asset_by_key_raw(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope | None = None,
    ) -> FileAsset: ...


class TrainingMaterialToolConsumerService:
    """Permission-safe entry point for persona/material tool consumers.

    The service never reads storage object contents. It only uses FileAsset
    metadata methods that already enforce OwnedMetadataScope at repository level.
    """

    def __init__(self, file_assets: TrainingMaterialFileAssetReader) -> None:
        self._file_assets = file_assets

    async def list_materials(
        self,
        *,
        metadata_scope: OwnedMetadataScope | None,
        skip: int = 0,
        limit: int = 20,
    ) -> TrainingMaterialAssetListDTO:
        scope = _require_metadata_scope(metadata_scope)
        safe_skip, safe_limit = _normalize_pagination(skip=skip, limit=limit)

        items, total = await self._file_assets.list_assets(
            owner_id=None,
            kind=TRAINING_MATERIAL_KIND,
            status=TRAINING_MATERIAL_STATUS,
            skip=safe_skip,
            limit=safe_limit,
            metadata_scope=scope,
        )
        return TrainingMaterialAssetListDTO(
            items=[_to_training_material_summary(item) for item in items],
            total=total,
            skip=safe_skip,
            limit=safe_limit,
        )

    async def get_material(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> TrainingMaterialAssetSummaryDTO:
        scope = _require_metadata_scope(metadata_scope)
        asset = await self._file_assets.get_asset(asset_id, metadata_scope=scope)
        _require_training_material(asset, asset_id=asset_id)
        return _to_training_material_summary(asset)

    async def get_material_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope | None,
    ) -> TrainingMaterialAssetSummaryDTO:
        scope = _require_metadata_scope(metadata_scope)
        asset = await self._file_assets.get_asset_by_key_raw(key, metadata_scope=scope)
        _require_training_material(asset, key=key)
        return _to_training_material_summary(asset)


def _require_metadata_scope(scope: OwnedMetadataScope | None) -> OwnedMetadataScope:
    if scope is None:
        raise DomainValidationException(
            "metadata_scope is required for training material access",
            field="metadata_scope",
            message_key="training_material.scope.required",
        )
    return scope


def _normalize_pagination(*, skip: int, limit: int) -> tuple[int, int]:
    if skip < 0:
        raise DomainValidationException(
            "skip must be greater than or equal to 0",
            field="skip",
            details={"skip": skip},
            message_key="pagination.skip.invalid",
        )
    if limit < 1:
        raise DomainValidationException(
            "limit must be greater than or equal to 1",
            field="limit",
            details={"limit": limit},
            message_key="pagination.limit.invalid",
        )
    return skip, min(limit, _MAX_LIMIT)


def _require_training_material(
    asset: FileAssetDTO | FileAsset,
    *,
    asset_id: int | None = None,
    key: str | None = None,
) -> None:
    if getattr(asset, "kind", None) != TRAINING_MATERIAL_KIND:
        raise FileAssetNotFoundException(asset_id, key=key)
    if getattr(asset, "status", None) != TRAINING_MATERIAL_STATUS:
        raise FileAssetNotFoundException(asset_id, key=key)


def _to_training_material_summary(
    asset: FileAssetDTO | FileAsset,
) -> TrainingMaterialAssetSummaryDTO:
    return TrainingMaterialAssetSummaryDTO(
        id=int(getattr(asset, "id") or 0),
        key=str(getattr(asset, "key")),
        name=_asset_name(asset),
        content_type=getattr(asset, "content_type", None),
        metadata_excerpt=_metadata_excerpt(getattr(asset, "metadata", None)),
    )


def _asset_name(asset: FileAssetDTO | FileAsset) -> str:
    filename = getattr(asset, "original_filename", None)
    if isinstance(filename, str) and filename.strip():
        return filename.strip()

    metadata = getattr(asset, "metadata", None)
    if isinstance(metadata, dict):
        for key in ("title", "name", "filename"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    key = str(getattr(asset, "key", "") or "")
    tail = PurePosixPath(key).name
    return tail or f"file-{int(getattr(asset, 'id') or 0)}"


def _metadata_excerpt(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    excerpt: dict[str, Any] = {}
    for key in sorted(_SAFE_METADATA_KEYS):
        if key not in metadata or _is_blocked_metadata_key(key):
            continue
        value = _excerpt_value(metadata[key], depth=0)
        if value is not None:
            excerpt[key] = value
    return excerpt


def _excerpt_value(value: Any, *, depth: int) -> Any:
    if value is None:
        return None
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if len(text) > _METADATA_STRING_LIMIT:
            return f"{text[:_METADATA_STRING_LIMIT]}..."
        return text
    if isinstance(value, list):
        items = []
        for item in value[:_METADATA_LIST_LIMIT]:
            excerpt = _excerpt_value(item, depth=depth + 1)
            if excerpt is not None:
                items.append(excerpt)
        return items
    if isinstance(value, dict) and depth < 1:
        nested: dict[str, Any] = {}
        for nested_key, nested_value in list(value.items())[:_METADATA_DICT_LIMIT]:
            if not isinstance(nested_key, str) or _is_blocked_metadata_key(nested_key):
                continue
            excerpt = _excerpt_value(nested_value, depth=depth + 1)
            if excerpt is not None:
                nested[nested_key] = excerpt
        return nested
    return None


def _is_blocked_metadata_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return any(part in normalized for part in _BLOCKED_METADATA_KEY_PARTS)
