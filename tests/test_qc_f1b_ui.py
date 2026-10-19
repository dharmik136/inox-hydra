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


# ---------------------------------------------------------------------------
# WRITE-03 / UX-17: Publish acts on what is on screen
# ---------------------------------------------------------------------------

def _composer(context, studio_url):
    page = _open(context, studio_url, "Composer")
    editor = page.get_by_label("Post body")
    editor.fill("")
    return page, editor


def _publish_dialog(page):
    return page.get_by_role("dialog", name="Publish")


def test_publish_queues_the_text_on_screen_not_the_last_saved_one(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill("QC F1B version one of the post, saved.")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_text("SAVED", exact=False).first.wait_for()
    editor.fill("QC F1B version two, the one on screen, with the typo fixed. Not saved.")
    page.get_by_text("UNSAVED").wait_for()

    page.get_by_role("button", name="Publish", exact=True).click()
    dialog = _publish_dialog(page)
    assert "version two" in dialog.inner_text(), "the dialog does not show the post it acts on"
    dialog.get_by_role("button", name="Queue it").click()
    dialog.wait_for(state="detached")

    queued = [r for r in _rows("scheduled") if (r["content"] or "").startswith("QC F1B")]
    assert [r["content"] for r in queued] == ["QC F1B version two, the one on screen, with the typo fixed. Not saved."]


def test_publish_with_nothing_written_explains_and_opens_no_dialog(context, studio_url):
    page, _ = _composer(context, studio_url)
    page.get_by_role("button", name="Publish", exact=True).click()
    page.get_by_text("SAVE FAILED").wait_for()
    assert page.get_by_title("There is nothing written to publish.").count() == 1
    assert _publish_dialog(page).count() == 0


def test_publish_after_a_refused_save_shows_the_reason_and_opens_no_dialog(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill("QC F1B " + "x" * 5100)
    page.get_by_role("button", name="Publish", exact=True).click()
    page.get_by_text("SAVE FAILED").wait_for()
    assert page.locator("[title*='5,000']").count() == 1
    assert _publish_dialog(page).count() == 0
    assert not [r for r in _rows() if (r["content"] or "").startswith("QC F1B")]


# ---------------------------------------------------------------------------
# WRITE-02 / UX-01: the next post does not overwrite the one just published
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("choice, status", [("Mark as published", "published"), ("Queue it", "scheduled")])
def test_the_next_post_is_a_new_post(context, studio_url, choice, status):
    page, editor = _composer(context, studio_url)
    first = f"QC F1B post A about hiring juniors ({status})."
    editor.fill(first)
    page.get_by_role("button", name="Publish", exact=True).click()
    dialog = _publish_dialog(page)
    dialog.get_by_role("button", name=choice).click()
    dialog.wait_for(state="detached")

    # The editor let go of the post and is ready for the next one.
    assert editor.input_value() == ""
    editor.fill("QC F1B post B, a completely different idea.")
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_text("SAVED", exact=False).first.wait_for()

    gone_out = [r for r in _rows(status) if (r["content"] or "").startswith("QC F1B post A")]
    assert [r["content"] for r in gone_out] == [first], "the published or queued post was overwritten"
    drafts = [r["content"] for r in _rows("draft") if (r["content"] or "").startswith("QC F1B post B")]
    assert drafts == ["QC F1B post B, a completely different idea."]


# ---------------------------------------------------------------------------
# UX-18 (the Publish dialog): it takes the keyboard and gives it back
# ---------------------------------------------------------------------------

def test_the_publish_dialog_holds_focus_and_returns_it(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill("QC F1B a post to check the dialog's focus with.")
    publish = page.get_by_role("button", name="Publish", exact=True)
    publish.click()
    dialog = _publish_dialog(page)
    dialog.get_by_role("button", name="Queue it").wait_for()
    page.wait_for_timeout(300)

    inside = "() => !!document.activeElement && !!document.activeElement.closest('[role=dialog]')"
    assert page.evaluate(inside), "focus stayed behind the dialog"
    for press in range(20):
        page.keyboard.press("Shift+Tab" if press % 7 == 6 else "Tab")
        assert page.evaluate(inside), f"Tab {press + 1} left the dialog"

    page.keyboard.press("Escape")
    dialog.wait_for(state="detached")
    assert page.evaluate("() => document.activeElement && document.activeElement.textContent.trim()") == "Publish"


# ---------------------------------------------------------------------------
# WRITE-22 / UX-05: the Queue shows local times
# ---------------------------------------------------------------------------

def test_the_queue_lists_a_post_at_its_local_time(browser, studio_url, api):
    from datetime import datetime, timedelta, timezone

    # 03:00 UTC on a day well ahead, which is 08:30 in India.
    day = (datetime.now(timezone.utc) + timedelta(days=20)).replace(hour=3, minute=0, second=0, microsecond=0)
    created = api.post("/api/posts", json={
        "content": "QC F1B timezone check post.", "status": "scheduled", "scheduled_for": day.isoformat(),
    })
    assert created.status_code == 200, created.text

    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block",
                              timezone_id="Asia/Kolkata", locale="en-GB")
    try:
        page = _open(ctx, studio_url, "Queue")
        row = page.locator("li", has_text="QC F1B timezone check post.")
        row.wait_for()
        text = row.inner_text()
        assert "08:30" in text, text
        assert "03:00" not in text
    finally:
        ctx.close()


# ---------------------------------------------------------------------------
# WRITE-15 / UX-04: the Queue names a due post, and says it posts nothing
# ---------------------------------------------------------------------------

def test_a_due_post_waits_on_the_queue_until_the_creator_posts_it(context, studio_url):
    from datetime import datetime, timedelta, timezone

    conn = get_db()
    try:
        conn.execute("DELETE FROM settings WHERE key = 'queue_status'")
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'scheduled', ?)",
            ("qcf1b-due", "QC F1B a queued post whose time has come.",
             (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    page = _open(context, studio_url, "Queue")
    page.get_by_text("does not post anything", exact=False).wait_for()
    body = page.inner_text("body")
    assert "Pause publishing" not in body and "WILL NOT GO OUT" not in body

    page.get_by_role("button", name="Check for due posts").click()
    row = page.locator("section[aria-labelledby=queue-due] li", has_text="QC F1B a queued post whose time has come.")
    row.wait_for()
    assert "DUE" in row.inner_text()
    assert [r["status"] for r in _rows() if r["id"] == "qcf1b-due"] == ["due"]

    row.get_by_role("button", name="I posted it").click()
    row.wait_for(state="detached")
    assert [r["status"] for r in _rows() if r["id"] == "qcf1b-due"] == ["published"]


def test_a_due_post_the_creator_will_not_post_can_leave_the_queue(context, studio_url):
    from datetime import datetime, timedelta, timezone

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'due', ?)",
            ("qcf1b-due-drop", "QC F1B a due post the creator changed their mind about.",
             (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    page = _open(context, studio_url, "Queue")
    row = page.locator("section[aria-labelledby=queue-due] li", has_text="changed their mind")
    row.wait_for()
    row.get_by_role("button", name="Back to drafts").click()
    row.wait_for(state="detached")
    assert [r["status"] for r in _rows() if r["id"] == "qcf1b-due-drop"] == ["draft"]


# ---------------------------------------------------------------------------
# WRITE-01: a window left on another profile cannot save into the new one
# ---------------------------------------------------------------------------

@pytest.fixture
def second_profile(api, monkeypatch):
    import base64

    import ed25519
    import licensing

    secret = bytes(range(32))
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(secret)).decode()])
    payload = {
        "v": 1, "id": "test", "email": "buyer@example.com", "name": "", "tier": "agency", "kind": "annual",
        "profiles": 5, "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01",
    }
    key = licensing.encode(payload, lambda message: ed25519.sign(secret, message))
    assert api.post("/api/v1/licence", json={"key": key}).status_code == 200
    assert api.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"}).status_code == 200
    yield "client-b"
    api.post("/api/v1/accounts/switch", json={"account_id": "default"})
    api.request("DELETE", "/api/v1/accounts/client-b", json={"confirm": "Client B"})
    api.delete("/api/v1/licence")


def test_a_window_left_on_the_old_profile_is_told_and_cannot_save(browser, studio_url, second_profile):
    import paths

    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    try:
        window_a = _open(ctx, studio_url, "Composer")
        window_a.get_by_label("Post body").fill("QC F1B Confidential: My studio's launch announcement")

        window_b = _open(ctx, studio_url)
        window_b.get_by_role("button", name="Current profile").first.click()
        window_b.get_by_role("button", name="Client B").first.click()
        window_b.wait_for_load_state("networkidle")

        banner = window_a.get_by_role("alert").filter(has_text="switched to Client B")
        banner.wait_for(timeout=5000)

        window_a.get_by_role("button", name="Save", exact=True).click()
        window_a.get_by_text("SAVE FAILED").wait_for(timeout=5000)
        with paths.using_profile("client-b"):
            leaked = [r for r in _rows() if "Confidential" in (r["content"] or "")]
        assert leaked == [], "the stale window's draft landed in the other profile"

        # Reload asks first while the Composer holds unsaved text, and staying
        # keeps the text on screen.
        asked = []

        def dismiss(dialog):
            asked.append(dialog.message)
            dialog.dismiss()

        window_a.on("dialog", dismiss)
        banner.get_by_role("button", name="Reload this window").click()
        window_a.wait_for_timeout(500)
        assert asked and "unsaved" in asked[0].lower()
        assert "Confidential" in window_a.get_by_label("Post body").input_value()
    finally:
        ctx.close()
