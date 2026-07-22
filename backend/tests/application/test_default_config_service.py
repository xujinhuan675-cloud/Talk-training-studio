from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from application.services.stakeholder.default_config_service import (
    DEFAULT_PERSONA_PRESETS,
    DEFAULT_SCENARIO_PRESETS,
    seed_default_stakeholder_config,
)
from infrastructure.models.base import Base
from infrastructure.unit_of_work import SQLAlchemyUnitOfWork


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def _uow_factory(session_factory):
    def factory(**kwargs):
        return SQLAlchemyUnitOfWork(session_factory=session_factory, **kwargs)

    return factory


@pytest.mark.asyncio
async def test_seed_default_stakeholder_config_creates_defaults_once(
    session_factory,
    tmp_path,
) -> None:
    persona_dir = tmp_path / "personas"

    first = await seed_default_stakeholder_config(
        uow_factory=_uow_factory(session_factory),
        persona_dir=persona_dir,
    )
    second = await seed_default_stakeholder_config(
        uow_factory=_uow_factory(session_factory),
        persona_dir=persona_dir,
    )

    assert first.persona_files_created == len(DEFAULT_PERSONA_PRESETS)
    assert first.organizations_created >= 3
    assert first.teams_created >= 10
    assert first.scenarios_created == len(DEFAULT_SCENARIO_PRESETS)
    assert second.changed is False

    async with _uow_factory(session_factory)(readonly=True) as uow:
        orgs = await uow.organization_repository.list_all(limit=100)
        scenarios = await uow.scenario_repository.list_all(limit=100)

    assert {org.name for org in orgs} >= {"星瀚科技", "澜舟零售", "云杉企业服务"}
    assert {scenario.name for scenario in scenarios} >= {
        "季度预算评审会",
        "产品路线优先级冲突",
        "高价值客户投诉升级",
    }
    assert (persona_dir / "tw-cfo-li-na.md").exists()
    assert "organization_id:" in (persona_dir / "tw-cfo-li-na.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_seed_default_stakeholder_config_does_not_overwrite_existing_persona(
    session_factory,
    tmp_path,
) -> None:
    persona_dir = tmp_path / "personas"
    persona_dir.mkdir()
    existing = persona_dir / "tw-cfo-li-na.md"
    existing.write_text("custom persona", encoding="utf-8")

    await seed_default_stakeholder_config(
        uow_factory=_uow_factory(session_factory),
        persona_dir=persona_dir,
    )

    assert existing.read_text(encoding="utf-8") == "custom persona"
