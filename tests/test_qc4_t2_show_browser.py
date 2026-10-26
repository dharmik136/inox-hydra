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


def _page_wait_until(page, condition, timeout=5.0):
    """
    _wait_until for a condition on what the page did. Playwright hands its
    events to Python only while Python is inside a Playwright call, so a plain
    sleep would never see a request the page made meanwhile.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        page.wait_for_timeout(50)
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
    assert _page_wait_until(page, lambda: len(opened) == 2), opened
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


# Setup's own heading. The tests waited for its CAPTURE HEALTH block, which
# moved to Health in the 2.9.0 merge (track 4), with the reader lines a
# capture used to change on Setup.
SETUP_READY = "text=Teach the studio who you are"


def _reads_of(page, path):
    reads = []
    page.on("request", lambda request: path in request.url and reads.append(request.url))
    return reads


def test_a_capture_reaches_setup_within_about_a_second(studio):
    """Setup reads every 30 seconds now; a capture is read long before that."""
    confirm_identity(studio["client"])
    page = studio["page"]
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector(SETUP_READY)
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1200)
    before = len(reads)
    _capture(studio["client"])
    saved = time.monotonic()
    assert _page_wait_until(page, lambda: len(reads) > before), "Setup did not read again after a capture"
    took = time.monotonic() - saved
    assert took < 2.0, f"Setup read the capture {took:.2f} s after it was saved"


def test_a_capture_reaches_health_within_about_a_second(studio):
    """
    The reader lines a capture changes live on Health since the 2.9.0 merge.
    Health holds a burst to one read per fifteen seconds, so the run comes
    after a quiet spell, which is read at once.
    """
    confirm_identity(studio["client"])
    page = studio["page"]
    page.clock.install()
    open_section(studio, "health")
    page.wait_for_selector("text=Is the bridge reading?")
    assert page.locator('text="WORKING"').count() == 0
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    _capture(studio["client"])
    saved = time.monotonic()
    page.wait_for_selector('text="WORKING"', timeout=5000)
    took = time.monotonic() - saved
    assert took < 2.0, f"Health showed the capture {took:.2f} s after it was saved"


def test_a_post_reaches_activity_within_about_a_second(studio):
    seed_creator(studio["client"])
    page = studio["page"]
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    assert _wait_until(lambda: _listening() == 1)
    text = "Captured while you watched, a post for the stream."
    ingested = studio["client"].post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn_days_ago(0, 99), "actor": ME, "text": text, "reactions": 1, "comments": 0}]})
    assert ingested.status_code == 200, ingested.text
    saved = time.monotonic()
    page.wait_for_selector(f"text={text}", timeout=5000)
    took = time.monotonic() - saved
    assert took < 2.0, f"Activity showed the post {took:.2f} s after it was saved"


def test_today_says_how_many_captures_wait_as_the_extension_reports_it(studio):
    """The waiting count was read once per visit to Today, so it could be stale all session."""
    import ingest_contract

    ingest_contract.forget()
    seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert "WAITING FOR THE STUDIO" not in page.inner_text("main")
    assert _wait_until(lambda: _listening() == 1)
    # Past Today's window since its first read, so the count is read at once.
    page.clock.fast_forward("00:20")
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
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector(SETUP_READY)
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1200)
    before = len(reads)
    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0)
    _capture(studio["client"])
    page.wait_for_timeout(500)
    _set_visibility(page, "visible")
    assert _page_wait_until(page, lambda: len(reads) > before), "the capture made while hidden was not read on return"


def test_a_window_back_with_nothing_changed_reads_nothing(studio):
    """A tab switch costs the studio a reconnect, not a read of every screen."""
    confirm_identity(studio["client"])
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector(SETUP_READY)
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
    page.wait_for_selector(SETUP_READY)
    start = len(reads)
    page.clock.run_for("01:00")
    page.wait_for_timeout(300)
    idle = len(reads) - start
    assert 1 <= idle <= 3, f"an idle Setup read {idle} times in a minute"


def test_a_window_back_after_a_while_reads_once_not_twice(studio):
    """
    Away fifteen seconds or more, a panel reads on coming back by age, and the
    stream's hello says the same news a moment later; one read covers it. The
    waiting count is the panel watched because nothing else reads it: it has
    no timer that could fire inside the count on a slow machine.
    """
    import ingest_contract

    ingest_contract.forget()
    seed_creator(studio["client"])
    page = studio["page"]
    page.add_init_script(VISIBILITY)
    page.clock.install()
    reads = _reads_of(page, "/api/v1/extension/captures/waiting")
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert _wait_until(lambda: _listening() == 1)
    _set_visibility(page, "hidden")
    assert _wait_until(lambda: _listening() == 0)
    beat = studio["client"].post("/api/v1/bridge/heartbeat", json={
        "extension_version": "2.7.0", "page_kind": "service_worker", "contract_version": 1, "waiting_captures": 5})
    assert beat.status_code == 200, beat.text
    page.clock.fast_forward("00:20")
    before = len(reads)
    try:
        _set_visibility(page, "visible")
        page.wait_for_selector("text=5 CAPTURES WAITING FOR THE STUDIO", timeout=5000)
        page.wait_for_timeout(2500)
        assert len(reads) - before == 1, f"coming back read the waiting count {len(reads) - before} times"
    finally:
        ingest_contract.forget()


# ---------------------------------------------------------------------------
# A write nothing announced: every screen reads it as "anything may have changed"
# ---------------------------------------------------------------------------

def _write_from_another_process(sql, params=()):
    """What the command line or a second studio does: a plain sqlite3 connection in a child process."""
    import json as _json
    import subprocess

    import paths

    writer = (
        "import json, sqlite3, sys\n"
        "conn = sqlite3.connect(sys.argv[1], timeout=10)\n"
        "conn.execute(sys.argv[2], json.loads(sys.argv[3]))\n"
        "conn.commit()\n"
        "conn.close()\n"
    )
    done = subprocess.run([sys.executable, "-c", writer, paths.get_db_path(), sql, _json.dumps(list(params))],
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr


def test_todays_panels_read_again_after_a_write_nothing_announced(studio):
    """The thirty day totals listened for one kind; a write the studio could not name reached no panel."""
    seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    totals = _reads_of(page, "/api/analytics/kpis")
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert _wait_until(lambda: _listening() == 1)
    # Long enough that no panel's last read is recent.
    page.clock.fast_forward("00:20")
    before = len(totals)
    _write_from_another_process(
        "INSERT INTO analytics_daily (date, impressions, period_label, source) VALUES (?, ?, '1d', 'observed') "
        "ON CONFLICT(date) DO UPDATE SET impressions = excluded.impressions",
        ("2026-10-25", 777))
    assert _page_wait_until(page, lambda: len(totals) > before, timeout=6.0), "the totals were not read again"


def test_the_header_reads_the_bridge_after_a_write_nothing_announced(studio):
    """A heartbeat a second studio recorded: the header learns of it from the backstop."""
    from datetime import datetime, timezone

    confirm_identity(studio["client"])
    import database

    conn = database.get_db()
    try:
        with conn:
            conn.execute("UPDATE bridge_heartbeats SET seen_at = '2000-01-01T00:00:00+00:00'")
    finally:
        conn.close()
    page = studio["page"]
    page.clock.install()
    open_section(studio, "queue")
    page.wait_for_selector("h1:has-text('Queue')")

    def mark():
        return page.locator("header button", has_text="Activity").first.text_content() or ""

    assert _wait_until(lambda: ", bridge not connected" in mark()), mark()
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    _write_from_another_process(
        "INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) VALUES (?, '2.7.0', 'feed')",
        (datetime.now(timezone.utc).isoformat(),))
    assert _wait_until(lambda: ", bridge connected" in mark(), timeout=8.0), mark()


def test_todays_totals_read_again_when_the_analytics_page_is_read(studio):
    """The creator analytics page writes the daily totals and now says so, as "account"."""
    from datetime import datetime

    seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    totals = _reads_of(page, "/api/analytics/kpis")
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    before = len(totals)
    read = studio["client"].post("/api/analytics/ingest", json={
        "author": ME, "period_label": "1d",
        "series": [{"date": datetime.now().strftime("%Y-%m-%d"), "impressions": 900, "reactions": 9, "followers": 400}]})
    assert read.status_code == 200, read.text
    assert _page_wait_until(page, lambda: len(totals) > before, timeout=6.0), "the totals were not read again"



# ---------------------------------------------------------------------------
# Review finding S1: a screen reads only for a change that can alter it, and
# Today and the header at most once per fifteen seconds
# ---------------------------------------------------------------------------

def _beat(client, **extra):
    beat = client.post("/api/v1/bridge/heartbeat", json={"extension_version": "2.7.0", "page_kind": "feed", **extra})
    assert beat.status_code == 200, beat.text


def test_today_reads_nothing_for_heartbeats_while_it_shows_the_bridge_connected(studio):
    """Ten LinkedIn tabs beat once a minute each; BRIDGE CONNECTED reads the same after every one."""
    seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    briefs = _reads_of(page, "/api/v1/today")
    waiting = _reads_of(page, "/api/v1/extension/captures/waiting")
    open_section(studio, "today")
    page.wait_for_selector("text=BRIDGE CONNECTED")
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    before, waited = len(briefs), len(waiting)
    for _ in range(5):
        _beat(studio["client"])
        page.wait_for_timeout(300)
    page.wait_for_timeout(1500)
    assert len(briefs) == before, f"Today read its brief {len(briefs) - before} times for heartbeats"
    assert len(waiting) == waited, "the waiting count was read for heartbeats that carried none"


def test_today_reads_its_brief_at_most_once_a_window_while_comments_come(studio):
    """Six new commenters in a few seconds: one read now or at the window's end, not one a second."""
    urns = seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    briefs = _reads_of(page, "/api/v1/today")
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert _wait_until(lambda: _listening() == 1)
    before = len(briefs)
    for index in range(6):
        engaged = studio["client"].post("/api/v1/crm/interactions/ingest", json={
            "full_name": f"Commenter {index}", "profile_url": f"https://www.linkedin.com/in/commenter-{index}-t2",
            "headline": "Engineer", "company": "Example", "interaction_type": "COMMENT",
            "comment_text": f"Comment number {index}.", "post_urn": urns[0], "post_author": ME})
        assert engaged.status_code == 200, engaged.text
        page.wait_for_timeout(400)
    page.clock.run_for(16_000)
    page.wait_for_timeout(500)
    reads = len(briefs) - before
    assert 1 <= reads <= 2, f"Today read its brief {reads} times for six comments inside one window"
    page.wait_for_selector("text=Comment number 5.", timeout=5000)


