@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT Bot + Control Panel
echo  =========================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found. Install Python 3.11+ and try again.
  pause
  exit /b 1
)

if not exist "web\frontend\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo NOTE: Node.js is not installed, so the web panel UI cannot be built yet.
    echo       The bot and API will still start. Install Node.js from https://nodejs.org
    echo       then run this script again to build the control panel.
    echo.
  ) else (
    echo Building the control panel UI ^(first time only^)...
    pushd web\frontend
    call npm install
    if errorlevel 1 goto :fail
    call npm run build
    if errorlevel 1 goto :fail
    popd
    echo.
  )
)

echo Starting bot + API...
python run.py
goto :end

:fail
echo.
echo Build failed. Fix the errors above and try again.
pause
exit /b 1

:end
pause
