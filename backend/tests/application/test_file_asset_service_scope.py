from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from application.services.file_asset_service import FileAssetApplicationService
from domain.common.exceptions import DomainValidationException, FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset.entity import FileAsset


def _asset(asset_id: int = 1, *, status: str = "pending") -> FileAsset:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAsset(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=f"training_material/{asset_id}.txt",
        size=1,
        etag=None,
        content_type="text/plain",
        original_filename=f"{asset_id}.txt",
        kind="training_material",
        is_public=False,
        metadata={
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
        },
        url=None,
        status=status,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


class _FakeFileAssetRepository:
    def __init__(self, assets: dict[int, FileAsset]) -> None:
        self.assets = assets
        self.get_by_id_calls: list[dict[str, Any]] = []
        self.get_by_key_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.create_calls: list[FileAsset] = []

    async def get_by_id(self, asset_id: int, *, metadata_scope=None):
        self.get_by_id_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        return self.assets.get(asset_id)

    async def get_by_key(self, key: str, *, metadata_scope=None):
        self.get_by_key_calls.append({"key": key, "metadata_scope": metadata_scope})
        for asset in self.assets.values():
            if asset.key == key:
                return asset
        return None

    async def create(self, asset: FileAsset):
        self.create_calls.append(asset)
        next_id = max(self.assets) + 1 if self.assets else 1
        asset.id = next_id
        self.assets[next_id] = asset
        return asset

    async def update(self, asset: FileAsset, *, metadata_scope=None):
        self.update_calls.append({"asset": asset, "metadata_scope": metadata_scope})
        self.assets[asset.id or 0] = asset
        return asset

    async def delete(self, asset_id: int, *, metadata_scope=None):
        self.delete_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        self.assets.pop(asset_id, None)

    async def delete_by_key(self, key: str, *, metadata_scope=None):
        for asset_id, asset in list(self.assets.items()):
            if asset.key == key:
                await self.delete(asset_id, metadata_scope=metadata_scope)
                return

    async def list(self, *, metadata_scope=None, **kwargs):
        return list(self.assets.values())

    async def count(self, *, metadata_scope=None, **kwargs):
        return len(self.assets)


class _FakeUnitOfWork:
    def __init__(self, repo: _FakeFileAssetRepository, *, readonly: bool = False) -> None:
        self.file_asset_repository = repo
        self.readonly = readonly
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            await self.rollback()
        elif not self.readonly:
            await self.commit()

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class _FakeStorage:
    def __init__(self) -> None:
        self.metadata_calls: list[str] = []
        self.delete_calls: list[str] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.upload_stream_calls: list[dict[str, Any]] = []
        self.streams: dict[str, list[bytes]] = {}
        self.custom_metadata: dict[str, Any] = {"title": "Confirmed"}

    async def get_metadata(self, key: str):
        self.metadata_calls.append(key)
        return SimpleNamespace(
            size=10,
            etag="etag-confirmed",
            content_type="text/markdown",
            custom_metadata=self.custom_metadata,
        )

    def public_url(self, key: str) -> str:
        return f"https://files.test/{key}"

    async def delete(self, key: str) -> bool:
        self.delete_calls.append(key)
        return True

    async def stream_download(self, key: str, chunk_size: int = 8192):
        self.stream_calls.append({"key": key, "chunk_size": chunk_size})
        for chunk in self.streams.get(key, []):
            yield chunk

    async def upload_stream(self, stream, key: str, *, metadata=None, content_type=None):
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
        self.upload_stream_calls.append(
            {
                "key": key,
                "metadata": metadata,
                "content_type": content_type,
                "bytes": b"".join(chunks),
            }
        )
        return SimpleNamespace(
            key=key,
            etag="etag-uploaded",
            size=sum(len(chunk) for chunk in chunks),
            content_type=content_type,
            url=f"https://provider.test/{key}",
        )

    def info(self):
        return SimpleNamespace(type="local", bucket=None, region=None)


def _service(repo: _FakeFileAssetRepository, storage=None) -> FileAssetApplicationService:
    def uow_factory(*, readonly: bool = False):
        return _FakeUnitOfWork(repo, readonly=readonly)

    return FileAssetApplicationService(uow_factory=uow_factory, storage=storage)


async def _byte_stream():
    yield b"abc"


@pytest.mark.asyncio
async def test_existing_asset_access_requires_metadata_scope_before_repository_or_storage() -> None:
    repo = _FakeFileAssetRepository({7: _asset(7)})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)

    with pytest.raises(DomainValidationException):
        await service.confirm_direct_upload(asset_id=7)
    with pytest.raises(DomainValidationException):
        await service.read_asset_bytes(7, max_bytes=8)
    with pytest.raises(DomainValidationException):
        await service.list_assets(
            owner_id=None,
            kind="training_material",
            status="active",
            skip=0,
            limit=10,
        )

    assert repo.get_by_id_calls == []
    assert storage.metadata_calls == []
    assert storage.stream_calls == []


