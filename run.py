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

import scriptt  # noqa: E402  (import after load_dotenv on purpose)
from web.api.app import create_app  # noqa: E402


async def _serve_api() -> None:
    import uvicorn

    app = create_app(bot=scriptt.bot)
    # Expose the bot's sync helper on the bot object for the API to call.
    scriptt.bot.force_sync_guild_orbat = scriptt.force_sync_guild_orbat  # type: ignore[attr-defined]

    port = int(os.getenv("PORT", "8000"))
    config = uvicorn.Config(
        app, host="0.0.0.0", port=port, log_level="info", access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    token = scriptt.TOKEN
    if not token:
        raise SystemExit("Set DISCORD_TOKEN in the environment / .env")

    await asyncio.gather(
        scriptt.bot.start(token),
        _serve_api(),
    )


if __name__ == "__main__":
    asyncio.run(main())
