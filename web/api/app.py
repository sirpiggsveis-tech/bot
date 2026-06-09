"""FastAPI application factory for the control panel."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import auth, orbat

_FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def frontend_dist() -> Path | None:
    return _FRONTEND_DIST if _FRONTEND_DIST.is_dir() else None


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React panel from the same server (local / single-host deploy)."""
    dist = frontend_dist()
    if dist is None:
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    async def spa_root():
        return FileResponse(dist / "index.html")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        candidate = dist / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


def create_app(bot: Any | None = None) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="ORBAT Control Panel API", version="1.0.0")
    app.state.bot = bot

    origins = {
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    }
    if frontend_dist() is not None:
        port = settings.local_port
        origins.update(
            {
                f"http://localhost:{port}",
                f"http://127.0.0.1:{port}",
            }
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o for o in origins if o],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        dist = frontend_dist()
        return {
            "ok": True,
            "panel_login_configured": settings.panel_login_configured,
            "guild_id": str(settings.guild_id) if settings.guild_id else None,
            "bot_attached": app.state.bot is not None,
            "frontend_bundled": dist is not None,
        }

    app.include_router(auth.router)
    app.include_router(orbat.router)
    _mount_frontend(app)
    return app
