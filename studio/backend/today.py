"""
Today: what to do in the next hour.
===================================

The screen a creator opens first once the studio knows who they are. It
answers one question, and every section is something they can act on now:

  who to reply to   people who engaged with your posts and have not heard
                    from you, repeat engagers first, then the most recent
  your latest post  how it is doing against your usual, at the same age
  the queue         what goes out next, and the next open slot
  one page to open  the single LinkedIn page most worth opening right now

What it will not do is rank people by the ICP score. That number is a keyword
guess about a job title; who engaged with you twice this week is a fact.

Strict Invariants:
- Zero em-dashes.
- Every comparison states how many posts it rests on, and says so when too few.
- No network request. Everything here is read from what the extension captured.
"""

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import onboarding
    from .database import get_db
except ImportError:
    import onboarding
    from database import get_db

# People are listed while their engagement is recent enough to answer.
REPLY_WINDOW = timedelta(days=14)
REPLY_LIMIT = 5

# Lead statuses that mean the creator has already responded.
ANSWERED_STATUSES = ("DM_SENT", "ENGAGED", "CONVERTED")

# Posts are compared at the same age, because a post read at six hours and one
# read at six weeks say nothing about each other. Two days is when most of a
# post's reach has arrived, and the window either side tolerates reading gaps.
COMPARE_AT_HOURS = 48.0
COMPARE_WINDOW = (36.0, 72.0)
COMPARE_WITH = 20
MIN_COMPARISONS = 3

COMPARED_METRICS = ("impressions", "reactions", "comments")


def _reading_at_age(conn, activity_urn: str) -> Optional[Dict[str, Any]]:
    """The post's reading closest to two days old, within the window."""
    rows = conn.execute(
        "SELECT age_hours, impressions, reactions, comments FROM post_metric_observations "
        "WHERE activity_urn = ? AND age_hours BETWEEN ? AND ?",
        (activity_urn, *COMPARE_WINDOW),
    ).fetchall()
    if not rows:
        return None
    best = min(rows, key=lambda r: abs(r["age_hours"] - COMPARE_AT_HOURS))
    return dict(best)


def _latest_reading(conn, activity_urn: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT age_hours, impressions, reactions, comments, observed_at FROM post_metric_observations "
        "WHERE activity_urn = ? ORDER BY observed_at DESC LIMIT 1", (activity_urn,)).fetchone()
    return dict(row) if row else None


def _latest_post(conn) -> Optional[Dict[str, Any]]:
    posts = conn.execute(
        "SELECT activity_urn, text, published_at FROM own_posts WHERE published_at IS NOT NULL "
        "ORDER BY published_at DESC LIMIT ?", (COMPARE_WITH + 1,)).fetchall()
    if not posts:
        return None

    latest, earlier = posts[0], posts[1:]
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest["published_at"])).total_seconds() / 3600.0
    own = _reading_at_age(conn, latest["activity_urn"])
    current = own or _latest_reading(conn, latest["activity_urn"])

    usual_readings = [r for r in (_reading_at_age(conn, p["activity_urn"]) for p in earlier) if r]
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
        "excerpt": " ".join((latest["text"] or "").split())[:160] or None,
        "published_at": latest["published_at"],
        "age_hours": round(age, 1),
        "current": current,
        "comparison": comparison or None,
        "not_compared_because": verdict,
        "url": f"https://www.linkedin.com/feed/update/{latest['activity_urn']}/",
        "analytics_url": f"https://www.linkedin.com/analytics/post-summary/{latest['activity_urn']}/",
    }


def _reply_to(conn) -> List[Dict[str, Any]]:
    own_ids = onboarding._own_activity_ids(conn)
    if not own_ids:
        return []
    since = (datetime.now(timezone.utc) - REPLY_WINDOW).strftime("%Y-%m-%d %H:%M:%S")
    rows = conn.execute(
        """
        SELECT i.lead_id, i.post_urn, i.comment_text, i.interaction_type,
               COALESCE(i.last_seen_at, i.interacted_at) AS seen_at,
               COALESCE(l.full_name, l.name) AS name, l.headline, l.lead_status
        FROM lead_interactions i JOIN leads l ON l.id = i.lead_id
        WHERE COALESCE(i.first_seen_at, i.interacted_at) >= ?
        """, (since,)).fetchall()

    people: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if onboarding._activity_id(row["post_urn"]) not in own_ids:
            continue
        if (row["lead_status"] or "").upper() in ANSWERED_STATUSES:
            continue
        person = people.setdefault(str(row["lead_id"]), {
            "lead_id": str(row["lead_id"]), "name": row["name"], "headline": row["headline"],
            "posts_engaged": set(), "last_seen_at": row["seen_at"], "latest_comment": None,
            "commented": False,
        })
        person["posts_engaged"].add(onboarding._activity_id(row["post_urn"]))
        if row["interaction_type"] == "COMMENT":
            person["commented"] = True
        if (row["seen_at"] or "") >= (person["last_seen_at"] or ""):
            person["last_seen_at"] = row["seen_at"]
            if row["comment_text"]:
                person["latest_comment"] = row["comment_text"][:200]

    # Repeat engagement first, then a comment over a reaction, then recency.
    ranked = sorted(
        people.values(),
        key=lambda p: (len(p["posts_engaged"]), p["commented"], p["last_seen_at"] or ""),
        reverse=True,
    )[:REPLY_LIMIT]
    for person in ranked:
        person["posts_engaged"] = len(person["posts_engaged"])
    return ranked


def _queue(conn) -> Dict[str, Any]:
    row = conn.execute(
        "SELECT id, content, scheduled_for FROM posts WHERE status = 'scheduled' AND scheduled_for IS NOT NULL "
        "ORDER BY scheduled_for LIMIT 1").fetchone()
    scheduled = None
    if row:
        scheduled = {"post_id": row["id"], "scheduled_for": row["scheduled_for"],
                     "excerpt": " ".join((row["content"] or "").split())[:120]}
    try:
        try:
            from .scheduler import native_scheduler
        except ImportError:
            from scheduler import native_scheduler
        slot = native_scheduler.calculate_next_smart_slot()
    except Exception:
        slot = None
    return {"next_scheduled": scheduled, "next_open_slot": slot}


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
    if not onboarding.post_history_complete(conn):
        return {"action": "setup", "reason": "Your post history has not been imported, so your usual is not known yet."}
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


def today_brief() -> Dict[str, Any]:
    state = onboarding.onboarding_state()
    conn = get_db()
    try:
        latest = _latest_post(conn) if state["steps"]["identity"] else None
        reply_to = _reply_to(conn) if state["steps"]["identity"] else []
        queue = _queue(conn)
        open_next = _open_next(state, latest, conn)
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
        },
        "reply_to": reply_to,
        "latest_post": latest,
        "queue": queue,
        "open_next": open_next,
    }
