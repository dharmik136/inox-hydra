"""
Offline Documentation Engine: SQLite FTS5 Full-Text Search (Day 09)
===================================================================
Provides zero-latency, sub-15ms full-text documentation search directly
from local embedded markdown files via SQLite FTS5 virtual tables.

Guarantees:
1. Zero Network Egress: Operates 100% offline with zero external cloud calls.
2. BM25 Relevance: Uses SQLite native FTS5 ranking and snippet generation.
3. Zero Em-Dashes: Strict enforcement across all indexed text and docstrings.
"""

import logging
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger("studio.docs")

try:
    from .database import get_db
except ImportError:
    from database import get_db

try:
    from .paths import get_docs_dir
except ImportError:
    from paths import get_docs_dir

DOCS_DIR = get_docs_dir()
MAX_DOCS_INDEX_FILE_SIZE = 2 * 1024 * 1024  # 2MB per document file
MAX_DOCS_SEARCH_QUERY_LENGTH = 300


def init_docs_search_index(conn: Optional[sqlite3.Connection] = None, docs_dir: Optional[str] = None) -> int:
    """
    Initializes and refreshes the SQLite FTS5 virtual table for offline documentation.
    Scans all .md files in docs_dir and inserts section records with em-dash sanitization.
    """
    target_dir = docs_dir or DOCS_DIR
    if not os.path.exists(target_dir):
        return 0

    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True

    em_dash = chr(0x2014)
    en_dash = chr(0x2013)

    try:
        cur = conn.cursor()

        # A table left over from an older schema is rebuilt rather than reused.
        #
        # CREATE VIRTUAL TABLE IF NOT EXISTS does nothing when a table of that
        # name exists, whatever its columns are. With a stale three-vs-four
        # column table the DELETE below still succeeded and every INSERT then
        # raised a column count error, which the per-file handler swallowed.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_index'")
        if cur.fetchone():
            try:
                existing = {row[1] for row in cur.execute("PRAGMA table_info(docs_index)").fetchall()}
            except Exception:
                existing = set()
            if not {"filename", "section", "content"}.issubset(existing):
                cur.execute("DROP TABLE IF EXISTS docs_index")

        cur.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_index USING fts5(filename, section, content)")
        cur.execute("DELETE FROM docs_index")

        indexed_count = 0
        # Counted so a total failure can be told apart from a docs directory
        # that genuinely has nothing in it.
        markdown_seen = 0
        failed_files = []
        for root, _, files in os.walk(target_dir):
            for f in files:
                if f.endswith(".md"):
                    markdown_seen += 1
                    file_path = os.path.join(root, f)
                    try:
                        # Defensive check: skip unusually huge files
                        if os.path.getsize(file_path) > MAX_DOCS_INDEX_FILE_SIZE:
                            continue

                        with open(file_path, "r", encoding="utf-8", errors="replace") as doc_file:
                            content = doc_file.read(MAX_DOCS_INDEX_FILE_SIZE)

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

                            # Sanitize em-dashes dynamically before indexing
                            clean_title = sec_title.replace(em_dash, " -- ").replace(en_dash, "-")
                            clean_sec = sec.replace(em_dash, " -- ").replace(en_dash, "-")

                            cur.execute(
                                "INSERT INTO docs_index (filename, section, content) VALUES (?, ?, ?)",
                                (rel_path, clean_title, clean_sec)
                            )
                            indexed_count += 1
                    except Exception as file_error:
                        # Recorded rather than merely skipped. This handler sits
                        # inside the outer guard, so it used to eat the very
                        # failures the rollback below exists to catch.
                        failed_files.append((f, str(file_error)))
                        continue

        # Refuse to commit an empty index when there were files to index.
        #
        # DELETE has already run at this point, so committing zero rows
        # replaces a working index with nothing, returns 0 and raises no
        # exception. Every search then returns nothing, for good, and the only
        # signal is that the docs tab looks broken.
        if indexed_count == 0 and markdown_seen > 0:
            conn.rollback()
            logger.error(
                "Refusing to publish an empty documentation index: %d markdown "
                "files were found and none could be indexed. First failures: %s",
                markdown_seen, failed_files[:3],
            )
            return 0

        if failed_files:
            logger.warning(
                "Documentation index built with %d of %d files failing: %s",
                len(failed_files), markdown_seen, failed_files[:3],
            )

        conn.commit()
        return indexed_count
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass


def search_docs_fts(query: Any, limit: int = 10, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """
    Executes a sub-millisecond BM25 full-text search against the docs_index virtual table.
    Returns matched snippets with <mark> keyword highlights.
    """
    if query is None or not isinstance(query, str):
        return []

    clean_q = re.sub(r'[^a-zA-Z0-9_\s]', ' ', query).strip()[:MAX_DOCS_SEARCH_QUERY_LENGTH]
    if not clean_q:
        return []

    try:
        bounded_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        bounded_limit = 10

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
        """, (fts_query, bounded_limit))

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
    except Exception:
        # Fallback to basic LIKE query if FTS5 syntax fails
        try:
            cur.execute("""
            SELECT filename, section, substr(content, 1, 160) AS snippet, 0.0 AS rank
            FROM docs_index
            WHERE content LIKE ? OR section LIKE ?
            LIMIT ?
            """, (f"%{clean_q}%", f"%{clean_q}%", bounded_limit))
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
        if should_close and conn:
            try:
                conn.close()
            except Exception:
                pass
