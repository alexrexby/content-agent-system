from __future__ import annotations

import os
import re
import sqlite3
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from tg_bot.config import BASE_DIR

OUTREACH_DB_PATH = BASE_DIR / "data" / "outreach.db"

def get_connection() -> sqlite3.Connection:
    OUTREACH_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(OUTREACH_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_outreach_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outreach_targets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                channel_name TEXT,
                source TEXT,
                status TEXT DEFAULT 'new', -- new, queued, sent, replied
                pitch_text TEXT,
                sent_at DATETIME,
                reply_text TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()

def extract_telegram_contacts(text: str) -> List[str]:
    """Extracts @usernames and t.me/ links from bio or post captions."""
    matches = re.findall(r"(?:(?:https?://)?(?:www\.)?t\.me/|@)([a-zA-Z0-9_]{4,32})", text, re.IGNORECASE)
    cleaned = []
    ignore_set = {"instagram", "telegram", "channel", "group", "bot", "admin", "help", "support"}
    for m in matches:
        u = m.lower().strip()
        if u not in ignore_set and not u.endswith("_bot"):
            if u not in cleaned:
                cleaned.append(u)
    return cleaned

def generate_pitch(channel_name: str = "", topic: str = "бьюти-бизнес") -> str:
    """Generates polite, conversion-optimized PR inquiry text."""
    intro = f"Здравствуйте{f', {channel_name}' if channel_name else ''}!"
    return (
        f"{intro} Подскажите, пожалуйста, актуальные условия и прайс на размещение рекламы "
        f"(пост / серия сторис) для проекта по тематике {topic}? "
        f"Буду благодарен за информацию по форматам и свежую статистику охватов. Спасибо!"
    )

def add_lead(username: str, channel_name: str = "", source: str = "instagram") -> Tuple[bool, str]:
    """Queues a new target contact into the database."""
    init_outreach_db()
    clean_u = username.replace("@", "").strip().lower()
    if not clean_u:
        return False, "Некорректный username"

    pitch = generate_pitch(channel_name)

    with get_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO outreach_targets (username, channel_name, source, status, pitch_text) VALUES (?, ?, ?, 'new', ?)",
                (clean_u, channel_name, source, pitch)
            )
            conn.commit()
            return True, f"@{clean_u} добавлен в базу"
        except sqlite3.IntegrityError:
            return False, f"@{clean_u} уже есть в базе"

def get_outreach_summary() -> str:
    """Returns status report of outreach campaign."""
    init_outreach_db()
    with get_connection() as conn:
        total = conn.execute("SELECT count(*) as c FROM outreach_targets").fetchone()["c"]
        new_cnt = conn.execute("SELECT count(*) as c FROM outreach_targets WHERE status='new'").fetchone()["c"]
        sent_cnt = conn.execute("SELECT count(*) as c FROM outreach_targets WHERE status='sent'").fetchone()["c"]
        replied_cnt = conn.execute("SELECT count(*) as c FROM outreach_targets WHERE status='replied'").fetchone()["c"]
        
        recent = conn.execute("SELECT username, channel_name, status FROM outreach_targets ORDER BY id DESC LIMIT 5").fetchall()

    lines = [
        f"📊 <b>Статистика аутрича рекламы:</b>",
        f"• Всего контактов: <b>{total}</b>",
        f"• Ожидают отправки (new): <b>{new_cnt}</b>",
        f"• Отправлено запросов: <b>{sent_cnt}</b>",
        f"• Получено ответов: <b>{replied_cnt}</b>",
    ]
    if recent:
        lines.append("\n<b>Последние добавленные:</b>")
        for r in recent:
            lines.append(f"• @{r['username']} ({r['channel_name'] or 'канал'}) — <code>{r['status']}</code>")

    return "\n".join(lines)

async def run_outreach_dispatch(limit: int = 5) -> Tuple[int, str]:
    """
    Simulates / performs outreach messages to queued contacts with anti-spam delays.
    If TG_API_ID and TG_API_HASH are configured, runs Telethon client.
    Otherwise operates in safe queue mode.
    """
    init_outreach_db()
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")

    with get_connection() as conn:
        leads = conn.execute(
            "SELECT id, username, pitch_text FROM outreach_targets WHERE status='new' LIMIT ?",
            (limit,)
        ).fetchall()

    if not leads:
        return 0, "Нет новых контактов в очереди."

    if not api_id or not api_hash:
        # Safe mock / dry-run mode
        with get_connection() as conn:
            for l in leads:
                conn.execute("UPDATE outreach_targets SET status='queued' WHERE id=?", (l["id"],))
            conn.commit()
        return len(leads), f"Подготовлено {len(leads)} сообщений в очередь (для реальной отправки укажите TG_API_ID и TG_API_HASH)."

    # Telethon live dispatch
    from telethon import TelegramClient
    session_file = str(OUTREACH_DB_PATH.parent / "manager_session")
    client = TelegramClient(session_file, int(api_id), api_hash)
    
    sent_count = 0
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        return 0, "Юзербот Telethon не авторизован на сервере."

    try:
        for l in leads:
            target = f"@{l['username']}"
            await client.send_message(target, l["pitch_text"])
            sent_count += 1
            with get_connection() as conn:
                conn.execute(
                    "UPDATE outreach_targets SET status='sent', sent_at=CURRENT_TIMESTAMP WHERE id=?",
                    (l["id"],)
                )
                conn.commit()
            # Safety delay: 30 seconds between requests
            await asyncio.sleep(30.0)
    finally:
        await client.disconnect()

    return sent_count, f"Успешно отправлено {sent_count} запросов прайса в Telegram."
