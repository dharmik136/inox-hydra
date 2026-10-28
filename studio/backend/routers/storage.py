"""
Storage and Privacy API Router
==============================
What the Storage and privacy panel in Brand Studio reads and asks for: sizes,
the retention rules, backups, previews of each cleanup, the review list of
silent leads, removing forgotten people from backups, and compacting.
studio/backend/retention.py holds the rules; this only carries them.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Nothing here removes data on a GET. Every removal is a POST the creator made.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

try:
    from .. import retention
except (ImportError, ValueError):
    import retention

router = APIRouter()


class RuleChanges(BaseModel):
    rules: Dict[str, Any]


class LeadChoice(BaseModel):
    lead_ids: List[str]


class ScrubChoice(BaseModel):
    leave: Optional[bool] = False


def _refused(call):
    try:
        return call()
    except retention.RetentionRefused as refused:
        raise HTTPException(status_code=400, detail=str(refused))


@router.get("/api/v1/storage", tags=["Support & Maintenance"])
def get_storage():
    """Sizes, rules with their defaults, last and next backup, the review count and the cleanup log."""
    return retention.overview()


@router.get("/api/v1/storage/backups", tags=["Support & Maintenance"])
def get_storage_backups():
    """
    The backup schedule alone: the newest backup, whether the schedule has
    stopped running, and when the next one is due.

    Today says when the schedule has gone stale, and the whole overview above
    costs 578 ms on a three year install against 1.7 ms for this, because it
    measures every table on the way.
    """
    return retention.backup_state()


@router.put("/api/v1/storage/rules", tags=["Support & Maintenance"])
def put_storage_rules(payload: RuleChanges):
    return {"rules": _refused(lambda: retention.set_rules(payload.rules))}


@router.get("/api/v1/storage/preview/{job}", tags=["Support & Maintenance"])
def get_storage_preview(job: str):
    """What a cleanup would remove now. Removes nothing."""
    return _refused(lambda: retention.preview(job))


@router.post("/api/v1/storage/run/{job}", tags=["Support & Maintenance"])
def post_storage_run(job: str):
    """The creator confirmed the preview: back up, then run it, and keep it on."""
    return _refused(lambda: retention.run(job))


@router.get("/api/v1/storage/review", tags=["Support & Maintenance"])
def get_storage_review(limit: int = 200):
    return retention.review_list(limit=limit)


@router.post("/api/v1/storage/review/forget", tags=["Support & Maintenance"])
def post_storage_review_forget(payload: LeadChoice):
    return _refused(lambda: retention.forget_leads(payload.lead_ids))


@router.post("/api/v1/storage/review/keep", tags=["Support & Maintenance"])
def post_storage_review_keep(payload: LeadChoice):
    return _refused(lambda: retention.keep_leads(payload.lead_ids))


@router.get("/api/v1/storage/kept", tags=["Support & Maintenance"])
def get_storage_kept():
    """The people you kept from the review, and when, so a keep can be seen and taken back."""
    return retention.kept_list()


@router.delete("/api/v1/storage/kept/{lead_id}", tags=["Support & Maintenance"])
def delete_storage_kept(lead_id: str):
    """Takes a keep back."""
    return retention.unkeep(lead_id)


@router.post("/api/v1/storage/backups/scrub", tags=["Support & Maintenance"])
def post_storage_scrub(payload: Optional[ScrubChoice] = None):
    """Removes forgotten people from backups too, or, with leave, lets rotation do it."""
    if payload and payload.leave:
        return retention.leave_backups()
    return retention.scrub_backups()


@router.post("/api/v1/storage/compact", tags=["Support & Maintenance"])
def post_storage_compact():
    return _refused(retention.compact)
