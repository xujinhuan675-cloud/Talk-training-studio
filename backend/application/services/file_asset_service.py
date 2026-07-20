"""Application layer orchestration for file asset lifecycle (application/services)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional, Tuple

from domain.file_asset import FileAsset
from domain.common.unit_of_work import AbstractUnitOfWork
from domain.common.exceptions import (
    FileAssetNotFoundException,
    FileAssetAlreadyDeletedException,
    DomainValidationException,
)
from application.dto import (
    FileAssetDTO,
    FileAssetSummaryDTO,
    StorageUploadResponseDTO,
)
from application.ports.storage import StoragePort
from application.ports.storage import PresignedURL, StorageInfo
from application.utils.storage import build_storage_key, guess_content_type
from core.config import settings
from domain.common.exceptions import (
    UnsupportedMimeTypeException,
    FileTooLargeException,
    InvalidFileNameException,
)
from domain.conversation.repository import OwnedMetadataScope
from os.path import splitext


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize_filename_for_header(filename: Optional[str], *, fallback: str) -> str:
    if not filename:
        return fallback
    cleaned = filename.replace("\r", " ").replace("\n", " ").strip()
    cleaned = cleaned.replace('"', "")
    return cleaned or fallback


def _build_content_disposition(mode: str, filename: Optional[str], *, fallback: str) -> str:
    safe = _sanitize_filename_for_header(filename, fallback=fallback)
    return f'{mode}; filename="{safe}"'


def _user_id_for_key(user_id: Optional[int]) -> Optional[str]:
    return str(user_id) if user_id is not None else None


_ACL_METADATA_KEYS = {
    "authScope",
    "ownerUserId",
    "owner_user_id",
    "createdByUserId",
    "created_by_user_id",
    "teamId",
    "team_id",
    "ownerTeamId",
    "owner_team_id",
}


def _require_metadata_scope(
    scope: OwnedMetadataScope | None,
    *,
    operation: str,
) -> OwnedMetadataScope:
    if scope is None:
        raise DomainValidationException(
            "metadata_scope is required for file asset access",
            field="metadata_scope",
            details={"operation": operation},
            message_key="file_asset.scope.required",
        )
    if scope.allow_unscoped:
        raise DomainValidationException(
            "allow_unscoped metadata_scope is not allowed for file asset access",
            field="metadata_scope",
            details={"operation": operation},
            message_key="file_asset.scope.unscoped_forbidden",
        )
    return scope


def _merge_metadata_preserving_acl(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(incoming or {}).items():
        if key not in _ACL_METADATA_KEYS:
            merged[key] = value
    for key in _ACL_METADATA_KEYS:
        if existing and key in existing:
            merged[key] = existing[key]
    return merged


def _metadata_with_scope_acl(
    incoming: dict[str, Any] | None,
    scope: OwnedMetadataScope,
) -> dict[str, Any]:
    metadata = {
        key: value
        for key, value in dict(incoming or {}).items()
        if key not in _ACL_METADATA_KEYS
    }
    auth_scope: dict[str, str] = {"userId": scope.user_id}
    if scope.team_id:
        metadata["teamId"] = scope.team_id
        auth_scope["teamId"] = scope.team_id
    metadata["ownerUserId"] = scope.user_id
    metadata["authScope"] = auth_scope
    return metadata


def _limit_stream(
    stream: AsyncIterator[bytes],
    *,
    max_bytes: int,
) -> AsyncIterator[bytes]:
    async def _gen() -> AsyncIterator[bytes]:
        seen = 0
        async for chunk in stream:
            if not chunk:
                continue
            seen += len(chunk)
            if max_bytes and seen > max_bytes:
                raise FileTooLargeException(size=seen, max_size=max_bytes)
            yield chunk

    return _gen()


async def _key_exists_outside_metadata_scope(
    repo: Any,
    *,
    key: str,
    metadata_scope: OwnedMetadataScope,
) -> bool:
    checker = getattr(repo, "key_exists_outside_metadata_scope", None)
    if not callable(checker):
        raise RuntimeError(
            "File asset repository must expose key_exists_outside_metadata_scope"
        )
    return bool(await checker(key, metadata_scope=metadata_scope))


class FileAssetApplicationService:
    """High-level file asset workflows bridging API and domain layers."""

    def __init__(
        self, uow_factory: Callable[..., AbstractUnitOfWork], storage: StoragePort | None = None
    ):
        self._uow_factory = uow_factory
        self._storage = storage

    # ------------------------------------------------------------------
    # DTO helpers
    # ------------------------------------------------------------------
    def _to_dto(self, asset: FileAsset) -> FileAssetDTO:
        return FileAssetDTO.model_validate(asset)

    def _to_summary(self, asset: FileAsset) -> FileAssetSummaryDTO:
        return FileAssetSummaryDTO(
            id=asset.id or 0,
            key=asset.key,
            status=asset.status,
            original_filename=asset.original_filename,
            content_type=asset.content_type,
            etag=asset.etag,
            size=asset.size,
            url=asset.url,
        )

    # ------------------------------------------------------------------
    # Workflow operations
    # ------------------------------------------------------------------
    async def create_pending_asset(
        self,
        *,
        owner_id: Optional[int],
        storage_type: str,
        bucket: Optional[str],
        region: Optional[str],
        key: str,
        original_filename: Optional[str],
        content_type: Optional[str],
        kind: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetSummaryDTO:
        scope = _require_metadata_scope(metadata_scope, operation="create_pending_asset")
        now = _utcnow()
        asset = FileAsset(
            id=None,
            owner_id=owner_id,
            storage_type=storage_type,
            bucket=bucket,
            region=region,
            key=key,
            size=0,
            etag=None,
            content_type=content_type,
            original_filename=original_filename,
            kind=kind,
            is_public=False,
            url=None,
            status="pending",
            created_at=now,
            updated_at=now,
            deleted_at=None,
            metadata=_metadata_with_scope_acl(metadata, scope),
        )
        async with self._uow_factory() as uow:
            created = await uow.file_asset_repository.create(asset)
            return self._to_summary(created)

    async def mark_asset_active(
        self,
        *,
        asset_id: Optional[int] = None,
        key: Optional[str] = None,
        size: Optional[int] = None,
        etag: Optional[str] = None,
        content_type: Optional[str] = None,
        url: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetDTO:
        scope = _require_metadata_scope(metadata_scope, operation="mark_asset_active")
        if asset_id is None and not key:
            raise FileAssetNotFoundException()

        async with self._uow_factory() as uow:
            repo = uow.file_asset_repository
            asset: Optional[FileAsset] = None
            if asset_id is not None:
                asset = await repo.get_by_id(asset_id, metadata_scope=scope)
            if asset is None and key:
                asset = await repo.get_by_key(key, metadata_scope=scope)
            if asset is None:
                raise FileAssetNotFoundException(asset_id, key=key)

            asset.update_object_metadata(
                size=size,
                etag=etag,
                content_type=content_type,
                url=url if url is not None else asset.url,
                metadata=(
                    _merge_metadata_preserving_acl(asset.metadata, metadata)
                    if metadata is not None
                    else asset.metadata
                ),
            )
            asset.mark_active()
            updated = await repo.update(asset, metadata_scope=scope)
            # 显式提交，确保在作用域内完成持久化
            await uow.commit()
            return self._to_dto(updated)

    # ---------------------- Orchestration with Storage ----------------------
    async def purge_asset(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        """Physically delete remote object then remove DB record (idempotent)."""
        await self.purge_asset_by_id(asset_id, metadata_scope=metadata_scope)

    async def purge_asset_by_id(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        """Physically delete remote object and DB record by id."""
        scope = _require_metadata_scope(metadata_scope, operation="purge_asset_by_id")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        async with self._uow_factory() as uow:
            asset = await uow.file_asset_repository.get_by_id(
                asset_id,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(asset_id)

            try:
                await self._storage.delete(asset.key)
            except Exception:
                # Best effort deletion; continue to keep API idempotent
                pass

            await uow.file_asset_repository.delete(asset_id, metadata_scope=scope)

    async def confirm_direct_upload(
        self,
        *,
        asset_id: Optional[int] = None,
        key: Optional[str] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetDTO:
        """Confirm client direct upload by reconciling metadata from storage."""
        scope = _require_metadata_scope(metadata_scope, operation="confirm_direct_upload")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        async with self._uow_factory() as uow:
            repo = uow.file_asset_repository
            asset: Optional[FileAsset] = None
            if asset_id is not None:
                asset = await repo.get_by_id(asset_id, metadata_scope=scope)
            if asset is None and key:
                asset = await repo.get_by_key(key, metadata_scope=scope)
            if asset is None:
                raise FileAssetNotFoundException(asset_id, key=key)

            meta = await self._storage.get_metadata(asset.key)
            public_url = self._storage.public_url(asset.key)

            asset.update_object_metadata(
                size=getattr(meta, "size", None),
                etag=getattr(meta, "etag", None),
                content_type=getattr(meta, "content_type", None) or asset.content_type,
                url=public_url,
                metadata=_merge_metadata_preserving_acl(
                    asset.metadata,
                    getattr(meta, "custom_metadata", None),
                ),
            )
            asset.mark_active()
            updated = await repo.update(asset, metadata_scope=scope)
            return self._to_dto(updated)

    async def generate_access_url_by_info(
        self,
        *,
        key: str,
        content_type: Optional[str],
        filename: Optional[str],
        expires_in: int,
        disposition_mode: str = "inline",
    ) -> dict[str, int | str]:
        """Generate signed access URL for given file info (no DB lookup)."""
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        if filename:
            disposition = _build_content_disposition(disposition_mode, filename, fallback="file")
        else:
            disposition = disposition_mode

        presigned = await self._storage.generate_presigned_url(
            key=key,
            expires_in=expires_in,
            method="GET",
            content_type=content_type,
            response_content_disposition=disposition,
            # response_content_type intentionally omitted for OSS
        )
        return {
            "url": getattr(presigned, "url", ""),
            "expires_in": getattr(presigned, "expires_in", expires_in),
        }

    async def generate_access_url_for_asset(
        self,
        *,
        asset: FileAsset,
        expires_in: int,
        filename: Optional[str],
        disposition_mode: str,
    ) -> dict[str, int | str]:
        """Generate public or signed URL for a specific asset."""
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        # If object is public and we can derive a stable URL, return it directly
        if asset.is_public:
            public_url = self._storage.public_url(asset.key)
            if public_url:
                return {"url": public_url, "expires_in": expires_in}

        # Build content type and disposition for signed access
        fname = filename or asset.original_filename or f"file-{asset.id}"
        content_type = asset.content_type or guess_content_type(fname)
        disposition = _build_content_disposition(
            disposition_mode,
            fname,
            fallback=f"file-{asset.id or 0}",
        )

        presigned = await self._storage.generate_presigned_url(
            key=asset.key,
            expires_in=expires_in,
            method="GET",
            content_type=content_type,
            response_content_disposition=disposition,
        )
        return {"url": presigned.url, "expires_in": presigned.expires_in}

    async def presign_upload(
        self,
        *,
        user_id: Optional[int],
        filename: str,
        mime_type: Optional[str],
        size_bytes: int,
        kind: str,
        method: str = "PUT",
        expires_in: int = 600,
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ):
        """Prepare client direct-upload: generate presigned request and persist pending asset."""
        scope = _require_metadata_scope(metadata_scope, operation="presign_upload")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        method = method or "PUT"
        if method not in {"PUT", "POST"}:
            raise DomainValidationException(
                "Invalid upload method",
                field="method",
                details={"method": method},
                message_key="storage.method.invalid",
            )

        # Basic validations
        fname = filename or "upload.bin"
        if len(fname) > 255:
            raise InvalidFileNameException(fname, max_len=255)

        _, ext = splitext(fname)
        content_type = mime_type or guess_content_type(fname)

        # Check allowed MIME types (presign context)
        allowed_types = getattr(settings.storage, "presign_content_types", None)
        if allowed_types and content_type and content_type not in allowed_types:
            raise UnsupportedMimeTypeException(content_type)

        # Check presign size limit
        presign_max = int(getattr(settings.storage, "presign_max_size", 0) or 0)
        if presign_max and size_bytes and size_bytes > presign_max:
            raise FileTooLargeException(size=size_bytes, max_size=presign_max)
        key = build_storage_key(kind=kind, user_id=_user_id_for_key(user_id), ext=ext)

        try:
            presigned: PresignedURL = await self._storage.generate_presigned_url(
                key=key,
                expires_in=expires_in,
                method=method,
                content_type=content_type,
            )
        except ValueError as exc:
            # Normalize to domain-level validation error for i18n handling
            raise DomainValidationException(
                "Validation failed",
                details={"reason": str(exc)},
                message_key="validation.failed",
                format_params={"reason": str(exc)},
            ) from exc

        info: StorageInfo = self._storage.info()
        file_summary = await self.create_pending_asset(
            owner_id=user_id,
            storage_type=info.type,
            bucket=info.bucket,
            region=info.region,
            key=key,
            original_filename=filename,
            content_type=content_type,
            kind=kind,
            metadata={
                **(metadata or {}),
                "expected_size": size_bytes,
                "upload_method": method,
            },
            metadata_scope=scope,
        )

        return file_summary, presigned

    async def generate_upload_presign(
        self,
        *,
        key: str,
        method: str,
        content_type: Optional[str],
        expires_in: int,
    ) -> PresignedURL:
        """Generate a presigned request for uploading to an existing key."""
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")
        method = method or "PUT"
        if method not in {"PUT", "POST"}:
            raise DomainValidationException(
                "Invalid upload method",
                field="method",
                details={"method": method},
                message_key="storage.method.invalid",
            )
        return await self._storage.generate_presigned_url(
            key=key,
            expires_in=expires_in,
            method=method,
            content_type=content_type,
        )

    async def relay_upload(
        self,
        *,
        user_id: Optional[int],
        file_bytes: bytes,
        filename: str,
        kind: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> StorageUploadResponseDTO:
        """Server-side relay upload and persistence to DB.

        Only persist stable public URL (if any); do not store presigned URL.
        """
        scope = _require_metadata_scope(metadata_scope, operation="relay_upload")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        _, ext = splitext(filename or "")
        ctype = content_type or guess_content_type(filename or "")

        # Optional validation for relay uploads (based on storage validation settings)
        if getattr(settings.storage, "validation_enabled", False):
            max_size = int(getattr(settings.storage, "max_file_size", 0) or 0)
            if max_size and len(file_bytes) > max_size:
                raise FileTooLargeException(size=len(file_bytes), max_size=max_size)
            allowed = getattr(settings.storage, "allowed_types", None)
            if allowed and ctype and ctype not in allowed:
                raise UnsupportedMimeTypeException(ctype)
        key = build_storage_key(kind=kind, user_id=_user_id_for_key(user_id), ext=ext)

        # Upload to storage
        meta = {"filename": filename or ""}
        outcome = await self._storage.upload(file_bytes, key, metadata=meta, content_type=ctype)

        # Derive stable public URL only
        info = self._storage.info()
        db_url = self._storage.public_url(outcome.key)

        asset_dto = await self.upsert_active_asset(
            owner_id=user_id,
            storage_type=info.type,
            bucket=info.bucket,
            region=info.region,
            key=outcome.key,
            original_filename=filename or None,
            content_type=outcome.content_type or ctype,
            kind=kind,
            size=outcome.size,
            etag=outcome.etag,
            url=db_url,
            metadata={
                **(metadata or {}),
                "upload_source": "relay",
                "filename": filename or "",
            },
            metadata_scope=scope,
        )

        return StorageUploadResponseDTO(
            key=outcome.key,
            etag=outcome.etag,
            size=outcome.size,
            content_type=outcome.content_type or ctype,
            url=outcome.url,  # response can return provider url if any; not persisted
            file_id=asset_dto.id,
            file_status=asset_dto.status,
        )

    async def relay_upload_stream(
        self,
        *,
        user_id: Optional[int],
        file_stream: AsyncIterator[bytes],
        filename: str,
        kind: str,
        content_type: Optional[str] = None,
        size_hint: Optional[int] = None,
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> StorageUploadResponseDTO:
        """Server-side relay upload with streaming body to reduce peak memory usage."""
        scope = _require_metadata_scope(metadata_scope, operation="relay_upload_stream")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")

        _, ext = splitext(filename or "")
        ctype = content_type or guess_content_type(filename or "")

        max_size = int(getattr(settings.storage, "max_file_size", 0) or 0)
        if getattr(settings.storage, "validation_enabled", False):
            if max_size and size_hint and size_hint > max_size:
                raise FileTooLargeException(size=size_hint, max_size=max_size)
            allowed = getattr(settings.storage, "allowed_types", None)
            if allowed and ctype and ctype not in allowed:
                raise UnsupportedMimeTypeException(ctype)

        key = build_storage_key(kind=kind, user_id=_user_id_for_key(user_id), ext=ext)

        stream: AsyncIterator[bytes] = file_stream
        if getattr(settings.storage, "validation_enabled", False) and max_size:
            stream = _limit_stream(stream, max_bytes=max_size)

        meta = {"filename": filename or ""}
        outcome = await self._storage.upload_stream(stream, key, metadata=meta, content_type=ctype)

        info = self._storage.info()
        db_url = self._storage.public_url(outcome.key)

        asset_dto = await self.upsert_active_asset(
            owner_id=user_id,
            storage_type=info.type,
            bucket=info.bucket,
            region=info.region,
            key=outcome.key,
            original_filename=filename or None,
            content_type=outcome.content_type or ctype,
            kind=kind,
            size=outcome.size,
            etag=outcome.etag,
            url=db_url,
            metadata={
                **(metadata or {}),
                "upload_source": "relay",
                "filename": filename or "",
            },
            metadata_scope=scope,
        )

        return StorageUploadResponseDTO(
            key=outcome.key,
            etag=outcome.etag,
            size=outcome.size,
            content_type=outcome.content_type or ctype,
            url=outcome.url,
            file_id=asset_dto.id,
            file_status=asset_dto.status,
        )

    async def upsert_active_asset(
        self,
        *,
        owner_id: Optional[int],
        storage_type: str,
        bucket: Optional[str],
        region: Optional[str],
        key: str,
        original_filename: Optional[str],
        content_type: Optional[str],
        kind: Optional[str],
        size: int,
        etag: Optional[str],
        url: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetDTO:
        scope = _require_metadata_scope(metadata_scope, operation="upsert_active_asset")
        async with self._uow_factory() as uow:
            repo = uow.file_asset_repository
            asset = await repo.get_by_key(key, metadata_scope=scope)
            if asset is None:
                if await _key_exists_outside_metadata_scope(
                    repo,
                    key=key,
                    metadata_scope=scope,
                ):
                    raise FileAssetNotFoundException(key=key)

                now = _utcnow()
                asset = FileAsset(
                    id=None,
                    owner_id=owner_id,
                    storage_type=storage_type,
                    bucket=bucket,
                    region=region,
                    key=key,
                    size=size,
                    etag=etag,
                    content_type=content_type,
                    original_filename=original_filename,
                    kind=kind,
                    is_public=False,
                    metadata=_metadata_with_scope_acl(metadata, scope),
                    url=url,
                    status="active",
                    created_at=now,
                    updated_at=now,
                    deleted_at=None,
                )
                created = await repo.create(asset)
                return self._to_dto(created)

            asset.owner_id = owner_id
            asset.storage_type = storage_type
            asset.bucket = bucket
            asset.region = region
            asset.original_filename = original_filename or asset.original_filename
            asset.kind = kind or asset.kind
            asset.update_object_metadata(
                size=size,
                etag=etag,
                content_type=content_type,
                url=url,
                metadata=(
                    _merge_metadata_preserving_acl(asset.metadata, metadata)
                    if metadata is not None
                    else asset.metadata
                ),
            )
            asset.mark_active()
            updated = await repo.update(asset, metadata_scope=scope)
            return self._to_dto(updated)

    async def get_asset(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetDTO:
        scope = _require_metadata_scope(metadata_scope, operation="get_asset")
        async with self._uow_factory(readonly=True) as uow:
            asset = await uow.file_asset_repository.get_by_id(
                asset_id,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(asset_id)
            return self._to_dto(asset)

    async def read_asset_bytes(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
        max_bytes: int = 8192,
    ) -> tuple[bytes, bool]:
        """Read a bounded byte prefix after the asset passes metadata scope checks."""
        scope = _require_metadata_scope(metadata_scope, operation="read_asset_bytes")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")
        if max_bytes < 1:
            raise DomainValidationException(
                "max_bytes must be greater than or equal to 1",
                field="max_bytes",
                details={"max_bytes": max_bytes},
                message_key="file_asset.max_bytes.invalid",
            )

        async with self._uow_factory(readonly=True) as uow:
            asset = await uow.file_asset_repository.get_by_id(
                asset_id,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(asset_id)
            key = asset.key
            expected_size = int(asset.size or 0)

        chunks: list[bytes] = []
        seen = 0
        truncated = expected_size > max_bytes
        async for chunk in self._storage.stream_download(key, chunk_size=min(max_bytes, 8192)):
            if not chunk:
                continue
            remaining = max_bytes - seen
            if len(chunk) > remaining:
                chunks.append(chunk[:remaining])
                truncated = True
                break
            chunks.append(chunk)
            seen += len(chunk)
            if seen >= max_bytes:
                break

        return b"".join(chunks), truncated

    async def get_asset_raw(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAsset:
        scope = _require_metadata_scope(metadata_scope, operation="get_asset_raw")
        async with self._uow_factory(readonly=True) as uow:
            asset = await uow.file_asset_repository.get_by_id(
                asset_id,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(asset_id)
            return asset

    async def get_asset_by_key_raw(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAsset:
        scope = _require_metadata_scope(metadata_scope, operation="get_asset_by_key_raw")
        async with self._uow_factory(readonly=True) as uow:
            asset = await uow.file_asset_repository.get_by_key(
                key,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(key=key)
            return asset

    async def list_assets(
        self,
        *,
        owner_id: Optional[int],
        kind: Optional[str],
        status: Optional[str],
        skip: int,
        limit: int,
        metadata_scope: OwnedMetadataScope,
    ) -> Tuple[list[FileAssetDTO], int]:
        scope = _require_metadata_scope(metadata_scope, operation="list_assets")
        async with self._uow_factory(readonly=True) as uow:
            repo = uow.file_asset_repository
            items = await repo.list(
                owner_id=owner_id,
                kind=kind,
                status=status,
                skip=skip,
                limit=limit,
                metadata_scope=scope,
            )
            total = await repo.count(
                owner_id=owner_id,
                kind=kind,
                status=status,
                metadata_scope=scope,
            )
            return [self._to_dto(item) for item in items], total

    async def soft_delete(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> FileAssetDTO:
        scope = _require_metadata_scope(metadata_scope, operation="soft_delete")
        async with self._uow_factory() as uow:
            asset = await uow.file_asset_repository.get_by_id(
                asset_id,
                metadata_scope=scope,
            )
            if asset is None:
                raise FileAssetNotFoundException(asset_id)
            if asset.is_deleted():
                raise FileAssetAlreadyDeletedException(asset_id)
            asset.mark_deleted()
            updated = await uow.file_asset_repository.update(
                asset,
                metadata_scope=scope,
            )
            return self._to_dto(updated)

    async def purge(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        scope = _require_metadata_scope(metadata_scope, operation="purge")
        async with self._uow_factory() as uow:
            await uow.file_asset_repository.delete(asset_id, metadata_scope=scope)

    async def purge_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        scope = _require_metadata_scope(metadata_scope, operation="purge_by_key")
        async with self._uow_factory() as uow:
            await uow.file_asset_repository.delete_by_key(key, metadata_scope=scope)

    # ---- Unified naming (wrappers) ----
    async def purge_asset_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        """Physically delete remote object and DB record by key (new)."""
        scope = _require_metadata_scope(metadata_scope, operation="purge_asset_by_key")
        if self._storage is None:
            raise RuntimeError("Storage port not configured for FileAssetApplicationService")
        async with self._uow_factory() as uow:
            repo = uow.file_asset_repository
            asset = await repo.get_by_key(key, metadata_scope=scope)
            if asset is None:
                raise FileAssetNotFoundException(key=key)
            try:
                await self._storage.delete(asset.key)
            except Exception:
                pass
            await repo.delete(asset.id or 0, metadata_scope=scope)
            await uow.commit()

    async def delete_record_by_id(
        self,
        asset_id: int,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        """Delete DB record only by id (soft API should be preferred)."""
        scope = _require_metadata_scope(metadata_scope, operation="delete_record_by_id")
        async with self._uow_factory() as uow:
            await uow.file_asset_repository.delete(asset_id, metadata_scope=scope)
            await uow.commit()

    async def delete_record_by_key(
        self,
        key: str,
        *,
        metadata_scope: OwnedMetadataScope,
    ) -> None:
        """Delete DB record only by key (no remote object deletion)."""
        scope = _require_metadata_scope(metadata_scope, operation="delete_record_by_key")
        async with self._uow_factory() as uow:
            await uow.file_asset_repository.delete_by_key(key, metadata_scope=scope)
            await uow.commit()
