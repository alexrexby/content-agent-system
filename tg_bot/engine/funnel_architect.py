from __future__ import annotations
import json
import re
from pathlib import Path
from tg_bot.config import BASE_DIR
from tg_bot.engine.agent_runner import run_agent_task

FUNNELS_DIR = BASE_DIR / "data" / "funnels"
FUNNELS_DIR.mkdir(parents=True, exist_ok=True)

def generate_funnel_prompt(topic: str, target_audience: str = "") -> str:
    ta_line = f"Целевая аудитория: {target_audience}\n" if target_audience else ""
    return f"""
Ты — Ведущий Архитектор Автоворонок (скилл funnel-architect).
Твоя задача — спроектировать сквозную конверсионную автоворонку под ключ по методологии:
- Сабри Суби: Пирамида 97% и формат High-Value Content Offer (HVCO).
- Алекс Хормози: Лид-магнит как продающий инструмент (The One-Step Solution & The Gap).
- Тимур Кадыров: 3-шаговая модель экспресс-прогрева «Микроволновка» внутри чат-бота с сегментацией.

ТЕМА ВОРОНКИ: «{topic}»
{ta_line}
Построй законченную систему из 5 неразрывных уровней:

==================================================
УРОВЕНЬ 1: ТРАФИК-ВХОД (ПОСТ / СЦЕНАРИЙ REELS)
- Контринтуитивный хук-пощечина (разрыв шаблона / вскрытие угрозы кассового разрыва).
- Текст вовлечения: показ коллективной ошибки 90% рынка.
- Отрезвляющая правда эксперта.
- Одно четкое КОДОВОЕ СЛОВО (капсом) для чат-бота.

==================================================
УРОВЕНЬ 2: HVCO ЛИД-МАГНИТ (ПРОДАЮЩИЙ АРТЕФАКТ)
- Сенсационный заголовок по формуле Сабри Суби (Оцифрованный результат + Срок + Без главной боли).
- Формат: Диагностический чек-лист потерь / Инженерный Blueprint / Калькулятор.
- 3-5 шагов концентрированной прикладной пользы.
- БЛОК «THE GAP» (Недостающее звено): почему в одиночку по бесплатному чек-листу систему не внедрить, и в чем ценность основного продукта.

==================================================
УРОВЕНЬ 3: СЦЕНАРИЙ ЧАТ-БОТА «МИКРОВОЛНОВКА» (3 СООБЩЕНИЯ)
- Сообщение 1 (0 мин): Моментальная выдача лид-магнита + Опрос-сегментатор в 1 клик (2-3 инлайн-кнопки).
- Сообщение 2 (+7 мин): Взлом ключевой иллюзии рынка (короткий тезис / аудио эксперта: почему старый подход разрушает кассу).
- Сообщение 3 (+15 мин): The Gap + Оффер-мост на следующий логичный шаг (приглашение на аудит / разбор).

==================================================
УРОВЕНЬ 4: КВАЛИФИКАЦИОННАЯ АНКЕТА (LEAD QUALIFICATION)
- 4-5 жестких фильтрующих вопросов для отсева нецелевых лидов перед записью к эксперту.

==================================================
УРОВЕНЬ 5: JSON-СХЕМА ВОРОНКИ ДЛЯ ЧАТ-БОТА
Создай валидный JSON-блок сценария для импорта:
```json
{{
  "funnel_name": "Название воронки",
  "keyword": "КОДОВОЕ_СЛОВО",
  "target_audience": "Описание ЦА",
  "steps": [
    {{
      "step": 1,
      "delay_seconds": 0,
      "type": "welcome_and_lead_magnet",
      "text": "Текст первого сообщения с лид-магнитом",
      "buttons": ["Кнопка 1 (Сегмент A)", "Кнопка 2 (Сегмент B)"]
    }},
    {{
      "step": 2,
      "delay_seconds": 420,
      "type": "mindset_break",
      "text": "Текст второго сообщения со сломом убеждения",
      "buttons": ["Посмотреть разбор", "У меня так же!"]
    }},
    {{
      "step": 3,
      "delay_seconds": 900,
      "type": "the_gap_offer",
      "text": "Текст третьего сообщения с оффером на аудит",
      "buttons": ["Заполнить анкету", "Узнать подробности"]
    }}
  ]
}}
```

Пиши живым, убедительным, экспертным языком. Никаких шаблонных фраз вроде «не потому что X, а потому что Y». Только короткое тире «-».
""".strip()

def extract_json_schema(text: str) -> dict | None:
    """Extracts JSON object from model markdown fences."""
    matches = re.findall(r"```(?:json)?\s*(\{.+?\})\s*```", text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except Exception:
            continue
    # Try finding raw json
    match_raw = re.search(r"(\{\s*\"funnel_name\".+?\})", text, re.DOTALL)
    if match_raw:
        try:
            return json.loads(match_raw.group(1))
        except Exception:
            pass
    return None

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:40] if text else "funnel"

def export_funnel_files(funnel_title: str, markdown_content: str, json_schema: dict | None = None) -> tuple[Path, Path]:
    """Exports full funnel dossier to Markdown and JSON schema files."""
    slug = slugify(funnel_title)
    target_dir = FUNNELS_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)

    md_path = target_dir / "funnel_dossier.md"
    md_path.write_text(markdown_content, encoding="utf-8")

    json_path = target_dir / "bot_schema.json"
    if json_schema:
        json_path.write_text(json.dumps(json_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        fallback = {
            "funnel_name": funnel_title,
            "raw_notes": "JSON schema parsed directly from dossier",
            "source_file": str(md_path)
        }
        json_path.write_text(json.dumps(fallback, ensure_ascii=False, indent=2), encoding="utf-8")

    return md_path, json_path

async def build_full_funnel(topic: str, target_audience: str = "") -> dict:
    """Runs the full architect generation and returns structured data."""
    prompt = generate_funnel_prompt(topic, target_audience)
    raw_response, model_name = await run_agent_task(
        role="copywriter",
        user_prompt=prompt,
        style="provocation"
    )

    json_schema = extract_json_schema(raw_response)
    funnel_title = json_schema.get("funnel_name", topic) if json_schema else topic
    keyword = json_schema.get("keyword", "СТАРТ") if json_schema else "СТАРТ"

    md_path, json_path = export_funnel_files(funnel_title, raw_response, json_schema)

    return {
        "title": funnel_title,
        "keyword": keyword,
        "markdown": raw_response,
        "json_schema": json_schema,
        "md_path": md_path,
        "json_path": json_path,
        "model_name": model_name
    }
