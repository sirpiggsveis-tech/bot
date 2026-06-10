@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT — free bot host (NO credit card)
echo  =====================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

echo Building bot-deploy.zip...
python scripts\build_bot_zip.py
echo.
echo Generating server.env (for copy-paste into host env panel)...
python scripts\generate_server_env.py
echo.
echo Opening HOSTING_NO_CARD.txt and host websites...
start "" "%~dp0HOSTING_NO_CARD.txt"
start "" "https://monkey-network.xyz/"
echo.
echo NEXT:
echo   1. Sign up on a free host (email only, no card)
echo   2. Upload bot-deploy.zip and unzip
echo   3. Paste env vars from server.env into their dashboard
echo   4. Start command: python scriptt.py
echo   5. Stop start-bot.bat on your PC
echo.
pause
