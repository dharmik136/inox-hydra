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
    from .. import results
    from ..contrast_engine import compute_all_contrasts
    from ..database import get_db
    from ..evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief
except (ImportError, ValueError):
    import insights
    import results
    from contrast_engine import compute_all_contrasts
    from database import get_db
    from evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief

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


def _derived(activity_urn: str) -> Dict[str, Any]:
    """
    What the readings of one post can say beyond its latest figures (cycle
    4, track 5): how precisely that reading was read and which of its figures
    LinkedIn rounded, so the screen says "about" beside those and nothing
    beside the rest. Every rule is results.py's.
    """
    conn = get_db()
    try:
        figure = results.figures(conn, [activity_urn]).get(activity_urn) or {}
    finally:
        conn.close()
    return {
        "figures_precision": figure.get("precision"),
        "approximate": results.approximate_fields(figure),
    }


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
    """Pairwise binary feature contrasts across settled posts with n>=8 per arm guard."""
    return compute_all_contrasts()


@router.get("/api/v1/insights/attribution")
def get_attribution_insights() -> Dict[str, Any]:
    """Topic to Qualified-Lead Attribution Map (CP4)."""
    return get_topic_attribution_map()


@router.get("/api/v1/insights/cadence")
def get_cadence_insights() -> Dict[str, Any]:
    """How steadily you post, and what the queue holds."""
    return insights.cadence_overview()


@router.get("/api/v1/insights/outbound")
def get_outbound_insights() -> Dict[str, Any]:
    """Whose content you spend attention on, and who has engaged back."""
    return insights.outbound_overview()


@router.get("/api/v1/insights/evidence")
def get_evidence_brief() -> Dict[str, Any]:
    """Retrieval evidence brief, top and bottom exemplars, and conclusive contrasts (CP2 and CP3)."""
    return get_retrieval_evidence_brief()
