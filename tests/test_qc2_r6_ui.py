"""
Writing and publishing, driven in the built interface (cycle 2, batch R6).
=========================================================================

Headless Chromium against the real app on a loopback port, with its own
sandboxed home. Every context blocks service workers, because the studio's
worker would otherwise answer requests the tests route. Nothing here presses
Send to LinkedIn's final button, opens a browser or leaves the machine.
"""

import json
import os
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone

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

FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
PREFIX = "QC2 R6"


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
    home = tempfile.mkdtemp(prefix="inox_qc2_r6_ui_")
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
def context(browser, studio_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=studio_url)
    yield ctx
    ctx.close()


def _rows(status=None):
    conn = get_db()
    try:
        sql = "SELECT * FROM posts WHERE content LIKE ?" + (" AND status = ?" if status else "")
        args = (PREFIX + "%",) + ((status,) if status else ())
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean_posts(studio_url):
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE content LIKE ?", (PREFIX + "%",))
        conn.execute("DELETE FROM settings WHERE key LIKE 'missed_post:qc2r6%'")
        conn.commit()
    finally:
        conn.close()


def _open(context, studio_url, address):
    page = context.new_page()
    page.goto(f"{studio_url}/#/{address}", wait_until="networkidle")
    return page


# ---------------------------------------------------------------------------
# BE-02 / D-7: a missed post is shown on Today, with Post now and Move to next slot
# ---------------------------------------------------------------------------

def _missed(post_id, text, hours=5):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    conn = get_db()
    try:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'due', ?)", (post_id, text, when))
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("missed_post:" + post_id, json.dumps({"scheduled_for": when, "noticed_at": when, "late_minutes": hours * 60})),
        )
        conn.commit()
    finally:
        conn.close()


def test_today_names_a_missed_post_and_moves_it_only_when_asked(context, studio_url):
    _missed("qc2r6-missed-a", f"{PREFIX} the launch post missed at breakfast")
    page = _open(context, studio_url, "today")
    page.get_by_text("A POST WAS MISSED", exact=True).wait_for()
    row = page.locator("li", has_text="the launch post missed at breakfast")
    assert "MISSED, WAS DUE" in row.inner_text()
    assert [r["status"] for r in _rows()] == ["due"], "the post moved before the creator chose"

    row.get_by_role("button", name="Move to next slot").click()
    page.get_by_text("It is queued again.", exact=False).wait_for()
    assert [r["status"] for r in _rows()] == ["scheduled"]


def test_post_now_copies_the_text_and_records_it_as_posted(context, studio_url):
    text = f"{PREFIX} the exact words of the missed post"
    _missed("qc2r6-missed-b", text)
    page = _open(context, studio_url, "today")
    row = page.locator("li", has_text="the exact words of the missed post")
    row.get_by_role("button", name="Post now").click()
    page.get_by_text("Copied and recorded as posted by you", exact=False).wait_for()
    assert page.evaluate("() => navigator.clipboard.readText()") == text
    assert [r["status"] for r in _rows()] == ["published"]


# ---------------------------------------------------------------------------
# D-4: the weekly slots can be changed from the Queue, and start with neutral names
# ---------------------------------------------------------------------------

def _slot_rows():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM queue_slots ORDER BY day_of_week, time_slot")]
    finally:
        conn.close()


def test_the_week_can_be_changed_from_the_queue(context, studio_url):
    before = _slot_rows()
    try:
        page = _open(context, studio_url, "queue")
        week = page.locator("section[aria-labelledby=queue-week]")
        # The slots are named on the week at a glance, which the Queue opens
        # on since cycle 3; this section changes them. Neutral names either
        # way: the author's own themes were the defect here.
        screen = page.locator("main").inner_text()
        assert "Architecture" not in screen and "Monday morning" in screen

        week.get_by_role("button", name="Change slots").click()
        week.get_by_label("Day of the new slot").select_option("5")
        week.get_by_label("Time of the new slot").fill("07:45")
        week.get_by_label("Name of the new slot").fill("Weekend early")
        week.get_by_role("button", name="Add slot").click()
        week.get_by_text("Added Saturday 07:45.").wait_for()
        assert any(r["time_slot"] == "07:45" and r["label"] == "Weekend early" for r in _slot_rows())

        week.get_by_label("Name of the Monday 08:30 slot").fill("Before work")
        row = week.locator("li", has=page.get_by_label("Name of the Monday 08:30 slot"))
        row.get_by_role("button", name="Save").click()
        week.get_by_text("Saved the Monday slot.").wait_for()
        assert any(r["time_slot"] == "08:30" and r["label"] == "Before work" for r in _slot_rows())

        week.get_by_role("button", name="Remove the Saturday 07:45 slot").click()
        week.get_by_text("Removed the Saturday 07:45 slot.").wait_for()
        assert not any(r["time_slot"] == "07:45" for r in _slot_rows())
    finally:
        conn = get_db()
        conn.execute("DELETE FROM queue_slots")
        conn.executemany(
            "INSERT INTO queue_slots (id, day_of_week, time_slot, label, is_active) VALUES (?,?,?,?,?)",
            [(r["id"], r["day_of_week"], r["time_slot"], r["label"], r["is_active"]) for r in before],
        )
        conn.commit()
        conn.close()


