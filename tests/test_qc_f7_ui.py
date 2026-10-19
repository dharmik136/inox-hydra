"""
Quality cycle 2026-10, batch F7: the studio shell, the profile switcher and the
copy a creator reads, driven in a real browser.

Every test runs the built interface (studio/frontend_next) against the app in
this process, on its own sandbox home. Contexts block the studio's service
worker, because requests from a page it controls bypass page.route, and every
route that could start a browser or touch the clipboard is answered here
rather than by the server.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND_DIR = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

if not os.path.exists(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("the studio interface is not built in this checkout", allow_module_level=True)

import uvicorn  # noqa: E402

from app import app  # noqa: E402
from database import init_db  # noqa: E402

# Routes that start a process or a browser. A test that wants one answered
# says how; anything else gets a refusal and never reaches the server.
GUARDED = ("/api/v1/browser/launch", "/api/v1/browser/copy-path", "/api/v1/browser/create-shortcuts",
           "/api/v1/self/sync-all")


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture(scope="module")
def studio_url():
    home = tempfile.mkdtemp(prefix="inox_qc_f7_")
    old_home = os.environ.get("INOX_HYDRA_HOME")
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
    if old_home is not None:
        os.environ["INOX_HYDRA_HOME"] = old_home
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch(headless=True)
        yield chromium
        chromium.close()


class Studio:
    """One browser context on the studio, with the guarded routes answered here."""

    def __init__(self, browser, url, width, height, scheme):
        self.url = url
        self.answers = {}
        self.context = browser.new_context(
            viewport={"width": width, "height": height},
            color_scheme=scheme,
            reduced_motion="reduce",
            service_workers="block",
        )
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.route("**/*", self._route)

    def _route(self, route, request):
        path = request.url.split("?", 1)[0]
        for suffix, answer in self.answers.items():
            if path.endswith(suffix):
                status, body = answer
                return route.fulfill(status=status, content_type="application/json", body=json.dumps(body))
        if any(path.endswith(guarded) for guarded in GUARDED):
            return route.fulfill(status=503, content_type="application/json",
                                 body=json.dumps({"detail": "refused by the test"}))
        if not path.startswith(self.url):
            return route.abort()
        return route.continue_()

    def answer(self, suffix, status, body):
        self.answers[suffix] = (status, body)

    def open(self, section=None):
        self.page.goto(self.url + "/", wait_until="networkidle")
        if section:
            self.go(section)
        return self.page

    def go(self, section):
        self.page.locator(f"nav[aria-label='Studio sections'] button[aria-label='{section}']").first.click()
        self.page.wait_for_timeout(500)

    def close(self):
        self.context.close()


@pytest.fixture
def studio(browser, studio_url):
    opened = []

    def make(width=1280, height=800, scheme="dark"):
        session = Studio(browser, studio_url, width, height, scheme)
        opened.append(session)
        return session

    yield make
    for session in opened:
        session.close()


def _api(studio_url, method, path, body=None):
    """Calls the sandbox studio directly, with its token, as the extension would."""
    import urllib.request
    from security import TOKEN_HEADER, get_or_create_token

    request = urllib.request.Request(
        studio_url + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={TOKEN_HEADER: get_or_create_token(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or b"{}")


# ---------------------------------------------------------------------------
# UX-08: a copy that failed is not announced as one that worked
# ---------------------------------------------------------------------------

EMPTY_LEADS = {"status": "success", "leads": []}
ONE_BROWSER = {
    "status": "success",
    "browsers": {"brave": {"id": "brave", "name": "Brave", "path": "/usr/bin/brave",
                           "is_available": True, "carries_extension": True}},
    "extension_path": "/opt/inox/studio/extension",
}


def _leads_empty_state(studio):
    session = studio()
    session.answer("/api/leads", 200, EMPTY_LEADS)
    session.answer("/api/v1/browser/status", 200, ONE_BROWSER)
    return session


def test_copy_path_reports_the_servers_failure_not_a_copy(studio):
    session = _leads_empty_state(studio)
    session.answer("/api/v1/browser/copy-path", 200, {
        "status": "error",
        "extension_path": "/opt/inox/studio/extension",
        "message": "Clipboard utility not found. Copy the path shown above by hand.",
    })
    page = session.open("Leads")
    page.get_by_role("button", name="Copy the folder path").click()
    note = page.locator("main [role=status]")
    note.wait_for(state="visible")
    text = note.inner_text()
    assert "Copied" not in text, f"a failed copy was announced as done: {text!r}"
    assert "Clipboard utility not found" in text, f"the server's reason is not shown: {text!r}"
    # The path is selected, so Ctrl+C is all that is left to do.
    selected = page.evaluate("() => String(window.getSelection())")
    assert selected.strip() == "/opt/inox/studio/extension"


def test_copy_path_still_says_copied_when_it_was(studio):
    session = _leads_empty_state(studio)
    session.answer("/api/v1/browser/copy-path", 200, {
        "status": "success",
        "extension_path": "/opt/inox/studio/extension",
        "message": "Extension path copied to clipboard.",
    })
    page = session.open("Leads")
    page.get_by_role("button", name="Copy the folder path").click()
    note = page.locator("main [role=status]")
    note.wait_for(state="visible")
    assert note.inner_text() == "Copied to the clipboard: /opt/inox/studio/extension"


def _deny_clipboard(page):
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', {value: {writeText: () => Promise.reject("
        "new DOMException('denied', 'NotAllowedError'))}, configurable: true});"
    )


def test_activity_copy_urn_shows_a_tick_only_after_the_copy(studio, studio_url):
    _seed_own_posts(studio_url)
    session = studio()
    _deny_clipboard(session.page)
    page = session.open("Activity")
    page.get_by_role("button", name="Live updates on").click()
    page.get_by_role("button", name="Copy activity URN").first.click()
    page.wait_for_timeout(300)
    first = page.locator("article").get_by_role("button", name="Copy activity URN").first
    assert first.locator("svg.lucide-check").count() == 0, "a copy the browser refused shows a tick"
    assert "could not be copied" in page.locator("main").inner_text().lower()


def test_dossier_copy_says_copied_only_after_the_copy(studio):
    session = studio()
    _deny_clipboard(session.page)
    page = session.open("Leads")
    page.locator("main").get_by_role("button", name="Peer question").first.click()
    copy = page.locator("main").get_by_role("button", name="COPY", exact=True).first
    copy.wait_for(state="visible")
    copy.click()
    page.wait_for_timeout(300)
    assert page.locator("main").get_by_role("button", name="COPIED", exact=True).count() == 0, (
        "the dossier says COPIED for a copy the browser refused"
    )


_SEEDED = set()


def _seed_own_posts(studio_url):
    """A confirmed identity and a few of your own posts, as the extension would record them."""
    from datetime import datetime, timedelta, timezone

    if studio_url in _SEEDED:
        return
    _SEEDED.add(studio_url)
    me = "sample-creator"
    _api(studio_url, "POST", "/api/v1/identity/observe", {
        "vanity": me, "self_evidence": ["owner_edit_controls"],
        "display_name": "Sample Creator", "headline": "Sample headline"})
    _api(studio_url, "POST", "/api/v1/identity/confirm", {"vanity": me})

    def urn(days, salt):
        moment = datetime.now(timezone.utc) - timedelta(days=days)
        return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)

    posts = [{"activity_urn": urn(days, days), "actor": me, "text": f"Sample own post {days} days ago",
              "reactions": 10 + days, "comments": days} for days in (3, 9, 15)]
    _api(studio_url, "POST", "/api/v1/self/posts/ingest", {"author": me, "posts": posts})


# ---------------------------------------------------------------------------
# UX-14: opening a post in the bridge browser says what happened
# ---------------------------------------------------------------------------

NO_BROWSER = (500, {"detail": "No supported browser was found on this machine."})
LAUNCHED = (200, {"status": "success", "browser": "Brave", "carries_extension": True,
                  "message": "Launched Brave with the bridge loaded.", "extension_path": "/opt/inox"})


def _open_the_post(studio, studio_url, answer):
    _seed_own_posts(studio_url)
    session = studio()
    session.answer("/api/v1/browser/launch", *answer)
    page = session.open("Posts")
    page.locator("article ul li button[aria-expanded]").first.click()
    page.get_by_role("button", name="Open the post").click()
    return session, page


def test_open_the_post_shows_why_it_failed(studio, studio_url):
    session, page = _open_the_post(studio, studio_url, NO_BROWSER)
    note = page.locator("article ul li [role=status]")
    note.wait_for(state="visible", timeout=3000)
    assert "No supported browser was found" in note.inner_text()
    assert not session.errors, f"the failure escaped as an uncaught error: {session.errors}"


def test_open_the_post_says_which_browser_opened(studio, studio_url):
    _, page = _open_the_post(studio, studio_url, LAUNCHED)
    note = page.locator("article ul li [role=status]")
    note.wait_for(state="visible", timeout=3000)
    assert "Launched Brave" in note.inner_text()


def _open_in_bridge(studio, studio_url, answer):
    _seed_own_posts(studio_url)
    session = studio()
    session.answer("/api/v1/browser/launch", *answer)
    page = session.open("Activity")
    page.get_by_role("button", name="Live updates on").click()
    page.get_by_role("button", name="Open in Bridge Browser").first.click()
    return session, page


def test_open_in_bridge_browser_shows_why_it_failed(studio, studio_url):
    session, page = _open_in_bridge(studio, studio_url, NO_BROWSER)
    page.locator("article [role=status]").filter(has_text="No supported browser").wait_for(
        state="visible", timeout=3000)
    assert not session.errors


def test_open_in_bridge_browser_says_which_browser_opened(studio, studio_url):
    _, page = _open_in_bridge(studio, studio_url, LAUNCHED)
    page.locator("article [role=status]").filter(has_text="Launched Brave").wait_for(
        state="visible", timeout=3000)
