from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_file_asset_service
from api.routes.files import router as files_router
from application.dto import FileAssetDTO
from core.exceptions import register_exception_handlers
from domain.common.exceptions import FileAssetNotFoundException
from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset.entity import FileAsset


def _asset(
    asset_id: int = 1,
    *,
    owner_user_id: str = "user-sales-001",
    team_id: str = "team-revenue",
) -> FileAsset:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAsset(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=f"training_material/{asset_id}.txt",
        size=1,
        content_type="text/plain",
        original_filename=f"{asset_id}.txt",
        kind="training_material",
        metadata={
            "ownerUserId": owner_user_id,
            "teamId": team_id,
            "authScope": {"userId": owner_user_id, "teamId": team_id},
        },
        url=None,
        status="active",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class FakeFileAssetService:
    def __init__(self, assets: list[FileAsset] | None = None) -> None:
        self.assets = {asset.id: asset for asset in assets or [_asset()]}
        self.list_scopes = []
        self.get_scopes = []
        self.delete_scopes = []
        self.sign_calls = []
        self.blocked_asset_ids = set()

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
        _ = (owner_id, kind, status, skip, limit)
        self.list_scopes.append(metadata_scope)
        items = [
            asset
            for asset in self.assets.values()
            if _matches_metadata_scope(asset.metadata, metadata_scope)
        ]
        return [FileAssetDTO.model_validate(asset) for asset in items], len(items)

    async def get_asset_raw(self, asset_id: int, *, metadata_scope):
        self.get_scopes.append(metadata_scope)
        if asset_id in self.blocked_asset_ids:
            raise FileAssetNotFoundException(asset_id)
        asset = self.assets.get(asset_id) or _asset(asset_id)
        if not _matches_metadata_scope(asset.metadata, metadata_scope):
            raise FileAssetNotFoundException(asset_id)
        return asset

    async def generate_access_url_by_info(self, **kwargs):
        return {"url": f"https://files.test/{kwargs['key']}"}

    async def generate_access_url_for_asset(self, **kwargs):
        asset = kwargs["asset"]
        self.sign_calls.append(kwargs)
        return {"url": f"https://files.test/{asset.key}"}

    async def soft_delete(self, asset_id: int, *, metadata_scope):
        self.delete_scopes.append(metadata_scope)
        asset = self.assets.get(asset_id) or _asset(asset_id)
        if not _matches_metadata_scope(asset.metadata, metadata_scope):
            raise FileAssetNotFoundException(asset_id)
        asset.mark_deleted()
        return FileAssetDTO.model_validate(asset)


def _matches_metadata_scope(
    metadata: dict | None,
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


def _client(fake_service: FakeFileAssetService) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(files_router, prefix="/api/v1")
    app.dependency_overrides[get_file_asset_service] = lambda: fake_service
    return TestClient(app)


def test_file_list_uses_current_user_metadata_scope() -> None:
    fake = FakeFileAssetService()
    client = _client(fake)

    response = client.get(
        "/api/v1/files?kind=training_material",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    scope = fake.list_scopes[0]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False


def test_file_list_hides_assets_outside_current_user_scope() -> None:
    fake = FakeFileAssetService(
        assets=[
            _asset(1),
            _asset(2, owner_user_id="user-cs-001", team_id="team-service"),
        ]
    )
    client = _client(fake)

    response = client.get(
        "/api/v1/files?kind=training_material",
        headers={"X-Mock-User": "sales"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [1]


def test_staff_file_detail_and_delete_are_limited_to_own_metadata_scope() -> None:
    fake = FakeFileAssetService(assets=[_asset(owner_user_id="user-peer-001")])
    client = _client(fake)

    detail = client.get("/api/v1/files/1", headers={"X-Mock-User": "sales"})
    deleted = client.delete("/api/v1/files/1", headers={"X-Mock-User": "sales"})

    assert detail.status_code == 404
    assert deleted.status_code == 404
    get_scope = fake.get_scopes[0]
    delete_scope = fake.delete_scopes[0]
    assert get_scope.user_id == "user-sales-001"
    assert get_scope.team_id == "team-revenue"
    assert get_scope.include_team_scope is False
    assert get_scope.allow_unscoped is False
    assert delete_scope.user_id == "user-sales-001"
    assert delete_scope.include_team_scope is False


def test_file_url_routes_use_scope_and_reject_before_signing() -> None:
    fake = FakeFileAssetService()
    fake.blocked_asset_ids.add(2)
    client = _client(fake)

    preview = client.post(
        "/api/v1/files/1/preview-url",
        headers={"X-Mock-User": "sales"},
        json={},
    )
    download = client.post(
        "/api/v1/files/1/download-url",
        headers={"X-Mock-User": "sales"},
        json={},
    )
    blocked = client.post(
        "/api/v1/files/2/preview-url",
        headers={"X-Mock-User": "sales"},
        json={},
    )

    assert preview.status_code == 200
    assert download.status_code == 200
    assert blocked.status_code == 404
    assert len(fake.sign_calls) == 2
    assert [scope.user_id for scope in fake.get_scopes] == [
        "user-sales-001",
        "user-sales-001",
        "user-sales-001",
    ]
    assert all(scope.allow_unscoped is False for scope in fake.get_scopes)