# ---------------------------------------------------------------------------
# D-1: a drafts list, New post, delete with confirmation, and no silent overwrite
# ---------------------------------------------------------------------------

def _composer(context, studio_url):
    page = _open(context, studio_url, "composer")
    editor = page.get_by_label("Post body")
    editor.wait_for()
    page.wait_for_timeout(300)
    editor.fill("")
    return page, editor


def _save(page):
    page.get_by_role("button", name="Save", exact=True).click()
    page.get_by_role("status").filter(has_text=re.compile(r"SAVED \d")).first.wait_for()


def _drafts(page):
    page.get_by_role("button", name="Drafts", exact=True).click()
    panel = page.get_by_role("dialog", name="Drafts")
    panel.wait_for()
    return panel


def test_replacing_the_whole_text_and_saving_keeps_the_first_draft(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} DRAFT A about the hiring plan")
    _save(page)

    editor.click()
    # Select all, which is Command+A on macOS: Control+A there moves the
    # caret to the start of the line instead, so the typing below would be
    # inserted rather than replace the draft.
    page.keyboard.press("ControlOrMeta+A")
    page.keyboard.type(f"{PREFIX} DRAFT B, a different idea")
    page.get_by_text("is kept as it was saved, in Drafts", exact=False).wait_for()
    _save(page)

    drafts = sorted(r["content"] for r in _rows("draft"))
    assert drafts == [f"{PREFIX} DRAFT A about the hiring plan", f"{PREFIX} DRAFT B, a different idea"], drafts


def test_emptying_the_editor_and_writing_again_makes_a_new_draft(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} the first post, kept")
    _save(page)
    editor.fill("")
    editor.fill(f"{PREFIX} the second post")
    _save(page)
    assert len(_rows("draft")) == 2


def test_the_drafts_list_opens_finds_and_starts_posts(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} Monday: the onboarding checklist")
    _save(page)
    page.get_by_role("button", name="New post", exact=True).click()
    assert editor.input_value() == ""
    editor.fill(f"{PREFIX} Tuesday: what the outage taught us")
    _save(page)

    panel = _drafts(page)
    panel.get_by_text("Monday: the onboarding checklist", exact=False).wait_for()
    panel.get_by_text("Tuesday: what the outage taught us", exact=False).wait_for()
    panel.get_by_label("Find a draft").fill("outage")
    panel.get_by_text("Monday: the onboarding checklist", exact=False).wait_for(state="detached")
    panel.get_by_label("Find a draft").fill("")
    panel.get_by_text("Monday: the onboarding checklist", exact=False).click()
    panel.wait_for(state="detached")
    assert editor.input_value() == f"{PREFIX} Monday: the onboarding checklist"


def test_switching_drafts_over_unsaved_text_asks_first(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} the saved one")
    _save(page)
    page.get_by_role("button", name="New post", exact=True).click()
    editor.fill(f"{PREFIX} typed and not saved")

    asked = []
    page.once("dialog", lambda dialog: (asked.append(dialog.message), dialog.dismiss()))
    panel = _drafts(page)
    panel.get_by_text("the saved one", exact=False).click()
    page.wait_for_timeout(200)
    assert asked and "unsaved changes" in asked[0]
    page.keyboard.press("Escape")
    assert editor.input_value() == f"{PREFIX} typed and not saved", "unsaved text was discarded without asking"


