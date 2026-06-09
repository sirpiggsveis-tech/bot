"""FastAPI application factory for the control panel."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import auth, orbat


def create_app(bot: Any | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ORBAT Control Panel API", version="1.0.0")
    app.state.bot = bot

    origins = {settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"}
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in origins if o],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        return {
            "ok": True,
            "oauth_configured": settings.oauth_configured,
            "guild_id": str(settings.guild_id) if settings.guild_id else None,
            "bot_attached": app.state.bot is not None,
        }

    app.include_router(auth.router)
    app.include_router(orbat.router)
    return app
