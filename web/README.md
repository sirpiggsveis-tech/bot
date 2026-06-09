# ORBAT Control Panel

A web control panel for the Discord bot. A **Supabase PostgreSQL** database is the
single source of truth; the bot keeps it synced from Discord, and this panel
reads/writes it through an API.

```
Browser ──► Cloudflare Pages (React UI)  ──►  Render (FastAPI + discord.py bot)  ──►  Supabase PostgreSQL
                                                     ▲
                                                     └── Discord gateway/API
```

- **Frontend** (`web/frontend`): React + Vite + Tailwind, deployed to **Cloudflare Pages**.
- **Backend** (`web/api`): FastAPI, runs in the **same process as the bot** via `run.py`, deployed to **Render**.
- **Auth**: "Login with Discord" (OAuth2), gated by your server roles (admin / staff / viewer tiers).

---

## 1. Discord setup

In the [Discord Developer Portal](https://discord.com/developers/applications) →
your application:

1. **OAuth2 → General**: copy the **Client ID** and **Client Secret**.
2. **OAuth2 → Redirects**: add `https://<your-render-service>.onrender.com/api/auth/callback`.
3. Decide which **role IDs** may log in and at what tier (admin/staff/viewer).
   - In Discord, enable Developer Mode, right-click a role → Copy ID. (Roles are
     copied from the role list, or copy a member's role via Server Settings.)

The panel uses the **same Discord application** as the bot.

---

## 2. Database on Supabase

1. Create a project at [supabase.com](https://supabase.com).
2. **Project Settings → Database → Connection string → URI**: copy it. Prefer the
   pooled connection (port `6543`) for hosted deploys; the direct one (`5432`)
   also works. Append `?sslmode=require`.
3. That becomes `DATABASE_URL`. The schema is created automatically on startup
   (`init_orbat_db()`), so no manual SQL is needed.

## 3. Backend on Render

1. Push this repo to GitHub.
2. On Render → **New → Blueprint**, point at the repo (it reads `render.yaml`), or
   create a **Web Service** manually:
   - Build: `pip install -r requirements.txt`
   - Start: `python run.py`
   - Health check path: `/api/health`
3. Set environment variables (see `.env.example`):
   - `DATABASE_URL` (Supabase, from step above)
   - `DISCORD_TOKEN`, `GUILD_ID`
   - `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `OAUTH_REDIRECT_URI`
   - `SESSION_SECRET` (long random string)
   - `FRONTEND_ORIGIN=https://<your-panel>.pages.dev`
   - `PANEL_ADMIN_ROLE_IDS` (and optionally staff/viewer, or `PANEL_ALLOW_USER_IDS`)

The bot and API run together in one service.

---

## 4. Frontend on Cloudflare Pages

1. Cloudflare → **Workers & Pages → Create → Pages → Connect to Git**.
2. Settings:
   - **Root directory**: `web/frontend`
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
3. Environment variable:
   - `VITE_API_BASE=https://<your-render-service>.onrender.com`
4. Deploy. Your panel is at `https://<your-panel>.pages.dev`.

Make sure the Render env vars `FRONTEND_ORIGIN` / `OAUTH_REDIRECT_URI` match the
real Pages URL.

---

## 5. Local development

Backend (from repo root):

```bash
pip install -r requirements.txt
# put values in .env (see .env.example); you still need a DATABASE_URL
# (a Supabase project works for local dev too). For local OAuth set
#   OAUTH_REDIRECT_URI=http://localhost:8000/api/auth/callback
#   FRONTEND_ORIGIN=http://localhost:5173
#   SESSION_COOKIE_SECURE=0   (so cookies work over http)
python run.py
```

Frontend:

```bash
cd web/frontend
npm install
echo "VITE_API_BASE=http://localhost:8000" > .env.local
npm run dev   # http://localhost:5173
```

---

## Access tiers

| Tier   | Can do                                                            |
|--------|------------------------------------------------------------------|
| admin  | Everything, incl. ORBAT settings and clear-units                 |
| staff  | Create/edit units, ranks, positions, members; trigger sync       |
| viewer | Read-only                                                        |

A user with no matching role is denied (bounced back to login with an error).

---

## API surface (v1)

`/api/auth/{login,callback,logout,me}` and `/api/orbat/*`
(overview, units, members, ranks, positions, settings, sync). See
`web/api/routers/` for the full list. Other bot features (auto-roles, PD mode,
squads, messaging) are scaffolded in the UI and will get endpoints next.
