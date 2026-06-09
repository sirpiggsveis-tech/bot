"""Login / logout / session endpoints (username + password)."""

from __future__ import annotations

import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..config import Settings, get_settings
from ..schemas import LoginRequest
from ..security import CurrentUser, get_current_user, issue_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


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


@router.post("/login")
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
):
    if not settings.panel_admin_password:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Panel login is not configured. Set PANEL_ADMIN_USERNAME and "
            "PANEL_ADMIN_PASSWORD in the environment.",
        )

    user_ok = secrets.compare_digest(body.username, settings.panel_admin_username)
    pass_ok = secrets.compare_digest(body.password, settings.panel_admin_password)
    if not (user_ok and pass_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    payload = {
        "id": "1",
        "username": settings.panel_admin_username,
        "avatar": None,
        "tier": "admin",
        "iat": time.time(),
    }
    session_token = issue_session(settings, payload)

    import json

    body = json.dumps({"ok": True, "user": payload})
    resp = Response(content=body, media_type="application/json")
    _set_session_cookie(resp, settings, session_token)
    return resp


@router.post("/logout")
async def logout(settings: Settings = Depends(get_settings)):
    from fastapi.responses import JSONResponse

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
