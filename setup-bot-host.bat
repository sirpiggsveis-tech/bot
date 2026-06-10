@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT bot - free host deploy (Monkey / Daki / Wispbyte / etc.)
echo  ==============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

python scripts\build_bot_zip.py
if errorlevel 1 pause & exit /b 1

python scripts\generate_monkey_env.py
if errorlevel 1 pause & exit /b 1

echo.
echo Opening guides and host sites...
start "" "%~dp0BOT_HOST_DEPLOY.txt"
start "" "https://daki.cc/"
start "" "https://wispbyte.com/free-discord-bot-hosting"
start "" "https://justrunmy.app/discord-bots"

echo.
echo Monkey full? Try DAKI first, then Wispbyte, then JustRunMy.App
echo Upload: %~dp0bot-deploy.zip
echo Env:    %~dp0monkey-env-paste.txt
pause
