import os
import io
import html
import asyncio
from pathlib import Path
from aiogram import Router, F, types
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, InputMediaPhoto

from tg_bot.config import MATERIALS_DIR, RAZBOR_DIR
from tg_bot.engine.agent_runner import run_agent_task
from tg_bot.engine.file_extractor import extract_text_from_file
from tg_bot.engine.carousel_builder import run_build_karusel, build_dynamic_carousel, remake_competitor_carousel, AVAILABLE_DECKS
from tg_bot.engine.formatter import markdown_to_telegram_html
from tg_bot.engine.insta_monitor import is_instagram_url, extract_instagram_url, analyze_instagram_post


router = Router()


TOPIC_ROLES = {}

FORUM_TOPICS = [
    {
        "name": "✍️ Копирайтер",
        "role": "copywriter",
        "welcome": "✍️ <b>Копирайтер команды</b>\n\nПишите задачи на посты в Telegram-канал, серии Stories, прогревы к вебинарам и продуктам или хуки по ВИСП для Reels.\nЯ упакую смыслы живым языком эксперта с точными образами и рублеными добивками."
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
        "welcome": "⚙️ <b>Технический специалист</b>\n\nОтвечаю за инфраструктуру: сервер, работу бота, Antigravity CLI (agy), лендинги, GetCourse и деплой.\nЗадавайте вопросы по технической части или отправляйте команды <code>/status</code>, <code>/deploy</code>."
    }
]

HELP_TEXT = """
👋 <b>Команда специалистов Content Agent System в сборе!</b>

👥 <b>Специалисты в команде:</b>
• ✍️ <b>Копирайтер</b> — посты в канал, сценарии Stories, хуки ВИСП и прогревы
• 🎨 <b>Дизайнер</b> — генерация каруселей 1080x1350 (PNG), визуал
• 🔍 <b>Главред</b> — факт-чекинг, вычитка стоп-слов, контроль голоса
• 🎙 <b>Смысловик</b> — расшифровка аудио/созвонов, извлечение задач и цитат
• ⚙️ <b>Техспециалист</b> — инфраструктура, сервер, бот, GetCourse

📌 <b>Как создать ветки в группе:</b>
1. Включите <b>«Темы» (Topics)</b> в настройках вашей группы Telegram.
2. Отправьте в группу команду <code>/setup_forum</code> — бот автоматически создаст все 5 веток специалистов с инструкциями!

📌 <b>Команды для любого чата:</b>
• <code>/setup_forum</code> — создание веток специалистов в группе
• <code>/post [тема]</code> — задача для Копирайтера
• <code>/karusel [тема]</code> — задача для Дизайнера (сборка PNG)
• <code>/check [текст]</code> — задача для Главреда (аудит)
• <code>/sozvon [файл/аудио]</code> — задача для Смысловика (разбор)
• <code>/insta [ссылка на Reels]</code> — скачать, расшифровать и разобрать рилс
• <code>/status</code> — статус бота, материалов и системы
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
        f"📁 Файлов в materials/: <code>{mat_count}</code> (транскрипты и выгрузки канала)\n"
        f"📝 Разборов в 02 Разборы созвонов: <code>{razbor_count}</code>\n"
        f"🧠 Мозг: Google Antigravity CLI (agy)",
        parse_mode="HTML"
    )


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

async def send_formatted_response(message: types.Message, wait_msg: types.Message | None, raw_response: str, model_name: str = ""):
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
            await wait_msg.edit_text(chunks[0], parse_mode="HTML")
        else:
            await message.answer(chunks[0], parse_mode="HTML")
            
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

@router.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith("/setup_forum") or message.text.startswith("/start") or message.text.startswith("/help") or message.text.startswith("/status") or message.text.startswith("/karusel") or message.text.startswith("/insta") or message.text.startswith("/adapt") or message.text.startswith("/remake"):
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

