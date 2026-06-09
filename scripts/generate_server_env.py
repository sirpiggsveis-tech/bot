"""Build server.env from local .env for Docker / Oracle VM deploy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

KEYS = [
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DATABASE_URL",
    "SESSION_SECRET",
    "PANEL_ADMIN_USERNAME",
    "PANEL_ADMIN_PASSWORD",
    "FRONTEND_ORIGIN",
    "POST_LOGIN_REDIRECT",
    "CLOUDFLARE_TUNNEL_TOKEN",
]

OUT = ROOT / "server.env"


def main() -> int:
    pages = os.getenv("PAGES_URL", "").strip()
    lines: list[str] = [
        "# Copy to server as ~/bot/.env  (scp server.env user@vm:~/bot/.env)",
        "# Delete this file after copying — it contains secrets.",
        "",
    ]

    for key in KEYS:
        val = os.getenv(key, "").strip()
        if val:
            lines.append(f"{key}={val}")

    if pages.startswith("http") and not os.getenv("FRONTEND_ORIGIN"):
        lines.append(f"FRONTEND_ORIGIN={pages}")
        lines.append(f"POST_LOGIN_REDIRECT={pages}")

    lines.extend(
        [
            "SESSION_COOKIE_SAMESITE=lax",
            "SESSION_COOKIE_SECURE=1",
            "",
        ]
    )

    missing = [k for k in ("DISCORD_TOKEN", "GUILD_ID", "DATABASE_URL", "PANEL_ADMIN_PASSWORD") if not os.getenv(k)]
    if missing:
        print("MISSING in .env:", ", ".join(missing))
        return 1

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print("Upload:  scp server.env ubuntu@YOUR_VM_IP:~/bot/.env")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
