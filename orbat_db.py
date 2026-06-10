"""Supabase PostgreSQL persistence for the ORBAT (order of battle) system.

This module is the single source of truth for ORBAT data. It talks to a
Supabase PostgreSQL database through psycopg (v3) using a connection pool.

All public functions are synchronous; callers wrap them in
``asyncio.to_thread(...)``. Rows are returned as plain ``dict`` objects
(``psycopg.rows.dict_row``), so the public return shapes are identical to the
previous SQLite implementation.

Schema overview (per guild):
  settings      one row per guild: embed color, title, rank source, auto-sync
  units         hierarchical org units (parent_id), with order/leader/description
  ranks         configurable rank ladder, each optionally mapped to a Discord role
  positions     configurable position/billet list (e.g. "Squad Leader")
  members       tracked Discord members: rank, position, unit, active, note
  member_roles  snapshot of each member's Discord roles

Members are never deleted on this layer; leaving the guild marks them inactive.
Clearing units keeps every member (their unit becomes NULL).

Configuration:
  DATABASE_URL  Supabase Postgres connection string, e.g.
                postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres
                (or the pooled :6543 connection string for serverless-style use).

The connection pool is created lazily on first database access, so importing
this module never requires a live database. If a database operation is
attempted while DATABASE_URL is unset, a clear, actionable error is raised.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import ConnectionPool

logger = logging.getLogger(__name__)

# Kept for backwards compatibility: other modules / deploy config may still
# reference this name. It is no longer used to locate a SQLite file.
ORBAT_DB_PATH = os.getenv("ORBAT_DB_PATH")

RANK_SOURCE_ROLES = "roles"
RANK_SOURCE_MANUAL = "manual"
DEFAULT_EMBED_COLOR = 0x2F4F4F

# ---------------------------------------------------------------------------
# Connection pool (created lazily on first use)
# ---------------------------------------------------------------------------
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def _validate_database_url(url: str) -> None:
    """Catch common Supabase paste mistakes before we open a connection pool."""
    try:
        info = conninfo_to_dict(url)
    except Exception as exc:
        raise RuntimeError(
            "DATABASE_URL is not a valid PostgreSQL connection string. "
            "Copy the URI again from Supabase -> Project Settings -> Database."
        ) from exc

    host = info.get("host") or ""
    if "@" in host:
        raise RuntimeError(
            "DATABASE_URL is malformed (hostname contains '@'). "
            "This usually means the Supabase URI was pasted incorrectly — "
            "often an extra @ before the host, or a password with @ that "
            "was not URL-encoded.\n\n"
            "Fix in Supabase -> Project Settings -> Database -> Connection string -> URI:\n"
            "  1. Choose 'Session pooler' (port 6543) or 'Direct' (port 5432)\n"
            "  2. Copy the full URI and replace [YOUR-PASSWORD] with your DB password\n"
            "  3. If the password has special characters (@ # : / etc.), reset the "
            "database password to letters and numbers only, OR URL-encode them "
            "(@ becomes %40)\n"
            "Correct shape:\n"
            "  postgresql://postgres.<project-ref>:<password>@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
        )
    if host and "supabase.com" not in host and "supabase.co" not in host:
        logger.warning("DATABASE_URL host %r does not look like Supabase", host)


def _database_url() -> str:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it to your Supabase PostgreSQL "
            "connection string, e.g. "
            "postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres "
            "(or the pooled :6543 connection string). The ORBAT data layer "
            "cannot run without it."
        )
    _validate_database_url(url)
    if "connect_timeout" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}connect_timeout=10"
    return url


def _get_pool() -> ConnectionPool:
    """Return the process-wide connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    conninfo=_database_url(),
                    min_size=0,
                    max_size=3,
                    timeout=10,
                    kwargs={"row_factory": dict_row},
                    name="orbat",
                    open=True,
                )
    return _pool


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_orbat_db() -> None:
    """Create the schema if it does not already exist (idempotent).

    Safe to call at startup. If DATABASE_URL is not configured the call logs a
    warning and returns without raising, so the bot/API can still import and
    boot; the first actual DB operation will raise a clear error instead.
    """
    if not os.getenv("DATABASE_URL"):
        logger.warning(
            "DATABASE_URL is not set; skipping ORBAT schema initialization. "
            "Database operations will fail until DATABASE_URL is configured."
        )
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS settings (
            guild_id BIGINT PRIMARY KEY,
            embed_color INTEGER NOT NULL DEFAULT 3100495,
            title TEXT NOT NULL DEFAULT '',
            rank_source TEXT NOT NULL DEFAULT 'roles',
            auto_sync SMALLINT NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS units (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            parent_id BIGINT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            leader_id BIGINT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (parent_id) REFERENCES units(id) ON DELETE CASCADE
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_units_guild ON units(guild_id)",
        "CREATE INDEX IF NOT EXISTS idx_units_parent ON units(parent_id)",
        """
        CREATE TABLE IF NOT EXISTS ranks (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            abbreviation TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            role_id BIGINT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_ranks_guild ON ranks(guild_id)",
        """
        CREATE TABLE IF NOT EXISTS positions (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_positions_guild ON positions(guild_id)",
        """
        CREATE TABLE IF NOT EXISTS members (
            guild_id BIGINT NOT NULL,
            discord_id BIGINT NOT NULL,
            username TEXT NOT NULL,
            rank TEXT NOT NULL DEFAULT '',
            position TEXT NOT NULL DEFAULT '',
            unit_id BIGINT,
            join_date TEXT NOT NULL,
            active SMALLINT NOT NULL DEFAULT 1,
            note TEXT NOT NULL DEFAULT '',
            rank_locked SMALLINT NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, discord_id),
            FOREIGN KEY (unit_id) REFERENCES units(id) ON DELETE SET NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_members_unit ON members(guild_id, unit_id)",
        """
        CREATE TABLE IF NOT EXISTS member_roles (
            guild_id BIGINT NOT NULL,
            discord_id BIGINT NOT NULL,
            role_id BIGINT NOT NULL,
            role_name TEXT NOT NULL,
            PRIMARY KEY (guild_id, discord_id, role_id)
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_member_roles_member ON member_roles(guild_id, discord_id)",
        # Migrations for databases created by earlier versions. Postgres
        # supports IF NOT EXISTS on ADD COLUMN, so these are idempotent.
        "ALTER TABLE units ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE units ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE units ADD COLUMN IF NOT EXISTS leader_id BIGINT",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS note TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS rank_locked SMALLINT NOT NULL DEFAULT 0",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS nickname TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS global_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE members ADD COLUMN IF NOT EXISTS synced_at TEXT",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS embed_footer TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS show_inactive_in_panel SMALLINT NOT NULL DEFAULT 1",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS member_sort_mode TEXT NOT NULL DEFAULT 'rank'",
        "ALTER TABLE settings ADD COLUMN IF NOT EXISTS roster_show_notes SMALLINT NOT NULL DEFAULT 0",
    ]

    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
        conn.commit()

    try:
        import bot_config_db

        bot_config_db.init_bot_config_db()
    except Exception as exc:
        logger.warning("bot_config schema init skipped: %s", exc)

    try:
        import guild_cache_db

        guild_cache_db.init_guild_cache_db()
    except Exception as exc:
        logger.warning("guild_cache schema init skipped: %s", exc)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def get_settings(guild_id: int) -> dict[str, Any]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM settings WHERE guild_id = %s", (guild_id,))
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO settings (guild_id, embed_color) VALUES (%s, %s)",
                    (guild_id, DEFAULT_EMBED_COLOR),
                )
                conn.commit()
                return {
                    "guild_id": guild_id,
                    "embed_color": DEFAULT_EMBED_COLOR,
                    "title": "",
                    "rank_source": RANK_SOURCE_ROLES,
                    "auto_sync": 1,
                    "embed_footer": "",
                    "show_inactive_in_panel": 1,
                    "member_sort_mode": "rank",
                    "roster_show_notes": 0,
                }
            row = dict(row)
            row.setdefault("embed_footer", "")
            row.setdefault("show_inactive_in_panel", 1)
            row.setdefault("member_sort_mode", "rank")
            row.setdefault("roster_show_notes", 0)
            return row


def update_settings(guild_id: int, **fields: Any) -> None:
    allowed = {
        "embed_color",
        "title",
        "rank_source",
        "auto_sync",
        "embed_footer",
        "show_inactive_in_panel",
        "member_sort_mode",
        "roster_show_notes",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    get_settings(guild_id)  # ensure row exists
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            assignments = ", ".join(f"{key} = %s" for key in updates)
            params = list(updates.values()) + [guild_id]
            cur.execute(
                f"UPDATE settings SET {assignments} WHERE guild_id = %s",
                params,
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
def _next_sort_order(cur: Any, table: str, guild_id: int) -> int:
    cur.execute(
        f"SELECT COALESCE(MAX(sort_order), -1) + 1 AS next FROM {table} WHERE guild_id = %s",
        (guild_id,),
    )
    row = cur.fetchone()
    return int(row["next"])


def create_unit(
    guild_id: int,
    name: str,
    parent_id: int | None = None,
    description: str = "",
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Unit name cannot be empty.")

    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            if parent_id is not None:
                cur.execute(
                    "SELECT id, guild_id FROM units WHERE id = %s",
                    (parent_id,),
                )
                parent = cur.fetchone()
                if parent is None or parent["guild_id"] != guild_id:
                    raise ValueError("Parent unit not found in this server.")

            sort_order = _next_sort_order(cur, "units", guild_id)
            cur.execute(
                """
                INSERT INTO units (guild_id, name, parent_id, sort_order, description, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (guild_id, name, parent_id, sort_order, description.strip(), _utc_now_iso()),
            )
            new_id = int(cur.fetchone()["id"])
        conn.commit()
        return new_id


def get_unit(guild_id: int, unit_id: int) -> dict[str, Any] | None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM units WHERE guild_id = %s AND id = %s",
                (guild_id, unit_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_units(guild_id: int) -> list[dict[str, Any]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, guild_id, name, parent_id, sort_order, description,
                       leader_id, created_at
                FROM units
                WHERE guild_id = %s
                ORDER BY sort_order, lower(name)
                """,
                (guild_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def rename_unit(guild_id: int, unit_id: int, name: str) -> None:
    name = name.strip()
    if not name:
        raise ValueError("Unit name cannot be empty.")
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE units SET name = %s WHERE guild_id = %s AND id = %s",
                (name, guild_id, unit_id),
            )
            if cur.rowcount == 0:
                raise ValueError("Unit not found.")
        conn.commit()


def set_unit_description(guild_id: int, unit_id: int, description: str) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE units SET description = %s WHERE guild_id = %s AND id = %s",
                (description.strip(), guild_id, unit_id),
            )
        conn.commit()


def set_unit_leader(guild_id: int, unit_id: int, leader_id: int | None) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE units SET leader_id = %s WHERE guild_id = %s AND id = %s",
                (leader_id, guild_id, unit_id),
            )
        conn.commit()


def set_unit_order(guild_id: int, unit_id: int, sort_order: int) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE units SET sort_order = %s WHERE guild_id = %s AND id = %s",
                (sort_order, guild_id, unit_id),
            )
        conn.commit()


def _is_descendant(
    units_by_id: dict[int, dict[str, Any]],
    candidate_id: int,
    ancestor_id: int,
) -> bool:
    """True if candidate_id is the same as, or a descendant of, ancestor_id."""
    current: int | None = candidate_id
    seen: set[int] = set()
    while current is not None and current not in seen:
        if current == ancestor_id:
            return True
        seen.add(current)
        parent = units_by_id.get(current)
        current = parent["parent_id"] if parent else None
    return False


def move_unit(guild_id: int, unit_id: int, new_parent_id: int | None) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, parent_id FROM units WHERE guild_id = %s",
                (guild_id,),
            )
            units_by_id = {row["id"]: dict(row) for row in cur.fetchall()}

            if unit_id not in units_by_id:
                raise ValueError("Unit not found.")
            if new_parent_id is not None:
                if new_parent_id not in units_by_id:
                    raise ValueError("Target parent unit not found.")
                if _is_descendant(units_by_id, new_parent_id, unit_id):
                    raise ValueError(
                        "Cannot move a unit under itself or one of its sub-units."
                    )

            cur.execute(
                "UPDATE units SET parent_id = %s WHERE guild_id = %s AND id = %s",
                (new_parent_id, guild_id, unit_id),
            )
        conn.commit()


def delete_unit(guild_id: int, unit_id: int) -> None:
    """Delete one unit; its children and members move up to its parent."""
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT parent_id FROM units WHERE guild_id = %s AND id = %s",
                (guild_id, unit_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("Unit not found.")
            new_parent = row["parent_id"]

            cur.execute(
                "UPDATE units SET parent_id = %s WHERE guild_id = %s AND parent_id = %s",
                (new_parent, guild_id, unit_id),
            )
            cur.execute(
                "UPDATE members SET unit_id = %s WHERE guild_id = %s AND unit_id = %s",
                (new_parent, guild_id, unit_id),
            )
            cur.execute(
                "DELETE FROM units WHERE guild_id = %s AND id = %s",
                (guild_id, unit_id),
            )
        conn.commit()


def clear_units(guild_id: int) -> int:
    """Remove all units for a guild; members stay (unit_id becomes NULL)."""
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET unit_id = NULL WHERE guild_id = %s",
                (guild_id,),
            )
            cur.execute("DELETE FROM units WHERE guild_id = %s", (guild_id,))
            removed = cur.rowcount
        conn.commit()
        return removed


# ---------------------------------------------------------------------------
# Ranks
# ---------------------------------------------------------------------------
def add_rank(
    guild_id: int,
    name: str,
    abbreviation: str = "",
    sort_order: int | None = None,
    role_id: int | None = None,
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Rank name cannot be empty.")
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            if sort_order is None:
                sort_order = _next_sort_order(cur, "ranks", guild_id)
            cur.execute(
                """
                INSERT INTO ranks (guild_id, name, abbreviation, sort_order, role_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (guild_id, name, abbreviation.strip(), sort_order, role_id),
            )
            new_id = int(cur.fetchone()["id"])
        conn.commit()
        return new_id


def get_ranks(guild_id: int) -> list[dict[str, Any]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, guild_id, name, abbreviation, sort_order, role_id
                FROM ranks
                WHERE guild_id = %s
                ORDER BY sort_order DESC, lower(name)
                """,
                (guild_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def remove_rank(guild_id: int, rank_id: int) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM ranks WHERE guild_id = %s AND id = %s",
                (guild_id, rank_id),
            )
        conn.commit()


def set_rank_order(guild_id: int, rank_id: int, sort_order: int) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ranks SET sort_order = %s WHERE guild_id = %s AND id = %s",
                (sort_order, guild_id, rank_id),
            )
        conn.commit()


def set_rank_role(guild_id: int, rank_id: int, role_id: int | None) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE ranks SET role_id = %s WHERE guild_id = %s AND id = %s",
                (role_id, guild_id, rank_id),
            )
        conn.commit()


def rank_order_map(guild_id: int) -> dict[str, int]:
    """Map rank name -> sort_order for sorting members by seniority."""
    return {rank["name"]: rank["sort_order"] for rank in get_ranks(guild_id)}


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------
def add_position(guild_id: int, name: str, sort_order: int | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Position name cannot be empty.")
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            if sort_order is None:
                sort_order = _next_sort_order(cur, "positions", guild_id)
            cur.execute(
                """
                INSERT INTO positions (guild_id, name, sort_order)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (guild_id, name, sort_order),
            )
            new_id = int(cur.fetchone()["id"])
        conn.commit()
        return new_id


def get_positions(guild_id: int) -> list[dict[str, Any]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, guild_id, name, sort_order
                FROM positions
                WHERE guild_id = %s
                ORDER BY sort_order, lower(name)
                """,
                (guild_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def remove_position(guild_id: int, position_id: int) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM positions WHERE guild_id = %s AND id = %s",
                (guild_id, position_id),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------
def sync_member(
    guild_id: int,
    discord_id: int,
    username: str,
    rank: str,
    join_date: str,
    *,
    nickname: str = "",
    global_name: str = "",
) -> None:
    """Insert or refresh a member from a Discord sync.

    Username and active status are always refreshed. Rank is only updated when
    it is not locked (locked = manually set by an admin). Unit, position, note
    are never touched here.
    """
    synced_at = _utc_now_iso()
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT rank_locked FROM members WHERE guild_id = %s AND discord_id = %s",
                (guild_id, discord_id),
            )
            existing = cur.fetchone()

            if existing is None:
                cur.execute(
                    """
                    INSERT INTO members (
                        guild_id, discord_id, username, rank, position,
                        unit_id, join_date, active, note, rank_locked,
                        nickname, global_name, synced_at
                    ) VALUES (%s, %s, %s, %s, '', NULL, %s, 1, '', 0, %s, %s, %s)
                    """,
                    (
                        guild_id,
                        discord_id,
                        username,
                        rank,
                        join_date,
                        nickname,
                        global_name,
                        synced_at,
                    ),
                )
            elif existing["rank_locked"]:
                cur.execute(
                    """
                    UPDATE members SET
                        username = %s, nickname = %s, global_name = %s,
                        active = 1, synced_at = %s
                    WHERE guild_id = %s AND discord_id = %s
                    """,
                    (username, nickname, global_name, synced_at, guild_id, discord_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE members SET
                        username = %s, rank = %s, nickname = %s, global_name = %s,
                        active = 1, synced_at = %s
                    WHERE guild_id = %s AND discord_id = %s
                    """,
                    (
                        username,
                        rank,
                        nickname,
                        global_name,
                        synced_at,
                        guild_id,
                        discord_id,
                    ),
                )
        conn.commit()


def mark_members_inactive_except(guild_id: int, active_ids: set[int]) -> int:
    """Mark members not in *active_ids* as inactive (after a full guild sync)."""
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            if active_ids:
                cur.execute(
                    """
                    UPDATE members SET active = 0
                    WHERE guild_id = %s AND NOT (discord_id = ANY(%s))
                    """,
                    (guild_id, list(active_ids)),
                )
            else:
                cur.execute(
                    "UPDATE members SET active = 0 WHERE guild_id = %s",
                    (guild_id,),
                )
            count = cur.rowcount
        conn.commit()
        return count


def set_member_nickname(guild_id: int, discord_id: int, nickname: str) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET nickname = %s WHERE guild_id = %s AND discord_id = %s",
                (nickname, guild_id, discord_id),
            )
        conn.commit()


def set_member_active(guild_id: int, discord_id: int, active: bool) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET active = %s WHERE guild_id = %s AND discord_id = %s",
                (1 if active else 0, guild_id, discord_id),
            )
        conn.commit()


def set_member_unit(guild_id: int, discord_id: int, unit_id: int | None) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET unit_id = %s WHERE guild_id = %s AND discord_id = %s",
                (unit_id, guild_id, discord_id),
            )
        conn.commit()


def set_member_rank(
    guild_id: int,
    discord_id: int,
    rank: str,
    *,
    lock: bool = True,
) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE members SET rank = %s, rank_locked = %s
                WHERE guild_id = %s AND discord_id = %s
                """,
                (rank, 1 if lock else 0, guild_id, discord_id),
            )
        conn.commit()


def set_member_position(guild_id: int, discord_id: int, position: str) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET position = %s WHERE guild_id = %s AND discord_id = %s",
                (position, guild_id, discord_id),
            )
        conn.commit()


def set_member_note(guild_id: int, discord_id: int, note: str) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET note = %s WHERE guild_id = %s AND discord_id = %s",
                (note, guild_id, discord_id),
            )
        conn.commit()


def get_member(guild_id: int, discord_id: int) -> dict[str, Any] | None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM members WHERE guild_id = %s AND discord_id = %s",
                (guild_id, discord_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_members(guild_id: int, *, active_only: bool = False) -> list[dict[str, Any]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT guild_id, discord_id, username, rank, position,
                       unit_id, join_date, active, note, rank_locked,
                       nickname, global_name, synced_at
                FROM members
                WHERE guild_id = %s
            """
            params: list[Any] = [guild_id]
            if active_only:
                query += " AND active = 1"
            query += " ORDER BY lower(username)"
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def replace_member_roles(
    guild_id: int,
    discord_id: int,
    roles: list[tuple[int, str]],
) -> None:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM member_roles WHERE guild_id = %s AND discord_id = %s",
                (guild_id, discord_id),
            )
            if roles:
                cur.executemany(
                    """
                    INSERT INTO member_roles (guild_id, discord_id, role_id, role_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [(guild_id, discord_id, rid, rname) for rid, rname in roles],
                )
        conn.commit()


def get_member_roles_map(guild_id: int) -> dict[int, list[str]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT discord_id, role_name
                FROM member_roles
                WHERE guild_id = %s
                ORDER BY lower(role_name)
                """,
                (guild_id,),
            )
            result: dict[int, list[str]] = {}
            for row in cur.fetchall():
                result.setdefault(row["discord_id"], []).append(row["role_name"])
            return result


def get_member_role_ids_map(guild_id: int) -> dict[int, set[int]]:
    with _get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT discord_id, role_id FROM member_roles WHERE guild_id = %s",
                (guild_id,),
            )
            result: dict[int, set[int]] = {}
            for row in cur.fetchall():
                result.setdefault(row["discord_id"], set()).add(row["role_id"])
            return result


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def format_units_tree(units: list[dict[str, Any]]) -> str:
    if not units:
        return "_No units configured. Use `/orbatconfig` to add platoons or teams._"

    by_parent: dict[int | None, list[dict[str, Any]]] = {}
    for unit in units:
        by_parent.setdefault(unit["parent_id"], []).append(unit)

    lines: list[str] = []

    def walk(parent_id: int | None, depth: int) -> None:
        children = sorted(
            by_parent.get(parent_id, []),
            key=lambda u: (u.get("sort_order", 0), u["name"].lower()),
        )
        for unit in children:
            indent = "\u2003" * depth
            lines.append(f"{indent}\u2022 **{unit['name']}** `#{unit['id']}`")
            walk(unit["id"], depth + 1)

    walk(None, 0)
    return "\n".join(lines)
