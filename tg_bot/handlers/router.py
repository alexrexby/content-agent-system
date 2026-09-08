from __future__ import annotations
import os
import io
import html
import asyncio
from pathlib import Path
from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

from tg_bot.config import MATERIALS_DIR, RAZBOR_DIR
from tg_bot.engine.agent_runner import run_agent_task
from tg_bot.engine.file_extractor import extract_text_from_file
from tg_bot.engine.carousel_builder import run_build_karusel, build_dynamic_carousel, remake_competitor_carousel, AVAILABLE_DECKS
from tg_bot.engine.formatter import markdown_to_telegram_html
from tg_bot.engine.insta_monitor import is_instagram_url, extract_instagram_url, analyze_instagram_post
from tg_bot.engine.prompts import STYLE_TITLES, resolve_style_name, get_lead_magnet_prompt, get_blueprint_prompt
from tg_bot.engine.knowledge_base import index_materials_directory, search_knowledge
from tg_bot.engine.insta_batch import analyze_competitor_profile
from tg_bot.engine.video_pipeline import process_video_montage
from tg_bot.engine.browser_worker import (
    take_page_screenshot, execute_web_recipe, is_playwright_available, SESSION_STATE_FILE
)
from tg_bot.engine.learning_engine import (
    add_rule, delete_rule, get_active_rules, add_golden_example,
    record_draft, get_draft_by_message, analyze_diff_and_learn
)
from tg_bot.engine.recipe_runner import (
    get_available_recipes, get_recipe_details, format_recipe_for_telegram, execute_recipe
)
from tg_bot.engine.recon_spider import build_dossier
from tg_bot.engine.outreach_worker import (
    add_lead, get_outreach_summary, run_outreach_dispatch
)

router = Router()

TOPIC_ROLES = {}
PENDING_POST_TOPICS: dict[int, str] = {}

def get_post_feedback_keyboard(style: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧲 Лид-магнит", callback_data=f"magnet:{style}"),
                InlineKeyboardButton(text="⭐️ В эталоны", callback_data=f"golden:{style}"),
                InlineKeyboardButton(text="💡 Обучение", callback_data="learn_hint")
            ]
        ]
    )

def get_styles_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎭 1. Драма & Факап", callback_data="style:drama")],
            [InlineKeyboardButton(text="🔥 2. Провокация & Мифбастер", callback_data="style:provocation")],
            [InlineKeyboardButton(text="📋 3. Чек-лист & Регламент", callback_data="style:checklist")],
            [InlineKeyboardButton(text="📊 4. Аналитика & Цифры", callback_data="style:analytics")],
            [InlineKeyboardButton(text="🏛 5. Манифест & Ценности", callback_data="style:manifest")]
        ]
    )

FORUM_TOPICS = [
    {
        "name": "✍️ Копирайтер",
        "role": "copywriter",
        "welcome": "✍️ <b>Копирайтер команды</b>\n\nПишите задачи на посты в Telegram-канал, серии Stories, прогревы к вебинарам и продукты.\nПоддерживается 5 стилей лонгридов (Драма, Провокация, Чек-лист, Аналитика, Манифест).\nИспользуйте команду <code>/post [стиль] [тема]</code>."
    },
    {
        "name": "🎨 Дизайнер",
        "role": "designer",
        "welcome": "🎨 <b>Дизайнер и Арт-директор</b>\n\nНапишите <b>любую новую тему</b> (например: <i>найм администратора</i>, <i>почему уходят клиенты</i>) — я сразу составлю структуру, сверстаю карточки 1080x1350 в фирменном стиле и пришлю готовые PNG в чат!\n\nИли выберите готовую тему: <code>" + ", ".join(AVAILABLE_DECKS[:8]) + "</code>."
    },
    {
        "name": "🔍 Главред",
        "role": "editor",
        "welcome": "🔍 <b>Главный редактор и Факт-чекер</b>\n\nПрисылайте готовые тексты на аудит. Я проверю соответствие первоисточникам (materials/), вычищу стоп-слова («не потому что X, а Y», канцелярит, инфостиль), проверю тире «-» и правило «диагноз бесплатно, лечение в продукте»."
    },
    {
        "name": "🎙 Смысловик",
        "role": "analyst",
        "welcome": "🎙 <b>Смысловик и Аналитик созвонов</b>\n\nСкидывайте сюда аудиозаписи, голосовые, кружки или файлы транскриптов (.docx, .pdf, .txt, .html).\nЯ моментально вытащу: задачи по исполнителям, дословные цитаты эксперта и смысловые блоки для контента."
    },
    {
        "name": "⚙️ Техспециалист",
        "role": "tech",
        "welcome": "⚙️ <b>Технический специалист</b>\n\nОтвечаю за инфраструктуру: сервер, работу бота, Antigravity CLI (agy), базу знаний FTS5, карусели и деплой.\nЗадавайте вопросы по технической части или отправляйте команды <code>/status</code>, <code>/index</code>."
    }
]

