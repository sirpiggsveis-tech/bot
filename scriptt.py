import asyncio
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import traceback
from datetime import datetime, timezone

# Make sure this script's own folder is importable, so `orbat_db` is found no
# matter which working directory the bot is launched from.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import discord
import edge_tts
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from orbat_db import (
    RANK_SOURCE_MANUAL,
    RANK_SOURCE_ROLES,
    add_position,
    add_rank,
    clear_units,
    create_unit,
    delete_unit,
    format_units_tree,
    get_member,
    get_member_roles_map,
    get_members,
    get_positions,
    get_ranks,
    get_settings,
    get_unit,
    get_units,
    init_orbat_db,
    move_unit,
    remove_position,
    remove_rank,
    rename_unit,
    replace_member_roles,
    set_member_active,
    set_member_note,
    set_member_position,
    set_member_rank,
    set_member_unit,
    set_rank_role,
    set_unit_description,
    set_unit_leader,
    sync_member,
    update_settings,
)

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
# Schema init runs in run.py (background) so the web API can bind its port first.

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
PD_ROLE_ID = int(os.getenv("PD_ROLE_ID", "1505952295408631973"))
TTS_VOICE = "en-US-AvaMultilingualNeural"
PD_MESSAGE = "Major PD in progress"
MAX_SELECT_CHANNELS = 25
MAX_PURGE = 50
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "pd_config.json")
AUTOROLE_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "autorole_config.json")
SQUAD_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "squad_config.json")
MAX_SQUAD_MEMBERS = 25
CHECKMARK_EMOJIS = {"✅", "☑️", "✔️", "\N{WHITE HEAVY CHECK MARK}"}
REACTION_SERVER_EMOJI_NAMES = ("Garrison", "TC")
REACTION_STANDARD_EMOJIS = ("✅", "⭐", "👍", "✔️", "🎉", "❤️")
_cached_ffmpeg: str | None = None

# ---------------------------------------------------------------------------
# AI_COMMAND_MAP — For any AI/agent reading this file: full bot surface area.
# Config files (same directory): pd_config.json, autorole_config.json,
# squad_config.json, orbat.db (SQLite). Env: DISCORD_TOKEN, GUILD_ID.
#
# Events (not slash commands):
#   on_ready          — sync commands, TTS check, PD auto-off if bot was offline
#   on_member_join    — join roles + auto-nickname; ORBAT member sync
#   on_member_remove  — mark ORBAT member inactive
#   on_member_update  — refresh ORBAT username/rank/roles
#   on_raw_reaction_add — staff react → roles go to message AUTHOR (not reactor)
#
# Groups:
#   Voice/Messages: order, say, purge
#   PD: pdconfig, pdconfigclear, pdon, pdoff  (only toggles Send Messages on 1 role)
#   autoroleconfig: view, join, reaction, nickname, clear  (admin)
#   Squads: squadconfig (admin), squadcreate, squaddelete
#   ORBAT: orbatview, orbatcard, orbatconfig (admin), orbatmember (admin),
#          orbatsync (admin), orbatclear (admin) — see orbat_db.py (SQLite)
#   Utility: help
# ---------------------------------------------------------------------------
AI_COMMAND_MAP: list[dict[str, object]] = [
    {
        "category": "Voice & messages",
        "commands": [
            {
                "name": "order",
                "usage": "/order",
                "summary": "Pick voice channel(s), enter text; bot joins and speaks via TTS.",
                "access": "Everyone",
            },
            {
                "name": "say",
                "usage": "/say",
                "summary": "Modal for multi-line text, then pick a text channel; sends red embed.",
                "access": "Everyone",
            },
            {
                "name": "purge",
                "usage": "/purge amount:<1-50>",
                "summary": "Deletes recent messages in the current text channel.",
                "access": "Manage Messages",
            },
        ],
    },
    {
        "category": "PD mode",
        "commands": [
            {
                "name": "pdconfig",
                "usage": "/pdconfig",
                "summary": "UI: pick role, then channels. Only denies Send Messages for that role.",
                "access": "Manage Channels",
            },
            {
                "name": "pdconfigclear",
                "usage": "/pdconfigclear",
                "summary": "Clears PD config; unlocks if PD was active.",
                "access": "Manage Channels",
            },
            {
                "name": "pdon",
                "usage": "/pdon",
                "summary": "Locks configured channels (Send Messages deny on lock role) + announces PD.",
                "access": "Manage Channels",
            },
            {
                "name": "pdoff",
                "usage": "/pdoff",
                "summary": "Marks PD off immediately; restores Send Messages in background.",
                "access": "Manage Channels",
            },
        ],
    },
    {
        "category": "Auto-role (/autoroleconfig)",
        "commands": [
            {
                "name": "autoroleconfig view",
                "usage": "/autoroleconfig view",
                "summary": "Shows join roles, reaction triggers, and auto-nickname.",
                "access": "Administrator",
            },
            {
                "name": "autoroleconfig join",
                "usage": "/autoroleconfig join",
                "summary": "Pick roles given automatically when someone joins.",
                "access": "Administrator",
            },
            {
                "name": "autoroleconfig reaction",
                "usage": "/autoroleconfig reaction",
                "summary": "Channel → emoji (:Garrison:/:TC: or standard) → roles for message author.",
                "access": "Administrator",
            },
            {
                "name": "autoroleconfig nickname",
                "usage": "/autoroleconfig nickname [nickname] [apply_to_existing]",
                "summary": "Sets exact nickname for new members; optional rename-all with confirm.",
                "access": "Administrator",
            },
            {
                "name": "autoroleconfig clear",
                "usage": "/autoroleconfig clear",
                "summary": "Wipes all auto-role settings.",
                "access": "Administrator",
            },
        ],
    },
    {
        "category": "Squads",
        "commands": [
            {
                "name": "squadconfig",
                "usage": "/squadconfig",
                "summary": "Pick category for squad VCs + staff roles that see all squads.",
                "access": "Administrator",
            },
            {
                "name": "squadcreate",
                "usage": "/squadcreate size:<1-25> name:<name>",
                "summary": "Private VC; multi-select members if size>1; DMs members invite.",
                "access": "Manage Channels",
            },
            {
                "name": "squaddelete",
                "usage": "/squaddelete",
                "summary": "Dropdown to delete a tracked squad voice channel.",
                "access": "Manage Channels",
            },
        ],
    },
    {
        "category": "ORBAT",
        "commands": [
            {
                "name": "orbatview",
                "usage": "/orbatview [unit]",
                "summary": "Full ORBAT (members by unit, rank-sorted) or one unit's roster.",
                "access": "Everyone",
            },
            {
                "name": "orbatcard",
                "usage": "/orbatcard [member]",
                "summary": "Service record card: rank, position, unit, roles, note.",
                "access": "Everyone",
            },
            {
                "name": "orbatconfig",
                "usage": "/orbatconfig",
                "summary": "Hub: manage units (tree), ranks (w/ role mapping), positions, settings.",
                "access": "Administrator",
            },
            {
                "name": "orbatmember",
                "usage": "/orbatmember member:<user>",
                "summary": "Editor: set unit, rank (locks it), position, active, note.",
                "access": "Administrator",
            },
            {
                "name": "orbatsync",
                "usage": "/orbatsync",
                "summary": "Re-pull every member from Discord into the ORBAT.",
                "access": "Administrator",
            },
            {
                "name": "orbatclear",
                "usage": "/orbatclear",
                "summary": "Deletes all units; members stay tracked but become unassigned.",
                "access": "Administrator",
            },
        ],
    },
    {
        "category": "Utility",
        "commands": [
            {
                "name": "help",
                "usage": "/help",
                "summary": "Shows this command list.",
                "access": "Everyone",
            },
        ],
    },
]

intents = discord.Intents.default()
intents.voice_states = True
intents.reactions = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
guild_locks: dict[int, asyncio.Lock] = {}


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.",
                ephemeral=True,
            )
            return False
        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "You must be an **Administrator** to use this command.",
                ephemeral=True,
            )
            return False
        return True

    return app_commands.check(predicate)


def bot_can_assign_role(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    if me is None:
        return False
    if role.managed or role.is_default():
        return False
    if not me.guild_permissions.manage_roles:
        return False
    return me.top_role > role


def role_assign_block_reason(guild: discord.Guild, role: discord.Role) -> str | None:
    me = guild.me
    if me is None:
        return "the bot is not in this server"
    if role.managed:
        return f"**{role.name}** is managed by an integration and cannot be assigned manually"
    if role.is_default():
        return "the @everyone role cannot be assigned"
    if not me.guild_permissions.manage_roles:
        return "the bot is missing **Manage Roles**"
    if me.top_role <= role:
        return (
            f"the bot role must be **above** **{role.name}** in Server Settings → Roles"
        )
    return None


def find_ffmpeg() -> str | None:
    global _cached_ffmpeg
    if _cached_ffmpeg and os.path.isfile(_cached_ffmpeg):
        return _cached_ffmpeg

    candidates: list[str] = []

    env_path = os.getenv("FFMPEG_PATH")
    if env_path:
        candidates.append(env_path)

    try:
        import imageio_ffmpeg

        candidates.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass

    which_path = shutil.which("ffmpeg")
    if which_path:
        candidates.append(which_path)

    winget_root = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Microsoft",
        "WinGet",
        "Packages",
    )
    candidates.extend(glob.glob(os.path.join(winget_root, "**", "ffmpeg.exe"), recursive=True))

    for path in candidates:
        if path and os.path.isfile(path):
            _cached_ffmpeg = path
            return path

    return None


def get_guild_lock(guild_id: int) -> asyncio.Lock:
    if guild_id not in guild_locks:
        guild_locks[guild_id] = asyncio.Lock()
    return guild_locks[guild_id]


def _highest_discord_role_name(member: discord.Member) -> str:
    roles = [role for role in member.roles if not role.is_default()]
    if not roles:
        return ""
    return max(roles, key=lambda role: role.position).name


def member_orbat_role_tuples(member: discord.Member) -> list[tuple[int, str]]:
    roles = [role for role in member.roles if not role.is_default()]
    roles.sort(key=lambda role: role.position, reverse=True)
    return [(role.id, role.name) for role in roles]


def member_orbat_join_date(member: discord.Member) -> str:
    if member.joined_at is not None:
        return member.joined_at.replace(microsecond=0).isoformat()
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def compute_member_rank(member: discord.Member, ranks: list[dict]) -> str:
    """Derive a rank name from the member's Discord roles.

    If any configured rank is mapped to a Discord role the member has, the
    most senior such rank (highest sort_order) wins. Otherwise fall back to the
    member's highest Discord role name.
    """
    member_role_ids = {role.id for role in member.roles}
    mapped = [
        rank
        for rank in ranks
        if rank["role_id"] and rank["role_id"] in member_role_ids
    ]
    if mapped:
        best = max(mapped, key=lambda rank: rank["sort_order"])
        return best["name"]
    return _highest_discord_role_name(member)


async def sync_orbat_member(member: discord.Member) -> None:
    if member.bot:
        return

    guild_id = member.guild.id
    settings = await asyncio.to_thread(get_settings, guild_id)

    if settings.get("rank_source", RANK_SOURCE_ROLES) == RANK_SOURCE_MANUAL:
        rank = ""
    else:
        ranks = await asyncio.to_thread(get_ranks, guild_id)
        rank = compute_member_rank(member, ranks)

    await asyncio.to_thread(
        sync_member,
        guild_id,
        member.id,
        member.display_name,
        rank,
        member_orbat_join_date(member),
    )
    await asyncio.to_thread(
        replace_member_roles,
        guild_id,
        member.id,
        member_orbat_role_tuples(member),
    )


async def sync_guild_orbat(guild: discord.Guild) -> int:
    settings = await asyncio.to_thread(get_settings, guild.id)
    if not settings.get("auto_sync", 1):
        return 0
    synced = 0
    for member in guild.members:
        if member.bot:
            continue
        await sync_orbat_member(member)
        synced += 1
    print(f"ORBAT: synced {synced} member(s) in {guild.name}", flush=True)
    return synced


async def force_sync_guild_orbat(guild: discord.Guild) -> int:
    """Sync every member regardless of the auto_sync setting."""
    synced = 0
    for member in guild.members:
        if member.bot:
            continue
        await sync_orbat_member(member)
        synced += 1
    return synced


def member_rank_label(member: dict, ranks_by_name: dict[str, dict]) -> str:
    rank = member["rank"] or ""
    if not rank:
        return ""
    info = ranks_by_name.get(rank)
    if info and info.get("abbreviation"):
        return info["abbreviation"]
    return rank


def member_sort_key(
    member: dict,
    rank_orders: dict[str, int],
) -> tuple[int, str]:
    # Higher rank sort_order = more senior, so negate for ascending sort.
    seniority = rank_orders.get(member["rank"], -1)
    return (-seniority, member["username"].lower())


def format_orbat_member_line(
    member: dict,
    roles_map: dict[int, list[str]],
    ranks_by_name: dict[str, dict],
) -> str:
    pieces: list[str] = []
    label = member_rank_label(member, ranks_by_name)
    if label:
        pieces.append(f"`{label}`")
    pieces.append(f"<@{member['discord_id']}>")
    if member["position"]:
        pieces.append(f"— {member['position']}")
    head = " ".join(pieces)

    tags: list[str] = []
    if not member["active"]:
        tags.append("inactive")
    if member.get("rank_locked"):
        tags.append("rank locked")
    tag_text = f"  _({', '.join(tags)})_" if tags else ""

    extra = ""
    if member.get("note"):
        extra = f"\n  ↳ {member['note']}"

    return f"{head}{tag_text}{extra}"


def _flush_field(
    embed: discord.Embed,
    embeds: list[discord.Embed],
    base_title: str,
    color: discord.Color,
    name: str,
    value: str,
) -> discord.Embed:
    if len(embed.fields) >= 25 or (len(embed) + len(name) + len(value)) > 5800:
        embeds.append(embed)
        embed = discord.Embed(title=f"{base_title} (cont.)", color=color)
    embed.add_field(name=name[:256], value=value[:1024] or "\u200b", inline=False)
    return embed


def build_orbat_embeds(guild: discord.Guild) -> list[discord.Embed]:
    settings = get_settings(guild.id)
    units = get_units(guild.id)
    members = get_members(guild.id)
    roles_map = get_member_roles_map(guild.id)
    ranks = get_ranks(guild.id)
    ranks_by_name = {rank["name"]: rank for rank in ranks}
    rank_orders = {rank["name"]: rank["sort_order"] for rank in ranks}
    color = discord.Color(settings.get("embed_color") or 0x2F4F4F)
    title = settings.get("title") or f"ORBAT — {guild.name}"

    members_by_unit: dict[int | None, list[dict]] = {}
    for member in members:
        members_by_unit.setdefault(member["unit_id"], []).append(member)

    active_count = sum(1 for member in members if member["active"])
    embeds: list[discord.Embed] = []
    overview = discord.Embed(
        title=title,
        description=(
            f"**Members tracked:** {len(members)} ({active_count} active)\n"
            f"**Units:** {len(units)}  |  **Ranks:** {len(ranks)}  "
            f"|  **Positions:** {len(get_positions(guild.id))}\n\n"
            "**Unit tree**\n"
            + format_units_tree(units)
        ),
        color=color,
    )
    overview.set_footer(text=f"Rank source: {settings.get('rank_source', 'roles')}")
    embeds.append(overview)

    detail = discord.Embed(title="ORBAT — Members by unit", color=color)
    base_title = "ORBAT — Members by unit"

    def unit_field_name(unit: dict, depth: int) -> str:
        prefix = "\u2003" * depth + ("\u2937 " if depth else "")
        leader = ""
        if unit.get("leader_id"):
            leader = f"  · led by <@{unit['leader_id']}>"
        return f"{prefix}{unit['name']}{leader}"

    def walk(parent_id: int | None, depth: int) -> None:
        nonlocal detail
        children = sorted(
            [u for u in units if u["parent_id"] == parent_id],
            key=lambda u: (u.get("sort_order", 0), u["name"].lower()),
        )
        for unit in children:
            unit_members = sorted(
                members_by_unit.get(unit["id"], []),
                key=lambda m: member_sort_key(m, rank_orders),
            )
            if unit_members:
                lines = [
                    format_orbat_member_line(m, roles_map, ranks_by_name)
                    for m in unit_members
                ]
                if unit.get("description"):
                    lines.insert(0, f"_{unit['description']}_")
                body = "\n".join(lines)
                for chunk in _chunk_lines(body):
                    detail = _flush_field(
                        detail, embeds, base_title, color,
                        unit_field_name(unit, depth), chunk,
                    )
            else:
                desc = unit.get("description")
                value = f"_{desc}_\n_No members assigned._" if desc else "_No members assigned._"
                detail = _flush_field(
                    detail, embeds, base_title, color,
                    unit_field_name(unit, depth), value,
                )
            walk(unit["id"], depth + 1)

    walk(None, 0)

    unassigned = sorted(
        members_by_unit.get(None, []),
        key=lambda m: member_sort_key(m, rank_orders),
    )
    if unassigned:
        lines = [
            format_orbat_member_line(m, roles_map, ranks_by_name) for m in unassigned
        ]
        for chunk in _chunk_lines("\n".join(lines)):
            detail = _flush_field(
                detail, embeds, base_title, color, "Unassigned", chunk,
            )

    if len(detail.fields) > 0:
        embeds.append(detail)

    if not members:
        overview.description = (
            "_No members tracked yet. Members are added when they join, "
            "when the bot starts, or via `/orbatsync`._"
        )

    return embeds


