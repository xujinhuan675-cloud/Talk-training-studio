from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_file_asset_service
from api.routes.training_studio import router
from application.dto import FileAssetDTO
from domain.common.exceptions import FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope


def _material_asset(
    asset_id: int = 1,
    *,
    kind: str | None = "training_material",
    status: str = "active",
    metadata: dict[str, Any] | None = None,
) -> FileAssetDTO:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAssetDTO(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=f"training_material/{asset_id}.md",
        size=128,
        etag="etag-1",
        content_type="text/markdown",
        original_filename=f"material-{asset_id}.md",
        kind=kind,
        is_public=False,
        metadata=metadata
        or {
            "title": f"Material {asset_id}",
            "summary": "Scoped training material summary",
            "tags": ["sales", "renewal"],
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "raw_text": "full content must not leak",
            "apiKey": "sk-secret-should-not-appear",
        },
        url=None,
        status=status,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class _FakeFileAssetService:
    def __init__(self, *, assets: list[FileAssetDTO] | None = None) -> None:
        self.assets = {asset.id: asset for asset in assets or []}
        self.content_by_id: dict[int, tuple[bytes, bool]] = {}
        self.list_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
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
        items = [
            asset
            for asset in self.assets.values()
            if asset.kind == kind
            and asset.status == status
            and _matches_metadata_scope(asset.metadata, metadata_scope)
        ]
        return items, len(items)

    async def get_asset(self, asset_id: int, *, metadata_scope):
        self.get_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        asset = self.assets.get(asset_id)
        if asset is None or not _matches_metadata_scope(asset.metadata, metadata_scope):
            raise FileAssetNotFoundException(asset_id)
        return asset

    async def read_asset_bytes(self, asset_id: int, *, metadata_scope, max_bytes=8192):
        self.read_calls.append(
            {
                "asset_id": asset_id,
                "metadata_scope": metadata_scope,
                "max_bytes": max_bytes,
            }
        )
        return self.content_by_id[asset_id]


def _matches_metadata_scope(
    metadata: dict[str, Any] | None,
    scope: OwnedMetadataScope,
) -> bool:
    metadata = metadata or {}
    auth_scope = metadata.get("authScope") if isinstance(metadata.get("authScope"), dict) else {}
    owner_user_id = (
        auth_scope.get("userId")
        or auth_scope.get("user_id")
        or metadata.get("ownerUserId")
        or metadata.get("owner_user_id")
        or metadata.get("createdByUserId")
        or metadata.get("created_by_user_id")
    )
    owner_team_id = (
        auth_scope.get("teamId")
        or auth_scope.get("team_id")
        or metadata.get("teamId")
        or metadata.get("team_id")
        or metadata.get("ownerTeamId")
        or metadata.get("owner_team_id")
    )
    owner_user_id = str(owner_user_id).strip() if owner_user_id else ""
    owner_team_id = str(owner_team_id).strip() if owner_team_id else ""

    if owner_user_id and owner_user_id == scope.user_id:
        return True
    if scope.team_id and owner_team_id == scope.team_id:
        return bool(scope.include_team_scope or not owner_user_id)
    if not owner_user_id and not owner_team_id:
        return scope.allow_unscoped
    return False


def _client(fake_service: _FakeFileAssetService) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_file_asset_service] = lambda: fake_service
    return TestClient(app)


def test_training_material_tool_consumer_lists_scoped_safe_materials() -> None:
    fake = _FakeFileAssetService(assets=[_material_asset()])
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials?skip=1&limit=5",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    scope = fake.list_calls[0]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False
    assert fake.list_calls[0]["kind"] == "training_material"
    assert fake.list_calls[0]["status"] == "active"

    data = response.json()["data"]
    assert data["total"] == 1
    assert data["skip"] == 1
    assert data["limit"] == 5
    material = data["items"][0]
    assert material["id"] == 1
    assert material["key"] == "training_material/1.md"
    assert material["name"] == "material-1.md"
    assert material["metadata_excerpt"] == {
        "summary": "Scoped training material summary",
        "tags": ["sales", "renewal"],
        "title": "Material 1",
    }
    assert "secret-should-not-appear" not in response.text
    assert "raw_text" not in response.text
    assert "ownerUserId" not in response.text
    assert "teamId" not in response.text
    assert fake.read_calls == []


def test_training_material_tool_consumer_legacy_leader_uses_own_scope() -> None:
    fake = _FakeFileAssetService(
        assets=[
            _material_asset(
                metadata={
                    "title": "Team material",
                    "summary": "Shared renewal material",
                    "ownerUserId": "user-peer-001",
                    "teamId": "team-revenue",
                }
            )
        ]
    )
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials",
        headers={"X-Mock-User": "leader"},
    )

    assert response.status_code == 200
    scope = fake.list_calls[0]["metadata_scope"]
    assert scope.user_id == "user-leader-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


def test_training_material_tool_consumer_list_filters_materials_outside_scope() -> None:
    fake = _FakeFileAssetService(
        assets=[
            _material_asset(1),
            _material_asset(
                2,
                metadata={
                    "title": "Other team material",
                    "summary": "Must be filtered before response.",
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            ),
        ]
    )
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [1]
    assert "Other team material" not in response.text


def test_training_material_tool_consumer_get_rejects_material_outside_scope() -> None:
    fake = _FakeFileAssetService(
        assets=[
            _material_asset(
                3,
                metadata={
                    "title": "Outside material",
                    "summary": "Must not be returned.",
                    "ownerUserId": "user-cs-001",
                    "teamId": "team-service",
                },
            )
        ]
    )
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials/3",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Training material not found"
    assert fake.read_calls == []


def test_training_material_tool_consumer_lists_opt_in_content_excerpt() -> None:
    fake = _FakeFileAssetService(assets=[_material_asset()])
    fake.content_by_id[1] = (
        b"Handle renewal objection with ROI proof.\npassword: hidden\nAsk for success criteria.",
        False,
    )
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials?include_content_excerpt=true",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    material = response.json()["data"]["items"][0]
    assert material["content_excerpt"] == (
        "Handle renewal objection with ROI proof.\n"
        "[redacted]\n"
        "Ask for success criteria."
    )
    assert material["content_excerpt_truncated"] is False
    scope = fake.read_calls[0]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.allow_unscoped is False


def test_training_material_tool_consumer_admin_still_uses_explicit_scope() -> None:
    fake = _FakeFileAssetService(assets=[_material_asset()])
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials",
        headers={"X-Mock-User": "admin"},
    )

    assert response.status_code == 200
    scope = fake.list_calls[0]["metadata_scope"]
    assert scope.user_id == "user-admin-001"
    assert scope.team_id == "team-ops"
    assert scope.include_team_scope is True
    assert scope.allow_unscoped is False


def test_training_material_tool_consumer_hides_non_material_asset() -> None:
    fake = _FakeFileAssetService(assets=[_material_asset(2, kind="avatar")])
    client = _client(fake)

    response = client.get(
        "/api/v1/training-studio/tool-consumers/training-materials/2",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Training material not found"
    scope = fake.get_calls[0]["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.allow_unscoped is False
