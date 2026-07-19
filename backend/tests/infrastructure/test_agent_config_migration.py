from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRE_BINDINGS_REVISION = "4a19c8e2d7b5"


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def _db_url(db_path: Path) -> str:
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def test_agent_config_bindings_migration_backfills_and_defaults(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "agent-config-migration.db"
    monkeypatch.setenv("DATABASE__URL", _db_url(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)

    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", _db_url(db_path))
    command.upgrade(config, PRE_BINDINGS_REVISION)

    timestamp = datetime(2026, 7, 19, tzinfo=timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO agent_configs (
                name,
                system_prompt,
                model,
                temperature,
                max_tokens,
                metadata,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-agent",
                "legacy prompt",
                "gpt-test",
                0.5,
                128,
                json.dumps({"ownerUserId": "user-sales-001", "teamId": "team-revenue"}),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()

    command.upgrade(config, "head")

    with _connect(db_path) as conn:
        columns = {
            row["name"]: row
            for row in conn.execute("PRAGMA table_info(agent_configs)").fetchall()
        }
        assert columns["tool_ids"]["notnull"] == 1
        assert columns["mcp_server_ids"]["notnull"] == 1

        legacy_row = conn.execute(
            "SELECT tool_ids, mcp_server_ids FROM agent_configs WHERE name = ?",
            ("legacy-agent",),
        ).fetchone()
        assert json.loads(legacy_row["tool_ids"]) == []
        assert json.loads(legacy_row["mcp_server_ids"]) == []

        conn.execute(
            """
            INSERT INTO agent_configs (
                name,
                system_prompt,
                model,
                temperature,
                max_tokens,
                metadata,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "new-agent",
                None,
                "gpt-test",
                None,
                None,
                json.dumps({}),
                timestamp,
                timestamp,
            ),
        )
        conn.commit()

        new_row = conn.execute(
            "SELECT tool_ids, mcp_server_ids FROM agent_configs WHERE name = ?",
            ("new-agent",),
        ).fetchone()
        assert json.loads(new_row["tool_ids"]) == []
        assert json.loads(new_row["mcp_server_ids"]) == []
