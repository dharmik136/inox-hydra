"""
Desk requests: a post the phone asked the desk to read.
=======================================================

The phone cannot read LinkedIn's analytics: no extension runs inside the
LinkedIn app, and the studio answers on loopback only. What the phone can do
is say which post to read next. A LinkedIn post link shared to the Telegram
bot (ingress.py) becomes one row here, in one of five states:

  open       one of the creator's own posts, waiting: Today offers the
             oldest one (today._phone_request_rule)
  read       that post's own analytics page was read after it was asked,
             which is the observation the extension records under source
             'post_analytics'
  expired    a week passed and nobody read it
  dismissed  the creator said Not now on Today
  refused    the link names no post of the creator's. The studio reads only
             the creator's own pages, so it is recorded with its reason, for
             the Telegram panel to show, and never offered on Today

A request is for an activity URN the studio holds, because a post's
analytics page is opened by its activity id. A share or ugcPost id, a post
the studio has never seen, and someone else's post are all refused.

Strict Invariants:
- Zero em-dashes.
- Zero egress: reads and writes the local database only.
- Nothing invented: a request names a URN the phone sent, never a guess.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import changes, post_identity
except ImportError:
    import changes
    import post_identity

# Why a link is refused, as the Telegram panel says it.
NOT_YOURS = ("Not one of your posts: the studio reads only your own posts, and this link does not name one it "
             "holds. If it is yours and new, run Posts you wrote in Setup's step 5, then share the link again.")

# How long a request waits to be read at the desk before it is closed unread.
REQUEST_TTL = timedelta(days=7)
EXPIRED_NOTE = "Not read at the desk within a week of being asked, so it was closed."

SOURCE_TELEGRAM = "telegram"

OPEN, READ, EXPIRED, DISMISSED, REFUSED = "open", "read", "expired", "dismissed", "refused"

# What became of a link, in the Telegram panel's words.
SAID = {
    OPEN: "Waiting: Today asks you to open its analytics page at this computer.",
    READ: "Read at the desk.",
    EXPIRED: "Closed after a week unread.",
    DISMISSED: "You said Not now on Today.",
    REFUSED: NOT_YOURS,
}

FIELDS = ("id", "activity_urn", "asked_at", "done_at", "note", "source", "state")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def analytics_url(activity_urn: str) -> Optional[str]:
    """The post's own analytics page, which only its author can open; None for a local key."""
    if not post_identity.linkedin_permalink(activity_urn):
        return None
    return f"https://www.linkedin.com/analytics/post-summary/{activity_urn}/"


def known_post(conn, activity_urn: str) -> bool:
    """Whether the URN is an activity URN of one of the creator's recorded posts."""
    if not (activity_urn or "").startswith("urn:li:activity:"):
        return False
    return bool(conn.execute("SELECT 1 FROM own_posts WHERE activity_urn = ?", (activity_urn,)).fetchone())


def _row(row) -> Dict[str, Any]:
    return {field: row[field] for field in FIELDS}


def record(conn, activity_urn: str, source: str = SOURCE_TELEGRAM) -> Dict[str, Any]:
    """
    Writes one link and returns it: open for one of the creator's own posts,
    refused, with its reason and closed at once, for anything else.
    """
    known = known_post(conn, activity_urn)
    asked_at = _now().isoformat()
    state, done_at, note = (OPEN, None, None) if known else (REFUSED, asked_at, NOT_YOURS)
    with conn:
        cursor = conn.execute(
            "INSERT INTO desk_requests (activity_urn, asked_at, done_at, note, source, state) VALUES (?, ?, ?, ?, ?, ?)",
            (activity_urn, asked_at, done_at, note, source, state),
        )
    changes.publish("desk")
    return {"id": cursor.lastrowid, "activity_urn": activity_urn, "asked_at": asked_at, "done_at": done_at,
            "note": note, "source": source, "state": state, "known_post": known}


def open_requests(conn) -> List[Dict[str, Any]]:
    """Every open request, oldest first."""
    rows = conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM desk_requests WHERE state = ? ORDER BY asked_at, id", (OPEN,)).fetchall()
    return [_row(r) for r in rows]


def open_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM desk_requests WHERE state = ?", (OPEN,)).fetchone()[0]


def recent(conn, limit: int = 5) -> List[Dict[str, Any]]:
    """The newest links, newest first, each with what became of it in the panel's words."""
    rows = conn.execute(
        f"SELECT {', '.join(FIELDS)} FROM desk_requests ORDER BY asked_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [{**_row(r), "said": SAID.get(r["state"], "")} for r in rows]


def dismiss(conn, request_id: int) -> bool:
    """The creator said Not now on Today. Returns whether an open request was closed."""
    with conn:
        changed = conn.execute(
            "UPDATE desk_requests SET state = ?, done_at = ? WHERE id = ? AND state = ?",
            (DISMISSED, _now().isoformat(), request_id, OPEN)).rowcount
    return changed > 0


def close_refused(conn, request_id: int) -> None:
    """An open request whose post the studio no longer holds is refused, with the reason."""
    with conn:
        conn.execute("UPDATE desk_requests SET state = ?, done_at = ?, note = ? WHERE id = ? AND state = ?",
                     (REFUSED, _now().isoformat(), NOT_YOURS, request_id, OPEN))


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
        WHERE d.state = 'open'
        GROUP BY d.id
        """).fetchall()
    read_ids = {row["id"] for row in read}
    expired = [row["id"] for row in conn.execute(
        "SELECT id FROM desk_requests WHERE state = ? AND asked_at < ?",
        (OPEN, (moment - REQUEST_TTL).isoformat())) if row["id"] not in read_ids]
    if read or expired:
        with conn:
            for row in read:
                conn.execute("UPDATE desk_requests SET state = ?, done_at = ? WHERE id = ? AND state = ?",
                             (READ, row["read_at"], row["id"], OPEN))
            for request_id in expired:
                conn.execute(
                    "UPDATE desk_requests SET state = ?, done_at = ?, note = CASE WHEN note IS NULL OR note = '' "
                    "THEN ? ELSE note || ' ' || ? END WHERE id = ? AND state = ?",
                    (EXPIRED, stamp, EXPIRED_NOTE, EXPIRED_NOTE, request_id, OPEN))
        changes.derived_written()
    return {"read": len(read), "expired": len(expired)}


def oldest_open(conn) -> Optional[Dict[str, Any]]:
    """The request that has waited longest, or None."""
    requests = open_requests(conn)
    return requests[0] if requests else None


def forget(conn) -> None:
    """Every request, for when the creator deletes what the studio holds about them."""
    conn.execute("DELETE FROM desk_requests")
