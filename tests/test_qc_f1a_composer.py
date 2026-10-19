"""
Composer editing and drafts, driven in a real browser
=====================================================
The quality cycle's F1a batch: unsaved work, applying hooks, saving drafts,
formatting, the strip's counts, screen addresses, the theme and the marks in
the header. Each test drives the built interface (studio/frontend_next) in
headless Chromium against an in-process studio, the way
tests/test_e2e_browser_flows.py does, because every one of these defects lived
in the interaction between the editor and the page rather than in one function.

Every context blocks service workers. The studio registers one for
installability, and a request it serves never reaches page.route, so a test
that intercepts the network without this is not intercepting it.
"""

import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

BUILT_INDEX = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
if not os.path.exists(BUILT_INDEX):
    pytest.skip("studio/frontend_next is not built (npm --prefix studio/ui run build)", allow_module_level=True)

from app import app  # noqa: E402
from database import init_db  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def studio_url():
    """A studio with its own throwaway home, serving the built interface."""
    home = tempfile.mkdtemp(prefix="inox_qc_f1a_")
    previous = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = home
    os.environ["INOX_DEMO_DATA"] = "1"
    init_db()

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
    else:
        server.should_exit = True
        raise RuntimeError("the studio did not start")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=3.0)
    if previous is not None:
        os.environ["INOX_HYDRA_HOME"] = previous
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def api(studio_url):
    """The same studio, called directly, for arranging and checking rows."""
    from fastapi.testclient import TestClient

    return TestClient(app)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def new_page(browser):
    """Opens a page in a fresh context. Several per test model several tabs."""
    contexts = []

    def make(**options):
        options.setdefault("viewport", {"width": 1280, "height": 800})
        context = browser.new_context(service_workers="block", **options)
        contexts.append(context)
        return context.new_page()

    yield make
    for context in contexts:
        context.close()


def _clear_posts(api):
    for row in api.get("/api/posts").json()["posts"]:
        api.delete(f"/api/posts/{row['id']}")


def _open_composer(page, studio_url):
    page.goto(studio_url + "/", wait_until="networkidle")
    page.get_by_role("button", name="Composer", exact=True).first.click()
    editor = page.get_by_label("Post body")
    expect(editor).to_be_visible()
    return editor


def _status(page):
    return page.locator("header [role=status]").first


def _rows_with(api, content):
    return [row for row in api.get("/api/posts").json()["posts"] if row["content"] == content]


def test_the_strip_shows_the_count_against_linkedins_limit(new_page, studio_url, api):
    _clear_posts(api)
    page = new_page()
    editor = _open_composer(page, studio_url)
    strip = page.locator('header p[aria-live="off"]')
    editor.fill("a" * 2999)
    expect(strip).to_contain_text("2,999 / 3,000")
    expect(strip.locator(".text-signal-orange-text", has_text="/ 3,000")).to_have_count(0)

    # Devanagari vowel signs are characters the limit counts, as the Audit does.
    hindi = "नमस्ते " * 450
    editor.fill(hindi)
    counted = api.post("/api/v1/gstack/audit", json={"content": hindi}).json()["audit"]["gates"]["gate_2_eng_manager"]["char_count"]
    expect(strip).to_contain_text(f"{counted:,} / 3,000")
    expect(strip).to_contain_text(f"{len(hindi):,} / 3,000")
    expect(strip.locator(".text-signal-orange-text", has_text="/ 3,000")).to_be_visible()
