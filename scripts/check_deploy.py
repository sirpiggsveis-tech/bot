"""Check that local .env is ready for Render + Cloudflare deploy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

REQUIRED = (
    "DISCORD_TOKEN",
    "GUILD_ID",
    "DATABASE_URL",
    "DISCORD_CLIENT_ID",
    "DISCORD_CLIENT_SECRET",
    "SESSION_SECRET",
    "OAUTH_REDIRECT_URI",
    "FRONTEND_ORIGIN",
    "PANEL_ADMIN_ROLE_IDS",
)

RENDER_URL = os.getenv("RENDER_SERVICE_URL", "https://bot-wf8x.onrender.com").rstrip("/")
PAGES_URL = os.getenv("PAGES_URL", "").rstrip("/") or "(set after Cloudflare Pages deploy)"


def main() -> int:
    print("=== Deploy readiness check ===\n")
    missing = [k for k in REQUIRED if not os.getenv(k, "").strip()]
    if missing:
        print("MISSING in .env (fix these first):")
        for k in missing:
            print(f"  - {k}")
        print()
    else:
        print("All required .env keys are set.\n")

    print("Use these values on Render (Environment tab):")
    print(f"  OAUTH_REDIRECT_URI = {RENDER_URL}/api/auth/callback")
    if PAGES_URL.startswith("http"):
        print(f"  FRONTEND_ORIGIN    = {PAGES_URL}")
        print(f"  POST_LOGIN_REDIRECT = {PAGES_URL}")
    else:
        print("  FRONTEND_ORIGIN    = https://YOUR-PANEL.pages.dev")
        print("  POST_LOGIN_REDIRECT = same as FRONTEND_ORIGIN")
    print("  SESSION_COOKIE_SAMESITE = none")
    print("  SESSION_COOKIE_SECURE   = 1")
    print()
    print("Copy the rest from your local .env file:")
    for k in REQUIRED:
        status = "set" if os.getenv(k, "").strip() else "MISSING"
        print(f"  {k} = ({status})")
    print()
    print("Discord Developer Portal -> OAuth2 -> Redirects, add:")
    print(f"  {RENDER_URL}/api/auth/callback")
    print()
    print("Cloudflare Pages build env:")
    print(f"  VITE_API_BASE = {RENDER_URL}")
    print()
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
