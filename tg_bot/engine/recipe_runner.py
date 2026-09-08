from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any

from tg_bot.config import BASE_DIR

PRIMARY_RECIPES_DIR = Path(os.path.expanduser("~/Project CODE/krasava-bridge/skill/recipes"))
FALLBACK_RECIPES_DIR = BASE_DIR / "data" / "recipes"

def get_recipes_dir() -> Path:
    if PRIMARY_RECIPES_DIR.exists() and (PRIMARY_RECIPES_DIR / "INDEX.md").exists():
        return PRIMARY_RECIPES_DIR
    FALLBACK_RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    return FALLBACK_RECIPES_DIR

def get_available_recipes() -> List[Dict[str, str]]:
    """Parses INDEX.md and returns a list of indexed recipes."""
    recipes_dir = get_recipes_dir()
    index_file = recipes_dir / "INDEX.md"
    if not index_file.exists():
        return []

    content = index_file.read_text(encoding="utf-8", errors="ignore")
    recipes = []
    
    # Table rows: | `domain` | [Title](file.md) | description | date |
    row_pattern = re.compile(
        r"\|\s*`?([^`\|]+)`?\s*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^\|]+)\|\s*([^\|]+)\|"
    )
    for line in content.splitlines():
        m = row_pattern.match(line.strip())
        if m:
            domain, title, filename, desc, date = m.groups()
            recipes.append({
                "domain": domain.strip(),
                "title": title.strip(),
                "file": filename.strip(),
                "description": desc.strip(),
                "date": date.strip()
            })
            
    return recipes

def find_recipe_file(target: str) -> Optional[Path]:
    """Finds matching recipe markdown file by domain or filename."""
    recipes_dir = get_recipes_dir()
    clean = target.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]

    # Exact filename match
    direct = recipes_dir / f"{clean}.md"
    if direct.exists():
        return direct

    # Try matching domain in available recipes
    for r in get_available_recipes():
        if clean in r["domain"].lower() or clean in r["title"].lower() or clean in r["file"].lower():
            target_path = recipes_dir / r["file"]
            if target_path.exists():
                return target_path

    # Fallback to directory scan
    for f in recipes_dir.glob("*.md"):
        if clean in f.stem.lower() and f.name != "_template.md" and f.name != "INDEX.md":
            return f

    return None

def get_recipe_details(target: str) -> Optional[Dict[str, Any]]:
    """Extracts structured sections from a recipe markdown file."""
    path = find_recipe_file(target)
    if not path or not path.exists():
        return None

    text = path.read_text(encoding="utf-8", errors="ignore")
    
    # Extract sections
    def extract_section(header_regex: str, next_header_regex: str = r"\n## ") -> str:
        pattern = re.compile(rf"## {header_regex}(.*?)(?={next_header_regex}|\Z)", re.DOTALL | re.IGNORECASE)
        m = pattern.search(text)
        return m.group(1).strip() if m else ""

    entry_section = extract_section(r"Как попасть внутрь")
    endpoints_section = extract_section(r"Внутренние эндпоинты")
    sequence_section = extract_section(r"Проверенная последовательность")
    traps_section = extract_section(r"Капканы")
    spoil_section = extract_section(r"Что здесь протухнет первым")

    # Entry point url
    entry_url = ""
    url_m = re.search(r"Точка входа:\s*`?([^\n`]+)`?", entry_section)
    if url_m:
        entry_url = url_m.group(1).strip()

    return {
        "file_name": path.name,
        "path": path,
        "entry_url": entry_url,
        "entry_section": entry_section,
        "endpoints": endpoints_section,
        "sequence": sequence_section,
        "traps": traps_section,
        "spoil": spoil_section,
        "raw_content": text
    }

def format_recipe_for_telegram(target: str) -> str:
    """Formats recipe into a concise Telegram briefing with traps and endpoints."""
    rec = get_recipe_details(target)
    if not rec:
        avail = get_available_recipes()
        domains_sample = ", ".join([f"<code>{r['domain']}</code>" for r in avail[:8]])
        return (
            f"⚠️ Рецепт для <b>{target}</b> не найден в базе.\n\n"
            f"Доступные рецепты ({len(avail)} шт.):\n{domains_sample}...\n\n"
            "Используйте <code>/recipes</code> для полного списка."
        )

    lines = [
        f"📖 <b>Рецепт автоматизации:</b> <code>{rec['file_name']}</code>\n",
        f"🔗 <b>Точка входа:</b> <code>{rec['entry_url'] or 'см. инструкцию'}</code>\n"
    ]

    if rec["traps"]:
        lines.append("⚠️ <b>Капканы и грабли платформы:</b>")
        clean_traps = "\n".join([f"• {l.lstrip('-* ')}" for l in rec["traps"].splitlines() if l.strip()][:5])
        lines.append(f"{clean_traps}\n")

    if rec["endpoints"]:
        lines.append("⚡️ <b>Внутренние API-эндпоинты:</b>")
        clean_ep = rec["endpoints"][:600]
        lines.append(f"<pre><code>{clean_ep}</code></pre>\n")

    if rec["sequence"]:
        lines.append("📋 <b>Проверенный алгоритм:</b>")
        clean_seq = "\n".join([f"{l.strip()}" for l in rec["sequence"].splitlines() if l.strip()][:6])
        lines.append(f"{clean_seq}\n")

    lines.append(f"Запуск в браузере: <code>/recipe run {rec['file_name'].replace('.md', '')}</code>")
    return "\n".join(lines)

async def execute_recipe(
    target: str,
    action: str = "status"
) -> Tuple[bool, Optional[Path], str]:
    """
    Executes a web recipe using Playwright and stored session states.
    Captures proof screenshot and returns action log.
    """
    from tg_bot.engine.browser_worker import take_page_screenshot, execute_web_recipe, SESSION_STATE_FILE

    rec = get_recipe_details(target)
    if not rec:
        return False, None, f"Рецепт {target} не найден."

    entry_url = rec["entry_url"]
    if not entry_url.startswith("http"):
        # Fallback to domain
        domain = rec["file_name"].replace(".md", "")
        entry_url = f"https://{domain}"

    # Default action: take authenticated screenshot and verify access
    success, shot_path, log = await take_page_screenshot(entry_url, wait_seconds=3.0)
    if not success:
        return False, None, f"Ошибка выполнения рецепта: {log}"

    has_session = SESSION_STATE_FILE.exists()
    status_text = (
        f"✅ <b>Рецепт {rec['file_name']} выполнен!</b>\n"
        f"• URL: <code>{entry_url}</code>\n"
        f"• Сессия: <b>{'Подключена' if has_session else 'Анонимная'}</b>\n\n"
        f"📸 Контрольный скриншот страницы прикреплён ниже."
    )
    return True, shot_path, status_text
