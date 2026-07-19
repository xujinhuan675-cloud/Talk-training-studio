from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_file_asset_service, get_idempotency_service
from api.routes.storage import router as storage_router
from application.dto import FileAssetSummaryDTO, StorageUploadResponseDTO
from application.ports.storage import PresignedURL
from application.services.idempotency_service import IdempotencyService
from application.ports.idempotency import IdempotencyRecord, IdempotencyStore
from core.exceptions import register_exception_handlers
from domain.common.exceptions import FileAssetNotFoundException
from domain.file_asset.entity import FileAsset


class InMemoryIdempotencyStore(IdempotencyStore):
    def __init__(self) -> None:
        self._locks: set[tuple[str, str]] = set()
        self._results: dict[tuple[str, str], IdempotencyRecord] = {}

    async def get(self, *, scope: str, key: str):
        return self._results.get((scope, key))

    async def try_start(self, *, scope: str, key: str, request_hash: str, ttl_seconds: int) -> bool:
        _ = ttl_seconds
        lk = (scope, key)
        if lk in self._locks:
            return False
        self._locks.add(lk)
        return True

    async def set_result(
        self,
        *,
        scope: str,
        key: str,
        request_hash: str,
        payload: dict,
        ttl_seconds: int,
    ) -> None:
        _ = ttl_seconds
        self._results[(scope, key)] = IdempotencyRecord(
            scope=scope,
            key=key,
            request_hash=request_hash,
            payload=payload,
        )

    async def release(self, *, scope: str, key: str) -> None:
        self._locks.discard((scope, key))


class FakeFileAssetService:
    def __init__(self) -> None:
        self.presign_calls = 0
        self.generate_calls = 0
        self.last_metadata = None
        self.get_raw_calls = []
        self.get_by_key_raw_calls = []
        self.complete_calls = []
        self.relay_stream_calls = []
        self.blocked_asset_ids = set()

    async def presign_upload(
        self,
        *,
        user_id,
        filename: str,
        mime_type,
        size_bytes: int,
        kind: str,
        method: str = "PUT",
        expires_in: int = 600,
        metadata=None,
    ):
        _ = (user_id, mime_type, kind, expires_in, size_bytes)
        self.last_metadata = metadata
        self.presign_calls += 1
        file_summary = FileAssetSummaryDTO(
            id=self.presign_calls,
            key=f"test/{filename}",
            status="pending",
            original_filename=filename,
            content_type="text/plain",
            etag=None,
            size=0,
            url=None,
        )
        presigned = PresignedURL(
            url=f"https://example.test/upload/{self.presign_calls}", method=method, expires_in=600
        )
        return file_summary, presigned

    async def generate_upload_presign(
        self,
        *,
        key: str,
        method: str,
        content_type,
        expires_in: int,
    ) -> PresignedURL:
        _ = (content_type, expires_in)
        self.generate_calls += 1
        return PresignedURL(
            url=f"https://example.test/upload/replay/{self.generate_calls}",
            method=method,
            expires_in=600,
        )

    async def get_asset_raw(self, asset_id: int, *, metadata_scope=None):
        self.get_raw_calls.append({"asset_id": asset_id, "metadata_scope": metadata_scope})
        if asset_id in self.blocked_asset_ids:
            raise FileAssetNotFoundException(asset_id)
        return _file_asset(asset_id=asset_id)

    async def get_asset_by_key_raw(self, key: str, *, metadata_scope=None):
        self.get_by_key_raw_calls.append({"key": key, "metadata_scope": metadata_scope})
        if key == "blocked.txt":
            raise FileAssetNotFoundException(key=key)
        return _file_asset(asset_id=17, key=key)

    async def confirm_direct_upload(
        self,
        *,
        asset_id=None,
        key=None,
        metadata_scope=None,
    ):
        self.complete_calls.append(
            {"asset_id": asset_id, "key": key, "metadata_scope": metadata_scope}
        )
        return _file_asset(asset_id=asset_id or 17, key=key)

    async def relay_upload_stream(
        self,
        *,
        user_id,
        file_stream,
        filename: str,
        kind: str,
        content_type=None,
        size_hint=None,
        metadata=None,
        metadata_scope=None,
    ):
        chunks = []
        async for chunk in file_stream:
            chunks.append(chunk)
        self.relay_stream_calls.append(
            {
                "user_id": user_id,
                "filename": filename,
                "kind": kind,
                "content_type": content_type,
                "size_hint": size_hint,
                "metadata": metadata,
                "metadata_scope": metadata_scope,
                "bytes": b"".join(chunks),
            }
        )
        return StorageUploadResponseDTO(
            key=f"uploads/{filename}",
            etag="etag-upload",
            size=sum(len(chunk) for chunk in chunks),
            content_type=content_type,
            url="https://provider.test/upload",
            file_id=31,
            file_status="active",
        )


def _file_asset(*, asset_id: int, key: str | None = None) -> FileAsset:
    now = datetime(2026, 7, 19, tzinfo=timezone.utc)
    return FileAsset(
        id=asset_id,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=key or f"training_material/{asset_id}.txt",
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
        status="pending",
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )


