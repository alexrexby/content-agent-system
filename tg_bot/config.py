from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file from project root or tg_bot directory
if (BASE_DIR / ".env").exists():
    load_dotenv(BASE_DIR / ".env")
elif (BASE_DIR / "tg_bot" / ".env").exists():
    load_dotenv(BASE_DIR / "tg_bot" / ".env")
else:
    load_dotenv()

# Bot credentials & LLM keys (configured via environment variables)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
POLZA_API_KEY = os.getenv("POLZA_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Base URL & Model configuration
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.polza.ai/api/v1")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "anthropic/claude-sonnet-4.5")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Directory mappings
MATERIALS_DIR = BASE_DIR / "materials"
if not MATERIALS_DIR.exists() and (BASE_DIR / "01 Материалы").exists():
    MATERIALS_DIR = BASE_DIR / "01 Материалы"

RAZBOR_DIR = BASE_DIR / "analysis"
if not RAZBOR_DIR.exists() and (BASE_DIR / "02 Разборы созвонов").exists():
    RAZBOR_DIR = BASE_DIR / "02 Разборы созвонов"

CONTENT_DIR = BASE_DIR / "content"
if not CONTENT_DIR.exists() and (BASE_DIR / "05 Контент").exists():
    CONTENT_DIR = BASE_DIR / "05 Контент"

KARUSEL_DIR = BASE_DIR / "carousel_generator"
if not KARUSEL_DIR.exists() and (BASE_DIR / "06 Карусели" / "Генератор").exists():
    KARUSEL_DIR = BASE_DIR / "06 Карусели" / "Генератор"

AGENTS_MD_PATH = BASE_DIR / "AGENTS.md"
