"""
Quality cycle 2026-10, batch F4a: the archive step on Setup, in a browser.
=========================================================================

Drives the built interface (studio/frontend_next) with Playwright's own
headless Chromium against a studio in a throwaway home. The archive is chosen
through the step's own file input; no button that opens a browser is pressed.
Every name and text here is invented.
"""

import io
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import zipfile

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built in this checkout", allow_module_level=True)

import uvicorn  # noqa: E402

import paths  # noqa: E402
from app import app  # noqa: E402
from database import init_db  # noqa: E402

SHARES = (
    "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"
    "2024-03-05 10:22:11,https://www.linkedin.com/feed/update/urn%3Ali%3Ashare%3A7170000000000000001,"
    '"A synthetic post about compilers.",,,MEMBER_NETWORK\n'
)
PROFILE = (
    "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,"
    "Twitter Handles,Websites,Instant Messengers\n"
    "Sample,Alice,,,,Synthetic headline,Synthetic about.,Software,,Synthetic City,,,\n"
)
CONNECTIONS = (
    "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
    "Ada,Example,https://www.linkedin.com/in/ada-example,,Co,Role,05 Mar 2024\n"
    "Hidden,Member,,,,,06 Mar 2024\n"
)


def _archive(members) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def studio(tmp_path, monkeypatch):
    """A studio with no profile confirmed and an empty database, on a free loopback port."""
    home = tempfile.mkdtemp(prefix="inox_f4a_ui_")
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
    yield {"url": f"http://127.0.0.1:{port}", "tmp": tmp_path}
    server.should_exit = True
    thread.join(timeout=5)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    # Module scoped, so it starts before `studio` points HOME at a throwaway folder.
    with sync_playwright() as p:
        chromium = p.chromium.launch(headless=True)
        yield chromium
        chromium.close()


@pytest.fixture
def setup_page(browser, studio):
    # The studio's service worker would hide requests from Playwright; it is blocked.
    context = browser.new_context(viewport={"width": 1280, "height": 900}, service_workers="block")
    page = context.new_page()
    try:
        page.goto(studio["url"], wait_until="networkidle")
        page.click('button[aria-label="Setup"]')
        expect(page.get_by_text("Your LinkedIn archive")).to_be_visible()
        yield page
    finally:
        context.close()


def _choose(page, studio, members, name="Complete_LinkedInDataExport_10-19-2026.zip"):
    path = studio["tmp"] / name
    path.write_bytes(_archive(members))
    page.set_input_files('input[aria-label="Choose your LinkedIn data archive"]', str(path))


def test_another_members_archive_waits_for_a_tick_naming_them(setup_page, studio):
    page = setup_page
    _choose(page, studio, {"Profile.csv": PROFILE, "Shares.csv": SHARES})
    expect(page.get_by_text("This archive belongs to Sample Alice.")).to_be_visible()
    submit = page.get_by_role("button", name="Import what is ticked")
    expect(submit).to_be_disabled()
    page.get_by_label("This is my archive: import Sample Alice's archive as my own record").check()
    expect(submit).to_be_enabled()
    submit.click()
    expect(page.get_by_text("Imported from Complete_LinkedInDataExport_10-19-2026.zip")).to_be_visible()
