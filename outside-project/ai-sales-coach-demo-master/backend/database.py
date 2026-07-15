# coding=utf-8
"""SQLite 数据库初始化与连接池（使用 aiosqlite 异步驱动）"""

import aiosqlite
import config

DB_PATH = config.DB_PATH

CREATE_TABLES_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS groups (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    username   TEXT    NOT NULL UNIQUE,
    password   TEXT    NOT NULL,
    role       TEXT    NOT NULL DEFAULT 'staff',  -- admin / leader / staff
    group_id   INTEGER DEFAULT 1,
    token      TEXT    UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(group_id) REFERENCES groups(id)
);

CREATE TABLE IF NOT EXISTS training_dimension (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT,
    status      INTEGER NOT NULL DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_scenario (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    difficulty  INTEGER NOT NULL DEFAULT 2,
    persona     TEXT,
    scene_desc  TEXT,
    opening     TEXT,
    is_required INTEGER NOT NULL DEFAULT 0,
    status      INTEGER NOT NULL DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 场景与维度的多对多关联（含权重）
CREATE TABLE IF NOT EXISTS scenario_dimension (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id  INTEGER NOT NULL,
    dimension_id INTEGER NOT NULL,
    weight       INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY(scenario_id)  REFERENCES training_scenario(id),
    FOREIGN KEY(dimension_id) REFERENCES training_dimension(id)
);

CREATE TABLE IF NOT EXISTS training_session (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    scenario_id INTEGER NOT NULL,
    status      INTEGER NOT NULL DEFAULT 0,
    -- 0=进行中, 1=已结束, 2=已评分, 3=评分失败
    duration_sec INTEGER,
    message_count INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    ended_at    DATETIME,
    FOREIGN KEY(user_id)     REFERENCES users(id),
    FOREIGN KEY(scenario_id) REFERENCES training_scenario(id)
);

CREATE TABLE IF NOT EXISTS training_message (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    seq        INTEGER NOT NULL,
    role       INTEGER NOT NULL,  -- 1=customer(AI), 2=sales(human)
    content    TEXT    NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES training_session(session_id)
);

CREATE TABLE IF NOT EXISTS training_score (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT    NOT NULL UNIQUE,
    total_score      INTEGER,
    dimension_scores TEXT,   -- JSON
    summary          TEXT,
    highlights       TEXT,   -- JSON array
    suggestions      TEXT,   -- JSON array
    status           INTEGER NOT NULL DEFAULT 0,
    -- 0=评分中, 1=完成, 2=异常
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(session_id) REFERENCES training_session(session_id)
);

CREATE TABLE IF NOT EXISTS ai_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    usage_date TEXT    NOT NULL,
    scope_type TEXT    NOT NULL, -- user / ip
    scope_key  TEXT    NOT NULL,
    action     TEXT    NOT NULL, -- chat / score
    count      INTEGER NOT NULL DEFAULT 0,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(usage_date, scope_type, scope_key, action)
);

CREATE INDEX IF NOT EXISTS idx_session_user    ON training_session(user_id);
CREATE INDEX IF NOT EXISTS idx_session_scenario ON training_session(scenario_id);
CREATE INDEX IF NOT EXISTS idx_message_session  ON training_message(session_id, seq);
CREATE INDEX IF NOT EXISTS idx_score_session    ON training_score(session_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_lookup  ON ai_usage(usage_date, scope_type, scope_key, action);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()


def get_db():
    return aiosqlite.connect(DB_PATH)
