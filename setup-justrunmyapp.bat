@echo off
setlocal
cd /d "%~dp0"

echo Building bot-deploy.zip and env file...
python scripts\build_bot_zip.py
python scripts\generate_monkey_env.py

start "" "https://justrunmy.app/discord-bots"
start "" "%~dp0JUSTRUNMYAPP.txt"
start "" "%~dp0monkey-env-paste.txt"
explorer /select,"%CD%\bot-deploy.zip"

echo.
echo Drag bot-deploy.zip into JustRunMy.App when it asks for a zip.
pause