HELP_TEXT = """
👋 <b>Команда специалистов Content Agent System в сборе!</b>

👥 <b>Специалисты в команде:</b>
• ✍️ <b>Копирайтер</b> — 5 стилей лонгридов, сценарии Stories, хуки ВИСП и прогревы
• 🎨 <b>Дизайнер</b> — генерация каруселей 1080x1350 (PNG), визуал
• 🔍 <b>Главред</b> — факт-чекинг, вычитка стоп-слов, контроль голоса
• 🎙 <b>Смысловик</b> — расшифровка аудио/созвонов, извлечение задач и цитат
• ⚙️ <b>Техспециалист</b> — инфраструктура, сервер, бот, база знаний FTS5

📌 <b>5 стилей лонгридов (/post):</b>
1. 🎭 <b>Драма</b> — личная история, факап и преодоление (доверие)
2. 🔥 <b>Провокация</b> — мифбастер, слом шаблона (комментарии)
3. 📋 <b>Чек-лист</b> — пошаговая инструкция, регламент (сохранения)
4. 📊 <b>Аналитика</b> — юнит-экономика, цифры, окупаемость (статус)
5. 🏛 <b>Манифест</b> — принципы эксперта, философия, фильтр ЦА

📌 <b>Команды для любого чата:</b>
• <code>/post [стиль] [тема]</code> — генерация поста (со стилем или кнопками)
• <code>/karusel [тема]</code> — задача для Дизайнера (сборка PNG 1080x1350)
• <code>/check [текст]</code> — задача для Главреда (аудит)
• <code>/sozvon [файл/аудио]</code> — задача для Смысловика (разбор)
• <code>/insta [ссылка на Reels/пост]</code> — скачать, расшифровать и разобрать рилс
• <code>/spy [аккаунт] [лимит]</code> — пакетный парсинг рилсов конкурента (топ-виральные, хуки, офферы)
• <code>/montage [видео]</code> — авто-монтаж: вырезка пауз + стильные субтитры 9:16
• <code>/browser [URL]</code> — браузерный агент (скриншот страницы Playwright)
• <code>/outreach [stats|add|send]</code> — PR-аутрич блогеров и запуск рассылки
• <code>/recon [username/URL]</code> — OSINT-разведка в стиле SpiderFoot (досье, стек, контакты)
• <code>/magnet [тема]</code> — продающий лид-магнит + кодовое слово в бот (методология 2026)
• <code>/blueprint [тема]</code> — архитектурный Blueprint / Miro-карта системы
• <code>/recipes</code> — каталог проверенных рецептов решения задач (GetCourse, Tilda, VK)
• <code>/recipe [домен]</code> — регламент и капканы работы с платформой (/recipe run)
• <code>/learn [правило]</code> — обучение бота персональным правилам Tone of Voice
• <code>/rules</code> — просмотр и управление выученными правилами (/delrule)
• <code>/index</code> — переиндексация базы знаний FTS5
• <code>/status</code> — статус бота, материалов и базы знаний
• <code>/setup_forum</code> — создание веток специалистов в группе
"""

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(HELP_TEXT, parse_mode="HTML")

