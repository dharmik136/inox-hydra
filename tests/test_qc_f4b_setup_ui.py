"""
Quality cycle 2026-10, batch F4b: the Setup and Today screens, driven in a browser.
==================================================================================

Playwright's own headless Chromium against the app and the built UI. Every
route that would open a browser is answered by the page itself (page.route),
so nothing here reaches the launcher, and service workers are blocked so the
studio's own cannot hide a request from page.route.

SETUP-22. With only Chrome installed, step 1 said to load the extension by
hand "from the path below", and Setup showed no path.
"""

import json
import os
import socket
import sys
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import uvicorn

from app import app
from database import get_db

BUILT = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(BUILT), reason="the UI is not built (npm --prefix studio/ui run build)")

ME = "sample-gita"
EXTENSION_PATH = "/opt/inox/studio/extension"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def studio_url():
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


@pytest.fixture(scope="module")
def chromium():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


def _wipe():
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "creator_positions", "creator_education", "creator_skills",
                          "own_posts", "outbound_engagements", "self_import_requests", "bridge_heartbeats",
                          "post_metric_observations"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM settings WHERE key IN ('identity_filled_profile', 'history_sync_chain')")
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _confirm():
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO creator_identity (id, vanity, display_name, profile_url, confirmed_at, "
                     "profile_observed_at) VALUES (1, ?, 'Sample Gita', ?, '2026-10-01T00:00:00+00:00', "
                     "'2026-10-01T00:00:00+00:00')", (ME, f"https://www.linkedin.com/in/{ME}/"))
    conn.close()


def _fulfil(body, status=200):
    return lambda route: route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


@pytest.fixture
def page(chromium, studio_url):
    context = chromium.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    page = context.new_page()
    sent = []
    # Nothing in these tests may reach a real launcher.
    for path in ("**/api/v1/browser/launch", "**/api/v1/self/sync-all", "**/api/v1/browser/create-shortcuts"):
        page.route(path, lambda route: (sent.append(route.request.url),
                                        route.fulfill(status=500, body="not in this test"))[1])
    page.sent = sent
    yield page
    context.close()


def _open_setup(page, studio_url):
    page.goto(studio_url, wait_until="networkidle")
    page.click('button[aria-label="Setup"]')
    page.wait_for_selector("text=Teach the studio who you are")


CHROME_ONLY = {"status": "success", "extension_path": EXTENSION_PATH, "total_detected": 1, "browsers": {
    "chrome": {"id": "chrome", "name": "Google Chrome", "path": "/x/chrome", "is_available": True,
               "carries_extension": False}}}


def test_with_only_chrome_step_one_shows_the_folder_to_load(page, studio_url):
    page.route("**/api/v1/browser/status", _fulfil(CHROME_ONLY))
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Connect the browser")
    assert step.get_by_text(EXTENSION_PATH).is_visible()
    assert step.get_by_role("button", name="Copy the folder path").is_visible()
    assert step.get_by_text("Load unpacked").first.is_visible()


# ---------------------------------------------------------------------------
# SETUP-07 [UX-02]. One click on a 10 px line deleted the identity, every
# imported post, every reading of their figures, comments, reactions,
# connections and the archive record, with no confirmation and no backup.
# ---------------------------------------------------------------------------

def _seed_history():
    _confirm()
    conn = get_db()
    with conn:
        for i in range(3):
            urn = f"urn:li:activity:73000000000000020{i:02d}"
            conn.execute("INSERT INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) "
                         "VALUES (?, 'A post', '2026-10-01', '2026-10-01')", (urn,))
            conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, source, "
                         "reactions) VALUES (?, '2026-10-01T10:00:00+00:00', '2026-10-01T10', 'activity_page', 4)",
                         (urn,))
        conn.execute("INSERT INTO outbound_engagements (target_activity_urn, kind, my_text_key, first_seen_at, "
                     "last_seen_at) VALUES ('urn:li:activity:7300000000000009999', 'reaction', '', '2026-10-01', "
                     "'2026-10-01')")
    conn.close()


