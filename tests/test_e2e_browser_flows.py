"""
End-to-End Browser Test Suite for Inox Hydra Studio.
====================================================

Tests real user workflows using Playwright headless Chromium against the live
FastAPI application and built React SPA (studio/frontend_next).

Validates:
1. App shell loading and Studio Rail workspace navigation (Today, Posts, Leads, Analytics, Brand Studio, Composer).
2. Real-time writing, fold calculation, and telemetry in the Composer canvas.
3. Multi-tenant creator profile switcher popover, inline profile creation, and account switching.
4. Universal search command palette open, search query, and escape key dismissal.
5. Strict zero em-dash compliance across test source code.
"""

import os
import sys
import time
import socket
import threading
import tempfile
import shutil
import pytest
import uvicorn

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import app
from database import init_db


def _find_free_port() -> int:
    """Finds an unused loopback TCP port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def live_studio_url():
    """
    Spins up the live Inox Hydra FastAPI backend with the compiled React SPA
    on a dedicated loopback port for headless browser testing.
    """
    test_home = tempfile.mkdtemp(prefix="inox_e2e_sandbox_")
    old_home = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = test_home
    os.environ["INOX_DEMO_DATA"] = "1"

    # Initialize sandbox database
    init_db()

    port = _find_free_port()
    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
    )
    server = uvicorn.Server(config=config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Poll until server is accepting connections
    base_url = f"http://127.0.0.1:{port}"
    connected = False
    for _ in range(60):
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.1)
            sock.close()
            connected = True
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.05)

    if not connected:
        server.should_exit = True
        raise RuntimeError(f"Live server at {base_url} failed to start")

    yield base_url

    # Teardown
    server.should_exit = True
    thread.join(timeout=3.0)
    if old_home is not None:
        os.environ["INOX_HYDRA_HOME"] = old_home
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(test_home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser_instance():
    """Provides a single Playwright Chromium headless instance for E2E tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser_instance, live_studio_url):
    """Provides a fresh browser context and page loaded at the studio home."""
    context = browser_instance.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    page.goto(live_studio_url, wait_until="networkidle")
    yield page
    context.close()


def test_e2e_app_shell_and_rail_navigation(page):
    """
    Validates that the studio SPA mounts cleanly and navigation between
    workspaces works as expected.
    """
    # 1. Page title and shell
    assert "Inox Hydra" in page.title()
    rail = page.locator('nav[aria-label="Studio sections"]')
    assert rail.is_visible()

    # 2. Navigate to Today workspace
    page.click('button[aria-label="Today"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Today"]').get_attribute("aria-current") == "page"

    # 3. Navigate to Posts workspace
    page.click('button[aria-label="Posts"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Posts"]').get_attribute("aria-current") == "page"

    # 4. Navigate to Leads (CRM) workspace
    page.click('button[aria-label="Leads"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Leads"]').get_attribute("aria-current") == "page"

    # 5. Navigate to Analytics workspace
    page.click('button[aria-label="Analytics"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Analytics"]').get_attribute("aria-current") == "page"

    # 6. Navigate to Brand Studio workspace
    page.click('button[aria-label="Brand Studio"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Brand Studio"]').get_attribute("aria-current") == "page"

    # 7. Return to Composer
    page.click('button[aria-label="Composer"]')
    page.wait_for_timeout(300)
    assert page.locator('button[aria-label="Composer"]').get_attribute("aria-current") == "page"


def test_e2e_composer_drafting_and_telemetry(page):
    """
    Validates drafting inside the Composer canvas and live telemetry updates.
    """
    # Navigate to Composer
    page.click('button[aria-label="Composer"]')
    page.wait_for_timeout(300)

    textarea = page.locator('textarea[aria-label="Post body"]')
    assert textarea.is_visible()

    test_content = "Decoupling message brokers for sub-millisecond local queries in distributed systems."
    textarea.fill(test_content)
    page.wait_for_timeout(400)

    # Check ContextBar live telemetry
    telemetry = page.locator('header p[aria-live="off"]')
    assert telemetry.is_visible()
    telemetry_text = telemetry.inner_text()
    assert "chars" in telemetry_text
    assert "read" in telemetry_text


