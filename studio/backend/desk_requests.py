"""
Desk requests: a post the phone asked the desk to read.
=======================================================

The phone cannot read LinkedIn's analytics: no extension runs inside the
LinkedIn app, and the studio answers on loopback only. What the phone can do
is say which post to read next. A LinkedIn post link shared to the Telegram
bot (ingress.py) becomes one row here; Today surfaces the oldest open one as
the page to open (today._phone_request_rule); and it is done once that
post's own analytics page has been read after it was asked, which is the
observation the extension records under source 'post_analytics'.

A link to a post the studio does not hold is still recorded, with the same
refusal sentence the analytics ingest uses, so Today can say what to do
rather than invent a post. A request nobody acted on for a week is closed
with a note, so a post that was never the creator's cannot stand in front of
the latest-post rule for good.

Strict Invariants:
- Zero em-dashes.
- Zero egress: reads and writes the local database only.
- Nothing invented: a request names a URN the phone sent, never a guess.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import post_identity
except ImportError:
    import post_identity

# The sentence onboarding.ingest_post_analytics refuses with; the same words
# here, so a request for an unknown post says what the reading would have.
UNKNOWN_POST = "this post is not one of your recorded posts; import your posts first"

# How long a request waits to be read at the desk before it is closed unread.
REQUEST_TTL = timedelta(days=7)
EXPIRED_NOTE = "Not read at the desk within a week of being asked, so it was closed."

SOURCE_TELEGRAM = "telegram"

FIELDS = ("id", "activity_urn", "asked_at", "done_at", "note", "source")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def analytics_url(activity_urn: str) -> Optional[str]:
    """The post's own analytics page, which only its author can open; None for a local key."""
    if not post_identity.linkedin_permalink(activity_urn):
        return None
    return f"https://www.linkedin.com/analytics/post-summary/{activity_urn}/"


def known_post(conn, activity_urn: str) -> bool:
    """Whether the post is one of the creator's recorded posts."""
    return bool(conn.execute("SELECT 1 FROM own_posts WHERE activity_urn = ?", (activity_urn,)).fetchone())


def _row(row) -> Dict[str, Any]:
    return {field: row[field] for field in FIELDS}


def record(conn, activity_urn: str, source: str = SOURCE_TELEGRAM, note: Optional[str] = None) -> Dict[str, Any]:
    """
    Writes one request and returns it. A post the studio does not hold gets
    the refusal sentence as its note; `known_post` says which it was.
    """
    known = known_post(conn, activity_urn)
    if note is None and not known:
        note = UNKNOWN_POST
    asked_at = _now().isoformat()
    with conn:
        cursor = conn.execute(
            "INSERT INTO desk_requests (activity_urn, asked_at, done_at, note, source) VALUES (?, ?, NULL, ?, ?)",
            (activity_urn, asked_at, note, source),
        )
    return {"id": cursor.lastrowid, "activity_urn": activity_urn, "asked_at": asked_at, "done_at": None,
            "note": note, "source": source, "known_post": known}


def open_requests(conn) -> List[Dict[str, Any]]:
    """Every request not yet done, oldest first."""
    rows = conn.execute(
        "SELECT id, activity_urn, asked_at, done_at, note, source FROM desk_requests "
        "WHERE done_at IS NULL ORDER BY asked_at, id").fetchall()
    return [_row(r) for r in rows]


def open_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM desk_requests WHERE done_at IS NULL").fetchone()[0]


def settle(conn, now: Optional[datetime] = None) -> Dict[str, int]:
    """
    Closes what has been answered or has waited too long. Returns the counts.

    Done when the post's own analytics page was read after the request was
    made: an observation under source 'post_analytics' with observed_at past
    asked_at. Expired when asked more than REQUEST_TTL ago, with a note that
    says so, so the row still tells the story.

    Found by reading first and written only when there is something to
    close, because Today asks on every refresh, and a write there would take
    the database's write lock on a read path the captures contend with.
    """
    moment = now or _now()
    stamp = moment.isoformat()
    read = conn.execute(
        """
        SELECT d.id AS id, MIN(o.observed_at) AS read_at
        FROM desk_requests d JOIN post_metric_observations o
          ON o.activity_urn = d.activity_urn AND o.source = 'post_analytics' AND o.observed_at > d.asked_at
        WHERE d.done_at IS NULL
        GROUP BY d.id
        """).fetchall()
    read_ids = {row["id"] for row in read}
    expired = [row["id"] for row in conn.execute(
        "SELECT id FROM desk_requests WHERE done_at IS NULL AND asked_at < ?",
        ((moment - REQUEST_TTL).isoformat(),)) if row["id"] not in read_ids]
    if read or expired:
        with conn:
            for row in read:
                conn.execute("UPDATE desk_requests SET done_at = ? WHERE id = ? AND done_at IS NULL",
                             (row["read_at"], row["id"]))
            for request_id in expired:
                conn.execute(
                    "UPDATE desk_requests SET done_at = ?, note = CASE WHEN note IS NULL OR note = '' THEN ? "
                    "ELSE note || ' ' || ? END WHERE id = ? AND done_at IS NULL",
                    (stamp, EXPIRED_NOTE, EXPIRED_NOTE, request_id))
    return {"read": len(read), "expired": len(expired)}


def oldest_open(conn) -> Optional[Dict[str, Any]]:
    """The request that has waited longest, or None."""
    requests = open_requests(conn)
    return requests[0] if requests else None


def forget(conn) -> None:
    """Every request, for when the creator deletes what the studio holds about them."""
    conn.execute("DELETE FROM desk_requests")
