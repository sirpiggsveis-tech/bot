"""Bot command surface for the control panel."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

import bot_config_db

from ..command_map import COMMAND_MAP
from ..config import Settings, get_settings
from ..discord_bridge import (
    bot_status,
    guild_directory,
    pd_clear,
    pd_off,
    pd_on,
    run_panel_action,
)
from ..schemas import (
    AutoroleConfigUpdate,
    OrderRequest,
    PurgeRequest,
    PdConfigUpdate,
    ReactionTriggerCreate,
    SayRequest,
    SquadConfigUpdate,
    SquadCreateRequest,
    SquadDeleteRequest,
)
from ..security import CurrentUser, get_current_user, require_admin, require_write

router = APIRouter(prefix="/api/bot", tags=["bot"])


def _gid(settings: Settings) -> int:
    if not settings.guild_id:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "GUILD_ID not set")
    return settings.guild_id


async def _thread(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _pd_defaults() -> dict:
    return {
        "channel_ids": [],
        "lock_role_id": None,
        "lock_role_ids": [],
        "bypass_role_ids": [],
        "active": False,
        "saved_permissions": {},
    }


def _autorole_defaults() -> dict:
    return {"join_roles": [], "reaction_triggers": [], "join_nickname": ""}


def _squad_defaults() -> dict:
    return {"staff_role_ids": [], "category_id": None, "squads": []}


@router.get("/status")
async def get_bot_status(request: Request, user: CurrentUser = Depends(get_current_user)):
    return await bot_status(request)


@router.get("/commands")
async def commands(user: CurrentUser = Depends(get_current_user)):
    return {"categories": COMMAND_MAP}


@router.get("/guild")
async def guild_meta(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return await guild_directory(request, _gid(settings))
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            import guild_cache_db

            try:
                cached = await _thread(
                    guild_cache_db.get_guild_directory, _gid(settings)
                )
                if cached.get("text_channels") or cached.get("roles"):
                    cached["bot_offline"] = True
                    cached["message"] = exc.detail
                    return cached
            except Exception:
                pass
            return {
                "text_channels": [],
                "voice_channels": [],
                "categories": [],
                "roles": [],
                "members": [],
                "bot_offline": True,
                "message": exc.detail,
            }
        raise


# --------------------------------------------------------------------------
# PD mode
# --------------------------------------------------------------------------
@router.get("/pd")
async def get_pd(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    data = await _thread(
        bot_config_db.get_guild_config, gid, "pd", _pd_defaults()
    )
    return data


@router.put("/pd")
async def update_pd(
    body: PdConfigUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    gid = _gid(settings)
    data = await _thread(
        bot_config_db.get_guild_config, gid, "pd", _pd_defaults()
    )
    if body.lock_role_id is not None:
        data["lock_role_id"] = body.lock_role_id
        data["lock_role_ids"] = [body.lock_role_id]
    if body.channel_ids is not None:
        data["channel_ids"] = body.channel_ids
    if body.bypass_role_ids is not None:
        data["bypass_role_ids"] = body.bypass_role_ids
    await _thread(bot_config_db.set_guild_config, gid, "pd", data)
    return {"ok": True, "config": data}


@router.post("/pd/on")
async def pd_turn_on(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    return await pd_on(request, _gid(settings))


@router.post("/pd/off")
async def pd_turn_off(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    return await pd_off(request, _gid(settings))


@router.delete("/pd")
async def pd_clear_config(
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    return await pd_clear(request, _gid(settings))


# --------------------------------------------------------------------------
# Auto-role
# --------------------------------------------------------------------------
@router.get("/autorole")
async def get_autorole(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    return await _thread(
        bot_config_db.get_guild_config, gid, "autorole", _autorole_defaults()
    )


@router.put("/autorole")
async def update_autorole(
    body: AutoroleConfigUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    gid = _gid(settings)
    data = await _thread(
        bot_config_db.get_guild_config, gid, "autorole", _autorole_defaults()
    )
    if body.join_roles is not None:
        data["join_roles"] = body.join_roles
    if body.join_nickname is not None:
        data["join_nickname"] = body.join_nickname
    if body.reaction_triggers is not None:
        data["reaction_triggers"] = body.reaction_triggers
    await _thread(bot_config_db.set_guild_config, gid, "autorole", data)
    return {"ok": True, "config": data}


@router.post("/autorole/reactions", status_code=status.HTTP_201_CREATED)
async def add_reaction_trigger(
    body: ReactionTriggerCreate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    gid = _gid(settings)
    data = await _thread(
        bot_config_db.get_guild_config, gid, "autorole", _autorole_defaults()
    )
    triggers = data.get("reaction_triggers", [])
    triggers.append(
        {
            "channel_id": body.channel_id,
            "emoji": body.emoji,
            "role_ids": body.role_ids,
        }
    )
    data["reaction_triggers"] = triggers
    await _thread(bot_config_db.set_guild_config, gid, "autorole", data)
    return {"ok": True, "config": data}


@router.delete("/autorole")
async def clear_autorole(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    gid = _gid(settings)
    await _thread(
        bot_config_db.set_guild_config,
        gid,
        "autorole",
        _autorole_defaults(),
    )
    return {"ok": True}


# --------------------------------------------------------------------------
# Squads
# --------------------------------------------------------------------------
@router.get("/squads")
async def get_squads(
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    gid = _gid(settings)
    return await _thread(
        bot_config_db.get_guild_config, gid, "squad", _squad_defaults()
    )


@router.put("/squads/config")
async def update_squad_config(
    body: SquadConfigUpdate,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_admin),
):
    gid = _gid(settings)
    data = await _thread(
        bot_config_db.get_guild_config, gid, "squad", _squad_defaults()
    )
    if body.category_id is not None:
        data["category_id"] = body.category_id
    if body.staff_role_ids is not None:
        data["staff_role_ids"] = body.staff_role_ids
    await _thread(bot_config_db.set_guild_config, gid, "squad", data)
    return {"ok": True, "config": data}


@router.post("/squads")
async def create_squad(
    body: SquadCreateRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    import scriptt

    gid = _gid(settings)
    if not body.member_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one member")
    creator_id = body.member_ids[0]

    async def _run(guild):
        return await scriptt.panel_create_squad(
            guild, body.name, body.member_ids, creator_id
        )

    return await run_panel_action(request, gid, _run)


@router.delete("/squads/{channel_id}")
async def delete_squad(
    channel_id: int,
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    import scriptt

    gid = _gid(settings)

    async def _run(guild):
        name = await scriptt.panel_delete_squad(guild, channel_id)
        return {"deleted": name, "channel_id": channel_id}

    return await run_panel_action(request, gid, _run)


# --------------------------------------------------------------------------
# Messaging
# --------------------------------------------------------------------------
@router.post("/messaging/say")
async def messaging_say(
    body: SayRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    import scriptt

    gid = _gid(settings)

    async def _run(guild):
        await scriptt.panel_send_say(guild, body.channel_id, body.text)
        return {"ok": True, "channel_id": body.channel_id}

    return await run_panel_action(request, gid, _run)


@router.post("/messaging/order")
async def messaging_order(
    body: OrderRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(get_current_user),
):
    import scriptt

    gid = _gid(settings)

    async def _run(guild):
        spoken, failed = await scriptt.panel_speak_in_voice_channels(
            guild, body.channel_ids, body.text
        )
        return {"spoken": spoken, "failed": failed}

    return await run_panel_action(request, gid, _run)


@router.post("/messaging/purge")
async def messaging_purge(
    body: PurgeRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    user: CurrentUser = Depends(require_write),
):
    import scriptt

    gid = _gid(settings)

    async def _run(guild):
        count = await scriptt.panel_purge_channel(guild, body.channel_id, body.amount)
        return {"deleted": count}

    return await run_panel_action(request, gid, _run)
