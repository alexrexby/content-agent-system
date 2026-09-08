from __future__ import annotations

import os
import json
import sqlite3
import difflib
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from tg_bot.config import BASE_DIR

DATA_DIR = BASE_DIR / "data"
LEARNING_DB_PATH = DATA_DIR / "learning.db"

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LEARNING_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_learning_db():
    """Initializes the learning database schema."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS learned_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL, -- 'stop_word', 'preferred_term', 'tone_rule', 'format_rule'
                rule_text TEXT NOT NULL,
                reason TEXT,
                source TEXT DEFAULT 'user', -- 'user', 'diff_auto'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS golden_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                style TEXT NOT NULL,
                topic TEXT,
                content TEXT NOT NULL,
                engagement_metric REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS draft_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                role TEXT DEFAULT 'copywriter',
                style TEXT DEFAULT 'drama',
                prompt TEXT,
                draft_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_draft_msg ON draft_history(chat_id, message_id);
            CREATE INDEX IF NOT EXISTS idx_rules_cat ON learned_rules(category, is_active);
        """)

init_learning_db()

def add_rule(category: str, rule_text: str, reason: str = "", source: str = "user") -> Tuple[bool, str]:
    """Adds a learned rule to the database."""
    clean_cat = category.strip().lower()
    clean_text = rule_text.strip()
    if not clean_text:
        return False, "Правило не может быть пустым."

    valid_cats = {"stop_word", "preferred_term", "tone_rule", "format_rule"}
    if clean_cat not in valid_cats:
        clean_cat = "tone_rule"

    try:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO learned_rules (category, rule_text, reason, source)
                VALUES (?, ?, ?, ?)
                """,
                (clean_cat, clean_text, reason.strip(), source)
            )
            rule_id = cur.lastrowid
        cat_titles = {
            "stop_word": "🚫 Стоп-слово/штамп",
            "preferred_term": "🎯 Предпочитаемый термин",
            "tone_rule": "⚖️ Правило тональности",
            "format_rule": "📐 Правило формата"
        }
        return True, f"Запомнил правило #{rule_id} ({cat_titles.get(clean_cat, clean_cat)}): «{clean_text}»"
    except Exception as e:
        return False, f"Ошибка сохранения правила: {e}"

def delete_rule(rule_id: int) -> Tuple[bool, str]:
    """Deactivates a learned rule."""
    try:
        with get_connection() as conn:
            cur = conn.execute(
                "UPDATE learned_rules SET is_active = 0 WHERE id = ?",
                (rule_id,)
            )
            if cur.rowcount > 0:
                return True, f"Правило #{rule_id} успешно отключено."
            return False, f"Правило #{rule_id} не найдено."
    except Exception as e:
        return False, f"Ошибка при удалении: {e}"

def get_active_rules(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches all active rules, optionally filtered by category."""
    with get_connection() as conn:
        if category:
            rows = conn.execute(
                "SELECT * FROM learned_rules WHERE is_active = 1 AND category = ? ORDER BY id ASC",
                (category,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM learned_rules WHERE is_active = 1 ORDER BY category, id ASC"
            ).fetchall()
        return [dict(r) for r in rows]

def get_learned_prompt_context() -> str:
    """Formats active learned rules for injection into agent system prompts."""
    rules = get_active_rules()
    if not rules:
        return ""

    stop_words = [r["rule_text"] for r in rules if r["category"] == "stop_word"]
    preferred = [r["rule_text"] for r in rules if r["category"] == "preferred_term"]
    tone_rules = [r["rule_text"] for r in rules if r["category"] in ("tone_rule", "format_rule")]

    lines = ["\n### ВЫУЧЕННЫЕ ПРАВИЛА И ЗАПРЕТЫ ЭКСПЕРТА (НА ОСНОВЕ РЕДАКТУРЫ):"]
    if stop_words:
        lines.append("🚫 **Строгие стоп-слова и запрещенные шаблоны:**")
        for sw in stop_words:
            lines.append(f"- НЕ использовать: {sw}")
    if preferred:
        lines.append("\n🎯 **Обязательные предпочтения и замена терминов:**")
        for pt in preferred:
            lines.append(f"- Использовать именно так: {pt}")
    if tone_rules:
        lines.append("\n⚖️ **Персональные правила тональности эксперта:**")
        for tr in tone_rules:
            lines.append(f"- {tr}")

    return "\n".join(lines) + "\n"

def add_golden_example(style: str, content: str, topic: str = "", engagement: float = 0.0) -> Tuple[bool, str]:
    """Saves a post as a golden few-shot benchmark."""
    clean_style = style.strip().lower() or "drama"
    clean_content = content.strip()
    if not clean_content:
        return False, "Текст эталона не может быть пустым."

    try:
        with get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO golden_examples (style, topic, content, engagement_metric)
                VALUES (?, ?, ?, ?)
                """,
                (clean_style, topic.strip(), clean_content, engagement)
            )
            ex_id = cur.lastrowid
        return True, f"Пост добавлен в Зал Славы (ID: #{ex_id}, стиль: {clean_style}) как золотой эталон!"
    except Exception as e:
        return False, f"Ошибка сохранения эталона: {e}"

def get_golden_examples(style: str, limit: int = 1) -> List[Dict[str, Any]]:
    """Returns top golden examples for the given style."""
    clean_style = style.strip().lower()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM golden_examples 
            WHERE style = ? 
            ORDER BY engagement_metric DESC, id DESC 
            LIMIT ?
            """,
            (clean_style, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def record_draft(message_id: int, chat_id: int, role: str, style: str, prompt: str, draft_text: str):
    """Saves a generated draft to history for later diff comparisons."""
    try:
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO draft_history (message_id, chat_id, role, style, prompt, draft_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, chat_id, role, style, prompt, draft_text)
            )
    except Exception:
        pass

def get_draft_by_message(message_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves draft info by message ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM draft_history WHERE chat_id = ? AND message_id = ? ORDER BY id DESC LIMIT 1",
            (chat_id, message_id)
        ).fetchone()
        return dict(row) if row else None

async def analyze_diff_and_learn(
    original_text: str,
    edited_text: str,
    user_comment: str = ""
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Compares original draft vs human-edited post.
    Uses LLM to extract atomic rules (stop words, vocabulary shifts)
    and automatically registers them into learned_rules table.
    """
    from tg_bot.engine.agent_runner import run_agent_task

    prompt = f"""
Ты — Chief Quality Officer и хранитель голоса (Tone of Voice) эксперта.
Сравни исходный черновик, сгенерированный ИИ, и финальную версию, которую человек-эксперт отредактировал руками.

Исходный черновик ИИ:
\"\"\"
{original_text[:3000]}
\"\"\"

Финальная версия эксперта:
\"\"\"
{edited_text[:3000]}
\"\"\"

Комментарий эксперта (если есть): {user_comment or "нет"}

Твоя задача — извлечь 2-4 КОНКРЕТНЫХ АТОМАРНЫХ ПРАВИЛА, которые сделали текст живым:
1. Какие штампы/канцеляризмы/пустые слова эксперт выкинул? (Категория: stop_word)
2. Какие термины/обороты эксперт поставил взамен? (Категория: preferred_term)
3. Что изменилось в ритме/пунктуации/длине фраз? (Категория: tone_rule)

Выдай ответ СТРОГО в формате JSON без markdown-разметки:
[
  {{"category": "stop_word", "rule_text": "Не использовать фразу X", "reason": "Заменено экспертом на Y"}},
  {{"category": "preferred_term", "rule_text": "Писать 'A' вместо 'B'", "reason": "Свойственный термин эксперта"}}
]
"""
    raw_response, model_name = await run_agent_task(
        role="editor",
        user_prompt=prompt
    )

    clean_json = raw_response.strip()
    if "```json" in clean_json:
        clean_json = clean_json.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in clean_json:
        clean_json = clean_json.split("```", 1)[1].split("```", 1)[0].strip()

    extracted_rules = []
    try:
        items = json.loads(clean_json)
        if isinstance(items, list):
            for item in items:
                cat = item.get("category", "tone_rule")
                rule = item.get("rule_text", "")
                reason = item.get("reason", "Извлечено из редактуры эксперта")
                if rule:
                    ok, _ = add_rule(cat, rule, reason=reason, source="diff_auto")
                    if ok:
                        extracted_rules.append(item)
    except Exception:
        pass

    report_lines = [
        "🧠 <b>Анализ редактуры эксперта завершён!</b>\n",
        f"Выявлено и закреплено новых правил ToV: <b>{len(extracted_rules)}</b>\n"
    ]
    for idx, r in enumerate(extracted_rules, 1):
        cat_icon = "🚫" if r.get("category") == "stop_word" else "🎯"
        report_lines.append(f"{idx}. {cat_icon} <b>{r.get('rule_text')}</b>\n   <i>Причина: {r.get('reason')}</i>")

    report_lines.append("\nВсе правила автоматически добавлены в системный промпт Копирайтера и чек-лист Главреда.")
    return "\n".join(report_lines), extracted_rules
