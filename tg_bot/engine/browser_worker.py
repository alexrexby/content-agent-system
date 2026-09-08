from __future__ import annotations

import os
import json
import asyncio
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from tg_bot.config import BASE_DIR

BROWSER_DATA_DIR = BASE_DIR / "data" / "browser"
SESSION_STATE_FILE = BROWSER_DATA_DIR / "storage_state.json"
SCREENSHOTS_DIR = BROWSER_DATA_DIR / "screenshots"

def is_playwright_available() -> bool:
    try:
        import playwright
        return True
    except ImportError:
        return False

async def take_page_screenshot(
    url: str,
    wait_seconds: float = 2.0,
    full_page: bool = True
) -> Tuple[bool, Optional[Path], str]:
    """Navigates to URL, captures high-res screenshot and saves to disk."""
    if not is_playwright_available():
        return False, None, "Playwright не установлен в окружении."

    from playwright.async_api import async_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    screenshot_path = SCREENSHOTS_DIR / "latest_page.png"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            context_kwargs = {"viewport": {"width": 1280, "height": 800}}
            if SESSION_STATE_FILE.exists():
                context_kwargs["storage_state"] = str(SESSION_STATE_FILE)

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            await page.screenshot(path=str(screenshot_path), full_page=full_page)
            await browser.close()

            return True, screenshot_path, f"Скриншот страницы {url} успешно сохранен."
    except Exception as e:
        return False, None, f"Ошибка браузерной автоматизации: {e}"

async def execute_web_recipe(
    url: str,
    recipe_actions: List[Dict[str, Any]]
) -> Tuple[bool, Optional[Path], str]:
    """
    Executes a sequence of actions on a web platform (Tilda, GetCourse, etc.)
    Actions list: [
        {"action": "click", "selector": ".popup-btn"},
        {"action": "fill", "selector": "#input-text", "text": "Текст акции"},
        {"action": "wait", "seconds": 1.5}
    ]
    Captures proof screenshot after actions finish.
    """
    if not is_playwright_available():
        return False, None, "Playwright не установлен."

    from playwright.async_api import async_playwright

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    proof_path = SCREENSHOTS_DIR / "recipe_result.png"

    log_messages = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            context_kwargs = {"viewport": {"width": 1280, "height": 800}}
            if SESSION_STATE_FILE.exists():
                context_kwargs["storage_state"] = str(SESSION_STATE_FILE)

            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()

            await page.goto(url, timeout=35000, wait_until="domcontentloaded")
            log_messages.append(f"Переход на {url}")

            for idx, act in enumerate(recipe_actions, 1):
                action_type = act.get("action")
                selector = act.get("selector", "")
                text = act.get("text", "")
                seconds = act.get("seconds", 1.0)

                if action_type == "click" and selector:
                    await page.click(selector, timeout=10000)
                    log_messages.append(f"Шаг {idx}: Клик по {selector}")
                elif action_type == "fill" and selector:
                    await page.fill(selector, text, timeout=10000)
                    log_messages.append(f"Шаг {idx}: Ввод текста в {selector}")
                elif action_type == "wait":
                    await asyncio.sleep(seconds)
                    log_messages.append(f"Шаг {idx}: Пауза {seconds}s")

            # Save state if session was updated
            await context.storage_state(path=str(SESSION_STATE_FILE))
            await page.screenshot(path=str(proof_path), full_page=False)
            await browser.close()

            return True, proof_path, "\n".join(log_messages)
    except Exception as e:
        return False, None, f"Ошибка выполнения сценария: {e}"
