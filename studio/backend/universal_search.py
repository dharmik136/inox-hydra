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
    text = str(query or "")[:MAX_QUERY_LENGTH].strip().casefold()
    words = [word.strip(QUOTES) for word in re.split(r"\s+", text)]
    # A term that folds to nothing, such as a lone accent, would be LIKE '%%'
    # and match every row.
    return [word for word in words if fold(word)][:MAX_TERMS]




# ---------------------------------------------------------------------------
# The search index
# ---------------------------------------------------------------------------
#
# search_docs gives every post, LinkedIn post and lead a stable integer id.
# The FTS5 tables are contentless: they hold only the index (about 25 MB at
# 49,142 leads and 131,000 comments) and the rows are read from their own
# tables. A comment's rowid is its lead's docid times 2^32 plus the
# interaction id, so the leads a comment search found are rowid >> 32, with
# no lookup per comment.
#
# Contentless rows are removed with the 'delete' command, which must be given
# the values that were indexed, so every trigger indexes through the same
# expression. Its replacements are the letters unicode61 does not fold the way
# fold() does: dotless i, and sharp s, which casefold() spells "ss".
#
# Not folded, as fold() did: compatibility forms (the "fi" ligature, full
# width letters, superscripts). unicode61 has no NFKD step.

SEARCH_TOKENIZER = "unicode61 remove_diacritics 2"
_COMMENT_SHIFT = 4294967296  # 2 ** 32


def _folded_sql(expression: str) -> str:
    return f"replace(replace(replace({expression}, char(305), 'i'), char(223), 'ss'), char(7838), 'ss')"


_POST_BODY = _folded_sql("COALESCE({p}.content, '') || ' ' || COALESCE({p}.tags, '')")
_OWN_BODY = _folded_sql("COALESCE({p}.text, '')")
_LEAD_NAME = _folded_sql("COALESCE({p}.full_name, '') || ' ' || COALESCE({p}.name, '')")
_LEAD_ABOUT = _folded_sql("COALESCE({p}.company, '') || ' ' || COALESCE({p}.headline, '')")
_LEAD_NOTES = _folded_sql("COALESCE({p}.notes, '')")
_COMMENT = _folded_sql("{p}.comment_text")


def _lead_doc(lead_id: str) -> str:
    return f"(SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST({lead_id} AS TEXT))"