@router.message(Command("setup_forum"))
async def cmd_setup_forum(message: types.Message):
    if not message.chat.is_forum:
        await message.answer(
            "⚠️ <b>В группе пока не включены Темы (Topics)!</b>\n\n"
            "Чтобы я мог создать ветки специалистов:\n"
            "1. Зайдите в <b>Настройки группы</b> (в Telegram)\n"
            "2. Включите переключатель <b>«Темы» / «Topics»</b>\n"
            "3. Снова напишите команду <code>/setup_forum</code>",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("🛠 Начинаю создание рабочих веток специалистов...", parse_mode="HTML")
    created_count = 0

    for topic_info in FORUM_TOPICS:
        try:
            topic = await message.bot.create_forum_topic(
                chat_id=message.chat.id,
                name=topic_info["name"]
            )
            TOPIC_ROLES[topic.message_thread_id] = topic_info["role"]
            
            await message.bot.send_message(
                chat_id=message.chat.id,
                message_thread_id=topic.message_thread_id,
                text=topic_info["welcome"],
                parse_mode="HTML"
            )
            created_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            await message.answer(f"Не удалось создать тему {topic_info['name']}: {e}")

    await status_msg.edit_text(
        f"✅ <b>Форум готов! Создано {created_count} рабочих веток специалистов.</b>\n\n"
        "Теперь вы можете писать в нужную ветку — бот автоматически будет отвечать от имени соответствующего эксперта команды!",
        parse_mode="HTML"
    )

@router.message(Command("status"))
async def cmd_status(message: types.Message):
    mat_count = len([f for f in MATERIALS_DIR.rglob("*.*") if not f.name.startswith(".")]) if MATERIALS_DIR.exists() else 0
    razbor_count = len(list(RAZBOR_DIR.glob("*.md"))) if RAZBOR_DIR.exists() else 0
    await message.answer(
        f"✅ <b>Команда активна и готова к работе!</b>\n\n"
        f"📁 Файлов в materials/: <code>{mat_count}</code> (транскрипты и выгрузки)\n"
        f"📝 Разборов в 02 Разборы созвонов: <code>{razbor_count}</code>\n"
        f"🔍 База знаний FTS5: <code>активна (SQLite WAL)</code>\n"
        f"🌐 Браузер: <code>{'Playwright готов' if is_playwright_available() else 'Playwright не установлен'}</code>\n"
        f"🧠 Мозг: Google Antigravity CLI (agy)",
        parse_mode="HTML"
    )

@router.message(Command("index"))
async def cmd_index(message: types.Message):
    wait_msg = await message.answer("🔄 <b>Индексирую материалы проекта в базу знаний SQLite FTS5...</b>", parse_mode="HTML")
    count = index_materials_directory(MATERIALS_DIR)
    await wait_msg.edit_text(
        f"✅ <b>База знаний FTS5 успешно обновлена!</b>\n\n"
        f"📚 Проиндексировано документов: <b>{count}</b>\n"
        f"Теперь Копирайтер и Главред мгновенно находят цитаты и цифры эксперта по запросам.",
        parse_mode="HTML"
    )

@router.message(Command("post"))
async def cmd_post(message: types.Message):
    args = message.text.replace("/post", "").strip()
    if not args:
        await message.answer(
            "✍️ <b>Написание поста живым голосом эксперта</b>\n\n"
            "Отправьте команду с темой:\n"
            "<code>/post Почему уходят мастера из салона</code>\n\n"
            "Или укажите номер/название стиля сразу:\n"
            "• <code>/post 1 [тема]</code> — 🎭 Драма и факап\n"
            "• <code>/post 2 [тема]</code> — 🔥 Провокация и мифбастер\n"
            "• <code>/post 3 [тема]</code> — 📋 Чек-лист и регламент\n"
            "• <code>/post 4 [тема]</code> — 📊 Аналитика и цифры\n"
            "• <code>/post 5 [тема]</code> — 🏛 Философия и манифест",
            parse_mode="HTML"
        )
        return

    # Check if first word is a style key (1..5 or name)
    parts = args.split(maxsplit=1)
    first_word = parts[0].lower()
    canonical_style = resolve_style_name(first_word)

    if canonical_style and len(parts) > 1:
        topic = parts[1].strip()
        style_title = STYLE_TITLES.get(canonical_style, canonical_style)
        wait_msg = await message.answer(
            f"⏳ ✍️ <b>Копирайтер</b> пишет лонгрид в стиле:\n<b>{style_title}</b>\n\nТема: <i>«{topic}»</i>...",
            parse_mode="HTML"
        )
        response, model_name = await run_agent_task(role="copywriter", user_prompt=topic, style=canonical_style)
        await send_formatted_response(message, wait_msg, response, model_name=model_name, reply_markup=get_post_feedback_keyboard(canonical_style))
    else:
        # Prompt provided without explicit style -> show interactive buttons
        PENDING_POST_TOPICS[message.from_user.id] = args
        await message.answer(
            f"✍️ <b>Тема лонгрида:</b> <i>«{args}»</i>\n\n"
            "Выберите стиль публикации:",
            reply_markup=get_styles_keyboard(),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("style:"))
async def callback_select_style(callback: types.CallbackQuery):
    await callback.answer()
    raw_style = callback.data.split(":", 1)[1]
    canonical_style = resolve_style_name(raw_style)
    style_title = STYLE_TITLES.get(canonical_style, canonical_style)
    
    topic = PENDING_POST_TOPICS.pop(callback.from_user.id, "")
    if not topic:
        topic = "Экспертный пост для Telegram-канала по методологии проекта"

    wait_msg = await callback.message.edit_text(
        f"⏳ ✍️ <b>Копирайтер</b> пишет лонгрид в стиле:\n<b>{style_title}</b>\n\nТема: <i>«{topic}»</i>...",
        parse_mode="HTML"
    )
    
    response, model_name = await run_agent_task(role="copywriter", user_prompt=topic, style=canonical_style)
    await send_formatted_response(callback.message, wait_msg, response, model_name=model_name, reply_markup=get_post_feedback_keyboard(canonical_style))

async def handle_carousel_generation(message: types.Message, query: str):
    """Handles both template rendering and dynamic AI generation."""
    clean_query = query.strip()
    
    matched_template = None
    for deck in AVAILABLE_DECKS:
        if clean_query.lower() == deck:
            matched_template = deck
            break
            
    if matched_template or not clean_query:
        target = matched_template or "voda"
        status_msg = await message.answer(f"🎨 Собираю шаблонную карусель <b>{target}</b>...", parse_mode="HTML")
        success, log, images, target_deck = run_build_karusel(target)
        model_name = "Template Builder"
    else:
        status_msg = await message.answer(
            f"🎨 Генерирую <b>новую карусель</b> на тему: <i>«{clean_query}»</i>...",
            parse_mode="HTML"
        )
        success, log, images, target_deck, model_name = await build_dynamic_carousel(clean_query)
    
    if not images:
        escaped_log = html.escape(log[:1000])
        await status_msg.edit_text(
            f"⚠️ Не удалось сгенерировать карточки:\n<pre><code>{escaped_log}</code></pre>",
            parse_mode="HTML"
        )
        return
        
    await status_msg.edit_text(
        f"✅ <b>Карусель готова!</b>\n"
        f"📌 Тема: <i>{target_deck}</i>\n"
        f"🖼 Слайдов: <b>{len(images)}</b> (1080x1350 PNG)\n"
        f"🧠 Модель: <i>{model_name}</i>\n\n"
        f"Отправляю карточки в чат...",
        parse_mode="HTML"
    )
    
    media_group = []
    for img_path in images[:10]:
        media_group.append(InputMediaPhoto(media=FSInputFile(str(img_path))))
        
    if media_group:
        await message.answer_media_group(media=media_group)

@router.message(Command("karusel"))
async def cmd_karusel(message: types.Message):
    args = message.text.replace("/karusel", "").strip()
    await handle_carousel_generation(message, args)

def determine_role(message: types.Message) -> tuple[str, str]:
    text = (message.text or message.caption or "").strip()
    thread_id = message.message_thread_id

    if text.startswith("/post") or text.startswith("/hooks") or text.startswith("/story"):
        return "copywriter", text.replace("/post", "").replace("/hooks", "").replace("/story", "").strip() or "Напиши пост в Telegram-канал живым голосом эксперта."
    elif text.startswith("/karusel"):
        return "designer", text.replace("/karusel", "").strip() or "Собери карусель."
    elif text.startswith("/check"):
        return "editor", text.replace("/check", "").strip() or "Проверь текст на факт-чек и голос."
    elif text.startswith("/sozvon"):
        return "analyst", text.replace("/sozvon", "").strip() or "Сделай разбор созвона по методологии проекта."
    elif text.startswith("/tech"):
        return "tech", text.replace("/tech", "").strip() or "Покажи статус инфраструктуры."

    if thread_id and thread_id in TOPIC_ROLES:
        return TOPIC_ROLES[thread_id], text

    return "copywriter", text

async def send_formatted_response(message: types.Message, wait_msg: types.Message | None, raw_response: str, model_name: str = "", reply_markup: InlineKeyboardMarkup | None = None):
    full_text = raw_response
    if model_name:
        full_text += f"\n\n---\n🧠 <i>Модель: {model_name}</i>"

    formatted_html = markdown_to_telegram_html(full_text)
    
    if len(formatted_html) > 4000:
        chunks = [formatted_html[i:i+3900] for i in range(0, len(formatted_html), 3900)]
    else:
        chunks = [formatted_html]

    try:
        if wait_msg:
            await wait_msg.edit_text(chunks[0], parse_mode="HTML", reply_markup=reply_markup if len(chunks) == 1 else None)
        else:
            await message.answer(chunks[0], parse_mode="HTML", reply_markup=reply_markup if len(chunks) == 1 else None)
            
        for chunk in chunks[1:]:
            await message.answer(chunk, parse_mode="HTML")
    except Exception:
        raw_chunks = [full_text[i:i+3900] for i in range(0, len(full_text), 3900)]
        if wait_msg:
            await wait_msg.edit_text(raw_chunks[0])
        else:
            await message.answer(raw_chunks[0])
        for chunk in raw_chunks[1:]:
            await message.answer(chunk)

@router.message(Command("insta"))
async def cmd_insta(message: types.Message):
    args = message.text.replace("/insta", "").strip()
    if not args:
        await message.answer(
            "🎬 <b>Отправьте ссылку на Instagram Reels или пост/карусель</b>\n\n"
            "Пример: <code>/insta https://www.instagram.com/p/C_...</code>\n"
            "• Для Reels: я скачаю видео, расшифрую речь эксперта и подготовлю пост для Telegram.\n"
            "• Для карусели: я скачаю карточки, перепишу живым голосом эксперта и сверстаю готовый альбом PNG!",
            parse_mode="HTML"
        )
        return
        
    wait_msg = await message.answer("📥 <b>Загружаю и анализирую публикацию из Instagram...</b>", parse_mode="HTML")
    response, model_name, images = await analyze_instagram_post(args)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)
    if images:
        media_group = [InputMediaPhoto(media=FSInputFile(str(img_path))) for img_path in images[:10]]
        if media_group:
            await message.answer_media_group(media=media_group)


