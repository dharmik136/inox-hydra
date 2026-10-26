"""
Universal search: one query across everything the studio holds.

The command palette searched its own list of actions and nothing else. A post
you wrote last week, a lead whose name you half remember, the specimen with
the opening you liked: none of them could be found from anywhere but the
surface that happened to hold them, and posts could not be found at all. The
help article on drafts says it plainly, "no surface reopens an older post in
the Composer".

This module answers the part that lives in SQLite:

- Every query runs locally, against this machine's database, with bound
  parameters. Nothing here makes a request anywhere.
- Every word of the query must match, as the start of a word, with case and
  accents folded on both sides, so Émile, ÉMILE and emile are one word and
  "pric" finds pricing. It is answered by an FTS5 index (unicode61, accents
  removed) kept in step with the posts, leads and comments by triggers
  (migration 22). It was a substring test through a Python function on
  every row of every lead joined to every interaction: 2 s for any query on
  three years of one creator's data, including a query that matched nothing.
  Words are matched from their start, not anywhere inside them: "pricing"
  no longer finds "repricing". That was the owner's choice, against a
  substring index six times the size.
- A word written with punctuation in it ("100%", "x_l", "c++") must also
  appear exactly as typed, so a wildcard is still a character.
- A result says where it opens. The interface decides what opening means for
  each kind, but the destination is chosen here, from the row's own state,
  so a published post is never offered as something to edit.

Help articles and Swipe File specimens are searched by the modules that
already own them, from the route, so their ranking and their ids agree with
what those surfaces render.
"""


import re
import sqlite3
import unicodedata
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db

MAX_QUERY_LENGTH = 200
MAX_TERMS = 8
SNIPPET_RADIUS = 70


# Quotes around a word are how people type a name, not part of it. "Asha"
# found nothing, because no lead's name contains a quotation mark.
QUOTES = "\"'`\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f\u00ab\u00bb"


def names_company(headline: str, company: str) -> bool:
    """
    Whether a headline already names the company, as whole words.

    "Engineering Manager at Logiq" names Logiq; "Metadata engineer" does not
    name Meta, which a substring test said it did, hiding the company.
    """
    if not company or not headline:
        return False
    return re.search(r"(?<!\w)" + re.escape(fold(company)) + r"(?!\w)", fold(headline)) is not None


def fold(text: Any) -> str:
    """
    Text with case and accents folded, for comparing and nothing else.

    SQLite's LOWER folds ASCII only, while the query was lowercased by Python,
    so "Émile" could never match a stored "Émile": one side said "émile" and
    the other still "Émile". Both sides now go through this, and accents are
    dropped too, so a creator who types "Olander" finds Ölander.
    """
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    # The Turkish dotless i has no decomposition, so it is mapped by hand:
    # without this "isik" never found Işık.
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().replace("\u0131", "i")


def _folded_with_offsets(text: str):
    """fold(text), and for each folded character the index it came from in text."""
    if text.isascii():
        # Folding ASCII is lowering it, one character for one, so the offsets
        # are the identity. A post's snippet folded character by character
        # took a third of a search's time.
        return text.lower(), range(len(text))
    folded, offsets = [], []
    for index, ch in enumerate(text):
        piece = fold(ch)
        folded.append(piece)
        offsets.extend([index] * len(piece))
    return "".join(folded), offsets


def terms_of(query: Any) -> List[str]:
    """The words of a query, lowercased and unquoted, bounded in count and length."""
    # Control characters are not text anyone typed; a NUL reached FTS5 as an
    # unterminated string and the Leads box answered 500.
    text = "".join(" " if unicodedata.category(ch) == "Cc" else ch for ch in str(query or "")[:MAX_QUERY_LENGTH])
    text = text.strip().casefold()
    words = [word.strip(QUOTES) for word in re.split(r"\s+", text)]
    # A term that folds to nothing, such as a lone accent, would be LIKE '%%'
    # and match every row.
    return [word for word in words if fold(word)][:MAX_TERMS]




