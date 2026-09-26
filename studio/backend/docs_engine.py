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

import hashlib
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


# The signature of the corpus the live index was built from.
#
# init_docs_search_index is imported into app.py and never called from it, and
# the only other call sites are inside search_docs_fts, guarded by "the table
# does not exist". So the index was built exactly once, on the first search ever
# run against a given database, and never again. Editing a playbook, adding a
# document or deleting one changed nothing that search could see, for the life
# of that database.
#
# paths.py states the opposite in as many words: a source checkout is
# authoritative "so editing docs/ during development takes effect immediately
# without a repackaging step". That was true for opening a document, which reads
# from disk, and false for finding one.
#
# It matters more now that every hit is a destination. A stale index can return
# a section of a file that has since been renamed, and the reader follows it to
# a 404 rather than to a slightly old snippet.
_index_signature = None


# The stat of the corpus the last content hash was taken from, so an unchanged
# directory costs 38 stat calls instead of reading 450KB.
_stat_gate = None


def corpus_stat(docs_dir: Optional[str] = None):
    """
    Path, size and modification time of every markdown file. No content.

    This is the gate, not the answer. It is here to say "nothing has been
    touched", which is true on almost every call, and it costs about a
    millisecond because it opens nothing.
    """
    target_dir = docs_dir or DOCS_DIR
    if not os.path.isdir(target_dir):
        return ()
    entries = []
    for root, _, files in os.walk(target_dir):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            rel = os.path.relpath(path, target_dir).replace(os.sep, "/")
            entries.append((rel, stat.st_size, stat.st_mtime_ns))
    return tuple(sorted(entries))


def corpus_signature(docs_dir: Optional[str] = None):
    """
    A fingerprint of the documentation directory, taken from its contents.

    The first version used path, size and modification time alone, which is the
    cheap answer and not a correct one: Windows stamps a write with the system
    clock tick, so two same length writes inside one tick share an mtime and the
    fingerprint does not move. So the content decides, with one sha256 over
    every markdown file.

    The content hash costs 22ms for 38 files and 450KB, almost all of it per
    file open overhead. Run on every search that was not free: an existing
    budget guard for the FTS5 query, which allows 50ms, started reporting 104ms.
    Making a search four times slower to notice an edit nobody made is a bad
    trade, and one nobody would have measured without that guard.

    So it is gated. An unchanged stat means an unchanged corpus and the cached
    hash stands; a changed stat is what triggers the read. The residual hole is
    narrow and worth naming: an edit that preserves byte length AND lands in the
    same filesystem timestamp tick as the previous check is not seen. A person
    saving a file never does that, because the tick has passed; only a program
    rewriting the same file within milliseconds can, which is what the test for
    this had to do on purpose.
    """
    global _stat_gate
    target_dir = docs_dir or DOCS_DIR
    if not os.path.isdir(target_dir):
        return ""

    stat = corpus_stat(target_dir)
    cached = _stat_gate
    if cached is not None and cached[0] == os.path.abspath(target_dir) and cached[1] == stat:
        return cached[2]

    digest = hashlib.sha256()
    for rel, _size, _mtime in stat:
        path = os.path.join(target_dir, *rel.split("/"))
        digest.update(rel.encode("utf-8", "replace"))
        try:
            with open(path, "rb") as handle:
                digest.update(handle.read(MAX_DOCS_INDEX_FILE_SIZE))
        except OSError:
            # A file that cannot be read is part of the state too: it
            # reappearing is a change, so it is stamped rather than skipped.
            digest.update(b"<unreadable>")

    hashed = digest.hexdigest()
    _stat_gate = (os.path.abspath(target_dir), stat, hashed)
    return hashed


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
                        # Stored with forward slashes on every platform. relpath
                        # returns backslashes on Windows, which the interface was
                        # showing to the reader verbatim, and a document id derived
                        # from it would differ between operating systems.
                        rel_path = os.path.relpath(file_path, target_dir).replace(os.sep, "/")

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
        # Recorded here and nowhere else, so a rebuild that rolled back above
        # leaves the previous signature in place and the next search tries
        # again rather than trusting an index that was never written.
        global _index_signature
        _index_signature = (os.path.abspath(target_dir), corpus_signature(target_dir))
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
        # Rebuild when the table is missing, and also when the documents have
        # changed since it was built. The second half is the one that was
        # absent: without it the index is a snapshot of whatever the corpus
        # looked like the first time anyone searched.
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='docs_index'")
        if not cur.fetchone():
            init_docs_search_index(conn)
        elif _index_signature != (os.path.abspath(DOCS_DIR), corpus_signature()):
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
                "filename": str(r[0]).replace("\\", "/"),
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
                    "filename": str(r[0]).replace("\\", "/"),
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