def make_test_app(fake_service: FakeFileAssetService) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(storage_router, prefix="/api/v1")

    store = InMemoryIdempotencyStore()
    idem = IdempotencyService(store=store, lock_ttl_seconds=5, result_ttl_seconds=60)

    app.dependency_overrides[get_file_asset_service] = lambda: fake_service
    app.dependency_overrides[get_idempotency_service] = lambda: idem
    return app


@pytest.mark.asyncio
async def test_presign_upload_idempotent_replay() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    payload = {
        "filename": "a.txt",
        "mime_type": None,
        "size_bytes": 1,
        "kind": "uploads",
        "method": "PUT",
        "expires_in": 600,
    }
    headers = {"Idempotency-Key": "aaaaaaaa"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/v1/storage/presign-upload", json=payload, headers=headers)
        r2 = await client.post("/api/v1/storage/presign-upload", json=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["file"]["id"] == r2.json()["data"]["file"]["id"]
    assert fake.presign_calls == 1
    assert fake.generate_calls == 1
    assert fake.last_metadata["authScope"]["userId"] == "user-admin-001"


@pytest.mark.asyncio
async def test_presign_upload_idempotency_key_reused_with_different_payload() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    payload1 = {
        "filename": "a.txt",
        "mime_type": None,
        "size_bytes": 1,
        "kind": "uploads",
        "method": "PUT",
        "expires_in": 600,
    }
    payload2 = {
        "filename": "b.txt",
        "mime_type": None,
        "size_bytes": 1,
        "kind": "uploads",
        "method": "PUT",
        "expires_in": 600,
    }
    headers = {"Idempotency-Key": "bbbbbbbb"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/api/v1/storage/presign-upload", json=payload1, headers=headers)
        r2 = await client.post("/api/v1/storage/presign-upload", json=payload2, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 422
    assert r2.json()["code"] == 10003


@pytest.mark.asyncio
async def test_presign_upload_stamps_current_user_file_scope() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    payload = {
        "filename": "training-material.txt",
        "mime_type": "text/plain",
        "size_bytes": 1,
        "kind": "training_material",
        "method": "PUT",
        "expires_in": 600,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/storage/presign-upload",
            json=payload,
            headers={"X-Mock-User": "sales"},
        )

    assert response.status_code == 200
    assert fake.last_metadata == {
        "resourceType": "file_asset",
        "usageScope": "training_material",
        "ownerUserId": "user-sales-001",
        "teamId": "team-revenue",
        "authScope": {
            "userId": "user-sales-001",
            "teamId": "team-revenue",
        },
    }


@pytest.mark.asyncio
async def test_confirm_presigned_upload_uses_current_user_metadata_scope() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/storage/complete",
            json={"id": 7},
            headers={"X-Mock-User": "sales"},
        )

    assert response.status_code == 200
    get_scope = fake.get_raw_calls[0]["metadata_scope"]
    confirm_scope = fake.complete_calls[0]["metadata_scope"]
    assert get_scope.user_id == "user-sales-001"
    assert get_scope.team_id == "team-revenue"
    assert get_scope.include_team_scope is False
    assert get_scope.allow_unscoped is False
    assert confirm_scope == get_scope
    assert fake.complete_calls[0]["asset_id"] == 7


@pytest.mark.asyncio
async def test_confirm_presigned_upload_by_key_uses_current_user_scope() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/storage/complete",
            json={"key": "training_material/17.txt"},
            headers={"X-Mock-User": "leader"},
        )

    assert response.status_code == 200
    get_scope = fake.get_by_key_raw_calls[0]["metadata_scope"]
    confirm_scope = fake.complete_calls[0]["metadata_scope"]
    assert get_scope.user_id == "user-leader-001"
    assert get_scope.team_id == "team-revenue"
    assert get_scope.include_team_scope is True
    assert get_scope.allow_unscoped is False
    assert confirm_scope == get_scope
    assert fake.complete_calls[0]["asset_id"] == 17


@pytest.mark.asyncio
async def test_confirm_presigned_upload_rejects_cross_user_asset_before_update() -> None:
    fake = FakeFileAssetService()
    fake.blocked_asset_ids.add(8)
    app = make_test_app(fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/storage/complete",
            json={"id": 8},
            headers={"X-Mock-User": "sales"},
        )

    assert response.status_code == 404
    assert fake.complete_calls == []


@pytest.mark.asyncio
async def test_upload_file_passes_current_user_scope_to_relay_upload_stream() -> None:
    fake = FakeFileAssetService()
    app = make_test_app(fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/storage/upload",
            params={"kind": "training_material"},
            files={"file": ("material.txt", b"hello", "text/plain")},
            headers={"X-Mock-User": "sales"},
        )

    assert response.status_code == 200
    call = fake.relay_stream_calls[0]
    scope = call["metadata_scope"]
    assert scope.user_id == "user-sales-001"
    assert scope.team_id == "team-revenue"
    assert scope.include_team_scope is False
    assert scope.allow_unscoped is False
    assert call["metadata"]["ownerUserId"] == "user-sales-001"
    assert call["metadata"]["teamId"] == "team-revenue"
