"""
The event bus is gone, and nothing a creator can reach went with it.
====================================================================

`event_bus.py` was a well built in-memory broadcaster with a replay ring, a
subscriber cap, an eviction sentinel, cross-thread hand-back to the owning
loop, and SSE wire formatting. It had five event types, seven publish sites,
and zero subscribers anywhere in the product.

The three routes that once served it, `GET /api/v1/stream/events`,
`GET /api/v1/stream/history` and `POST /api/v1/stream/broadcast`, were removed
in cycle 2 because the broadcast route accepted a forged `post_published`.
The two read-only routes went with the forgeable one. The publishers stayed,
and so did five docstrings describing a live stream to a browser that was not
listening: `event_bus.py:3-6`, `scheduler.py:11` and `:15`, `ingress.py:353`,
`app.py:967`.

Measured on this branch before the removal, after a full `import app`:
`event_bus.subscriber_count == 0`, `len(get_history()) == 0`, no `EventSource`
anywhere in `studio/ui/src`, and `grep -rn "event_bus.subscribe"` over
`studio/` matched only `event_bus.py` itself.

The decision was to remove rather than wire. Wiring it needs a read-only SSE
route plus an `EventSource` hook plus the six per-component `busy` flags merged
into one surface, which is the screen work batches T5 to T7 own and the PRD
gates behind this one. Adding a route nothing reads would have been the same
fault in a new place. These tests hold the removal: the module is gone, the
publishers are gone, the claims are gone, and every flow that published an
event still works and is still visible by the route the screen actually reads.
"""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "studio", "backend"))

import app as app_module
from database import get_db

client = TestClient(app_module.app)

PUBLISHED_FROM = (
    os.path.join("studio", "backend", "app.py"),
    os.path.join("studio", "backend", "scheduler.py"),
    os.path.join("studio", "backend", "ingress.py"),
    os.path.join("studio", "backend", "routers", "queue.py"),
    os.path.join("studio", "backend", "routers", "posts.py"),
)


def test_the_module_is_gone():
    assert not os.path.exists(os.path.join(REPO, "studio", "backend", "event_bus.py"))
    with pytest.raises(ImportError):
        __import__("event_bus")


def test_nothing_publishes_to_it_any_more():
    """Seven publish sites across five files, every one of them into a void."""
    for relative in PUBLISHED_FROM:
        with open(os.path.join(REPO, relative), encoding="utf-8") as handle:
            source = handle.read()
        assert "event_bus" not in source, f"{relative} still names the event bus"


def test_no_docstring_describes_a_stream_that_does_not_exist():
    """
    The claims were the part that cost a reader time: five of them, each
    describing zero-latency live streaming to a browser Studio UI.
    """
    claims = ("SSE bus", "via SSE", "SSE stream", "SSE real-time", "Server-Sent Events",
              "real-time event bus", "event nothing listens to")
    for relative in PUBLISHED_FROM + (os.path.join("studio", "backend", "gstack_governance.py"),):
        with open(os.path.join(REPO, relative), encoding="utf-8") as handle:
            source = handle.read()
        for claim in claims:
            assert claim not in source, f"{relative} still promises a stream: {claim}"


def test_the_stream_routes_are_still_gone():
    """Cycle 2 removed them because one accepted a forged post_published."""
    # 404 or 405: with the interface built, its catch-all answers GET for an
    # unknown path, so a POST to one is Method Not Allowed. Either way there
    # is no route, which is how tests/test_qc2_r2_route_surface.py pins them.
    for path in ("/api/v1/stream/events", "/api/v1/stream/history"):
        assert client.get(path).status_code in (404, 405), path
    assert client.post("/api/v1/stream/broadcast", json={}).status_code in (404, 405)


def test_nothing_a_creator_can_reach_depended_on_it():
    """
    The three flows that published an event. Each one still does its work and
    is still readable by the route the screen reads, which is how the creator
    learned about it before as well: nothing subscribed to the bus.
    """
    # Publish now: the post moves, and the Posts screen's own route says so.
    made = client.post("/api/posts", json={"content": "A post the bus used to announce.",
                                           "status": "draft"})
    assert made.status_code in (200, 201), made.text
    body = made.json()
    post_id = body.get("id") or body.get("post_id") or body.get("post", {}).get("id")
    assert post_id, made.text
    published = client.post(f"/api/posts/{post_id}/publish-now")
    assert published.status_code == 200, published.text
    listed = client.get("/api/posts").json()
    rows = listed.get("posts") or listed.get("data") or []
    assert any(row["id"] == post_id and row["status"] == "published" for row in rows)

    # The queue pausing: the state is read back, not pushed.
    paused = client.post("/api/queue/toggle-pause", json={"paused": True})
    assert paused.status_code == 200, paused.text
    assert client.get("/api/queue/status").json()["queue_paused"] is True
    client.post("/api/queue/toggle-pause", json={"paused": False})

    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    finally:
        conn.close()


def test_the_scheduler_still_reports_what_it_did():
    """
    The dispatcher published post_due and schedule_recovery. It returns the
    same facts to its caller, which is what Today and the Queue read.
    """
    from scheduler import native_scheduler
    actions = native_scheduler.check_scheduled_queue()
    assert isinstance(actions, list)


def test_importing_the_app_no_longer_starts_a_broadcaster():
    """
    A module-level singleton with a growing ring buffer nobody read. The one
    thread an import still starts is the single writer, which now has work.
    """
    probe = (
        "import threading, sys, os\n"
        "before = {t.name for t in threading.enumerate()}\n"
        "sys.path.insert(0, os.path.join(os.getcwd(), 'studio', 'backend'))\n"
        "import app\n"
        "after = {t.name for t in threading.enumerate()}\n"
        "print(sorted(after - before))\n"
    )
    env = dict(os.environ)
    env["INOX_HYDRA_HOME"] = env.get("INOX_HYDRA_HOME", "")
    done = subprocess.run([sys.executable, "-c", probe], cwd=REPO, env=env,
                          capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    started = done.stdout.strip().splitlines()[-1]
    assert "EventBus" not in started and "event" not in started.lower(), started
