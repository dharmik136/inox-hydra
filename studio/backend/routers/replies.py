"""
Replies API Router
==================
What the Replies section reads and writes: one page of the comments on the
creator's own posts in the window, grouped by post, oldest seen first, and the
creator's own Answered mark. studio/backend/replies.py holds the rules; this
only carries them.

Strict Invariants:
- Zero em-dashes.
- A GET writes nothing. Only the creator's click marks or unmarks a comment.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

try:
    from .. import replies
except (ImportError, ValueError):
    import replies

router = APIRouter(tags=["Replies"])


class CommentRef(BaseModel):
    """A comment as lead_interactions keys it."""
    lead_id: str
    post_urn: str = ""
    comment_key: str = ""


@router.get("/api/v1/replies")
def get_replies(
    days: Optional[int] = Query(None, ge=1, le=replies.WINDOW_MAX_DAYS),
    view: str = Query("waiting", pattern="^(waiting|answered)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(replies.PAGE, ge=1, le=replies.PAGE_MAX),
) -> Dict[str, Any]:
    """
    Comments on your posts, first seen by the studio in the window (14 days
    unless asked), that you have not marked answered, oldest first and grouped
    by post. view=answered lists the ones you marked instead.
    """
    return replies.overview(days=days, view=view, offset=offset, limit=limit)


@router.post("/api/v1/replies/mark")
def post_reply_mark(payload: CommentRef) -> Dict[str, Any]:
    """You answered this comment. The studio cannot read that from LinkedIn, so it is your mark."""
    try:
        return replies.mark(payload.lead_id, payload.post_urn, payload.comment_key)
    except replies.UnknownComment as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/api/v1/replies/unmark")
def post_reply_unmark(payload: CommentRef) -> Dict[str, Any]:
    """Takes the mark back: the comment is waiting again."""
    return replies.unmark(payload.lead_id, payload.post_urn, payload.comment_key)
