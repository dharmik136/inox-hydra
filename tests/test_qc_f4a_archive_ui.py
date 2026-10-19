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
import re
import shutil
import socket
import sqlite3
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


def _import_by_hand(page, studio, members, name="Complete_LinkedInDataExport_10-19-2026.zip"):
    _choose(page, studio, members, name)
    page.get_by_label("This is my archive: import Sample Alice's archive as my own record").check()
    page.get_by_role("button", name="Import what is ticked").click()
    expect(page.get_by_text(f"Imported from {name}")).to_be_visible()
    page.get_by_role("button", name="Done").click()


def test_an_import_can_be_removed_before_any_profile_is_confirmed(setup_page, studio):
    page = setup_page
    _import_by_hand(page, studio, {"Profile.csv": PROFILE, "Shares.csv": SHARES, "Connections.csv": CONNECTIONS})
    expect(page.get_by_text("Fills in once you have confirmed it is you")).to_be_visible()
    page.get_by_role("button", name="Remove what this import added").click()
    page.get_by_role("button", name="Remove it").click()
    expect(page.get_by_text("Removed what that import added: 1 post, 1 connection and 4 profile details.")
           ).to_be_visible()
    expect(page.get_by_role("button", name="Remove what this import added")).to_have_count(0)
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0] == 0


def test_the_basic_archive_says_the_posts_are_still_to_come(setup_page, studio):
    page = setup_page
    _import_by_hand(page, studio, {"Profile.csv": PROFILE, "Connections.csv": CONNECTIONS},
                    name="Basic_LinkedInDataExport_10-19-2026.zip")
    expect(page.get_by_text("That was LinkedIn's first part, which has no posts.", exact=False)).to_be_visible()
    expect(page.get_by_text("without your posts", exact=False)).to_be_visible()
    page.get_by_role("button", name="My account has no posts").click()
    expect(page.get_by_text("That was LinkedIn's first part", exact=False)).to_have_count(0)
    expect(page.get_by_text("For a newer copy, ask LinkedIn again", exact=False)).to_be_visible()


def test_a_download_still_arriving_is_shown_as_one(setup_page, studio):
    page = setup_page
    downloads = studio["tmp"] / "user" / "Downloads"
    (downloads / "Complete_LinkedInDataExport_10-19-2026.zip.crdownload").write_bytes(b"PK\x03\x04partial")
    page.get_by_role("button", name="I have asked for it").click()
    # The step says which folder it is looking in (SETUP-20).
    expect(page.get_by_text(f"IN YOUR DOWNLOADS FOLDER ({downloads})", exact=False)).to_be_visible()
    item = page.get_by_role("listitem").filter(has_text="Complete_LinkedInDataExport_10-19-2026.zip").last
    expect(item).to_contain_text("STILL DOWNLOADING")
    expect(item.get_by_role("button", name="See what is in it")).to_be_disabled()


def test_a_folder_safari_unpacked_can_be_chosen_and_imported(setup_page, studio):
    page = setup_page
    folder = studio["tmp"] / "Complete_LinkedInDataExport_10-19-2026"
    (folder / "Jobs").mkdir(parents=True)
    (folder / "Profile.csv").write_text(PROFILE, encoding="utf-8")
    (folder / "Shares.csv").write_text(SHARES, encoding="utf-8")
    (folder / "Connections.csv").write_text(CONNECTIONS, encoding="utf-8")
    (folder / "Jobs" / "Job Applications.csv").write_text("Application Date,Company Name\n", encoding="utf-8")
    (folder / "Notes.txt").write_text("not read", encoding="utf-8")
    page.set_input_files('input[aria-label="Choose the folder your LinkedIn data archive was unpacked into"]',
                         str(folder))
    expect(page.get_by_text("This archive belongs to Sample Alice.")).to_be_visible()
    expect(page.get_by_text("Complete_LinkedInDataExport_10-19-2026", exact=True)).to_be_visible()
    page.get_by_label("This is my archive: import Sample Alice's archive as my own record").check()
    page.get_by_role("button", name="Import what is ticked").click()
    expect(page.get_by_text("Imported from Complete_LinkedInDataExport_10-19-2026")).to_be_visible()
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM connections").fetchone()[0] == 1


def test_the_result_is_in_words_not_column_names(setup_page, studio):
    page = setup_page
    _choose(page, studio, {"Profile.csv": PROFILE, "Shares.csv": SHARES, "Connections.csv": CONNECTIONS})
    page.get_by_label("This is my archive: import Sample Alice's archive as my own record").check()
    page.get_by_role("button", name="Import what is ticked").click()
    panel = page.get_by_role("status").filter(has_text="Imported from")
    expect(panel).to_contain_text("filled your name, headline, about and location")
    expect(panel).to_contain_text("1 added, 1 skipped: no public profile address")
    text = panel.inner_text()
    assert not re.search(r"[a-z]+_[a-z]+", text), f"an identifier reached the screen: {text}"
