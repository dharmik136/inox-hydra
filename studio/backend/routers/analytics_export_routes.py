"""
LinkedIn's Analytics Export API Router
======================================
What Setup's analytics export block reads and asks for: where the step
stands, the creator's word that they exported, an upload, a preview that
writes nothing, the import of what they kept ticked, and setting a copy
aside. studio/backend/analytics_export.py holds the reading; this only
carries it.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Zero egress: nothing here opens a connection.
- Nothing is written on a GET or by a preview.
"""

from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

try:
    from .. import analytics_export, licensing
except (ImportError, ValueError):
    import analytics_export
    import licensing

router = APIRouter()


class ExportSourcePayload(BaseModel):
    source: str = Field(..., min_length=1, max_length=2000, description="upload:<token> or downloads:<path>")


class ExportImportPayload(ExportSourcePayload):
    include: Optional[List[str]] = Field(None, description="Sheet names to import; the ticked defaults when omitted")


def _call(work):
    try:
        return work()
    except analytics_export.ExportBusy as error:
        raise HTTPException(status_code=409, detail=str(error))
    except analytics_export.ExportError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/api/v1/analytics-export", tags=["Onboarding"])
def get_export_state():
    """Whether an export was asked for, what is waiting in Downloads, and the last import. Writes nothing."""
    return analytics_export.export_state(look=True)


@router.post("/api/v1/analytics-export/requested", tags=["Onboarding"])
def post_export_requested():
    """The creator says they pressed Export on LinkedIn's analytics page, so Downloads may be looked in."""
    return analytics_export.mark_requested()


@router.post("/api/v1/analytics-export/upload", tags=["Onboarding"])
async def post_export_upload(request: Request):
    """
    Keeps a spreadsheet the creator chose by hand, and previews it. Nothing is imported.

    The raw body, streamed to disk with the size cap checked as it arrives.
    X-File-Modified is when the browser says the file was written, in
    milliseconds, which dates a post's own export.
    """
    declared = request.headers.get("content-length") or ""
    if declared.isdigit() and int(declared) > analytics_export.MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="That file is larger than any LinkedIn analytics export the studio expects.")
    modified = None
    raw = (request.headers.get("x-file-modified") or "").strip()
    if raw.isdigit():
        try:
            modified = datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            modified = None
    writer = analytics_export.UploadWriter(unquote(request.headers.get("x-export-name") or "analytics.xlsx"), modified)
    try:
        async for chunk in request.stream():
            await run_in_threadpool(writer.write, chunk)
    except analytics_export.ExportError as error:
        raise HTTPException(status_code=413, detail=str(error))
    except BaseException:
        writer.abort()
        raise
    source = writer.finish()

    def work():
        try:
            return analytics_export.preview(source)
        except BaseException:
            analytics_export.discard(source)
            raise
    return await run_in_threadpool(_call, work)


@router.post("/api/v1/analytics-export/preview", tags=["Onboarding"])
def post_export_preview(payload: ExportSourcePayload):
    """What the export holds, sheet by sheet, and what would be imported. Writes nothing."""
    return _call(lambda: analytics_export.preview(payload.source))


@router.post("/api/v1/analytics-export/import", tags=["Onboarding"])
def post_export_import(payload: ExportImportPayload):
    """Imports the sheets the creator kept ticked, every figure exact and named as the export's."""
    if not licensing.allows("analytics"):
        raise HTTPException(status_code=402, detail="Importing LinkedIn's analytics export is part of the Creator licence.")
    return _call(lambda: analytics_export.import_export(payload.source, payload.include))


@router.post("/api/v1/analytics-export/discard", tags=["Onboarding"])
def post_export_discard(payload: ExportSourcePayload):
    """Deletes the copy of a spreadsheet the creator chose by hand and then set aside."""
    return analytics_export.discard(payload.source)