def _own_post_count():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0]
    finally:
        conn.close()


def test_onboarding_state_counts_what_deleting_would_remove():
    from fastapi.testclient import TestClient
    _seed_history()
    counts = TestClient(app).get("/api/v1/onboarding/state").json()["counts"]
    assert counts["posts"] == 3 and counts["readings"] == 3 and counts["reactions"] == 1
    assert "connections" in counts


def test_deleting_everything_needs_a_deliberate_confirmation(page, studio_url):
    _seed_history()
    deletes = []
    page.on("request", lambda r: deletes.append(r.url) if r.method == "DELETE" and "/api/v1/identity" in r.url else None)
    page.route("**/api/v1/support/backups", _fulfil({"directory": "/x", "count": 0, "backups": []}))
    _open_setup(page, studio_url)

    page.get_by_role("button", name="Not you, or want it gone? Delete everything the studio holds about you").click()
    page.wait_for_timeout(400)
    assert deletes == [], "one click deleted everything"
    assert _own_post_count() == 3

    panel = page.get_by_role("region", name="Delete everything the studio holds about you")
    panel.get_by_text("no backup", exact=False).wait_for(timeout=5000)
    text = panel.inner_text()
    assert "3 of your posts" in text and "3 readings" in text, text
    assert "1 reaction" in text
    assert "no backup" in text.lower()
    assert panel.get_by_role("button", name="Back up first").is_visible()

    confirm = panel.get_by_role("button", name="Delete everything")
    assert confirm.is_disabled()
    panel.get_by_label("Type delete to confirm").fill("delete")
    assert confirm.is_enabled()
    confirm.click()
    page.wait_for_timeout(600)
    assert len(deletes) == 1
    assert _own_post_count() == 0


def test_keeping_it_deletes_nothing(page, studio_url):
    _seed_history()
    page.route("**/api/v1/support/backups", _fulfil({"directory": "/x", "count": 1, "backups": [
        {"name": "inox_backup_manual_20261018_101500.zip", "bytes": 10, "modified": "2026-10-18T10:15:00"}]}))
    _open_setup(page, studio_url)
    page.get_by_role("button", name="Not you, or want it gone? Delete everything the studio holds about you").click()
    panel = page.get_by_role("region", name="Delete everything the studio holds about you")
    panel.get_by_text("2026-10-18", exact=False).wait_for(timeout=5000)
    panel.get_by_role("button", name="Keep it").click()
    assert panel.count() == 0
    assert _own_post_count() == 3


def test_the_session_delete_asks_once_before_it_deletes(page, studio_url):
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', 'sample-not-a-real-session')")
    conn.close()
    try:
        cookie_deletes = []
        page.on("request", lambda r: cookie_deletes.append(r.url)
                if r.method == "DELETE" and "/api/auth/cookies" in r.url else None)
        page.route("**/api/auth/cookies", _fulfil({"status": "success"}))
        _open_setup(page, studio_url)
        section = page.locator("section", has_text="LINKEDIN SESSION")
        section.get_by_role("button", name="Delete", exact=True).click()
        page.wait_for_timeout(300)
        assert cookie_deletes == []
        section.get_by_role("button", name="Yes, delete the session").click()
        page.wait_for_timeout(300)
        assert len(cookie_deletes) == 1
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM settings WHERE key = 'li_at'")
        conn.close()


# ---------------------------------------------------------------------------
# UX-06. What happened after a click was written at the bottom of a long page,
# out of sight of the button, so it looked as though nothing had happened.
# ---------------------------------------------------------------------------

def _in_view(page, locator):
    box = locator.bounding_box()
    return box is not None and 0 <= box["y"] and box["y"] + box["height"] <= page.viewport_size["height"]


def test_a_launch_error_appears_beside_the_button_that_caused_it(page, studio_url):
    page.route("**/api/v1/browser/launch",
               _fulfil({"detail": "No supported browser was found on this machine."}, status=500))
    _open_setup(page, studio_url)
    page.get_by_role("button", name="Open LinkedIn with the bridge").click()
    message = page.get_by_text("No supported browser was found on this machine.")
    message.wait_for(timeout=5000)
    assert _in_view(page, message), "the error is out of sight of the button"
    step = page.locator("li", has_text="Connect the browser")
    assert step.get_by_text("No supported browser was found on this machine.").count() == 1


