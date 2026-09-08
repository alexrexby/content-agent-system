from __future__ import annotations
import os
import re
import sys
import json
import time
import subprocess
from pathlib import Path
from tg_bot.config import KARUSEL_DIR

AVAILABLE_DECKS = [
    "voda", "sobraniya", "kreslo", "opytny", "smenili", "ne_prodaet",
    "zerkalo", "silnye", "stabilizaciya", "sostoyanie", "progibaetes",
    "procent", "poteri", "upravlyayushchaya", "baza", "adaptaciya"
]

def extract_json_slides(text: str) -> list[dict] | None:
    """Extracts JSON array from agent response."""
    try:
        match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        match_raw = re.search(r'(\[\s*\{.*\}\s*\])', text, re.DOTALL)
        if match_raw:
            return json.loads(match_raw.group(1))
    except Exception:
        pass
    return None

async def build_dynamic_carousel(topic: str) -> tuple[bool, str, list[Path], str, str]:
    """
    Generates a brand new carousel from scratch using AI Agent and compiles it to PNG slides.
    Returns (success, log, images, deck_name, model_name).
    """
    from tg_bot.engine.agent_runner import run_agent_task

    prompt = (
        f"Создай полноценную новую карусель (4-7 слайдов) для блога эксперта на тему:\n«{topic}»\n\n"
        "ОБЯЗАТЕЛЬНО верни результат в виде валидного JSON-массива карточек (с типами: cover, break, list, cta)."
    )

    ai_response, model_name = await run_agent_task(role="karusel", user_prompt=prompt)
    return await compile_slides_to_png(ai_response, topic, model_name)

async def remake_competitor_carousel(source_text: str = "", image_bytes: bytes = None) -> tuple[bool, str, list[Path], str, str, str]:
    """
    Adapts competitor carousel/post into Expert Tone of Voice and compiles to PNG slides.
    Returns (success, log, images, deck_name, model_name, explanation_text).
    """
    from tg_bot.engine.agent_runner import run_agent_task

    prompt = (
        "Ты — Копирайтер и Дизайнер проекта эксперта.\n"
        "Перед тобой карусель или пост другого автора/конкурента.\n\n"
        "ТВОЯ ЗАДАЧА:\n"
        "1. Сохрани вирусный ХУК и базовую структуру пользы.\n"
        "2. ПОЛНОСТЬЮ перепиши текст карточек живым голосом эксперта (бьюти-бизнес, живая речь, бытовые образы, рубленые добивки, короткое тире '-', ЗАПРЕТ на 'не потому что X, а Y' и канцелярит).\n"
        "3. В начале ответа дай краткий комментарий: в чём был хук и что мы усилили под голос эксперта.\n"
        "4. Затем сформируй строгий JSON-массив карточек для Дизайнера (1080x1350):\n"
        "```json\n"
        "[\n"
        "  {\n"
        "    \"type\": \"cover\",\n"
        "    \"title\": [[\"Заголовок обложки\", \"INK\"], [\"акцент\", \"BLUE\"]],\n"
        "    \"lead\": \"Лид обложки на 2 предложения\",\n"
        "    \"quote\": \"Хлёсткая цитата эксперта\"\n"
        "  },\n"
        "  {\n"
        "    \"type\": \"break\",\n"
        "    \"tag\": \"Проблема\",\n"
        "    \"title\": \"Заголовок синей перебивки\",\n"
        "    \"lead\": \"Текст перебивки\"\n"
        "  },\n"
        "  {\n"
        "    \"type\": \"list\",\n"
        "    \"tag\": \"Шаг 1\",\n"
        "    \"title\": [[\"Суть пункта\", \"INK\"], [\"важно\", \"BLUE\"]],\n"
        "    \"label\": \"Чек-лист:\",\n"
        "    \"items\": [\"Пункт 1\", \"Пункт 2\", \"Пункт 3\"]\n"
        "  },\n"
        "  {\n"
        "    \"type\": \"cta\",\n"
        "    \"tag\": \"Забирайте\",\n"
        "    \"word\": \"СЛОВО\",\n"
        "    \"title\": [[\"Разбираем в канале\", \"INK\"], [\"подробнее\", \"BLUE\"]],\n"
        "    \"lead\": \"Напишите кодовое слово в комментариях.\"\n"
        "  }\n"
        "]\n"
        "```\n\n"
        f"ИСХОДНЫЙ МАТЕРИАЛ ДЛЯ АДАПТАЦИИ:\n{source_text}"
    )

    ai_response, model_name = await run_agent_task(
        role="karusel",
        user_prompt=prompt,
        image_bytes=image_bytes,
        mime_type="image/jpeg" if image_bytes else None
    )

    success, log, images, deck_name, _ = await compile_slides_to_png(ai_response, "Адаптация карусели", model_name)
    
    # Clean explanation text from JSON block
    clean_explanation = re.sub(r'```(?:json)?\s*\[.*?\]\s*```', '', ai_response, flags=re.DOTALL).strip()
    return success, log, images, deck_name, model_name, clean_explanation

async def compile_slides_to_png(ai_response: str, topic: str, model_name: str) -> tuple[bool, str, list[Path], str, str]:
    slides = extract_json_slides(ai_response)
    if not slides:
        return False, f"Не удалось извлечь структуру карусели:\n{ai_response[:500]}", [], topic, model_name

    timestamp = int(time.time())
    custom_dir = KARUSEL_DIR / f"karusel_custom_{timestamp}"
    custom_dir.mkdir(parents=True, exist_ok=True)
    json_path = custom_dir / "deck.json"
    json_path.write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = KARUSEL_DIR / "build_karusel.py"
    cmd = [sys.executable, str(script_path), "--json", str(json_path), str(custom_dir)]

    try:
        res = subprocess.run(cmd, cwd=str(KARUSEL_DIR), capture_output=True, text=True, check=False)
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        images = sorted(list(custom_dir.glob("*.png")))
        return (res.returncode == 0 and len(images) > 0), output, images, topic, model_name
    except Exception as e:
        return False, str(e), [], topic, model_name

def run_build_karusel(deck_name: str | None = None) -> tuple[bool, str, list[Path], str]:
    """Executes build_karusel.py for pre-built templates."""
    if not KARUSEL_DIR.exists():
        return False, f"Папка генератора {KARUSEL_DIR} не найдена.", [], ""
        
    script_path = KARUSEL_DIR / "build_karusel.py"
    if not script_path.exists():
        return False, f"Скрипт {script_path} не найден.", [], ""

    target_deck = "voda"
    if deck_name:
        clean_name = deck_name.strip().lower()
        matched = [d for d in AVAILABLE_DECKS if clean_name in d or d in clean_name]
        if matched:
            target_deck = matched[0]
        elif clean_name in AVAILABLE_DECKS:
            target_deck = clean_name
        else:
            target_deck = "voda"

    cmd = [sys.executable, str(script_path), target_deck]

    try:
        res = subprocess.run(cmd, cwd=str(KARUSEL_DIR), capture_output=True, text=True, check=False)
        output = (res.stdout or "") + "\n" + (res.stderr or "")
        cards_dir = KARUSEL_DIR / target_deck
        images = sorted(list(cards_dir.glob("*.png"))) if cards_dir.exists() else []
        return (res.returncode == 0 and len(images) > 0), output, images, target_deck
    except Exception as e:
        return False, str(e), [], target_deck