def test_the_header_reads_nothing_for_heartbeats(studio):
    """A heartbeat is the bridge heard from now: the mark turns connected from the news itself."""
    confirm_identity(studio["client"])
    import database

    conn = database.get_db()
    try:
        with conn:
            conn.execute("UPDATE bridge_heartbeats SET seen_at = '2000-01-01T00:00:00+00:00'")
    finally:
        conn.close()
    page = studio["page"]
    page.clock.install()
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "queue")
    page.wait_for_selector("h1:has-text('Queue')")

    def mark():
        return page.locator("header button", has_text="Activity").first.text_content() or ""

    assert _wait_until(lambda: ", bridge not connected" in mark()), mark()
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    before = len(reads)
    for _ in range(5):
        _beat(studio["client"])
        page.wait_for_timeout(300)
    assert _page_wait_until(page, lambda: ", bridge connected" in mark()), mark()
    page.clock.run_for(5_000)
    page.wait_for_timeout(500)
    assert len(reads) == before, f"the header read the bridge {len(reads) - before} times for heartbeats"


def test_setup_reads_once_for_a_reader_running_again_in_the_same_minute(studio):
    """
    WORKING, LAST READ is to the minute: twenty runs of one working reader
    change it once. The line is drawn on Health since the 2.9.0 merge; Setup
    keeps track 2's rule, and still reads the state that carries it.
    """
    confirm_identity(studio["client"])
    page = studio["page"]
    reads = _reads_of(page, "/api/v1/onboarding/state")
    open_section(studio, "setup")
    page.wait_for_selector(SETUP_READY)
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1200)
    before = len(reads)
    for _ in range(20):
        _capture(studio["client"])
        page.wait_for_timeout(200)
    page.wait_for_timeout(2000)
    assert 1 <= len(reads) - before <= 2, f"Setup read {len(reads) - before} times for one reader running twenty times"