def test_a_draft_is_deleted_only_after_confirming_and_can_be_brought_back(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} a draft to throw away")
    _save(page)
    panel = _drafts(page)
    delete = panel.get_by_role("button", name=f"Delete draft: {PREFIX} a draft to throw away")

    page.once("dialog", lambda dialog: dialog.dismiss())
    delete.click()
    page.wait_for_timeout(200)
    assert len(_rows("draft")) == 1, "the draft was deleted without the author agreeing"

    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.accept()))
    delete.click()
    panel.get_by_text("Deleted", exact=False).wait_for()
    assert "a draft to throw away" in messages[0]
    assert _rows("draft") == []
    assert editor.input_value() == "", "the Composer still holds a deleted draft"

    panel.get_by_role("button", name="Undo").click()
    panel.get_by_text("is back in your drafts", exact=False).wait_for()
    assert [r["content"] for r in _rows("draft")] == [f"{PREFIX} a draft to throw away"]


# ---------------------------------------------------------------------------
# D-2: Publish's main action copies the exact text and records it as posted
# ---------------------------------------------------------------------------

def _publish(page):
    page.get_by_role("button", name="Publish", exact=True).click()
    dialog = page.get_by_role("dialog", name="Publish")
    dialog.get_by_role("button", name="Queue it").wait_for()
    return dialog


def test_copy_and_mark_posted_copies_the_exact_text_then_records_it(context, studio_url):
    page, editor = _composer(context, studio_url)
    text = f"{PREFIX} The exact words.\n\nWith \U0001d5ef\U0001d5fc\U0001d5f9\U0001d5f1 and a second paragraph."
    editor.fill(text)
    dialog = _publish(page)

    primary = dialog.get_by_role("button", name="Copy and mark posted")
    assert "bg-signal-orange" in (primary.get_attribute("class") or ""), "Copy and mark posted is not the main action"
    assert "bg-signal-orange" not in (dialog.get_by_role("button", name="Queue it").get_attribute("class") or "")

    primary.click()
    dialog.wait_for(state="detached")
    assert page.evaluate("() => navigator.clipboard.readText()").replace("\r\n", "\n") == text
    assert [r["status"] for r in _rows()] == ["published"]
    page.get_by_text("COPIED AND MARKED AS POSTED").wait_for()
    assert editor.input_value() == ""


def test_the_dialog_says_exactly_what_each_action_does(context, studio_url):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} a post to read the dialog with")
    dialog = _publish(page)
    text = " ".join(dialog.inner_text().split())
    assert "Copies this post's exact text to your clipboard, then records it in the studio as posted by you, now." in text
    assert "the studio does not post it" in text
    assert "Puts it in the studio's queue for the next slot below." in text
    assert "NEITHER OF THOSE TWO SENDS ANYTHING" in text
    dialog.get_by_role("button", name="Queue it").click()
    dialog.wait_for(state="detached")
    assert [r["status"] for r in _rows()] == ["scheduled"]


def test_a_refused_copy_records_nothing(browser, studio_url):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, service_workers="block")
    ctx.add_init_script("navigator.clipboard.writeText = () => Promise.reject(new Error('denied'));")
    try:
        page, editor = _composer(ctx, studio_url)
        editor.fill(f"{PREFIX} the copy is refused")
        dialog = _publish(page)
        dialog.get_by_role("button", name="Copy and mark posted").click()
        dialog.get_by_text("nothing was recorded", exact=False).wait_for()
        assert [r["status"] for r in _rows()] == ["draft"]
        dialog.get_by_role("button", name="Mark posted without copying").click()
        dialog.wait_for(state="detached")
        assert [r["status"] for r in _rows()] == ["published"]
    finally:
        ctx.close()


def test_the_composer_copies_the_text_as_written(context, studio_url):
    page, editor = _composer(context, studio_url)
    text = f"{PREFIX} copy me\n\nexactly as I am"
    editor.fill(text)
    page.get_by_role("button", name="Copy", exact=True).click()
    page.get_by_role("button", name="Copied").wait_for()
    assert page.evaluate("() => navigator.clipboard.readText()").replace("\r\n", "\n") == text
    assert _rows() == [], "copying saved or recorded something"


# ---------------------------------------------------------------------------
# BE-09 / D-21: Send to LinkedIn names the account and the time, and says why not
# ---------------------------------------------------------------------------

def _served_client():
    """The LinkedIn client the served app uses. A test elsewhere reloads the
    module, so its own attribute can be a different instance."""
    import app as served

    return served.linkedin_client


@pytest.fixture
def no_session():
    _served_client().clear_tokens()
    yield


