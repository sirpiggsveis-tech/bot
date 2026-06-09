@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT Discord Bot (24/7 — bot only, no web panel)
echo  ==================================================
echo.
echo  Panel: use your Cloudflare Pages URL (talks to Render API).
echo  This window must stay open for the bot to stay online.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found. Install Python 3.11+ and try again.
  pause
  exit /b 1
)

python scriptt.py
pause
