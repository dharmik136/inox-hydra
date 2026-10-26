"""
The show path in a real browser: one stream per window, and screens that move with it.
======================================================================================

Cycle 4, track 2. The studio's windows learn that something changed from
GET /api/v1/events instead of each screen polling on its own timer
(studio/ui/src/lib/refresh.ts, App.tsx). These drive the built interface in
headless Chromium against a studio served in this process, so the server's
own count of listening windows can be read beside what the page does.

Service workers are blocked, as in every browser test here. Nothing clicks a
control that opens a browser, and nothing leaves loopback.
"""

import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

from qc2_r5_live import ME, confirm_identity, open_section, seed_creator, server, studio, urn_days_ago  # noqa: F401,E402

EVENTS = "/api/v1/events"

# Lets a test say the window is hidden. Headless Chromium always reports
# "visible", and the stream and the screens decide from this.
VISIBILITY = """
Object.defineProperty(Document.prototype, "visibilityState", {
  configurable: true,
  get() { return window.__visibility || "visible"; },
});
"""


def _wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _listening():
    import changes

    return changes.subscriber_count()


def _set_visibility(page, state):
    page.evaluate(
        "(state) => { window.__visibility = state; document.dispatchEvent(new Event('visibilitychange')); }", state)


def _streams_opened(page):
    opened = []
    page.on("request", lambda request: EVENTS in request.url and opened.append(request.url))
    return opened


def test_one_stream_for_the_window_whichever_screen_is_open(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    opened = _streams_opened(page)
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    for section in ("setup", "activity", "queue", "posts", "today"):
        page.evaluate("(section) => { location.hash = '#/' + section; }", section)
        page.wait_for_timeout(300)
    assert len(opened) == 1, f"the window opened {len(opened)} streams: {opened}"
    assert _wait_until(lambda: _listening() == 1), f"the studio counts {_listening()} listening windows"


def test_a_hidden_window_closes_its_stream_and_reopens_it_on_return(studio):
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    opened = _streams_opened(page)
    open_section(studio, "setup")
    assert _wait_until(lambda: _listening() == 1)

    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0), "a hidden window kept its stream open"

    _set_visibility(page, "visible")
    assert _wait_until(lambda: _listening() == 1), "the window did not open its stream again on return"
    assert len(opened) == 2, opened
    assert "since=" not in opened[0] and "since=" in opened[1], \
        f"the window did not name what it last heard when it came back: {opened}"


def test_the_header_mark_follows_a_heartbeat_on_a_screen_that_does_not_report_it(studio):
    """The Queue reads nothing about the bridge; the mark beside Activity still moves within seconds."""
    confirm_identity(studio["client"])
    import database

    conn = database.get_db()
    try:
        with conn:
            conn.execute("UPDATE bridge_heartbeats SET seen_at = '2000-01-01T00:00:00+00:00'")
    finally:
        conn.close()
    page = studio["page"]
    open_section(studio, "queue")
    page.wait_for_selector("h1:has-text('Queue')")

    def mark():
        return page.locator("header button", has_text="Activity").first.text_content() or ""

    assert _wait_until(lambda: ", bridge not connected" in mark()), mark()
    assert _wait_until(lambda: _listening() == 1)
    beat = studio["client"].post("/api/v1/bridge/heartbeat", json={"extension_version": "2.7.0", "page_kind": "feed"})
    assert beat.status_code == 200, beat.text
    # The header's own read is once a minute; the stream makes it seconds.
    assert _wait_until(lambda: ", bridge connected" in mark(), timeout=5.0), mark()


# ---------------------------------------------------------------------------
# What the creator sees: a capture within about a second, nothing for nothing
# ---------------------------------------------------------------------------

def _capture(client):
    captured = client.post("/api/v1/bridge/capture",
                           json={"extractor": "engagers", "page_kind": "post", "items_seen": 3, "items_kept": 2})
    assert captured.status_code == 200, captured.text


def _reads_of(page, path):
    reads = []
    page.on("request", lambda request: path in request.url and reads.append(request.url))
    return reads


