"""
Item 28, in a browser: Setup's analytics export block and the link to it
from Analytics.
========================================================================

Drives the built interface (studio/frontend_next) with Playwright's own
headless Chromium against a studio in a throwaway home. The export is chosen
through the block's own file input; the button that opens the bridge browser
is never pressed. Every name and figure is invented
(tests/linkedin_export_fixtures.py).

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
for folder in (BACKEND_DIR, os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

if not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built in this checkout", allow_module_level=True)

import uvicorn  # noqa: E402

import linkedin_export_fixtures as fx  # noqa: E402
from app import app  # noqa: E402
from database import get_db, init_db  # noqa: E402

AXE_JS = os.path.join(REPO_ROOT, "studio", "ui", "node_modules", "axe-core", "axe.min.js")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def studio(tmp_path, monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t6_export_ui_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    os.makedirs(tmp_path / "user" / "Downloads")
    init_db()
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
    yield {"url": f"http://127.0.0.1:{port}"}
    server.should_exit = True
    thread.join(timeout=5)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        chromium = p.chromium.launch(headless=True)
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser, studio):
    # Reduced motion, so a colour is measured where it rests, not part way
    # through the transition a theme switch starts.
    context = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block",
                                  reduced_motion="reduce")
    tab = context.new_page()
    try:
        yield tab
    finally:
        context.close()


def _setup(page, studio):
    page.goto(studio["url"] + "/#/setup", wait_until="networkidle")
    block = page.locator('section[aria-labelledby="analytics-export-title"]')
    expect(block).to_be_visible()
    return block


def _axe(page, selector):
    if not os.path.exists(AXE_JS):
        pytest.skip("axe-core is not installed with the UI dependencies")
    page.add_script_tag(path=AXE_JS)
    found = []
    for theme in ("dark", "light"):
        page.evaluate("(t) => t === 'light' ? document.documentElement.setAttribute('data-theme', 'light') "
                      ": document.documentElement.setAttribute('data-theme', 'dark')", theme)
        page.wait_for_timeout(100)
        found += page.evaluate("""async (selector) => {
            const r = await axe.run(document.querySelector(selector),
                { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } });
            return r.violations.map(v => v.id + ': ' + v.nodes.map(n => n.target.join(' ')).join(', '));
        }""", selector)
    return found


def test_setup_previews_the_export_sheet_by_sheet_and_imports_what_is_ticked(page, studio):
    block = _setup(page, studio)
    expect(block.get_by_text("CHECKED AGAINST A REAL LINKEDIN EXPORT: NOT YET", exact=False)).to_be_visible()
    data = fx.build(fx.dashboard_sheets() + [("Sheet9", [["Something", "else"], [1, 2]])])
    page.set_input_files('input[aria-label="Choose your LinkedIn analytics export"]',
                         files=[{"name": fx.DASHBOARD_NAME, "mimeType": XLSX, "buffer": data}])
    expect(block.get_by_text("COVERS 2026-09-26 TO 2026-10-25, READ FROM THE FILE'S NAME")).to_be_visible()
    expect(block.get_by_text("NOT RECOGNISED", exact=True)).to_be_visible()
    expect(block.get_by_text("Not recognised: the studio does not know a sheet called Sheet9", exact=False)).to_be_visible()
    # Nothing is written before the creator imports.
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0] == 0
    conn.close()
    assert _axe(page, 'section[aria-labelledby="analytics-export-title"]') == []
    block.get_by_role("button", name="Import what is ticked").click()
    expect(block.get_by_text("Days: 30 added, 0 brought up to date, 0 kept as your analytics page read them.")).to_be_visible()
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM analytics_daily WHERE source = 'linkedin_export'").fetchone()[0] == 30
    conn.close()


def test_analytics_links_to_the_export_in_setup(page, studio):
    page.goto(studio["url"] + "/#/analytics", wait_until="networkidle")
    link = page.get_by_role("link", name="Import LinkedIn's analytics export in Setup")
    expect(link).to_be_visible()
    assert _axe(page, 'a[href="#/setup"]') == []
    link.click()
    expect(page.locator('section[aria-labelledby="analytics-export-title"]')).to_be_visible()
    expect(page.get_by_role("heading", level=1)).to_have_count(1)
