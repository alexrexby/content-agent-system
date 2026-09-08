from __future__ import annotations

import re
import asyncio
import aiohttp
from typing import Tuple, Optional, List, Dict, Any
from bs4 import BeautifulSoup

from tg_bot.engine.outreach_worker import add_lead, extract_telegram_contacts

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

PLATFORMS_MAP = {
    "telegram": "https://t.me/{user}",
    "vk": "https://vk.com/{user}",
    "youtube": "https://www.youtube.com/@{user}",
    "dzen": "https://dzen.ru/{user}",
    "tiktok": "https://www.tiktok.com/@{user}",
    "vc": "https://vc.ru/u/{user}",
    "rutube": "https://rutube.ru/channel/{user}",
    "taplink": "https://taplink.cc/{user}"
}

async def check_platform_presence(session: aiohttp.ClientSession, platform: str, url_template: str, username: str) -> Tuple[str, bool, str]:
    """Checks whether an account exists on a platform via async request."""
    url = url_template.format(user=username)
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=7), allow_redirects=True) as resp:
            status = resp.status
            if status == 200:
                body = await resp.text(errors="ignore")
                # Specific platform checks to eliminate false positives
                if platform == "telegram" and ("If you have <strong>Telegram</strong>" in body or "tgme_page" in body):
                    if "t.me/" in url and not "tgme_page_action" in body and "View in Telegram" not in body:
                        return platform, False, url
                    return platform, True, url
                elif platform == "dzen" and ("Канал не найден" in body or "404" in body):
                    return platform, False, url
                elif platform == "vk" and ("Страница удалена" in body or "Страница заблокирована" in body):
                    return platform, False, url
                elif platform == "tiktok" and "Couldn't find this account" in body:
                    return platform, False, url
                elif platform == "taplink" and ("Профиль не найден" in body or "404" in body):
                    return platform, False, url
                return platform, True, url
            return platform, False, url
    except Exception:
        return platform, False, url

async def enumerate_usernames(username: str) -> Dict[str, Dict[str, Any]]:
    """Checks username presence across 8 social and media platforms."""
    clean_user = username.lstrip("@").strip().split("/")[0]
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"}
    
    results = {}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            check_platform_presence(session, plat, tpl, clean_user)
            for plat, tpl in PLATFORMS_MAP.items()
        ]
        completed = await asyncio.gather(*tasks, return_exceptions=True)
        for res in completed:
            if isinstance(res, tuple):
                plat, exists, url = res
                results[plat] = {"exists": exists, "url": url}
    return results

def extract_legal_entities(text: str) -> Dict[str, str]:
    """Extracts INN, OGRN, and legal business name from text."""
    entities = {}
    
    inn_match = re.search(r"\bИНН\b[:\s]*(\d{12}|\d{10})", text, re.IGNORECASE)
    if inn_match:
        entities["inn"] = inn_match.group(1)

    ogrn_match = re.search(r"\bОГРН(?:ИП)?\b[:\s]*(\d{15}|\d{13})", text, re.IGNORECASE)
    if ogrn_match:
        entities["ogrn"] = ogrn_match.group(1)

    biz_match = re.search(
        r"((?:ИП|Индивидуальный предприниматель)\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2}|ООО\s+[\"«][^\"»]+[\"»])",
        text
    )
    if biz_match:
        entities["legal_name"] = biz_match.group(1).strip()

    return entities

def detect_tech_stack(html: str) -> List[str]:
    """Profiles web technology stack from page source code."""
    stack = []
    lower_html = html.lower()

    # CMS / Site builders
    if "tilda.ws" in lower_html or "t-records" in lower_html:
        stack.append("Tilda")
    if "wp-content" in lower_html or "wordpress" in lower_html:
        stack.append("WordPress")
    if "taplink.cc" in lower_html:
        stack.append("Taplink")

    # LMS / Course platforms
    if "getcourse" in lower_html or "gc-main" in lower_html:
        stack.append("GetCourse")
    if "chatium" in lower_html:
        stack.append("Chatium")

    # CRM
    if "amocrm" in lower_html or "amo-forms" in lower_html:
        stack.append("AmoCRM")
    if "bitrix" in lower_html or "b24-" in lower_html:
        stack.append("Bitrix24")

    # Payments
    if "prodamus" in lower_html:
        stack.append("Prodamus")
    if "robokassa" in lower_html:
        stack.append("Robokassa")
    if "cloudpayments" in lower_html:
        stack.append("CloudPayments")

    # Analytics / Pixels
    ym_match = re.search(r"ym\((\d{6,10})", html)
    if ym_match:
        stack.append(f"Яндекс Метрика (ID: {ym_match.group(1)})")
    
    vk_match = re.search(r"(VK-RTRG-\d+-[a-zA-Z0-9]+)", html)
    if vk_match:
        stack.append(f"VK Pixel ({vk_match.group(1)})")

    return list(dict.fromkeys(stack))