@pytest.mark.asyncio
async def test_destructive_helpers_require_metadata_scope_before_delete() -> None:
    repo = _FakeFileAssetRepository({11: _asset(11, status="active")})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)

    with pytest.raises(DomainValidationException):
        await service.purge_asset_by_id(11)
    with pytest.raises(DomainValidationException):
        await service.purge_asset_by_key("training_material/11.txt")
    with pytest.raises(DomainValidationException):
        await service.delete_record_by_id(11)
    with pytest.raises(DomainValidationException):
        await service.delete_record_by_key("training_material/11.txt")

    assert repo.get_by_id_calls == []
    assert repo.get_by_key_calls == []
    assert repo.delete_calls == []
    assert storage.delete_calls == []


@pytest.mark.asyncio
async def test_confirm_direct_upload_uses_metadata_scope_for_get_and_update() -> None:
    repo = _FakeFileAssetRepository({7: _asset(7)})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)
    scope = _scope()

    confirmed = await service.confirm_direct_upload(asset_id=7, metadata_scope=scope)

    assert confirmed.status == "active"
    assert repo.get_by_id_calls == [{"asset_id": 7, "metadata_scope": scope}]
    assert repo.update_calls[0]["metadata_scope"] == scope
    assert storage.metadata_calls == ["training_material/7.txt"]


@pytest.mark.asyncio
async def test_confirm_direct_upload_preserves_existing_acl_metadata() -> None:
    asset = _asset(7)
    repo = _FakeFileAssetRepository({7: asset})
    storage = _FakeStorage()
    storage.custom_metadata = {
        "title": "Confirmed",
        "ownerUserId": "user-cs-001",
        "teamId": "team-service",
        "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
    }
    service = _service(repo, storage=storage)

    confirmed = await service.confirm_direct_upload(asset_id=7, metadata_scope=_scope())

    assert confirmed.metadata["title"] == "Confirmed"
    assert confirmed.metadata["ownerUserId"] == "user-sales-001"
    assert confirmed.metadata["teamId"] == "team-revenue"
    assert confirmed.metadata["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }


@pytest.mark.asyncio
async def test_confirm_direct_upload_rejects_scoped_miss_before_storage_or_update() -> None:
    repo = _FakeFileAssetRepository({})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)

    with pytest.raises(FileAssetNotFoundException):
        await service.confirm_direct_upload(asset_id=8, metadata_scope=_scope())

    assert storage.metadata_calls == []
    assert repo.update_calls == []


@pytest.mark.asyncio
async def test_soft_delete_uses_metadata_scope_for_get_and_update() -> None:
    repo = _FakeFileAssetRepository({9: _asset(9, status="active")})
    service = _service(repo)
    scope = _scope()

    deleted = await service.soft_delete(9, metadata_scope=scope)

    assert deleted.status == "deleted"
    assert repo.get_by_id_calls == [{"asset_id": 9, "metadata_scope": scope}]
    assert repo.update_calls[0]["metadata_scope"] == scope