# ---------------------------------------------------------------------------
# The document registry
# ---------------------------------------------------------------------------
# The search index covers every markdown file under the docs directory, 38 of
# them, and the product exposed 7. So a search could match a section of
# DATA_ARCHITECTURE.md, return a real snippet, and have nowhere to send the
# reader: the hit existed, the document had no route, and the interface simply
# did not offer it. Four fifths of what the search can find was unreachable by
# construction, which is also why the result list was not clickable.
#
# This gives every indexed file an id. Resolution is a dictionary lookup against
# a table built by walking the directory here, so an incoming request never
# contributes a path segment and traversal is not something that has to be
# defended a second time.

DOC_EXCERPT_LENGTH = 220

_FOLDER_LABELS = {
    "": "Reference",
    "modules": "Module Manuals",
}


def document_slug(rel_path):
    """
    A stable id for a documentation file, derived from its path.

    Lowercased, with the separators and the extension folded away, so
    modules/05_ANALYTICS.md becomes modules-05_analytics. The character class is
    the one the API sanitizer permits, so a slug survives a round trip through a
    URL unchanged rather than being silently rewritten into a 404.
    """
    stem = str(rel_path or "").replace("\\", "/")
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    slug = re.sub(r"[^a-z0-9_]+", "-", stem.lower())
    return re.sub(r"-{2,}", "-", slug).strip("-")


def is_rule(line):
    """A horizontal rule: three or more of one rule character, and nothing else."""
    bare = str(line or "").replace(" ", "").replace("\t", "")
    return len(bare) >= 3 and bare in (
        "-" * len(bare), "*" * len(bare), "_" * len(bare),
    )


def _folder_label(rel_path):
    folder = os.path.dirname(rel_path)
    if folder in _FOLDER_LABELS:
        return _FOLDER_LABELS[folder]
    return folder.replace("_", " ").replace("/", " / ").title()


def _describe_document(path, rel_path):
    """
    Title, opening line and length, read from the file itself.

    Nothing here is generated. The title is the document's own first level one
    heading and falls back to its filename; the excerpt is its own first line of
    prose. A document with neither gets an empty excerpt rather than a sentence
    the studio made up about it.
    """
    em_dash = chr(0x2014)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read(MAX_DOCS_INDEX_FILE_SIZE)
    except OSError:
        return None

    title = None
    excerpt = ""
    # A list item is a fallback rather than a first choice. Two files open on a
    # checklist, and taking that line verbatim put "- [x] Configured ..." in the
    # sidebar, marker and all. A prose line is what an opening line means; the
    # item is only used when the document has no paragraph at all, and then its
    # marker comes off.
    fallback = ""
    in_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if title is None and stripped.startswith("# "):
            title = stripped[2:].strip()
            continue
        if excerpt or stripped.startswith("#") or stripped.startswith(">"):
            continue
        if stripped.startswith("|") or is_rule(stripped):
            continue
        item = re.match(r"^(?:[-*+]|\d{1,9}[.)])\s+(.*)$", stripped)
        if item:
            if not fallback:
                fallback = re.sub(r"^\[[ xX]\]\s*", "", item.group(1)).strip()
            continue
        excerpt = stripped

    if not excerpt:
        excerpt = fallback
    if title is None:
        title = os.path.basename(rel_path)[:-3].replace("_", " ").title()

    return {
        "id": document_slug(rel_path),
        "path": rel_path,
        "title": title.replace(em_dash, " -- "),
        "excerpt": excerpt[:DOC_EXCERPT_LENGTH].replace(em_dash, " -- "),
        "folder": _folder_label(rel_path),
        "section": section_for_path(rel_path),
        "words": len(re.findall(r"[^\s]+", content)),
    }


