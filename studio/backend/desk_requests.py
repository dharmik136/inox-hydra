"""
Desk requests: a post the phone asked the desk to read.
=======================================================

The phone cannot read LinkedIn's analytics: no extension runs inside the
LinkedIn app, and the studio answers on loopback only. What the phone can do
is say which post to read next. A LinkedIn post link shared to the Telegram
bot (ingress.py) becomes one row here, in one of six states:

  open       one of the creator's own posts, waiting: Today offers the
             oldest one (today._phone_request_rule)
  read       that post's own analytics page was read after it was asked,
             which is the observation the extension records under source
             'post_analytics'
  expired    a week passed and nobody read it
  dismissed  the creator said Not now on Today
  done       the creator said Done on Today, for a short link whose post
             was never reported
  refused    the link names no post of the creator's. The studio reads only
             the creator's own pages, so it is recorded with its reason, for
             the Telegram panel to show, and never offered on Today

A request is for an activity URN the studio holds, because a post's
analytics page is opened by its activity id. A share or ugcPost id, a post
the studio has never seen, and someone else's post are all refused.

A short link (the LinkedIn app's Copy link gives an lnkd.in/p/<code>
address) names no post, and the studio never fetches it to find out. It is kept in
`link`, open, with activity_urn '' until the post it opens is known. Today
opens it in the creator's browser with #inox-desk-<id>; a browser keeps a
fragment across lnkd.in's redirect, so the extension, on the post page it
lands on, reports the request id with that post (landed). One of the
creator's posts is attached and the request goes on like any other; a post
of anyone else's refuses it. When nothing reports, because LinkedIn's own
routing dropped the fragment, the creator's Done completes it.

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

OPEN, READ, EXPIRED, DISMISSED, DONE, REFUSED = "open", "read", "expired", "dismissed", "done", "refused"

# What became of a link, in the Telegram panel's words.
SAID = {
    OPEN: "Waiting: Today asks you to open its analytics page at this computer.",
    READ: "Read at the desk.",
    EXPIRED: "Closed after a week unread.",
    DISMISSED: "You said Not now on Today.",
    DONE: "You said Done on Today.",
    REFUSED: NOT_YOURS,
}
SAID_SHORT = ("Waiting: Today asks you to open the link at this computer, where your browser finds which post "
              "it is.")

# Today opens a short link with this fragment, which the page it lands on
# keeps, so the extension can say which request the post answers.
FRAGMENT = "#inox-desk-{id}"

FIELDS = ("id", "activity_urn", "asked_at", "done_at", "note", "source", "state", "link")


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
            "note": note, "source": source, "state": state, "link": None, "known_post": known}


def record_short(conn, link: str, source: str = SOURCE_TELEGRAM) -> Dict[str, Any]:
    """
    Writes a short link as an open request with no post yet. Which post it
    is becomes known in the creator's browser (landed), or never, and then
    the creator's Done closes it. Nothing here follows the link.
    """
    asked_at = _now().isoformat()
    with conn:
        cursor = conn.execute(
            "INSERT INTO desk_requests (activity_urn, asked_at, done_at, note, source, state, link) "
            "VALUES ('', ?, NULL, NULL, ?, ?, ?)", (asked_at, source, OPEN, link))
    changes.publish("desk")
    return {"id": cursor.lastrowid, "activity_urn": "", "asked_at": asked_at, "done_at": None, "note": None,
            "source": source, "state": OPEN, "link": link, "known_post": False}


def waits_for_its_post(request: Dict[str, Any]) -> bool:
    """A short link whose post is not known yet."""
    return bool(request.get("link")) and not request.get("activity_urn")


def open_url(request: Dict[str, Any]) -> str:
    """The short link as Today opens it, with the fragment the page it lands on keeps."""
    return str(request["link"]) + FRAGMENT.format(id=int(request["id"]))


def landed(conn, request_id: int, activity_urn: str) -> Dict[str, Any]:
    """
    The extension saw the page a short link landed on, carrying this
    request's fragment. One of the creator's posts is attached, and the
    request goes on like any other; anyone else's post refuses it, as a full
    link to it would have been. An id that is not an activity id names no
    post the studio can open, so nothing is attached and the creator's Done
    stays the way to close it. Only an open request still waiting for its
    post moves.
    """
    row = conn.execute(f"SELECT {', '.join(FIELDS)} FROM desk_requests WHERE id = ?", (request_id,)).fetchone()
    if not row or row["state"] != OPEN or not waits_for_its_post(_row(row)):
        return {"attached": False, "state": row["state"] if row else None,
                "said": "No request from your phone is waiting for this post."}
    urn = (activity_urn or "").strip()
    if not urn.startswith("urn:li:activity:"):
        return {"attached": False, "state": OPEN,
                "said": "This page does not say which post it is by its activity id. Press Done on Today once "
                        "you have seen it."}
    if not known_post(conn, urn):
        with conn:
            conn.execute("UPDATE desk_requests SET activity_urn = ?, state = ?, done_at = ?, note = ? "
                         "WHERE id = ? AND state = ?", (urn, REFUSED, _now().isoformat(), NOT_YOURS, request_id, OPEN))
        changes.publish("desk")
        return {"attached": False, "state": REFUSED, "said": NOT_YOURS}
    with conn:
        conn.execute("UPDATE desk_requests SET activity_urn = ? WHERE id = ? AND state = ? AND activity_urn = ''",
                     (urn, request_id, OPEN))
    changes.publish("desk")
    return {"attached": True, "state": OPEN, "activity_urn": urn,
            "said": "Today now asks you to open this post's analytics."}


def done(conn, request_id: int) -> bool:
    """
    The creator's Done on Today, for a short link whose post was never
    reported. A request that names its post is done when that post's
    analytics page is read, not by a press. Returns whether one was closed.
    """
    with conn:
        changed = conn.execute(
            "UPDATE desk_requests SET state = ?, done_at = ? WHERE id = ? AND state = ? AND link IS NOT NULL "
            "AND activity_urn = ''", (DONE, _now().isoformat(), request_id, OPEN)).rowcount
    if changed:
        changes.publish("desk")
    return changed > 0


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
    return [{**_row(r), "said": SAID_SHORT if r["state"] == OPEN and waits_for_its_post(_row(r))
             else SAID.get(r["state"], "")} for r in rows]


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
