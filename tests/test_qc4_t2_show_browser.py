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

from qc2_r5_live import confirm_identity, open_section, seed_creator, server, studio  # noqa: F401,E402

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
