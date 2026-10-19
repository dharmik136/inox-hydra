"""
The publish flow, the queue and the request core, driven in the built interface.
================================================================================

Headless Chromium against the real app on a loopback port, with its own
sandboxed home. Every context blocks service workers, because the studio's
worker would otherwise answer requests the tests route.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest
import uvicorn

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import app  # noqa: E402
from database import get_db, init_db  # noqa: E402
from security import TOKEN_HEADER, get_or_create_token  # noqa: E402

FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def studio_url():
    if not os.path.exists(FRONTEND):
        pytest.skip("the interface is not built (npm --prefix studio/ui run build)")
    home = tempfile.mkdtemp(prefix="inox_qc_f1b_ui_")
    old_home = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = home
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
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=3.0)
    if old_home is not None:
        os.environ["INOX_HYDRA_HOME"] = old_home
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def context(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    yield ctx
    ctx.close()


@pytest.fixture
def api(studio_url):
    """Direct calls to the same server, as the test's own hands."""
    import httpx

    with httpx.Client(base_url=studio_url, headers={TOKEN_HEADER: get_or_create_token()}) as client:
        yield client


def _rows(status=None):
    conn = get_db()
    try:
        if status:
            return [dict(r) for r in conn.execute("SELECT * FROM posts WHERE status = ?", (status,))]
        return [dict(r) for r in conn.execute("SELECT * FROM posts")]
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean_posts(studio_url):
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE content LIKE 'QC F1B%'")
        conn.commit()
    finally:
        conn.close()


def _open(context, studio_url, section=None):
    page = context.new_page()
    page.goto(studio_url, wait_until="networkidle")
    if section:
        page.get_by_role("button", name=section, exact=True).first.click()
    return page


# ---------------------------------------------------------------------------
# UX-21: losing the studio is announced, in words
# ---------------------------------------------------------------------------

def test_a_lost_studio_is_announced_and_never_reads_failed_to_fetch(context, studio_url):
    page = _open(context, studio_url)
    context.route("**/api/**", lambda route: route.abort())
    page.keyboard.press("Control+k")
    page.keyboard.type("anything")
    page.wait_for_timeout(800)
    banner = page.get_by_role("alert").filter(has_text="goes away by itself")
    banner.first.wait_for(timeout=5000)
    assert "Failed to fetch" not in page.inner_text("body")
    context.unroute("**/api/**")
    # The banner asks again by itself and goes once the studio answers.
    banner.first.wait_for(state="detached", timeout=12000)
