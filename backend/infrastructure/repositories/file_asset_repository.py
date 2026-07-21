"""SQLAlchemy-backed repository for file assets."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.common.exceptions import DomainValidationException, FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset import FileAsset, FileAssetRepository
from infrastructure.models.file_asset import FileAssetModel
from infrastructure.repositories.metadata_scope import (
    apply_owned_metadata_scope,
    owned_metadata_scope_condition,
)
import hashlib


class SQLAlchemyFileAssetRepository(FileAssetRepository):
    """Persist file asset aggregates using SQLAlchemy ORM."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, model: FileAssetModel) -> FileAsset:
        return FileAsset(
            id=model.id,
            owner_id=model.owner_id,
            storage_type=model.storage_type,
            bucket=model.bucket,
            region=model.region,
            key=model.key,
            size=model.size,
            etag=model.etag,
            content_type=model.content_type,
            original_filename=model.original_filename,
            kind=model.kind,
            is_public=model.is_public,
            metadata=dict(model.extra_metadata or {}),
            url=model.url,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deleted_at=model.deleted_at,
        )

    @staticmethod
    def _calc_unique_hash(storage_type: str, bucket: Optional[str], key: str) -> str:
        raw = f"{storage_type}|{bucket or ''}|{key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _require_metadata_scope(metadata_scope: OwnedMetadataScope | None) -> OwnedMetadataScope:
        if metadata_scope is None:
            raise DomainValidationException(
                "metadata_scope is required for file asset repository access",
                field="metadata_scope",
                message_key="file_asset.repository.scope.required",
            )
        return metadata_scope

    def _apply_filters(
        self,
        query,
        *,
        owner_id: Optional[int],
        kind: Optional[str],
        status: Optional[str],
        metadata_scope: OwnedMetadataScope,
    ):
        if owner_id is not None:
            query = query.where(FileAssetModel.owner_id == owner_id)
        if kind:
            query = query.where(FileAssetModel.kind == kind)
        if status:
            query = query.where(FileAssetModel.status == status)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        return query

    async def create(self, asset: FileAsset) -> FileAsset:
        model = FileAssetModel(
            owner_id=asset.owner_id,
            storage_type=asset.storage_type,
            bucket=asset.bucket,
            region=asset.region,
            key=asset.key,
            unique_key_hash=self._calc_unique_hash(asset.storage_type, asset.bucket, asset.key),
            size=asset.size,
            etag=asset.etag,
            content_type=asset.content_type,
            original_filename=asset.original_filename,
            kind=asset.kind,
            is_public=asset.is_public,
            extra_metadata=asset.metadata or {},
            url=asset.url,
            status=asset.status,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            deleted_at=asset.deleted_at,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(
        self,
        asset: FileAsset,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAsset:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel).where(FileAssetModel.id == asset.id)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        if model is None:
            raise FileAssetNotFoundException(asset.id)

        model.owner_id = asset.owner_id
        model.storage_type = asset.storage_type
        model.bucket = asset.bucket
        model.region = asset.region
        model.key = asset.key
        model.unique_key_hash = self._calc_unique_hash(asset.storage_type, asset.bucket, asset.key)
        model.size = asset.size
        model.etag = asset.etag
        model.content_type = asset.content_type
        model.original_filename = asset.original_filename
        model.kind = asset.kind
        model.is_public = asset.is_public
        model.extra_metadata = asset.metadata or {}
        model.url = asset.url
        model.status = asset.status
        model.created_at = asset.created_at
        model.updated_at = asset.updated_at
        model.deleted_at = asset.deleted_at

        await self.session.flush()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def delete(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel).where(FileAssetModel.id == asset_id)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        if model is None:
            raise FileAssetNotFoundException(asset_id)
        await self.session.delete(model)
        await self.session.flush()

    async def delete_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel).where(FileAssetModel.key == key)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        if model is None:
            raise FileAssetNotFoundException(key=key)
        await self.session.delete(model)
        await self.session.flush()

    async def get_by_id(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> Optional[FileAsset]:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel).where(FileAssetModel.id == asset_id)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_id_for_maintenance(self, asset_id: int) -> Optional[FileAsset]:
        query = select(FileAssetModel).where(FileAssetModel.id == asset_id)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> Optional[FileAsset]:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel).where(FileAssetModel.key == key)
        query = apply_owned_metadata_scope(query, FileAssetModel.extra_metadata, metadata_scope)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_key_for_maintenance(self, key: str) -> Optional[FileAsset]:
        query = select(FileAssetModel).where(FileAssetModel.key == key)
        result = await self.session.execute(query)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def key_exists_outside_metadata_scope(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> bool:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        visible_condition = owned_metadata_scope_condition(
            FileAssetModel.extra_metadata,
            metadata_scope,
        )
        total_query = (
            select(func.count())
            .select_from(FileAssetModel)
            .where(FileAssetModel.key == key)
        )
        visible_query = (
            select(func.count())
            .select_from(FileAssetModel)
            .where(FileAssetModel.key == key, visible_condition)
        )
        total_result = await self.session.execute(total_query)
        visible_result = await self.session.execute(visible_query)
        return int(total_result.scalar() or 0) > int(visible_result.scalar() or 0)

    async def list(
        self,
        *,
        owner_id: Optional[int] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        metadata_scope: OwnedMetadataScope,
    ) -> list[FileAsset]:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(FileAssetModel)
        query = self._apply_filters(
            query,
            owner_id=owner_id,
            kind=kind,
            status=status,
            metadata_scope=metadata_scope,
        )
        query = query.order_by(
            FileAssetModel.created_at.desc(),
            FileAssetModel.id.desc(),
        )
        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def count(
        self,
        *,
        owner_id: Optional[int] = None,
        kind: Optional[str] = None,
        status: Optional[str] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> int:
        metadata_scope = self._require_metadata_scope(metadata_scope)
        query = select(func.count()).select_from(FileAssetModel)
        query = self._apply_filters(
            query,
            owner_id=owner_id,
            kind=kind,
            status=status,
            metadata_scope=metadata_scope,
        )
        result = await self.session.execute(query)
        return int(result.scalar() or 0)
