"""Login / logout / session endpoints (Discord OAuth2)."""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from .. import discord_oauth
from ..config import Settings, get_settings
from ..security import CurrentUser, get_current_user, issue_session

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Short-lived CSRF state values for the OAuth round trip.
_pending_states: dict[str, float] = {}
_STATE_TTL = 600


def _gc_states() -> None:
    now = time.time()
    for key, created in list(_pending_states.items()):
        if now - created > _STATE_TTL:
            _pending_states.pop(key, None)


def _set_session_cookie(resp: Response, settings: Settings, token: str) -> None:
    resp.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_ttl,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )


@router.get("/login")
async def login(settings: Settings = Depends(get_settings)):
    if not settings.oauth_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "OAuth is not configured. Set DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, "
            "OAUTH_REDIRECT_URI and GUILD_ID.",
        )
    _gc_states()
    state = secrets.token_urlsafe(24)
    _pending_states[state] = time.time()
    return RedirectResponse(discord_oauth.build_authorize_url(settings, state))


@router.get("/callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    settings: Settings = Depends(get_settings),
):
    if not code or not state or state not in _pending_states:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")
    _pending_states.pop(state, None)

    token_data = await discord_oauth.exchange_code(settings, code)
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Token exchange failed")

    user = await discord_oauth.fetch_user(access_token)
    user_id = int(user["id"])

    member = await discord_oauth.fetch_guild_member(access_token, settings.guild_id)
    role_ids = {int(r) for r in (member or {}).get("roles", [])}

    tier = settings.role_for(user_id, role_ids)
    if tier is None:
        # Not allowed: bounce back to the frontend with an error flag.
        return RedirectResponse(f"{settings.post_login_redirect}?error=forbidden")

    payload = {
        "id": str(user_id),
        "username": user.get("global_name") or user.get("username", ""),
        "avatar": user.get("avatar"),
        "tier": tier,
        "iat": time.time(),
    }
    session_token = issue_session(settings, payload)

    resp = RedirectResponse(settings.post_login_redirect)
    _set_session_cookie(resp, settings, session_token)
    return resp


@router.post("/logout")
async def logout(settings: Settings = Depends(get_settings)):
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(
        key=settings.cookie_name,
        domain=settings.cookie_domain,
        path="/",
    )
    return resp


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return user.public()