def test_activity_reads_nothing_for_the_readers_run_log(studio):
    """The log shows what the bridge kept; a reader's run is in Setup's health, not here."""
    seed_creator(studio["client"])
    page = studio["page"]
    reads = _reads_of(page, "/api/v1/self/activity-stream")
    open_section(studio, "activity")
    page.wait_for_selector("text=What the bridge has read")
    assert _wait_until(lambda: _listening() == 1)
    page.wait_for_timeout(1200)
    before = len(reads)
    for _ in range(5):
        _capture(studio["client"])
        page.wait_for_timeout(300)
    page.wait_for_timeout(1500)
    assert len(reads) == before, f"Activity read {len(reads) - before} times for the readers' run log"



def test_todays_panels_and_the_header_read_nothing_for_reactions(studio):
    """
    A feed scroll: people react to a post of yours every few seconds. None of
    Today's side panels shows who reacted, and neither does the header; the
    evidence panel, which counts people per topic, reads once a window at most.
    """
    urns = seed_creator(studio["client"])
    page = studio["page"]
    page.clock.install()
    watched = {path: _reads_of(page, path) for path in (
        "/api/v1/onboarding/state", "/api/analytics/kpis", "/api/queue/smart-slots",
        "/api/v1/extension/captures/waiting", "/api/v1/storage/backups", "/api/v1/insights/cadence",
        "/api/v1/insights/evidence")}
    open_section(studio, "today")
    page.wait_for_selector("text=What to do in the next hour")
    assert _wait_until(lambda: _listening() == 1)
    page.clock.fast_forward("00:20")
    before = {path: len(reads) for path, reads in watched.items()}
    # Eight, a second and a bit apart: each post's summary is recomputed in a
    # write of its own a moment after the engagement, and that write has to be
    # announced for what it is, whenever the backstop happens to look.
    for index in range(8):
        engaged = studio["client"].post("/api/v1/crm/interactions/ingest", json={
            "full_name": f"Reactor {index}", "profile_url": f"https://www.linkedin.com/in/reactor-{index}-t2",
            "headline": "Engineer", "company": "Example", "interaction_type": "LIKE",
            "post_urn": urns[0], "post_author": ME})
        assert engaged.status_code == 200, engaged.text
        page.wait_for_timeout(1200)
    page.wait_for_timeout(2000)
    grew = {path: len(reads) - before[path] for path, reads in watched.items()}
    evidence = grew.pop("/api/v1/insights/evidence")
    assert all(count == 0 for count in grew.values()), f"reactions made Today read: {grew}"
    assert evidence <= 1, f"the evidence panel read {evidence} times inside one window"
