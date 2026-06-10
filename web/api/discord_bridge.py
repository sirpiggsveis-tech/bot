"""Resolve the attached Discord bot and run panel actions."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status


def _discord():
    """discord.py is only installed when the bot runs (run.py), not on panel-only Render."""
    import discord

    return discord


def _bot(request: Request):
    bot = getattr(request.app.state, "bot", None)
    if bot is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Discord bot is offline. Run start-bot.bat on your PC.",
        )
    if not getattr(bot, "is_ready", lambda: False)():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Discord bot is still connecting. Wait a few seconds.",
        )
    return bot


def _guild(bot: Any, guild_id: int) -> Any:
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Bot is not in this server (check GUILD_ID).",
        )
    return guild


async def bot_status(request: Request) -> dict[str, Any]:
    bot = getattr(request.app.state, "bot", None)
    ready = bool(bot and getattr(bot, "is_ready", False))
    return {
        "online": ready,
        "attached": bot is not None,
    }


async def guild_directory(request: Request, guild_id: int) -> dict[str, Any]:
    discord = _discord()
    bot = _bot(request)
    guild = _guild(bot, guild_id)

    text_channels = []
    voice_channels = []
    categories = []
    for ch in guild.channels:
        if isinstance(ch, discord.TextChannel):
            text_channels.append({"id": str(ch.id), "name": ch.name, "category": ch.category.name if ch.category else None})
        elif isinstance(ch, discord.VoiceChannel):
            voice_channels.append({"id": str(ch.id), "name": ch.name, "category": ch.category.name if ch.category else None})
        elif isinstance(ch, discord.CategoryChannel):
            categories.append({"id": str(ch.id), "name": ch.name})

    roles = [
        {"id": str(r.id), "name": r.name, "color": r.color.value}
        for r in sorted(guild.roles, key=lambda r: r.position, reverse=True)
        if not r.is_default()
    ]

    try:
        await guild.chunk()
    except Exception:
        pass
    members = [
        {"id": str(m.id), "name": m.display_name}
        for m in sorted(guild.members, key=lambda m: m.display_name.lower())[:200]
    ]

    return {
        "text_channels": sorted(text_channels, key=lambda c: c["name"].lower()),
        "voice_channels": sorted(voice_channels, key=lambda c: c["name"].lower()),
        "categories": sorted(categories, key=lambda c: c["name"].lower()),
        "roles": roles,
        "members": sorted(members, key=lambda m: m["name"].lower()),
    }


async def run_panel_action(request: Request, guild_id: int, coro):
    discord = _discord()
    bot = _bot(request)
    guild = _guild(bot, guild_id)
    try:
        return await coro(guild)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except discord.Forbidden as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Discord permission denied: {exc}") from exc
    except discord.HTTPException as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Discord API error: {exc}") from exc


async def pd_on(request: Request, guild_id: int) -> dict:
    import scriptt

    async def _run(guild):
        locked, failed = await scriptt.lock_pd_channels(guild)
        return {"locked": locked, "failed": failed, "active": True}

    return await run_panel_action(request, guild_id, _run)


async def pd_off(request: Request, guild_id: int) -> dict:
    import scriptt

    async def _run(guild):
        saved, restore_context = scriptt.clear_pd_active_state(guild.id)
        unlocked, failed = await scriptt.restore_pd_permissions(guild, saved, restore_context)
        return {"unlocked": unlocked, "failed": failed, "active": False}

    return await run_panel_action(request, guild_id, _run)


async def pd_clear(request: Request, guild_id: int) -> dict:
    import scriptt

    async def _run(guild):
        guild_data = scriptt.get_guild_pd(guild.id)
        unlocked_note = []
        if guild_data.get("active") or guild_data.get("saved_permissions"):
            try:
                saved, restore_context = scriptt.clear_pd_active_state(guild.id)
                unlocked, _ = await scriptt.restore_pd_permissions(guild, saved, restore_context)
                unlocked_note = unlocked
            except ValueError:
                pass
        scriptt.set_guild_pd(
            guild.id,
            {
                "channel_ids": [],
                "lock_role_id": None,
                "lock_role_ids": [],
                "bypass_role_ids": [],
                "active": False,
                "saved_permissions": {},
            },
        )
        return {"ok": True, "unlocked": unlocked_note}

    return await run_panel_action(request, guild_id, _run)
