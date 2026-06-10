@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT bot - Monkey Network deploy pack
echo  ======================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

echo [1/3] Building bot-deploy.zip...
python scripts\build_bot_zip.py
if errorlevel 1 pause & exit /b 1

echo.
echo [2/3] Writing monkey-env-paste.txt...
python scripts\generate_monkey_env.py
if errorlevel 1 pause & exit /b 1

echo.
echo [3/3] Opening Monkey Network + guide...
start "" "https://monkey-network.xyz/"
start "" "%~dp0MONKEY_NETWORK.txt"
start "" "%~dp0monkey-env-paste.txt"

echo.
echo READY:
echo   Upload bot-deploy.zip to Monkey (Files -^> upload -^> extract)
echo   Paste monkey-env-paste.txt into Variables
echo   Startup: python scriptt.py
echo   STOP start-bot.bat on your PC first!
echo.
echo bot-deploy.zip is in: %~dp0
pause
