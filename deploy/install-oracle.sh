#!/usr/bin/env bash
# One-shot install on Ubuntu 22.04/24.04 (Oracle Cloud Always Free ARM, or any VPS).
# Run ON THE SERVER as a user with sudo:
#   curl -fsSL https://raw.githubusercontent.com/sirpiggsveis-tech/bot/main/deploy/install-oracle.sh | bash

set -euo pipefail

REPO="${ORBAT_REPO:-https://github.com/sirpiggsveis-tech/bot.git}"
INSTALL_DIR="${ORBAT_DIR:-$HOME/bot}"

echo "==> ORBAT 24/7 server install"
echo "    Repo: $REPO"
echo "    Dir:  $INSTALL_DIR"

if ! command -v sudo >/dev/null 2>&1; then
  echo "sudo is required."
  exit 1
fi

echo "==> Installing Docker..."
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl git
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER" || true

if [ ! -d "$INSTALL_DIR/.git" ]; then
  echo "==> Cloning repository..."
  git clone "$REPO" "$INSTALL_DIR"
else
  echo "==> Updating repository..."
  git -C "$INSTALL_DIR" pull --ff-only
fi

cd "$INSTALL_DIR"

if [ ! -f .env ]; then
  echo ""
  echo "!!! Create $INSTALL_DIR/.env before starting (secrets)."
  echo "    On your PC run:  python scripts/generate_server_env.py"
  echo "    Copy server.env to the server:  scp server.env ubuntu@YOUR_VM_IP:$INSTALL_DIR/.env"
  echo ""
  exit 1
fi

echo "==> Building and starting (docker compose)..."
sudo docker compose up -d --build

echo ""
echo "==> Done. Bot + API should be starting."
echo "    Local health: curl -s http://127.0.0.1:8000/ping"
echo ""
echo "Next: set up Cloudflare Tunnel for HTTPS (see HOSTING_24_7.txt),"
echo "      then set VITE_API_BASE on Cloudflare Pages to your tunnel URL."
