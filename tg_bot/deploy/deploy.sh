#!/usr/bin/env bash
set -e

SERVER="${1:-root@31.77.148.115}"
KEY="${2:-$HOME/.ssh/content_agent_prod}"
REMOTE_DIR="/opt/content_agent_bot"

echo "🚀 [1/3] Синхронизация файлов проекта на $SERVER:$REMOTE_DIR..."
rsync -avz -e "ssh -i $KEY -o StrictHostKeyChecking=no" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'venv' \
    --exclude '.DS_Store' \
    --exclude '*.log' \
    ./ "$SERVER:$REMOTE_DIR/"

echo "⚙️ [2/3] Запуск настройки на сервере..."
ssh -i "$KEY" -o StrictHostKeyChecking=no "$SERVER" "bash $REMOTE_DIR/tg_bot/deploy/setup_server.sh $REMOTE_DIR"

echo "✅ [3/3] Деплой успешно завершён!"
