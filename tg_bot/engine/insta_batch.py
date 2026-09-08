from __future__ import annotations

import os
import re
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import instaloader
from tg_bot.config import BASE_DIR, MATERIALS_DIR
from tg_bot.engine.agent_runner import run_agent_task
from tg_bot.engine.knowledge_base import add_document

SPY_DIR = MATERIALS_DIR / "Instagram" / "Competitors"

def clean_username(raw: str) -> str:
    """Extracts pure username from @username or full Instagram profile URL."""
    cleaned = raw.strip()
    match = re.search(r"(?:https?://(?:www\.)?instagram\.com/)?@?([a-zA-Z0-9_\.]+)/?", cleaned)
    if match:
        return match.group(1).rstrip("/")
    return cleaned.replace("@", "").strip()

def fetch_competitor_posts_sync(username: str, max_count: int = 50) -> List[Dict[str, Any]]:
    """Synchronously fetches metadata for the latest posts of an Instagram profile."""
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        post_metadata_txt_pattern=""
    )
    
    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        raise RuntimeError(f"Не удалось загрузить профиль @{username}: {e}")

    posts_data = []
    count = 0
    
    for post in profile.get_posts():
        if count >= max_count:
            break
            
        is_video = post.is_video
        views = getattr(post, "video_view_count", 0) or 0
        likes = post.likes or 0
        comments = post.comments or 0
        caption = post.caption or ""
        shortcode = post.shortcode
        url = f"https://www.instagram.com/p/{shortcode}/"
        date_str = post.date.strftime("%Y-%m-%d") if post.date else ""

        posts_data.append({
            "shortcode": shortcode,
            "url": url,
            "is_video": is_video,
            "views": views,
            "likes": likes,
            "comments": comments,
            "score": views if is_video and views > 0 else (likes * 3 + comments * 5),
            "caption": caption[:1500],
            "date": date_str
        })
        count += 1

    return posts_data

def filter_viral_reels(posts: List[Dict[str, Any]]) -> Tuple[float, List[Dict[str, Any]]]:
    """Finds viral posts by calculating median engagement and selecting > 2.0x median."""
    if not posts:
        return 0.0, []

    scores = [p["score"] for p in posts]
    sorted_scores = sorted(scores)
    median_score = sorted_scores[len(sorted_scores) // 2]
    
    # Threshold is 2x median, or at least 1
    threshold = max(median_score * 2.0, 1.0)
    
    viral = [p for p in posts if p["score"] >= threshold]
    # Sort viral by score descending
    viral = sorted(viral, key=lambda p: p["score"], reverse=True)
    
    # If no posts crossed 2x median, take top 20%
    if not viral:
        cutoff = max(1, len(posts) // 5)
        viral = sorted(posts, key=lambda p: p["score"], reverse=True)[:cutoff]

    return median_score, viral

async def analyze_competitor_profile(raw_target: str, max_count: int = 40) -> Tuple[str, str, Dict[str, Any]]:
    """
    Scrapes profile posts, filters viral content, and runs a single-pass LLM analysis
    on hooks, offers, and sales patterns. Returns (summary_report, model_name, raw_data).
    """
    username = clean_username(raw_target)
    if not username:
        return "⚠️ Не удалось определить имя пользователя Instagram.", "Instagram Spy", {}

    SPY_DIR.mkdir(parents=True, exist_ok=True)

    try:
        posts = await asyncio.to_thread(fetch_competitor_posts_sync, username, max_count)
    except Exception as e:
        return f"⚠️ Ошибка сбора данных по профилю @{username}:\n<code>{e}</code>", "Instagram Spy", {}

    if not posts:
        return f"⚠️ В профиле @{username} не найдено публикаций.", "Instagram Spy", {}

    median_score, viral_posts = filter_viral_reels(posts)
    
    # Prepare compact condensed representation of top viral posts
    condensed_items = []
    for idx, p in enumerate(viral_posts[:15], 1):
        condensed_items.append(
            f"--- Рилс #{idx} ({p['url']}) | Охват/Лайки: {p['score']} ---\n"
            f"Текст подписи:\n{p['caption'][:600]}\n"
        )

    analysis_payload = "\n".join(condensed_items)
    
    prompt = f"""
Ты — Ведущий Маркетолог и Аналитик Контента.
Мы спарсили {len(posts)} последних публикаций конкурента @{username}.
Вот выборка ТОП-{len(viral_posts[:15])} самых вирусных публикаций (с охватом в 2-5 раз выше среднего):

{analysis_payload}

Сделай глубокую декомпозицию и подготовь контент-отчет:

1. 🎯 ТОП-5 ХУКОВ И ТЕМ (почему именно эти рилсы залетели: психологический триггер, интрига, боль ЦА).
2. 💰 РАЗБОР ВОРОНКИ И ОФФЕРОВ (куда они уводят зрителей: кодовое слово в директ, лид-магнит, бот, ссылка в шапке? Что именно продают?).
3. 💬 АНТИПАТТЕРНЫ (какие ошибки или инфостиль есть у конкурента, которые нам повторять нельзя).
4. 🚀 3 ГОТОВЫЕ ИДЕИ ДЛЯ НАШЕГО ЭКСПЕРТА (адаптируй лучшие связки под Tone of Voice и принципы нашего проекта — предложи 3 сильных заголовка и краткую суть для наших постов/каруселей).
"""

    report, model_name = await run_agent_task(
        role="analyst",
        user_prompt=prompt
    )

    # Save to file for archive
    save_path = SPY_DIR / f"Spy_{username}.md"
    try:
        full_doc = (
            f"# Анализ конкурента @{username}\n\n"
            f"- Всего проанализировано постов: {len(posts)}\n"
            f"- Вирусных публикаций отобрано: {len(viral_posts)}\n"
            f"- Медианный показатель вовлеченности: {int(median_score)}\n\n"
            f"## Отчет аналитика:\n\n{report}"
        )
        save_path.write_text(full_doc, encoding="utf-8")
        
        # Index in SQLite FTS5 database so copywriter can query it!
        add_document(
            title=f"Анализ рилсов и офферов @{username}",
            content=report,
            tags=f"конкурент, {username}, рилсы, офферы, хуки",
            source=str(save_path.name)
        )
    except Exception:
        pass

    summary = (
        f"🕵️‍♂️ <b>Анализ конкурента @{username} завершен!</b>\n\n"
        f"📊 Спарсено постов: <b>{len(posts)}</b>\n"
        f"🔥 Выделено вирусных: <b>{len(viral_posts[:15])}</b> (выше медианы)\n"
        f"💾 Сохранено в базу знаний FTS5.\n\n"
        f"{report}"
    )

    return summary, model_name, {"total": len(posts), "viral": len(viral_posts), "posts": viral_posts}
