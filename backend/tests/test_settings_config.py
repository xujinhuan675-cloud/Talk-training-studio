from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings


def test_settings_accepts_app_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("APP_NAME", "kit-service")
    monkeypatch.setenv("APP_VERSION", "9.9.9")

    settings = Settings(_env_file=None)

    assert settings.PROJECT_NAME == "kit-service"
    assert settings.VERSION == "9.9.9"


def test_settings_rejects_unknown_env_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setenv("SECRET_KEY", "test-secret")

    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=test-secret\nUNKNOWN_KEY=oops\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        Settings(_env_file=str(env_file))


def test_settings_loads_capability_inventory_from_nested_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv(
        "CAPABILITY_INVENTORY__TOOL_CONFIGS",
        '[{"id":"crm.lookup","name":"CRM Lookup","requires_mcp":true,"mcp_server":"crm"}]',
    )
    monkeypatch.setenv(
        "CAPABILITY_INVENTORY__MCP_SERVERS",
        '[{"id":"crm","name":"CRM MCP","transport":"stdio","command":"npx"}]',
    )
    monkeypatch.setenv("CAPABILITY_INVENTORY__AGENT_CONFIG_SCAN_LIMIT", "3")

    settings = Settings(_env_file=None)

    assert settings.capability_inventory.tool_configs == [
        {
            "id": "crm.lookup",
            "name": "CRM Lookup",
            "requires_mcp": True,
            "mcp_server": "crm",
        }
    ]
    assert settings.capability_inventory.mcp_servers == [
        {
            "id": "crm",
            "name": "CRM MCP",
            "transport": "stdio",
            "command": "npx",
        }
    ]
    assert settings.capability_inventory.agent_config_scan_limit == 3
