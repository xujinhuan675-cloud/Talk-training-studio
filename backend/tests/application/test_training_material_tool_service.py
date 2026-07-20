from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from application.dto import FileAssetDTO
from application.services.training_studio.training_material_tool_service import (
    TRAINING_MATERIAL_KIND,
    TRAINING_MATERIAL_STATUS,
    TrainingMaterialToolConsumerService,
)
from domain.common.exceptions import DomainValidationException, FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset.entity import FileAsset


def _scoped_metadata(metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "ownerUserId": "user-sales-001",
        "teamId": "team-revenue",
        "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
        **(metadata or {}),
    }


def _file_asset_dto(
    *,
    asset_id: int = 1,
    key: str = "training_material/1.txt",
    original_filename: str | None = "training-material.txt",
    content_type: str | None = "text/plain",
    kind: str | None = TRAINING_MATERIAL_KIND,
    status: str = TRAINING_MATERIAL_STATUS,
    metadata: dict[str, Any] | None = None,
) -> FileAssetDTO:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAssetDTO(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=key,
        size=128,
        etag="etag-1",
        content_type=content_type,
        original_filename=original_filename,
        kind=kind,
        is_public=False,
        metadata=_scoped_metadata(metadata),
        url=None,
        status=status,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def _file_asset_entity(
    *,
    asset_id: int = 2,
    key: str = "training_material/2.txt",
    original_filename: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FileAsset:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAsset(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=key,
        size=128,
        etag="etag-1",
        content_type="text/plain",
        original_filename=original_filename,
        kind=TRAINING_MATERIAL_KIND,
        is_public=False,
        metadata=_scoped_metadata(metadata),
        url=None,
        status=TRAINING_MATERIAL_STATUS,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class _FakeFileAssetService:
    def __init__(
        self,
        *,
        list_items: list[FileAssetDTO] | None = None,
        assets_by_id: dict[int, FileAssetDTO] | None = None,
        assets_by_key: dict[str, FileAsset] | None = None,
    ) -> None:
        self.list_items = list_items or []
        self.assets_by_id = assets_by_id or {}
        self.assets_by_key = assets_by_key or {}
        self.content_by_id: dict[int, tuple[bytes, bool]] = {}
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.get_by_key_calls: list[dict[str, Any]] = []
        self.read_calls: list[dict[str, Any]] = []

    async def list_assets(
        self,
        *,
        owner_id,
        kind,
        status,
        skip,
        limit,
        metadata_scope,
    ):
        kwargs = {
            "owner_id": owner_id,
            "kind": kind,
            "status": status,
            "skip": skip,
            "limit": limit,
            "metadata_scope": metadata_scope,
        }
        self.list_calls.append(kwargs)
        return self.list_items, len(self.list_items)

    async def get_asset(self, asset_id: int, *, metadata_scope):
        self.get_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        asset = self.assets_by_id.get(asset_id)
        if asset is None:
            raise FileAssetNotFoundException(asset_id)
        return asset

    async def get_asset_by_key_raw(self, key: str, *, metadata_scope):
        self.get_by_key_calls.append({"key": key, "metadata_scope": metadata_scope})
        asset = self.assets_by_key.get(key)
        if asset is None:
            raise FileAssetNotFoundException(key=key)
        return asset

    async def read_asset_bytes(self, asset_id: int, *, metadata_scope, max_bytes=8192):
        self.read_calls.append(
            {
                "asset_id": asset_id,
                "metadata_scope": metadata_scope,
                "max_bytes": max_bytes,
            }
        )
        if asset_id not in self.content_by_id:
            raise FileAssetNotFoundException(asset_id)
        return self.content_by_id[asset_id]


def _scope() -> OwnedMetadataScope:
    return OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )


@pytest.mark.asyncio
async def test_list_materials_uses_scoped_training_material_file_asset_query() -> None:
    long_summary = "x" * 260
    file_service = _FakeFileAssetService(
        list_items=[
            _file_asset_dto(
                metadata={
                    "usageScope": "training_material",
                    "title": "Negotiation transcript",
                    "summary": long_summary,
                    "tags": ["sales", "renewal", "enterprise"],
                    "authScope": {"userId": "user-sales-001"},
                    "ownerUserId": "user-sales-001",
                    "teamId": "team-revenue",
                    "raw_text": "full file content must not leak",
                    "apiKey": "secret",
                }
            )
        ]
    )
    scope = _scope()
    service = TrainingMaterialToolConsumerService(file_service)

    result = await service.list_materials(metadata_scope=scope, skip=2, limit=500)

    assert result.total == 1
    assert result.skip == 2
    assert result.limit == 100
    assert file_service.list_calls == [
        {
            "owner_id": None,
            "kind": TRAINING_MATERIAL_KIND,
            "status": TRAINING_MATERIAL_STATUS,
            "skip": 2,
            "limit": 100,
            "metadata_scope": scope,
        }
    ]
    material = result.items[0]
    assert material.id == 1
    assert material.key == "training_material/1.txt"
    assert material.name == "training-material.txt"
    assert material.content_type == "text/plain"
    assert material.metadata_excerpt["usageScope"] == "training_material"
    assert material.metadata_excerpt["title"] == "Negotiation transcript"
    assert material.metadata_excerpt["summary"] == f"{long_summary[:240]}..."
    assert material.metadata_excerpt["tags"] == ["sales", "renewal", "enterprise"]
    assert "authScope" not in material.metadata_excerpt
    assert "ownerUserId" not in material.metadata_excerpt
    assert "teamId" not in material.metadata_excerpt
    assert "raw_text" not in material.metadata_excerpt
    assert "apiKey" not in material.metadata_excerpt
    assert file_service.read_calls == []


@pytest.mark.asyncio
async def test_list_materials_can_include_bounded_text_content_excerpt() -> None:
    file_service = _FakeFileAssetService(
        list_items=[
            _file_asset_dto(
                metadata={
                    "title": "Renewal playbook",
                    "summary": "How to handle renewal objections.",
                }
            )
        ]
    )
    file_service.content_by_id[1] = (
        b"Discovery question: What changed since rollout?\napi_key: sk-hidden\nClose with a pilot.",
        False,
    )
    scope = _scope()
    service = TrainingMaterialToolConsumerService(file_service)

    result = await service.list_materials(
        metadata_scope=scope,
        limit=5,
        include_content_excerpt=True,
    )

    material = result.items[0]
    assert file_service.read_calls == [
        {"asset_id": 1, "metadata_scope": scope, "max_bytes": 8192}
    ]
    assert material.content_excerpt == (
        "Discovery question: What changed since rollout?\n"
        "[redacted]\n"
        "Close with a pilot."
    )
    assert material.content_excerpt_truncated is False


@pytest.mark.asyncio
async def test_list_materials_filters_reader_scope_escape_before_content_read() -> None:
    file_service = _FakeFileAssetService(
        list_items=[
            _file_asset_dto(asset_id=1, metadata={"title": "Visible material"}),
            _file_asset_dto(
                asset_id=2,
                metadata={
                    "title": "Hidden material",
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                    "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                },
            ),
        ]
    )
    file_service.content_by_id[1] = (b"Visible scoped content.", False)
    file_service.content_by_id[2] = (b"Hidden content must not be read.", False)
    scope = _scope()
    service = TrainingMaterialToolConsumerService(file_service)

    result = await service.list_materials(
        metadata_scope=scope,
        include_content_excerpt=True,
    )

    assert result.total == 1
    assert [material.id for material in result.items] == [1]
    assert file_service.read_calls == [
        {"asset_id": 1, "metadata_scope": scope, "max_bytes": 8192}
    ]


@pytest.mark.asyncio
async def test_list_materials_skips_binary_content_excerpt_reads() -> None:
    file_service = _FakeFileAssetService(
        list_items=[
            _file_asset_dto(
                key="training_material/voice.mp3",
                original_filename="voice.mp3",
                content_type="audio/mpeg",
            )
        ]
    )
    scope = _scope()
    service = TrainingMaterialToolConsumerService(file_service)

    result = await service.list_materials(
        metadata_scope=scope,
        include_content_excerpt=True,
    )

    assert file_service.read_calls == []
    assert result.items[0].content_excerpt is None
    assert result.items[0].content_excerpt_truncated is False


@pytest.mark.asyncio
async def test_get_material_keeps_scope_and_hides_non_material_assets() -> None:
    scope = _scope()
    file_service = _FakeFileAssetService(
        assets_by_id={
            1: _file_asset_dto(metadata={"title": "Visible material"}),
            2: _file_asset_dto(asset_id=2, kind="avatar", metadata={"title": "Wrong kind"}),
            3: _file_asset_dto(asset_id=3, status="deleted", metadata={"title": "Deleted"}),
        }
    )
    service = TrainingMaterialToolConsumerService(file_service)

    material = await service.get_material(1, metadata_scope=scope)

    assert material.id == 1
    assert material.metadata_excerpt == {"title": "Visible material"}
    assert file_service.get_calls[0] == {"asset_id": 1, "metadata_scope": scope}

    with pytest.raises(FileAssetNotFoundException):
        await service.get_material(2, metadata_scope=scope)
    with pytest.raises(FileAssetNotFoundException):
        await service.get_material(3, metadata_scope=scope)


@pytest.mark.asyncio
async def test_get_material_hides_reader_scope_escape_without_content_read() -> None:
    scope = _scope()
    file_service = _FakeFileAssetService(
        assets_by_id={
            4: _file_asset_dto(
                asset_id=4,
                metadata={
                    "title": "Hidden material",
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                    "authScope": {"userId": "user-cs-001", "teamId": "team-service"},
                },
            )
        }
    )
    file_service.content_by_id[4] = (b"Hidden content must not be read.", False)
    service = TrainingMaterialToolConsumerService(file_service)

    with pytest.raises(FileAssetNotFoundException):
        await service.get_material(4, metadata_scope=scope, include_content_excerpt=True)

    assert file_service.get_calls == [{"asset_id": 4, "metadata_scope": scope}]
    assert file_service.read_calls == []


@pytest.mark.asyncio
async def test_get_material_by_key_returns_summary_without_reading_file_content() -> None:
    scope = _scope()
    key = "training_material/persona-seed.md"
    file_service = _FakeFileAssetService(
        assets_by_key={
            key: _file_asset_entity(
                key=key,
                original_filename=None,
                metadata={
                    "title": "Persona seed",
                    "content": "actual file content must not be returned",
                },
            )
        }
    )
    service = TrainingMaterialToolConsumerService(file_service)

    material = await service.get_material_by_key(key, metadata_scope=scope)

    assert file_service.get_by_key_calls == [{"key": key, "metadata_scope": scope}]
    assert material.key == key
    assert material.name == "Persona seed"
    assert material.metadata_excerpt == {"title": "Persona seed"}


@pytest.mark.asyncio
async def test_training_material_consumer_requires_metadata_scope() -> None:
    service = TrainingMaterialToolConsumerService(_FakeFileAssetService())

    with pytest.raises(DomainValidationException):
        await service.list_materials(metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await service.get_material(1, metadata_scope=None)
    with pytest.raises(DomainValidationException):
        await service.get_material_by_key("training_material/1.txt", metadata_scope=None)


@pytest.mark.asyncio
async def test_training_material_consumer_rejects_allow_unscoped_scope() -> None:
    file_service = _FakeFileAssetService()
    service = TrainingMaterialToolConsumerService(file_service)
    unsafe_scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=True,
        allow_unscoped=True,
    )

    with pytest.raises(DomainValidationException):
        await service.list_materials(metadata_scope=unsafe_scope)

    assert file_service.list_calls == []
