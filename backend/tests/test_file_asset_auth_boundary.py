from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_file_asset_service
from api.routes.files import router as files_router
from application.dto import FileAssetDTO
from domain.file_asset.entity import FileAsset


def _asset(asset_id: int = 1) -> FileAsset:
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
            "ownerUserId": "user-sales-001",
            "teamId": "team-revenue",
            "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
        },
        url=None,
        status="active",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


class FakeFileAssetService:
    def __init__(self) -> None:
        self.list_scopes = []
        self.get_scopes = []
        self.delete_scopes = []

    async def list_assets(self, **kwargs):
        self.list_scopes.append(kwargs.get("metadata_scope"))
        return [FileAssetDTO.model_validate(_asset())], 1

    async def get_asset_raw(self, asset_id: int, *, metadata_scope=None):
        self.get_scopes.append(metadata_scope)
        return _asset(asset_id)

    async def generate_access_url_by_info(self, **kwargs):
        return {"url": f"https://files.test/{kwargs['key']}"}

    async def generate_access_url_for_asset(self, **kwargs):
        asset = kwargs["asset"]
        return {"url": f"https://files.test/{asset.key}"}

    async def soft_delete(self, asset_id: int, *, metadata_scope=None):
        self.delete_scopes.append(metadata_scope)
        asset = _asset(asset_id)
        asset.mark_deleted()
        return FileAssetDTO.model_validate(asset)


def _client(fake_service: FakeFileAssetService) -> TestClient:
    app = FastAPI()
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


def test_file_detail_and_delete_use_current_user_metadata_scope() -> None:
    fake = FakeFileAssetService()
    client = _client(fake)

    detail = client.get("/api/v1/files/1", headers={"X-Mock-User": "leader"})
    deleted = client.delete("/api/v1/files/1", headers={"X-Mock-User": "leader"})

    assert detail.status_code == 200
    assert deleted.status_code == 200
    get_scope = fake.get_scopes[0]
    delete_scope = fake.delete_scopes[0]
    assert get_scope.user_id == "user-leader-001"
    assert get_scope.team_id == "team-revenue"
    assert get_scope.include_team_scope is True
    assert get_scope.allow_unscoped is False
    assert delete_scope.user_id == "user-leader-001"
    assert delete_scope.include_team_scope is True
