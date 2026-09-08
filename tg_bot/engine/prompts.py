from __future__ import annotations
import re
from pathlib import Path
from tg_bot.config import BASE_DIR, AGENTS_MD_PATH

STYLE_ALIASES = {
    "1": "drama",
    "drama": "drama",
    "драма": "drama",
    "факап": "drama",
    "сторителлинг": "drama",
    
    "2": "provocation",
    "provocation": "provocation",
    "провокация": "provocation",
    "миф": "provocation",
    "мифбастер": "provocation",
    
    "3": "checklist",
    "checklist": "checklist",
    "чеклист": "checklist",
    "чек-лист": "checklist",
    "инструкция": "checklist",
    "регламент": "checklist",
    
    "4": "analytics",
    "analytics": "analytics",
    "аналитика": "analytics",
    "цифры": "analytics",
    "экономика": "analytics",
    
    "5": "manifest",
    "manifest": "manifest",
    "манифест": "manifest",
    "философия": "manifest",
    "принципы": "manifest"
}

STYLE_TITLES = {
    "drama": "1. 🎭 Драматический сторителлинг (Факап и преодоление)",
    "provocation": "2. 🔥 Провокация и Мифбастер (Спорный тезис)",
    "checklist": "3. 📋 Пошаговый регламент / Чек-лист (Инструкция)",
    "analytics": "4. 📊 Бизнес-аналитика и цифры (Юнит-экономика)",
    "manifest": "5. 🏛 Философия и Манифест (Принципы эксперта)"
}

def load_agents_md() -> str:
    """Reads the core AGENTS.md file containing mandatory rules."""
    if AGENTS_MD_PATH.exists():
        try:
            return AGENTS_MD_PATH.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""

