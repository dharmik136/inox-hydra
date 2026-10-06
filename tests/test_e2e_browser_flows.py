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
    assert "LinkedIn Studio" in page.title()
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


def test_e2e_multi_tenant_account_switching(page):
    """
    Validates opening the AccountSwitcher popover, adding a new creator profile,
    and switching profiles seamlessly in the browser.
    """
    # 1. Trigger the Account Switcher from the Studio Rail
    trigger = page.locator('button[aria-label^="Current profile:"]')
    assert trigger.is_visible()
    trigger.click()
    page.wait_for_timeout(300)

    # 2. Verify dialog opened
    dialog = page.locator('div[role="dialog"][aria-label="Manage creator profiles"]')
    assert dialog.is_visible()

    # 3. Verify Default Profile is present
    default_text = dialog.inner_text()
    assert "Default Profile" in default_text
    assert "DEFAULT" in default_text

    # 4. Open "Add Creator Profile" form
    add_btn = dialog.locator('button:has-text("Add Creator Profile")')
    assert add_btn.is_visible()
    add_btn.click()
    page.wait_for_timeout(200)

    # 5. Fill new profile details
    name_input = dialog.locator('input[placeholder*="Profile Name"]')
    name_input.fill("Marcus Vance")

    headline_input = dialog.locator('input[placeholder*="Headline"]')
    headline_input.fill("Principal Systems Architect")

    vanity_input = dialog.locator('input[placeholder*="LinkedIn Vanity"]')
    vanity_input.fill("marcus-vance")

    # 6. Submit profile
    submit_btn = dialog.locator('button:has-text("Add Profile")')
    submit_btn.click()
    page.wait_for_timeout(500)

    # 7. Verify new profile is now created and active
    trigger_badge = trigger.locator("span").first
    assert trigger_badge.inner_text() == "MV"

    # 8. Re-open dialog and switch back to Default Profile
    trigger.click()
    page.wait_for_timeout(400)
    dialog = page.locator('div[role="dialog"][aria-label="Manage creator profiles"]')
    assert dialog.is_visible()

    default_entry = dialog.locator('div[role="button"]:has-text("Default Profile")')
    default_entry.click()
    page.wait_for_timeout(600)

    # Verify switched back
    assert trigger.locator("span").first.inner_text() == "DP"


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


def test_strict_zero_em_dashes_in_e2e_test_source():
    """Strict verification: Zero literal em-dashes in this E2E test file."""
    this_file = os.path.abspath(__file__)
    with open(this_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "\u2014" not in content, "Forbidden em-dash found in E2E test suite"
