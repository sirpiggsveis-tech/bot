@echo off
setlocal
cd /d "%~dp0"

echo.
echo  Deploy helper - opens the sites you need to finish setup
echo  ========================================================
echo.

python scripts\check_deploy.py
echo.
echo Generating render-env-paste.txt from your .env (for copy-paste into Render)...
python scripts\copy_render_env.py
echo.
echo Full click-by-click guide: DEPLOY_STEPS.txt
echo.

set RENDER=https://dashboard.render.com/web/srv
set RENDER_HEALTH=https://bot-wf8x.onrender.com/api/health
set GITHUB=https://github.com/sirpiggsveis-tech/bot
set DISCORD=https://discord.com/developers/applications
set CLOUDFLARE=https://dash.cloudflare.com/?to=/:account/pages/new/provider/github
set SUPABASE=https://supabase.com/dashboard/project/_/settings/database

echo Opening setup pages in your browser...
echo   1. Render service health check
echo   2. Render dashboard
echo   3. Your GitHub repo
echo   4. Discord Developer Portal
echo   5. Cloudflare Pages (new project)
echo   6. Supabase database settings
echo.

start "" "%RENDER_HEALTH%"
timeout /t 1 /nobreak >nul
start "" "%RENDER%"
timeout /t 1 /nobreak >nul
start "" "%GITHUB%"
timeout /t 1 /nobreak >nul
start "" "%DISCORD%"
timeout /t 1 /nobreak >nul
start "" "%CLOUDFLARE%"
timeout /t 1 /nobreak >nul
start "" "%SUPABASE%"

echo.
echo YOUR 3 CLICKS (details in DEPLOY_STEPS.txt):
echo   1. Render: sign in, open orbat-bot, paste render-env-paste.txt, keep Free plan
echo   2. Cloudflare Pages: connect GitHub repo, build web/frontend
echo   3. Discord: add OAuth redirect https://bot-wf8x.onrender.com/api/auth/callback
echo.
notepad DEPLOY_STEPS.txt
pause
