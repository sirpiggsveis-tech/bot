@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT Panel + Bot (runs on YOUR PC - fast, no Render sleep)
echo  =============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

if not exist "web\frontend\dist\index.html" (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo Building UI skipped - Node.js not installed.
  ) else (
    echo Building panel UI...
    pushd web\frontend
    call npm install
    call npm run build
    popd
  )
)

echo Starting bot + panel...
echo.
echo  Open in browser:  http://localhost:8000/
echo  Login: admin + your password from .env
echo.
echo  Keep this window open. Close it = bot goes offline.
echo.

python run.py
pause
