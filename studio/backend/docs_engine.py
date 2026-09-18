"""
Offline Documentation Engine: SQLite FTS5 Full-Text Search (Day 09)
===================================================================
Provides zero-latency, sub-15ms full-text documentation search directly
from local embedded markdown files via SQLite FTS5 virtual tables.

Guarantees:
1. Zero Network Egress: Operates 100% offline with zero external cloud calls.
2. BM25 Relevance: Uses SQLite native FTS5 ranking and snippet generation.
3. Zero Em-Dashes: The character \\u2014 is strictly prohibited.
"""

import os
import re
import sqlite3
from typing import List, Dict, Any, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db

try:
    from .paths import get_docs_dir
except ImportError:
    from paths import get_docs_dir

DOCS_DIR = get_docs_dir()


def init_docs_search_index(conn: Optional[sqlite3.Connection] = None, docs_dir: Optional[str] = None) -> int:
    """
    Initializes and refreshes the SQLite FTS5 virtual table for offline documentation.
    Scans all .md files in docs_dir and inserts section records.
    """
    target_dir = docs_dir or DOCS_DIR
    if not os.path.exists(target_dir):
        return 0

    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    try:
        cur = conn.cursor()
        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_index USING fts5(filename, section, content)")
        cur.execute("DELETE FROM docs_index")

        indexed_count = 0
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.endswith(".md"):
                    file_path = os.path.join(root, f)
                    try:
                        with open(file_path, "r", encoding="utf-8") as doc_file:
                            content = doc_file.read()

                        # Split document into logical sections by Markdown headers
                        sections = re.split(r'\n(?=#{1,3}\s+)', content)
                        rel_path = os.path.relpath(file_path, target_dir)

                        for sec in sections:
                            sec_lines = sec.strip().splitlines()
                            if not sec_lines:
                                continue
                            first_line = sec_lines[0]
                            sec_title = re.sub(r'^#{1,3}\s+', '', first_line).strip()
                            if not sec_title:
                                sec_title = f.replace(".md", "").replace("_", " ").title()

                            cur.execute(
                                "INSERT INTO docs_index (filename, section, content) VALUES (?, ?, ?)",
                                (rel_path, sec_title, sec)
                            )
                            indexed_count += 1
                    except Exception:
                        continue

        conn.commit()
        return indexed_count
    finally:
        if should_close:
            conn.close()


def search_docs_fts(query: str, limit: int = 10, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """
    Executes a sub-millisecond BM25 full-text search against the docs_index virtual table.
    Returns matched snippets with <mark> keyword highlights.
    """
    if not query or not query.strip():
        return []

    clean_q = re.sub(r'[^a-zA-Z0-9_\s]', ' ', query).strip()
    if not clean_q:
        return []

    # Format words for FTS5 prefix / token matching
    tokens = clean_q.split()
    fts_query = " ".join([f'"{t}"*' for t in tokens])

    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    try:
        cur = conn.cursor()
        # Verify docs_index exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_index'")
        if not cur.fetchone():
            init_docs_search_index(conn)

        cur.execute("""
        SELECT filename, section, snippet(docs_index, 2, '<mark>', '</mark>', '...', 25) AS snippet, rank
        FROM docs_index
        WHERE docs_index MATCH ?
        ORDER BY rank
        LIMIT ?
        """, (fts_query, limit))

        rows = cur.fetchall()
        results = []
        for r in rows:
            results.append({
                "filename": r[0],
                "section": r[1],
                "snippet": r[2],
                "relevance_rank": float(r[3])
            })
        return results
    except Exception as err:
        # Fallback to basic LIKE query if FTS5 syntax fails
        try:
            cur.execute("""
            SELECT filename, section, substr(content, 1, 160) AS snippet, 0.0 AS rank
            FROM docs_index
            WHERE content LIKE ? OR section LIKE ?
            LIMIT ?
            """, (f"%{clean_q}%", f"%{clean_q}%", limit))
            rows = cur.fetchall()
            return [
                {
                    "filename": r[0],
                    "section": r[1],
                    "snippet": r[2] + "...",
                    "relevance_rank": float(r[3])
                }
                for r in rows
            ]
        except Exception:
            return []
    finally:
        if should_close:
            conn.close()
