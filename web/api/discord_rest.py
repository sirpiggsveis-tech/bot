"""Fetch guild channels/roles via Discord REST (no discord.py). Used when cache is empty."""

from __future__ import annotations

from typing import Any

import httpx

_API = "https://discord.com/api/v10"


def _channel_type(ch: dict[str, Any]) -> str | None:
    kind = ch.get("type")
    if kind == 0:
        return "text"
    if kind == 2:
        return "voice"
    if kind == 4:
        return "category"
    return None


async def fetch_guild_directory(guild_id: int, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bot {token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        ch_resp = await client.get(
            f"{_API}/guilds/{guild_id}/channels",
            headers=headers,
        )
        ch_resp.raise_for_status()
        ro_resp = await client.get(
            f"{_API}/guilds/{guild_id}/roles",
            headers=headers,
        )
        ro_resp.raise_for_status()
        raw_channels = ch_resp.json()
        raw_roles = ro_resp.json()

    categories = {c["id"]: c["name"] for c in raw_channels if c.get("type") == 4}

    text_channels: list[dict[str, str | None]] = []
    voice_channels: list[dict[str, str | None]] = []
    category_list: list[dict[str, str | None]] = []

    for ch in sorted(raw_channels, key=lambda c: (c.get("position", 0), c.get("name", "").lower())):
        kind = _channel_type(ch)
        if kind is None:
            continue
        parent = ch.get("parent_id")
        cat_name = categories.get(parent) if parent else None
        entry = {
            "id": str(ch["id"]),
            "name": ch.get("name") or "unknown",
            "category": cat_name,
        }
        if kind == "text":
            text_channels.append(entry)
        elif kind == "voice":
            voice_channels.append(entry)
        elif kind == "category":
            category_list.append({"id": str(ch["id"]), "name": entry["name"], "category": None})

    roles = [
        {
            "id": str(r["id"]),
            "name": r.get("name") or "unknown",
            "color": int(r.get("color") or 0),
        }
        for r in sorted(raw_roles, key=lambda x: x.get("position", 0), reverse=True)
        if r.get("name") != "@everyone"
    ]

    return {
        "text_channels": text_channels,
        "voice_channels": voice_channels,
        "categories": category_list,
        "roles": roles,
        "members": [],
        "from_cache": False,
        "live": True,
        "needs_sync": False,
    }
