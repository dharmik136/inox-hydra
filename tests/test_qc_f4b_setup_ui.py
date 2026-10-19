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


def test_with_a_browser_that_carries_the_bridge_no_folder_is_needed(page, studio_url):
    page.route("**/api/v1/browser/status", _fulfil({**CHROME_ONLY, "browsers": {
        "brave": {"id": "brave", "name": "Brave Browser", "path": "/x/brave", "is_available": True,
                  "carries_extension": True}}}))
    _open_setup(page, studio_url)
    step = page.locator("li", has_text="Connect the browser")
    assert step.get_by_text(EXTENSION_PATH).count() == 0