def _text_triggers(kind: str, table: str, key: str, body: str, columns: str) -> List[str]:
    """Insert, update and delete triggers keeping one kind of document in search_posts."""
    old, new = body.format(p="OLD"), body.format(p="NEW")
    return [
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_added AFTER INSERT ON {table}
        BEGIN
            INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('{kind}', NEW.{key});
            INSERT INTO search_posts (rowid, body) SELECT last_insert_rowid(), {new} WHERE changes() > 0;
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_changed AFTER UPDATE OF {columns} ON {table}
        WHEN {" OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in columns.split(", "))}
        BEGIN
            INSERT INTO search_posts (search_posts, rowid, body)
            SELECT 'delete', docid, {old} FROM search_docs WHERE kind = '{kind}' AND ref = OLD.{key};
            UPDATE search_docs SET ref = NEW.{key} WHERE kind = '{kind}' AND ref = OLD.{key};
            INSERT INTO search_posts (rowid, body)
            SELECT docid, {new} FROM search_docs WHERE kind = '{kind}' AND ref = NEW.{key};
        END
        """,
        f"""
        CREATE TRIGGER IF NOT EXISTS search_{kind}_removed AFTER DELETE ON {table}
        BEGIN
            INSERT INTO search_posts (search_posts, rowid, body)
            SELECT 'delete', docid, {old} FROM search_docs WHERE kind = '{kind}' AND ref = OLD.{key};
            DELETE FROM search_docs WHERE kind = '{kind}' AND ref = OLD.{key};
        END
        """,
    ]


_LEAD_COLUMNS = "full_name, name, company, headline, notes, id"


def _lead_values(p: str) -> str:
    return f"{_LEAD_NAME.format(p=p)}, {_LEAD_ABOUT.format(p=p)}, {_LEAD_NOTES.format(p=p)}"


SEARCH_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS search_docs (
        docid INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        ref TEXT NOT NULL,
        UNIQUE (kind, ref)
    )
    """,
    f"CREATE VIRTUAL TABLE IF NOT EXISTS search_posts USING fts5(body, content='', tokenize='{SEARCH_TOKENIZER}')",
    f"CREATE VIRTUAL TABLE IF NOT EXISTS search_leads USING fts5(name, about, notes, content='', "
    f"tokenize='{SEARCH_TOKENIZER}')",
    f"CREATE VIRTUAL TABLE IF NOT EXISTS search_comments USING fts5(comment_text, content='', "
    f"tokenize='{SEARCH_TOKENIZER}')",
    *_text_triggers("post", "posts", "id", _POST_BODY, "content, tags, id"),
    *_text_triggers("own_post", "own_posts", "activity_urn", _OWN_BODY, "text, activity_urn"),
    # A lead: their profile, and anything they said before the lead existed.
    f"""
    CREATE TRIGGER IF NOT EXISTS search_lead_added AFTER INSERT ON leads
    BEGIN
        INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('lead', NEW.id);
        INSERT INTO search_leads (rowid, name, about, notes)
        SELECT last_insert_rowid(), {_lead_values("NEW")} WHERE changes() > 0;
        INSERT INTO search_comments (rowid, comment_text)
        SELECT {_lead_doc("NEW.id")} * {_COMMENT_SHIFT} + i.id, {_COMMENT.format(p="i")}
        FROM lead_interactions i
        WHERE changes() > 0 AND i.lead_id = NEW.id AND i.comment_text IS NOT NULL ORDER BY i.id;
    END
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS search_lead_changed AFTER UPDATE OF {_LEAD_COLUMNS} ON leads
    WHEN {" OR ".join(f"OLD.{c} IS NOT NEW.{c}" for c in _LEAD_COLUMNS.split(", "))}
    BEGIN
        INSERT INTO search_leads (search_leads, rowid, name, about, notes)
        SELECT 'delete', docid, {_lead_values("OLD")} FROM search_docs WHERE kind = 'lead' AND ref = OLD.id;
        UPDATE search_docs SET ref = NEW.id WHERE kind = 'lead' AND ref = OLD.id;
        INSERT INTO search_leads (rowid, name, about, notes)
        SELECT docid, {_lead_values("NEW")} FROM search_docs WHERE kind = 'lead' AND ref = NEW.id;
    END
    """,
    # Whichever runs first, this or the forget trigger that deletes the
    # lead's interactions, every comment of theirs leaves the index: here
    # while they still exist, or by the interaction trigger before.
    f"""
    CREATE TRIGGER IF NOT EXISTS search_lead_removed AFTER DELETE ON leads
    BEGIN
        INSERT INTO search_comments (search_comments, rowid, comment_text)
        SELECT 'delete', d.docid * {_COMMENT_SHIFT} + i.id, {_COMMENT.format(p="i")}
        FROM search_docs d JOIN lead_interactions i ON i.lead_id = OLD.id
        WHERE d.kind = 'lead' AND d.ref = OLD.id AND i.comment_text IS NOT NULL;
        INSERT INTO search_leads (search_leads, rowid, name, about, notes)
        SELECT 'delete', docid, {_lead_values("OLD")} FROM search_docs WHERE kind = 'lead' AND ref = OLD.id;
        DELETE FROM search_docs WHERE kind = 'lead' AND ref = OLD.id;
    END
    """,
    # What someone said, indexed under the lead who said it.
    f"""
    CREATE TRIGGER IF NOT EXISTS search_comment_added AFTER INSERT ON lead_interactions
    WHEN NEW.comment_text IS NOT NULL
    BEGIN
        INSERT INTO search_comments (rowid, comment_text)
        SELECT docid * {_COMMENT_SHIFT} + NEW.id, {_COMMENT.format(p="NEW")}
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT);
    END
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS search_comment_changed AFTER UPDATE OF comment_text, lead_id, id ON lead_interactions
    WHEN OLD.comment_text IS NOT NEW.comment_text OR OLD.lead_id IS NOT NEW.lead_id OR OLD.id IS NOT NEW.id
    BEGIN
        INSERT INTO search_comments (search_comments, rowid, comment_text)
        SELECT 'delete', docid * {_COMMENT_SHIFT} + OLD.id, {_COMMENT.format(p="OLD")}
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.lead_id AS TEXT) AND OLD.comment_text IS NOT NULL;
        INSERT INTO search_comments (rowid, comment_text)
        SELECT docid * {_COMMENT_SHIFT} + NEW.id, {_COMMENT.format(p="NEW")}
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT) AND NEW.comment_text IS NOT NULL;
    END
    """,
    f"""
    CREATE TRIGGER IF NOT EXISTS search_comment_removed AFTER DELETE ON lead_interactions
    WHEN OLD.comment_text IS NOT NULL
    BEGIN
        INSERT INTO search_comments (search_comments, rowid, comment_text)
        SELECT 'delete', docid * {_COMMENT_SHIFT} + OLD.id, {_COMMENT.format(p="OLD")}
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.lead_id AS TEXT);
    END
    """,
]


def build_search_index(conn) -> None:
    """
    Indexes everything already held, inside the caller's transaction, after
    SEARCH_SCHEMA. Run again it starts from empty, so it is idempotent.
    Rows go in rowid order, which FTS5 writes fastest.
    """
    for table in ("search_posts", "search_leads", "search_comments"):
        conn.execute(f"INSERT INTO {table} ({table}) VALUES ('delete-all')")
    conn.execute("DELETE FROM search_docs")
    conn.execute("INSERT INTO search_docs (kind, ref) SELECT 'post', id FROM posts ORDER BY rowid")
    conn.execute("INSERT INTO search_docs (kind, ref) SELECT 'own_post', activity_urn FROM own_posts ORDER BY rowid")
    conn.execute("INSERT INTO search_docs (kind, ref) SELECT 'lead', id FROM leads ORDER BY rowid")
    conn.execute(f"INSERT INTO search_posts (rowid, body) SELECT d.docid, {_POST_BODY.format(p='p')} "
                 f"FROM search_docs d JOIN posts p ON p.id = d.ref WHERE d.kind = 'post' ORDER BY d.docid")
    conn.execute(f"INSERT INTO search_posts (rowid, body) SELECT d.docid, {_OWN_BODY.format(p='p')} "
                 f"FROM search_docs d JOIN own_posts p ON p.activity_urn = d.ref WHERE d.kind = 'own_post' "
                 f"ORDER BY d.docid")
    conn.execute(f"INSERT INTO search_leads (rowid, name, about, notes) SELECT d.docid, {_lead_values('p')} "
                 f"FROM search_docs d JOIN leads p ON p.id = d.ref WHERE d.kind = 'lead' ORDER BY d.docid")
    conn.execute(f"INSERT INTO search_comments (rowid, comment_text) "
                 f"SELECT d.docid * {_COMMENT_SHIFT} + i.id, {_COMMENT.format(p='i')} "
                 f"FROM lead_interactions i JOIN search_docs d ON d.kind = 'lead' AND d.ref = CAST(i.lead_id AS TEXT) "
                 f"WHERE i.comment_text IS NOT NULL ORDER BY 1")
    for table in ("search_posts", "search_leads", "search_comments"):
        conn.execute(f"INSERT INTO {table} ({table}) VALUES ('optimize')")


# What unicode61 counts as part of a word: letters and numbers. Anything else
# separates words, so a query word made only of it cannot be searched for.
_SEPARATORS = re.compile(r"[\W_]+")


def _match_word(term: str) -> Optional[str]:
    """One query word as an FTS5 prefix phrase, or None when it has no letters or digits."""
    text = term.casefold().replace("ı", "i")
    if not any(piece for piece in _SEPARATORS.split(text)):
        return None
    return '"' + text.replace('"', '""') + '"*'


def _literal_terms(terms: List[str]) -> List[str]:
    """Words with punctuation in them, which must also appear exactly as typed."""
    return [fold(t) for t in terms if _SEPARATORS.sub("", t) != t]


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




def _literally(text: Any, literal: List[str]) -> bool:
    folded = fold(text)
    return all(term in folded for term in literal)


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
        expression = " ".join(match)
        found = []
        rows = []
        for row in conn.execute(
            """
            SELECT p.id, p.content, p.tags, p.status, p.scheduled_for, p.published_at, p.created_at, p.activity_urn
            FROM search_posts f JOIN search_docs d ON d.docid = f.rowid AND d.kind = 'post'
            JOIN posts p ON p.id = d.ref
            WHERE search_posts MATCH ?
            ORDER BY COALESCE(p.published_at, p.scheduled_for, p.created_at) DESC, p.rowid
            """, (expression,)):
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
        taken = 0
        for row in conn.execute(
            """
            SELECT o.activity_urn, o.text, o.published_at
            FROM search_posts f JOIN search_docs d ON d.docid = f.rowid AND d.kind = 'own_post'
            JOIN own_posts o ON o.activity_urn = d.ref
            WHERE search_posts MATCH ?
            ORDER BY o.published_at DESC, o.rowid
            """, (expression,)):
            if taken >= limit:
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
    own = conn is None
    conn = conn or get_db()
    try:
        folded_terms = [fold(term) for term in terms]
        results = []
        for row in conn.execute(
            f"""
            SELECT l.id, l.full_name, l.name, l.company, l.headline, l.notes, l.lead_status, l.status
            FROM search_docs d JOIN leads l ON l.id = d.ref
            WHERE d.kind = 'lead' AND {where}
            ORDER BY l.updated_at DESC, l.id
            """, params):
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
            if literal or not profile_hit:
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
            if literal and not _literally(f"{profile} {said}", literal):
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
