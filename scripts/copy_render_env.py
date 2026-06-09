"""Write Render env vars from .env to a local paste file (never commit this file)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

RENDER_URL = os.getenv("RENDER_SERVICE_URL", "https://orbat-bot.onrender.com").rstrip("/")
PAGES_URL = os.getenv("PAGES_URL", "").strip()

# Keys to copy into Render. Production URLs override local .env values.
KEYS = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DATABASE_URL",
    "SESSION_SECRET",
    "PANEL_ADMIN_USERNAME",
    "PANEL_ADMIN_PASSWORD",
]

OUT = ROOT / "render-env-paste.txt"


def _validate_database_url(url: str) -> str | None:
    try:
        from psycopg.conninfo import conninfo_to_dict

        host = conninfo_to_dict(url).get("host") or ""
        if "@" in host:
            return (
                "DATABASE_URL looks WRONG (hostname contains '@'). "
                "Re-copy from Supabase -> Database -> Connection string -> URI. "
                "Use postgres.<project-ref>:password@host — not an extra @ before the host."
            )
    except Exception:
        return "DATABASE_URL could not be parsed — re-copy from Supabase."
    return None


def main() -> int:
    lines: list[str] = [
        "Paste these into Render -> your service -> Environment",
        "(Delete this file after pasting — it contains secrets)",
        "",
    ]

    for key in KEYS:
        val = os.getenv(key, "").strip()
        if val:
            lines.append(f"{key}={val}")

    db_warn = _validate_database_url(os.getenv("DATABASE_URL", ""))
    if db_warn:
        lines.extend(["", f"!!! {db_warn}", ""])

    if PAGES_URL.startswith("http"):
        lines.append(f"FRONTEND_ORIGIN={PAGES_URL}")
    lines.append("SESSION_COOKIE_SAMESITE=lax")
    lines.append("SESSION_COOKIE_SECURE=1")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print("Open it, copy each line into Render Environment, then delete the file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
