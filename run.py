"""Run the Discord bot and the control-panel API together in one process.

The HTTP API starts first (without loading discord.py) so Render health checks
and the panel login page can respond quickly. The bot connects in the background.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _prepare_local_bundled_panel() -> None:
    dist = os.path.join(os.path.dirname(__file__), "web", "frontend", "dist")
    if not os.path.isdir(dist):
        return
    redirect = os.getenv("OAUTH_REDIRECT_URI", "")
    if "localhost" not in redirect and "127.0.0.1" not in redirect:
        return
    port = os.getenv("PORT", "8000")
    origin = f"http://localhost:{port}"
    os.environ["FRONTEND_ORIGIN"] = origin
    os.environ["POST_LOGIN_REDIRECT"] = origin
    os.environ["OAUTH_REDIRECT_URI"] = f"{origin}/api/auth/callback"


_prepare_local_bundled_panel()

from orbat_db import init_orbat_db  # noqa: E402
from web.api.app import create_app  # noqa: E402
from web.api.config import get_settings  # noqa: E402

get_settings.cache_clear()

_REQUIRED_ENV = (
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DATABASE_URL",
    "SESSION_SECRET",
    "PANEL_ADMIN_PASSWORD",
)


def _require_env() -> None:
    missing = [key for key in _REQUIRED_ENV if not os.getenv(key, "").strip()]
    if missing:
        raise SystemExit(
            "Missing required environment variables on Render:\n  - "
            + "\n  - ".join(missing)
            + "\n\nRender Dashboard -> your service -> Environment -> Add Environment Variable. "
            + "The local .env file is not deployed (gitignored)."
        )


async def _serve_uvicorn(app) -> None:
    import uvicorn

    from web.api.app import frontend_dist

    port = int(os.getenv("PORT", "8000"))
    dist = frontend_dist()
    print("\n--- Control panel API listening ---", flush=True)
    print(f"  http://0.0.0.0:{port}/api/health", flush=True)
    if dist is not None:
        print(f"  Panel UI: http://localhost:{port}/", flush=True)
    print("-----------------------------------\n", flush=True)

    config = uvicorn.Config(
        app, host="0.0.0.0", port=port, log_level="info", access_log=False
    )
    await uvicorn.Server(config).serve()


async def _start_bot(app) -> None:
    """Load discord.py and connect after the API port is already open."""
    try:
        import scriptt

        app.state.bot = scriptt.bot
        scriptt.bot.force_sync_guild_orbat = scriptt.force_sync_guild_orbat  # type: ignore[attr-defined]
        token = scriptt.TOKEN
        if not token:
            print("DISCORD_TOKEN missing — API up, bot offline.", flush=True)
            return
        print("Connecting Discord bot…", flush=True)
        await scriptt.bot.start(token)
    except Exception as exc:
        print(f"Discord bot failed to start (API still up): {exc}", flush=True)


async def _init_db_background() -> None:
    try:
        await asyncio.to_thread(init_orbat_db)
        print("ORBAT database schema ready.", flush=True)
    except Exception as exc:
        print(f"ORBAT database init failed (will retry on use): {exc}", flush=True)


async def main() -> None:
    _require_env()
    app = create_app(bot=None)

    await asyncio.gather(
        _serve_uvicorn(app),
        _start_bot(app),
        _init_db_background(),
    )


if __name__ == "__main__":
    asyncio.run(main())
