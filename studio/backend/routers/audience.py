"""
Audience API Router
===================
What the Audience section reads: the first view (who keeps coming back, who
has gone quiet, new people by week, how the connections join), the
searchable connections list, the second level's funnel and company counts,
and one person's facts for the Leads dossier. studio/backend/audience.py
holds the rules; this only carries them.

The first view is one route. The list a creator searches, the counts one
level down and a dossier's facts are each read when asked for, so the first
view does not pay for them.

Strict Invariants:
- Zero em-dashes.
- Nothing here writes, and nothing here orders people by score.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

try:
    from .. import audience
except (ImportError, ValueError):
    import audience

router = APIRouter(tags=["Audience"])


@router.get("/api/v1/audience")
def get_audience() -> Dict[str, Any]:
    """Repeat engagers by posts engaged then recency, gone quiet, new people by week, and the connections join."""
    return audience.overview()


@router.get("/api/v1/audience/connections")
def get_audience_connections(
    q: Optional[str] = Query(None, max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(audience.CONNECTIONS_PAGE, ge=1, le=audience.CONNECTIONS_MAX),
) -> Dict[str, Any]:
    """Your connections as LinkedIn's archive listed them, by name, each marked when they are also a lead."""
    return audience.connections(q=q, offset=offset, limit=limit)


@router.get("/api/v1/audience/counts")
def get_audience_counts() -> Dict[str, Any]:
    """How many people are at each stage you set in Leads, and how many name each company. Counts only."""
    return audience.counts()


@router.get("/api/v1/audience/people/{lead_id}")
def get_audience_person(lead_id: str) -> Dict[str, Any]:
    """First seen, last seen and times seen, and whether the person is a connection, for the dossier."""
    found = audience.person(lead_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return found
