from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from domain.conversation.repository import OwnedMetadataScope
from domain.file_asset.entity import FileAsset
from infrastructure.models.base import Base
from infrastructure.repositories.file_asset_repository import SQLAlchemyFileAssetRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        yield db

    await engine.dispose()


def _asset(filename: str, day: int, metadata: dict) -> FileAsset:
    created_at = datetime(2026, 7, day, tzinfo=timezone.utc)
    return FileAsset(
        id=None,
        owner_id=None,
        storage_type="local",
        bucket=None,
        region=None,
        key=f"training_material/{filename}",
        size=1,
        content_type="text/plain",
        original_filename=filename,
        kind="training_material",
        metadata=metadata,
        status="active",
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.mark.asyncio
async def test_file_asset_repository_filters_metadata_scope_before_pagination(session) -> None:
    repo = SQLAlchemyFileAssetRepository(session)
    await repo.create(
        _asset(
            "hidden-newest.txt",
            19,
            {"ownerUserId": "user-cs-001", "teamId": "team-service"},
        )
    )
    visible = await repo.create(
        _asset(
            "visible-user.txt",
            18,
            {
                "ownerUserId": "user-sales-001",
                "teamId": "team-revenue",
                "authScope": {"userId": "user-sales-001", "teamId": "team-revenue"},
            },
        )
    )
    await repo.create(
        _asset(
            "visible-team.txt",
            17,
            {"teamId": "team-revenue", "usageScope": "training_material"},
        )
    )
    await repo.create(_asset("unscoped.txt", 16, {}))

    staff_scope = OwnedMetadataScope(
        user_id="user-sales-001",
        team_id="team-revenue",
        include_team_scope=False,
        allow_unscoped=False,
    )
    leader_scope = OwnedMetadataScope(
        user_id="user-leader-001",
        team_id="team-revenue",
        include_team_scope=True,
        allow_unscoped=False,
    )

    first_staff_page = await repo.list(
        kind="training_material",
        status="active",
        skip=0,
        limit=1,
        metadata_scope=staff_scope,
    )
    staff_assets = await repo.list(
        kind="training_material",
        status="active",
        skip=0,
        limit=10,
        metadata_scope=staff_scope,
    )
    leader_assets = await repo.list(
        kind="training_material",
        status="active",
        skip=0,
        limit=10,
        metadata_scope=leader_scope,
    )

    assert [asset.original_filename for asset in first_staff_page] == ["visible-user.txt"]
    assert [asset.original_filename for asset in staff_assets] == [
        "visible-user.txt",
        "visible-team.txt",
    ]
    assert await repo.count(kind="training_material", status="active", metadata_scope=staff_scope) == 2
    assert [asset.original_filename for asset in leader_assets] == [
        "visible-user.txt",
        "visible-team.txt",
    ]
    assert await repo.get_by_id(visible.id or 0, metadata_scope=staff_scope) is not None
    assert await repo.get_by_key("training_material/hidden-newest.txt", metadata_scope=staff_scope) is None
