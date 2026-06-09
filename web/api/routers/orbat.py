"""ORBAT REST endpoints. The SQLite DB (orbat_db) is the source of truth."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

import orbat_db

from ..config import Settings, get_settings
from ..schemas import (
    MemberUpdate,
    PositionCreate,
    RankCreate,
    RankRole,
    SettingsUpdate,
    UnitCreate,
    UnitMove,
    UnitUpdate,
)
from ..security import CurrentUser, get_current_user, require_admin, require_write

router = APIRouter(prefix="/api/orbat", tags=["orbat"])


def _gid(settings: Settings) -> int:
    if not settings.guild_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GUILD_ID not set")
    return settings.guild_id


async def _run(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _rank_sort_key(member: dict, rank_orders: dict[str, int]):
    seniority = rank_orders.get(member["rank"], -1)
    return (-seniority, member["username"].lower())


# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------
@router.get("/overview")
async def overview(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    units = await _run(orbat_db.get_units, gid)
    members = await _run(orbat_db.get_members, gid)
    ranks = await _run(orbat_db.get_ranks, gid)
    positions = await _run(orbat_db.get_positions, gid)
    cfg = await _run(orbat_db.get_settings, gid)
    return {
        "settings": cfg,
        "counts": {
            "members": len(members),
            "active": sum(1 for m in members if m["active"]),
            "units": len(units),
            "ranks": len(ranks),
            "positions": len(positions),
        },
        "units": units,
        "ranks": ranks,
        "positions": positions,
    }


# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------
@router.get("/units")
async def list_units(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    return await _run(orbat_db.get_units, _gid(settings))


@router.post("/units", status_code=status.HTTP_201_CREATED)
async def create_unit(
    body: UnitCreate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    try:
        unit_id = await _run(
            orbat_db.create_unit, _gid(settings), body.name, body.parent_id, body.description
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"id": unit_id}


@router.patch("/units/{unit_id}")
async def update_unit(
    unit_id: int,
    body: UnitUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    gid = _gid(settings)
    if await _run(orbat_db.get_unit, gid, unit_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unit not found")
    try:
        if body.name is not None:
            await _run(orbat_db.rename_unit, gid, unit_id, body.name)
        if body.description is not None:
            await _run(orbat_db.set_unit_description, gid, unit_id, body.description)
        if body.clear_leader:
            await _run(orbat_db.set_unit_leader, gid, unit_id, None)
        elif body.leader_id is not None:
            await _run(orbat_db.set_unit_leader, gid, unit_id, body.leader_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}


@router.post("/units/{unit_id}/move")
async def move_unit(
    unit_id: int,
    body: UnitMove,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    try:
        await _run(orbat_db.move_unit, _gid(settings), unit_id, body.new_parent_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}


@router.delete("/units/{unit_id}")
async def delete_unit(
    unit_id: int,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    try:
        await _run(orbat_db.delete_unit, _gid(settings), unit_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"ok": True}


@router.post("/units/clear")
async def clear_units(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    removed = await _run(orbat_db.clear_units, _gid(settings))
    return {"removed": removed}


# --------------------------------------------------------------------------
# Members
# --------------------------------------------------------------------------
@router.get("/members")
async def list_members(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    members = await _run(orbat_db.get_members, gid)
    ranks = await _run(orbat_db.get_ranks, gid)
    roles_map = await _run(orbat_db.get_member_roles_map, gid)
    rank_orders = {r["name"]: r["sort_order"] for r in ranks}
    members.sort(key=lambda m: _rank_sort_key(m, rank_orders))
    for m in members:
        m["roles"] = roles_map.get(m["discord_id"], [])
    return members


@router.get("/members/{discord_id}")
async def get_member(
    discord_id: int,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    member = await _run(orbat_db.get_member, gid, discord_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not tracked")
    roles_map = await _run(orbat_db.get_member_roles_map, gid)
    member["roles"] = roles_map.get(discord_id, [])
    return member


@router.patch("/members/{discord_id}")
async def update_member(
    discord_id: int,
    body: MemberUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    gid = _gid(settings)
    if await _run(orbat_db.get_member, gid, discord_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not tracked")

    if body.clear_unit:
        await _run(orbat_db.set_member_unit, gid, discord_id, None)
    elif body.unit_id is not None:
        await _run(orbat_db.set_member_unit, gid, discord_id, body.unit_id)

    if body.rank is not None:
        await _run(
            orbat_db.set_member_rank, gid, discord_id, body.rank, lock=body.lock_rank
        )
    if body.position is not None:
        await _run(orbat_db.set_member_position, gid, discord_id, body.position)
    if body.active is not None:
        await _run(orbat_db.set_member_active, gid, discord_id, body.active)
    if body.note is not None:
        await _run(orbat_db.set_member_note, gid, discord_id, body.note)
    return {"ok": True}


# --------------------------------------------------------------------------
# Ranks
# --------------------------------------------------------------------------
@router.get("/ranks")
async def list_ranks(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    return await _run(orbat_db.get_ranks, _gid(settings))


@router.post("/ranks", status_code=status.HTTP_201_CREATED)
async def create_rank(
    body: RankCreate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    try:
        rank_id = await _run(
            orbat_db.add_rank,
            _gid(settings),
            body.name,
            body.abbreviation,
            body.sort_order,
            body.role_id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"id": rank_id}


@router.put("/ranks/{rank_id}/role")
async def set_rank_role(
    rank_id: int,
    body: RankRole,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    await _run(orbat_db.set_rank_role, _gid(settings), rank_id, body.role_id)
    return {"ok": True}


@router.delete("/ranks/{rank_id}")
async def delete_rank(
    rank_id: int,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    await _run(orbat_db.remove_rank, _gid(settings), rank_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Positions
# --------------------------------------------------------------------------
@router.get("/positions")
async def list_positions(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    return await _run(orbat_db.get_positions, _gid(settings))


@router.post("/positions", status_code=status.HTTP_201_CREATED)
async def create_position(
    body: PositionCreate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    try:
        pos_id = await _run(orbat_db.add_position, _gid(settings), body.name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"id": pos_id}


@router.delete("/positions/{position_id}")
async def delete_position(
    position_id: int,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    await _run(orbat_db.remove_position, _gid(settings), position_id)
    return {"ok": True}


# --------------------------------------------------------------------------
# Settings + sync
# --------------------------------------------------------------------------
@router.get("/settings")
async def get_orbat_settings(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    return await _run(orbat_db.get_settings, _gid(settings))


@router.patch("/settings")
async def update_orbat_settings(
    body: SettingsUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    fields: dict[str, Any] = {}
    if body.title is not None:
        fields["title"] = body.title
    if body.embed_color is not None:
        fields["embed_color"] = body.embed_color
    if body.rank_source is not None:
        fields["rank_source"] = body.rank_source
    if body.auto_sync is not None:
        fields["auto_sync"] = 1 if body.auto_sync else 0
    if fields:
        await _run(orbat_db.update_settings, _gid(settings), **fields)
    return {"ok": True}


@router.post("/sync")
async def trigger_sync(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    """Force a re-pull of every member from Discord (needs the bot online)."""
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Bot is not attached to this API"
        )
    guild = bot.get_guild(_gid(settings))
    if guild is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Bot is not in the guild")

    syncer = getattr(bot, "force_sync_guild_orbat", None)
    if syncer is None:
        # Imported lazily to avoid a hard dependency at module import time.
        import scriptt  # type: ignore

        count = await scriptt.force_sync_guild_orbat(guild)
    else:
        count = await syncer(guild)
    return {"synced": count}
