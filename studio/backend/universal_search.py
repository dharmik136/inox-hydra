"""
Universal search: one query across everything the studio holds.

The command palette searched its own list of actions and nothing else. A post
you wrote last week, a lead whose name you half remember, the specimen with
the opening you liked: none of them could be found from anywhere but the
surface that happened to hold them, and posts could not be found at all. The
help article on drafts says it plainly, "no surface reopens an older post in
the Composer".

This module answers the part that lives in SQLite. It is deliberately plain:

- Every query runs locally, against this machine's database, with bound
  parameters. Nothing here makes a request anywhere.
- Matching is a case insensitive substring test on every word of the query,
  all of which must appear. The data is one creator's, measured in hundreds
  of rows, and a LIKE over that is fast enough that an index would be
  machinery for its own sake.
- A result says where it opens. The interface decides what opening means for
  each kind, but the destination is chosen here, from the row's own state,
  so a published post is never offered as something to edit.

Help articles and Swipe File specimens are searched by the modules that
already own them, from the route, so their ranking and their ids agree with
what those surfaces render.
"""

import re
from typing import Any, Dict, List, Optional

try:
    from .database import get_db
except ImportError:
    from database import get_db

MAX_QUERY_LENGTH = 200
MAX_TERMS = 8
SNIPPET_RADIUS = 70


def terms_of(query: Any) -> List[str]:
    """The words of a query, lowercased, bounded in count and length."""
    text = str(query or "")[:MAX_QUERY_LENGTH].strip().lower()
    words = [word for word in re.split(r"\s+", text) if word]
    return words[:MAX_TERMS]


def _like(term: str) -> str:
    """A LIKE pattern that matches the term literally, wildcards and all."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _all_terms_in(columns: List[str], terms: List[str]):
    """
    A WHERE clause requiring every term to appear in at least one column.

    Every term, not any: "acme cto" should find the CTO at Acme, not every CTO
    and every Acme employee. The column names are this module's own, never the
    caller's, so interpolating them is safe; the terms are always bound.
    """
    clauses, params = [], []
    haystack = " || ' ' || ".join(f"COALESCE({column}, '')" for column in columns)
    for term in terms:
        clauses.append(f"LOWER({haystack}) LIKE ? ESCAPE '\\'")
        params.append(_like(term))
    return " AND ".join(clauses), params


def snippet_around(text: str, terms: List[str], radius: int = SNIPPET_RADIUS) -> str:
    """
    The stretch of text around the first matched term, on one line.

    Plain text only. The interface highlights the terms itself, so nothing
    here is markup and nothing a row contains is ever interpreted.
    """
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if not flat:
        return ""
    lower = flat.lower()
    positions = [lower.find(term) for term in terms if lower.find(term) != -1]
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


def search_posts(terms: List[str], limit: int = 6, conn=None) -> List[Dict[str, Any]]:
    if not terms:
        return []
    own = conn is None
    conn = conn or get_db()
    try:
        where, params = _all_terms_in(["content", "tags"], terms)
        rows = conn.execute(
            f"""
            SELECT id, content, status, scheduled_for, published_at, created_at
            FROM posts
            WHERE {where}
            ORDER BY COALESCE(published_at, scheduled_for, created_at) DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        results = []
        for row in rows:
            status = row["status"] or "draft"
            when = row["published_at"] or row["scheduled_for"] or row["created_at"] or ""
            # The first line is the title, so the snippet reads from the rest
            # of the post. Otherwise every result printed its title twice.
            lines = str(row["content"] or "").strip().splitlines()
            body = "\n".join(lines[1:]).strip()
            results.append({
                "kind": "post",
                "id": str(row["id"]),
                "title": _first_line(row["content"]) or "Untitled post",
                "snippet": snippet_around(body or row["content"], terms),
                "meta": f"{status.upper()}" + (f"  {str(when)[:10]}" if when else ""),
                "status": status,
                "opens": destination_for_post(status, row["scheduled_for"]),
            })
        return results
    finally:
        if own:
            conn.close()


def search_leads(terms: List[str], limit: int = 6, conn=None) -> List[Dict[str, Any]]:
    """
    People, matched on who they are or on what they said.

    A comment someone left is often the thing you remember about them, so the
    interactions table is searched too, and a lead found that way shows the
    comment rather than their headline.
    """
    if not terms:
        return []
    own = conn is None
    conn = conn or get_db()
    try:
        where, params = _all_terms_in(
            ["l.full_name", "l.name", "l.company", "l.headline", "l.notes", "i.comment_text"], terms
        )
        rows = conn.execute(
            f"""
            SELECT l.id, l.full_name, l.name, l.company, l.headline, l.lead_status, l.status,
                   GROUP_CONCAT(i.comment_text, ' ') AS comments
            FROM leads l
            LEFT JOIN lead_interactions i ON i.lead_id = l.id
            WHERE {where}
            GROUP BY l.id
            ORDER BY l.updated_at DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
        results = []
        for row in rows:
            who = row["full_name"] or row["name"] or "Unnamed lead"
            about = " ".join(part for part in (row["headline"], row["company"]) if part)
            profile_hit = all(term in f"{who} {about}".lower() for term in terms)
            said = row["comments"] or ""
            results.append({
                "kind": "lead",
                "id": str(row["id"]),
                "title": who,
                "snippet": snippet_around(about, terms) if profile_hit or not said
                           else "Commented: " + snippet_around(said, terms),
                "meta": (row["lead_status"] or row["status"] or "").replace("_", " ").upper(),
                "opens": "leads",
            })
        return results
    finally:
        if own:
            conn.close()
