"""
The Storage and Privacy Panel, Driven in a Browser.
===================================================
DATA-06 and DATA-01, from the creator's side. There was no storage or
retention control anywhere in the interface, and nothing told a creator
that a person they forgot stayed in their backups. Brand Studio now has a
Storage and privacy tab: sizes, each rule with its default, the last and
next backup, previews before anything is removed, the review list of
silent leads, and the disclosure about backups with its second step.

Runs the real app and the built interface on a loopback port. The browser
context blocks service workers, so every request is visible to the page.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import socket
import sqlite3
import sys
import tempfile
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(FRONTEND), reason="the interface is not built")

import uvicorn  # noqa: E402

from app import app  # noqa: E402
from database import init_db  # noqa: E402
import paths  # noqa: E402


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _seed():
    old = (datetime.now(timezone.utc) - timedelta(days=800)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO leads (id, name, full_name, lead_status, created_at, updated_at) "
                 "VALUES ('lead-quiet', 'Quentin Quiet', 'Quentin Quiet', 'NEW', ?, ?)", (old, old))
    conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at, comment_key, "
                 "first_seen_at, last_seen_at) VALUES ('lead-quiet', 'urn:li:activity:1', 'LIKE', ?, '', ?, ?)",
                 (old, old, old))
    # A database that already held readings asks before rolling them up.
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('retention_readings', 'ask')")
    conn.commit()
    conn.close()


@pytest.fixture(scope="module")
def studio_url():
    home = tempfile.mkdtemp(prefix="inox_r4_panel_")
    old_home = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = home
    init_db()
    _seed()
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error",
                                           access_log=False))
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
    if old_home is not None:
        os.environ["INOX_HYDRA_HOME"] = old_home
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def page(studio_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(studio_url, wait_until="networkidle")
        page.click('button[aria-label="Brand Studio"]')
        page.get_by_role("tab", name="Storage and privacy").click()
        yield page
        assert errors == [], errors
        context.close()
        browser.close()


def test_the_panel_shows_sizes_rules_defaults_and_backups(page):
    expect(page.get_by_role("heading", name="What this profile holds")).to_be_visible()
    expect(page.get_by_text("The database file")).to_be_visible()
    expect(page.get_by_text("Leads and their engagement")).to_be_visible()
    expect(page.get_by_label("Back up automatically once a day")).to_have_value("on")
    expect(page.get_by_text("DEFAULT ON")).to_be_visible()
    expect(page.get_by_text("DEFAULT 30 DAYS").first).to_be_visible()
    expect(page.get_by_text("Next automatic backup")).to_be_visible()
    expect(page.get_by_role("heading", name="Forgotten people and backups")).to_be_visible()
    expect(page.get_by_text("in backups you made yourself until you delete them", exact=False)).to_be_visible()
    assert page.locator("h1").count() == 1


def test_readings_wait_for_the_creator_and_preview_before_anything_is_removed(page):
    expect(page.get_by_text("WAITING FOR YOU")).to_be_visible()
    page.get_by_role("button", name="Preview and turn on").click()
    expect(page.get_by_text("Nothing to remove now.")).to_be_visible()
    page.get_by_role("button", name="Turn on", exact=True).click()
    expect(page.get_by_role("status").filter(has_text="Done")).to_be_visible()


def test_a_silent_lead_is_reviewed_forgotten_and_removed_from_backups_too(page):
    expect(page.get_by_text("1 person is still New", exact=False)).to_be_visible()
    page.get_by_role("button", name="Review them").click()
    page.get_by_label("Quentin Quiet", exact=False).check()
    page.get_by_role("button", name="Forget 1").click()
    expect(page.get_by_role("alertdialog")).to_contain_text("A backup is made first")
    page.get_by_role("button", name="Forget them").click()
    expect(page.get_by_role("status").filter(has_text="Forgot 1.")).to_be_visible()
    expect(page.get_by_text("may still be in older backups", exact=False)).to_be_visible()
    page.get_by_role("button", name="Remove from backups too").click()
    expect(page.get_by_role("status").filter(has_text="Removed from")).to_be_visible()
    expect(page.get_by_text("may still be in older backups", exact=False)).to_have_count(0)