def test_an_import_result_appears_in_the_history_step(page, studio_url):
    _confirm()
    page.route("**/api/v1/self/sync-all", _fulfil({"detail": "Launched Google Chrome. Nothing was imported."},
                                                   status=409))
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Your history")
    step.get_by_role("button", name="Import all three").click()
    step.get_by_text("Nothing was imported.", exact=False).wait_for(timeout=5000)


def test_todays_result_appears_where_you_clicked(page, studio_url):
    _confirm()
    page.route("**/api/v1/today", _fulfil({
        "status": "success", "identity": {"known": True, "name": "Sample Gita"},
        "freshness": {"bridge": {"connected": False, "last_seen_at": None, "seconds_ago": None},
                      "drifting": [], "last_capture_at": None},
        "reply_to": [], "latest_post": None,
        "queue": {"next_scheduled": None, "next_open_slot": None},
        "open_next": {"action": "open", "url": "https://www.linkedin.com/feed/",
                      "reason": "The bridge has not been heard from recently, so nothing is being captured."}}))
    page.route("**/api/v1/browser/launch", _fulfil({
        "status": "error", "message": "No Chromium browser was found on this computer, so nothing opened."}))
    page.goto(studio_url, wait_until="networkidle")
    page.click('button[aria-label="Today"]')
    section = page.locator("section", has_text="ONE THING TO OPEN")
    section.get_by_role("button").first.click()
    message = section.get_by_text("so nothing opened", exact=False)
    message.wait_for(timeout=5000)
    assert _in_view(page, message)


def test_step_five_is_not_ticked_by_the_archive_alone(page, studio_url):
    """SETUP-13: rows from the archive are not your posts read to the end, which Today needs."""
    _seed_history()
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Your history")
    step.get_by_text("has not been read to its end yet", exact=False).wait_for(timeout=5000)
    assert step.locator('[aria-label="Step 5"]').count() == 1, "step 5 is ticked"


def test_an_import_by_an_older_extension_says_to_reload_it(page, studio_url):
    """Review of BRIDGE-04: the row said NOT TO THE END. IMPORT AGAIN, which looped while the old extension ran."""
    _confirm()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, started_at, finished_at, items_seen, "
                     "outcome) VALUES ('posts', '2026-10-01T10:00:00+00:00', '2026-10-01T10:00:00+00:00', "
                     "'2026-10-01T10:05:00+00:00', 40, 'completed')")
    conn.close()
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Your history")
    row = step.get_by_text("OLDER EXTENSION", exact=False).first
    row.wait_for(timeout=5000)
    text = step.inner_text()
    assert "RELOAD" in text.upper() and "EXTENSIONS PAGE" in text.upper()
    assert "NOT TO THE END" not in text.upper()


def test_an_unchecked_browser_is_not_said_to_fail(page, studio_url):
    """Review of SETUP-22: Opera has not been probed, which is not the same as cannot."""
    page.route("**/api/v1/browser/status", _fulfil({**CHROME_ONLY, "browsers": {
        "opera": {"id": "opera", "name": "Opera", "path": "/x/opera", "is_available": True,
                  "carries_extension": None}}}))
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Connect the browser")
    step.get_by_text(EXTENSION_PATH).wait_for(timeout=5000)
    text = step.inner_text()
    assert "Opera cannot" not in text
    assert "has not been checked" in text


def test_with_a_browser_that_carries_the_bridge_no_folder_is_needed(page, studio_url):
    page.route("**/api/v1/browser/status", _fulfil({**CHROME_ONLY, "browsers": {
        "brave": {"id": "brave", "name": "Brave Browser", "path": "/x/brave", "is_available": True,
                  "carries_extension": True}}}))
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Connect the browser")
    assert step.get_by_text(EXTENSION_PATH).count() == 0