def _chunk_lines(body: str, limit: int = 1024) -> list[str]:
    if len(body) <= limit:
        return [body] if body else [""]
    chunks: list[str] = []
    current = ""
    for line in body.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit and current:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def build_orbat_unit_embed(guild: discord.Guild, unit_id: int) -> discord.Embed | None:
    settings = get_settings(guild.id)
    unit = get_unit(guild.id, unit_id)
    if unit is None:
        return None
    units = get_units(guild.id)
    members = get_members(guild.id)
    ranks = get_ranks(guild.id)
    ranks_by_name = {rank["name"]: rank for rank in ranks}
    rank_orders = {rank["name"]: rank["sort_order"] for rank in ranks}
    roles_map = get_member_roles_map(guild.id)
    color = discord.Color(settings.get("embed_color") or 0x2F4F4F)

    children = [u for u in units if u["parent_id"] == unit_id]
    unit_members = sorted(
        [m for m in members if m["unit_id"] == unit_id],
        key=lambda m: member_sort_key(m, rank_orders),
    )

    embed = discord.Embed(
        title=f"ORBAT — {unit['name']}",
        color=color,
        description=unit["description"] or None,
    )
    if unit.get("leader_id"):
        embed.add_field(name="Leader", value=f"<@{unit['leader_id']}>", inline=False)

    if unit_members:
        lines = [
            format_orbat_member_line(m, roles_map, ranks_by_name) for m in unit_members
        ]
        chunks = _chunk_lines("\n".join(lines))
        for index, chunk in enumerate(chunks):
            embed.add_field(
                name="Members" if index == 0 else "Members (cont.)",
                value=chunk,
                inline=False,
            )
    else:
        embed.add_field(name="Members", value="_None assigned._", inline=False)

    if children:
        child_text = "\n".join(
            f"\u2022 **{c['name']}** `#{c['id']}`"
            for c in sorted(children, key=lambda c: (c.get("sort_order", 0), c["name"].lower()))
        )
        embed.add_field(name="Sub-units", value=child_text[:1024], inline=False)

    embed.set_footer(text=f"Unit #{unit_id}  ·  {len(unit_members)} member(s)")
    return embed


def build_orbat_card(guild: discord.Guild, discord_id: int) -> discord.Embed | None:
    member = get_member(guild.id, discord_id)
    if member is None:
        return None
    settings = get_settings(guild.id)
    roles_map = get_member_roles_map(guild.id)
    ranks_by_name = {rank["name"]: rank for rank in get_ranks(guild.id)}
    color = discord.Color(settings.get("embed_color") or 0x2F4F4F)

    unit = get_unit(guild.id, member["unit_id"]) if member["unit_id"] else None
    rank_label = member_rank_label(member, ranks_by_name)
    rank_full = member["rank"] or "—"
    if rank_label and rank_label != rank_full:
        rank_full = f"{rank_full} ({rank_label})"

    embed = discord.Embed(
        title=f"Service record — {member['username']}",
        color=color,
    )
    discord_member = guild.get_member(discord_id)
    if discord_member is not None and discord_member.display_avatar:
        embed.set_thumbnail(url=discord_member.display_avatar.url)

    embed.add_field(name="Member", value=f"<@{discord_id}>", inline=True)
    embed.add_field(name="Status", value="Active" if member["active"] else "Inactive", inline=True)
    embed.add_field(
        name="Rank",
        value=rank_full + (" 🔒" if member.get("rank_locked") else ""),
        inline=True,
    )
    embed.add_field(name="Position", value=member["position"] or "—", inline=True)
    embed.add_field(name="Unit", value=unit["name"] if unit else "Unassigned", inline=True)
    join = member["join_date"][:10] if member["join_date"] else "—"
    embed.add_field(name="Joined", value=join, inline=True)

    roles = roles_map.get(discord_id, [])
    embed.add_field(
        name=f"Discord roles ({len(roles)})",
        value=", ".join(roles)[:1024] if roles else "—",
        inline=False,
    )
    if member.get("note"):
        embed.add_field(name="Note", value=member["note"][:1024], inline=False)

    embed.set_footer(text=f"Discord ID: {discord_id}")
    return embed


async def generate_tts(text: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)
    size = os.path.getsize(output_path)
    if size < 100:
        raise RuntimeError(f"TTS file too small ({size} bytes).")


async def get_voice_client(
    guild: discord.Guild,
    voice_channel: discord.VoiceChannel,
) -> discord.VoiceClient:
    vc = guild.voice_client

    if vc is None:
        vc = await voice_channel.connect(reconnect=True, timeout=60.0)
    elif vc.channel != voice_channel:
        await vc.move_to(voice_channel, timeout=60.0)

    if not vc.wait_until_connected(timeout=60.0):
        raise RuntimeError("Timed out waiting for voice connection.")

    return vc


async def play_audio_file(vc: discord.VoiceClient, audio_path: str, ffmpeg: str) -> None:
    done = asyncio.Event()
    play_error: list[BaseException | None] = [None]

    def after_playing(error: Exception | None) -> None:
        if error is not None:
            play_error[0] = error
        bot.loop.call_soon_threadsafe(done.set)

    if vc.is_playing():
        vc.stop()
        await asyncio.sleep(0.2)

    source = discord.FFmpegPCMAudio(
        audio_path,
        executable=ffmpeg,
        before_options="-nostdin",
    )
    vc.play(source, after=after_playing)

    for _ in range(60):
        if vc.is_playing() or done.is_set():
            break
        await asyncio.sleep(0.1)
    else:
        raise RuntimeError("Playback never started. Check ffmpeg path and bot Speak permission.")

    await asyncio.wait_for(done.wait(), timeout=120)

    if play_error[0] is not None:
        raise play_error[0]


async def sync_slash_commands() -> None:
    registered = [command.name for command in bot.tree.get_commands()]
    print(f"Commands on tree: {registered}", flush=True)

    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            guild_synced = await bot.tree.sync(guild=guild)
            guild_names = [command.name for command in guild_synced]
            print(
                f"Guild sync ({GUILD_ID}): {len(guild_synced)} command(s) -> {guild_names}",
                flush=True,
            )

            # Remove global commands so they don't duplicate guild commands in this server.
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync()
            print("Cleared global slash commands (using guild-only sync).", flush=True)
        else:
            global_synced = await bot.tree.sync()
            global_names = [command.name for command in global_synced]
            print(
                f"Global sync: {len(global_synced)} command(s) -> {global_names}",
                flush=True,
            )
    except Exception:
        print(f"Command sync failed:\n{traceback.format_exc()}", flush=True)


@bot.event
async def setup_hook():
    await sync_slash_commands()


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    if isinstance(error, app_commands.CheckFailure):
        # The check already messaged the user; nothing more to do.
        return

    cmd = interaction.command.name if interaction.command else "unknown"
    print(f"App command error in /{cmd}:\n", flush=True)
    traceback.print_exception(type(error), error, error.__traceback__)

    message = "Something went wrong running that command. Check the bot logs."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


MAX_VOICE_CHANNELS = MAX_SELECT_CHANNELS


def parse_channel_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.replace(",", " ").replace("\n", " ").split():
        try:
            channel_id = int(part.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid channel ID: {part!r}") from exc
        if channel_id not in ids:
            ids.append(channel_id)
    if not ids:
        raise ValueError("No channel IDs provided.")
    if len(ids) > MAX_VOICE_CHANNELS:
        raise ValueError(f"You can select at most {MAX_VOICE_CHANNELS} voice channels.")
    return ids


class MessageModal(discord.ui.Modal, title="Your Message"):
    message = discord.ui.TextInput(
        label="Message to speak",
        style=discord.TextStyle.paragraph,
        placeholder="Type what you want the bot to say...",
        max_length=500,
    )

    def __init__(self, channel_ids: list[int]):
        super().__init__()
        self.channel_ids = channel_ids

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await speak_in_channels(interaction, self.channel_ids, self.message.value)


class ChannelIdModal(discord.ui.Modal, title="Voice Channel IDs"):
    channel_ids = discord.ui.TextInput(
        label="Channel IDs (one or more)",
        style=discord.TextStyle.paragraph,
        placeholder="Paste one or more voice channel IDs, separated by spaces or commas",
        min_length=17,
        max_length=500,
    )
    message = discord.ui.TextInput(
        label="Message to speak",
        style=discord.TextStyle.paragraph,
        placeholder="Type what you want the bot to say...",
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ids = parse_channel_ids(self.channel_ids.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await speak_in_channels(interaction, ids, self.message.value)


def build_voice_channel_options(guild: discord.Guild) -> list[discord.SelectOption]:
    channels = sorted(
        guild.voice_channels,
        key=lambda channel: (
            channel.category.name.lower() if channel.category else "",
            channel.name.lower(),
        ),
    )

    options: list[discord.SelectOption] = []
    for channel in channels[:MAX_VOICE_CHANNELS]:
        description = channel.category.name if channel.category else "Voice channel"
        options.append(
            discord.SelectOption(
                label=channel.name[:100],
                value=str(channel.id),
                description=description[:100],
            )
        )
    return options


class VoiceChannelMenu(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = build_voice_channel_options(guild)
        super().__init__(
            placeholder="Choose one or more voice channels...",
            min_values=1,
            max_values=max(1, min(MAX_VOICE_CHANNELS, len(options))),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        channel_ids = [int(value) for value in self.values]
        await interaction.response.send_modal(MessageModal(channel_ids))


class OrderView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=300)
        self.add_item(VoiceChannelMenu(guild))

    @discord.ui.button(label="Enter Channel IDs", style=discord.ButtonStyle.secondary, row=1)
    async def enter_id(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ChannelIdModal())


async def speak_in_channels(
    interaction: discord.Interaction,
    channel_ids: list[int],
    text: str,
):
    guild = interaction.guild
    if guild is None:
        await interaction.followup.send("This command only works in a server.", ephemeral=True)
        return

    voice_channels: list[discord.VoiceChannel] = []
    for channel_id in channel_ids:
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            try:
                fetched = await guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.HTTPException):
                fetched = None
            channel = fetched if isinstance(fetched, discord.VoiceChannel) else None
        if channel is None:
            await interaction.followup.send(
                f"Could not find voice channel with ID `{channel_id}`.",
                ephemeral=True,
            )
            return
        voice_channels.append(channel)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        await interaction.followup.send(
            "ffmpeg was not found. Install it, then restart the bot.",
            ephemeral=True,
        )
        return

    tmp_path = None
    lock = get_guild_lock(guild.id)
    spoken: list[str] = []
    failed: list[str] = []

    async with lock:
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            print(f"Generating TTS for {len(voice_channels)} channel(s): {text!r}", flush=True)
            await generate_tts(text, tmp_path)
            print(f"TTS saved ({os.path.getsize(tmp_path)} bytes)", flush=True)

            for voice_channel in voice_channels:
                try:
                    vc = await get_voice_client(guild, voice_channel)
                    print(f"Connected to voice channel: {voice_channel.name}", flush=True)

                    await play_audio_file(vc, tmp_path, ffmpeg)
                    print(f"Playback finished in: {voice_channel.name}", flush=True)
                    spoken.append(voice_channel.name)
                except Exception as exc:
                    print(
                        f"Failed in {voice_channel.name}: {exc}\n{traceback.format_exc()}",
                        flush=True,
                    )
                    failed.append(f"**{voice_channel.name}**: {exc}")
                    if guild.voice_client:
                        try:
                            await guild.voice_client.disconnect(force=True)
                        except Exception:
                            pass
                    await asyncio.sleep(0.5)

            if guild.voice_client:
                await guild.voice_client.disconnect()

            if spoken and not failed:
                channel_list = ", ".join(f"**{name}**" for name in spoken)
                await interaction.followup.send(
                    f"Spoke your message in {len(spoken)} channel(s): {channel_list}.",
                    ephemeral=True,
                )
            elif spoken and failed:
                await interaction.followup.send(
                    f"Spoke in {len(spoken)} channel(s), but failed in {len(failed)}:\n"
                    + "\n".join(failed),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "Failed in every selected channel:\n" + "\n".join(failed),
                    ephemeral=True,
                )
        except Exception as exc:
            print(traceback.format_exc(), flush=True)
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect(force=True)
                except Exception:
                    pass
            await interaction.followup.send(f"Failed: {exc}", ephemeral=True)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)


@bot.event
async def on_ready():
    ffmpeg = find_ffmpeg()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})", flush=True)
    print(f"discord.py: {discord.__version__}", flush=True)
    print(f"ffmpeg: {ffmpeg or 'NOT FOUND'}", flush=True)

    test_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            test_path = tmp.name
        await generate_tts("startup test", test_path)
        print("TTS check: OK", flush=True)
    except Exception as exc:
        print(f"TTS check: FAILED ({exc})", flush=True)
    finally:
        if test_path and os.path.exists(test_path):
            os.unlink(test_path)

    print(
        "Bot is ready. Use /help for commands.",
        flush=True,
    )

    if not intents.members:
        print(
            "WARNING: members intent is off — reaction roles may fail to resolve users. "
            "Enable Server Members Intent in the Discord Developer Portal.",
            flush=True,
        )

    for guild in bot.guilds:
        log_autorole_startup_checks(guild)
        asyncio.create_task(recover_stale_pd_on_startup(guild))
        if intents.members:
            asyncio.create_task(_chunk_guild_safe(guild))


async def _chunk_guild_safe(guild: discord.Guild) -> None:
    try:
        await guild.chunk()
    except Exception as exc:
        print(f"Guild member chunk failed for {guild.name}: {exc}", flush=True)
    try:
        await sync_guild_orbat(guild)
    except Exception as exc:
        print(f"ORBAT sync failed for {guild.name}: {exc}", flush=True)


async def defer_ephemeral(interaction: discord.Interaction) -> bool:
    if interaction.response.is_done():
        return True
    try:
        await interaction.response.defer(ephemeral=True)
        return True
    except (discord.NotFound, discord.HTTPException):
        return False


# --- Auto-role configuration ---