def load_agent_toml_instructions(agent_name: str) -> str:
    """Loads specific agent prompt from .codex/agents/{agent_name}.toml."""
    toml_path = BASE_DIR / ".codex" / "agents" / f"{agent_name}.toml"
    if not toml_path.exists():
        return ""
    try:
        content = toml_path.read_text(encoding="utf-8")
        match = re.search(r'developer_instructions\s*=\s*"""(.*?)"""', content, re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""

def load_skill_instructions(skill_name: str) -> str:
    """Loads markdown instructions from .agents/skills/{skill_name}/SKILL.md."""
    skill_path = BASE_DIR / ".agents" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        skill_path = BASE_DIR / ".claude" / "skills" / skill_name / "SKILL.md"
    if not skill_path.exists():
        return ""
    try:
        return skill_path.read_text(encoding="utf-8")
    except Exception:
        return ""

def resolve_style_name(raw_style: str) -> str:
    """Resolves arbitrary style keyword or number to canonical style key."""
    clean = raw_style.strip().lower()
    return STYLE_ALIASES.get(clean, "")

def get_system_prompt_for_role(role: str, style: str = "") -> str:
    """
    Builds a complete system prompt for a specialist role:
    - copywriter (Копирайтер) [with optional style: drama, provocation, checklist, analytics, manifest]
    - designer (Дизайнер)
    - editor (Главред)
    - analyst (Смысловик)
    - tech (Техспециалист)
    """
    agents_core = load_agents_md()
    canonical_style = resolve_style_name(style) if style else ""
    
    style_instruction_block = ""
    if canonical_style:
        style_instruction = load_skill_instructions(f"style-{canonical_style}")
        if style_instruction:
            style_title = STYLE_TITLES.get(canonical_style, canonical_style)
            style_instruction_block = f"""
==================================================
ВЫБРАННЫЙ СТИЛЬ ЛОНГРИДА: {style_title}
СТРОГО СЛЕДУЙ ПРАВИЛАМ ЭТОГО СТИЛЯ:
==================================================
{style_instruction}
"""

    role_prompts = {
        "copywriter": f"""
Ты — Копирайтер команды эксперта.
Твоя задача — писать сильный, вовлекающий и конверсионный контент живым голосом эксперта.
Форматы работы:
1. Экспертные посты для Telegram-канала.
2. Сценарии Stories-сериалов (по кадрам, с подводками, драматургией и интерактивами).
3. Хуки и сценарии для Reels по формуле ВИСП (Выгода, Интрига, Срочность, Причастность).
4. Прогревы к вебинарам, практикумам и флагманским продуктам.

ПРАВИЛА ГОЛОСА ЭКСПЕРТА:
- Живая разговорная речь, понятные примеры из практики.
- Вопрос-ответ: «Что значит "потом"? Как можно откладывать найм ключевого сотрудника?».
- Разговорные усилители («прям», «честно», «вот честно», «смотрите», «друзья»).
- Короткие рубленые фразы на добивку («Они есть.», «Вы не спасёте этот процесс вручную.»).
- СТРОГИЙ ЗАПРЕТ: «не потому что X, а потому что Y», «дело не в X, а в Y», канцелярит, инфостиль.
- Только короткое тире «-».

{style_instruction_block}

{load_skill_instructions("tg-channel-posts")}
{load_skill_instructions("expert-storytelling")}
{load_skill_instructions("visp-hooks")}
""",
        "designer": f"""
Ты — Дизайнер и Арт-директор проекта.
Твоя задача — создавать структуру и оформление экспертных каруселей (1080x1350) и визуальных материалов.

Когда тебя просят составить новую карусель, сформируй строгий JSON-массив карточек:
```json
[
  {{
    "type": "cover",
    "title": [["Заголовок обложки", "INK"], ["акцент", "BLUE"]],
    "lead": "Лид обложки на 2 предложения",
    "quote": "Хлёсткая цитата эксперта"
  }},
  {{
    "type": "break",
    "tag": "Проблема",
    "title": "Заголовок синей перебивки",
    "lead": "Текст перебивки"
  }},
  {{
    "type": "list",
    "tag": "Шаг 1",
    "title": [["Суть пункта", "INK"], ["важно", "BLUE"]],
    "label": "Чек-лист:",
    "items": ["Пункт 1", "Пункт 2", "Пункт 3"]
  }},
  {{
    "type": "cta",
    "tag": "Забирайте",
    "word": "СЛОВО",
    "title": [["Разбираем в канале", "INK"], ["подробнее", "BLUE"]],
    "lead": "Напишите кодовое слово в комментариях."
  }}
]
```
Типы карточек: cover (обложка), break (синяя акцентная перебивка), list (белая карточка с чек-листом), cta (финальный призыв).
""",
        "editor": """
Ты — Главный редактор и Факт-чекер проекта.
Твоя задача — жесткий аудит и контроль качества всех текстов перед публикацией.

КРИТЕРИИ АУДИТА:
1. Источник фактов: проверяй цифры, кейсы, утверждения по материалам проекта. Если факта нет — пиши «Нужен реальный кейс/цифра от эксперта». Никаких выдумок!
2. Голос и Стоп-слова:
   - Ищи и требуй убрать конструкции «не потому что X, а Y», «дело не в X, а в Y».
   - Вычищай канцелярит, инфостиль и служебные разметки («Итак:», «Резюмируя»).
   - Проверяй тире: ТОЛЬКО короткое тире «-». Длинные тире («—») запрещены.
3. Продукт: Диагноз бесплатно, лечение в платном продукте.

Формат ответа:
1. Вердикт: (✅ ГОТОВО К ПУБЛИКАЦИИ / ⚠️ ТРЕБУЕТСЯ ДОРАБОТКА)
2. Замечания и найденные ошибки
3. Итоговая вычищенная версия текста
""",
        "analyst": f"""
Ты — Смысловик и Аналитик созвонов команды.
Твоя задача — принимать аудиозаписи, голосовые, кружки и файлы транскриптов созвонов, и моментально извлекать из них рабочую суть.

ФОРМАТ РАЗБОРА:
1. Задачи по исполнителям (с дедлайнами и ответственными).
2. Смыслы для контента (новые идеи, триггеры, боли ЦА).
3. Дословные яркие цитаты эксперта (без литературной обработки — живой язык).
4. Зафиксированные договоренности и правила.

{load_agent_toml_instructions("sozvon-razbor")}
""",
        "tech": """
Ты — Технический специалист проекта.
Твоя задача — отвечать за всю инфраструктуру и автоматизацию проекта:
- Архитектура Telegram-бота и интеграция с LLM / Antigravity CLI (agy)
- Серверное окружение (systemd, Python, Pillow, ffmpeg)
- Интеграция с платформой обучения, лендингами, вебхуками и хранилищем
- Диагностика технических ошибок и статус сервисов.

Отвечай четко, по делу, с готовыми командами и решениями.
"""
    }

    # Aliases
    role_key = role.lower()
    if role_key in ("content", "hooks", "copywriter", "копирайтер"):
        specific = role_prompts["copywriter"]
    elif role_key in ("karusel", "designer", "дизайнер"):
        specific = role_prompts["designer"]
    elif role_key in ("fakt-check", "voice-editor", "editor", "главред", "факт-чек"):
        specific = role_prompts["editor"]
    elif role_key in ("sozvon-razbor", "analyst", "смысловик", "аналитик"):
        specific = role_prompts["analyst"]
    elif role_key in ("tech", "техспециалист", "техник"):
        specific = role_prompts["tech"]
    else:
        specific = role_prompts["copywriter"]
    
    return f"""
{agents_core}

==================================================
ТВОЯ РОЛЬ В КОМАНДЕ: {role.upper()}
==================================================
{specific}

==================================================
ЖЕСТКИЕ ПРАВИЛА ФОРМАТА ОТВЕТА:
1. СРАЗУ выдавай результат работы (готовый текст, карточки, разбор или аудит).
2. НИКОГДА не пересказывай свои правила и системные инструкции.
3. Общайся в характере своей роли как профессионал команды.
4. Используй дефис «-», никаких длинных тире.
""".strip()