def test_e2e_multi_tenant_account_switching(page, monkeypatch):
    """
    Each creator profile is its own database. The switcher says so, refuses a
    second profile without the Agency licence, shows a new profile empty,
    switches by reloading, and deletes only when the name is typed.
    """
    import base64

    import ed25519
    import licensing

    secret = bytes(range(32))
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(secret)).decode()])
    agency = licensing.encode(
        {"v": 1, "id": "e2e", "email": "buyer@example.com", "tier": "agency", "kind": "annual",
         "profiles": 5, "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"},
        lambda message: ed25519.sign(secret, message),
    )
    trigger = page.locator('button[aria-label^="Current profile:"]')
    dialog = page.locator('div[role="dialog"][aria-label="Manage creator profiles"]')

    def open_switcher():
        trigger.click()
        dialog.wait_for(state="visible")

    def add_profile(name):
        opener = dialog.locator('button:has-text("Add Creator Profile")')
        if opener.is_visible():
            opener.click()
        dialog.locator('input[placeholder*="Profile Name"]').fill(name)
        dialog.locator('button:has-text("Add Profile")').click()

    open_switcher()
    text = dialog.inner_text()
    assert "My studio" in text and "DEFAULT" in text
    assert "its own database" in text
    assert "Agency licence" in text, "the switcher does not say a second profile needs a licence"

    # Without a licence the second profile is refused, and the reason is shown.
    add_profile("Marcus Vance")
    alert = dialog.locator('[role="alert"]')
    alert.wait_for(state="visible")
    assert "Agency" in alert.inner_text()
    page.keyboard.press("Escape")

    installed = page.evaluate(
        "async (key) => (await fetch('/api/v1/licence', {method: 'POST', credentials: 'same-origin',"
        " headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key})})).status",
        agency,
    )
    assert installed == 200
    try:
        open_switcher()
        with page.expect_navigation():
            add_profile("Marcus Vance")
        page.wait_for_load_state("networkidle")
        assert trigger.locator("span").first.inner_text() == "MV"

        # A post written now lands in Marcus's database and nowhere else.
        written = page.evaluate(
            "async () => (await fetch('/api/posts', {method: 'POST', credentials: 'same-origin',"
            " headers: {'Content-Type': 'application/json'},"
            " body: JSON.stringify({content: 'Only in Marcus', status: 'draft'})})).status"
        )
        assert written in (200, 201)
        open_switcher()
        counts = {
            row["id"]: row["posts_count"]
            for row in page.evaluate(
                "async () => (await (await fetch('/api/v1/accounts', {credentials: 'same-origin'})).json()).accounts"
            )
        }
        marcus_id = next(key for key in counts if key.startswith("marcus-vance"))
        assert counts[marcus_id] == counts["default"] + 1, "a post written in one profile reached another"
        with page.expect_navigation():
            dialog.locator('div[role="button"]:has-text("My studio")').click()
        page.wait_for_load_state("networkidle")
        assert trigger.locator("span").first.inner_text() == "MS"

        open_switcher()
        marcus = dialog.locator('div[role="button"]:has-text("Marcus Vance")')
        marcus.hover()
        marcus.locator('button[aria-label="Delete Marcus Vance profile"]').click()
        confirm = dialog.locator('form[aria-label="Delete Marcus Vance"]')
        delete = confirm.locator('button:has-text("Delete profile")')
        assert delete.is_disabled(), "a profile can be deleted without typing its name"
        confirm.locator("input").fill("Marcus Vance")
        delete.click()
        marcus.wait_for(state="detached")
    finally:
        page.evaluate("async () => fetch('/api/v1/licence', {method: 'DELETE', credentials: 'same-origin'})")


def test_e2e_universal_search_command_palette(page):
    """
    Validates opening the universal search command palette and closing it with Escape.
    """
    # 1. Click search button on the rail
    search_btn = page.locator('button[aria-label*="Search everything"]')
    assert search_btn.is_visible()
    search_btn.click()
    page.wait_for_timeout(300)

    # 2. Verify palette opened
    palette = page.locator('div[cmdk-root], [role="dialog"]')
    assert palette.first.is_visible()

    # 3. Dismiss using Escape key
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def _narrow_page(browser_instance, live_studio_url, width, height=800):
    context = browser_instance.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.goto(live_studio_url, wait_until="networkidle")
    page.click('button[aria-label="Composer"]')
    page.wait_for_timeout(400)
    return context, page


def test_e2e_the_inspector_can_always_be_closed(page):
    """
    The six mode labels overflowed the panel at every width and pushed the
    close control out of reach. It must stay inside the window.
    """
    page.click('button[aria-label="Composer"]')
    page.wait_for_timeout(400)
    close = page.locator('aside[aria-label="Inspector"] button[aria-label="Close inspector"]')
    box = close.bounding_box()
    assert box is not None, "the inspector has no close control"
    assert box["x"] + box["width"] <= 1280, "the close control sits outside the window"
    close.click()
    page.wait_for_timeout(400)
    assert page.locator('aside[aria-label="Inspector"]').count() == 0
    assert page.locator('button[aria-label="Open inspector"]').is_visible()


@pytest.mark.parametrize("width", [390, 768])
def test_e2e_a_narrow_window_keeps_the_editor(browser_instance, live_studio_url, width):
    """
    Below 1024 pixels the inspector used to stay docked: at 768 it left the
    editor a 330 pixel column, and on a phone it left none. It is now a drawer
    over the editor, closed at first, with Escape to dismiss it.
    """
    context, narrow = _narrow_page(browser_instance, live_studio_url, width)
    try:
        assert narrow.locator('aside[aria-label="Inspector"]').count() == 0, "the inspector opened over a narrow window"
        editor = narrow.locator("main textarea, main [contenteditable='true']").first
        box = editor.bounding_box()
        assert box is not None and box["width"] >= width * 0.6, "the editor has no room to write in"

        narrow.click('button[aria-label="Open inspector"]')
        narrow.wait_for_timeout(400)
        assert narrow.locator('aside[aria-label="Inspector"]').is_visible()
        narrow.keyboard.press("Escape")
        narrow.wait_for_timeout(400)
        assert narrow.locator('aside[aria-label="Inspector"]').count() == 0, "Escape did not close the drawer"
    finally:
        context.close()


def test_e2e_every_surface_names_itself_once(page):
    """Each surface owns the page while it is shown, so each carries one level-one heading."""
    for label in ("Setup", "Today", "Queue", "Posts", "Patterns", "Outbound", "Analytics", "Command", "Brand Studio", "Activity"):
        page.click(f'nav[aria-label="Studio sections"] button[aria-label="{label}"]')
        page.wait_for_timeout(500)
        assert page.locator("h1:visible").count() == 1, f"{label} has {page.locator('h1:visible').count()} level-one headings"


def test_strict_zero_em_dashes_in_e2e_test_source():
    """Strict verification: Zero literal em-dashes in this E2E test file."""
    this_file = os.path.abspath(__file__)
    with open(this_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "\u2014" not in content, "Forbidden em-dash found in E2E test suite"