# ---------------------------------------------------------------------------
# The search index
# ---------------------------------------------------------------------------
#
# search_docs gives every post, LinkedIn post and lead a stable integer id;
# the FTS5 tables (unicode61, accents removed) hold the indexed text by that
# id. A comment's rowid is its lead's docid times 2^32 plus the interaction
# id, so the leads a comment search found are rowid >> 32, with no lookup per
# comment, and all of one person's comments are one rowid range.
#
# Triggers (migration 24) keep the index in step with posts, own_posts,
# leads and lead_interactions in plain SQL, so any connection can write
# those tables: a row is indexed as it is written and removed by its rowid
# the moment it is deleted, which forget relies on. The SQL replacements are
# the letters unicode61 does not fold as fold() does: dotless i, and sharp s,
# which casefold() spells "ss".
#
# What SQL cannot fold is compatibility text: the Mathematical Bold and
# Italic letters the Composer's own Bold and Italic write (formatters.py),
# the letterlike forms its italic h uses, ligatures and full-width letters.
# Indexed as written they were words of their own, and a bolded "Pricing
# lessons" could not be found by "pricing". A row holding any of them is put
# on search_refold by its trigger, and refold() re-indexes it through NFKC in
# Python, before the next search reads the index.

SEARCH_TOKENIZER = "unicode61 remove_diacritics 2"
_COMMENT_SHIFT = 4294967296  # 2 ** 32

# Mathematical Alphanumeric Symbols, Letterlike Symbols, Alphabetic
# Presentation Forms (the ligatures) and Halfwidth and Fullwidth Forms.
COMPAT_RANGES = ((0x1D400, 0x1D7FF), (0x2100, 0x214F), (0xFB00, 0xFB4F), (0xFF00, 0xFFEF))
_COMPAT_GLOB = "'*[' || " + " || ".join(f"char({lo}) || '-' || char({hi})" for lo, hi in COMPAT_RANGES) + " || ']*'"


def _folded_sql(expression: str) -> str:
    return f"replace(replace(replace({expression}, char(305), 'i'), char(223), 'ss'), char(7838), 'ss')"


def fold_for_index(text: Any) -> str:
    """What refold() indexes: NFKC, so styled letters are letters, then the SQL replacements."""
    folded = unicodedata.normalize("NFKC", str(text or ""))
    return folded.replace("ı", "i").replace("ß", "ss").replace("ẞ", "ss")


def _needs_refold(text: Any) -> bool:
    return any(lo <= ord(ch) <= hi for ch in str(text or "") for lo, hi in COMPAT_RANGES)


# Each kind of document: its source table and key, the SQL of its indexed
# columns, and the Python that refold() uses for the same columns.
_RAW = {
    "post": "COALESCE({p}.content, '') || ' ' || COALESCE({p}.tags, '')",
    "own_post": "COALESCE({p}.text, '')",
    "lead_name": "COALESCE({p}.full_name, '') || ' ' || COALESCE({p}.name, '')",
    "lead_about": "COALESCE({p}.company, '') || ' ' || COALESCE({p}.headline, '')",
    "lead_notes": "COALESCE({p}.notes, '')",
    "comment": "COALESCE({p}.comment_text, '')",
}


def _sql(part: str, p: str) -> str:
    return _folded_sql(_RAW[part].format(p=p))


def _compat(parts, p: str) -> str:
    return " OR ".join(f"({_RAW[part].format(p=p)}) GLOB {_COMPAT_GLOB}" for part in parts)


def _lead_values(p: str) -> str:
    return f"{_sql('lead_name', p)}, {_sql('lead_about', p)}, {_sql('lead_notes', p)}"


