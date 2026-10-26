"""
Today: what to do in the next hour.
===================================

The screen a creator opens first once the studio knows who they are. It
answers one question, and every section is something they can act on now:

  who to reply to   people who commented on your posts and have not heard
                    from you, repeat engagers first, then the most recent
  your latest post  how it is doing against your usual, at the same age
  the queue         posts that are due to post now, what goes out next,
                    and the next open slot
  one page to open  the single LinkedIn page most worth opening right now

What it will not do is rank people by the ICP score. That number is a keyword
guess about a job title; who engaged with you twice this week is a fact.

Strict Invariants:
- Zero em-dashes.
- Every comparison states how many posts it rests on, and says so when too few.
- No network request. Everything here is read from what the extension captured.
"""

import json
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from .text_cut import clip
except ImportError:
    from text_cut import clip

try:
    from . import desk_requests, onboarding, post_identity, post_summary, results
    from .database import get_db
except ImportError:
    import desk_requests
    import onboarding
    import post_identity
    import post_summary
    import results
    from database import get_db

# People are listed while their engagement is recent enough to answer.
REPLY_WINDOW = timedelta(days=14)
REPLY_LIMIT = 5

# Lead statuses that mean the creator has already responded.
ANSWERED_STATUSES = ("DM_SENT", "ENGAGED", "CONVERTED")

# Posts are compared at the same age, because a post read at six hours and one
# read at six weeks say nothing about each other. Two days is when most of a
# post's reach has arrived, and the window either side tolerates reading gaps.
# The summary keeps each post's reading at this age, so the numbers live there.
COMPARE_AT_HOURS = post_summary.READING_AT_HOURS
COMPARE_WINDOW = post_summary.READING_WINDOW
COMPARE_WITH = 20
MIN_COMPARISONS = 3

COMPARED_METRICS = ("impressions", "reactions", "comments")

# Due posts listed on Today; the Queue lists every one.
DUE_LIMIT = 10


def _latest_post(conn) -> Optional[Dict[str, Any]]:
    # A post published from the studio has a publication record from the
    # moment it goes out, under a local key, because every other surface needs
    # to see it. This card is how LinkedIn read the post against the creator's
    # own history, and LinkedIn has not seen it yet, so it stays out of here
    # and _marked_published names it instead.
    posts = conn.execute(
        "SELECT activity_urn, text, published_at FROM own_posts WHERE published_at IS NOT NULL "
        "AND activity_urn NOT LIKE ? ORDER BY published_at DESC LIMIT ?",
        (post_identity.LOCAL_URN_PREFIX + "%", COMPARE_WITH + 1)).fetchall()
    if not posts:
        return None

    # Each post's reading closest to two days old, and its latest, from the
    # per-post summary rather than from every reading of 21 posts.
    readings = post_summary.current(conn, [p["activity_urn"] for p in posts])

    def at_age(urn: str) -> Optional[Dict[str, Any]]:
        return post_summary.reading_of(readings.get(urn), "reading_48h")

    latest, earlier = posts[0], posts[1:]
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["published_at"])).total_seconds() / 3600.0
    own = at_age(latest["activity_urn"])
    # How the post is doing now, from results.figures, which every screen
    # reads. This showed the two day old reading as the post's current
    # figures, so one post read 19,943 impressions here and 50,118 on Posts
    # and Analytics in the same minute. The two day reading is still what the
    # comparison below is made at, and it says so.
    current = results.figures(conn, [latest["activity_urn"]]).get(latest["activity_urn"])

    usual_readings = [r for r in (at_age(p["activity_urn"]) for p in earlier) if r]
    comparison = None
    if own and len(usual_readings) >= MIN_COMPARISONS:
        comparison = {}
        for metric in COMPARED_METRICS:
            theirs = [r[metric] for r in usual_readings if r[metric] is not None]
            if own[metric] is None or len(theirs) < MIN_COMPARISONS:
                continue
            usual = statistics.median(theirs)
            comparison[metric] = {
                "this_post": own[metric],
                "your_usual": usual,
                "posts_compared": len(theirs),
                "ratio": round(own[metric] / usual, 2) if usual else None,
            }

    if comparison:
        verdict = None
    elif age < COMPARE_WINDOW[0]:
        verdict = f"too new to compare: posts are compared at about two days old, and this one is {age:.0f} hours"
    elif not own and age <= COMPARE_WINDOW[1]:
        verdict = "not read yet at about two days old; open its analytics page now and it can be compared"
    elif not own:
        # Past the window, reading it now cannot help: the comparison is at two
        # days old, and that moment has gone. Found on a live install, where the
        # screen told the creator to open a 13 day old post's analytics.
        verdict = ("not read while it was about two days old, so it cannot be compared fairly. "
                   "Today asks you to open each new post's analytics in its first three days, "
                   "so your next post will be")
    else:
        verdict = (f"only {len(usual_readings)} of your earlier posts were read at about two days old; "
                   f"{MIN_COMPARISONS} are needed before a comparison means anything")

    return {
        "activity_urn": latest["activity_urn"],
        "excerpt": clip(" ".join((latest["text"] or "").split()), 160) or None,
        "published_at": latest["published_at"],
        "age_hours": round(age, 1),
        "current": current,
        "comparison": comparison or None,
        "not_compared_because": verdict,
        # None for a post published from the studio and not yet seen on
        # LinkedIn: it is recorded under a local key, and a link built from
        # that key would 404.
        "url": post_identity.linkedin_permalink(latest["activity_urn"]),
        "analytics_url": (f"https://www.linkedin.com/analytics/post-summary/{latest['activity_urn']}/"
                          if post_identity.linkedin_permalink(latest["activity_urn"]) else None),
    }


