# План реализации: Система самообучения, Рецепты задач и OSINT-разведка (SpiderFoot)

Модернизация [content-agent-system](file:///Users/a123456/Desktop/content-agent-system) на основе трех системных блоков, обсужденных с владельцем:
1. **Система самообучения (Self-Improvement Loop)**: постоянная калибровка голоса эксперта через `diff`-анализ ручных правок, команду `/learn` и золотой датасет эталонных постов.
2. **Система рецептов (Recipe Runner)**: интеграция проверенной базы регламентов `~/Project CODE/krasava-bridge/skill/recipes/` (GetCourse, Tilda, VK, YouTube, Директ) для детерминированного решения веб-задач без лишних шагов.
3. **OSINT-разведка в стиле SpiderFoot (Recon Spider)**: сбор полного цифрового досье по никнейму или сайту (сетка аккаунтов, стек воронки, Taplink, реквизиты ИП/ИНН, прямые PR-контакты с авто-подачей в аутрич).

---

## 1. Архитектурные компоненты

### Компонент 1: `learning_engine.py` (Самообучение и память правок)
- **Хранилище:** локальная база данных `data/learning.db` в режиме SQLite WAL.
- **Таблицы:**
  - `learned_rules`: `id`, `category` (`stop_word`, `preferred_term`, `tone_rule`, `format_rule`), `rule_text`, `reason`, `source` (`user_explicit`, `diff_auto`), `created_at`, `is_active`.
  - `golden_examples`: `id`, `style`, `topic`, `content`, `engagement_metric`, `created_at`.
  - `draft_history`: `message_id`, `chat_id`, `role`, `style`, `prompt`, `draft_text`, `created_at`.
- **Логика работы:**
  - `add_rule()` / `delete_rule()` / `get_active_rules()`
  - `get_learned_prompt_context()`: форматирование выученных ограничений и предпочтений для подмешивания в системные промпты Копирайтера и Главреда.
  - `analyze_diff_and_learn()`: LLM-анализ различий между драфтом бота и отредактированным текстом эксперта. Извлекает:
    - какие обороты/слова были вырезаны (добавляются в `stop_words`),
    - какие термины/фразы добавлены (добавляются в `preferred_terms`).
  - `add_golden_example()` / `get_golden_examples()`: банк эталонных постов для Few-Shot инъекции.

### Компонент 2: `recipe_runner.py` (Система рецептов задач)
- **Источник:** боевой каталог рецептов `~/Project CODE/krasava-bridge/skill/recipes/` (с локальным fallback в `data/recipes/`).
- **Логика работы:**
  - `get_available_recipes()`: чтение `INDEX.md`, извлечение доменов, описаний, ключевых капканов и дат проверки.
  - `get_recipe_details(domain)`: парсинг регламента по стандарту `_template.md` (вход, внутренние эндпоинты, последовательность, капканы).
  - `execute_recipe(domain, action, params)`: запуск последовательности через `browser_worker.py` (Playwright с сохраненными куками) с контролем капканов и снятием подтверждающего скриншота.

### Компонент 3: `recon_spider.py` (OSINT-разведка а-ля SpiderFoot)
- **Подсистемы:**
  1. `enumerate_usernames(username)`: асинхронный опрос 8+ платформ (Telegram, YouTube, VK, Дзен, TikTok, VC.ru, Rutube, TenChat) через легковесные HEAD/GET-запросы.
  2. `crawl_landing_or_taplink(url)`: переход по мультиссылке из bio, парсинг дерева ссылок, поиск Telegram PR-контактов (`@username`, `t.me/...`), WhatsApp (`wa.me`), почт, телефонов.
  3. `detect_tech_stack(html)`: определение CMS (Tilda, WordPress), обучающей платформы (GetCourse, Prodamus), CRM (AmoCRM, Bitrix24), ID Яндекс Метрики и пикселей VK.
  4. `extract_corporate_entities(html)`: извлечение реквизитов из `/offer`, `/terms`, `/privacy` (ИП, ООО, ИНН).
  5. `build_dossier(target)`: компиляция единого цифрового досье и автоматическая передача найденных PR-контактов в `outreach_worker.py`.

---

## 2. Интеграция в Telegram-бот (`router.py`)

- Новые команды:
  - `/learn [инструкция]` — прямое сохранение правила ToV или стоп-слова.
  - `/rules` — просмотр всех активных выученных правил.
  - `/delrule [id]` — удаление правила.
  - `/recipes` — список всех доступных рецептов из `INDEX.md`.
  - `/recipe [домен]` — детальный регламент и капканы работы с сайтом/сервисом.
  - `/recon [username или url]` — формирование полного цифрового досье конкурента / блогера.
- Интерактивность:
  - Под каждым сгенерированным постом кнопки: `[⭐️ В эталоны]` и `[✍️ Запомнить мою редактуру]`.
  - Ответ (Reply) на сообщение бота с отредактированным текстом запускает `diff-анализ` и предложение сохранить выученные правила.

---

## 3. План верификации

- **Unit-тесты:**
  - `learning_engine`: добавление правила, проверка инъекции в промпт, добавление золотого эталона.
  - `recipe_runner`: парсинг `INDEX.md`, извлечение капканов и эндпоинтов из `learn.amaliapro.biz.md` и `vkvideo.ru.md`.
  - `recon_spider`: проверка регулярных выражений ИНН/реквизитов, детекция стека (Tilda/GetCourse), парсинг контактов.
- **Интеграционные тесты:**
  - Проверка сквозного импорта `tg_bot.main` и `tg_bot.handlers.router`.
  - Синхронизация с базой аутрича `data/outreach.db`.
