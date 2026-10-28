"""
Insights API Router
===================
Surfaces observed post history, cadence, outbound engagement reciprocity,
patterns, and binary feature contrasts. Zero cloud egress.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional

try:
    from .. import insights
    from .. import onboarding
    from .. import own_insights
    from .. import post_summary
    from .. import results
    from .. import retention
    from ..contrast_engine import compute_all_contrasts
    from ..database import get_db
    from ..evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief, patterns_comparisons
except (ImportError, ValueError):
    import insights
    import onboarding
    import own_insights
    import post_summary
    import results
    import retention
    from contrast_engine import compute_all_contrasts
    from database import get_db
    from evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief, patterns_comparisons

router = APIRouter(tags=["Insights"])


@router.get("/api/v1/insights/posts")
def get_posts_insights(limit: Optional[int] = Query(None, ge=1), offset: int = Query(0, ge=0),
                        sort: str = Query("newest"), settled_state: Optional[str] = Query(None),
                        q: Optional[str] = Query(None, max_length=200)) -> Dict[str, Any]:
    """
    Which settled posts did best against your median, and who engaged.

    One page of posts, sorted and filtered as asked (insights.POSTS_SORTS,
    insights.POSTS_SETTLED_STATES), insights.POSTS_PAGE of them by default.
    Every figure beside the list (your usual, the best two, the counts) is
    read from your whole history whichever page this is, sort or filter.
    """
    return insights.posts_overview(limit=limit, offset=offset, sort=sort, settled_state=settled_state, q=q)


# LinkedIn's own per-post figures from the post analytics page, read as they
# were printed and never derived: the newest reading of that page answers.
PER_POST_FIELDS = ("followers_gained", "profile_viewers", "link_visits", "article_views", "video_views",
                   "in_network_pct", "out_of_network_pct", "watch_time_seconds", "average_watch_seconds")


def _derived(activity_urn: str) -> Dict[str, Any]:
    """
    What the readings of one post can say beyond its latest figures (cycle
    4, track 5): how precisely that reading was read and which of its figures
    LinkedIn rounded, so the screen says "about" beside those and nothing
    beside the rest; every reading, oldest first; the per-post figures the
    post analytics page shows, from its newest reading; the viewer
    demographics as a dated series; whether the post is still moving; and
    its reach half-life. Every rule is results.py's.
    """
    conn = get_db()
    try:
        figure = results.figures(conn, [activity_urn]).get(activity_urn) or {}
        # Whether it is still moving, and its reach half-life: the engine's
        # sentences, with their reading counts and their abstentions.
        movement = results.movement(conn, activity_urn)
        half_life = results.half_life(conn, activity_urn)
        # What kind of post it was (post_format.py), "unknown" unless a source said,
        # and when it was first seen marked edited (phase 2).
        held = conn.execute("SELECT format, edited_first_seen_at FROM own_posts WHERE activity_urn = ?",
                            (activity_urn,)).fetchone()
        two_day = _two_day(conn, activity_urn)
        # The readings roll-up thins readings older than its age to the first
        # and last of each day (and keeps every one at 36 to 72 hours), so
        # "read N times" is the readings kept; the screen says so when it ran.
        rule = retention.rules(conn)
        thinned_after = int(rule["readings_days"]) if rule.get("readings") == "on" else None
    finally:
        conn.close()
    readings = onboarding.post_readings(activity_urn)
    # Each figure from the newest analytics-page reading that has it (review
    # S2 and N7), with that reading's time, age and precision: a figure read
    # at 26 hours and not shown at 50 is still the figure read at 26.
    per_post: Dict[str, Any] = {}
    for reading in readings:
        if reading["source"] != "post_analytics":
            continue
        for field in PER_POST_FIELDS:
            if reading.get(field) is not None:
                per_post[field] = {"value": reading[field], "read_at": reading["observed_at"],
                                   "read_at_age_hours": reading["age_hours"], "precision": reading["precision"]}
    return {
        "figures_precision": figure.get("precision"),
        "approximate": results.approximate_fields(figure),
        "readings": readings,
        "per_post": per_post or None,
        "demographics": onboarding.post_demographics(activity_urn),
        "movement": movement,
        "half_life": half_life,
        "format": held["format"] if held else None,
        "edited_first_seen_at": held["edited_first_seen_at"] if held else None,
        "two_day": two_day,
        "readings_thinned_after_days": thinned_after,
    }


def _two_day(conn, activity_urn: str) -> Dict[str, Any]:
    """
    The reading nearest two days old, the age Today compares a post at
    (post_summary.READING_AT_HOURS, within READING_WINDOW), from the per-post
    summary that Today reads, so the two screens cannot pick different ones.
    With none, which of three reasons: too young to have one, in the window
    and not read yet, or past the window without one.
    """
    row = post_summary.current(conn, [activity_urn]).get(activity_urn)
    reading = post_summary.reading_of(row, "reading_48h")
    published = conn.execute("SELECT published_at FROM own_posts WHERE activity_urn = ?", (activity_urn,)).fetchone()
    age = results.age_hours(published[0]) if published and published[0] else None
    low, high = post_summary.READING_WINDOW
    if reading:
        state = "read"
    elif age is None:
        state = "unknown_age"
    elif age < low:
        state = "too_new"
    elif age <= high:
        state = "not_yet"
    else:
        state = "missed"
    return {"state": state, "reading": reading, "age_hours": round(age, 1) if age is not None else None,
            "at_hours": post_summary.READING_AT_HOURS, "window": [low, high]}


@router.get("/api/v1/insights/reposts")
def get_own_reposts() -> Dict[str, Any]:
    """
    The creator's own reposts: when, and their own figures where the card
    told them apart. Never the original's author, words or figures.
    """
    return {"status": "success", "reposts": own_insights.own_reposts()}


@router.get("/api/v1/insights/posts/{activity_urn}")
def get_post_detail(activity_urn: str) -> Dict[str, Any]:
    """One post's whole text and figures, for the detail view the Posts table opens into."""
    detail = insights.post_detail(activity_urn)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such post")
    return {**detail, **_derived(activity_urn)}


