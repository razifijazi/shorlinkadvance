#!/bin/bash
# Production deploy script for ShortLink
# Usage: bash deploy/deploy-prod.sh
# Idempotent: safe to run multiple times

set -e

APP_DIR="/home/ubuntu/shortlink-prod"
SERVICE_NAME="shortlink-prod"
DB_PATH="${APP_DIR}/shortlink-prod.db"

echo "==> Deploying ShortLink production"
echo "    App dir: $APP_DIR"
echo "    Service: $SERVICE_NAME"
echo

# 1. Stop running service (if any)
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    echo "==> Stopping $SERVICE_NAME"
    sudo systemctl stop "$SERVICE_NAME"
fi

# 2. Pull latest code (or clone if first time)
if [ -d "$APP_DIR/.git" ]; then
    echo "==> Pulling latest from origin"
    cd "$APP_DIR"
    git pull origin main
else
    echo "==> Cloning fresh (first deploy)"
    cd /home/ubuntu
    git clone git@github.com:razifijazi/shorlinkadvance.git shortlink-prod
    cd "$APP_DIR"
fi

# 3. Setup venv if missing
if [ ! -d "$APP_DIR/.venv" ]; then
    echo "==> Creating venv"
    python3 -m venv .venv
fi

# 4. Install/upgrade deps
echo "==> Installing deps"
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
deactivate

# 5. Ensure DB exists (init_db is idempotent)
echo "==> Initializing DB"
cd "$APP_DIR"
SHORTLINK_DB="$DB_PATH" .venv/bin/python -c "import db; db.init_db()"

# 6. Install systemd service if missing
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
if [ ! -f "$SERVICE_FILE" ]; then
    echo "==> Installing systemd service"
    sudo cp deploy/shortlink-prod.service "$SERVICE_FILE"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
fi

# 7. Start service
echo "==> Starting $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

# 8. Wait briefly and show status
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo
    echo "✅ Deploy complete — $SERVICE_NAME is running"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -20
else
    echo
    echo "❌ Service failed to start"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    sudo journalctl -u "$SERVICE_NAME" --no-pager -n 30
    exit 1
fi

echo
echo "==> Test: curl http://127.0.0.1:5071/"
curl -sS -o /dev/null -w "    HTTP %{http_code}\n" http://127.0.0.1:5071/ || echo "    (curl failed — check service status)"
