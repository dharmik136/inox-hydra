"""
Setup's first step stays done while LinkedIn sits in a background tab.
=====================================================================

BRIDGE-12 / SETUP-15  The launcher opens LinkedIn with the studio in a second
    tab. While the creator reads Setup, the LinkedIn tab is hidden, and the
    bridge sent its heartbeat only from a visible tab. After 150 s Setup
    unticked "Connect the browser", said "Open a LinkedIn tab in the bridge
    browser" and offered to open LinkedIn again, though the tab was open.

Now the heartbeat is sent from a hidden tab too, and the step is done once the
bridge has been heard from; how long ago is the line under it.
"""

import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
import uvicorn

from database import get_db
from qc_f3_pages import Pages, page_html

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# The bridge's half: own_pages.js on a hidden tab
# ---------------------------------------------------------------------------

def test_a_hidden_linkedin_tab_still_reports_the_bridge():
    pages = Pages()
    try:
        page = pages.open(
            "/feed/", page_html("<main></main>"), scripts=("voyager_schema.js", "content.js", "own_pages.js"),
            before="() => Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })",
        )
        page.clock.run_for(3 * 60 * 1000 + 1000)
        # Since cycle 4, track 1, phase 2 a tab reports to the worker
        # (PAGE_STATE), which beats once for the browser; a hidden tab still
        # reports, so the worker still counts it as open.
        beats = [m for m in pages.sent(page) if m.get("action") == "PAGE_STATE"]
        to_studio = pages.sent(page, "/api/v1/bridge/heartbeat")
    finally:
        pages.close()
    assert len(beats) >= 3, f"a hidden tab reported {len(beats)} times in three minutes"
    assert beats[-1]["visible"] is False
    assert to_studio == [], "a tab sent the studio a heartbeat of its own"


# ---------------------------------------------------------------------------
# The studio's half: Setup step 1 with a heartbeat 200 s old
# ---------------------------------------------------------------------------

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def studio_url():
    if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
        pytest.fail("studio/frontend_next is not built: run npm --prefix studio/ui run build")
    from app import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3.0)


@pytest.fixture
def heard_from_200_seconds_ago():
    conn = get_db()
    with conn:
        saved_beats = [dict(r) for r in conn.execute("SELECT * FROM bridge_heartbeats")]
        saved_identity = [dict(r) for r in conn.execute("SELECT * FROM creator_identity")]
        conn.execute("DELETE FROM bridge_heartbeats")
        conn.execute("DELETE FROM creator_identity")
        seen = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        conn.execute("INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) VALUES (?, '2.6.0', 'feed')",
                     (seen,))
    conn.close()
    yield
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM bridge_heartbeats")
        conn.execute("DELETE FROM creator_identity")
        for table, rows in (("bridge_heartbeats", saved_beats), ("creator_identity", saved_identity)):
            for row in rows:
                conn.execute(f"INSERT INTO {table} ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})",
                             tuple(row.values()))
    conn.close()


def test_step_one_stays_done_when_the_bridge_was_heard_from_minutes_ago(studio_url, heard_from_200_seconds_ago):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"])
        try:
            context = browser.new_context(service_workers="block")
            context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(studio_url) else r.abort())
            page = context.new_page()
            page.goto(studio_url, wait_until="networkidle")
            step = page.get_by_role("img", name="Step 1, done")
            step.wait_for(timeout=10000)
            item = page.locator("li", has=step)
            text = item.inner_text()
            assert "Last heard from 3 min ago" in text
            assert "THIS STEP TICKS BY ITSELF" not in text
        finally:
            browser.close()
