"""Zip the Discord bot for free hosts (Monkey Network, Wispbyte, etc.).

Creates bot-deploy.zip in the project root — upload and unzip on the host.
Does NOT include the web panel or node_modules.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bot-deploy.zip"

INCLUDE = [
    "scriptt.py",
    "orbat_db.py",
    "bot_config_db.py",
    "requirements-bot.txt",
    "pd_config.json",
    "autorole_config.json",
    "squad_config.json",
]

INCLUDE_DIRS: list[str] = []


def main() -> int:
    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in INCLUDE:
            path = ROOT / name
            if path.is_file():
                zf.write(path, name)
            else:
                print(f"skip missing: {name}")

        readme = (
            "ORBAT Discord bot — upload to free host\n"
            "1. Unzip this folder\n"
            "2. pip install -r requirements-bot.txt\n"
            "3. Set env: DISCORD_TOKEN, GUILD_ID, DATABASE_URL\n"
            "4. Start: python scriptt.py\n"
        )
        zf.writestr("README-DEPLOY.txt", readme)

    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    print("Upload to your free bot host, then set env vars and run: python scriptt.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
