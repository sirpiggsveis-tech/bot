"""Control-panel API only — use this on Render (lightweight, no discord.py).

Run the Discord bot separately on your PC:  python scriptt.py
(or use start.bat)
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from web.api.app import create_app  # noqa: E402
from web.api.config import get_settings  # noqa: E402

get_settings.cache_clear()

_REQUIRED = ("DATABASE_URL", "SESSION_SECRET", "PANEL_ADMIN_PASSWORD", "GUILD_ID")


def _require_env() -> None:
    missing = [k for k in _REQUIRED if not os.getenv(k, "").strip()]
    if missing:
        raise SystemExit(
            "Missing on Render:\n  - "
            + "\n  - ".join(missing)
            + "\n\nAdd them in Render -> Environment."
        )
    print("Panel API env OK (bot is not started by this process).", flush=True)


def main() -> None:
    import uvicorn

    _require_env()
    port = int(os.getenv("PORT", "8000"))
    app = create_app(bot=None)
    print(f"Panel API on http://0.0.0.0:{port}/api/health", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