@router.get("/api/v1/insights/patterns")
def get_patterns_insights() -> Dict[str, Any]:
    """Which forms of post have gone with more reactions, for you, with counts."""
    return insights.patterns_overview()


@router.get("/api/v1/insights/contrasts")
def get_contrast_insights() -> Dict[str, Any]:
    """
    The contrast engine's comparisons across settled posts, n>=8 per arm: the
    seven forms under `contrasts`, and the creator's own topics compared the
    same way under `topics`, from one reading of the figures. Patterns draws
    both; the Evidence panel reads the seven through the brief.
    """
    return patterns_comparisons()


@router.get("/api/v1/insights/attribution")
def get_attribution_insights() -> Dict[str, Any]:
    """
    Topic to Qualified-Lead Attribution Map (CP4). No screen reads it since
    cycle 4 retired the qualified framing on Patterns (decision 7); topics
    are compared as forms under /api/v1/insights/contrasts instead.
    """
    return get_topic_attribution_map()


@router.get("/api/v1/insights/cadence")
def get_cadence_insights() -> Dict[str, Any]:
    """How steadily you post, and what the queue holds."""
    return insights.cadence_overview()


@router.get("/api/v1/insights/outbound")
def get_outbound_insights() -> Dict[str, Any]:
    """Whose content you spend attention on, and who has engaged back."""
    return insights.outbound_overview()


@router.get("/api/v1/insights/outbound/author")
def get_outbound_author(name: str = Query(..., min_length=1, max_length=200)) -> Dict[str, Any]:
    """One account: the posts of theirs you engaged with, and theirs on yours with the time between."""
    detail = insights.outbound_author(name)
    if detail is None:
        raise HTTPException(status_code=404, detail="You have not engaged with an account of that name")
    return detail


@router.get("/api/v1/insights/evidence")
def get_evidence_brief() -> Dict[str, Any]:
    """Retrieval evidence brief, top and bottom exemplars, and conclusive contrasts (CP2 and CP3)."""
    return get_retrieval_evidence_brief()