def _text_triggers(kind: str, table: str, key: str, columns: str) -> List[str]:
    """Insert, update and delete triggers keeping one kind of document in search_posts."""
    doc = f"(SELECT docid FROM search_docs WHERE kind = '{kind}' AND ref = {{k}})"
    return [
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_added AFTER INSERT ON {table}
        BEGIN
            INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('{kind}', NEW.{key});
            INSERT INTO search_posts (rowid, body) SELECT last_insert_rowid(), {_sql(kind, 'NEW')} WHERE changes() > 0;
            INSERT OR IGNORE INTO search_refold (kind, ref) SELECT '{kind}', NEW.{key} WHERE {_compat([kind], 'NEW')};
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_changed AFTER UPDATE OF {columns} ON {table}
        WHEN {" OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in columns.split(", "))}
        BEGIN
            DELETE FROM search_posts WHERE rowid = {doc.format(k=f'OLD.{key}')};
            UPDATE search_docs SET ref = NEW.{key} WHERE kind = '{kind}' AND ref = OLD.{key};
            INSERT INTO search_posts (rowid, body)
            SELECT docid, {_sql(kind, 'NEW')} FROM search_docs WHERE kind = '{kind}' AND ref = NEW.{key};
            DELETE FROM search_refold WHERE kind = '{kind}' AND ref = OLD.{key};
            INSERT OR IGNORE INTO search_refold (kind, ref) SELECT '{kind}', NEW.{key} WHERE {_compat([kind], 'NEW')};
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_removed AFTER DELETE ON {table}
        BEGIN
            DELETE FROM search_posts WHERE rowid = {doc.format(k=f'OLD.{key}')};
            DELETE FROM search_docs WHERE kind = '{kind}' AND ref = OLD.{key};
            DELETE FROM search_refold WHERE kind = '{kind}' AND ref = OLD.{key};
        END
        """,
    ]


_LEAD_COLUMNS = "full_name, name, company, headline, notes, id"
_LEAD_PARTS = ("lead_name", "lead_about", "lead_notes")


def _lead_doc(lead_id: str) -> str:
    return f"(SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST({lead_id} AS TEXT))"


def search_schema() -> List[str]:
    """The tables and triggers of the index, as migration 24 created them (it keeps a frozen copy)."""
    return [
        """
        CREATE TABLE IF NOT EXISTS search_docs (
            docid INTEGER PRIMARY KEY,
            kind TEXT NOT NULL,
            ref TEXT NOT NULL,
            UNIQUE (kind, ref)
        )
        """,
        "CREATE TABLE IF NOT EXISTS search_refold (kind TEXT NOT NULL, ref TEXT NOT NULL, "
        "PRIMARY KEY (kind, ref)) WITHOUT ROWID",
        f"CREATE VIRTUAL TABLE IF NOT EXISTS search_posts USING fts5(body, tokenize='{SEARCH_TOKENIZER}')",
        f"CREATE VIRTUAL TABLE IF NOT EXISTS search_leads USING fts5(name, about, notes, tokenize='{SEARCH_TOKENIZER}')",
        f"CREATE VIRTUAL TABLE IF NOT EXISTS search_comments USING fts5(comment_text, tokenize='{SEARCH_TOKENIZER}')",
        *_text_triggers("post", "posts", "id", "content, tags, id"),
        *_text_triggers("own_post", "own_posts", "activity_urn", "text, activity_urn"),
        # A lead: their profile, and anything they said before the lead existed.
        f"""
        CREATE TRIGGER IF NOT EXISTS search_lead_added AFTER INSERT ON leads
        BEGIN
            INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('lead', NEW.id);
            INSERT INTO search_leads (rowid, name, about, notes)
            SELECT last_insert_rowid(), {_lead_values("NEW")} WHERE changes() > 0;
            INSERT INTO search_comments (rowid, comment_text)
            SELECT {_lead_doc("NEW.id")} * {_COMMENT_SHIFT} + i.id, {_sql("comment", "i")}
            FROM lead_interactions i
            WHERE changes() > 0 AND i.lead_id = NEW.id AND i.comment_text IS NOT NULL ORDER BY i.id;
            INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'lead', NEW.id WHERE {_compat(_LEAD_PARTS, 'NEW')};
            INSERT OR IGNORE INTO search_refold (kind, ref)
            SELECT 'comment', CAST(i.id AS TEXT) FROM lead_interactions i
            WHERE i.lead_id = NEW.id AND i.comment_text IS NOT NULL AND ({_compat(['comment'], 'i')});
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_lead_changed AFTER UPDATE OF {_LEAD_COLUMNS} ON leads
        WHEN {" OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in _LEAD_COLUMNS.split(", "))}
        BEGIN
            DELETE FROM search_leads WHERE rowid = {_lead_doc("OLD.id")};
            UPDATE search_docs SET ref = NEW.id WHERE kind = 'lead' AND ref = OLD.id;
            INSERT INTO search_leads (rowid, name, about, notes)
            SELECT docid, {_lead_values("NEW")} FROM search_docs WHERE kind = 'lead' AND ref = NEW.id;
            DELETE FROM search_refold WHERE kind = 'lead' AND ref = OLD.id;
            INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'lead', NEW.id WHERE {_compat(_LEAD_PARTS, 'NEW')};
        END
        """,
        # Whichever runs first, this or the forget trigger that deletes the
        # lead's interactions, every comment of theirs leaves the index: here
        # as one rowid range, or by the interaction trigger before.
        f"""
        CREATE TRIGGER IF NOT EXISTS search_lead_removed AFTER DELETE ON leads
        BEGIN
            DELETE FROM search_comments WHERE rowid BETWEEN {_lead_doc("OLD.id")} * {_COMMENT_SHIFT}
                AND {_lead_doc("OLD.id")} * {_COMMENT_SHIFT} + {_COMMENT_SHIFT - 1};
            DELETE FROM search_leads WHERE rowid = {_lead_doc("OLD.id")};
            DELETE FROM search_docs WHERE kind = 'lead' AND ref = OLD.id;
            DELETE FROM search_refold WHERE kind = 'lead' AND ref = OLD.id;
        END
        """,
        # What someone said, indexed under the lead who said it.
        f"""
        CREATE TRIGGER IF NOT EXISTS search_comment_added AFTER INSERT ON lead_interactions
        WHEN NEW.comment_text IS NOT NULL
        BEGIN
            INSERT INTO search_comments (rowid, comment_text)
            SELECT docid * {_COMMENT_SHIFT} + NEW.id, {_sql("comment", "NEW")}
            FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT);
            INSERT OR IGNORE INTO search_refold (kind, ref)
            SELECT 'comment', CAST(NEW.id AS TEXT) WHERE {_compat(['comment'], 'NEW')};
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_comment_changed AFTER UPDATE OF comment_text, lead_id, id ON lead_interactions
        WHEN OLD.comment_text IS NOT NEW.comment_text OR OLD.lead_id IS NOT NEW.lead_id OR OLD.id IS NOT NEW.id
        BEGIN
            DELETE FROM search_comments WHERE rowid = {_lead_doc("OLD.lead_id")} * {_COMMENT_SHIFT} + OLD.id;
            INSERT INTO search_comments (rowid, comment_text)
            SELECT docid * {_COMMENT_SHIFT} + NEW.id, {_sql("comment", "NEW")}
            FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT) AND NEW.comment_text IS NOT NULL;
            DELETE FROM search_refold WHERE kind = 'comment' AND ref = CAST(OLD.id AS TEXT);
            INSERT OR IGNORE INTO search_refold (kind, ref)
            SELECT 'comment', CAST(NEW.id AS TEXT) WHERE NEW.comment_text IS NOT NULL AND ({_compat(['comment'], 'NEW')});
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_comment_removed AFTER DELETE ON lead_interactions
        WHEN OLD.comment_text IS NOT NULL
        BEGIN
            DELETE FROM search_comments WHERE rowid = {_lead_doc("OLD.lead_id")} * {_COMMENT_SHIFT} + OLD.id;
            DELETE FROM search_refold WHERE kind = 'comment' AND ref = CAST(OLD.id AS TEXT);
        END
        """,
    ]


def search_build() -> List[str]:
    """Statements that index everything already held, after search_schema (migration 24 keeps a frozen copy)."""
    return [
        "DELETE FROM search_posts",
        "DELETE FROM search_leads",
        "DELETE FROM search_comments",
        "DELETE FROM search_docs",
        "DELETE FROM search_refold",
        "INSERT INTO search_docs (kind, ref) SELECT 'post', id FROM posts ORDER BY rowid",
        "INSERT INTO search_docs (kind, ref) SELECT 'own_post', activity_urn FROM own_posts ORDER BY rowid",
        "INSERT INTO search_docs (kind, ref) SELECT 'lead', id FROM leads ORDER BY rowid",
        f"INSERT INTO search_posts (rowid, body) SELECT d.docid, {_sql('post', 'p')} "
        f"FROM search_docs d JOIN posts p ON p.id = d.ref WHERE d.kind = 'post' ORDER BY d.docid",
        f"INSERT INTO search_posts (rowid, body) SELECT d.docid, {_sql('own_post', 'p')} "
        f"FROM search_docs d JOIN own_posts p ON p.activity_urn = d.ref WHERE d.kind = 'own_post' ORDER BY d.docid",
        f"INSERT INTO search_leads (rowid, name, about, notes) SELECT d.docid, {_lead_values('p')} "
        f"FROM search_docs d JOIN leads p ON p.id = d.ref WHERE d.kind = 'lead' ORDER BY d.docid",
        f"INSERT INTO search_comments (rowid, comment_text) "
        f"SELECT d.docid * {_COMMENT_SHIFT} + i.id, {_sql('comment', 'i')} "
        f"FROM lead_interactions i JOIN search_docs d ON d.kind = 'lead' AND d.ref = CAST(i.lead_id AS TEXT) "
        f"WHERE i.comment_text IS NOT NULL ORDER BY 1",
        f"INSERT INTO search_refold (kind, ref) SELECT 'post', id FROM posts p WHERE {_compat(['post'], 'p')}",
        f"INSERT INTO search_refold (kind, ref) SELECT 'own_post', activity_urn FROM own_posts p "
        f"WHERE {_compat(['own_post'], 'p')}",
        f"INSERT INTO search_refold (kind, ref) SELECT 'lead', id FROM leads p WHERE {_compat(_LEAD_PARTS, 'p')}",
        f"INSERT INTO search_refold (kind, ref) SELECT 'comment', CAST(i.id AS TEXT) FROM lead_interactions i "
        f"WHERE i.comment_text IS NOT NULL AND ({_compat(['comment'], 'i')})",
        "INSERT INTO search_posts (search_posts) VALUES ('optimize')",
        "INSERT INTO search_leads (search_leads) VALUES ('optimize')",
        "INSERT INTO search_comments (search_comments) VALUES ('optimize')",
    ]


def build_search_index(conn) -> None:
    """
    Indexes everything already held, inside the caller's transaction, then
    folds what holds styled letters. Run again it starts from empty.
    """
    for statement in search_build():
        conn.execute(statement)
    refold(conn, limit=None)


REFOLD_BATCH = 500


def refold(conn, limit: Optional[int] = REFOLD_BATCH) -> int:
    """
    Re-indexes the rows on search_refold through fold_for_index, inside the
    caller's transaction. Returns how many were done.
    """
    cursor = conn.cursor()
    cursor.row_factory = sqlite3.Row
    sql = "SELECT kind, ref FROM search_refold"
    queued = cursor.execute(sql + (f" LIMIT {int(limit):d}" if limit else "")).fetchall()
    for item in queued:
        kind, ref = item["kind"], item["ref"]
        if kind in ("post", "own_post"):
            table, key, column = (("posts", "id", "COALESCE(content, '') || ' ' || COALESCE(tags, '')")
                                  if kind == "post" else ("own_posts", "activity_urn", "COALESCE(text, '')"))
            row = cursor.execute(
                f"SELECT d.docid, {column} AS body FROM {table} t JOIN search_docs d ON d.kind = ? AND d.ref = t.{key} "
                f"WHERE t.{key} = ?", (kind, ref)).fetchone()
            if row:
                cursor.execute("DELETE FROM search_posts WHERE rowid = ?", (row["docid"],))
                cursor.execute("INSERT INTO search_posts (rowid, body) VALUES (?, ?)",
                               (row["docid"], fold_for_index(row["body"])))
        elif kind == "lead":
            row = cursor.execute(
                "SELECT d.docid, COALESCE(l.full_name, '') || ' ' || COALESCE(l.name, '') AS name, "
                "COALESCE(l.company, '') || ' ' || COALESCE(l.headline, '') AS about, COALESCE(l.notes, '') AS notes "
                "FROM leads l JOIN search_docs d ON d.kind = 'lead' AND d.ref = l.id WHERE l.id = ?", (ref,)).fetchone()
            if row:
                cursor.execute("DELETE FROM search_leads WHERE rowid = ?", (row["docid"],))
                cursor.execute("INSERT INTO search_leads (rowid, name, about, notes) VALUES (?, ?, ?, ?)",
                               (row["docid"], fold_for_index(row["name"]), fold_for_index(row["about"]),
                                fold_for_index(row["notes"])))
        elif kind == "comment":
            row = cursor.execute(
                "SELECT d.docid * ? + i.id AS rowid, i.comment_text FROM lead_interactions i "
                "JOIN search_docs d ON d.kind = 'lead' AND d.ref = CAST(i.lead_id AS TEXT) "
                "WHERE i.id = ? AND i.comment_text IS NOT NULL", (_COMMENT_SHIFT, int(ref))).fetchone()
            if row:
                cursor.execute("DELETE FROM search_comments WHERE rowid = ?", (row["rowid"],))
                cursor.execute("INSERT INTO search_comments (rowid, comment_text) VALUES (?, ?)",
                               (row["rowid"], fold_for_index(row["comment_text"])))
        cursor.execute("DELETE FROM search_refold WHERE kind = ? AND ref = ?", (kind, ref))
    return len(queued)


def refold_pending(conn) -> None:
    """
    Folds what the triggers queued, before a search reads the index. Waits a
    quarter of a second at most for the write lock; a search that cannot have
    it reads the index as it is, and the next one folds.
    """
    try:
        if not conn.execute("SELECT 1 FROM search_refold LIMIT 1").fetchone():
            return
    except sqlite3.OperationalError:
        return
    if conn.in_transaction:
        refold(conn)
        return
    previous = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.execute("PRAGMA busy_timeout = 250")
    try:
        while True:
            conn.execute("BEGIN IMMEDIATE")
            done = refold(conn)
            conn.commit()
            if done < REFOLD_BATCH:
                break
    except sqlite3.OperationalError:
        if conn.in_transaction:
            conn.rollback()
    finally:
        conn.execute(f"PRAGMA busy_timeout = {int(previous)}")


# What unicode61 counts as part of a word: letters and numbers. Anything else
# separates words, so a query word made only of it cannot be searched for.
_SEPARATORS = re.compile(r"[\W_]+")


def _query_word(term: str) -> str:
    """A query word folded the way the index folds: NFKC, case, dotless i; a typed trailing * is the prefix."""
    return unicodedata.normalize("NFKC", term).casefold().replace("ı", "i").rstrip("*")


def _match_word(term: str) -> Optional[str]:
    """One query word as an FTS5 prefix phrase, or None when it has no letters or digits."""
    text = _query_word(term)
    if not any(piece for piece in _SEPARATORS.split(text)):
        return None
    return '"' + text.replace('"', '""') + '"*'


def _literal_terms(terms: List[str]) -> List[str]:
    """Words with punctuation in them, which must also appear exactly as typed."""
    words = [_query_word(t) for t in terms]
    return [fold(w) for w in words if w and _SEPARATORS.sub("", w) != w]


def _searchable(terms: List[str]) -> List[str]:
    return [m for m in (_match_word(t) for t in terms) if m]



def snippet_around(text: str, terms: List[str], radius: int = SNIPPET_RADIUS) -> str:
    """
    The stretch of text around the first matched term, on one line.

    Plain text only. The interface highlights the terms itself, so nothing
    here is markup and nothing a row contains is ever interpreted.
    """
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if not flat:
        return ""
    folded, offsets = _folded_with_offsets(flat)
    found = [folded.find(fold(term)) for term in terms]
    positions = [offsets[at] for at in found if at != -1]
    if not positions:
        return flat[: radius * 2] + ("..." if len(flat) > radius * 2 else "")
    start = max(0, min(positions) - radius)
    end = min(len(flat), min(positions) + radius)
    return ("..." if start > 0 else "") + flat[start:end].strip() + ("..." if end < len(flat) else "")


def _first_line(text: str, limit: int = 90) -> str:
    for line in str(text or "").splitlines():
        if line.strip():
            line = line.strip()
            return line if len(line) <= limit else line[: limit - 3].rstrip() + "..."
    return ""


def destination_for_post(status: Optional[str], scheduled_for: Optional[str]) -> str:
    """
    Where a post opens.

    Only a draft opens in the Composer. The Composer has one editor and Save
    writes over whatever post it is attached to, so opening a published or
    queued post there would make the next Save quietly rewrite a post that has
    already gone out or is waiting to. Those open where they are listed.
    """
    state = (status or "").lower()
    if state == "draft":
        return "composer"
    if state in ("scheduled", "queued") or (scheduled_for and state != "published"):
        return "queue"
    return "analytics"


def _post_result(content, terms, **fields) -> Dict[str, Any]:
    # The first line is the title, so the snippet reads from the rest of the
    # post. Otherwise every result printed its title twice.
    lines = str(content or "").strip().splitlines()
    body = "\n".join(lines[1:]).strip()
    return {
        "kind": "post",
        "title": _first_line(content) or "Untitled post",
        "snippet": snippet_around(body or content, terms),
        **fields,
    }




# A word typed with punctuation ("c++", "100%") is matched from the start of
# its letters and then checked as typed, row by row. Its letters can be one
# or two, the start of thousands of words, so only this many of the newest
# matching rows are checked: "c++" read every lead's comments, 481 ms.
LITERAL_SCAN_LIMIT = 300


def _literally(text: Any, literal: List[str]) -> bool:
    folded = fold(text)
    return all(term in folded for term in literal)


def _matches(conn, sql: str, params=()):
    """Rows of an FTS query, or none when FTS5 refuses the query text."""
    try:
        yield from conn.execute(sql, params)
    except sqlite3.OperationalError as exc:
        if "fts5" not in str(exc).lower() and "syntax" not in str(exc).lower():
            raise


def search_posts(terms: List[str], limit: int = 6, conn=None) -> List[Dict[str, Any]]:
    """
    The studio's posts, and the creator's posts on LinkedIn.

    Only the studio's own table was searched, so the creator's whole imported
    history, what Posts, Patterns and Today are built from, could not be found
    by a single word of it. A LinkedIn post the studio already holds as one of
    its own posts is listed once, as the studio's.
    """
    match = _searchable(terms)
    if not match:
        return []
    literal = _literal_terms(terms)
    own = conn is None
    conn = conn or get_db()
    try:
        refold_pending(conn)
        expression = " ".join(match)
        found = []
        rows = []
        examined = 0
        for row in _matches(conn, 
            """
            SELECT p.id, p.content, p.tags, p.status, p.scheduled_for, p.published_at, p.created_at, p.activity_urn
            FROM search_posts f JOIN search_docs d ON d.docid = f.rowid AND d.kind = 'post'
            JOIN posts p ON p.id = d.ref
            WHERE search_posts MATCH ?
              -- A post made from a LinkedIn publication stands in for it, and
              -- the publication is the result: published on LinkedIn, opened
              -- in analytics (post_identity.ensure_post).
              AND COALESCE(p.source, 'studio') != 'linkedin'
            ORDER BY COALESCE(p.published_at, p.scheduled_for, p.created_at) DESC, p.rowid
            """, (expression,)):
            examined += 1
            if literal and examined > LITERAL_SCAN_LIMIT:
                break
            if literal and not _literally(f"{row['content'] or ''} {row['tags'] or ''}", literal):
                continue
            rows.append(row)
            if len(rows) >= limit:
                break
        for row in rows:
            status = row["status"] or "draft"
            when = row["published_at"] or row["scheduled_for"] or row["created_at"] or ""
            found.append((str(when), _post_result(
                row["content"], terms,
                id=str(row["id"]),
                meta=f"{status.upper()}" + (f"  {str(when)[:10]}" if when else ""),
                status=status,
                opens=destination_for_post(status, row["scheduled_for"]),
            )))

        studio_urns = {row["activity_urn"] for row in rows if row["activity_urn"]}
        taken = examined = 0
        for row in _matches(conn, 
            """
            SELECT o.activity_urn, o.text, o.published_at
            FROM search_posts f JOIN search_docs d ON d.docid = f.rowid AND d.kind = 'own_post'
            JOIN own_posts o ON o.activity_urn = d.ref
            WHERE search_posts MATCH ?
            ORDER BY o.published_at DESC, o.rowid
            """, (expression,)):
            examined += 1
            if taken >= limit or (literal and examined > LITERAL_SCAN_LIMIT):
                break
            if literal and not _literally(row["text"], literal):
                continue
            taken += 1
            if row["activity_urn"] in studio_urns:
                continue
            when = row["published_at"] or ""
            found.append((str(when), _post_result(
                row["text"], terms,
                id=row["activity_urn"],
                meta="PUBLISHED ON LINKEDIN" + (f"  {str(when)[:10]}" if when else ""),
                status="published",
                opens="analytics",
            )))

        found.sort(key=lambda pair: pair[0], reverse=True)
        return [result for _when, result in found[:limit]]
    finally:
        if own:
            conn.close()


# What someone said is searched from the third letter of a word. One or two
# letters are the start of a name being typed, and as the start of any word
# in 131,000 comments they matched most of them: 0.2 to 0.5 s a keystroke.
SAID_FROM_LETTERS = 3


def _matching_lead_docs(terms: List[str], with_comments: bool):
    """The SQL condition on d.docid for leads matching every word, and its parameters."""
    clauses, params = [], []
    for term, word in ((t, _match_word(t)) for t in terms):
        if not word:
            continue
        if with_comments and len(_SEPARATORS.sub("", fold(term))) >= SAID_FROM_LETTERS:
            clauses.append("d.docid IN (SELECT rowid FROM search_leads WHERE search_leads MATCH ? "
                           "UNION ALL SELECT rowid >> 32 FROM search_comments WHERE search_comments MATCH ?)")
            params += [word, word]
        else:
            clauses.append("d.docid IN (SELECT rowid FROM search_leads WHERE search_leads MATCH ?)")
            params.append(word)
    return " AND ".join(clauses), params


def lead_filter(terms: List[str]):
    """
    A WHERE condition on leads l for the Leads list's search box: every word
    is the start of a word in the person's name, company, headline or notes.
    Returns (sql, params), or None when no word can be searched for, which
    matches nobody.
    """
    where, params = _matching_lead_docs(terms, with_comments=False)
    if not where:
        return None
    return f"l.id IN (SELECT d.ref FROM search_docs d WHERE d.kind = 'lead' AND {where})", params


def search_leads(terms: List[str], limit: int = 6, conn=None) -> List[Dict[str, Any]]:
    """
    People, matched on who they are or on what they said.

    A comment someone left is often the thing you remember about them, so
    their comments are searched too, and a lead found that way shows the
    comment rather than their headline. Every word must be found in the
    person's profile or in something they said.
    """
    where, params = _matching_lead_docs(terms, with_comments=True)
    if not where:
        return []
    literal = _literal_terms(terms)
    # Comments are read for a word typed with punctuation only when every
    # such word has letters enough to search what people said for.
    literal_in_said = all(len(_SEPARATORS.sub("", t)) >= SAID_FROM_LETTERS for t in literal)
    own = conn is None
    conn = conn or get_db()
    try:
        refold_pending(conn)
        folded_terms = [fold(term) for term in terms]
        results = []
        examined = 0
        for row in _matches(conn, 
            f"""
            SELECT l.id, l.full_name, l.name, l.company, l.headline, l.notes, l.lead_status, l.status
            FROM search_docs d JOIN leads l ON l.id = d.ref
            WHERE d.kind = 'lead' AND {where}
            ORDER BY l.updated_at DESC, l.id
            """, params):
            examined += 1
            if literal and examined > LITERAL_SCAN_LIMIT:
                break
            who = row["full_name"] or row["name"] or "Unnamed lead"
            # The company is left out when the headline already names it:
            # "Engineering Manager at Logiq" and "Logiq" read "Logiq Logiq".
            headline, company = row["headline"] or "", row["company"] or ""
            about = headline if names_company(headline, company) else " ".join(
                part for part in (headline, company) if part)
            profile = " ".join(str(part or "") for part in (row["full_name"], row["name"], row["company"],
                                                            row["headline"], row["notes"]))
            profile_hit = all(term in fold(f"{who} {about}") for term in folded_terms)
            said = ""
            profile_literal = bool(literal) and _literally(profile, literal)
            if literal and not profile_literal and not literal_in_said:
                continue
            if not profile_hit or (literal and not profile_literal):
                # What they said that holds a word of the query, in the order
                # they said it: the first few, for the snippet.
                spoken = []
                for (text,) in conn.execute(
                        "SELECT comment_text FROM lead_interactions WHERE lead_id = ? AND comment_text IS NOT NULL "
                        "ORDER BY id", (row["id"],)):
                    if any(term in fold(text) for term in folded_terms):
                        spoken.append(text)
                        if len(spoken) >= 3 and not literal:
                            break
                said = " ".join(spoken)
            if literal and not profile_literal and not (said and _literally(f"{profile} {said}", literal)):
                continue
            results.append({
                "kind": "lead",
                "id": str(row["id"]),
                "title": who,
                "snippet": snippet_around(about, terms) if profile_hit or not said
                           else "Commented: " + snippet_around(said, terms),
                # The stage as the dossier names it ("Outreach Sent"), not the
                # second vocabulary kept beside it ("DM_SENT").
                "meta": (row["status"] or row["lead_status"] or "").replace("_", " ").upper(),
                "opens": "leads",
            })
            if len(results) >= limit:
                break
        return results
    finally:
        if own:
            conn.close()
