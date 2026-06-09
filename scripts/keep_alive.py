"""Ping the Render panel so the free tier does not sleep (optional).

Run every 10-14 minutes from Windows Task Scheduler, cron, or UptimeRobot:
  python scripts/keep_alive.py

Set RENDER_SERVICE_URL in .env if your Render URL is not the default.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

URL = os.getenv("RENDER_SERVICE_URL", "https://orbat-bot.onrender.com").rstrip("/") + "/ping"


def main() -> int:
    req = urllib.request.Request(URL, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = resp.read(32).decode("utf-8", errors="replace")
            print(f"{resp.status} {URL} -> {body!r}")
            return 0 if resp.status == 200 and body.strip() == "ok" else 1
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code} {URL}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"FAIL {URL}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
