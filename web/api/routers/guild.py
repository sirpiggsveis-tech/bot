"""Guild directory and sync status from the Supabase cache (no live bot required)."""

from __future__ import annotations

import asyncio
import os

from fastapi import APIRouter, Depends, HTTPException, status

import guild_cache_db

from ..config import Settings, get_settings
from ..discord_rest import fetch_guild_directory as live_guild_directory
from ..security import CurrentUser, get_current_user, require_write

router = APIRouter(prefix="/api/guild", tags=["guild"])


def _gid(settings: Settings) -> int:
    if not settings.guild_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GUILD_ID not set")
    return settings.guild_id


async def _run(func, *args, **kwargs):
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Database error: {exc}",
        ) from exc


def _empty_directory(sync: dict) -> dict:
    return {
        "text_channels": [],
        "voice_channels": [],
        "categories": [],
        "roles": [],
        "members": [],
        "sync": sync,
        "from_cache": True,
        "needs_sync": True,
    }


@router.get("/directory")
async def guild_directory(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    """Channels, roles, and members for panel dropdowns."""
    gid = _gid(settings)
    sync_state = await _run(guild_cache_db.get_sync_state, gid)
    try:
        data = await _run(guild_cache_db.get_guild_directory, gid)
    except HTTPException:
        data = _empty_directory(sync_state)

    has_data = bool(data.get("roles") or data.get("text_channels"))
    if has_data:
        data.setdefault("needs_sync", False)
        return data

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if token:
        try:
            live = await live_guild_directory(gid, token)
            live["sync"] = data.get("sync") or await _run(guild_cache_db.get_sync_state, gid)
            return live
        except Exception as exc:
            data["live_error"] = str(exc)

    data["needs_sync"] = True
    return data


@router.get("/sync-status")
async def sync_status(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    return await _run(guild_cache_db.get_sync_state, _gid(settings))


@router.post("/request-sync")
async def request_sync(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    """Ask the 24/7 bot to run a full sync on its next background poll (~20s)."""
    gid = _gid(settings)
    await _run(guild_cache_db.request_sync, gid)
    return {"ok": True, "message": "Sync queued. Run /botpanel sync in Discord for immediate sync."}
