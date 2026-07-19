from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from application.services.file_asset_service import FileAssetApplicationService
from domain.common.exceptions import FileAssetNotFoundException
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
        self.update_calls: list[dict[str, Any]] = []

    async def get_by_id(self, asset_id: int, *, metadata_scope=None):
        self.get_by_id_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        return self.assets.get(asset_id)

    async def update(self, asset: FileAsset, *, metadata_scope=None):
        self.update_calls.append({"asset": asset, "metadata_scope": metadata_scope})
        self.assets[asset.id or 0] = asset
        return asset


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

    async def get_metadata(self, key: str):
        self.metadata_calls.append(key)
        return SimpleNamespace(
            size=10,
            etag="etag-confirmed",
            content_type="text/markdown",
            custom_metadata={"title": "Confirmed"},
        )

    def public_url(self, key: str) -> str:
        return f"https://files.test/{key}"


def _service(repo: _FakeFileAssetRepository, storage=None) -> FileAssetApplicationService:
    def uow_factory(*, readonly: bool = False):
        return _FakeUnitOfWork(repo, readonly=readonly)

    return FileAssetApplicationService(uow_factory=uow_factory, storage=storage)


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
