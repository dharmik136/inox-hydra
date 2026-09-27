"""
Posts and Outbound: what your own history says.
===============================================

Two questions a creator can act on, answered only from what the studio
observed on their own account:

  Posts     Which of my posts worked, and whom did each one bring?
  Outbound  Whose content do I spend my attention on, and does it come back?

Neither screen predicts anything. A post is compared with your own median, not
with a benchmark, and "worked" is said only of posts old enough for their
numbers to have settled. Reciprocity is matched by name, because a reaction
records the author's display name and not their profile, and the screen says
so rather than presenting a name match as an identity.

Strict Invariants:
- Zero em-dashes.
- Every comparison carries the number of posts it rests on.
- A count never read is shown as unknown, not as zero.
"""

import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from . import onboarding
    from .database import get_db
except ImportError:
    import onboarding
    from database import get_db

# A post's reactions and comments have mostly arrived by a week. Before that
# a low number may just be a young post, so it is not called weak.
SETTLED_AFTER_HOURS = 7 * 24
MIN_FOR_MEDIAN = 3


def _age_hours(published_at: Optional[str]) -> Optional[float]:
    if not published_at:
        return None
    return (datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600.0


def _excerpt(text: Optional[str], limit: int = 140) -> Optional[str]:
    return " ".join((text or "").split())[:limit] or None


def posts_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        posts = [dict(r) for r in conn.execute(
            "SELECT activity_urn, text, published_at, reactions, comments, reposts, impressions "
            "FROM own_posts ORDER BY published_at DESC")]

        # Who engaged with each post: leads whose interactions name it.
        engagers: Dict[str, List[Dict[str, Any]]] = {}
        for row in conn.execute(
            "SELECT i.post_urn, i.lead_id, i.interaction_type, i.comment_text, "
            "COALESCE(l.full_name, l.name) AS name, l.lead_status "
            "FROM lead_interactions i JOIN leads l ON l.id = i.lead_id WHERE i.post_urn IS NOT NULL"):
            key = onboarding._activity_id(row["post_urn"])
            engagers.setdefault(key, []).append(dict(row))
    finally:
        conn.close()

    settled = [p for p in posts if (_age_hours(p["published_at"]) or 0) >= SETTLED_AFTER_HOURS]

    def median_of(metric):
        values = [p[metric] for p in settled if p[metric] is not None]
        return (statistics.median(values), len(values)) if len(values) >= MIN_FOR_MEDIAN else (None, len(values))

    usual = {m: median_of(m) for m in ("reactions", "comments", "impressions")}

    out = []
    for post in posts:
        age = _age_hours(post["published_at"])
        people = engagers.get(onboarding._activity_id(post["activity_urn"]), [])
        by_person: Dict[str, Dict[str, Any]] = {}
        for p in people:
            person = by_person.setdefault(str(p["lead_id"]), {
                "lead_id": str(p["lead_id"]), "name": p["name"], "commented": False,
                "status": p["lead_status"]})
            if p["interaction_type"] == "COMMENT":
                person["commented"] = True

        ratios = {}
        for metric, (median, _n) in usual.items():
            if median and post[metric] is not None and age is not None and age >= SETTLED_AFTER_HOURS:
                ratios[metric] = round(post[metric] / median, 2)

        out.append({
            "activity_urn": post["activity_urn"],
            "excerpt": _excerpt(post["text"]),
            "published_at": post["published_at"],
            "age_days": round(age / 24, 1) if age is not None else None,
            "settled": age is not None and age >= SETTLED_AFTER_HOURS,
            "reactions": post["reactions"],
            "comments": post["comments"],
            "reposts": post["reposts"],
            "impressions": post["impressions"],
            "against_usual": ratios or None,
            "people": sorted(by_person.values(), key=lambda p: (not p["commented"], p["name"] or ""))[:12],
            "people_count": len(by_person),
            # People from this post the creator went on to talk to: Connected
            # or Meeting Booked. The question the Posts screen exists for.
            "conversations": sum(1 for p in by_person.values() if (p["status"] or "") in ("ENGAGED", "CONVERTED")),
            "url": f"https://www.linkedin.com/feed/update/{post['activity_urn']}/",
        })

    # The two settled posts that did best against your own median reactions,
    # which is what "repurpose the top two" means: forms that already worked.
    ranked = sorted((p for p in out if p["against_usual"] and "reactions" in p["against_usual"]),
                    key=lambda p: p["against_usual"]["reactions"], reverse=True)
    return {
        "status": "success",
        "posts": out,
        "usual": {m: {"median": v[0], "posts": v[1]} for m, v in usual.items()},
        "best": [p["activity_urn"] for p in ranked[:2]],
        "settled_after_days": SETTLED_AFTER_HOURS // 24,
    }


def _name_key(name: Optional[str]) -> str:
    return " ".join((name or "").lower().split())


def outbound_overview() -> Dict[str, Any]:
    conn = get_db()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT target_author, kind, reaction_kind, my_text, last_seen_at FROM outbound_engagements")]
        own_ids = onboarding._own_activity_ids(conn)
        # People who engaged with your posts, by display name.
        engaged_back: Dict[str, int] = {}
        for row in conn.execute(
            "SELECT COALESCE(l.full_name, l.name) AS name, i.post_urn FROM lead_interactions i "
            "JOIN leads l ON l.id = i.lead_id WHERE i.post_urn IS NOT NULL"):
            if onboarding._activity_id(row["post_urn"]) in own_ids:
                key = _name_key(row["name"])
                engaged_back[key] = engaged_back.get(key, 0) + 1
    finally:
        conn.close()

    authors: Dict[str, Dict[str, Any]] = {}
    unknown = 0
    for row in rows:
        if not row["target_author"]:
            unknown += 1
            continue
        key = _name_key(row["target_author"])
        entry = authors.setdefault(key, {"name": row["target_author"], "reactions": 0, "comments": 0,
                                         "last_at": None})
        entry["reactions" if row["kind"] == "reaction" else "comments"] += 1
        if (row["last_seen_at"] or "") > (entry["last_at"] or ""):
            entry["last_at"] = row["last_seen_at"]

    for key, entry in authors.items():
        entry["total"] = entry["reactions"] + entry["comments"]
        entry["engaged_back"] = engaged_back.get(key, 0)

    ranked = sorted(authors.values(), key=lambda a: (a["total"], a["comments"]), reverse=True)

    # "Never engaged back" is only a finding once the studio has read who
    # engaged with most of your posts. Engagers are captured as you open your
    # posts, so on a new install nobody has, and every account would be listed
    # as one-way on the strength of the studio not having looked. Measured on
    # the first live install: 1 engager captured, and 6 of 6 top accounts
    # would have been called one-way.
    conn = get_db()
    try:
        read_posts = {onboarding._activity_id(r["post_urn"]) for r in conn.execute(
            "SELECT DISTINCT post_urn FROM lead_interactions WHERE post_urn IS NOT NULL")}
        engaged_posts = [r["activity_urn"] for r in conn.execute(
            "SELECT activity_urn FROM own_posts WHERE COALESCE(reactions, 0) + COALESCE(comments, 0) > 0")]
    finally:
        conn.close()
    covered = sum(1 for urn in engaged_posts if onboarding._activity_id(urn) in read_posts)
    coverage = round(covered / len(engaged_posts), 2) if engaged_posts else 0.0
    judged = coverage >= 0.5

    return {
        "coverage": {"posts_read": covered, "posts_with_engagement": len(engaged_posts), "share": coverage,
                     "one_way_judged": judged},
        "status": "success",
        "totals": {"reactions": sum(1 for r in rows if r["kind"] == "reaction"),
                   "comments": sum(1 for r in rows if r["kind"] == "comment"),
                   "authors": len(authors), "without_author": unknown},
        "authors": ranked[:40],
        # Accounts you engaged with at least three times that have never
        # engaged with a post of yours: where your attention goes one way.
        "one_way": ([a["name"] for a in ranked if a["total"] >= 3 and not a["engaged_back"]][:12]
                    if judged else []),
        "reciprocal": [a["name"] for a in ranked if a["engaged_back"]][:12],
        "matched_by": "display name",
    }
