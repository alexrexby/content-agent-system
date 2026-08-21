# 🚀 Content Agent System

> **Многоагентная ИИ-система полного цикла для производства экспертного контента** (от транскриптов созвонов и голосовых заметок до готовых постов, сторителлинга и программно сгенерированных каруселей 1080×1350).

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Telegram Bot: Aiogram 3](https://img.shields.io/badge/Telegram_Bot-Aiogram_3-blue)](https://github.com/aiogram/aiogram)
[![Claude 3.5 / Gemini / Antigravity](https://img.shields.io/badge/AI_Engine-Claude%20%7C%20Gemini%20%7C%20Antigravity-purple)](https://cloud.google.com)

---

## 📌 Архитектура и принцип работы

Главное правило системы — **«Упаковка, а не выдумка»**:
1. Производство контента и факт-чекинг **строго разведены** между независимыми агентами.
2. Проверяющие агенты (`fakt-check`, `golos-amalii`) имеют статус **Read-Only** и выносят вердикт по каждому факту против реальных материалов эксперта.
3. Голос эксперта защищён от канцелярита, инфостиля и токсичных шаблонов-раздражителей.

```mermaid
flowchart TD
    A[🎙 Исходные материалы: Созвоны / Аудио / Тексты] --> B[🤖 sozvon-razbor: Смыслы & Факты]
    B --> C[🤖 hooks: ВИСП-Хуки & Скоринг виральности]
    C --> D[🤖 content: Посты / Сторис / Карусели]
    D --> E{🛡 Параллельная проверка}
    E -->|Факты| F[🤖 fakt-check: Сверка с первоисточниками]
    E -->|Tone of Voice| G[🤖 golos-amalii: Проверка живой речи]
    F & G --> H[✏️ Правки и финальная сборка]
    H --> I[🤖 karusel / Pillow: Генерация PNG 1080x1350]
```

---

## 👥 6 Ролей агентов

| Агент | Роль | Описание и задачи |
|---|---|---|
| **`sozvon-razbor`** | Аналитик созвонов | Транскрипт / запись созвона → ключевые инсайты, цитаты, задачи и реестр фактов. |
| **`hooks`** | Архитектор хуков | Генерация цепляющих заголовков по формуле **ВИСП** (Выгода, Интрига, Срочность, Причастность) + скоринг виральности (1-10). |
| **`content`** | Копирайтер | Написание постов в Telegram, сценариев Stories, подписей к рилс и текстов каруселей на основе реального опыта эксперта. |
| **`fakt-check`** | Факт-чекер *(Read-Only)* | Разбирает готовый текст на утверждения и сверяет с базой знаний. Защищает от ИИ-галлюцинаций. |
| **`golos-amalii`** | Главред ToV *(Read-Only)* | Следит за живой речью: убирает служебную разметку, канцелярит, заменяет длинные тире на короткие `-`, устраняет шаблонные фразы. |
| **`karusel`** | Арт-директор & Верстальщик | Проектирует структуру слайдов в JSON и компилирует карусели в PNG (1080×1350) через модуль верстки. |

---

## 🛠 Компоненты системы

### 1. Telegram-бот ассистент (`tg_bot/`)
- Построен на **Aiogram 3.x**.
- **Мультимодальный прием данных**: распознает голосовые сообщения и кружки (через Whisper API), документы (`.docx`, `.pdf`, `.txt`), изображения и ссылки.
- **Ремикс чужого контента**: принимает пост или скриншот карусели конкурента, сохраняет вирусный хук и полностью переписывает текст в Tone of Voice эксперта с генерацией готовых слайдов.
- **Оркестратор LLM (`agent_runner.py`)**: каскадный вызов через Google Antigravity CLI (`agy`), Anthropic Claude 3.5/4.5 (Polza AI / Direct API) и Google Gemini 2.5 Flash.

### 2. Программный генератор каруселей (`carousel_generator/`)
- Генерация слайдов высокой четкости **1080×1350 (соотношение 4:5)** на базе **Pillow (PIL)**.
- Автоматический перенос строк, расчет вертикальных отступов и выравнивание.
- Типографическая система: обложки (Cover), синие перебивки (Break), списки/чек-листы (List), финальные слайды с CTA (Endcard).
- Поддержка вставки фото эксперта с авто-кадрированием.

### 3. Скиллы для ИИ-ассистентов (`.agents/skills/`, `.claude/`, `.codex/`)
- Совместимы с **Claude Code**, **OpenAI Codex**, **Google Antigravity IDE** и **Antigravity CLI**:
  - `expert-storytelling` — сценарии сторис по кадрам с интерактивами.
  - `tg-channel-posts` — прогревающие контент-планы и публикации для Telegram.
  - `visp-hooks` — формула ВИСП для Reels и заголовков.

---

## 📂 Структура проекта

```
content-agent-system/
├── .agents/
│   └── skills/                # Скиллы для ИИ-ассистентов (Markdown + Frontmatter)
├── .claude/
│   └── agents/                # Промпты ролей для Claude Code (.md)
├── .codex/
│   └── agents/                # Промпты ролей для Codex (.toml)
├── tg_bot/
│   ├── main.py                # Точка входа Telegram-бота
│   ├── config.py              # Конфигурация и переменные окружения
│   ├── requirements.txt       # Python-зависимости бота
│   ├── deploy/                # Systemd service и скрипты деплоя
│   ├── engine/
│   │   ├── agent_runner.py    # LLM-оркестратор (Antigravity / Claude / Gemini / Whisper)
│   │   ├── carousel_builder.py# Динамическая сборка карточек из JSON
│   │   ├── file_extractor.py  # Извлечение текста из docx, pdf, аудио
│   │   ├── formatter.py       # Telegram MarkdownV2 / HTML форматирование
│   │   ├── insta_monitor.py   # Модуль мониторинга и ремикса рилсов
│   │   └── prompts.py         # Менеджер промптов и интеграции скиллов
│   └── handlers/
│       └── router.py          # Обработчики команд и диалогов бота
├── carousel_generator/
│   ├── build_karusel.py       # Движок верстки слайдов на Pillow
│   ├── decks.py               # Шаблоны и примеры каруселей
│   └── photo.jpg              # Фото эксперта для обложек и CTA
├── AGENTS.md                  # Корневой манифест правил системы и голоса
├── CLAUDE.md                  # Системные инструкции для Claude Code
├── .env.example               # Шаблон переменных окружения
├── .gitignore
├── LICENSE                    # MIT License
├── requirements.txt
└── README.md
```

---

## ⚡️ Быстрый старт

### 1. Клонирование и установка зависимостей

```bash
git clone https://github.com/alexrexby/content-agent-system.git
cd content-agent-system

python3 -m venv venv
source venv/bin/activate  # На Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env` и укажите необходимые ключи:

```bash
cp .env.example .env
```

Отредактируйте `.env`:
```ini
# Токен бота из @BotFather
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# API-ключ для Claude 3.5 / Polza AI (или прямой OpenAI / Gemini)
POLZA_API_KEY=pza_xxxxxxxxxxxx
AI_BASE_URL=https://api.polza.ai/api/v1
CLAUDE_MODEL=anthropic/claude-sonnet-4.5

# Опционально: Google Gemini
GEMINI_API_KEY=AIzaxxxxxxxxxxxxx
```

### 3. Запуск Telegram-бота

```bash
python -m tg_bot.main
```

### 4. Генерация каруселей через консоль

Собрать все предустановленные карусели:
```bash
python carousel_generator/build_karusel.py
```

Собрать конкретную карусель (например, `voda`):
```bash
python carousel_generator/build_karusel.py voda
```

Собрать карусель из произвольного JSON-файла:
```bash
python carousel_generator/build_karusel.py --json path/to/deck.json path/to/output_dir
```

---

## 🎯 Формула ВИСП для хуков

Каждый заголовок и первый кадр контента валидируется по 4 осям:
- **В (Выгода)**: что конкретно получит читатель (деньги, время, спокойствие).
- **И (Интрига)**: разрыв шаблона, парадокс, неочевидный факт.
- **С (Срочность)**: почему это нужно внедрить прямо сейчас (сезонность, потери).
- **П (Причастность)**: точное попадание в статус и боли целевой аудитории (собственники, обороты, найм).

---

## 📜 Лицензия

Проект распространяется под лицензией [MIT](LICENSE).