def test_a_capture_reaches_setup_within_about_a_second(studio):
    """Setup reads every 30 seconds now; a capture shows long before that."""
    confirm_identity(studio["client"])
    page = studio["page"]
    open_section(studio, "setup")
    page.wait_for_selector("text=CAPTURE HEALTH")
    assert page.locator("text=WORKING, LAST READ").count() == 0
    assert _wait_until(lambda: _listening() == 1)
    started = time.monotonic()
    _capture(studio["client"])
    page.wait_for_selector("text=WORKING, LAST READ", timeout=5000)
    took = time.monotonic() - started
    assert took < 2.0, f"Setup showed the capture {took:.2f} s after it was saved"


def test_a_post_reaches_activity_within_about_a_second(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    assert _wait_until(lambda: _listening() == 1)
    text = "Captured while you watched, a post for the stream."
    started = time.monotonic()
    ingested = studio["client"].post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn_days_ago(0, 99), "actor": ME, "text": text, "reactions": 1, "comments": 0}]})
    assert ingested.status_code == 200, ingested.text
    page.wait_for_selector(f"text={text}", timeout=5000)
    took = time.monotonic() - started
    assert took < 2.0, f"Activity showed the post {took:.2f} s after it was saved"


def test_today_says_how_many_captures_wait_as_the_extension_reports_it(studio):
    """The waiting count was read once per visit to Today, so it could be stale all session."""
    import ingest_contract

    ingest_contract.forget()
    seed_creator(studio["client"])
    page = studio["page"]
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert "WAITING FOR THE STUDIO" not in page.inner_text("main")
    assert _wait_until(lambda: _listening() == 1)
    beat = studio["client"].post("/api/v1/bridge/heartbeat", json={
        "extension_version": "2.7.0", "page_kind": "service_worker", "contract_version": 1,
        "waiting_captures": 7, "oldest_waiting_at": "2026-10-26T09:00:00+00:00"})
    assert beat.status_code == 200, beat.text
    try:
        page.wait_for_selector("text=7 CAPTURES WAITING FOR THE STUDIO", timeout=5000)
    finally:
        ingest_contract.forget()


def test_a_capture_while_the_window_was_hidden_is_read_on_return(studio):
    """Back within 15 seconds no read is due by age; the stream says what changed."""
    confirm_identity(studio["client"])
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    open_section(studio, "setup")
    page.wait_for_selector("text=CAPTURE HEALTH")
    assert _wait_until(lambda: _listening() == 1)
    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0)
    _capture(studio["client"])
    page.wait_for_timeout(500)
    _set_visibility(page, "visible")
    page.wait_for_selector("text=WORKING, LAST READ", timeout=5000)


def test_a_window_back_with_nothing_changed_reads_nothing(studio):
    """A tab switch costs the studio a reconnect, not a read of every screen."""
    confirm_identity(studio["client"])
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector("text=CAPTURE HEALTH")
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1500)
    before = len(reads)
    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0)
    _set_visibility(page, "visible")
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1500)
    assert len(reads) == before, f"coming back with nothing changed read Setup {len(reads) - before} times"


def test_an_idle_setup_reads_twice_a_minute(studio):
    """It read every 3 seconds: twenty times a minute to learn nothing had changed."""
    confirm_identity(studio["client"])
    page = studio["page"]
    page.clock.install()
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector("text=CAPTURE HEALTH")
    start = len(reads)
    page.clock.run_for("01:00")
    page.wait_for_timeout(300)
    idle = len(reads) - start
    assert 1 <= idle <= 3, f"an idle Setup read {idle} times in a minute"


def test_a_window_back_after_a_while_reads_once_not_twice(studio):
    """
    Away fifteen seconds or more, the screen reads on coming back by age, and
    the stream's hello says the same news a moment later; one read covers it.
    """
    confirm_identity(studio["client"])
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    page.clock.install()
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector("text=CAPTURE HEALTH")
    assert _wait_until(lambda: _listening() == 1)
    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0)
    _capture(studio["client"])
    page.clock.fast_forward("00:20")
    before = len(reads)
    _set_visibility(page, "visible")
    page.wait_for_selector("text=WORKING, LAST READ", timeout=5000)
    page.wait_for_timeout(2500)
    assert len(reads) - before == 1, f"coming back read Setup {len(reads) - before} times"
