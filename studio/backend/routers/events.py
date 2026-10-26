"""
The Change Stream
=================
GET /api/v1/events is a text/event-stream, one per studio window, that says
when something changed so the window reads again only then. What changed is
a word (studio/backend/changes.py names them); every figure a screen shows
still comes from the route that screen reads.

It is read by the browser's EventSource, which can send nothing but the
same-origin cookie, and the cookie is enough: the request passes the Host,
Origin and token checks in security.py exactly as every other route does,
and a foreign page is refused exactly as it is everywhere else. The extension's
own pages are not served by this stream, and do not need it: a capture passes
through the worker before it reaches the studio.

The first event, `hello`, names the profile the stream serves (EventSource
cannot send X-Inox-Profile) and says whether anything changed since the id
the window last saw, which the window sends as `?since=` when it reopens the
stream on coming back into view, and the browser sends as Last-Event-ID on a
reconnect of its own. A `change` event carries the kinds that changed since
the last one; a burst of thirty captures is one message. A comment line every
fifteen seconds keeps the connection from timing out. The stream ends when the
window goes away, and when the server stops: uvicorn waits for every response
in flight before it exits, so an endless stream would hold a reload for ever.

Strict Invariants:
- Zero em-dashes in all code, comments, and strings.
- Nothing here leaves the machine, and nothing here is a figure.
"""

import asyncio
import json
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

try:
    from .. import changes, paths
except (ImportError, ValueError):
    import changes
    import paths

router = APIRouter()

# A comment line this often keeps a proxy or a browser from closing a quiet
# stream; sse-starlette's default, and well under any idle timeout seen.
KEEP_ALIVE_S = 15.0
# How long after the first wake a change waits for the rest of its burst.
COALESCE_S = 0.25
# How often a quiet stream checks that its window is still there.
WAIT_S = 1.0
# What the browser is told to wait before reconnecting after a drop: long
# enough that a reload's new process is listening, short enough to be missed.
RETRY_MS = 2000


# An id is this process's boot name and its count of changes; anything longer
# than this is not one of ours.
MAX_ID = 64


def _event(name: str, event_id: str, payload: dict) -> str:
    return f"event: {name}\nid: {event_id}\ndata: {json.dumps(payload)}\n\n"


async def _stream(request: Request, since: Optional[str]) -> AsyncIterator[str]:
    sub = await changes.open_subscription()
    try:
        current = changes.current_id()
        hello = {
            "profile": paths.get_active_profile_id(),
            "id": current,
            # Unknown counts as changed: a window that never said what it
            # saw, or one that names an id from before the studio restarted.
            "changed": since != current,
        }
        yield f"retry: {RETRY_MS}\n" + _event("hello", current, hello)
        quiet_for = 0.0
        while not sub.closing:
            woken = await sub.wait(WAIT_S)
            if sub.closing or await request.is_disconnected():
                break
            if woken:
                await asyncio.sleep(COALESCE_S)
                kinds = sub.take()
                if kinds:
                    yield _event("change", changes.current_id(), {"kinds": kinds})
                quiet_for = 0.0
                continue
            quiet_for += WAIT_S
            if quiet_for >= KEEP_ALIVE_S:
                yield ": keep-alive\n\n"
                quiet_for = 0.0
    finally:
        changes.unsubscribe(sub)


@router.get("/api/v1/events", tags=["LinkedIn Bridge"])
async def get_events(request: Request, since: Optional[str] = None):
    """
    The change stream for one window. `since` is the id of the last event the
    window saw, so the hello can say whether it missed anything; a browser's
    own reconnect sends the same thing as Last-Event-ID.
    """
    if since is None:
        since = request.headers.get("last-event-id")
    if since is not None and len(since) > MAX_ID:
        since = None
    return StreamingResponse(
        _stream(request, since),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