def document_library(docs_dir=None):
    """
    Every markdown file the search index covers, in a form the interface can
    open. Sorted by folder then path so the listing is stable between calls.
    """
    target_dir = docs_dir or DOCS_DIR
    if not os.path.isdir(target_dir):
        return []

    entries = []
    seen = set()
    for root, _, files in os.walk(target_dir):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, target_dir).replace(os.sep, "/")
            described = _describe_document(path, rel_path)
            if described is None:
                continue
            # Two paths cannot collapse onto one id without one of them becoming
            # unreachable, which is the bug this table exists to remove.
            if described["id"] in seen:
                described["id"] = document_slug(rel_path + "-" + str(len(entries)))
            seen.add(described["id"])
            entries.append(described)

    entries.sort(key=lambda entry: (entry["folder"], entry["path"]))
    return entries


# ---------------------------------------------------------------------------
# The help sections
# ---------------------------------------------------------------------------
# Documents were grouped by the folder they sit in, which produced "Reference",
# "Prudent Handoff" and "Builder Feedback" as the top level of a help centre.
# Those are facts about the filesystem. Somebody looking for how to connect a
# model, or what leaves this machine, has no reason to guess that the answer is
# filed under a directory named after a handoff process.
#
# So the grouping is by what a reader came to do. It is a written table rather
# than keyword matching on titles, for the same reason template provenance is
# recorded rather than inferred: a guess that is right most of the time files
# the rest somewhere wrong and nothing says which. Every indexed file must
# appear here exactly once, and tests/test_docs_library.py fails on a document
# that is missing, listed twice, or listed but absent from disk. A new file is
# a deliberate decision about where it belongs, not a silent fall through into
# whichever bucket happened to be last.

HELP_SECTIONS = [
    {
        "id": "start",
        "title": "Start here",
        "blurb": "Installing it, the first launch, and what the studio does before anything is configured.",
        "paths": [
            "GETTING_STARTED.md",
            "FIRST_RUN.md",
            "README.md",
        ],
    },
    {
        "id": "using",
        "title": "Using the studio",
        "blurb": "The six module manuals, the master operational guide, and the content strategy they assume.",
        "paths": [
            "modules/01_STUDIO_AND_EDITOR.md",
            "modules/02_SCHEDULE_AND_QUEUE.md",
            "modules/03_INBOUND_CRM.md",
            "modules/04_VIRAL_SWIPE_FILE.md",
            "modules/05_ANALYTICS.md",
            "modules/06_AI_COMMAND.md",
            "ENTERPRISE_USAGE.md",
            "strategy_playbook.md",
        ],
    },
    {
        "id": "ai",
        "title": "Bringing your own AI",
        "blurb": "Choosing a provider, what runs locally with no network at all, and what a key is used for.",
        "paths": [
            "AI_ENGINE.md",
            "BYO_AI_ARCHITECTURE.md",
        ],
    },
    {
        "id": "data",
        "title": "Your data and privacy",
        "blurb": "What the studio captures, where it is stored, and what does or does not leave this machine.",
        "paths": [
            "DATA_ARCHITECTURE.md",
            "ARCHITECTURE.md",
            "EXTENSION_AND_SYNC.md",
        ],
    },
    {
        "id": "running",
        "title": "Installing and maintaining",
        "blurb": "The desktop shell, packaging and release, and how to test a build as a user rather than as its author.",
        "paths": [
            "DESKTOP_SHELL.md",
            "PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md",
            "DEEP_QA_BRIEF.md",
        ],
    },
    {
        "id": "building",
        "title": "Building on it",
        "blurb": "The REST API, the design system, and the conventions the interface is held to.",
        "paths": [
            "API_REFERENCE.md",
            "DESIGN.md",
            "linkedin_studio_reimagined_design.md",
            "UI_CONVENTIONS.md",
            "ICON_SYSTEM.md",
            "UI_AGENT_WORKFLOW.md",
            "PRD_AGNO_AGENTOS_MEDIA_STUDIO.md",
        ],
    },
    {
        "id": "history",
        "title": "Project history",
        "blurb": "Day by day implementation briefs, and the feedback reports written back against them.",
        "paths": [
            "prudent_handoff/README_AGENT_INSTRUCTIONS.md",
            "prudent_handoff/DAY_01_IMPLEMENTATION_SPEC.md",
            "prudent_handoff/DAY_01_FEEDBACK.md",
            "prudent_handoff/DAY_01_ENGINEERING_OBSERVATIONS_AND_RISKS.md",
            "prudent_handoff/DAY_02_IMPLEMENTATION_SPEC.md",
            "prudent_handoff/DAY_02_FEEDBACK.md",
            "prudent_handoff/DAY_03_IMPLEMENTATION_SPEC.md",
            "prudent_handoff/DAY_03_FEEDBACK.md",
            "prudent_handoff/DAY_04_IMPLEMENTATION_SPEC.md",
            "prudent_handoff/DAY_04_FEEDBACK.md",
            "prudent_handoff/PRODUCTIZATION_FEEDBACK.md",
            "builder_feedback/DAY_03_FEEDBACK.md",
        ],
    },
]

