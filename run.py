"""Run the Discord bot and the control-panel API together in one process.

This is the entrypoint for the Render deployment. Running the bot by itself is
still possible with `python scriptt.py`.
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv

# Load env before importing the bot so things like ORBAT_DB_PATH are honored.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def _prepare_local_bundled_panel() -> None:
    """When the built UI is served from this server, align OAuth redirect URLs."""
    dist = os.path.join(os.path.dirname(__file__), "web", "frontend", "dist")
    if not os.path.isdir(dist):
        return
    redirect = os.getenv("OAUTH_REDIRECT_URI", "")
    if "localhost" not in redirect and "127.0.0.1" not in redirect:
        return
    port = os.getenv("PORT", "8000")
    origin = f"http://localhost:{port}"
    callback = f"{origin}/api/auth/callback"
    os.environ["FRONTEND_ORIGIN"] = origin
    os.environ["POST_LOGIN_REDIRECT"] = origin
    if redirect != callback:
        os.environ["OAUTH_REDIRECT_URI"] = callback
        print(
            f"\nNOTE: Using bundled panel at {origin}/",
            flush=True,
        )
        print(
            "      Add this Discord OAuth redirect if you have not already:",
            flush=True,
        )
        print(f"        {callback}\n",
              flush=True,
        )


_prepare_local_bundled_panel()

import scriptt  # noqa: E402  (import after load_dotenv on purpose)
from web.api.app import create_app  # noqa: E402
from web.api.config import get_settings  # noqa: E402

get_settings.cache_clear()


async def _serve_api() -> None:
    import uvicorn

    from web.api.app import frontend_dist

    app = create_app(bot=scriptt.bot)
    # Expose the bot's sync helper on the bot object for the API to call.
    scriptt.bot.force_sync_guild_orbat = scriptt.force_sync_guild_orbat  # type: ignore[attr-defined]

    port = int(os.getenv("PORT", "8000"))
    dist = frontend_dist()
    print("\n--- Control panel ---", flush=True)
    if dist is not None:
        print(f"  Open in browser: http://localhost:{port}/", flush=True)
    else:
        print(
            f"  API only (no built UI yet): http://localhost:{port}/api/health",
            flush=True,
        )
        print(
            "  Build the panel: cd web/frontend && npm install && npm run build",
            flush=True,
        )
        print(f"  Or run the UI dev server: npm run dev  (API stays on port {port})",
              flush=True)
    print("---------------------\n", flush=True)

    config = uvicorn.Config(
        app, host="0.0.0.0", port=port, log_level="info", access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()


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


async def main() -> None:
    _require_env()
    token = scriptt.TOKEN
    if not token:
        raise SystemExit("DISCORD_TOKEN is empty. Check the value in Render Environment.")

    await asyncio.gather(
        scriptt.bot.start(token),
        _serve_api(),
    )


if __name__ == "__main__":
    asyncio.run(main())
