"""Environment-driven configuration for the control-panel API."""

from __future__ import annotations

import os
from functools import lru_cache


def _is_local_url(url: str) -> bool:
    lowered = url.lower()
    return "localhost" in lowered or "127.0.0.1" in lowered


def _split_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for piece in raw.replace(";", ",").split(","):
        piece = piece.strip()
        if piece.isdigit():
            ids.add(int(piece))
    return ids


class Settings:
    """Loaded once from environment variables.

    Required for login to work:
      DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, OAUTH_REDIRECT_URI,
      SESSION_SECRET, GUILD_ID

    Role gating (Discord user must hold at least one listed role):
      PANEL_ADMIN_ROLE_IDS   full read/write
      PANEL_STAFF_ROLE_IDS   write to ORBAT, no destructive settings
      PANEL_VIEWER_ROLE_IDS  read-only
      PANEL_ALLOW_USER_IDS   bootstrap allowlist (always admin)
    """

    def __init__(self) -> None:
        self.client_id = os.getenv("DISCORD_CLIENT_ID", "")
        self.client_secret = os.getenv("DISCORD_CLIENT_SECRET", "")
        self.redirect_uri = os.getenv("OAUTH_REDIRECT_URI", "")
        self.session_secret = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")
        self.session_ttl = int(os.getenv("SESSION_TTL_SECONDS", str(60 * 60 * 24 * 7)))
        self.cookie_name = os.getenv("SESSION_COOKIE_NAME", "orbat_session")
        self.cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN") or None
        self.local_port = int(os.getenv("PORT", "8000"))

        local_dev = _is_local_url(self.redirect_uri) or _is_local_url(
            os.getenv("FRONTEND_ORIGIN", "")
        )
        # Cross-site (Cloudflare Pages -> Render) cookies need SameSite=None; Secure.
        # Local http://localhost needs lax + insecure cookies unless overridden.
        cookie_secure_default = "0" if local_dev else "1"
        cookie_samesite_default = "lax" if local_dev else "none"
        self.cookie_secure = os.getenv("SESSION_COOKIE_SECURE", cookie_secure_default) != "0"
        self.cookie_samesite = os.getenv("SESSION_COOKIE_SAMESITE", cookie_samesite_default).lower()

        self.guild_id = int(os.getenv("GUILD_ID", "0") or "0")
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
        # Where to send the browser after a successful login.
        self.post_login_redirect = os.getenv("POST_LOGIN_REDIRECT", self.frontend_origin)

        self.admin_role_ids = _split_ids(os.getenv("PANEL_ADMIN_ROLE_IDS", ""))
        self.staff_role_ids = _split_ids(os.getenv("PANEL_STAFF_ROLE_IDS", ""))
        self.viewer_role_ids = _split_ids(os.getenv("PANEL_VIEWER_ROLE_IDS", ""))
        self.allow_user_ids = _split_ids(os.getenv("PANEL_ALLOW_USER_IDS", ""))

    @property
    def oauth_configured(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.redirect_uri
            and self.guild_id
        )

    def role_for(self, user_id: int, role_ids: set[int]) -> str | None:
        """Return the access tier for a user, or None if not allowed."""
        if user_id in self.allow_user_ids:
            return "admin"
        if self.admin_role_ids & role_ids:
            return "admin"
        if self.staff_role_ids & role_ids:
            return "staff"
        if self.viewer_role_ids & role_ids:
            return "viewer"
        # If no role lists are configured at all, deny by default (secure).
        if not (self.admin_role_ids or self.staff_role_ids or self.viewer_role_ids):
            return None
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
