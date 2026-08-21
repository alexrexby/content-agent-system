#!/usr/bin/env bash
set -e

APP_DIR="${1:-/opt/amalia_team_bot}"

echo "=== [1/4] Обновление пакетов и установка системных утилит ==="
apt-get update -y
apt-get install -y python3 python3-pip python3-venv ffmpeg git rsync

echo "=== [2/4] Настройка рабочей директории $APP_DIR ==="
mkdir -p "$APP_DIR"

echo "=== [3/4] Создание и обновление Python venv ==="
if [ ! -d "$APP_DIR/venv" ]; then
    python3 -m venv "$APP_DIR/venv"
fi

"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/tg_bot/requirements.txt"

echo "=== [4/4] Настройка Systemd службы ==="
cat << 'EOF' > /etc/systemd/system/amalia-team-bot.service
[Unit]
Description=Amalia Team AI Agent Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/amalia_team_bot
ExecStart=/opt/amalia_team_bot/venv/bin/python -m tg_bot.main
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable amalia-team-bot.service
systemctl restart amalia-team-bot.service

echo "=== Готово! Статус службы: ==="
systemctl status amalia-team-bot.service --no-pager
