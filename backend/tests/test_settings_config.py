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


def test_settings_uses_newapi_access_token_as_llm_gateway_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "LLM__API_KEY",
        "LLM__BASE_URL",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setenv("NEWAPI_ACCESS_TOKEN", "newapi-token")

    settings = Settings(_env_file=None)

    assert settings.llm.api_key == "newapi-token"
    assert settings.llm.base_url == "https://newapi.example/v1"


def test_settings_uses_explicit_newapi_gateway_base_url_for_llm_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "LLM__API_KEY",
        "LLM__BASE_URL",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("NEWAPI_BASE_URL", "https://newapi.example")
    monkeypatch.setenv("NEWAPI_GATEWAY_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("NEWAPI_ACCESS_TOKEN", "newapi-token")

    settings = Settings(_env_file=None)

    assert settings.llm.api_key == "newapi-token"
    assert settings.llm.base_url == "https://gateway.example/v1"
