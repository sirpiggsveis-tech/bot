"""Session signing and request authentication dependencies."""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import Settings, get_settings

TIER_RANK = {"viewer": 0, "staff": 1, "admin": 2}


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="orbat-panel-session")


def issue_session(settings: Settings, payload: dict[str, Any]) -> str:
    return _serializer(settings).dumps(payload)


def read_session(settings: Settings, token: str) -> dict[str, Any] | None:
    try:
        return _serializer(settings).loads(token, max_age=settings.session_ttl)
    except (BadSignature, SignatureExpired):
        return None


class CurrentUser:
    def __init__(self, data: dict[str, Any]):
        self.id: int = int(data["id"])
        self.username: str = data.get("username", "")
        self.avatar: str | None = data.get("avatar")
        self.tier: str = data.get("tier", "viewer")
        self.issued_at: float = data.get("iat", time.time())

    def can_write(self) -> bool:
        return TIER_RANK.get(self.tier, 0) >= TIER_RANK["staff"]

    def is_admin(self) -> bool:
        return self.tier == "admin"

    def public(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "username": self.username,
            "avatar": self.avatar,
            "tier": self.tier,
        }


def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    data = read_session(settings, token)
    if data is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    return CurrentUser(data)


def require_write(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.can_write():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Read-only access")
    return user


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not user.is_admin():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
