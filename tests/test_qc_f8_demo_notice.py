"""
Quality cycle 2026-10, batch F8 [AUDIENCE-15 wiring]: Today says once what the demo cleanup removed.

The demo cleanup removes sample content an earlier version
seeded, after copying the database aside, and records what it removed under
the settings key demo_cleanup_notice with "shown": false. Today shows that
once, with the counts and where the copy is, until it is dismissed. The key is
read defensively: absent, malformed or already shown means nothing is shown.
"""

import json
import os
import socket
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NOTICE_KEY = "demo_cleanup_notice"
BACKUP = "/tmp/inox-test/backups/pre_demo_cleanup_20261020.db"


def _wipe():
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (NOTICE_KEY,))
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _notice(value):
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                     (NOTICE_KEY, value if isinstance(value, str) else json.dumps(value)))
    conn.close()


def _stored_notice():
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (NOTICE_KEY,)).fetchone()
    conn.close()
    return json.loads(row["value"]) if row else None


def _brief():
    response = client.get("/api/v1/today")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# The demo cleanup notice
# ---------------------------------------------------------------------------

def _f5a_notice(shown=False, removed=None):
    return {"removed": removed if removed is not None else
            {"leads": 0, "drafts": 16, "posts": 16, "analytics_days": 0, "audience_rows": 0},
            "backup": BACKUP, "removed_at": "2026-10-20T09:15:00", "shown": shown}


def test_an_unshown_notice_is_on_today_with_counts_and_the_copy():
    _notice(_f5a_notice())
    notice = _brief()["demo_cleanup"]
    assert notice["backup"] == BACKUP
    assert notice["removed"] == [{"kind": "drafts", "count": 16}, {"kind": "posts", "count": 16}]


def test_counts_at_the_top_level_are_read_too():
    _notice({"drafts": 2, "posts": 1, "backup": BACKUP, "shown": False})
    assert _brief()["demo_cleanup"]["removed"] == [{"kind": "drafts", "count": 2}, {"kind": "posts", "count": 1}]


@pytest.mark.parametrize("value", [
    None,                                   # absent
    "not json {",                           # malformed
    json.dumps(["drafts", 16]),             # not an object
    json.dumps(_f5a_notice(shown=True)),    # already shown
    json.dumps(_f5a_notice(removed={"drafts": 0, "posts": 0})),  # nothing removed
    json.dumps({"removed": {"drafts": "lots"}, "backup": BACKUP, "shown": False}),  # nonsense counts
])
def test_no_notice_unless_there_is_one_to_show(value):
    if value is not None:
        _notice(value)
    assert _brief().get("demo_cleanup") is None


def test_dismissing_marks_it_shown_and_keeps_the_record():
    _notice(_f5a_notice())
    response = client.post("/api/v1/today/demo-cleanup-notice/dismiss")
    assert response.status_code == 200, response.text
    assert response.json()["dismissed"] is True
    stored = _stored_notice()
    assert stored["shown"] is True and stored["backup"] == BACKUP and stored["removed"]["drafts"] == 16
    assert _brief().get("demo_cleanup") is None


def test_dismissing_with_no_notice_changes_nothing():
    response = client.post("/api/v1/today/demo-cleanup-notice/dismiss")
    assert response.status_code == 200 and response.json()["dismissed"] is False
    assert _stored_notice() is None
    _notice("not json {")
    assert client.post("/api/v1/today/demo-cleanup-notice/dismiss").json()["dismissed"] is False


# ---------------------------------------------------------------------------
# What Today shows
# ---------------------------------------------------------------------------

def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def studio_url():
    if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
        pytest.fail("studio/frontend_next is not built: run npm --prefix studio/ui run build")
    import uvicorn

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app_module.app, host="127.0.0.1", port=port,
                                           log_level="error", access_log=False))
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


def _browser(p, studio_url):
    browser = p.chromium.launch(headless=True, args=["--host-resolver-rules=MAP * ~NOTFOUND , EXCLUDE 127.0.0.1"])
    context = browser.new_context(service_workers="block")
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=studio_url)
    context.route("**/*", lambda r: r.continue_() if r.request.url.startswith(studio_url) else r.abort())
    return browser, context.new_page()


def test_today_shows_the_cleanup_notice_once(studio_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    _notice(_f5a_notice())
    with sync_playwright() as p:
        browser, page = _browser(p, studio_url)
        try:
            page.goto(studio_url + "/#/today", wait_until="networkidle")
            notice = page.get_by_role("status").filter(has_text="removed sample content")
            expect(notice).to_be_visible(timeout=10000)
            expect(notice).to_contain_text(
                "The studio removed sample content it had added itself: 16 drafts, 16 posts.")
            expect(notice).to_contain_text(f"A copy of your database from before is at {BACKUP}.")
            notice.get_by_role("button", name="Dismiss").click()
            expect(page.get_by_text("removed sample content")).to_have_count(0)
            page.reload(wait_until="networkidle")
            page.get_by_role("heading", level=1).wait_for()
            expect(page.get_by_text("removed sample content")).to_have_count(0)
        finally:
            browser.close()
    assert _stored_notice()["shown"] is True