async def crawl_landing_or_taplink(url: str) -> Dict[str, Any]:
    """Crawls a target landing or taplink to extract contacts, stack, and legal details."""
    target_url = url if url.startswith("http") else f"https://{url}"
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"}

    contacts = {
        "telegrams": [],
        "whatsapps": [],
        "emails": [],
        "phones": []
    }
    stack = []
    legal = {}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(target_url, timeout=aiohttp.ClientTimeout(total=12), allow_redirects=True) as resp:
                if resp.status != 200:
                    return {"url": target_url, "error": f"HTTP {resp.status}"}

                html = await resp.text(errors="ignore")
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(separator=" ")

                # Extract emails
                found_emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
                contacts["emails"] = list(dict.fromkeys([e for e in found_emails if not e.endswith(".png") and not e.endswith(".jpg")]))[:4]

                # Extract WhatsApp
                wa_matches = re.findall(r"(?:wa\.me|api\.whatsapp\.com/send\?phone=)(\d{10,14})", html)
                contacts["whatsapps"] = list(dict.fromkeys(wa_matches))[:3]

                # Extract Telegrams
                tg_contacts = extract_telegram_contacts(html + " " + text)
                contacts["telegrams"] = tg_contacts[:5]

                # Extract tech stack
                stack = detect_tech_stack(html)

                # Extract legal details
                legal = extract_legal_entities(text)

                return {
                    "url": str(resp.url),
                    "title": soup.title.string.strip() if soup.title and soup.title.string else "",
                    "contacts": contacts,
                    "stack": stack,
                    "legal": legal
                }
    except Exception as e:
        return {"url": target_url, "error": str(e)}

async def build_dossier(target: str) -> Tuple[str, Dict[str, Any]]:
    """
    Executes full OSINT reconnaissance inspired by SpiderFoot:
    1. Determines whether target is username or URL.
    2. Runs username pivoting across 8 platforms.
    3. Crawls primary landing/Taplink for contacts, stack and legal entities.
    4. Auto-feeds discovered PR contacts into outreach database.
    Returns formatted Telegram HTML summary and raw intelligence dictionary.
    """
    raw_target = target.strip()
    is_url = raw_target.startswith("http://") or raw_target.startswith("https://") or ("." in raw_target and "/" in raw_target)
    
    clean_user = raw_target.lstrip("@").split("/")[0] if not is_url else ""
    primary_url = raw_target if is_url else f"https://taplink.cc/{clean_user}"

    # 1. Enumerate usernames if clean_user is available
    socials = {}
    if clean_user:
        socials = await enumerate_usernames(clean_user)

    # 2. Crawl landing or taplink
    web_data = await crawl_landing_or_taplink(primary_url)

    # 3. Auto-feed contacts to outreach leads
    discovered_telegrams = web_data.get("contacts", {}).get("telegrams", [])
    added_leads = []
    for tg_user in discovered_telegrams:
        ok, msg = add_lead(username=tg_user, channel_name=f"Recon: {clean_user or primary_url}", source="recon_spider")
        if ok:
            added_leads.append(tg_user)

    # 4. Format structured report
    lines = [
        f"🕵️‍♂️ <b>Цифровое OSINT-досье:</b> <code>{raw_target}</code>\n"
    ]

    # Social Presence
    if socials:
        active_socials = [f"• <b>{plat.capitalize()}</b>: {info['url']}" for plat, info in socials.items() if info["exists"]]
        missing_socials = [plat.capitalize() for plat, info in socials.items() if not info["exists"]]
        lines.append("🌐 <b>Сетка присутствия (Username Pivoting):</b>")
        if active_socials:
            lines.extend(active_socials)
        else:
            lines.append("• Прямых совпадений по никнейму не обнаружено.")
        if missing_socials:
            lines.append(f"<i>Свободные площадки (точки роста): {', '.join(missing_socials)}</i>")
        lines.append("")

    # Web & Funnel Stack
    if web_data and not web_data.get("error"):
        lines.append("🛒 <b>Воронка и стек технологий:</b>")
        lines.append(f"• Точка входа: <code>{web_data.get('url')}</code>")
        if web_data.get("title"):
            lines.append(f"• Заголовок: <i>«{web_data.get('title')[:80]}»</i>")
        stack_list = web_data.get("stack", [])
        if stack_list:
            lines.append(f"• Стек сервисов: <b>{', '.join(stack_list)}</b>")
        else:
            lines.append("• Стек: стандартный веб")
        lines.append("")

    # Contacts & Outreach
    contacts = web_data.get("contacts", {})
    all_contacts_found = False
    lines.append("📬 <b>Контакты для рекламы и PR:</b>")
    if contacts.get("telegrams"):
        all_contacts_found = True
        lines.append(f"• Telegram: <b>{', '.join(['@' + u for u in contacts['telegrams']])}</b>")
    if contacts.get("emails"):
        all_contacts_found = True
        lines.append(f"• Email: {', '.join(contacts['emails'])}")
    if contacts.get("whatsapps"):
        all_contacts_found = True
        lines.append(f"• WhatsApp: {', '.join(contacts['whatsapps'])}")
    if not all_contacts_found:
        lines.append("• Прямые контакты в коде лендинга не найдены.")

    if added_leads:
        lines.append(f"💡 <i>Лиды автоматически добавлены в очередь аутрича ({len(added_leads)} шт.). Запуск: /outreach send</i>")
    lines.append("")

    # Corporate & Legal
    legal = web_data.get("legal", {})
    if legal:
        lines.append("🏛 <b>Юридические реквизиты:</b>")
        if legal.get("legal_name"):
            lines.append(f"• Юрлицо: <b>{legal.get('legal_name')}</b>")
        if legal.get("inn"):
            lines.append(f"• ИНН: <code>{legal.get('inn')}</code>")
        if legal.get("ogrn"):
            lines.append(f"• ОГРН: <code>{legal.get('ogrn')}</code>")

    full_report = "\n".join(lines)
    raw_data = {
        "target": raw_target,
        "socials": socials,
        "web": web_data,
        "added_leads": added_leads
    }
    return full_report, raw_data
