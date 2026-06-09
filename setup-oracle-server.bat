@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ORBAT — 24/7 server setup (Oracle Cloud FREE)
echo  =============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python not found.
  pause
  exit /b 1
)

echo [1/3] Generating server.env from your .env...
python scripts\generate_server_env.py
if errorlevel 1 (
  echo Fix .env first, then run again.
  pause
  exit /b 1
)

echo.
echo [2/3] Opening guides...
start "" "https://www.oracle.com/cloud/free/"
start "" "%~dp0HOSTING_24_7.txt"

echo.
echo [3/3] Next steps (also in HOSTING_24_7.txt):
echo   1. Create Ubuntu ARM VM on Oracle Cloud
echo   2. Upload secrets:  scp server.env ubuntu@YOUR_VM_IP:~/server.env
echo   3. SSH in and run the install script from HOSTING_24_7.txt
echo   4. Cloudflare Tunnel -^> set VITE_API_BASE on Pages
echo.
pause
