"""
Insights API Router
===================
Surfaces observed post history, cadence, outbound engagement reciprocity,
patterns, and binary feature contrasts. Zero cloud egress.
"""

from fastapi import APIRouter
from typing import Dict, Any

try:
    from .. import insights
    from ..contrast_engine import compute_all_contrasts
    from ..evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief
except (ImportError, ValueError):
    import insights
    from contrast_engine import compute_all_contrasts
    from evidence_briefing import get_topic_attribution_map, get_retrieval_evidence_brief

router = APIRouter(tags=["Insights"])


@router.get("/api/v1/insights/posts")
def get_posts_insights() -> Dict[str, Any]:
    """Which settled posts did best against your median, and who engaged."""
    return insights.posts_overview()


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
