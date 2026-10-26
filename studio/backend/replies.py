"""
Replies: who commented on my posts that I have not answered, oldest-seen first?
==============================================================================

Today lists five people. Every comment on the creator's own posts is held in
lead_interactions, and none of the screens showed the whole set: only one
person at a time in the dossier, or one post at a time. This lists every
comment in the window, grouped by post, oldest seen first, which is the order
of a queue: the comment that has waited longest comes first.

The rules are Today's (today.py), so the two screens agree:

  - only comments, because a reaction leaves nothing to reply to;
  - only on the creator's own posts (onboarding._own_activity_ids);
  - only comments the studio first saw inside the window, 14 days unless the
    creator asks for another;
  - not from a lead whose status says the creator already answered them
    (today.ANSWERED_STATUSES: Outreach Sent, Connected, Meeting Booked).

What Today does not have is the creator's own mark. Whether a creator replied
to a comment is not something the bridge reads, so the only honest
"answered" is the one they set, a row in reply_marks keyed the way
lead_interactions keys a comment. MARKED_AT is the one statement of "this
comment is marked answered"; Today's list reads it too, so a comment marked
here leaves Today as well.

A comment's time is when the studio first saw it: crm.py stamps the row with
CURRENT_TIMESTAMP when the bridge reads the page, and LinkedIn's own time is
not captured. The screen says "seen by the studio", never "commented at".

Nothing here orders people by a score: the order is when each comment was
first seen.

Strict Invariants:
- Zero em-dashes.
- No network request.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import onboarding, post_identity
    from .database import get_db
    from .text_cut import clip
except ImportError:
    import onboarding
    import post_identity
    from database import get_db
    from text_cut import clip

# How many comments one page of the route carries, and the most a caller may
# ask for. The page is of comments rather than of posts, because one post can
# hold a few hundred comments in a fortnight.
PAGE = 30
PAGE_MAX = 100

# The longest window a creator can ask for. Fourteen days is Today's.
WINDOW_MAX_DAYS = 90

# The window the empty list's "answered" count covers.
ANSWERED_RECENT = timedelta(days=7)

# The one statement of "this comment is marked answered": the time the
# creator marked it, or NULL. Formatted with the alias of lead_interactions.
MARKED_AT = (
    "(SELECT m.marked_at FROM reply_marks m WHERE m.lead_id = CAST({i}.lead_id AS TEXT) "
    "AND m.post_urn = COALESCE({i}.post_urn, '') AND m.comment_key = {i}.comment_key)"
)

VIEWS = ("waiting", "answered")


class UnknownComment(LookupError):
    """A mark for a comment the studio does not hold."""


def _today():
    # Imported here, not at the top: today.py reads MARKED_AT from this module.
    try:
        from . import today
    except ImportError:
        import today
    return today


def default_days() -> int:
    return _today().REPLY_WINDOW.days


def _since(days: int) -> str:
    # The form crm.py stores (CURRENT_TIMESTAMP), as Today compares it.
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _comments(conn, days: int) -> List[Dict[str, Any]]:
    """Every comment that counts for Replies in the window, marked or not."""
    today = _today()
    own_ids = onboarding._own_activity_ids(conn)
    if not own_ids:
        return []
    rows = conn.execute(
        f"""
        SELECT i.id, CAST(i.lead_id AS TEXT) AS lead_id, i.post_urn, i.comment_key, i.comment_text,
               COALESCE(i.first_seen_at, i.interacted_at) AS seen_at,
               COALESCE(l.full_name, l.name) AS name, l.headline, l.lead_status,
               {MARKED_AT.format(i="i")} AS marked_at
        FROM lead_interactions i JOIN leads l ON l.id = CAST(i.lead_id AS TEXT)
        WHERE COALESCE(i.first_seen_at, i.interacted_at) >= ? AND i.interaction_type = 'COMMENT'
        """, (_since(days),)).fetchall()
    found = []
    for row in rows:
        post_id = onboarding._activity_id(row["post_urn"])
        if not post_id or post_id not in own_ids:
            continue
        if (row["lead_status"] or "").upper() in today.ANSWERED_STATUSES:
            continue
        found.append({
            "id": row["id"],
            "lead_id": row["lead_id"],
            "post_urn": row["post_urn"] or "",
            "post_id": post_id,
            "comment_key": row["comment_key"] or "",
            "comment_text": clip(row["comment_text"], 1000) if row["comment_text"] else None,
            "seen_at": row["seen_at"],
            "name": row["name"],
            "headline": clip(row["headline"], 160) if row["headline"] else None,
            "marked_at": row["marked_at"],
        })
    return found


def _posts(conn) -> Dict[str, Dict[str, Any]]:
    """The creator's posts by activity id: the opening, when, and a link LinkedIn will answer."""
    posts: Dict[str, Dict[str, Any]] = {}
    for row in conn.execute("SELECT activity_urn, text, published_at FROM own_posts"):
        post_id = onboarding._activity_id(row["activity_urn"])
        if not post_id:
            continue
        entry = posts.setdefault(post_id, {"activity_urn": None, "excerpt": None, "published_at": None})
        if row["activity_urn"].startswith("urn:li:activity:") or entry["activity_urn"] is None:
            entry["activity_urn"] = row["activity_urn"]
        if row["text"] and not entry["excerpt"]:
            entry["excerpt"] = clip(" ".join(row["text"].split()), 160)
        entry["published_at"] = entry["published_at"] or row["published_at"]
    for row in conn.execute("SELECT activity_urn, content FROM posts WHERE activity_urn IS NOT NULL"):
        post_id = onboarding._activity_id(row["activity_urn"])
        if post_id and post_id in posts and not posts[post_id]["excerpt"] and row["content"]:
            posts[post_id]["excerpt"] = clip(" ".join(row["content"].split()), 160)
    return posts