@router.message(Command("spy"))
async def cmd_spy(message: types.Message):
    args = message.text.replace("/spy", "").strip()
    if not args:
        await message.answer(
            "🕵️‍♂️ <b>Пакетный шпионаж и аудит конкурентов</b>\n\n"
            "Пример: <code>/spy @alexyanovsky 40</code>\n"
            "Или: <code>/spy username</code>\n\n"
            "Что делает агент:\n"
            "• Парсит до 100 последних рилсов аккаунта\n"
            "• Вычисляет медианные просмотры и фильтрует виральные рилсы (x2.0+)\n"
            "• Извлекает хуки (первые 3 сек), структуры, офферы и триггеры\n"
            "• Сохраняет отчёт в <code>data/competitors/</code> и индексирует в базу знаний FTS5",
            parse_mode="HTML"
        )
        return

    parts = args.split()
    target_username = parts[0]
    limit = 40
    if len(parts) > 1 and parts[1].isdigit():
        limit = min(int(parts[1]), 100)

    wait_msg = await message.answer(
        f"🕵️‍♂️ <b>Шпионю за аккаунтом @{target_username.lstrip('@')}...</b>\n"
        f"Сбор до {limit} публикаций, расчет виральности (x2.0+), декомпозиция хуков и офферов.\n"
        "Пожалуйста, подождите...",
        parse_mode="HTML"
    )

    try:
        report, model_name, stats = await analyze_competitor_profile(target_username, max_count=limit)
        await send_formatted_response(message, wait_msg, report, model_name=model_name)
    except Exception as e:
        await wait_msg.edit_text(f"⚠️ Ошибка при анализе конкурента: {html.escape(str(e))}", parse_mode="HTML")

@router.message(Command("browser"))
async def cmd_browser(message: types.Message):
    args = message.text.replace("/browser", "").strip()
    if not args:
        await message.answer(
            "🌐 <b>Браузерный агент Playwright</b>\n\n"
            "Используется для взаимодействия с Tilda, GetCourse, веб-страницами и скриншотинга.\n\n"
            "Примеры команд:\n"
            "• <code>/browser https://ya.ru</code> — снять скриншот веб-страницы\n"
            "• <code>/browser status</code> — статус Playwright и директории браузера",
            parse_mode="HTML"
        )
        return

    if args.startswith("http://") or args.startswith("https://"):
        wait_msg = await message.answer(f"🌐 <b>Открываю браузер и загружаю</b> <code>{args}</code>...", parse_mode="HTML")
        success, shot_path, log = await take_page_screenshot(args)
        if success and shot_path and shot_path.exists():
            await message.answer_photo(
                photo=FSInputFile(str(shot_path)),
                caption=f"📸 <b>Скриншот страницы:</b>\n<code>{args}</code>\n\n{log}",
                parse_mode="HTML"
            )
            await wait_msg.delete()
        else:
            await wait_msg.edit_text(f"⚠️ Ошибка браузера:\n<code>{html.escape(log)}</code>", parse_mode="HTML")
    else:
        if args == "status":
            avail = is_playwright_available()
            has_session = SESSION_STATE_FILE.exists()
            await message.answer(
                f"🌐 <b>Статус браузерного агента:</b>\n\n"
                f"• Playwright установлен: <b>{'Да' if avail else 'Нет'}</b>\n"
                f"• Сессия авторизации (storage_state): <b>{'Сохранена' if has_session else 'Не настроена'}</b>\n"
                f"• Браузерный движок: Chromium Headless",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "🌐 <b>Укажите URL для скриншота:</b> <code>/browser https://...</code>",
                parse_mode="HTML"
            )