def load_autorole_store() -> dict:
    if not os.path.exists(AUTOROLE_CONFIG_PATH):
        return {}
    try:
        with open(AUTOROLE_CONFIG_PATH, encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_autorole_store(data: dict) -> None:
    with open(AUTOROLE_CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def get_guild_autorole(guild_id: int) -> dict:
    store = load_autorole_store()
    key = str(guild_id)
    if key not in store:
        store[key] = {
            "join_roles": [],
            "reaction_triggers": [],
            "join_nickname": "",
        }
    data = store[key]
    data.setdefault("join_roles", [])
    data.setdefault("reaction_triggers", [])
    data.setdefault("join_nickname", "")
    return data


def set_guild_autorole(guild_id: int, guild_data: dict) -> None:
    store = load_autorole_store()
    store[str(guild_id)] = guild_data
    save_autorole_store(store)


def strip_emoji_colons(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith(":") and value.endswith(":"):
        return value[1:-1]
    return value


def normalize_emoji_name(value: str) -> str:
    return strip_emoji_colons(value).lower()


def parse_emoji_id_from_trigger(trigger: str) -> int | None:
    trigger = trigger.strip()
    if trigger.isdigit():
        return int(trigger)
    match = re.fullmatch(r"<a?:\w+:(\d+)>", trigger)
    if match:
        return int(match.group(1))
    if ":" in trigger and not trigger.startswith("<"):
        name, emoji_id = trigger.rsplit(":", 1)
        if name and emoji_id.isdigit():
            return int(emoji_id)
    return None


def get_reaction_server_emojis(guild: discord.Guild) -> list[discord.Emoji]:
    found: list[discord.Emoji] = []
    for name in REACTION_SERVER_EMOJI_NAMES:
        emoji = discord.utils.get(guild.emojis, name=name)
        if emoji is None:
            lowered = name.lower()
            emoji = next(
                (item for item in guild.emojis if item.name.lower() == lowered),
                None,
            )
        if emoji is not None and emoji not in found:
            found.append(emoji)
    return found


async def show_reaction_role_picker(
    interaction: discord.Interaction,
    guild: discord.Guild,
    channel_id: int,
    emoji_raw: str,
) -> None:
    canonical = canonicalize_trigger_emoji(guild, emoji_raw)
    emoji_label = format_trigger_emoji_display(guild, canonical)
    view = ReactionRoleConfigView(guild, channel_id, canonical)
    await interaction.response.edit_message(
        content=(
            f"**Step 3:** Pick the role(s) the **message author** gets "
            f"when staff react with {emoji_label}."
        ),
        view=view,
    )


def find_guild_emoji(guild: discord.Guild, raw: str) -> discord.Emoji | None:
    emoji_id = parse_emoji_id_from_trigger(raw)
    if emoji_id is not None:
        emoji = discord.utils.get(guild.emojis, id=emoji_id)
        if emoji is not None:
            return emoji

    name = normalize_emoji_name(raw)
    if not name:
        return None

    for emoji in guild.emojis:
        if emoji.name.lower() == name:
            return emoji
    return None


def is_unicode_emoji(value: str) -> bool:
    try:
        partial = discord.PartialEmoji.from_str(value.strip())
    except Exception:
        return False
    return partial.id is None


def parse_trigger_emoji_input(raw: str) -> discord.PartialEmoji | None:
    raw = raw.strip()
    if not raw:
        return None

    if raw.isdigit():
        return discord.PartialEmoji(name="emoji", id=int(raw))

    try:
        return discord.PartialEmoji.from_str(raw)
    except Exception:
        pass

    if raw.startswith(":") and raw.endswith(":"):
        name = strip_emoji_colons(raw)
        if name:
            return discord.PartialEmoji(name=name)

    if ":" in raw and not raw.startswith("<"):
        name, emoji_id = raw.rsplit(":", 1)
        if name and emoji_id.isdigit():
            return discord.PartialEmoji(name=name, id=int(emoji_id))

    return None


def is_valid_trigger_emoji(guild: discord.Guild | None, raw: str) -> bool:
    raw = raw.strip()
    if not raw:
        return False

    if parse_emoji_id_from_trigger(raw) is not None:
        return True

    parsed = parse_trigger_emoji_input(raw)
    if parsed is None:
        return False

    if parsed.id is not None:
        return True

    if is_unicode_emoji(raw):
        return True

    if guild is not None and find_guild_emoji(guild, raw) is not None:
        return True

    if raw.startswith(":") and raw.endswith(":"):
        return False

    return parsed.id is None and bool(parsed.name)


def canonicalize_trigger_emoji(guild: discord.Guild | None, raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return raw

    parsed = parse_trigger_emoji_input(raw)
    if parsed is not None and parsed.id is not None:
        if parsed.name and parsed.name != "emoji":
            return str(parsed)
        return str(parsed.id)

    if guild is not None:
        found = find_guild_emoji(guild, raw)
        if found is not None:
            return str(found)

    if parsed is not None and parsed.id is None:
        return str(parsed)

    return raw


def partial_from_trigger(
    guild: discord.Guild | None,
    trigger_emoji: str,
) -> discord.PartialEmoji:
    parsed = parse_trigger_emoji_input(trigger_emoji)
    if parsed is not None:
        if parsed.id is not None and guild is not None:
            found = discord.utils.get(guild.emojis, id=parsed.id)
            if found is not None:
                return discord.PartialEmoji(
                    name=found.name,
                    id=found.id,
                    animated=found.animated,
                )
        return parsed

    try:
        return discord.PartialEmoji.from_str(trigger_emoji)
    except Exception:
        pass

    if guild is not None:
        found = find_guild_emoji(guild, trigger_emoji)
        if found is not None:
            return discord.PartialEmoji(
                name=found.name,
                id=found.id,
                animated=found.animated,
            )

    name = strip_emoji_colons(trigger_emoji)
    return discord.PartialEmoji(name=name)


def emoji_matches(payload_emoji: discord.PartialEmoji, trigger_emoji: str) -> bool:
    if str(payload_emoji) == trigger_emoji:
        return True

    trigger_id = parse_emoji_id_from_trigger(trigger_emoji)
    if payload_emoji.id is not None and trigger_id is not None and payload_emoji.id == trigger_id:
        return True
    if payload_emoji.id is not None and trigger_emoji.isdigit() and payload_emoji.id == int(trigger_emoji):
        return True

    payload_name = normalize_emoji_name(payload_emoji.name or "")
    trigger_name = normalize_emoji_name(trigger_emoji)
    if payload_name and trigger_name and payload_name == trigger_name:
        return True

    if trigger_emoji in CHECKMARK_EMOJIS and str(payload_emoji) in CHECKMARK_EMOJIS:
        return True
    return False


def triggers_match_emoji(
    guild: discord.Guild | None,
    stored: str,
    new: str,
) -> bool:
    if stored == new:
        return True
    if guild is None:
        return False
    stored_partial = partial_from_trigger(guild, stored)
    return emoji_matches(stored_partial, new) or emoji_matches(
        stored_partial,
        canonicalize_trigger_emoji(guild, new),
    )


def format_trigger_emoji_display(guild: discord.Guild, trigger_emoji: str) -> str:
    if guild is not None:
        found = find_guild_emoji(guild, trigger_emoji)
        if found is not None:
            return str(found)

    parsed = parse_trigger_emoji_input(trigger_emoji)
    if parsed is not None:
        if parsed.id is not None and parsed.name and parsed.name != "emoji":
            return str(parsed)
        if parsed.id is None:
            return str(parsed)

    try:
        return str(discord.PartialEmoji.from_str(trigger_emoji))
    except Exception:
        pass

    name = strip_emoji_colons(trigger_emoji)
    if name.isdigit():
        return f"`{name}`"
    return f":{name}:" if name else trigger_emoji


async def resolve_parent_channel_id(guild: discord.Guild, channel_id: int) -> int:
    """Map thread / forum-post IDs to their parent text channel for trigger matching."""
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(channel_id)
        except (discord.NotFound, discord.HTTPException):
            return channel_id
    if isinstance(channel, discord.Thread):
        return channel.parent_id or channel_id
    return channel_id


async def resolve_reacted_message_author(
    guild: discord.Guild,
    payload: discord.RawReactionActionEvent,
) -> discord.Member | None:
    channel = guild.get_channel(payload.channel_id)
    if channel is None:
        try:
            channel = await guild.fetch_channel(payload.channel_id)
        except (discord.NotFound, discord.HTTPException) as exc:
            print(f"Reaction: channel {payload.channel_id} unavailable: {exc}", flush=True)
            return None

    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        print(
            f"Reaction: channel {payload.channel_id} does not support message lookup",
            flush=True,
        )
        return None

    try:
        message = await channel.fetch_message(payload.message_id)
    except discord.NotFound:
        print(f"Reaction: message {payload.message_id} not found", flush=True)
        return None
    except discord.Forbidden:
        print(
            f"Reaction: no permission to read messages in channel {payload.channel_id}",
            flush=True,
        )
        return None
    except discord.HTTPException as exc:
        print(f"Reaction: could not fetch message {payload.message_id}: {exc}", flush=True)
        return None

    if message.author.bot:
        print("Reaction: ignored — message author is a bot", flush=True)
        return None

    try:
        return await guild.fetch_member(message.author.id)
    except discord.NotFound:
        print(f"Reaction: message author {message.author.id} is not in guild", flush=True)
    except discord.HTTPException as exc:
        print(f"Reaction: could not fetch message author {message.author.id}: {exc}", flush=True)
    return None


def trigger_matches_reaction(
    trigger: dict,
    payload: discord.RawReactionActionEvent,
    effective_channel_id: int,
) -> bool:
    if trigger.get("channel_id") != effective_channel_id:
        return False
    message_id = trigger.get("message_id")
    if message_id and message_id != payload.message_id:
        return False
    return emoji_matches(payload.emoji, trigger["emoji"])


def log_autorole_startup_checks(guild: discord.Guild) -> None:
    data = get_guild_autorole(guild.id)
    triggers = data.get("reaction_triggers", [])
    if not triggers:
        return

    me = guild.me
    print(f"Auto-role checks for {guild.name}:", flush=True)
    for trigger in triggers:
        channel = guild.get_channel(trigger["channel_id"])
        channel_label = f"#{channel.name}" if channel else f"channel {trigger['channel_id']}"
        message_note = ""
        if trigger.get("message_id"):
            message_note = f" on message {trigger['message_id']}"
        emoji_label = format_trigger_emoji_display(guild, trigger["emoji"])
        print(
            f"  - {emoji_label} in {channel_label}{message_note}",
            flush=True,
        )
        for role_id in trigger.get("role_ids", []):
            role = guild.get_role(role_id)
            if role is None:
                print(f"    ! Role {role_id} not found", flush=True)
            elif me and (block := role_assign_block_reason(guild, role)):
                print(f"    ! Cannot assign {role.name}: {block}", flush=True)
            else:
                print(f"    OK -> {role.name if role else role_id}", flush=True)


def get_sorted_text_channels(guild: discord.Guild) -> list[discord.TextChannel]:
    channels = [
        channel
        for channel in guild.channels
        if isinstance(channel, discord.TextChannel)
    ]
    return sorted(
        channels,
        key=lambda channel: (
            channel.category.name.lower() if channel.category else "",
            channel.name.lower(),
        ),
    )


def build_text_channel_options(
    channels: list[discord.TextChannel],
    page: int = 0,
) -> list[discord.SelectOption]:
    start = page * MAX_SELECT_CHANNELS
    page_channels = channels[start : start + MAX_SELECT_CHANNELS]

    options: list[discord.SelectOption] = []
    for channel in page_channels:
        description = channel.category.name if channel.category else "Text channel"
        options.append(
            discord.SelectOption(
                label=channel.name[:100],
                value=str(channel.id),
                description=description[:100],
            )
        )
    return options


def get_sorted_roles(guild: discord.Guild) -> list[discord.Role]:
    return sorted(guild.roles, key=lambda role: role.position, reverse=True)


def get_pd_lock_roles(guild: discord.Guild) -> list[discord.Role]:
    """Roles the bot can lock during PD, lowest rank first."""
    me = guild.me
    if me is None:
        return sorted(guild.roles, key=lambda role: role.position)

    bot_position = me.top_role.position
    lockable = [role for role in guild.roles if role.position < bot_position]
    return sorted(lockable, key=lambda role: role.position)


def build_role_options(
    roles: list[discord.Role],
    page: int = 0,
    *,
    show_rank: bool = False,
) -> list[discord.SelectOption]:
    start = page * MAX_SELECT_CHANNELS
    page_roles = roles[start : start + MAX_SELECT_CHANNELS]

    options: list[discord.SelectOption] = []
    for role in page_roles:
        description = f"Rank {role.position}" if show_rank else f"Role ID: {role.id}"
        options.append(
            discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                description=description[:100],
            )
        )
    return options


def format_autorole_summary(guild: discord.Guild) -> str:
    data = get_guild_autorole(guild.id)
    lines = ["**Auto-role configuration**", ""]

    join_roles = data.get("join_roles", [])
    if join_roles:
        role_mentions = []
        for role_id in join_roles:
            role = guild.get_role(role_id)
            role_mentions.append(role.mention if role else f"`{role_id}`")
        lines.append("**On join:** " + ", ".join(role_mentions))
    else:
        lines.append("**On join:** none configured")

    join_nickname = data.get("join_nickname", "")
    if join_nickname:
        lines.append(f"**Auto-nickname:** every new member → `{truncate_nickname(join_nickname)}`")
    else:
        lines.append("**Auto-nickname:** disabled")

    triggers = data.get("reaction_triggers", [])
    if triggers:
        lines.append("")
        lines.append("**Reaction triggers:**")
        for trigger in triggers:
            channel = guild.get_channel(trigger["channel_id"])
            channel_name = channel.mention if channel else f"`{trigger['channel_id']}`"
            role_names = []
            for role_id in trigger.get("role_ids", []):
                role = guild.get_role(role_id)
                role_names.append(role.mention if role else f"`{role_id}`")
            scope = channel_name
            if trigger.get("message_id"):
                scope = f"{channel_name} (message `{trigger['message_id']}`)"
            emoji_label = format_trigger_emoji_display(guild, trigger["emoji"])
            lines.append(
                f"- {emoji_label} in {scope} → message author gets "
                + (", ".join(role_names) if role_names else "no roles")
            )
    else:
        lines.append("")
        lines.append("**Reaction triggers:** none configured")

    lines.append("")
    lines.append(
        "Staff react to someone's message to award roles. "
        "Use `/autoroleconfig join` or `/autoroleconfig reaction` to set up."
    )
    return "\n".join(lines)


def parse_role_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.replace(",", " ").replace("\n", " ").split():
        try:
            role_id = int(part.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid role ID: {part!r}") from exc
        if role_id not in ids:
            ids.append(role_id)
    if not ids:
        raise ValueError("No role IDs provided.")
    return ids


def get_autorole_roles(guild: discord.Guild) -> list[discord.Role]:
    return get_pd_lock_roles(guild)


def save_reaction_trigger(
    guild_id: int,
    channel_id: int,
    emoji: str,
    role_ids: list[int],
    guild: discord.Guild | None = None,
) -> None:
    if guild is None:
        guild = bot.get_guild(guild_id)
    canonical = canonicalize_trigger_emoji(guild, emoji)

    data = get_guild_autorole(guild_id)
    triggers = data.get("reaction_triggers", [])

    updated = False
    for trigger in triggers:
        if trigger["channel_id"] == channel_id and triggers_match_emoji(
            guild,
            trigger["emoji"],
            canonical,
        ):
            trigger["emoji"] = canonical
            trigger["role_ids"] = role_ids
            updated = True
            break

    if not updated:
        triggers.append(
            {
                "channel_id": channel_id,
                "emoji": canonical,
                "role_ids": role_ids,
            }
        )

    data["reaction_triggers"] = triggers
    set_guild_autorole(guild_id, data)


def roles_member_is_missing(
    member: discord.Member,
    role_ids: list[int],
) -> list[discord.Role]:
    missing: list[discord.Role] = []
    for role_id in role_ids:
        role = member.guild.get_role(role_id)
        if role is not None and role not in member.roles:
            missing.append(role)
    return missing


MAX_NICKNAME_LENGTH = 32


def truncate_nickname(text: str) -> str:
    return (text or "").strip()[:MAX_NICKNAME_LENGTH]


def nickname_block_reason(member: discord.Member) -> str | None:
    guild = member.guild
    me = guild.me
    if me is None:
        return "the bot is not in this server"
    if not me.guild_permissions.manage_nicknames:
        return "the bot is missing **Manage Nicknames**"
    if member.id == guild.owner_id:
        return "Discord does not allow bots to rename the server owner"
    if member.id == me.id:
        return "the bot cannot rename itself this way"
    if member.top_role >= me.top_role:
        return f"**{member.display_name}**'s top role is not below the bot's role"
    return None


async def apply_join_nickname(member: discord.Member, nickname: str) -> bool:
    nickname = truncate_nickname(nickname)
    if not nickname:
        return False

    block_reason = nickname_block_reason(member)
    if block_reason:
        print(
            f"Skip nickname for {member.name}: {block_reason}",
            flush=True,
        )
        return False

    if member.nick == nickname:
        return False

    try:
        await member.edit(nick=nickname, reason="Auto-nickname on join")
        print(f"Set nickname for {member.name} -> {nickname}", flush=True)
        return True
    except discord.Forbidden:
        print(f"Forbidden setting nickname for {member.name}", flush=True)
    except discord.HTTPException as exc:
        print(f"Failed setting nickname for {member.name}: {exc}", flush=True)
    return False


async def rename_existing_members(
    guild: discord.Guild,
    nickname: str,
) -> tuple[int, int]:
    renamed = 0
    skipped = 0
    for member in guild.members:
        if member.bot:
            continue
        if await apply_join_nickname(member, nickname):
            renamed += 1
        else:
            skipped += 1
        await asyncio.sleep(0.3)
    return renamed, skipped


class ConfirmRenameView(discord.ui.View):
    def __init__(self, guild: discord.Guild, nickname: str, author_id: int):
        super().__init__(timeout=60)
        self.guild = guild
        self.nickname = nickname
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation isn't yours.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Yes, rename everyone", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="Renaming everyone… this can take a moment.",
            view=None,
        )
        renamed, skipped = await rename_existing_members(self.guild, self.nickname)
        result = f"Renamed **{renamed}** member(s) to **{truncate_nickname(self.nickname)}**."
        if skipped:
            result += (
                f" Skipped **{skipped}** (already named, owner, higher role, "
                "or missing permission)."
            )
        await interaction.edit_original_response(content=result)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Cancelled. No existing members were renamed.",
            view=None,
        )
        self.stop()


async def assign_roles_to_member(
    member: discord.Member,
    role_ids: list[int],
    reason: str,
) -> list[str]:
    assigned: list[str] = []
    for role_id in role_ids:
        role = member.guild.get_role(role_id)
        if role is None:
            continue
        if role in member.roles:
            continue
        block_reason = role_assign_block_reason(member.guild, role)
        if block_reason:
            print(f"Cannot assign {role.name}: {block_reason}", flush=True)
            continue
        try:
            await member.add_roles(role, reason=reason)
            assigned.append(role.name)
        except discord.Forbidden:
            print(f"Forbidden assigning {role.name} to {member.display_name}", flush=True)
        except discord.HTTPException as exc:
            print(f"Failed assigning {role.name}: {exc}", flush=True)
    return assigned


class JoinRoleIdsModal(discord.ui.Modal, title="Join Role IDs"):
    role_ids = discord.ui.TextInput(
        label="Role IDs (one or more)",
        style=discord.TextStyle.paragraph,
        placeholder="Paste role IDs separated by spaces or commas",
        min_length=17,
        max_length=500,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ids = parse_role_ids(self.role_ids.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        names = []
        for role_id in ids:
            role = interaction.guild.get_role(role_id)
            if role is None:
                await interaction.response.send_message(
                    f"Role `{role_id}` was not found.",
                    ephemeral=True,
                )
                return
            names.append(role.name)

        data = get_guild_autorole(interaction.guild_id)
        data["join_roles"] = ids
        set_guild_autorole(interaction.guild_id, data)

        await interaction.response.edit_message(
            content=(
                f"**Join roles saved ({len(ids)}):** "
                + ", ".join(f"**{name}**" for name in names)
                + "\nNew members will get these roles automatically."
            ),
            view=None,
        )


class JoinRolesSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, page: int, total_pages: int):
        options = build_role_options(get_autorole_roles(guild), page, show_rank=True)
        placeholder = "Select roles to give on join (lowest first)..."
        if total_pages > 1:
            placeholder = f"Join roles — page {page + 1}/{total_pages}..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max(1, min(MAX_SELECT_CHANNELS, len(options))),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        role_ids = [int(value) for value in self.values]
        data = get_guild_autorole(interaction.guild_id)
        data["join_roles"] = role_ids
        set_guild_autorole(interaction.guild_id, data)

        names = []
        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                names.append(role.name)

        await interaction.response.edit_message(
            content=(
                f"**Join roles saved ({len(role_ids)}):** "
                + ", ".join(f"**{name}**" for name in names)
                + "\nNew members will get these roles automatically."
            ),
            view=None,
        )


class JoinRoleConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.page = page
        self.roles = get_autorole_roles(guild)
        self.total_pages = max(
            1,
            (len(self.roles) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.roles:
            return

        self.add_item(JoinRolesSelect(self.guild, self.page, self.total_pages))

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        id_btn = discord.ui.Button(
            label="Enter Role IDs",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        id_btn.callback = self._enter_ids
        self.add_item(id_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _enter_ids(self, interaction: discord.Interaction):
        await interaction.response.send_modal(JoinRoleIdsModal())


class ReactionChannelIdModal(discord.ui.Modal, title="Trigger Channel ID"):
    channel_id = discord.ui.TextInput(
        label="Text channel ID",
        placeholder="Paste the channel ID here",
        min_length=17,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_id.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "That is not a valid text channel.",
                ephemeral=True,
            )
            return

        view = ReactionEmojiView(interaction.guild, channel_id)
        await interaction.response.edit_message(
            content=(
                f"**Step 2:** Pick the emoji staff use to approve messages in **#{channel.name}**.\n"
                "Choose one **server emoji** (`:Garrison:` or `:TC:`) or one **Discord emoji** below."
            ),
            view=view,
        )


class ReactionChannelSelect(discord.ui.Select):
    def __init__(
        self,
        channels: list[discord.TextChannel],
        page: int,
        total_pages: int,
    ):
        options = build_text_channel_options(channels, page)
        placeholder = "Choose the trigger channel..."
        if total_pages > 1:
            placeholder = f"Trigger channel — page {page + 1}/{total_pages}..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        channel_name = channel.name if channel else str(channel_id)

        view = ReactionEmojiView(interaction.guild, channel_id)
        await interaction.response.edit_message(
            content=(
                f"**Step 2:** Pick the emoji staff use to approve messages in **#{channel_name}**.\n"
                "Choose one **server emoji** (`:Garrison:` or `:TC:`) or one **Discord emoji** below."
            ),
            view=view,
        )


class ReactionChannelView(discord.ui.View):
    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.page = page
        self.channels = get_sorted_text_channels(guild)
        self.total_pages = max(
            1,
            (len(self.channels) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.channels:
            return

        self.add_item(
            ReactionChannelSelect(self.channels, self.page, self.total_pages)
        )

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        id_btn = discord.ui.Button(
            label="Enter Channel ID",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        id_btn.callback = self._enter_id
        self.add_item(id_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _enter_id(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ReactionChannelIdModal())


class ReactionCustomEmojiSelect(discord.ui.Select):
    def __init__(
        self,
        guild: discord.Guild,
        channel_id: int,
        emojis: list[discord.Emoji],
    ):
        options = [
            discord.SelectOption(
                label=emoji.name[:100],
                value=str(emoji.id),
                emoji=emoji,
            )
            for emoji in emojis
        ]
        super().__init__(
            placeholder="Server emojis — :Garrison: or :TC:",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.guild = guild
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        emoji = discord.utils.get(self.guild.emojis, id=int(self.values[0]))
        if emoji is None:
            await interaction.response.send_message("That emoji was not found.", ephemeral=True)
            return
        await show_reaction_role_picker(
            interaction,
            self.guild,
            self.channel_id,
            str(emoji),
        )


class ReactionStandardEmojiSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, channel_id: int):
        options = [
            discord.SelectOption(label=emoji, value=emoji, emoji=emoji)
            for emoji in REACTION_STANDARD_EMOJIS
        ]
        super().__init__(
            placeholder="Discord emojis — ✅ ⭐ 👍 and more",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )
        self.guild = guild
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await show_reaction_role_picker(
            interaction,
            self.guild,
            self.channel_id,
            self.values[0],
        )


class ReactionEmojiView(discord.ui.View):
    def __init__(self, guild: discord.Guild, channel_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.channel_id = channel_id

        server_emojis = get_reaction_server_emojis(guild)
        if server_emojis:
            self.add_item(ReactionCustomEmojiSelect(guild, channel_id, server_emojis))
        self.add_item(ReactionStandardEmojiSelect(guild, channel_id))


class ReactionRoleIdsModal(discord.ui.Modal, title="Award Role IDs"):
    role_ids = discord.ui.TextInput(
        label="Role IDs (one or more)",
        style=discord.TextStyle.paragraph,
        placeholder="Paste role IDs separated by spaces or commas",
        min_length=17,
        max_length=500,
    )

    def __init__(self, channel_id: int, emoji: str):
        super().__init__()
        self.channel_id = channel_id
        self.emoji = emoji

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ids = parse_role_ids(self.role_ids.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        role_names = []
        for role_id in ids:
            role = interaction.guild.get_role(role_id)
            if role is None:
                await interaction.response.send_message(
                    f"Role `{role_id}` was not found.",
                    ephemeral=True,
                )
                return
            role_names.append(role.name)

        save_reaction_trigger(
            interaction.guild_id,
            self.channel_id,
            self.emoji,
            ids,
            guild=interaction.guild,
        )
        channel = interaction.guild.get_channel(self.channel_id)
        emoji_label = format_trigger_emoji_display(interaction.guild, self.emoji)

        await interaction.response.edit_message(
            content=(
                f"**Reaction trigger saved.**\n"
                f"**Channel:** {channel.mention if channel else self.channel_id}\n"
                f"**Emoji:** {emoji_label}\n"
                f"**Roles:** {', '.join(f'**{n}**' for n in role_names)}"
            ),
            view=None,
        )


class ReactionRolesSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, channel_id: int, emoji: str, page: int, total_pages: int):
        self.channel_id = channel_id
        self.emoji = emoji
        options = build_role_options(get_autorole_roles(guild), page, show_rank=True)
        placeholder = "Choose role(s) to award (lowest first)..."
        if total_pages > 1:
            placeholder = f"Award roles — page {page + 1}/{total_pages}..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max(1, min(MAX_SELECT_CHANNELS, len(options))),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        role_ids = [int(value) for value in self.values]
        save_reaction_trigger(
            interaction.guild_id,
            self.channel_id,
            self.emoji,
            role_ids,
            guild=interaction.guild,
        )

        channel = interaction.guild.get_channel(self.channel_id)
        role_names = []
        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                role_names.append(role.name)
        emoji_label = format_trigger_emoji_display(interaction.guild, self.emoji)

        await interaction.response.edit_message(
            content=(
                f"**Reaction trigger saved.**\n"
                f"**Channel:** {channel.mention if channel else self.channel_id}\n"
                f"**Emoji:** {emoji_label}\n"
                f"**Roles:** {', '.join(f'**{n}**' for n in role_names)}"
            ),
            view=None,
        )


class ReactionRoleConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, channel_id: int, emoji: str, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.channel_id = channel_id
        self.emoji = emoji
        self.page = page
        self.roles = get_autorole_roles(guild)
        self.total_pages = max(
            1,
            (len(self.roles) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.roles:
            return

        self.add_item(
            ReactionRolesSelect(
                self.guild, self.channel_id, self.emoji, self.page, self.total_pages
            )
        )

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        id_btn = discord.ui.Button(
            label="Enter Role IDs",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        id_btn.callback = self._enter_ids
        self.add_item(id_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _enter_ids(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            ReactionRoleIdsModal(self.channel_id, self.emoji)
        )


autorole_group = app_commands.Group(
    name="autoroleconfig",
    description="Configure join roles and staff reaction approvals",
)


@autorole_group.command(name="view", description="Show current auto-role setup")
@admin_only()
async def autorole_view(interaction: discord.Interaction):
    await interaction.response.send_message(
        format_autorole_summary(interaction.guild),
        ephemeral=True,
    )


@autorole_group.command(name="join", description="Set which roles new members get")
@admin_only()
async def autorole_join(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    roles = get_autorole_roles(interaction.guild)
    if not roles:
        await interaction.followup.send(
            "No assignable roles found. Move the bot role above the roles you want to give.",
            ephemeral=True,
        )
        return

    extra = ""
    if len(roles) > MAX_SELECT_CHANNELS:
        extra = (
            f"\n\nShowing **{len(roles)}** roles ({MAX_SELECT_CHANNELS} per page). "
            "Lowest ranks first — use **Next** or **Enter Role IDs**."
        )

    current = get_guild_autorole(interaction.guild.id).get("join_roles", [])
    current_text = ""
    if current:
        names = [
            interaction.guild.get_role(rid).name
            for rid in current
            if interaction.guild.get_role(rid)
        ]
        if names:
            current_text = f"\n\n**Current:** {', '.join(f'**{n}**' for n in names)}"

    view = JoinRoleConfigView(interaction.guild)
    await interaction.followup.send(
        "**Pick all roles** new members should get when they join."
        + current_text
        + extra,
        view=view,
        ephemeral=True,
    )


@autorole_group.command(
    name="reaction",
    description="When staff react to a message, award roles to the message author",
)
@admin_only()
async def autorole_reaction(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channels = get_sorted_text_channels(interaction.guild)
    if not channels:
        await interaction.followup.send("This server has no text channels.", ephemeral=True)
        return

    extra = ""
    if len(channels) > MAX_SELECT_CHANNELS:
        extra = (
            f"\n\nShowing **{len(channels)}** channels ({MAX_SELECT_CHANNELS} per page). "
            "Use **Next** or **Enter Channel ID** if yours isn't listed."
        )

    view = ReactionChannelView(interaction.guild)
    await interaction.followup.send(
        "**Step 1:** Pick the channel where members post (e.g. applications).\n"
        "When staff react to someone's message, **that message's author** gets the role.\n"
        "Use the menu, **Next** to page through all channels, or **Enter Channel ID**."
        + extra,
        view=view,
        ephemeral=True,
    )


@autorole_group.command(
    name="nickname",
    description="Set the exact nickname every new member gets",
)
@app_commands.describe(
    nickname="The exact nickname for new members (e.g. doofus). Leave empty to disable.",
    apply_to_existing="Ask for confirmation to also rename everyone already in the server.",
)
@admin_only()
async def autorole_nickname(
    interaction: discord.Interaction,
    nickname: str = "",
    apply_to_existing: bool = False,
):
    await interaction.response.defer(ephemeral=True)

    nickname = nickname.strip()
    data = get_guild_autorole(interaction.guild.id)
    data["join_nickname"] = nickname
    set_guild_autorole(interaction.guild.id, data)

    if not nickname:
        await interaction.followup.send(
            "Auto-nickname **disabled**. New members keep their own names.",
            ephemeral=True,
        )
        return

    final = truncate_nickname(nickname)
    trim_note = f"\n(Trimmed to 32 characters: `{final}`)" if final != nickname else ""

    me = interaction.guild.me
    perm_note = ""
    if me is None or not me.guild_permissions.manage_nicknames:
        perm_note = (
            "\n\n**Heads up:** I need **Manage Nicknames** and my role must be "
            "**above** members for renaming to work."
        )

    summary = (
        f"Auto-nickname **enabled**.\n"
        f"Every new member will be named **{final}**."
        + trim_note
        + perm_note
    )

    if not apply_to_existing:
        await interaction.followup.send(summary, ephemeral=True)
        return

    members = [m for m in interaction.guild.members if not m.bot]
    view = ConfirmRenameView(interaction.guild, nickname, interaction.user.id)
    await interaction.followup.send(
        summary
        + f"\n\n**Are you sure?** This will rename all **{len(members)}** current "
        f"member(s) to **{final}**.",
        view=view,
        ephemeral=True,
    )


@autorole_group.command(name="clear", description="Clear all auto-role settings")
@admin_only()
async def autorole_clear(interaction: discord.Interaction):
    set_guild_autorole(
        interaction.guild_id,
        {"join_roles": [], "reaction_triggers": [], "join_nickname": ""},
    )
    await interaction.response.send_message(
        "Auto-role config cleared.",
        ephemeral=True,
    )


bot.tree.add_command(autorole_group)


@bot.event
async def on_member_join(member: discord.Member):
    data = get_guild_autorole(member.guild.id)

    join_nickname = data.get("join_nickname", "")
    if join_nickname:
        await apply_join_nickname(member, join_nickname)

    role_ids = data.get("join_roles", [])
    if not role_ids:
        return

    assigned = await assign_roles_to_member(member, role_ids, "Auto-role on join")
    if assigned:
        print(f"Join roles for {member.display_name}: {assigned}", flush=True)

    await sync_orbat_member(member)


@bot.event
async def on_member_remove(member: discord.Member):
    if member.bot:
        return
    await asyncio.to_thread(set_member_active, member.guild.id, member.id, False)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    if after.bot:
        return
    if (
        before.display_name != after.display_name
        or before.roles != after.roles
    ):
        await sync_orbat_member(after)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id is None:
        return
    if payload.user_id == bot.user.id:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        try:
            guild = await bot.fetch_guild(payload.guild_id)
        except discord.HTTPException as exc:
            print(f"Reaction: guild {payload.guild_id} unavailable: {exc}", flush=True)
            return

    data = get_guild_autorole(guild.id)
    triggers = data.get("reaction_triggers", [])
    if not triggers:
        return

    effective_channel_id = await resolve_parent_channel_id(guild, payload.channel_id)
    matching = [
        trigger
        for trigger in triggers
        if trigger_matches_reaction(trigger, payload, effective_channel_id)
    ]
    if not matching:
        return

    recipient = await resolve_reacted_message_author(guild, payload)
    if recipient is None:
        return

    reactor = guild.get_member(payload.user_id)
    if reactor is None:
        try:
            reactor = await guild.fetch_member(payload.user_id)
        except (discord.NotFound, discord.HTTPException):
            reactor = None

    for trigger in matching:
        role_ids = trigger.get("role_ids", [])
        if not role_ids:
            continue

        emoji = trigger["emoji"]
        missing = roles_member_is_missing(recipient, role_ids)
        if not missing:
            already = [
                recipient.guild.get_role(role_id).name
                for role_id in role_ids
                if recipient.guild.get_role(role_id) is not None
            ]
            reactor_name = reactor.display_name if reactor else str(payload.user_id)
            print(
                f"Reaction: {recipient.display_name} already has {already} "
                f"({emoji}, reacted by {reactor_name})",
                flush=True,
            )
            continue

        assigned = await assign_roles_to_member(
            recipient,
            role_ids,
            f"Reaction approval {emoji}",
        )
        reactor_name = reactor.display_name if reactor else str(payload.user_id)
        if assigned:
            print(
                f"Reaction roles for {recipient.display_name} ({emoji}, "
                f"approved by {reactor_name}): {assigned}",
                flush=True,
            )
            continue

        failed: list[str] = []
        for role in missing:
            block_reason = role_assign_block_reason(recipient.guild, role)
            if block_reason:
                failed.append(f"{role.name}: {block_reason}")
            else:
                failed.append(f"{role.name}: assignment failed (check bot logs)")
        print(
            f"Reaction failed for {recipient.display_name} ({emoji}, "
            f"reacted by {reactor_name}): {failed}",
            flush=True,
        )


# --- PD configuration storage ---


def load_pd_store() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_pd_store(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def get_guild_pd(guild_id: int) -> dict:
    store = load_pd_store()
    key = str(guild_id)
    if key not in store:
        store[key] = {
            "channel_ids": [],
            "lock_role_id": None,
            "lock_role_ids": [],
            "bypass_role_ids": [],
            "active": False,
            "saved_permissions": {},
        }
    data = store[key]
    data.setdefault("lock_role_ids", [])
    data.setdefault("bypass_role_ids", [])
    return data


def set_guild_pd(guild_id: int, guild_data: dict) -> None:
    store = load_pd_store()
    store[str(guild_id)] = guild_data
    save_pd_store(store)


def format_say_embed_text(text: str) -> str:
    """Discord embeds collapse empty lines — use a zero-width space so they show."""
    lines = text.splitlines()
    if not lines:
        return text
    formatted: list[str] = []
    for line in lines:
        if line == "":
            formatted.append("\u200b")
        else:
            formatted.append(line)
    return "\n".join(formatted)


def make_say_embed(text: str) -> discord.Embed:
    return discord.Embed(
        description=format_say_embed_text(text),
        color=discord.Color.from_rgb(220, 20, 60),
    )


async def send_say_message(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    text: str,
) -> None:
    if not channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.followup.send(
            f"I can't send messages in {channel.mention}.",
            ephemeral=True,
        )
        return

    try:
        await channel.send(embed=make_say_embed(text))
        await interaction.followup.send(
            f"Message sent in {channel.mention}.",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            f"I don't have permission to send messages in {channel.mention}.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        await interaction.followup.send(f"Failed to send message: {exc}", ephemeral=True)


class PdRoleIdModal(discord.ui.Modal, title="Role ID"):
    role_id = discord.ui.TextInput(
        label="Role ID to lock",
        placeholder="Paste the role ID here",
        min_length=17,
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid role ID.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message("That role was not found.", ephemeral=True)
            return

        guild_data = get_guild_pd(interaction.guild_id)
        guild_data["lock_role_id"] = role.id
        guild_data["lock_role_ids"] = [role.id]
        set_guild_pd(interaction.guild_id, guild_data)

        view = PdChannelConfigView(interaction.guild, lock_role_id=role.id)
        await interaction.response.edit_message(
            content=(
                f"**Step 2:** Pick channels where **{role.name}** cannot send messages."
                + _pd_channel_extra_text(interaction.guild)
            ),
            view=view,
        )


class PdRoleMenu(discord.ui.Select):
    def __init__(self, guild: discord.Guild, page: int, total_pages: int):
        roles = get_pd_lock_roles(guild)
        options = build_role_options(roles, page, show_rank=True)
        placeholder = "Choose role to deny Send Messages (lowest first)..."
        if total_pages > 1:
            placeholder = f"Lowest roles first — page {page + 1}/{total_pages}..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if role is None:
            await interaction.response.send_message("That role was not found.", ephemeral=True)
            return

        guild_data = get_guild_pd(interaction.guild_id)
        guild_data["lock_role_id"] = role.id
        guild_data["lock_role_ids"] = [role.id]
        set_guild_pd(interaction.guild_id, guild_data)

        view = PdChannelConfigView(interaction.guild, lock_role_id=role.id)
        await interaction.response.edit_message(
            content=(
                f"**Step 2:** Pick channels where **{role.name}** cannot send messages."
                + _pd_channel_extra_text(interaction.guild)
            ),
            view=view,
        )


class PdRoleConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.page = page
        self.roles = get_pd_lock_roles(guild)
        self.total_pages = max(
            1,
            (len(self.roles) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.roles:
            return

        self.add_item(PdRoleMenu(self.guild, self.page, self.total_pages))

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        id_btn = discord.ui.Button(label="Enter Role ID", style=discord.ButtonStyle.secondary, row=2)
        id_btn.callback = self._enter_id
        self.add_item(id_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _enter_id(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PdRoleIdModal())


class PdChannelSelect(discord.ui.Select):
    def __init__(
        self,
        config_view: "PdChannelConfigView",
        channels: list[discord.TextChannel],
        page: int,
        total_pages: int,
    ):
        options = build_text_channel_options(channels, page)
        placeholder = "Choose channels to lock..."
        if total_pages > 1:
            placeholder = f"Choose channels (page {page + 1}/{total_pages})..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max(1, min(MAX_SELECT_CHANNELS, len(options))),
            options=options,
            row=0,
        )
        self.config_view = config_view

    async def callback(self, interaction: discord.Interaction):
        lock_role = interaction.guild.get_role(self.config_view.lock_role_id)
        if lock_role is None:
            await interaction.response.send_message(
                "That role no longer exists. Run `/pdconfig` again.",
                ephemeral=True,
            )
            return

        channel_ids = [int(value) for value in self.values]
        guild_data = get_guild_pd(interaction.guild_id)
        guild_data["channel_ids"] = channel_ids
        guild_data["lock_role_id"] = lock_role.id
        guild_data["lock_role_ids"] = [lock_role.id]
        guild_data["active"] = False
        guild_data["saved_permissions"] = {}
        set_guild_pd(interaction.guild_id, guild_data)

        channel_names = []
        for channel_id in channel_ids:
            channel = interaction.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                channel_names.append(channel.name)

        await interaction.response.edit_message(
            content=(
                f"PD config saved.\n"
                f"**Role:** {lock_role.mention} — **Send Messages** will be denied during PD\n"
                f"**Channels ({len(channel_ids)}):** "
                + ", ".join(f"**{name}**" for name in channel_names)
                + "\nUse `/pdon` to lock and `/pdoff` to unlock."
            ),
            view=None,
        )


class PdChannelConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, lock_role_id: int, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.lock_role_id = lock_role_id
        self.page = page
        self.channels = get_sorted_text_channels(guild)
        self.total_pages = max(
            1,
            (len(self.channels) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.channels:
            return

        self.add_item(PdChannelSelect(self, self.channels, self.page, self.total_pages))

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)


def _pd_channel_extra_text(guild: discord.Guild) -> str:
    channels = get_sorted_text_channels(guild)
    if len(channels) > MAX_SELECT_CHANNELS:
        return (
            f"\n\n{MAX_SELECT_CHANNELS} channels per page — use **Next** if you don't see yours."
        )
    return ""


PD_SEND_PERMISSION = "send_messages"
PD_SAVE_SKIP_KEYS = frozenset({"permissions_synced", "everyone_pair", "roles"})


def snapshot_send_messages(
    channel: discord.TextChannel,
    role: discord.Role,
) -> bool | None:
    """Channel-only overwrite — not merged category perms (synced channels)."""
    overwrite = channel.overwrites.get(role)
    if overwrite is None:
        return None
    return overwrite.send_messages


async def apply_send_messages(
    channel: discord.TextChannel,
    role: discord.Role,
    send_messages: bool | None,
    *,
    reason: str,
) -> discord.TextChannel:
    """Flip only Send Messages on this channel for one role."""
    existing = channel.overwrites.get(role)
    if send_messages is None and existing is None:
        return channel

    if existing is None:
        overwrite = discord.PermissionOverwrite(send_messages=send_messages)
    else:
        allow, deny = existing.pair()
        overwrite = discord.PermissionOverwrite.from_pair(allow, deny)
        overwrite.send_messages = send_messages

    if overwrite.is_empty():
        coro = channel.set_permissions(role, overwrite=None, reason=reason)
    else:
        coro = channel.set_permissions(role, overwrite=overwrite, reason=reason)
    await asyncio.wait_for(coro, timeout=10.0)

    refreshed = await channel.guild.fetch_channel(channel.id)
    if isinstance(refreshed, discord.TextChannel):
        return refreshed
    return channel


async def lock_role_send_messages(
    channel: discord.TextChannel,
    role: discord.Role,
    *,
    reason: str,
) -> discord.TextChannel:
    channel = await apply_send_messages(channel, role, False, reason=reason)

    overwrite = channel.overwrites.get(role)
    if overwrite is not None and overwrite.send_messages is False:
        return channel

    # Retry with a clean deny-only overwrite (handles odd synced/category states).
    await asyncio.wait_for(
        channel.set_permissions(
            role,
            overwrite=discord.PermissionOverwrite(send_messages=False),
            reason=reason,
        ),
        timeout=10.0,
    )
    refreshed = await channel.guild.fetch_channel(channel.id)
    if not isinstance(refreshed, discord.TextChannel):
        raise RuntimeError(
            f"Could not refresh channel `{channel.id}` after PD lock."
        )
    channel = refreshed

    overwrite = channel.overwrites.get(role)
    if overwrite is None or overwrite.send_messages is not False:
        raise RuntimeError(
            f"Send Messages is still not denied for **{role.name}** in **#{channel.name}**. "
            "Move the bot role **above** that role and give it **Manage Roles** + **Manage Channels**."
        )
    return channel


def extract_role_send_snapshots(
    perms: dict,
    guild_data: dict,
) -> dict[str, bool | None]:
    if not perms:
        return {}

    if "roles" in perms:
        snapshots: dict[str, bool | None] = {}
        for role_key, snapshot in perms["roles"].items():
            if role_key == "@everyone":
                continue
            if isinstance(snapshot, dict):
                snapshots[role_key] = snapshot.get(PD_SEND_PERMISSION)
            else:
                snapshots[role_key] = snapshot
        return snapshots

    if PD_SEND_PERMISSION in perms:
        lock_role_id = guild_data.get("lock_role_id")
        if lock_role_id:
            return {str(lock_role_id): perms[PD_SEND_PERMISSION]}
        return {}

    snapshots = {}
    for key, value in perms.items():
        if key in PD_SAVE_SKIP_KEYS:
            continue
        if isinstance(value, bool) or value is None:
            snapshots[key] = value
        elif isinstance(value, dict) and PD_SEND_PERMISSION in value:
            snapshots[key] = value[PD_SEND_PERMISSION]
    return snapshots


def resolve_pd_role(guild: discord.Guild, storage_key: str) -> discord.Role | None:
    if storage_key == "@everyone":
        return guild.default_role
    try:
        return guild.get_role(int(storage_key))
    except (TypeError, ValueError):
        return None


def bot_can_edit_channel_permissions(guild: discord.Guild, role: discord.Role) -> bool:
    me = guild.me
    if me is None:
        return False
    if not me.guild_permissions.manage_roles or not me.guild_permissions.manage_channels:
        return False
    if role.is_default():
        return True
    return me.top_role > role


def get_pd_lock_role_ids(guild_data: dict) -> list[int]:
    role_ids = list(guild_data.get("lock_role_ids", []))
    lock_role_id = guild_data.get("lock_role_id")
    if lock_role_id and lock_role_id not in role_ids:
        role_ids.append(lock_role_id)
    return role_ids


def get_pd_roles_to_lock(guild: discord.Guild, guild_data: dict) -> list[discord.Role]:
    roles: list[discord.Role] = []
    for role_id in get_pd_lock_role_ids(guild_data):
        role = guild.get_role(role_id)
        if role is not None and role not in roles:
            roles.append(role)
    return roles


def require_pd_lock_roles(guild: discord.Guild, guild_data: dict) -> list[discord.Role]:
    roles = get_pd_roles_to_lock(guild, guild_data)
    if not roles:
        raise ValueError(
            "No lock role configured. Run `/pdconfig`, pick the **role**, then pick channels."
        )
    return roles


async def get_text_channel(
    guild: discord.Guild,
    channel_id: int,
) -> discord.TextChannel | None:
    channel = guild.get_channel(channel_id)
    if isinstance(channel, discord.TextChannel):
        return channel

    try:
        fetched = await asyncio.wait_for(guild.fetch_channel(channel_id), timeout=8.0)
    except asyncio.TimeoutError:
        print(f"PD: timed out fetching channel {channel_id}", flush=True)
        return None
    except (discord.NotFound, discord.HTTPException) as exc:
        print(f"PD: could not fetch channel {channel_id}: {exc}", flush=True)
        return None

    if isinstance(fetched, discord.TextChannel):
        return fetched
    return None


async def unlock_channel_send_messages(
    channel: discord.TextChannel,
    guild: discord.Guild,
    guild_data: dict,
    perms: dict,
) -> None:
    sync_state = perms.get("permissions_synced")
    role_snapshots = extract_role_send_snapshots(perms, guild_data)
    if role_snapshots:
        for role_key, send_val in role_snapshots.items():
            role = resolve_pd_role(guild, role_key)
            if role is None or role.is_default():
                continue
            channel = await apply_send_messages(
                channel,
                role,
                send_val,
                reason="PD unlock",
            )
    else:
        for role in get_pd_roles_to_lock(guild, guild_data):
            channel = await apply_send_messages(
                channel,
                role,
                None,
                reason="PD unlock",
            )

    if sync_state is not None and channel.permissions_synced != sync_state:
        await channel.edit(permissions_synced=sync_state, reason="PD unlock")


async def lock_pd_channels(guild: discord.Guild) -> tuple[list[str], list[str]]:
    guild_data = get_guild_pd(guild.id)
    channel_ids = guild_data.get("channel_ids", [])
    if not channel_ids:
        raise ValueError("No PD channels configured. Run `/pdconfig` first.")

    if guild_data.get("active"):
        raise ValueError("PD mode is already on. Use `/pdoff` first.")

    roles_to_lock = require_pd_lock_roles(guild, guild_data)

    for role in roles_to_lock:
        if not bot_can_edit_channel_permissions(guild, role):
            raise ValueError(
                f"I can't edit channel permissions for **{role.name}**. "
                "Move my bot role **above** that role and give me **Manage Roles** + **Manage Channels**."
            )

    locked: list[str] = []
    failed: list[str] = []
    saved: dict[str, dict[str, bool | None]] = {}

    for channel_id in channel_ids:
        channel = await get_text_channel(guild, channel_id)
        if channel is None:
            failed.append(f"Missing channel `{channel_id}`")
            continue

        try:
            channel_saved: dict[str, bool | None] = {
                "permissions_synced": channel.permissions_synced,
            }
            for role in roles_to_lock:
                channel_saved[str(role.id)] = snapshot_send_messages(channel, role)
                channel = await lock_role_send_messages(
                    channel,
                    role,
                    reason="PD lock",
                )
                print(
                    f"PD lock: denied Send Messages for {role.name} in #{channel.name}",
                    flush=True,
                )

            saved[str(channel_id)] = channel_saved
            await channel.send(PD_MESSAGE)
            locked.append(channel.name)
        except asyncio.TimeoutError:
            failed.append(f"**{channel.name}**: timed out applying permissions")
        except RuntimeError as exc:
            failed.append(f"**{channel.name}**: {exc}")
        except discord.Forbidden:
            failed.append(f"**{channel.name}**: missing permissions")
        except discord.HTTPException as exc:
            failed.append(f"**{channel.name}**: {exc}")

    if locked:
        guild_data["active"] = True
        guild_data["saved_permissions"] = saved
        set_guild_pd(guild.id, guild_data)

    return locked, failed


async def _unlock_pd_channels(
    guild: discord.Guild,
    saved: dict,
    guild_data: dict,
) -> tuple[list[str], list[str]]:
    channel_ids: set[int] = set(guild_data.get("channel_ids", []))
    channel_ids.update(int(channel_id_str) for channel_id_str in saved)

    unlocked: list[str] = []
    failed: list[str] = []

    for channel_id in channel_ids:
        channel = await get_text_channel(guild, channel_id)
        if channel is None:
            failed.append(f"Missing channel `{channel_id}`")
            continue

        perms = saved.get(str(channel_id), {})
        try:
            await unlock_channel_send_messages(channel, guild, guild_data, perms)
            unlocked.append(channel.name)
        except discord.Forbidden:
            failed.append(f"**{channel.name}**: missing permissions")
        except discord.HTTPException as exc:
            failed.append(f"**{channel.name}**: {exc}")
        except Exception as exc:
            print(f"PD unlock error for #{channel.name}: {traceback.format_exc()}", flush=True)
            failed.append(f"**{channel.name}**: {exc}")

    return unlocked, failed


def get_pd_restore_context(guild_data: dict) -> dict:
    return {
        "channel_ids": list(guild_data.get("channel_ids", [])),
        "lock_role_id": guild_data.get("lock_role_id"),
        "lock_role_ids": list(guild_data.get("lock_role_ids", [])),
    }


def clear_pd_active_state(guild_id: int) -> tuple[dict, dict]:
    guild_data = get_guild_pd(guild_id)
    if not guild_data.get("active") and not guild_data.get("saved_permissions"):
        raise ValueError("PD mode is not active.")

    saved = dict(guild_data.get("saved_permissions", {}))
    restore_context = get_pd_restore_context(guild_data)
    guild_data["active"] = False
    guild_data["saved_permissions"] = {}
    set_guild_pd(guild_id, guild_data)
    return saved, restore_context


async def recover_stale_pd_on_startup(guild: discord.Guild) -> None:
    """If the bot was offline/crashed during PD, unlock channels and mark PD off."""
    guild_data = get_guild_pd(guild.id)
    if not guild_data.get("active") and not guild_data.get("saved_permissions"):
        return

    saved = dict(guild_data.get("saved_permissions", {}))
    restore_context = get_pd_restore_context(guild_data)
    was_active = bool(guild_data.get("active"))

    guild_data["active"] = False
    guild_data["saved_permissions"] = {}
    set_guild_pd(guild.id, guild_data)

    if not saved:
        if was_active:
            print(
                f"PD auto-off for {guild.name}: marked inactive after bot restart.",
                flush=True,
            )
        return

    try:
        unlocked, failed = await restore_pd_permissions(guild, saved, restore_context)
        note = f"restored {len(unlocked)} channel(s)"
        if failed:
            note += f", {len(failed)} failed"
        print(f"PD auto-off for {guild.name}: {note}.", flush=True)
    except Exception:
        print(
            f"PD auto-off failed for {guild.name}:\n{traceback.format_exc()}",
            flush=True,
        )


async def restore_pd_permissions(
    guild: discord.Guild,
    saved: dict,
    restore_context: dict,
) -> tuple[list[str], list[str]]:
    try:
        return await asyncio.wait_for(
            _unlock_pd_channels(guild, saved, restore_context),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise ValueError(
            "Restoring Send Messages timed out. Check that the bot has "
            "**Manage Channels** and **Manage Roles**."
        ) from None


async def _pdoff_restore_permissions(
    guild: discord.Guild,
    saved: dict,
    restore_context: dict,
) -> None:
    try:
        unlocked, failed = await restore_pd_permissions(guild, saved, restore_context)
        if failed:
            print(
                f"PD off: restored {unlocked}, but some channels failed: {failed}",
                flush=True,
            )
        else:
            print(f"PD off: restored Send Messages in {unlocked}", flush=True)
    except Exception:
        print(f"PD off background restore failed:\n{traceback.format_exc()}", flush=True)


def user_can_manage_pd(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    perms = interaction.user.guild_permissions
    return perms.manage_channels or perms.administrator


@bot.tree.command(
    name="order",
    description="Join one or more voice channels and speak your message in each",
)
async def order(interaction: discord.Interaction):
    if not await defer_ephemeral(interaction):
        return

    guild = interaction.guild
    if guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not guild.voice_channels:
        await interaction.followup.send(
            "This server has no voice channels.",
            ephemeral=True,
        )
        return

    extra = ""
    if len(guild.voice_channels) > MAX_VOICE_CHANNELS:
        extra = (
            f"\n\nOnly the first {MAX_VOICE_CHANNELS} channels are shown in the menu. "
            "Use **Enter Channel IDs** for any others."
        )

    view = OrderView(guild)
    await interaction.followup.send(
        "Use the **select menu** below to pick one or more voice channels, "
        "or click **Enter Channel IDs** to paste IDs manually. "
        "The bot will speak your message in every channel you pick."
        + extra,
        view=view,
        ephemeral=True,
    )


class SayMessageModal(discord.ui.Modal, title="Your Message"):
    message = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        placeholder="Paste or type your message — blank lines are kept.",
        max_length=4000,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command only works in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        channels = get_sorted_text_channels(interaction.guild)
        if not channels:
            await interaction.followup.send(
                "This server has no text channels.",
                ephemeral=True,
            )
            return

        extra = ""
        if len(channels) > MAX_SELECT_CHANNELS:
            extra = (
                f"\n\nShowing {MAX_SELECT_CHANNELS} channels per page "
                f"({len(channels)} total). Use **Next** to see more."
            )

        view = SayChannelView(interaction.guild, self.message.value)
        await interaction.followup.send(
            "Pick the text channel to send your message in."
            + extra,
            view=view,
            ephemeral=True,
        )


class SayChannelIdModal(discord.ui.Modal, title="Text Channel ID"):
    channel_id = discord.ui.TextInput(
        label="Channel ID",
        placeholder="Paste the text channel ID here",
        min_length=17,
        max_length=20,
    )

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_id.value.strip())
        except ValueError:
            await interaction.response.send_message("Invalid channel ID.", ephemeral=True)
            return

        if not await defer_ephemeral(interaction):
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            try:
                fetched = await interaction.guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.HTTPException):
                fetched = None
            channel = fetched if isinstance(fetched, discord.TextChannel) else None

        if channel is None:
            await interaction.followup.send(
                "That is not a valid text channel.",
                ephemeral=True,
            )
            return

        await send_say_message(interaction, channel, self.text)


class SayChannelSelect(discord.ui.Select):
    def __init__(self, channels: list[discord.TextChannel], text: str, page: int, total_pages: int):
        options = build_text_channel_options(channels, page)
        placeholder = "Choose a text channel..."
        if total_pages > 1:
            placeholder = f"Choose a text channel (page {page + 1}/{total_pages})..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.text = text

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        if not await defer_ephemeral(interaction):
            return

        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            try:
                fetched = await interaction.guild.fetch_channel(channel_id)
            except (discord.NotFound, discord.HTTPException):
                fetched = None
            channel = fetched if isinstance(fetched, discord.TextChannel) else None

        if channel is None:
            await interaction.followup.send(
                "Could not find that text channel.",
                ephemeral=True,
            )
            return

        await send_say_message(interaction, channel, self.text)


class SayChannelView(discord.ui.View):
    def __init__(self, guild: discord.Guild, text: str, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.text = text
        self.page = page
        self.channels = get_sorted_text_channels(guild)
        self.total_pages = max(
            1,
            (len(self.channels) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        if not self.channels:
            return

        self.add_item(
            SayChannelSelect(self.channels, self.text, self.page, self.total_pages)
        )

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=1)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

        id_btn = discord.ui.Button(
            label="Enter Channel ID",
            style=discord.ButtonStyle.secondary,
            row=2,
        )
        id_btn.callback = self._enter_id
        self.add_item(id_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _enter_id(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SayChannelIdModal(self.text))


@bot.tree.command(
    name="say",
    description="Send a multi-line message in a text channel as an embed",
)
async def say(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    await interaction.response.send_modal(SayMessageModal())


@bot.tree.command(name="purge", description="Delete recent messages in this channel")
@app_commands.describe(amount="How many messages to delete (max 50)")
async def purge(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, MAX_PURGE],
):
    if not isinstance(interaction.channel, discord.TextChannel):
        await interaction.response.send_message(
            "This command only works in text channels.",
            ephemeral=True,
        )
        return

    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "You need **Manage Messages** to use this.",
            ephemeral=True,
        )
        return

    if not interaction.channel.permissions_for(interaction.guild.me).manage_messages:
        await interaction.response.send_message(
            "I need **Manage Messages** in this channel.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(
            f"Deleted **{len(deleted)}** message(s).",
            ephemeral=True,
        )
    except discord.Forbidden:
        await interaction.followup.send(
            "I don't have permission to delete messages here.",
            ephemeral=True,
        )
    except discord.HTTPException as exc:
        await interaction.followup.send(f"Failed to purge messages: {exc}", ephemeral=True)


@bot.tree.command(
    name="pdconfig",
    description="Choose a role and channels for PD mode (denies Send Messages only)",
)
async def pdconfig(interaction: discord.Interaction):
    if not await defer_ephemeral(interaction):
        return

    if interaction.guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_pd(interaction):
        await interaction.followup.send(
            "You need **Manage Channels** to configure PD mode.",
            ephemeral=True,
        )
        return

    channels = get_sorted_text_channels(interaction.guild)
    if not channels:
        await interaction.followup.send(
            "This server has no text channels.",
            ephemeral=True,
        )
        return

    guild_data = get_guild_pd(interaction.guild.id)
    current = ""
    lock_roles = get_pd_roles_to_lock(interaction.guild, guild_data)
    if lock_roles:
        current += f"\n\n**Current role:** {', '.join(r.mention for r in lock_roles)}"
    if guild_data.get("channel_ids"):
        names = []
        for channel_id in guild_data["channel_ids"]:
            channel = interaction.guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                names.append(channel.name)
        if names:
            current += f"\n**Current channels:** {', '.join(f'**{n}**' for n in names)}"

    roles = get_pd_lock_roles(interaction.guild)
    role_extra = ""
    if len(roles) > MAX_SELECT_CHANNELS:
        role_extra = (
            f"\n\nShowing **{len(roles)}** roles ({MAX_SELECT_CHANNELS} per page). "
            "Lowest ranks first — use **Next** for higher roles."
        )
    elif not roles:
        role_extra = (
            "\n\nNo lockable roles found. Move the bot role above the role you want to lock."
        )

    view = PdRoleConfigView(interaction.guild)
    await interaction.followup.send(
        "**Step 1:** Pick the role to deny **Send Messages** for during PD.\n"
        "Then pick the channels on the next screen. `/pdon` only changes **Send Messages**."
        + current
        + role_extra,
        view=view,
        ephemeral=True,
    )


@bot.tree.command(name="pdconfigclear", description="Clear all PD configuration")
async def pdconfigclear(interaction: discord.Interaction):
    if not await defer_ephemeral(interaction):
        return

    if interaction.guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_pd(interaction):
        await interaction.followup.send(
            "You need **Manage Channels** to configure PD mode.",
            ephemeral=True,
        )
        return

    guild_data = get_guild_pd(interaction.guild.id)
    unlocked_note = ""
    if guild_data.get("active") or guild_data.get("saved_permissions"):
        try:
            saved, restore_context = clear_pd_active_state(interaction.guild.id)
            unlocked, _ = await restore_pd_permissions(
                interaction.guild,
                saved,
                restore_context,
            )
            if unlocked:
                unlocked_note = f"\nAlso unlocked {len(unlocked)} active PD channel(s)."
        except ValueError:
            pass

    set_guild_pd(
        interaction.guild_id,
        {
            "channel_ids": [],
            "lock_role_id": None,
            "lock_role_ids": [],
            "bypass_role_ids": [],
            "active": False,
            "saved_permissions": {},
        },
    )
    await interaction.followup.send(
        "PD config cleared." + unlocked_note,
        ephemeral=True,
    )


@bot.tree.command(name="pdon", description="Lock configured channels and announce PD")
async def pdon(interaction: discord.Interaction):
    if not await defer_ephemeral(interaction):
        return

    if interaction.guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_pd(interaction):
        await interaction.followup.send(
            "You need **Manage Channels** to use PD mode.",
            ephemeral=True,
        )
        return

    try:
        locked, failed = await lock_pd_channels(interaction.guild)
    except ValueError as exc:
        await interaction.followup.send(str(exc), ephemeral=True)
        return

    lock_roles = get_pd_roles_to_lock(interaction.guild, get_guild_pd(interaction.guild.id))
    role_text = ", ".join(f"**{r.name}**" for r in lock_roles) if lock_roles else "configured role"

    if locked and not failed:
        await interaction.followup.send(
            f"PD mode **ON**. Denied **Send Messages** for {role_text} in "
            f"{len(locked)} channel(s): "
            + ", ".join(f"**{name}**" for name in locked),
            ephemeral=True,
        )
    elif locked and failed:
        await interaction.followup.send(
            f"PD mode **ON** for {len(locked)} channel(s), but some failed:\n"
            + "\n".join(failed),
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "PD mode failed for every channel:\n" + "\n".join(failed),
            ephemeral=True,
        )


@bot.tree.command(name="pdoff", description="Unlock channels locked by PD mode")
async def pdoff(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_pd(interaction):
        await interaction.response.send_message(
            "You need **Manage Channels** to use PD mode.",
            ephemeral=True,
        )
        return

    try:
        saved, restore_context = clear_pd_active_state(interaction.guild.id)
    except ValueError as exc:
        await interaction.response.send_message(str(exc), ephemeral=True)
        return

    await interaction.response.send_message(
        "PD mode **OFF**. Restoring **Send Messages** now.",
        ephemeral=True,
    )
    asyncio.create_task(
        _pdoff_restore_permissions(interaction.guild, saved, restore_context)
    )


# --- Squad configuration ---


def load_squad_store() -> dict:
    if not os.path.exists(SQUAD_CONFIG_PATH):
        return {}
    try:
        with open(SQUAD_CONFIG_PATH, encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def save_squad_store(data: dict) -> None:
    with open(SQUAD_CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def get_guild_squad(guild_id: int) -> dict:
    store = load_squad_store()
    key = str(guild_id)
    if key not in store:
        store[key] = {
            "staff_role_ids": [],
            "category_id": None,
            "squads": [],
        }
    data = store[key]
    data.setdefault("staff_role_ids", [])
    data.setdefault("category_id", None)
    data.setdefault("squads", [])
    return data


def set_guild_squad(guild_id: int, guild_data: dict) -> None:
    store = load_squad_store()
    store[str(guild_id)] = guild_data
    save_squad_store(store)


def sanitize_voice_channel_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "", name.strip().lower())
    cleaned = re.sub(r"\s+", "-", cleaned).strip("-")
    return (cleaned or "squad")[:100]


def user_can_manage_squads(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    perms = interaction.user.guild_permissions
    return perms.manage_channels or perms.administrator


def get_squads_for_delete(guild: discord.Guild) -> list[dict]:
    active = prune_squad_records(guild)
    if active:
        return active

    category = get_squad_category(guild)
    if category is None:
        return []

    return [
        {"channel_id": channel.id, "name": channel.name}
        for channel in category.voice_channels
    ]


def prune_squad_records(guild: discord.Guild) -> list[dict]:
    data = get_guild_squad(guild.id)
    squads = data.get("squads", [])
    active: list[dict] = []
    for entry in squads:
        channel_id = entry.get("channel_id")
        if channel_id is None:
            continue
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.VoiceChannel):
            active.append(
                {
                    "channel_id": channel_id,
                    "name": entry.get("name") or channel.name,
                }
            )
    if active != squads:
        data["squads"] = active
        set_guild_squad(guild.id, data)
    return active


def add_squad_record(guild_id: int, channel_id: int, name: str) -> None:
    data = get_guild_squad(guild_id)
    squads = data.setdefault("squads", [])
    squads.append({"channel_id": channel_id, "name": name})
    set_guild_squad(guild_id, data)


def remove_squad_record(guild_id: int, channel_id: int) -> None:
    data = get_guild_squad(guild_id)
    squads = data.get("squads", [])
    data["squads"] = [
        entry for entry in squads if entry.get("channel_id") != channel_id
    ]
    set_guild_squad(guild_id, data)


def get_squad_category(guild: discord.Guild) -> discord.CategoryChannel | None:
    category_id = get_guild_squad(guild.id).get("category_id")
    if not category_id:
        return None
    channel = guild.get_channel(category_id)
    if isinstance(channel, discord.CategoryChannel):
        return channel
    return None


def format_squad_config_summary(guild: discord.Guild) -> str:
    data = get_guild_squad(guild.id)
    lines: list[str] = []

    category = get_squad_category(guild)
    if category:
        lines.append(f"**Category:** {category.name}")
    else:
        lines.append("**Category:** not set (squads go at the top level)")

    role_ids = data.get("staff_role_ids", [])
    if role_ids:
        mentions = []
        for role_id in role_ids:
            role = guild.get_role(role_id)
            mentions.append(role.mention if role else f"`{role_id}`")
        lines.append("**Staff roles:** " + ", ".join(mentions))
    else:
        lines.append("**Staff roles:** none (only squad members see their VC)")

    active = prune_squad_records(guild)
    lines.append(f"**Active squads:** {len(active)}")
    return "\n".join(lines)


async def resolve_guild_member(
    guild: discord.Guild,
    user_id: int,
) -> discord.Member | None:
    member = guild.get_member(user_id)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def create_squad_voice_channel(
    guild: discord.Guild,
    squad_name: str,
    members: list[discord.Member],
    creator: discord.Member,
) -> discord.VoiceChannel:
    squad_data = get_guild_squad(guild.id)
    staff_role_ids = squad_data.get("staff_role_ids", [])

    overwrites: dict[discord.Role | discord.Member, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
    }

    me = guild.me
    if me is not None:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
            manage_channels=True,
            move_members=True,
        )

    for role_id in staff_role_ids:
        role = guild.get_role(role_id)
        if role is not None:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
            )

    for member in members:
        overwrites[member] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
        )

    creator_ids = {member.id for member in members}
    creator_has_staff = any(role.id in staff_role_ids for role in creator.roles)
    if creator.id not in creator_ids and not creator_has_staff:
        overwrites[creator] = discord.PermissionOverwrite(
            view_channel=True,
            connect=True,
            speak=True,
        )

    channel_name = sanitize_voice_channel_name(squad_name)
    category = get_squad_category(guild)
    return await guild.create_voice_channel(
        name=channel_name,
        overwrites=overwrites,
        category=category,
        reason=f"Squad '{squad_name}' created by {creator}",
    )


async def notify_squad_members(
    members: list[discord.Member],
    channel: discord.VoiceChannel,
) -> tuple[int, int]:
    sent = 0
    failed = 0
    message = f"A squad has been created, join this VC: {channel.mention}"
    for member in members:
        try:
            await member.send(message)
            sent += 1
        except (discord.Forbidden, discord.HTTPException):
            failed += 1
    return sent, failed


class SquadCategorySelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="Pick category for squad voice channels...",
            channel_types=[discord.ChannelType.category],
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        data = get_guild_squad(interaction.guild_id)
        data["category_id"] = category.id
        set_guild_squad(interaction.guild_id, data)

        await interaction.response.edit_message(
            content=(
                f"**Category saved:** {category.name}\n\n"
                + format_squad_config_summary(interaction.guild)
                + "\n\nPick **staff roles** below (optional)."
            ),
            view=self.view,
        )


class SquadStaffRolesSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, page: int, total_pages: int):
        options = build_role_options(get_sorted_roles(guild), page, show_rank=True)
        placeholder = "Pick role(s) that can see all squad VCs..."
        if total_pages > 1:
            placeholder = f"Staff roles — page {page + 1}/{total_pages}..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max(1, min(MAX_SELECT_CHANNELS, len(options))),
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        role_ids = [int(value) for value in self.values]
        data = get_guild_squad(interaction.guild_id)
        data["staff_role_ids"] = role_ids
        set_guild_squad(interaction.guild_id, data)

        names = []
        for role_id in role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                names.append(role.name)

        await interaction.response.edit_message(
            content=(
                "**Squad config saved.**\n"
                f"Staff roles: {', '.join(f'**{name}**' for name in names)}\n\n"
                + format_squad_config_summary(interaction.guild)
            ),
            view=None,
        )


class SquadConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.page = page
        self.roles = get_sorted_roles(guild)
        self.total_pages = max(
            1,
            (len(self.roles) + MAX_SELECT_CHANNELS - 1) // MAX_SELECT_CHANNELS,
        )
        self._build_items()

    def _build_items(self) -> None:
        self.clear_items()
        self.add_item(SquadCategorySelect())

        if not self.roles:
            return

        self.add_item(SquadStaffRolesSelect(self.guild, self.page, self.total_pages))

        if self.total_pages > 1 and self.page > 0:
            prev = discord.ui.Button(label="◀ Previous", style=discord.ButtonStyle.secondary, row=2)
            prev.callback = self._prev_page
            self.add_item(prev)

        if self.total_pages > 1 and self.page < self.total_pages - 1:
            next_btn = discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, row=2)
            next_btn.callback = self._next_page
            self.add_item(next_btn)

    async def _prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_items()
        await interaction.response.edit_message(view=self)

    async def _next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_items()
        await interaction.response.edit_message(view=self)


class SquadDeleteSelect(discord.ui.Select):
    def __init__(self, squads: list[dict]):
        options = [
            discord.SelectOption(
                label=entry["name"][:100],
                value=str(entry["channel_id"]),
            )
            for entry in squads[:MAX_SELECT_CHANNELS]
        ]
        super().__init__(
            placeholder="Pick a squad to delete...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        channel_id = int(self.values[0])
        channel = interaction.guild.get_channel(channel_id)
        squad_name = channel.name if channel else str(channel_id)

        if channel is None:
            remove_squad_record(interaction.guild_id, channel_id)
            await interaction.response.edit_message(
                content="That squad channel was already gone. Removed it from the list.",
                view=None,
            )
            return

        try:
            await channel.delete(reason=f"Squad deleted by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to delete that channel.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Failed to delete squad: {exc}",
                ephemeral=True,
            )
            return

        remove_squad_record(interaction.guild_id, channel_id)
        await interaction.response.edit_message(
            content=f"Deleted squad **{squad_name}**.",
            view=None,
        )


class SquadDeleteView(discord.ui.View):
    def __init__(self, squads: list[dict]):
        super().__init__(timeout=300)
        self.add_item(SquadDeleteSelect(squads))


class SquadMemberSelect(discord.ui.UserSelect):
    def __init__(self, squad_name: str, max_members: int):
        multi = max_members > 1
        if multi:
            placeholder = (
                f"Multi-select up to {max_members} members for the squad..."
            )
        else:
            placeholder = "Pick 1 member for the squad..."

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=max_members,
            row=0,
        )
        self.squad_name = squad_name
        self.max_members = max_members
        self.multi = multi

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send(
                "This command only works in a server.",
                ephemeral=True,
            )
            return

        members: list[discord.Member] = []
        for user in self.values:
            member = await resolve_guild_member(guild, user.id)
            if member is None or member.bot:
                continue
            if member not in members:
                members.append(member)

        if not members:
            await interaction.followup.send(
                "No valid members were selected.",
                ephemeral=True,
            )
            return

        if len(members) > self.max_members:
            await interaction.followup.send(
                f"You can only pick up to **{self.max_members}** member(s).",
                ephemeral=True,
            )
            return

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            await interaction.followup.send(
                "I need **Manage Channels** to create squad voice channels.",
                ephemeral=True,
            )
            return

        creator = await resolve_guild_member(guild, interaction.user.id)
        if creator is None:
            await interaction.followup.send(
                "Could not resolve your server membership.",
                ephemeral=True,
            )
            return

        try:
            channel = await create_squad_voice_channel(
                guild,
                self.squad_name,
                members,
                creator,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create voice channels here.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"Failed to create squad VC: {exc}",
                ephemeral=True,
            )
            return

        add_squad_record(interaction.guild_id, channel.id, self.squad_name)
        sent, dm_failed = await notify_squad_members(members, channel)
        dm_note = ""
        if dm_failed:
            dm_note = f"\nCould not DM **{dm_failed}** member(s) (DMs may be closed)."

        await interaction.followup.send(
            f"Squad **{self.squad_name}** created: {channel.mention}\n"
            f"Members: {', '.join(m.mention for m in members)}\n"
            f"DMs sent: **{sent}**{dm_note}",
            ephemeral=True,
        )


class SquadCreateView(discord.ui.View):
    def __init__(self, squad_name: str, max_members: int):
        super().__init__(timeout=300)
        self.squad_name = squad_name
        self.max_members = max_members
        self.add_item(SquadMemberSelect(squad_name, max_members))


@bot.tree.command(
    name="squadconfig",
    description="Choose roles that can see all squad voice channels",
)
@admin_only()
async def squadconfig(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    roles = get_sorted_roles(interaction.guild)
    if not roles:
        await interaction.followup.send("This server has no roles.", ephemeral=True)
        return

    current = format_squad_config_summary(interaction.guild)
    extra = ""
    if len(roles) > MAX_SELECT_CHANNELS:
        extra = (
            f"\n\nShowing **{len(roles)}** roles ({MAX_SELECT_CHANNELS} per page). "
            "Use **Next** to see more."
        )

    view = SquadConfigView(interaction.guild)
    await interaction.followup.send(
        "**Squad config**\n"
        "1. Pick a **category** for new squad voice channels.\n"
        "2. Pick **staff roles** that can see every squad VC.\n\n"
        + current
        + extra,
        view=view,
        ephemeral=True,
    )


@bot.tree.command(
    name="squadcreate",
    description="Create a private squad voice channel for selected members",
)
@app_commands.describe(
    size="How many people in the squad (including picks, max 25)",
    name="Squad name (used for the voice channel)",
)
async def squadcreate(
    interaction: discord.Interaction,
    size: app_commands.Range[int, 1, MAX_SQUAD_MEMBERS],
    name: str,
):
    if not await defer_ephemeral(interaction):
        return

    if interaction.guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_squads(interaction):
        await interaction.followup.send(
            "You need **Manage Channels** to create squads.",
            ephemeral=True,
        )
        return

    squad_name = name.strip()
    if not squad_name:
        await interaction.followup.send("Enter a squad name.", ephemeral=True)
        return

    view = SquadCreateView(squad_name, size)
    if size > 1:
        pick_text = (
            f"**Squad: {squad_name}** — use the picker below to **multi-select** "
            f"up to **{size}** members."
        )
    else:
        pick_text = f"**Squad: {squad_name}** — pick **1** member below."

    await interaction.followup.send(
        pick_text,
        view=view,
        ephemeral=True,
    )


@bot.tree.command(name="squaddelete", description="Delete a squad voice channel")
async def squaddelete(interaction: discord.Interaction):
    if not await defer_ephemeral(interaction):
        return

    if interaction.guild is None:
        await interaction.followup.send(
            "This command only works in a server.",
            ephemeral=True,
        )
        return

    if not user_can_manage_squads(interaction):
        await interaction.followup.send(
            "You need **Manage Channels** to delete squads.",
            ephemeral=True,
        )
        return

    squads = get_squads_for_delete(interaction.guild)
    if not squads:
        await interaction.followup.send(
            "There are no squads to delete. Use `/squadcreate` first, "
            "or set a category in `/squadconfig`.",
            ephemeral=True,
        )
        return

    view = SquadDeleteView(squads)
    await interaction.followup.send(
        "Pick the squad voice channel to delete:",
        view=view,
        ephemeral=True,
    )


# ===========================================================================
# ORBAT — interactive configuration UI
#
# For any AI reading this: the ORBAT command surface is
#   /orbatview [unit]   — full ORBAT, or a single unit's roster (autocomplete)
#   /orbatcard [member] — one member's service record (defaults to caller)
#   /orbatconfig        — admin hub: Units / Ranks / Positions / Settings
#   /orbatmember <user> — admin per-member editor (unit, rank, position, etc.)
#   /orbatsync          — admin: re-pull every member from Discord
#   /orbatclear         — admin: delete all units (members kept, unassigned)
# All persistence lives in orbat_db.py (SQLite at orbat.db).
# ===========================================================================
ORBAT_NONE_VALUE = "__none__"


def _guild_or_none(interaction: discord.Interaction) -> discord.Guild | None:
    return interaction.guild


def _truncate_options(items: list[dict], limit: int = 24) -> list[dict]:
    return items[:limit]


def orbat_hub_content(guild: discord.Guild) -> str:
    units = get_units(guild.id)
    ranks = get_ranks(guild.id)
    positions = get_positions(guild.id)
    members = get_members(guild.id)
    settings = get_settings(guild.id)
    return (
        "**ORBAT configuration**\n"
        f"Members tracked: **{len(members)}**  ·  Units: **{len(units)}**  ·  "
        f"Ranks: **{len(ranks)}**  ·  Positions: **{len(positions)}**\n"
        f"Rank source: **{settings.get('rank_source', 'roles')}**  ·  "
        f"Auto-sync: **{'on' if settings.get('auto_sync', 1) else 'off'}**\n\n"
        "Use the buttons below to manage each part.\n\n"
        "**Unit tree**\n" + format_units_tree(units)
    )


class OrbatBackButton(discord.ui.Button):
    def __init__(self, guild: discord.Guild, row: int = 4):
        super().__init__(label="Back", style=discord.ButtonStyle.secondary, row=row)
        self.guild = guild

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=orbat_hub_content(self.guild),
            embed=None,
            view=OrbatHubView(self.guild),
        )


class OrbatHubView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild

    @discord.ui.button(label="Units", style=discord.ButtonStyle.primary, row=0)
    async def units_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=units_manage_content(self.guild),
            embed=None,
            view=OrbatUnitsView(self.guild),
        )

    @discord.ui.button(label="Ranks", style=discord.ButtonStyle.primary, row=0)
    async def ranks_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=ranks_manage_content(self.guild),
            embed=None,
            view=OrbatRanksView(self.guild),
        )

    @discord.ui.button(label="Positions", style=discord.ButtonStyle.primary, row=0)
    async def positions_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=positions_manage_content(self.guild),
            embed=None,
            view=OrbatPositionsView(self.guild),
        )

    @discord.ui.button(label="Settings", style=discord.ButtonStyle.secondary, row=1)
    async def settings_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=settings_content(self.guild),
            embed=None,
            view=OrbatSettingsView(self.guild),
        )

    @discord.ui.button(label="Sync now", style=discord.ButtonStyle.success, row=1)
    async def sync_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        count = await force_sync_guild_orbat(self.guild)
        await interaction.followup.send(
            f"Synced **{count}** member(s) from Discord.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Units management
# ---------------------------------------------------------------------------
def units_manage_content(guild: discord.Guild) -> str:
    return (
        "**Units**\n"
        "1. Pick a unit to manage (top select) and/or a destination (second select).\n"
        "2. Use the buttons: Add creates a sub-unit under the destination "
        "(or top level if none picked). Move re-parents the managed unit.\n\n"
        "**Current units**\n" + format_units_tree(get_units(guild.id))
    )


def _unit_options(guild: discord.Guild, include_top: bool) -> list[discord.SelectOption]:
    options: list[discord.SelectOption] = []
    if include_top:
        options.append(
            discord.SelectOption(label="Top level (no parent)", value=ORBAT_NONE_VALUE)
        )
    for unit in _truncate_options(get_units(guild.id)):
        options.append(
            discord.SelectOption(label=unit["name"][:100], value=str(unit["id"]))
        )
    if not options:
        options.append(
            discord.SelectOption(label="(no units yet)", value=ORBAT_NONE_VALUE)
        )
    return options


class UnitTargetSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = _unit_options(guild, include_top=False)
        has_units = bool(get_units(guild.id))
        super().__init__(
            placeholder="Unit to manage (rename / move / delete / leader)...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not has_units,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.target_id = (
            None if self.values[0] == ORBAT_NONE_VALUE else int(self.values[0])
        )
        await interaction.response.defer()


class UnitDestSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        super().__init__(
            placeholder="Destination / parent (defaults to top level)...",
            min_values=1,
            max_values=1,
            options=_unit_options(guild, include_top=True),
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.dest_id = (
            None if self.values[0] == ORBAT_NONE_VALUE else int(self.values[0])
        )
        await interaction.response.defer()


class UnitLeaderSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Pick a member (for Set leader)...",
            min_values=1,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.leader_id = self.values[0].id
        await interaction.response.defer()


class UnitNameModal(discord.ui.Modal):
    name_input = discord.ui.TextInput(
        label="Unit name",
        placeholder='e.g. "1st Platoon" or "dingus team"',
        max_length=100,
        required=True,
    )

    def __init__(self, guild: discord.Guild, *, parent_id: int | None, rename_id: int | None):
        title = "Rename unit" if rename_id is not None else "New unit"
        super().__init__(title=title)
        self.guild = guild
        self.parent_id = parent_id
        self.rename_id = rename_id

    async def on_submit(self, interaction: discord.Interaction):
        name = self.name_input.value.strip()
        try:
            if self.rename_id is not None:
                await asyncio.to_thread(rename_unit, self.guild.id, self.rename_id, name)
                msg = f"Renamed unit to **{name}**."
            else:
                unit_id = await asyncio.to_thread(
                    create_unit, self.guild.id, name, self.parent_id
                )
                where = ""
                if self.parent_id is not None:
                    parent = get_unit(self.guild.id, self.parent_id)
                    if parent:
                        where = f" under **{parent['name']}**"
                msg = f"Created **{name}** `#{unit_id}`{where}."
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            msg + "\nReopen the Units menu to refresh the lists.", ephemeral=True
        )


class UnitDescriptionModal(discord.ui.Modal, title="Unit description"):
    desc_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )

    def __init__(self, guild: discord.Guild, unit_id: int):
        super().__init__()
        self.guild = guild
        self.unit_id = unit_id

    async def on_submit(self, interaction: discord.Interaction):
        await asyncio.to_thread(
            set_unit_description, self.guild.id, self.unit_id, self.desc_input.value
        )
        await interaction.response.send_message("Description updated.", ephemeral=True)


class OrbatUnitsView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.target_id: int | None = None
        self.dest_id: int | None = None
        self.leader_id: int | None = None
        self.add_item(UnitTargetSelect(guild))
        self.add_item(UnitDestSelect(guild))
        self.add_item(UnitLeaderSelect())
        self.add_item(OrbatBackButton(guild))

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=units_manage_content(self.guild),
            view=OrbatUnitsView(self.guild),
        )

    @discord.ui.button(label="Add", style=discord.ButtonStyle.success, row=3)
    async def add_unit(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(
            UnitNameModal(self.guild, parent_id=self.dest_id, rename_id=None)
        )

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, row=3)
    async def rename_unit_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a unit to manage first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            UnitNameModal(self.guild, parent_id=None, rename_id=self.target_id)
        )

    @discord.ui.button(label="Move", style=discord.ButtonStyle.secondary, row=3)
    async def move_unit_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a unit to manage first.", ephemeral=True
            )
            return
        try:
            await asyncio.to_thread(
                move_unit, self.guild.id, self.target_id, self.dest_id
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self._refresh(interaction)

    @discord.ui.button(label="Set description", style=discord.ButtonStyle.secondary, row=3)
    async def desc_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a unit to manage first.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            UnitDescriptionModal(self.guild, self.target_id)
        )

    @discord.ui.button(label="Set leader", style=discord.ButtonStyle.secondary, row=4)
    async def leader_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None or self.leader_id is None:
            await interaction.response.send_message(
                "Pick both a unit (top select) and a member (member select).",
                ephemeral=True,
            )
            return
        await asyncio.to_thread(
            set_unit_leader, self.guild.id, self.target_id, self.leader_id
        )
        await self._refresh(interaction)

    @discord.ui.button(label="Clear leader", style=discord.ButtonStyle.secondary, row=4)
    async def clear_leader_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a unit to manage first.", ephemeral=True
            )
            return
        await asyncio.to_thread(set_unit_leader, self.guild.id, self.target_id, None)
        await self._refresh(interaction)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, row=4)
    async def delete_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a unit to manage first.", ephemeral=True
            )
            return
        unit = get_unit(self.guild.id, self.target_id)
        if unit is None:
            await interaction.response.send_message("Unit not found.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=(
                f"Delete **{unit['name']}**? Its sub-units and members move up to "
                "its parent. This cannot be undone."
            ),
            view=UnitDeleteConfirmView(self.guild, self.target_id),
        )


class UnitDeleteConfirmView(discord.ui.View):
    def __init__(self, guild: discord.Guild, unit_id: int):
        super().__init__(timeout=120)
        self.guild = guild
        self.unit_id = unit_id

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            await asyncio.to_thread(delete_unit, self.guild.id, self.unit_id)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.edit_message(
            content=units_manage_content(self.guild),
            view=OrbatUnitsView(self.guild),
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.edit_message(
            content=units_manage_content(self.guild),
            view=OrbatUnitsView(self.guild),
        )


# ---------------------------------------------------------------------------
# Ranks management
# ---------------------------------------------------------------------------
def ranks_manage_content(guild: discord.Guild) -> str:
    ranks = get_ranks(guild.id)
    if ranks:
        lines = []
        for rank in ranks:
            abbr = f" `{rank['abbreviation']}`" if rank["abbreviation"] else ""
            role = f" → <@&{rank['role_id']}>" if rank["role_id"] else ""
            lines.append(
                f"\u2022 **{rank['name']}**{abbr} (priority {rank['sort_order']}){role}"
            )
        body = "\n".join(lines)
    else:
        body = "_No ranks yet. Higher priority = more senior._"
    return (
        "**Ranks**\n"
        "Add ranks with a name, optional abbreviation, and priority (higher = "
        "more senior). Map a rank to a Discord role so it is detected "
        "automatically when `rank source` is set to **roles**.\n\n" + body
    )


def _rank_options(guild: discord.Guild) -> tuple[list[discord.SelectOption], bool]:
    ranks = get_ranks(guild.id)
    options = [
        discord.SelectOption(label=rank["name"][:100], value=str(rank["id"]))
        for rank in _truncate_options(ranks)
    ]
    if not options:
        options.append(discord.SelectOption(label="(no ranks yet)", value=ORBAT_NONE_VALUE))
    return options, bool(ranks)


class RankTargetSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options, enabled = _rank_options(guild)
        super().__init__(
            placeholder="Pick a rank (for remove / map role)...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not enabled,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.target_id = (
            None if self.values[0] == ORBAT_NONE_VALUE else int(self.values[0])
        )
        await interaction.response.defer()


class RankRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Pick a Discord role (for Map role)...",
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.role_id = self.values[0].id
        await interaction.response.defer()


class RankAddModal(discord.ui.Modal, title="Add rank"):
    name_input = discord.ui.TextInput(label="Rank name", max_length=80, required=True)
    abbr_input = discord.ui.TextInput(
        label="Abbreviation (optional)", max_length=16, required=False
    )
    priority_input = discord.ui.TextInput(
        label="Priority number (higher = more senior)",
        placeholder="e.g. 10",
        max_length=6,
        required=False,
    )

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        priority: int | None = None
        raw = self.priority_input.value.strip()
        if raw:
            try:
                priority = int(raw)
            except ValueError:
                await interaction.response.send_message(
                    "Priority must be a whole number.", ephemeral=True
                )
                return
        try:
            await asyncio.to_thread(
                add_rank,
                self.guild.id,
                self.name_input.value,
                self.abbr_input.value,
                priority,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Added rank **{self.name_input.value.strip()}**. "
            "Reopen the Ranks menu to refresh.",
            ephemeral=True,
        )


class OrbatRanksView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.target_id: int | None = None
        self.role_id: int | None = None
        self.add_item(RankTargetSelect(guild))
        self.add_item(RankRoleSelect())
        self.add_item(OrbatBackButton(guild))

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=ranks_manage_content(self.guild),
            view=OrbatRanksView(self.guild),
        )

    @discord.ui.button(label="Add rank", style=discord.ButtonStyle.success, row=2)
    async def add_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(RankAddModal(self.guild))

    @discord.ui.button(label="Remove rank", style=discord.ButtonStyle.danger, row=2)
    async def remove_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a rank first.", ephemeral=True
            )
            return
        await asyncio.to_thread(remove_rank, self.guild.id, self.target_id)
        await self._refresh(interaction)

    @discord.ui.button(label="Map role", style=discord.ButtonStyle.secondary, row=2)
    async def map_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None or self.role_id is None:
            await interaction.response.send_message(
                "Pick both a rank and a Discord role.", ephemeral=True
            )
            return
        await asyncio.to_thread(
            set_rank_role, self.guild.id, self.target_id, self.role_id
        )
        await self._refresh(interaction)

    @discord.ui.button(label="Clear role", style=discord.ButtonStyle.secondary, row=2)
    async def clear_role_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a rank first.", ephemeral=True
            )
            return
        await asyncio.to_thread(set_rank_role, self.guild.id, self.target_id, None)
        await self._refresh(interaction)


# ---------------------------------------------------------------------------
# Positions management
# ---------------------------------------------------------------------------
def positions_manage_content(guild: discord.Guild) -> str:
    positions = get_positions(guild.id)
    if positions:
        body = "\n".join(f"\u2022 **{pos['name']}**" for pos in positions)
    else:
        body = "_No positions yet (e.g. Squad Leader, Rifleman, Medic)._"
    return "**Positions / billets**\n" + body


class PositionTargetSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        positions = get_positions(guild.id)
        options = [
            discord.SelectOption(label=pos["name"][:100], value=str(pos["id"]))
            for pos in _truncate_options(positions)
        ] or [discord.SelectOption(label="(no positions yet)", value=ORBAT_NONE_VALUE)]
        super().__init__(
            placeholder="Pick a position (to remove)...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
            disabled=not positions,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.target_id = (
            None if self.values[0] == ORBAT_NONE_VALUE else int(self.values[0])
        )
        await interaction.response.defer()


class PositionAddModal(discord.ui.Modal, title="Add position"):
    name_input = discord.ui.TextInput(
        label="Position name",
        placeholder="e.g. Squad Leader",
        max_length=80,
        required=True,
    )

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await asyncio.to_thread(add_position, self.guild.id, self.name_input.value)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Added position **{self.name_input.value.strip()}**. "
            "Reopen the Positions menu to refresh.",
            ephemeral=True,
        )


class OrbatPositionsView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.target_id: int | None = None
        self.add_item(PositionTargetSelect(guild))
        self.add_item(OrbatBackButton(guild))

    @discord.ui.button(label="Add position", style=discord.ButtonStyle.success, row=1)
    async def add_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(PositionAddModal(self.guild))

    @discord.ui.button(label="Remove position", style=discord.ButtonStyle.danger, row=1)
    async def remove_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if self.target_id is None:
            await interaction.response.send_message(
                "Pick a position first.", ephemeral=True
            )
            return
        await asyncio.to_thread(remove_position, self.guild.id, self.target_id)
        await interaction.response.edit_message(
            content=positions_manage_content(self.guild),
            view=OrbatPositionsView(self.guild),
        )


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def settings_content(guild: discord.Guild) -> str:
    settings = get_settings(guild.id)
    color = settings.get("embed_color") or 0x2F4F4F
    return (
        "**ORBAT settings**\n"
        f"\u2022 Title: **{settings.get('title') or f'ORBAT — {guild.name}'}**\n"
        f"\u2022 Embed color: **#{color:06X}**\n"
        f"\u2022 Rank source: **{settings.get('rank_source', 'roles')}** "
        "(roles = auto from Discord roles, manual = admins set ranks)\n"
        f"\u2022 Auto-sync on events: **{'on' if settings.get('auto_sync', 1) else 'off'}**"
    )


class SettingsTitleModal(discord.ui.Modal, title="ORBAT title"):
    title_input = discord.ui.TextInput(
        label="Embed title (blank = default)",
        max_length=200,
        required=False,
    )

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        await asyncio.to_thread(
            update_settings, self.guild.id, title=self.title_input.value.strip()
        )
        await interaction.response.edit_message(
            content=settings_content(self.guild),
            view=OrbatSettingsView(self.guild),
        )


class SettingsColorModal(discord.ui.Modal, title="ORBAT embed color"):
    color_input = discord.ui.TextInput(
        label="Hex color (e.g. #2F4F4F)",
        max_length=7,
        required=True,
    )

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.color_input.value.strip().lstrip("#")
        try:
            value = int(raw, 16)
            if not 0 <= value <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(
                "Enter a valid hex color like `#2F4F4F`.", ephemeral=True
            )
            return
        await asyncio.to_thread(update_settings, self.guild.id, embed_color=value)
        await interaction.response.edit_message(
            content=settings_content(self.guild),
            view=OrbatSettingsView(self.guild),
        )


class OrbatSettingsView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        self.add_item(OrbatBackButton(guild))

    @discord.ui.button(label="Set title", style=discord.ButtonStyle.secondary, row=0)
    async def title_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SettingsTitleModal(self.guild))

    @discord.ui.button(label="Set color", style=discord.ButtonStyle.secondary, row=0)
    async def color_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(SettingsColorModal(self.guild))

    @discord.ui.button(label="Toggle rank source", style=discord.ButtonStyle.primary, row=1)
    async def rank_source_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        current = get_settings(self.guild.id).get("rank_source", RANK_SOURCE_ROLES)
        new = RANK_SOURCE_MANUAL if current == RANK_SOURCE_ROLES else RANK_SOURCE_ROLES
        await asyncio.to_thread(update_settings, self.guild.id, rank_source=new)
        await interaction.response.edit_message(
            content=settings_content(self.guild),
            view=OrbatSettingsView(self.guild),
        )

    @discord.ui.button(label="Toggle auto-sync", style=discord.ButtonStyle.primary, row=1)
    async def auto_sync_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        current = get_settings(self.guild.id).get("auto_sync", 1)
        await asyncio.to_thread(
            update_settings, self.guild.id, auto_sync=0 if current else 1
        )
        await interaction.response.edit_message(
            content=settings_content(self.guild),
            view=OrbatSettingsView(self.guild),
        )


# ---------------------------------------------------------------------------
# Per-member editor
# ---------------------------------------------------------------------------
class MemberUnitSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [discord.SelectOption(label="Unassign", value=ORBAT_NONE_VALUE)]
        for unit in _truncate_options(get_units(guild.id)):
            options.append(
                discord.SelectOption(label=unit["name"][:100], value=str(unit["id"]))
            )
        super().__init__(
            placeholder="Set unit...", min_values=1, max_values=1, options=options, row=0
        )

    async def callback(self, interaction: discord.Interaction):
        unit_id = None if self.values[0] == ORBAT_NONE_VALUE else int(self.values[0])
        await asyncio.to_thread(
            set_member_unit, self.view.guild.id, self.view.discord_id, unit_id
        )
        await self.view.refresh(interaction)


class MemberRankSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [
            discord.SelectOption(
                label="Clear / auto", value=ORBAT_NONE_VALUE,
                description="Unlock rank; let role sync set it",
            )
        ]
        for rank in _truncate_options(get_ranks(guild.id)):
            options.append(
                discord.SelectOption(label=rank["name"][:100], value=rank["name"][:100])
            )
        super().__init__(
            placeholder="Set rank...", min_values=1, max_values=1, options=options, row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == ORBAT_NONE_VALUE:
            await asyncio.to_thread(
                set_member_rank, self.view.guild.id, self.view.discord_id, "", lock=False
            )
        else:
            await asyncio.to_thread(
                set_member_rank,
                self.view.guild.id,
                self.view.discord_id,
                self.values[0],
                lock=True,
            )
        await self.view.refresh(interaction)


class MemberPositionSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        options = [discord.SelectOption(label="Clear position", value=ORBAT_NONE_VALUE)]
        for pos in _truncate_options(get_positions(guild.id)):
            options.append(
                discord.SelectOption(label=pos["name"][:100], value=pos["name"][:100])
            )
        super().__init__(
            placeholder="Set position...", min_values=1, max_values=1,
            options=options, row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        value = "" if self.values[0] == ORBAT_NONE_VALUE else self.values[0]
        await asyncio.to_thread(
            set_member_position, self.view.guild.id, self.view.discord_id, value
        )
        await self.view.refresh(interaction)


class MemberNoteModal(discord.ui.Modal, title="Member note"):
    note_input = discord.ui.TextInput(
        label="Note", style=discord.TextStyle.paragraph,
        max_length=300, required=False,
    )

    def __init__(self, view: "MemberEditorView"):
        super().__init__()
        self.editor = view

    async def on_submit(self, interaction: discord.Interaction):
        await asyncio.to_thread(
            set_member_note,
            self.editor.guild.id,
            self.editor.discord_id,
            self.note_input.value,
        )
        await self.editor.refresh(interaction)


class MemberEditorView(discord.ui.View):
    def __init__(self, guild: discord.Guild, discord_id: int):
        super().__init__(timeout=600)
        self.guild = guild
        self.discord_id = discord_id
        self.add_item(MemberUnitSelect(guild))
        self.add_item(MemberRankSelect(guild))
        self.add_item(MemberPositionSelect(guild))

    async def refresh(self, interaction: discord.Interaction):
        embed = build_orbat_card(self.guild, self.discord_id)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Toggle active", style=discord.ButtonStyle.secondary, row=3)
    async def toggle_active(self, interaction: discord.Interaction, _: discord.ui.Button):
        member = get_member(self.guild.id, self.discord_id)
        if member is None:
            await interaction.response.send_message("Member not tracked.", ephemeral=True)
            return
        await asyncio.to_thread(
            set_member_active, self.guild.id, self.discord_id, not member["active"]
        )
        await self.refresh(interaction)

    @discord.ui.button(label="Set note", style=discord.ButtonStyle.secondary, row=3)
    async def note_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(MemberNoteModal(self))


# ---------------------------------------------------------------------------
# ORBAT slash commands
# ---------------------------------------------------------------------------
async def _orbat_unit_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    if interaction.guild is None:
        return []
    current_lower = current.lower()
    choices: list[app_commands.Choice[str]] = []
    for unit in get_units(interaction.guild.id):
        if current_lower in unit["name"].lower():
            choices.append(
                app_commands.Choice(name=unit["name"][:100], value=str(unit["id"]))
            )
        if len(choices) >= 25:
            break
    return choices


@bot.tree.command(
    name="orbatview",
    description="View the ORBAT: members by unit, ranks, and Discord roles",
)
@app_commands.describe(unit="Optional: view a single unit's roster")
@app_commands.autocomplete(unit=_orbat_unit_autocomplete)
async def orbatview(interaction: discord.Interaction, unit: str | None = None):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    if unit:
        try:
            unit_id = int(unit)
        except ValueError:
            await interaction.followup.send("Unknown unit.", ephemeral=True)
            return
        embed = build_orbat_unit_embed(interaction.guild, unit_id)
        if embed is None:
            await interaction.followup.send("Unit not found.", ephemeral=True)
            return
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    embeds = build_orbat_embeds(interaction.guild)
    await interaction.followup.send(embeds=embeds[:10], ephemeral=True)


@bot.tree.command(
    name="orbatcard",
    description="Show a member's ORBAT service record",
)
@app_commands.describe(member="Member to view (defaults to you)")
async def orbatcard(
    interaction: discord.Interaction,
    member: discord.Member | None = None,
):
    if interaction.guild is None:
        await interaction.response.send_message(
            "This command only works in a server.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)
    target = member or interaction.user
    embed = build_orbat_card(interaction.guild, target.id)
    if embed is None:
        await interaction.followup.send(
            f"{target.mention} is not tracked yet. Run `/orbatsync` or wait for "
            "the next sync.",
            ephemeral=True,
        )
        return
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(
    name="orbatconfig",
    description="Configure ORBAT: units, ranks, positions, and settings",
)
@admin_only()
async def orbatconfig(interaction: discord.Interaction):
    await interaction.response.send_message(
        content=orbat_hub_content(interaction.guild),
        view=OrbatHubView(interaction.guild),
        ephemeral=True,
    )


@bot.tree.command(
    name="orbatmember",
    description="Edit a member's ORBAT record (unit, rank, position, note)",
)
@app_commands.describe(member="The member to edit")
@admin_only()
async def orbatmember(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)

    if member.bot:
        await interaction.followup.send("Bots are not tracked.", ephemeral=True)
        return

    if get_member(interaction.guild.id, member.id) is None:
        await sync_orbat_member(member)

    embed = build_orbat_card(interaction.guild, member.id)
    await interaction.followup.send(
        embed=embed,
        view=MemberEditorView(interaction.guild, member.id),
        ephemeral=True,
    )


@bot.tree.command(
    name="orbatsync",
    description="Re-sync every member's ORBAT record from Discord",
)
@admin_only()
async def orbatsync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    count = await force_sync_guild_orbat(interaction.guild)
    await interaction.followup.send(
        f"Synced **{count}** member(s) from Discord.", ephemeral=True
    )


@bot.tree.command(
    name="orbatclear",
    description="Remove all ORBAT units; members stay tracked but unassigned",
)
@admin_only()
async def orbatclear(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    removed = await asyncio.to_thread(clear_units, interaction.guild_id)
    member_count = len(get_members(interaction.guild_id))
    await interaction.followup.send(
        f"Cleared **{removed}** unit(s). "
        f"**{member_count}** member(s) are still tracked (now unassigned).",
        ephemeral=True,
    )


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Garrison Bot — Commands",
        description=(
            "Slash commands for this server. Most setup commands reply only to you "
            "(ephemeral)."
        ),
        color=discord.Color.from_rgb(220, 20, 60),
    )
    for section in AI_COMMAND_MAP:
        lines: list[str] = []
        for cmd in section["commands"]:
            lines.append(
                f"**{cmd['usage']}**\n"
                f"{cmd['summary']}\n"
                f"*Access: {cmd['access']}*"
            )
        value = "\n\n".join(lines)
        if len(value) > 1024:
            value = value[:1021] + "..."
        embed.add_field(
            name=str(section["category"]),
            value=value,
            inline=False,
        )
    embed.set_footer(
        text="PD auto-clears if the bot restarts while PD was on. "
        "Bot needs Manage Channels/Roles above roles it edits."
    )
    return embed


@bot.tree.command(name="help", description="List all bot commands and what they do")
async def help_command(interaction: discord.Interaction):
    await interaction.response.send_message(
        embed=build_help_embed(),
        ephemeral=True,
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in .env")
    bot.run(TOKEN)
