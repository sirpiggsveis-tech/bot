"""Write monkey-env-paste.txt for Monkey Network variable panel."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

KEYS = (
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DATABASE_URL",
    "PD_ROLE_ID",
)

OUT = ROOT / "monkey-env-paste.txt"


def main() -> int:
    lines = [
        "Paste into Monkey Network → your server → Variables / Environment",
        "(Delete this file after pasting — secrets)",
        "",
    ]
    missing = []
    for key in KEYS[:3]:
        val = os.getenv(key, "").strip()
        if val:
            lines.append(f"{key}={val}")
        else:
            missing.append(key)
    for key in KEYS[3:]:
        val = os.getenv(key, "").strip()
        if val:
            lines.append(f"{key}={val}")

    if missing:
        print("MISSING in .env:", ", ".join(missing))
        return 1

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