def _marked_published(conn, latest: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    The newest post marked published in the studio that the bridge has not yet
    seen on LinkedIn, when it is newer than the latest post the bridge has.

    "Your latest post" reads only what the bridge read, so right after Mark as
    published it went on showing a post from months before, while Analytics
    and search already had the new one. Today now says which post is waiting.
    """
    row = conn.execute(
        "SELECT id, content, published_at FROM posts WHERE status = 'published' AND activity_urn IS NULL "
        "AND published_at IS NOT NULL ORDER BY published_at DESC LIMIT 1").fetchone()
    if not row:
        return None
    try:
        marked = datetime.fromisoformat(row["published_at"])
        if marked.tzinfo is None:
            marked = marked.replace(tzinfo=timezone.utc)
        if latest and latest.get("published_at"):
            seen = datetime.fromisoformat(latest["published_at"])
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=timezone.utc)
            if seen >= marked:
                return None
    except (TypeError, ValueError):
        return None
    return {"post_id": row["id"], "published_at": row["published_at"],
            "excerpt": " ".join((row["content"] or "").split())[:160] or None}


def _reply_to(conn) -> List[Dict[str, Any]]:
    own_ids = onboarding._own_activity_ids(conn)
    if not own_ids:
        return []
    since = (datetime.now(timezone.utc) - REPLY_WINDOW).strftime("%Y-%m-%d %H:%M:%S")
    # When an engagement happened is when the studio first saw it. last_seen_at
    # moves every time the post is reopened and the same comment read again,
    # which made a comment from 13 days ago read "JUST NOW" and jump the queue.
    #
    # The window is read through idx_interactions_engaged, and each row finds
    # its lead by the leads primary key. Joined as l.id = i.lead_id, the
    # INTEGER affinity of lead_interactions.lead_id made SQLite scan all
    # 49,142 leads and probe each one's interactions: 424 ms for 9,780 rows.
    # CAST(... AS TEXT) compares as text, which the key can serve, until the
    # phase 3 rebuild gives the column its real type. The ORDER BY is the
    # order that scan produced, so ties come out as they always did.
    rows = conn.execute(
        """
        SELECT i.lead_id, i.post_urn, i.comment_text, i.interaction_type,
               COALESCE(i.first_seen_at, i.interacted_at) AS engaged_at,
               COALESCE(i.last_seen_at, i.interacted_at) AS seen_at,
               COALESCE(l.full_name, l.name) AS name, l.headline, l.lead_status
        FROM lead_interactions i JOIN leads l ON l.id = CAST(i.lead_id AS TEXT)
        WHERE COALESCE(i.first_seen_at, i.interacted_at) >= ?
        ORDER BY l.rowid, i.interacted_at DESC, i.id
        """, (since,)).fetchall()

    people: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if onboarding._activity_id(row["post_urn"]) not in own_ids:
            continue
        if (row["lead_status"] or "").upper() in ANSWERED_STATUSES:
            continue
        person = people.setdefault(str(row["lead_id"]), {
            "lead_id": str(row["lead_id"]), "name": row["name"], "headline": row["headline"],
            "posts_engaged": set(), "engaged_at": None, "last_seen_at": None, "latest_comment": None,
            "commented": False,
        })
        person["posts_engaged"].add(onboarding._activity_id(row["post_urn"]))
        person["last_seen_at"] = max(person["last_seen_at"] or "", row["seen_at"] or "") or None
        if row["interaction_type"] != "COMMENT":
            continue
        person["commented"] = True
        if (row["engaged_at"] or "") >= (person["engaged_at"] or ""):
            person["engaged_at"] = row["engaged_at"]
            if row["comment_text"]:
                person["latest_comment"] = clip(row["comment_text"], 200)

    # Only people who commented: a reaction leaves nothing to reply to. Repeat
    # engagement first, then the most recent comment.
    ranked = sorted(
        (p for p in people.values() if p["commented"]),
        key=lambda p: (len(p["posts_engaged"]), p["engaged_at"] or ""),
        reverse=True,
    )[:REPLY_LIMIT]
    for person in ranked:
        person["posts_engaged"] = len(person["posts_engaged"])
    return ranked


def _missed(note: Optional[Dict[str, Any]], scheduled_for: Optional[str]) -> Optional[Dict[str, Any]]:
    """The missed note for Today, only while it is about the post's current time."""
    if not note or note.get("scheduled_for") != scheduled_for:
        return None
    late = note.get("late_minutes")
    return {"scheduled_for": scheduled_for, "noticed_at": note.get("noticed_at"),
            "late_minutes": late if isinstance(late, (int, float)) else None}


def due_posts(conn, limit: int = DUE_LIMIT) -> List[Dict[str, Any]]:
    """
    Queued posts whose time has come, oldest first, with the whole text for
    Copy text, and why one was missed when it was: the machine was asleep or
    the studio was closed at its time, noticed this late. This is the one
    place that reads the due status; Today and the Queue both call it, so a
    creator sees the same list and the same reason on either screen.
    """
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    try:
        missed = native_scheduler.missed_notes(conn)
    except Exception:
        missed = {}
    return [{"post_id": r["id"], "scheduled_for": r["scheduled_for"], "content": r["content"] or "",
             "excerpt": clip(" ".join((r["content"] or "").split()), 120),
             "missed": _missed(missed.get(r["id"]), r["scheduled_for"])}
            for r in conn.execute(
                "SELECT id, content, scheduled_for FROM posts WHERE status = 'due' "
                "ORDER BY scheduled_for LIMIT ?", (limit,))]


def _queue(conn) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled' AND scheduled_for IS NOT NULL "
        "ORDER BY scheduled_for LIMIT 1").fetchone()
    scheduled = None
    if row:
        scheduled = {"post_id": row["id"], "scheduled_for": row["scheduled_for"],
                     "excerpt": clip(" ".join((row["content"] or "").split()), 120)}
    try:
        from .scheduler import native_scheduler
    except ImportError:
        from scheduler import native_scheduler
    try:
        slot = native_scheduler.calculate_next_smart_slot()
    except Exception:
        slot = None
    # Posts whose time has come. The studio does not post them; it marks them
    # due and waits for the creator, so Today says so, oldest first, with the
    # whole text for Copy text. A post missed while the machine slept carries
    # the time it was due and how late it was noticed, so Today can say it
    # was missed rather than let it read as on time.
    due = due_posts(conn)
    return {"next_scheduled": scheduled, "next_open_slot": slot, "due": due}


