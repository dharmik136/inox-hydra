"""
Quality cycle 2026-10, batch F8 [WRITE-15 follow-up]: Today lists posts that are due.

A queued post whose time has come is now "due": the
studio does not post it, the creator does. Only the Queue listed due posts,
so a creator who opened Today, the first screen, was not told it was time.
Today now lists them first, with Copy text and I posted it.
"""

import os
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PREFIX = "post-f8-today-"


def _wipe():
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _post(suffix, status, minutes_from_now, content):
    when = (datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)).isoformat()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, ?, ?)",
                     (PREFIX + suffix, content, status, when))
    conn.close()
    return PREFIX + suffix


def _brief():
    response = client.get("/api/v1/today")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Due posts
# ---------------------------------------------------------------------------

def test_today_lists_posts_that_are_due_oldest_first_with_their_text():
    later = _post("b", "due", -5, "Second due post.\n\nIts body.")
    first = _post("a", "due", -60, "First due post.\n\nIts body.")
    _post("c", "scheduled", 120, "Still in the future.")
    _post("d", "published", -300, "Already out.")

    due = _brief()["queue"]["due"]
    ours = [d for d in due if d["post_id"].startswith(PREFIX)]
    assert [d["post_id"] for d in ours] == [first, later]
    assert ours[0]["content"] == "First due post.\n\nIts body.", "Copy text needs the whole post"
    assert ours[0]["excerpt"].startswith("First due post.")
    assert ours[0]["scheduled_for"]


def test_a_post_marked_posted_leaves_today():
    post_id = _post("a", "due", -30, "Due, then posted.")
    assert any(d["post_id"] == post_id for d in _brief()["queue"]["due"])
    assert client.post(f"/api/posts/{post_id}/publish-now").status_code == 200
    assert not any(d["post_id"] == post_id for d in _brief()["queue"]["due"])


def test_nothing_due_is_an_empty_list():
    _post("c", "scheduled", 120, "Still in the future.")
    assert [d for d in _brief()["queue"]["due"] if d["post_id"].startswith(PREFIX)] == []


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


def test_today_shows_a_due_post_and_i_posted_it_takes_it_off(studio_url):
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import expect, sync_playwright

    post_id = _post("a", "due", -30, "Time to post this one.\n\nBody.")
    with sync_playwright() as p:
        browser, page = _browser(p, studio_url)
        try:
            page.goto(studio_url + "/#/today", wait_until="networkidle")
            section = page.locator("section", has_text="Time to post this one.")
            expect(section).to_be_visible(timeout=10000)
            expect(section).to_contain_text("post it on LinkedIn")
            # Other tests may leave due posts in the shared database, so the
            # buttons are the ones on this post's own row.
            row = section.locator("li", has_text="Time to post this one.")
            row.get_by_role("button", name="Copy text").click()
            expect(section).to_contain_text("Copied")
            assert page.evaluate("() => navigator.clipboard.readText()") == "Time to post this one.\n\nBody."
            row.get_by_role("button", name="I posted it").click()
            expect(page.get_by_text("Time to post this one.")).to_have_count(0, timeout=10000)
        finally:
            browser.close()
    conn = get_db()
    status = conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()["status"]
    conn.close()
    assert status == "published"
