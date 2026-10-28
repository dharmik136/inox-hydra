"""
The collection box: what the creator sent their bot, in one place.
==================================================================
Phase 3 of the Telegram bot (docs/quality/cycle4/collection-box.md). These
routes are what From your record's "Your collection" level reads and
changes: the items newest first with their counts, an item set aside or
brought back, used as a draft as it is, or removed. Nothing here leaves the
machine; the bot's side is ingress.py and telegram_bot.py.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Zero egress: these routes read and write the creator's own rows only.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

try:
    from .. import collection, writing
except (ImportError, ValueError):
    import collection
    import writing

router = APIRouter()


class StatusPayload(BaseModel):
    status: str = Field(..., max_length=20, description="new, or not_now to set the item aside")


class RelatedPayload(BaseModel):
    text: str = Field("", max_length=20000, description="The draft being written")


class UsedPayload(BaseModel):
    post_id: str = Field(..., max_length=80, description="The draft the item's words went into")


class WritePayload(BaseModel):
    items: List[int] = Field(..., description="One item for Make a post, two or more to Combine")
    angle: Optional[str] = Field(None, max_length=400, description="An opening line Angles offered, to start from")


def _answer(work):
    try:
        return work()
    except (collection.Refused, writing.Refused) as refused:
        raise HTTPException(status_code=400, detail=str(refused))
    except LookupError as gone:
        raise HTTPException(status_code=404, detail=str(gone))


@router.get("/api/v1/collection", tags=["Collection"])
def get_collection(status: str = Query("new", max_length=10), kind: Optional[str] = Query(None, max_length=20),
                   q: Optional[str] = Query(None, max_length=200), limit: int = Query(50, ge=1, le=200),
                   offset: int = Query(0, ge=0)):
    """The items newest first, of one status (new by default) or all, one kind or every kind, holding a word or not."""
    return _answer(lambda: collection.listing(status=status, kind=kind, q=q, limit=limit, offset=offset))


@router.post("/api/v1/collection/{item_id}/status", tags=["Collection"])
def post_collection_status(item_id: int, payload: StatusPayload):
    """Not now, or back to new. Used is set by making something from the item."""
    return _answer(lambda: {"status": "success", "item": collection.set_status(item_id, payload.status)})


@router.post("/api/v1/collection/{item_id}/draft", tags=["Collection"])
def post_collection_draft(item_id: int):
    """Use as a draft: the item's words, as they are, become a Composer draft, and the item is used."""
    return _answer(lambda: collection.use_as_draft(item_id))


@router.post("/api/v1/collection/{item_id}/media", tags=["Collection"])
def post_collection_media(item_id: int):
    """Add to your media library: a copy of a photo from the phone, where a post's images are kept."""
    return _answer(lambda: {"status": "success", "item": collection.to_library(item_id)})


@router.post("/api/v1/collection/related", tags=["Collection"])
def post_collection_related(payload: RelatedPayload):
    """The Composer's "From your collection": new items whose words the draft shares, matched locally."""
    return collection.related(payload.text)


@router.post("/api/v1/collection/{item_id}/used", tags=["Collection"])
def post_collection_used(item_id: int, payload: UsedPayload):
    """Add to the draft: the item's words went into this draft, so it is used."""
    return _answer(lambda: {"status": "success", "item": collection.used_in(item_id, payload.post_id)})


@router.post("/api/v1/collection/write", tags=["Collection"])
def post_collection_write(payload: WritePayload):
    """
    Make a post from one item, or Combine several into one draft, through
    the creator's own provider, as their writing preferences say. With no
    provider it says so and writes nothing; a provider that fails says why.
    """
    return _answer(lambda: writing.make_post(payload.items, payload.angle))


@router.post("/api/v1/collection/{item_id}/angles", tags=["Collection"])
def post_collection_angles(item_id: int):
    """Angles: the creator's number of opening lines for a post from this item, kept on the item."""
    return _answer(lambda: writing.angles(item_id))


@router.delete("/api/v1/collection/{item_id}", tags=["Collection"])
def delete_collection_item(item_id: int):
    """Removes an item for good. A draft already made from it stays."""
    if not collection.remove(item_id):
        raise HTTPException(status_code=404, detail="That item is no longer in your collection.")
    return {"status": "success", "removed": True}