@router.message(Command("outreach"))
async def cmd_outreach(message: types.Message):
    args = message.text.replace("/outreach", "").strip()
    if not args or args == "stats":
        summary = get_outreach_summary()
        await message.answer(
            f"📢 <b>Агент Аутрича и PR-переговоров</b>\n\n"
            f"{summary}\n\n"
            "Команды управления:\n"
            "• <code>/outreach add @username [канал]</code> — добавить контакт блогера в базу\n"
            "• <code>/outreach send</code> — безопасная отправка питчей из очереди (userbot)\n"
            "• <code>/outreach stats</code> — статистика по лидам",
            parse_mode="HTML"
        )
        return

    if args.startswith("add"):
        parts = args.split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("⚠️ Укажите username: <code>/outreach add @username [канал]</code>", parse_mode="HTML")
            return
        username = parts[1]
        channel = parts[2] if len(parts) > 2 else ""
        ok, res = add_lead(username=username, channel_name=channel)
        await message.answer(f"{'✅' if ok else '⚠️'} {res}", parse_mode="HTML")
        return

    if args == "send" or args.startswith("send"):
        wait_msg = await message.answer("📢 <b>Запуск безопасной отправки питчей через userbot...</b>", parse_mode="HTML")
        sent_count, report = await run_outreach_dispatch(limit=5)
        await wait_msg.edit_text(
            f"📢 <b>Результат отправки аутрича:</b>\n\n{report}",
            parse_mode="HTML"
        )
        return

    await message.answer("Неизвестная подкоманда. Используйте <code>/outreach</code> для справки.", parse_mode="HTML")

async def handle_video_file_processing(message: types.Message, video_obj: types.Video, caption_prompt: str = ""):
    wait_msg = await message.answer(
        "🎬 <b>Начинаю монтаж видео...</b>\n"
        "• Скачивание файла из Telegram\n"
        "• Вырезание пауз и вздохов (<code>ffmpeg silenceremove</code>)\n"
        "• Распознавание речи с таймкодами (Whisper)\n"
        "• Стилизация вертикальных субтитров (9:16 ASS)\n"
        "• Финальный рендеринг MP4...",
        parse_mode="HTML"
    )

    temp_dir = MATERIALS_DIR / "temp_video"
    temp_dir.mkdir(parents=True, exist_ok=True)
    raw_video_path = temp_dir / f"raw_{message.message_id}_{video_obj.file_unique_id}.mp4"

    try:
        file_info = await message.bot.get_file(video_obj.file_id)
        await message.bot.download_file(file_info.file_path, destination=raw_video_path)

        success, final_video_path, log_msg = await process_video_montage(
            raw_video_path, cut_pauses=True, add_subs=True
        )

        if success and final_video_path and final_video_path.exists():
            await wait_msg.edit_text("📤 <b>Отправляю смонтированное видео...</b>", parse_mode="HTML")
            await message.answer_video(
                video=FSInputFile(str(final_video_path)),
                caption=f"🎬 <b>Видео успешно смонтировано!</b>\n\n{log_msg[:900]}",
                parse_mode="HTML"
            )
            await wait_msg.delete()
        else:
            await wait_msg.edit_text(
                f"⚠️ Не удалось смонтировать видео:\n<code>{html.escape(log_msg)}</code>",
                parse_mode="HTML"
            )
    except Exception as e:
        await wait_msg.edit_text(f"⚠️ Ошибка при обработке видео: {html.escape(str(e))}", parse_mode="HTML")
    finally:
        if raw_video_path.exists():
            try:
                raw_video_path.unlink()
            except Exception:
                pass

@router.message(Command("montage"))
async def cmd_montage(message: types.Message):
    video_obj = None
    if message.reply_to_message and message.reply_to_message.video:
        video_obj = message.reply_to_message.video
    elif message.video:
        video_obj = message.video

    if not video_obj:
        await message.answer(
            "🎬 <b>Автоматический монтаж видео через агента</b>\n\n"
            "Как использовать:\n"
            "1. Отправьте видео в чат с подписью <code>/montage</code>\n"
            "2. Или отправьте видео напрямую — бот предложит монтаж\n"
            "3. Или сделайте Reply на видео с командой <code>/montage</code>\n\n"
            "🔧 Конвейер:\n"
            "• Детекция тишины (<-32dB >0.35s) и склейка без пауз\n"
            "• Распознавание речи через Whisper с точными таймкодами\n"
            "• Стилизация 9:16 субтитров (ASS с жёлтым акцентом и обводкой)\n"
            "• Вжигание субтитров через ffmpeg в готовый MP4",
            parse_mode="HTML"
        )
        return

    await handle_video_file_processing(message, video_obj)

@router.message(F.video)
async def handle_video(message: types.Message):
    caption = (message.caption or "").lower()
    if "/montage" in caption or any(w in caption for w in ("монтаж", "нареж", "субтитр", "пауз")):
        await handle_video_file_processing(message, message.video, caption)
    else:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎬 Авто-монтаж (паузы + субтитры)",
                        callback_data=f"montage:{message.message_id}"
                    )
                ]
            ]
        )
        await message.answer(
            "📹 <b>Видео получено!</b>\nХотите выполнить авто-монтаж (вырезка пауз + стильные 9:16 субтитры)?",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("montage:"))
async def callback_montage(callback: types.CallbackQuery):
    await callback.answer("Запускаю монтаж...")
    target_msg = callback.message.reply_to_message or callback.message
    if target_msg and target_msg.video:
        await handle_video_file_processing(target_msg, target_msg.video)
    else:
        await callback.message.edit_text("⚠️ Видео не найдено. Отправьте видео снова с подписью /montage.")



@router.message(Command("learn"))
async def cmd_learn(message: types.Message):
    args = message.text.replace("/learn", "").strip()
    if not args:
        await message.answer(
            "🧠 <b>Обучение и кодификация правил эксперта (/learn)</b>\n\n"
            "Примеры:\n"
            "• <code>/learn Никогда не начинай пост со слов 'Привет, друзья'</code>\n"
            "• <code>/learn В темах про найм пиши 'тестовый день' вместо 'собеседование'</code>\n"
            "• <code>/learn Не используй восклицательные знаки в заголовках</code>\n\n"
            "Все выученные правила сразу внедряются в промпты Копирайтера и чек-лист Главреда!\n"
            "Посмотреть список: <code>/rules</code>",
            parse_mode="HTML"
        )
        return

    lower_args = args.lower()
    if any(w in lower_args for w in ("не используй", "не пиши", "запрети", "стоп-слово", "убрать")):
        category = "stop_word"
    elif any(w in lower_args for w in ("вместо", "заменяй", "пиши именно", "термин")):
        category = "preferred_term"
    else:
        category = "tone_rule"

    ok, res = add_rule(category, args, source="user_explicit")
    await message.answer(f"{'✅' if ok else '⚠️'} {res}\n\n<i>Правило активно и учитывается при генерации постов.</i>", parse_mode="HTML")