@pytest.fixture
def signed_in(monkeypatch):
    """A confirmed creator, a session the bridge synced with their URN, and a fake LinkedIn."""
    import socket

    from test_qc2_r6_linkedin_send import FakeLinkedIn

    sender = _served_client()
    fake = FakeLinkedIn()
    monkeypatch.setenv("INOX_ALLOW_LINKEDIN_EGRESS", "1")
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    monkeypatch.setattr(sender, "base_url", f"http://127.0.0.1:{fake.port}/voyager/api")
    sender.circuit_breaker.reset()
    real_getaddrinfo = socket.getaddrinfo

    def loopback_names_only(host, *args, **kwargs):
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a name lookup for {host} was attempted")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", loopback_names_only)
    conn = get_db()
    conn.execute("DELETE FROM creator_identity WHERE id = 1")
    conn.execute(
        "INSERT INTO creator_identity (id, vanity, display_name, confirmed_at) VALUES (1, 'r6-creator', 'Rae Six', ?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    # A studio that has never sent, so the cycle 3 one-time risk
    # acknowledgement is where each of these tests starts from.
    conn.execute("DELETE FROM settings WHERE key = 'linkedin_send_risk_ack'")
    conn.commit()
    conn.close()
    sender.save_tokens(
        "AQEDAR6liveshaped", '"ajax:6060606060"',
        account={"vanity": "r6-creator", "member_urn": "urn:li:fsd_profile:ACoAAR6CREATOR0001"},
    )
    yield fake
    fake.close()
    sender.clear_tokens()
    sender.circuit_breaker.reset()
    conn = get_db()
    conn.execute("DELETE FROM creator_identity WHERE id = 1")
    conn.execute(
        "DELETE FROM settings WHERE key LIKE 'linkedin_send_log:%' OR key LIKE 'linkedin_holds:%' "
        "OR key = 'linkedin_send_risk_ack'"
    )
    conn.commit()
    conn.close()


def test_send_to_linkedin_without_a_session_is_greyed_out_with_the_reason(context, studio_url, no_session):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} a post with no session to send it")
    dialog = _publish(page)
    send = dialog.get_by_role("button", name="Send to LinkedIn")
    dialog.get_by_text("no saved LinkedIn session", exact=False).wait_for()
    assert send.is_disabled()


def test_the_first_send_from_a_studio_asks_for_the_risk_to_be_acknowledged(context, studio_url, signed_in):
    """
    Cycle 3, T8: the one-time gate, in the real dialog.

    This studio has never sent, so the account risk is named in place of the
    Send to LinkedIn button, and there is no way past it but to answer it.
    """
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} the first post this studio would ever send")
    dialog = _publish(page)
    dialog.get_by_text("BEFORE THE FIRST SEND FROM THIS STUDIO, ONCE").wait_for()
    shown = " ".join(dialog.inner_text().split())

    assert "outside LinkedIn's published terms" in shown
    assert "account's standing" in shown
    assert dialog.get_by_role("button", name="Send to LinkedIn").count() == 0, (
        "the send button was offered before the risk was acknowledged"
    )
    assert signed_in.requests == []

    dialog.get_by_role("button", name="I understand, and accept this risk").click()
    dialog.get_by_role("button", name="Send to LinkedIn").wait_for()
    assert signed_in.requests == [], "acknowledging sent the post"


def test_the_confirmation_names_the_account_and_the_time_and_the_send_reaches_only_the_fake(
        context, studio_url, signed_in):
    page, editor = _composer(context, studio_url)
    editor.fill(f"{PREFIX} the post for LinkedIn to hold")
    dialog = _publish(page)
    # Since cycle 3 (T8) a studio's first send asks once for the account risk
    # to be acknowledged. This test is about the per-send confirmation that
    # follows it, so the one-time gate is answered first.
    acknowledge = dialog.get_by_role("button", name="I understand, and accept this risk")
    if acknowledge.count():
        acknowledge.click()
    dialog.get_by_text("Sends as Rae Six (linkedin.com/in/r6-creator).").wait_for()

    dialog.get_by_role("button", name="Send to LinkedIn").click()
    confirm = " ".join(dialog.inner_text().split())
    assert "Send as Rae Six (linkedin.com/in/r6-creator), for LinkedIn to publish at" in confirm
    assert "(this computer's time)" in confirm
    assert signed_in.requests == [], "the first press sent something"

    dialog.get_by_role("button", name="Yes, send as Rae Six").click()
    dialog.wait_for(state="detached")
    assert len(signed_in.requests) == 1
    assert signed_in.requests[0]["body"]["author"] == "urn:li:fsd_profile:ACoAAR6CREATOR0001"
    assert signed_in.requests[0]["body"]["commentary"]["text"] == f"{PREFIX} the post for LinkedIn to hold"
    page.get_by_text("LINKEDIN IS HOLDING THIS POST", exact=False).wait_for()
    assert [r["status"] for r in _rows()] == ["scheduled"]