# Path to section id. Built once from the table above, which is also where a
# duplicate would be caught rather than quietly overwriting an earlier entry.
_SECTION_OF_PATH = {}
for _section in HELP_SECTIONS:
    for _path in _section["paths"]:
        if _path in _SECTION_OF_PATH:
            raise ValueError(f"{_path} is filed under two help sections")
        _SECTION_OF_PATH[_path] = _section["id"]

_SECTION_BY_ID = {section["id"]: section for section in HELP_SECTIONS}

# Where a file that nobody has filed goes.
#
# It is its own section rather than an existing one, and it is named for what
# it is. A document quietly appended to "Building on it" reads as a decision
# somebody made; one sitting under "Not yet filed" reads as the open question
# it actually is, and the test that fails is what gets it moved.
UNFILED = {
    "id": "unfiled",
    "title": "Not yet filed",
    "blurb": "Indexed and readable, but nobody has said yet which part of the help this belongs to.",
}


def section_for_path(rel_path):
    """The help section a document belongs to, or the unfiled one."""
    return _SECTION_OF_PATH.get(str(rel_path or "").replace("\\", "/"), UNFILED["id"])


def section_meta(section_id):
    """Title and blurb for a section id."""
    return _SECTION_BY_ID.get(section_id, UNFILED)


def help_sections(docs_dir=None):
    """
    The sections, each carrying the documents filed under it.

    Ordered as HELP_SECTIONS is written, because that order is the reading
    order: installing it comes before using it, and the project's own history
    comes last. Within a section the written order wins too, so Getting Started
    sits above First Run rather than being alphabetised away from it.
    """
    library = document_library(docs_dir)
    by_path = {entry["path"]: entry for entry in library}

    sections = []
    for section in HELP_SECTIONS:
        documents = [by_path[path] for path in section["paths"] if path in by_path]
        sections.append({
            "id": section["id"],
            "title": section["title"],
            "blurb": section["blurb"],
            "documents": documents,
            "count": len(documents),
            "words": sum(entry["words"] for entry in documents),
        })

    stray = [entry for entry in library if entry["path"] not in _SECTION_OF_PATH]
    if stray:
        sections.append({
            "id": UNFILED["id"],
            "title": UNFILED["title"],
            "blurb": UNFILED["blurb"],
            "documents": stray,
            "count": len(stray),
            "words": sum(entry["words"] for entry in stray),
        })
    return sections


def resolve_document_path(document_id, docs_dir=None):
    """
    The absolute path an id refers to, or None.

    A lookup rather than a join: the id selects a row from a table of files this
    module walked, so nothing a caller sends is ever used to build a path.
    """
    wanted = str(document_id or "").lower()
    if not wanted:
        return None
    target_dir = docs_dir or DOCS_DIR
    for entry in document_library(target_dir):
        if entry["id"] == wanted:
            return os.path.join(target_dir, *entry["path"].split("/"))
    return None
