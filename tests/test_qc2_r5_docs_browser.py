"""
Batch R5, D-5 in the built interface: the Docs home and its name filter offer
a creator the help, not the maintainer and retired documents.
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
import uvicorn  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built (npm --prefix studio/ui run build)", allow_module_level=True)

from app import app  # noqa: E402
from database import init_db  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def studio_url():
    home = tempfile.mkdtemp(prefix="inox_qc2_r5_docs_")
    previous = os.environ.get("INOX_HYDRA_HOME")
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


@pytest.fixture
def page(studio_url, monkeypatch):
    monkeypatch.delenv("INOX_DEV_MODE", raising=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block", viewport={"width": 1280, "height": 800})
        page = context.new_page()
        page.goto(f"{studio_url}/#/docs", wait_until="networkidle")
        yield page
        context.close()
        browser.close()


def test_the_docs_home_offers_only_the_help(page):
    main = page.locator("main")
    expect(main.get_by_role("heading", name="What do you need to know?")).to_be_visible()
    expect(main.get_by_text("Your data and privacy").first).to_be_visible()
    assert main.get_by_text("For maintainers").count() == 0
    assert main.get_by_text("Retired manuals and history").count() == 0


def test_the_name_filter_skips_hidden_documents(page):
    # The probe has to be a word a creator's own help answers: "architecture"
    # reached the help only through browse-the-swipe-file.md, which was
    # retired with the Swipe File (cycle 3, batch T7), so a consumer build now
    # finds nothing for it and the filter has nothing to skip.
    page.get_by_label("Search the documentation").fill("analytics")
    page.wait_for_timeout(600)
    main = page.locator("main")
    expect(main.get_by_text("result", exact=False).first).to_be_visible()
    # ARCHITECTURE.md and DATA_ARCHITECTURE.md are maintainer reference.
    assert main.get_by_text("ARCHITECTURE.md").count() == 0
    assert main.get_by_text("DATA_ARCHITECTURE.md").count() == 0
    assert main.get_by_text("For maintainers").count() == 0


def test_dev_mode_brings_them_back(studio_url, monkeypatch):
    """The control: the same checks see the maintainer documents when they are shown."""
    monkeypatch.setenv("INOX_DEV_MODE", "1")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block", viewport={"width": 1280, "height": 800})
        try:
            page = context.new_page()
            page.goto(f"{studio_url}/#/docs", wait_until="networkidle")
            main = page.locator("main")
            expect(main.get_by_text("For maintainers").first).to_be_visible()
            # "architecture" here, because this control asserts that
            # ARCHITECTURE.md itself comes back when maintainer documents are
            # shown, and the filter matches a document's name.
            page.get_by_label("Search the documentation").fill("architecture")
            page.wait_for_timeout(600)
            expect(main.get_by_text("ARCHITECTURE.md").first).to_be_visible()
        finally:
            context.close()
            browser.close()