@router.message(Command("rules"))
async def cmd_rules(message: types.Message):
    rules = get_active_rules()
    if not rules:
        await message.answer(
            "🧠 <b>Выученные правила пока отсутствуют.</b>\n\n"
            "Чтобы добавить первое правило, используйте:\n"
            "<code>/learn [ваше правило или стоп-слово]</code>\n"
            "Или просто ответьте (Reply) на сгенерированный пост отредактированным текстом!",
            parse_mode="HTML"
        )
        return

    cat_icons = {
        "stop_word": "🚫 Стоп-слова",
        "preferred_term": "🎯 Предпочтения",
        "tone_rule": "⚖️ Тональность",
        "format_rule": "📐 Формат"
    }
    lines = [f"🧠 <b>Активные выученные правила эксперта ({len(rules)} шт.):</b>\n"]
    for r in rules:
        cat_title = cat_icons.get(r["category"], r["category"])
        lines.append(f"• <b>#{r['id']}</b> [{cat_title}]: «{r['rule_text']}»")

    lines.append("\nЧтобы отключить правило: <code>/delrule [ID]</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("delrule"))
async def cmd_delrule(message: types.Message):
    args = message.text.replace("/delrule", "").strip()
    if not args or not args.isdigit():
        await message.answer("⚠️ Укажите числовой ID правила: <code>/delrule 1</code>", parse_mode="HTML")
        return

    ok, res = delete_rule(int(args))
    await message.answer(f"{'✅' if ok else '⚠️'} {res}", parse_mode="HTML")

@router.message(Command("recipes"))
async def cmd_recipes(message: types.Message):
    recipes = get_available_recipes()
    if not recipes:
        await message.answer("📖 Рецепты пока не найдены в каталоге.", parse_mode="HTML")
        return

    lines = [f"📖 <b>Проверенные рецепты автоматизации ({len(recipes)} шт.):</b>\n"]
    for r in recipes:
        lines.append(f"• <code>/recipe {r['domain']}</code> — <b>{r['title']}</b>\n  <i>{r['description'][:90]}...</i>")

    lines.append("\nДля подробностей отправьте: <code>/recipe [домен]</code>\nДля выполнения в браузере: <code>/recipe run [домен]</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("recipe"))
async def cmd_recipe(message: types.Message):
    raw_args = message.text.replace("/recipe", "").strip()
    if not raw_args:
        await cmd_recipes(message)
        return

    parts = raw_args.split()
    if parts[0].lower() == "run":
        if len(parts) < 2:
            await message.answer("⚠️ Укажите домен рецепта: <code>/recipe run learn.amaliapro.biz</code>", parse_mode="HTML")
            return
        target_domain = parts[1]
        wait_msg = await message.answer(f"⚙️ <b>Запуск рецепта</b> <code>{target_domain}</code> в браузере Playwright...", parse_mode="HTML")
        ok, shot_path, log = await execute_recipe(target_domain)
        if ok and shot_path and shot_path.exists():
            await message.answer_photo(
                photo=FSInputFile(str(shot_path)),
                caption=log,
                parse_mode="HTML"
            )
            await wait_msg.delete()
        else:
            await wait_msg.edit_text(f"⚠️ Ошибка выполнения рецепта:\n<code>{html.escape(log)}</code>", parse_mode="HTML")
        return

    briefing = format_recipe_for_telegram(parts[0])
    await message.answer(briefing, parse_mode="HTML")

@router.message(Command("recon", "dossier"))
async def cmd_recon(message: types.Message):
    args = message.text.replace("/recon", "").replace("/dossier", "").strip()
    if not args:
        await message.answer(
            "🕵️‍♂️ <b>OSINT-разведка и сбор цифрового досье (/recon)</b>\n\n"
            "Пример: <code>/recon @amalia_beauty</code>\n"
            "Или: <code>/recon https://amaliapro.biz</code>\n\n"
            "Что делает агент:\n"
            "• Проверяет сетку аккаунтов (Username Pivoting по 8+ платформам: TG, VK, YT, Dzen, TikTok, VC)\n"
            "• Обходит мультиссылку (Taplink) и лендинг\n"
            "• Выявляет стек (Tilda, GetCourse, AmoCRM, пиксели, Метрику)\n"
            "• Находит прямые PR-контакты и юрлица (ИП/ИНН)\n"
            "• Автоматически передает контакты в базу аутрича",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer(
        f"🕵️‍♂️ <b>Провожу OSINT-разведку по {args}...</b>\n"
        "• Проверка сетки аккаунтов (Username Pivoting)\n"
        "• Анализ структуры лендинга и Taplink\n"
        "• Детекция стека и юридических реквизитов...",
        parse_mode="HTML"
    )

    try:
        report, raw_data = await build_dossier(args)
        await send_formatted_response(message, wait_msg, report)
    except Exception as e:
        await wait_msg.edit_text(f"⚠️ Ошибка при разведке: {html.escape(str(e))}", parse_mode="HTML")

@router.message(Command("magnet"))
async def cmd_magnet(message: types.Message):
    topic = message.text.replace("/magnet", "").strip()
    if not topic:
        await message.answer(
            "🧲 <b>Генератор продающих лид-магнитов (методология 2026)</b>\n\n"
            "Принцип Наты Анарбаевой: <i>Лид-магнит — это инструмент продажи, а не подарок.</i>\n"
            "Он вскрывает скрытую проблему и делает неизбежным обращение за основным продуктом.\n\n"
            "Отправьте команду с темой:\n"
            "<code>/magnet Осенний спад в салонах красоты</code>\n"
            "<code>/magnet Контентная воронка для эксперта</code>",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer(
        f"⏳ 🧲 <b>Копирайтер</b> проектирует продающий лид-магнит и кодовое слово для бота...\n\nТема: <i>«{topic}»</i>",
        parse_mode="HTML"
    )
    prompt = get_lead_magnet_prompt(topic)
    response, model_name = await run_agent_task(role="copywriter", user_prompt=prompt, style="provocation")
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(Command("blueprint"))
async def cmd_blueprint(message: types.Message):
    topic = message.text.replace("/blueprint", "").strip()
    if not topic:
        await message.answer(
            "🏛 <b>Генератор системных Blueprint (Miro-карта / архитектура системы)</b>\n\n"
            "Создает пошаговую инженерную блок-схему процесса в Markdown/ASCII со связками, фильтрами и конверсиями.\n\n"
            "Отправьте команду с темой:\n"
            "<code>/blueprint Контентная воронка на 300 заявок</code>\n"
            "<code>/blueprint Перезапись клиентской базы перед спадом</code>",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer(
        f"⏳ 🏛 <b>Смысловик</b> строит архитектурный Blueprint системы...\n\nТема: <i>«{topic}»</i>",
        parse_mode="HTML"
    )
    prompt = get_blueprint_prompt(topic)
    response, model_name = await run_agent_task(role="analyst", user_prompt=prompt)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.callback_query(F.data.startswith("magnet:"))
async def callback_make_magnet(callback: types.CallbackQuery):
    await callback.answer("Проектирую лид-магнит к посту...")
    orig_text = callback.message.text or callback.message.caption or ""
    first_lines = [l.strip() for l in orig_text.strip().split("\n") if l.strip()][:2]
    topic_summary = " ".join(first_lines)[:120] if first_lines else "Экспертный пост"
    
    wait_msg = await callback.message.reply(
        f"⏳ 🧲 Создаю продающий лид-магнит и кодовое слово к этому посту...\n\nТема: <i>{topic_summary}</i>",
        parse_mode="HTML"
    )
    prompt = get_lead_magnet_prompt(f"Лид-магнит к посту:\n{orig_text[:900]}")
    response, model_name = await run_agent_task(role="copywriter", user_prompt=prompt, style="provocation")
    await send_formatted_response(callback.message, wait_msg, response, model_name=model_name)

@router.callback_query(F.data.startswith("golden:"))
async def callback_golden(callback: types.CallbackQuery):
    style = callback.data.split(":", 1)[1]
    text = callback.message.text or callback.message.caption or ""
    if text:
        ok, msg = add_golden_example(style=style, content=text)
        await callback.answer("⭐️ Добавлено в золотые эталоны!", show_alert=True)
        await callback.message.reply(f"✅ {msg}")
    else:
        await callback.answer("Не удалось извлечь текст поста.", show_alert=True)

@router.callback_query(F.data == "learn_hint")
async def callback_learn_hint(callback: types.CallbackQuery):
    await callback.answer(
        "💡 Обучение бота:\n\n"
        "1. Отредактируйте текст поста и отправьте его в Reply — бот сам выделит отличия и выучит ваш Tone of Voice!\n"
        "2. Или напишите команду /learn [ваше правило].",
        show_alert=True
    )


@router.message(F.text)
async def handle_text(message: types.Message):
    # Check if user replied to bot message with edited text (Diff learning)
    if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_bot:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        edited_text = (message.text or "").strip()
        if len(replied_text) > 100 and len(edited_text) > 60 and not edited_text.startswith("/"):
            wait_msg = await message.answer("🧠 <b>Вижу вашу редактуру! Сравниваю версии и извлекаю правила Tone of Voice...</b>", parse_mode="HTML")
            report, rules = await analyze_diff_and_learn(replied_text, edited_text)
            await wait_msg.edit_text(report, parse_mode="HTML")
            return
    # Skip handled commands
    if any(message.text.startswith(c) for c in (
        "/setup_forum", "/start", "/help", "/status", "/karusel", 
        "/insta", "/adapt", "/remake", "/post", "/index", "/spy", "/montage", "/browser", "/outreach", "/learn", "/rules", "/delrule", "/recipes", "/recipe", "/recon", "/dossier"
    )):
        return

    # Check if user sent an Instagram link directly
    if is_instagram_url(message.text):
        insta_url = extract_instagram_url(message.text)
        if insta_url:
            wait_msg = await message.answer("📥 <b>Загружаю и анализирую публикацию из Instagram...</b>", parse_mode="HTML")
            response, model_name, images = await analyze_instagram_post(insta_url)
            await send_formatted_response(message, wait_msg, response, model_name=model_name)
            if images:
                media_group = [InputMediaPhoto(media=FSInputFile(str(img_path))) for img_path in images[:10]]
                if media_group:
                    await message.answer_media_group(media=media_group)
            return

    role, prompt = determine_role(message)

    # In designer topic, trigger carousel generation
    if role in ("designer", "karusel"):
        await handle_carousel_generation(message, prompt)
        return

    role_titles = {
        "copywriter": "✍️ Копирайтер",
        "designer": "🎨 Дизайнер",
        "editor": "🔍 Главред",
        "analyst": "🎙 Смысловик",
        "tech": "⚙️ Техспециалист"
    }
    display_title = role_titles.get(role, role)

    wait_msg = await message.answer(
        f"⏳ {display_title} готовит ответ...",
        parse_mode="HTML"
    )
    
    response, model_name = await run_agent_task(role=role, user_prompt=prompt)
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(F.document)
async def handle_document(message: types.Message):
    doc = message.document
    file_name = doc.file_name or "document"
    caption = message.caption or ""
    
    wait_msg = await message.answer(
        f"📥 Скачиваю и передаю в анализ <code>{file_name}</code>...",
        parse_mode="HTML"
    )
    
    save_path = MATERIALS_DIR / file_name
    file_info = await message.bot.get_file(doc.file_id)
    await message.bot.download_file(file_info.file_path, destination=save_path)
    
    extracted_text = extract_text_from_file(save_path)
    
    role, prompt = determine_role(message)
    if not caption:
        if "созвон" in file_name.lower() or "транскрипт" in file_name.lower():
            role = "analyst"
            prompt = f"Разбери транскрипт созвона {file_name} и выдели главные смыслы, задачи и дословные цитаты эксперта."
        else:
            prompt = f"Разбери документ {file_name}."
    
    response, model_name = await run_agent_task(
        role=role,
        user_prompt=prompt,
        attachment_text=extracted_text[:100000]
    )
    
    if role == "analyst":
        razbor_file = RAZBOR_DIR / f"Разбор_{Path(file_name).stem}.md"
        try:
            razbor_file.write_text(response, encoding="utf-8")
        except Exception:
            pass

    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(F.voice | F.audio)
async def handle_audio(message: types.Message):
    audio_obj = message.voice or message.audio
    wait_msg = await message.answer("🎙 <b>Смысловик</b> слушает и расшифровывает запись...", parse_mode="HTML")
    
    file_info = await message.bot.get_file(audio_obj.file_id)
    audio_bytes_io = io.BytesIO()
    await message.bot.download_file(file_info.file_path, destination=audio_bytes_io)
    audio_bytes = audio_bytes_io.getvalue()
    
    mime_type = getattr(audio_obj, "mime_type", "audio/ogg") or "audio/ogg"
    caption = message.caption or "Расшифруй аудио, сделай разбор созвона/голосового: выдели задачи, смыслы для контента и дословные цитаты эксперта."
    
    response, model_name = await run_agent_task(
        role="analyst",
        user_prompt=caption,
        audio_bytes=audio_bytes,
        mime_type=mime_type
    )
    
    await send_formatted_response(message, wait_msg, response, model_name=model_name)

@router.message(Command("adapt", "remake"))
async def cmd_adapt(message: types.Message):
    args = message.text.replace("/adapt", "").replace("/remake", "").strip()
    if not args:
        await message.answer(
            "🎨 <b>Отправьте текст или скриншот чужой карусели</b>\n\n"
            "Пример: <code>/adapt [текст карусели конкурента]</code>\n"
            "Или просто пришлите скриншоты в ветку <b>🎨 Дизайнер</b>.\n"
            "Дизайнер и Копирайтер возьмут хук и логику, перепишут в голос эксперта и сверстают готовые PNG-карточки 1080x1350!",
            parse_mode="HTML"
        )
        return

    wait_msg = await message.answer("🎨 <b>Адаптирую чужую карусель под голос эксперта и верстаю карточки...</b>", parse_mode="HTML")
    success, log, images, deck_name, model_name, explanation = await remake_competitor_carousel(source_text=args)

    if not images:
        await send_formatted_response(message, wait_msg, explanation or log, model_name=model_name)
        return

    await wait_msg.edit_text(
        f"✅ <b>Карусель успешно адаптирована под эксперта!</b>\n\n"
        f"{explanation}\n\n"
        f"🖼 Слайдов: <b>{len(images)}</b> (1080x1350 PNG)\n"
        f"🧠 Модель: <i>{model_name}</i>\n\n"
        f"Отправляю карточки в чат...",
        parse_mode="HTML"
    )

    media_group = [InputMediaPhoto(media=FSInputFile(str(img_path))) for img_path in images[:10]]
    if media_group:
        await message.answer_media_group(media=media_group)

@router.message(F.photo)
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    caption = (message.caption or "").strip()
    role, prompt = determine_role(message)

    # If sent to Designer or requested adaptation
    if role in ("designer", "karusel") or any(w in caption.lower() for w in ("адаптир", "переделай", "карусель", "эксперт")):
        wait_msg = await message.answer("🎨 <b>Дизайнер и Копирайтер</b> адаптируют чужую карусель под голос эксперта...", parse_mode="HTML")
        file_info = await message.bot.get_file(photo.file_id)
        img_bytes_io = io.BytesIO()
        await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
        image_bytes = img_bytes_io.getvalue()

        success, log, images, deck_name, model_name, explanation = await remake_competitor_carousel(
            source_text=caption or "Адаптируй эту карточку/карусель конкурента для блога эксперта.",
            image_bytes=image_bytes
        )

        if images:
            await wait_msg.edit_text(
                f"✅ <b>Готово! Карусель переписана живым голосом эксперта и сверстана:</b>\n\n"
                f"{explanation}\n\n"
                f"🖼 Слайдов: <b>{len(images)}</b> (1080x1350 PNG)\n"
                f"🧠 Модель: <i>{model_name}</i>",
                parse_mode="HTML"
            )
            media_group = [InputMediaPhoto(media=FSInputFile(str(img_path))) for img_path in images[:10]]
            if media_group:
                await message.answer_media_group(media=media_group)
            return

    # Standard photo analysis
    wait_msg = await message.answer("🖼 Анализирую изображение/скриншот...", parse_mode="HTML")
    file_info = await message.bot.get_file(photo.file_id)
    img_bytes_io = io.BytesIO()
    await message.bot.download_file(file_info.file_path, destination=img_bytes_io)
    image_bytes = img_bytes_io.getvalue()
    
    if not prompt:
        prompt = "Проанализируй этот скриншот/изображение с точки зрения контента, маркетинга и смыслов проекта."
    
    response, model_name = await run_agent_task(
        role=role,
        user_prompt=prompt,
        image_bytes=image_bytes,
        mime_type="image/jpeg"
    )
    
    await send_formatted_response(message, wait_msg, response, model_name=model_name)
