"""Bot configuration (PD, auto-role, squads) in Supabase PostgreSQL.

Shared by the Discord bot and the web panel API so configs edited on Render
reach the bot on the next read (no local JSON required on Render).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

CONFIG_KEYS = ("pd", "autorole", "squad")

# Legacy JSON paths (migrated into DB on first read).
_JSON_PATHS: dict[str, str] = {
    "pd": "pd_config.json",
    "autorole": "autorole_config.json",
    "squad": "squad_config.json",
}


def _root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _pool_get() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from orbat_db import _database_url

                _pool = ConnectionPool(
                    conninfo=_database_url(),
                    min_size=0,
                    max_size=3,
                    timeout=10,
                    kwargs={"row_factory": dict_row},
                    name="bot_config",
                    open=True,
                )
    return _pool


def init_bot_config_db() -> None:
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not set; skipping bot_config schema init")
        return
    with _pool_get().connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_guild_config (
                guild_id BIGINT NOT NULL,
                config_key TEXT NOT NULL,
                data JSONB NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, config_key)
            )
            """
        )
        conn.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _migrate_json_file(config_key: str) -> dict[str, Any]:
    path = os.path.join(_root(), _JSON_PATHS[config_key])
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return {}


def load_config_store(config_key: str) -> dict[str, Any]:
    """Return {guild_id_str: config_dict} for a config type."""
    if config_key not in CONFIG_KEYS:
        raise ValueError(f"Unknown config key: {config_key}")

    init_bot_config_db()
    store: dict[str, Any] = {}
    with _pool_get().connection() as conn:
        rows = conn.execute(
            "SELECT guild_id, data FROM bot_guild_config WHERE config_key = %s",
            (config_key,),
        ).fetchall()
        for row in rows:
            store[str(row["guild_id"])] = row["data"]

    if not store:
        legacy = _migrate_json_file(config_key)
        if legacy:
            save_config_store(config_key, legacy)
            return legacy
    return store


def save_config_store(config_key: str, store: dict[str, Any]) -> None:
    if config_key not in CONFIG_KEYS:
        raise ValueError(f"Unknown config key: {config_key}")

    init_bot_config_db()
    now = _utc_now()
    with _pool_get().connection() as conn:
        for guild_id_str, data in store.items():
            conn.execute(
                """
                INSERT INTO bot_guild_config (guild_id, config_key, data, updated_at)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (guild_id, config_key)
                DO UPDATE SET data = EXCLUDED.data, updated_at = EXCLUDED.updated_at
                """,
                (int(guild_id_str), config_key, json.dumps(data), now),
            )
        conn.commit()


def get_guild_config(guild_id: int, config_key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    store = load_config_store(config_key)
    key = str(guild_id)
    if key not in store:
        store[key] = dict(defaults)
    data = store[key]
    for k, v in defaults.items():
        data.setdefault(k, v if not isinstance(v, list) else list(v))
    return data


def set_guild_config(guild_id: int, config_key: str, guild_data: dict[str, Any]) -> None:
    store = load_config_store(config_key)
    store[str(guild_id)] = guild_data
    save_config_store(config_key, store)
