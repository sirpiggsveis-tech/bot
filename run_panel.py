"""Control-panel API only — lightweight Render entrypoint (no discord.py).

Run the Discord bot on your PC: python scriptt.py or start.bat
"""

from __future__ import annotations

import os
import sys

print("run_panel: booting…", flush=True)

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from web.api.app import create_app  # noqa: E402
from web.api.config import get_settings  # noqa: E402

get_settings.cache_clear()

_WARNED: list[str] = []


def _warn_missing_env() -> list[str]:
    global _WARNED
    needed = ("DATABASE_URL", "SESSION_SECRET", "PANEL_ADMIN_PASSWORD", "GUILD_ID")
    missing = [k for k in needed if not os.getenv(k, "").strip()]
    if missing and missing != _WARNED:
        print(
            "WARNING: missing environment variables (login/DB may fail until set):\n  - "
            + "\n  - ".join(missing),
            flush=True,
        )
        _WARNED = list(missing)
    return missing


def main() -> None:
    import uvicorn

    _warn_missing_env()
    port = int(os.getenv("PORT", "8000"))
    print(f"run_panel: binding 0.0.0.0:{port} (ping=/ping health=/api/health)", flush=True)
    app = create_app(bot=None)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False,
        timeout_keep_alive=5,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FATAL: {exc}", file=sys.stderr, flush=True)
        raise
