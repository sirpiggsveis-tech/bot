"""Thin Discord OAuth2 client used for the panel login flow."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings

DISCORD_API = "https://discord.com/api"
OAUTH_SCOPES = "identify guilds.members.read"


def build_authorize_url(settings: Settings, state: str) -> str:
    from urllib.parse import urlencode

    query = urlencode(
        {
            "client_id": settings.client_id,
            "redirect_uri": settings.redirect_uri,
            "response_type": "code",
            "scope": OAUTH_SCOPES,
            "state": state,
            "prompt": "consent",
        }
    )
    return f"{DISCORD_API}/oauth2/authorize?{query}"


async def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    data = {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_guild_member(
    access_token: str,
    guild_id: int,
) -> dict[str, Any] | None:
    """Return the OAuth user's member object in the guild, or None if absent."""
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds/{guild_id}/member",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
