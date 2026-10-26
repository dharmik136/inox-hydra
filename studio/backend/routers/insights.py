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
    from ..evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief, patterns_comparisons
except (ImportError, ValueError):
    import insights
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


@router.get("/api/v1/insights/posts/{activity_urn}")
def get_post_detail(activity_urn: str) -> Dict[str, Any]:
    """One post's whole text and figures, for the detail view the Posts table opens into."""
    detail = insights.post_detail(activity_urn)
    if detail is None:
        raise HTTPException(status_code=404, detail="No such post")
    return detail


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


@router.get("/api/v1/insights/evidence")
def get_evidence_brief() -> Dict[str, Any]:
    """Retrieval evidence brief, top and bottom exemplars, and conclusive contrasts (CP2 and CP3)."""
    return get_retrieval_evidence_brief()
