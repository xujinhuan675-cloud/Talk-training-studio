from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import main


class _SeedResult:
    persona_files_created = 1
    organizations_created = 2
    teams_created = 3
    scenarios_created = 4


async def _noop_async(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_lifespan_invokes_default_config_seed(monkeypatch) -> None:
    calls = {}

    async def fake_seed(*, uow_factory, persona_dir):
        calls["uow_factory"] = uow_factory
        calls["persona_dir"] = persona_dir
        return _SeedResult()

    monkeypatch.setattr(main.settings, "AUTO_RUN_MIGRATIONS", False)
    monkeypatch.setattr(main.settings, "DEBUG", False)
    monkeypatch.setattr(main.settings.redis, "url", None)
    monkeypatch.setattr(main.settings.tracing, "enabled", False)
    monkeypatch.setattr(main, "seed_default_stakeholder_config", fake_seed)
    monkeypatch.setattr(main, "init_storage_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_storage_client", _noop_async)
    monkeypatch.setattr(main, "get_storage_config", lambda: SimpleNamespace(type="local", bucket=None))
    monkeypatch.setattr(main, "init_llm_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_llm_client", _noop_async)
    monkeypatch.setattr(main, "init_anthropic_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_anthropic_client", _noop_async)
    monkeypatch.setattr(main, "init_agent_sdk_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_agent_sdk_client", _noop_async)
    monkeypatch.setattr(main, "init_tts_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_tts_client", _noop_async)
    monkeypatch.setattr(main, "init_stt_client", _noop_async)
    monkeypatch.setattr(main, "shutdown_stt_client", _noop_async)

    async with main.lifespan(FastAPI()):
        pass

    assert calls == {
        "uow_factory": main.SQLAlchemyUnitOfWork,
        "persona_dir": main.settings.stakeholder.persona_dir,
    }