@pytest.mark.asyncio
async def test_mark_asset_active_preserves_existing_acl_metadata() -> None:
    repo = _FakeFileAssetRepository({10: _asset(10)})
    service = _service(repo)

    updated = await service.mark_asset_active(
        asset_id=10,
        metadata={
            "title": "Active",
            "ownerUserId": "user-cs-001",
            "teamId": "team-service",
            "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
        },
        metadata_scope=_scope(),
    )

    assert updated.metadata["title"] == "Active"
    assert updated.metadata["ownerUserId"] == "user-sales-001"
    assert updated.metadata["teamId"] == "team-revenue"
    assert updated.metadata["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }


@pytest.mark.asyncio
async def test_read_asset_bytes_uses_metadata_scope_and_limits_storage_read() -> None:
    repo = _FakeFileAssetRepository({13: _asset(13, status="active")})
    storage = _FakeStorage()
    storage.streams["training_material/13.txt"] = [b"abcdef", b"ghijkl"]
    service = _service(repo, storage=storage)
    scope = _scope()

    data, truncated = await service.read_asset_bytes(13, metadata_scope=scope, max_bytes=8)

    assert data == b"abcdefgh"
    assert truncated is True
    assert repo.get_by_id_calls == [{"asset_id": 13, "metadata_scope": scope}]
    assert storage.stream_calls == [{"key": "training_material/13.txt", "chunk_size": 8}]


@pytest.mark.asyncio
async def test_read_asset_bytes_marks_known_large_asset_truncated() -> None:
    asset = _asset(14, status="active")
    asset.size = 64
    repo = _FakeFileAssetRepository({14: asset})
    storage = _FakeStorage()
    storage.streams["training_material/14.txt"] = [b"abcdefgh"]
    service = _service(repo, storage=storage)

    data, truncated = await service.read_asset_bytes(14, metadata_scope=_scope(), max_bytes=8)

    assert data == b"abcdefgh"
    assert truncated is True


@pytest.mark.asyncio
async def test_upsert_active_asset_uses_metadata_scope_for_existing_asset_update() -> None:
    repo = _FakeFileAssetRepository({10: _asset(10)})
    service = _service(repo)
    scope = _scope()

    updated = await service.upsert_active_asset(
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key="training_material/10.txt",
        original_filename="scoped-update.txt",
        content_type="text/plain",
        kind="training_material",
        size=32,
        etag="etag-updated",
        url="https://files.test/training_material/10.txt",
        metadata={"title": "Scoped update"},
        metadata_scope=scope,
    )

    assert updated.id == 10
    assert updated.status == "active"
    assert repo.get_by_key_calls == [
        {"key": "training_material/10.txt", "metadata_scope": scope}
    ]
    assert repo.update_calls[0]["metadata_scope"] == scope
    assert repo.create_calls == []


@pytest.mark.asyncio
async def test_upsert_active_asset_preserves_acl_metadata_on_existing_asset_update() -> None:
    repo = _FakeFileAssetRepository({10: _asset(10)})
    service = _service(repo)

    updated = await service.upsert_active_asset(
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key="training_material/10.txt",
        original_filename="scoped-update.txt",
        content_type="text/plain",
        kind="training_material",
        size=32,
        etag="etag-updated",
        url="https://files.test/training_material/10.txt",
        metadata={
            "title": "Scoped update",
            "ownerUserId": "user-cs-001",
            "teamId": "team-service",
            "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
        },
        metadata_scope=_scope(),
    )

    assert updated.metadata["title"] == "Scoped update"
    assert updated.metadata["ownerUserId"] == "user-sales-001"
    assert updated.metadata["teamId"] == "team-revenue"
    assert updated.metadata["authScope"] == {
        "userId": "user-sales-001",
        "teamId": "team-revenue",
    }


@pytest.mark.asyncio
async def test_relay_upload_stream_uses_metadata_scope_for_upsert_lookup() -> None:
    repo = _FakeFileAssetRepository({})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)
    scope = _scope()

    uploaded = await service.relay_upload_stream(
        user_id=None,
        file_stream=_byte_stream(),
        filename="relay.txt",
        kind="training_material",
        content_type="text/plain",
        metadata={
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
        },
        metadata_scope=scope,
    )

    assert uploaded.file_status == "active"
    assert repo.get_by_key_calls[0]["metadata_scope"] == scope
    assert repo.create_calls[0].metadata["ownerUserId"] == "user-sales-001"


@pytest.mark.asyncio
async def test_purge_asset_by_id_uses_metadata_scope_for_lookup_and_delete() -> None:
    repo = _FakeFileAssetRepository({11: _asset(11, status="active")})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)
    scope = _scope()

    await service.purge_asset_by_id(11, metadata_scope=scope)

    assert repo.get_by_id_calls == [{"asset_id": 11, "metadata_scope": scope}]
    assert repo.delete_calls == [{"asset_id": 11, "metadata_scope": scope}]
    assert storage.delete_calls == ["training_material/11.txt"]


@pytest.mark.asyncio
async def test_purge_asset_by_key_uses_metadata_scope_for_lookup_and_delete() -> None:
    repo = _FakeFileAssetRepository({12: _asset(12, status="active")})
    storage = _FakeStorage()
    service = _service(repo, storage=storage)
    scope = _scope()

    await service.purge_asset_by_key("training_material/12.txt", metadata_scope=scope)

    assert repo.get_by_key_calls == [
        {"key": "training_material/12.txt", "metadata_scope": scope}
    ]
    assert repo.delete_calls == [{"asset_id": 12, "metadata_scope": scope}]
    assert storage.delete_calls == ["training_material/12.txt"]
