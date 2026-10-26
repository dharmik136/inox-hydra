"""
Health API Router
=================
What the Health section reads that no other route answered: each reader's
runs inside the prune's window, as counts on the first view and as rows one
level down, the day rows kept past the window, and the heartbeat summary. studio/backend/health.py holds the reads; this only carries them.

The rest of the section stands on routes that already existed:
/api/v1/extension/health, /api/v1/schema/status, /api/v1/storage/backups and
/api/v1/updates/status, with the update preference written through
/api/v1/updates/preference.

Strict Invariants:
- Zero em-dashes.
- Nothing here writes. A GET reads the log; it never prunes it.
"""

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

try:
    from .. import health
except (ImportError, ValueError):
    import health

router = APIRouter(tags=["Health"])


@router.get("/api/v1/bridge/readers")
def get_health_readers() -> Dict[str, Any]:
    """Per reader: state and runs in the last seven days, as counts; the heartbeats over the same week."""
    return health.readers()


@router.get("/api/v1/bridge/readers/{extractor}")
def get_health_reader(extractor: str) -> Dict[str, Any]:
    """One reader one level down: its newest runs this week and the day rows kept past the week."""
    detail = health.reader(extractor)
    if detail is None:
        raise HTTPException(status_code=404, detail="The extension reports on no reader of that name.")
    return detail