def _ordered(comments: List[Dict[str, Any]], view: str) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Groups by post. Waiting: posts by their oldest comment, and each post's
    comments oldest first. Answered: the most recent mark first.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for comment in comments:
        groups.setdefault(comment["post_id"], []).append(comment)
    if view == "answered":
        for items in groups.values():
            items.sort(key=lambda c: (c["marked_at"] or "", c["id"]), reverse=True)
        return sorted(groups.items(), key=lambda g: g[1][0]["marked_at"] or "", reverse=True)
    for items in groups.values():
        items.sort(key=lambda c: (c["seen_at"] or "", c["id"]))
    return sorted(groups.items(), key=lambda g: (g[1][0]["seen_at"] or "", g[1][0]["id"]))


def _answered_recently(conn) -> int:
    since = (datetime.now(timezone.utc) - ANSWERED_RECENT).isoformat()
    return conn.execute("SELECT COUNT(*) FROM reply_marks WHERE marked_at >= ?", (since,)).fetchone()[0]


def waiting_count(conn, days: Optional[int] = None) -> int:
    """How many comments are waiting in the window: the count Today shows."""
    return sum(1 for c in _comments(conn, days or default_days()) if not c["marked_at"])


def overview(days: Optional[int] = None, view: str = "waiting", offset: int = 0,
             limit: int = PAGE) -> Dict[str, Any]:
    """One page of the comments in the view, grouped by post, with the counts for the whole window."""
    days = days or default_days()
    view = view if view in VIEWS else "waiting"
    limit = max(1, min(int(limit), PAGE_MAX))
    offset = max(0, int(offset))
    known = bool(onboarding.confirmed_vanity())
    conn = get_db()
    try:
        comments = _comments(conn, days) if known else []
        posts = _posts(conn) if comments else {}
        answered_recently = _answered_recently(conn)
    finally:
        conn.close()

    waiting = [c for c in comments if not c["marked_at"]]
    answered = [c for c in comments if c["marked_at"]]
    chosen = waiting if view == "waiting" else answered
    ordered = _ordered(chosen, view)
    flat = [(post_id, comment) for post_id, items in ordered for comment in items]
    page = flat[offset:offset + limit]

    per_post = {post_id: len(items) for post_id, items in ordered}
    waiting_by_post: Dict[str, int] = {}
    for comment in waiting:
        waiting_by_post[comment["post_id"]] = waiting_by_post.get(comment["post_id"], 0) + 1
    answered_by_post: Dict[str, int] = {}
    for comment in answered:
        answered_by_post[comment["post_id"]] = answered_by_post.get(comment["post_id"], 0) + 1

    groups: List[Dict[str, Any]] = []
    for post_id, comment in page:
        if not groups or groups[-1]["post_id"] != post_id:
            post = posts.get(post_id, {})
            urn = post.get("activity_urn") or comment["post_urn"]
            groups.append({
                "post_id": post_id,
                "activity_urn": urn,
                "excerpt": post.get("excerpt"),
                "published_at": post.get("published_at"),
                "url": post_identity.linkedin_permalink(urn),
                "in_view": per_post[post_id],
                "waiting": waiting_by_post.get(post_id, 0),
                "answered": answered_by_post.get(post_id, 0),
                "comments": [],
            })
        groups[-1]["comments"].append({key: comment[key] for key in (
            "lead_id", "post_urn", "comment_key", "comment_text", "seen_at", "name", "headline", "marked_at")})

    following = offset + len(page)
    return {
        "status": "success",
        "identity_known": known,
        "view": view,
        "window": {"days": days, "label": f"last {days} days", "since": _since(days)},
        "counts": {
            "waiting": len(waiting),
            "people": len({c["lead_id"] for c in waiting}),
            "posts": len(waiting_by_post),
            "answered_in_window": len(answered),
            "answered_last_7_days": answered_recently,
        },
        "offset": offset,
        "limit": limit,
        "total": len(flat),
        "next_offset": following if following < len(flat) else None,
        "posts": groups,
    }


def _the_comment(conn, lead_id: str, post_urn: str, comment_key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM lead_interactions WHERE lead_id = ? AND COALESCE(post_urn, '') = ? "
        "AND interaction_type = 'COMMENT' AND comment_key = ?",
        (lead_id, post_urn, comment_key)).fetchone() is not None


def mark(lead_id: str, post_urn: str, comment_key: str) -> Dict[str, Any]:
    """The creator says they answered this comment. Marking twice keeps the first time."""
    conn = get_db()
    try:
        with conn:
            if not _the_comment(conn, lead_id, post_urn or "", comment_key or ""):
                raise UnknownComment("The studio holds no such comment.")
            conn.execute(
                "INSERT OR IGNORE INTO reply_marks (lead_id, post_urn, comment_key, marked_at) VALUES (?, ?, ?, ?)",
                (lead_id, post_urn or "", comment_key or "", datetime.now(timezone.utc).isoformat()))
            marked_at = conn.execute(
                "SELECT marked_at FROM reply_marks WHERE lead_id = ? AND post_urn = ? AND comment_key = ?",
                (lead_id, post_urn or "", comment_key or "")).fetchone()[0]
    finally:
        conn.close()
    return {"status": "success", "marked_at": marked_at}


def unmark(lead_id: str, post_urn: str, comment_key: str) -> Dict[str, Any]:
    """The creator takes the mark back: the comment is waiting again."""
    conn = get_db()
    try:
        with conn:
            removed = conn.execute(
                "DELETE FROM reply_marks WHERE lead_id = ? AND post_urn = ? AND comment_key = ?",
                (lead_id, post_urn or "", comment_key or "")).rowcount
    finally:
        conn.close()
    return {"status": "success", "removed": removed}