def _open_next(state: Dict[str, Any], latest: Optional[Dict[str, Any]], conn) -> Dict[str, Any]:
    """
    The one page most worth opening now, by a fixed rule, with the reason.

    A rule rather than a recommendation engine: the order is the order in
    which each thing blocks the ones after it.
    """
    if not state["steps"]["identity"]:
        return {"action": "setup", "reason": "The studio does not know which LinkedIn account is yours yet."}
    if not state["bridge"]["connected"]:
        return {"action": "open", "url": "https://www.linkedin.com/feed/",
                "reason": "The bridge has not been heard from recently, so nothing is being captured."}
    drifting = [h["label"] for h in state["health"] if h["state"] == "drifting"]
    if drifting:
        return {"action": "setup", "reason": f"{drifting[0]} has stopped reading LinkedIn's pages. See Capture health in Setup."}
    if not state["steps"]["history"] and state.get("extension_outdated"):
        # Importing again with the old extension still loaded repeats the same
        # result, so the instruction is to reload it first.
        return {"action": "setup", "reason": (
            "Your last posts import was read by an older copy of the extension, which cannot tell whether it "
            "reached the end of your posts. Reload the extension on your browser's extensions page "
            "(edge://extensions or brave://extensions), then run Posts you wrote in Setup's step 5 again."
        )}
    if not state["steps"]["history"]:
        # The same test as Setup's step 5, so Today never sends the creator
        # to a Setup screen where that step is ticked.
        return {"action": "setup", "reason": (
            "Your posts have not been read to the end of the list yet, so your usual is not known. "
            "Run Posts you wrote in Setup's step 5."
        )}
    asked = _phone_request_rule(conn)
    if asked:
        return asked
    if latest and latest["age_hours"] <= COMPARE_WINDOW[1]:
        recent = conn.execute(
            "SELECT 1 FROM post_metric_observations WHERE activity_urn = ? AND source = 'post_analytics' "
            "AND observed_at >= ?", (latest["activity_urn"],
                                     (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat())).fetchone()
        if not recent:
            return {"action": "open", "url": latest["analytics_url"],
                    "reason": "Your latest post is in its first three days and its figures were not read in the last 12 hours."}
    if latest:
        return {"action": "open", "url": latest["url"],
                "reason": "Opening your latest post picks up anyone who has commented since."}
    return {"action": "setup", "reason": "No post of yours has been imported yet."}


def _phone_request_rule(conn) -> Optional[Dict[str, Any]]:
    """
    The oldest post the phone asked the desk to read, as the one page to
    open, or None when nothing is asked (cycle 4, track 6).

    Sits after the rules that block everything (identity, the bridge, drift,
    the history) and ahead of the latest-post rule, because the creator
    asked for it: a post seen moving on the phone is read at the desk, where
    the extension reads the real page. Settling first closes what has since
    been read, and what waited a week unread, so a request can never stand
    in front of the latest-post rule for good. A post the studio does not
    hold is answered with the same refusal the reading would meet.
    """
    desk_requests.settle(conn)
    request = desk_requests.oldest_open(conn)
    if not request:
        return None
    asked = {"id": request["id"], "activity_urn": request["activity_urn"], "asked_at": request["asked_at"],
             "source": request["source"]}
    url = desk_requests.analytics_url(request["activity_urn"])
    if desk_requests.known_post(conn, request["activity_urn"]) and url:
        return {"action": "open", "url": url,
                "reason": "You asked from your phone to read this post's analytics.",
                "phone_request": asked}
    return {"action": "setup",
            "reason": (f"You asked from your phone to read a post's analytics, but {desk_requests.UNKNOWN_POST}. "
                       "Run Posts you wrote in Setup's step 5; if the post is yours, it is offered here next."),
            "phone_request": asked}


# What the demo cleanup removed, written by database.clean_up_demo_data with
# "shown": false, for Today to say once.
DEMO_CLEANUP_NOTICE_KEY = "demo_cleanup_notice"


def _read_demo_cleanup(conn) -> Optional[Dict[str, Any]]:
    """The stored notice as a dict, or None when absent or not a JSON object."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (DEMO_CLEANUP_NOTICE_KEY,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row["value"] or "")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _demo_cleanup(conn) -> Optional[Dict[str, Any]]:
    """
    The notice to show, or None. Read defensively, because nothing should
    appear on Today from a value that does not say what was removed: absent,
    malformed, already shown, or counting nothing all show nothing.
    """
    notice = _read_demo_cleanup(conn)
    if not notice or notice.get("shown") is not False:
        return None
    counts = notice.get("removed") if isinstance(notice.get("removed"), dict) else notice
    removed = [{"kind": kind, "count": count} for kind, count in counts.items()
               if isinstance(count, int) and not isinstance(count, bool) and count > 0]
    if not removed:
        return None
    backup = notice.get("backup")
    return {"removed": removed, "backup": backup if isinstance(backup, str) and backup else None,
            "removed_at": notice.get("removed_at") if isinstance(notice.get("removed_at"), str) else None}


def dismiss_demo_cleanup() -> Dict[str, Any]:
    """Marks the notice shown, keeping the record of what was removed and where the copy is."""
    conn = get_db()
    try:
        notice = _read_demo_cleanup(conn)
        if notice is None or notice.get("shown") is True:
            return {"status": "success", "dismissed": False}
        notice["shown"] = True
        with conn:
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(notice), DEMO_CLEANUP_NOTICE_KEY))
    finally:
        conn.close()
    return {"status": "success", "dismissed": True}


def today_brief() -> Dict[str, Any]:
    state = onboarding.onboarding_state()
    conn = get_db()
    try:
        latest = _latest_post(conn) if state["steps"]["identity"] else None
        marked = _marked_published(conn, latest)
        reply_to = _reply_to(conn) if state["steps"]["identity"] else []
        queue = _queue(conn)
        open_next = _open_next(state, latest, conn)
        demo_cleanup = _demo_cleanup(conn)
    finally:
        conn.close()

    drifting = [h["label"] for h in state["health"] if h["state"] == "drifting"]
    return {
        "status": "success",
        "identity": {"known": state["steps"]["identity"],
                     "name": (state["identity"] or {}).get("display_name")},
        "freshness": {
            "bridge": state["bridge"],
            "drifting": drifting,
            "last_capture_at": max((h["last_run_at"] for h in state["health"] if h["last_run_at"]), default=None),
            # Your posts the studio holds, however they arrived. With none of
            # the capture's runs recorded, the line read NOTHING CAPTURED YET
            # beside twelve imported posts.
            "posts_held": state["counts"]["posts"],
        },
        "reply_to": reply_to,
        "latest_post": latest,
        "marked_published": marked,
        "queue": queue,
        "open_next": open_next,
        "demo_cleanup": demo_cleanup,
        # The archive age nudge, from archive_state, the same sentence Setup says.
        "archive_age": state["archive"].get("age_nudge"),
    }
