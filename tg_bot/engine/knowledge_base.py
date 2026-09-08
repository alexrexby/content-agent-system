from __future__ import annotations
import os
import re
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

from tg_bot.config import BASE_DIR, MATERIALS_DIR

DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "knowledge.db"

STOP_WORDS_RU = {
    "как", "что", "для", "это", "под", "при", "все", "или", "без", "над",
    "про", "тот", "кто", "она", "они", "оно", "эти", "был", "быть", "есть",
    "так", "уже", "еще", "ещё", "где", "куда", "чем", "нет", "даже", "если"
}

def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_knowledge_db():
    """Initializes SQLite tables and FTS5 index for full-text search."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT,
                source TEXT,
                file_hash TEXT UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                title,
                content,
                tags,
                source,
                tokenize = 'unicode61'
            );
        """)
        conn.commit()

def stem_russian(word: str) -> str:
    """Lightweight morphological pseudo-stemmer for Russian FTS prefix search."""
    w = word.lower().strip()
    if len(w) > 5:
        return w[:len(w)-2] + "*"
    elif len(w) > 3:
        return w[:len(w)-1] + "*"
    return w + "*"

def clean_fts_query(query: str) -> str:
    """Sanitizes and stems user query for Russian SQLite FTS5 matching."""
    cleaned = re.sub(r'[^\w\sа-яА-ЯёЁ]', ' ', query)
    raw_tokens = [t.strip().lower() for t in cleaned.split() if len(t.strip()) > 2]
    
    # Filter common stop words if meaningful tokens exist
    filtered = [t for t in raw_tokens if t not in STOP_WORDS_RU]
    tokens_to_use = filtered if filtered else raw_tokens
    
    if not tokens_to_use:
        return ""
    
    stemmed_terms = [stem_russian(t) for t in tokens_to_use[:8]]
    return " OR ".join(stemmed_terms)

def add_document(title: str, content: str, tags: str = "", source: str = "", file_hash: Optional[str] = None) -> int:
    """Adds a document to both raw table and FTS5 index."""
    init_knowledge_db()
    with get_connection() as conn:
        if file_hash:
            cur = conn.execute("SELECT id FROM documents WHERE file_hash = ?", (file_hash,))
            existing = cur.fetchone()
            if existing:
                return existing["id"]

        cur = conn.execute(
            "INSERT INTO documents (title, content, tags, source, file_hash) VALUES (?, ?, ?, ?, ?)",
            (title, content, tags, source, file_hash)
        )
        doc_id = cur.lastrowid
        conn.execute(
            "INSERT INTO knowledge_fts (rowid, title, content, tags, source) VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, content, tags, source)
        )
        conn.commit()
        return doc_id

def search_knowledge(query: str, limit: int = 4) -> List[Dict[str, Any]]:
    """Performs full-text search with ranking and snippet extraction."""
    init_knowledge_db()
    fts_query = clean_fts_query(query)
    if not fts_query:
        return []

    results = []
    with get_connection() as conn:
        try:
            sql = """
                SELECT 
                    rowid as id,
                    title,
                    source,
                    tags,
                    snippet(knowledge_fts, 1, '<b>', '</b>', '...', 25) as snippet,
                    content
                FROM knowledge_fts
                WHERE knowledge_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = conn.execute(sql, (fts_query, limit)).fetchall()
            for r in rows:
                results.append({
                    "id": r["id"],
                    "title": r["title"],
                    "source": r["source"],
                    "tags": r["tags"],
                    "snippet": r["snippet"],
                    "content": r["content"][:1200]
                })
        except sqlite3.OperationalError:
            pass

        # Fallback to substring match if FTS yielded no results
        if not results:
            tokens = [t.strip() for t in query.split() if len(t.strip()) > 3]
            if tokens:
                main_word = tokens[0]
                sql_fallback = """
                    SELECT id, title, source, tags, content
                    FROM documents
                    WHERE content LIKE ? OR title LIKE ?
                    LIMIT ?
                """
                param = f"%{main_word[:5]}%"
                rows = conn.execute(sql_fallback, (param, param, limit)).fetchall()
                for r in rows:
                    results.append({
                        "id": r["id"],
                        "title": r["title"],
                        "source": r["source"],
                        "tags": r["tags"],
                        "snippet": r["content"][:200],
                        "content": r["content"][:1200]
                    })

    return results

def get_relevant_context(query: str, max_chars: int = 2500) -> str:
    """Formats top relevant search excerpts into a prompt-ready context block."""
    items = search_knowledge(query, limit=3)
    if not items:
        return ""

    context_lines = ["\n[БАЗА ЗНАНИЙ И ФАКТЫ ЭКСПЕРТА (FTS5 Поиск)]"]
    current_len = 0
    for idx, item in enumerate(items, 1):
        excerpt = (
            f"\n--- Источник {idx}: {item['title']} ({item['source'] or 'материалы'}) ---\n"
            f"{item['content']}\n"
        )
        if current_len + len(excerpt) > max_chars:
            break
        context_lines.append(excerpt)
        current_len += len(excerpt)

    return "\n".join(context_lines)

def index_materials_directory(dir_path: Path = MATERIALS_DIR) -> int:
    """Scans and indexes text documents from materials directory."""
    if not dir_path.exists():
        dir_path.mkdir(parents=True, exist_ok=True)
        return 0

    indexed_count = 0
    import hashlib

    for ext in ("*.txt", "*.md"):
        for p in dir_path.rglob(ext):
            if p.name.startswith("."):
                continue
            try:
                content = p.read_text(encoding="utf-8", errors="ignore").strip()
                if not content:
                    continue
                file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                add_document(
                    title=p.name,
                    content=content,
                    tags="materials",
                    source=str(p.relative_to(dir_path.parent)),
                    file_hash=file_hash
                )
                indexed_count += 1
            except Exception:
                continue

    return indexed_count

if __name__ == "__main__":
    init_knowledge_db()
    count = index_materials_directory()
    print(f"База знаний инициализирована. Проиндексировано документов: {count}")
