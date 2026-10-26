"""
The change stream: one connection per window, told when something changed.
==========================================================================

Cycle 4, track 2 (the show path). Every screen polled on its own timer and
re-ran the whole onboarding aggregate to learn, almost always, that nothing
had changed. GET /api/v1/events is a text/event-stream fed by the ingest
paths through studio/backend/changes.py, with PRAGMA data_version on one
long-lived connection as the backstop that also sees a write the bus was
never told about (the CLI, a second studio process, a path nobody hooked).

These tests speak HTTP to a real uvicorn server over a socket, because what
matters here cannot be seen through the test client: a cookie sent with no
header, a foreign origin, a client that goes away, a server asked to stop
while a stream is open.
"""

import http.client
import json
import math
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import changes  # noqa: E402
import database  # noqa: E402
import paths  # noqa: E402
import security  # noqa: E402

EVENTS = "/api/v1/events"


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(app):
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    return server, thread, port


@pytest.fixture(scope="module")
def studio():
    """A studio of its own, on a real port, for the whole module."""
    old_home = os.environ.get("INOX_HYDRA_HOME")
    home = tempfile.mkdtemp(prefix="inox_t2_stream_")
    os.environ["INOX_HYDRA_HOME"] = home
    database.init_db()
    import app as app_module

    server, thread, port = _serve(app_module.app)
    yield {"port": port, "app": app_module.app, "server": server}
    server.should_exit = True
    thread.join(timeout=5)
    assert not thread.is_alive(), "the server did not stop within five seconds of being asked"
    if old_home is None:
        os.environ.pop("INOX_HYDRA_HOME", None)
    else:
        os.environ["INOX_HYDRA_HOME"] = old_home
    shutil.rmtree(home, ignore_errors=True)


class Stream:
    """One EventSource-shaped request, read line by line with a deadline."""

    def __init__(self, port, cookie=True, origin=None, header_token=None, since=None, last_event_id=None):
        path = EVENTS if since is None else f"{EVENTS}?since={since}"
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        lines = [f"GET {path} HTTP/1.1", f"Host: 127.0.0.1:{port}", "Accept: text/event-stream",
                 "Cache-Control: no-cache"]
        if cookie:
            lines.append(f"Cookie: {security.TOKEN_COOKIE}={security.get_or_create_token()}")
        if origin is not None:
            lines.append(f"Origin: {origin}")
        if header_token is not None:
            lines.append(f"{security.TOKEN_HEADER}: {header_token}")
        if last_event_id is not None:
            lines.append(f"Last-Event-ID: {last_event_id}")
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        self.reader = self.sock.makefile("rb")
        status_line = self.reader.readline().decode()
        self.status = int(status_line.split()[1])
        self.headers = {}
        while True:
            line = self.reader.readline().decode().rstrip("\r\n")
            if not line:
                break
            name, _, value = line.partition(":")
            self.headers[name.strip().lower()] = value.strip()
        self.chunked = self.headers.get("transfer-encoding", "").lower() == "chunked"

    def _raw_line(self, deadline):
        self.sock.settimeout(max(0.05, deadline - time.monotonic()))
        line = self.reader.readline()
        if not line:
            raise EOFError("the stream ended")
        return line

    def line(self, deadline):
        """The next payload line, with chunk framing removed."""
        if not self.chunked:
            return self._raw_line(deadline).decode().rstrip("\r\n")
        while True:
            size = int(self._raw_line(deadline).strip() or "0", 16)
            if size == 0:
                raise EOFError("the stream ended")
            payload = b""
            while len(payload) < size:
                payload += self.reader.read(size - len(payload))
            self.reader.readline()  # the CRLF after the chunk
            # The blank line that ends an event is part of the payload; kept.
            return payload.decode()

    def event(self, timeout=5.0):
        """The next event as (name, id, data), skipping keep-alive comments."""
        deadline = time.monotonic() + timeout
        name, event_id, data = None, None, []
        while True:
            # A chunk may carry several lines; split them without losing any.
            for line in self.line(deadline).split("\n"):
                if line == "":
                    if name or data:
                        return name, event_id, "\n".join(data)
                    continue
                if line.startswith(":"):
                    continue
                field, _, value = line.partition(":")
                value = value[1:] if value.startswith(" ") else value
                if field == "event":
                    name = value
                elif field == "id":
                    event_id = value
                elif field == "data":
                    data.append(value)

    def change(self, timeout=5.0):
        """Waits for the next change event; returns its kinds and how long it took."""
        kinds, _notes, took = self.change_notes(timeout)
        return kinds, took

    def change_notes(self, timeout=5.0):
        """Waits for the next change event; returns its kinds, its changes and how long it took."""
        started = time.monotonic()
        while True:
            name, _id, data = self.event(timeout=max(0.1, timeout - (time.monotonic() - started)))
            if name == "change":
                body = json.loads(data)
                return body["kinds"], body.get("changes", []), time.monotonic() - started

    def close(self):
        # The file object holds the socket open until it is closed too, so
        # the server would not see this client go until the file was collected.
        for closing in (self.reader.close, self.sock.close):
            try:
                closing()
            except OSError:
                pass


def _post(port, path, body):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("POST", path, body=json.dumps(body),
                 headers={"Content-Type": "application/json", security.TOKEN_HEADER: security.get_or_create_token()})
    response = conn.getresponse()
    text = response.read().decode()
    conn.close()
    return response.status, text


def _wait_until(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


# ---------------------------------------------------------------------------
# The three checks, unchanged: Host, Origin, token. EventSource can send only
# the same-origin cookie, and that is enough; a foreign page is still refused.
# ---------------------------------------------------------------------------

def test_the_route_answers_behind_the_same_checks_as_every_other_route():
    assert not security.request_is_exempt(EVENTS)
    assert security.UNAUTHENTICATED_PREFIXES == ("/api/v1/health", "/api/health")


def test_the_cookie_alone_opens_the_stream_as_a_browser_would(studio):
    stream = Stream(studio["port"])
    try:
        assert stream.status == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        name, event_id, data = stream.event()
        assert name == "hello"
        hello = json.loads(data)
        assert hello["profile"] == paths.get_active_profile_id()
        assert event_id == hello["id"] == changes.current_id()
        assert event_id.startswith(changes.BOOT + "-")
    finally:
        stream.close()


def test_the_studio_own_origin_is_accepted(studio):
    stream = Stream(studio["port"], origin=f"http://127.0.0.1:{studio['port']}")
    try:
        assert stream.status == 200
    finally:
        stream.close()


@pytest.mark.parametrize("origin", ["https://evil.example", "https://www.linkedin.com", "null"])
def test_a_foreign_origin_is_refused_even_with_the_cookie(studio, origin):
    stream = Stream(studio["port"], origin=origin)
    try:
        assert stream.status == 403
    finally:
        stream.close()


def test_no_credential_is_refused(studio):
    stream = Stream(studio["port"], cookie=False)
    try:
        assert stream.status == 401
    finally:
        stream.close()


def test_a_wrong_header_token_is_refused(studio):
    stream = Stream(studio["port"], cookie=False, header_token="not-the-token")
    try:
        assert stream.status == 401
    finally:
        stream.close()


# ---------------------------------------------------------------------------
# What the stream says
# ---------------------------------------------------------------------------

def test_a_capture_reaches_an_open_stream_within_a_second(studio):
    stream = Stream(studio["port"])
    try:
        stream.event()
        status, text = _post(studio["port"], "/api/v1/bridge/capture",
                             {"extractor": "engagers", "page_kind": "post", "items_seen": 3, "items_kept": 2})
        assert status == 200, text
        kinds, took = stream.change(timeout=3.0)
        assert "capture" in kinds, kinds
        assert took < 1.0, f"the capture took {took:.2f} s to reach the stream"
    finally:
        stream.close()


def test_a_heartbeat_reaches_an_open_stream(studio):
    stream = Stream(studio["port"])
    try:
        stream.event()
        status, text = _post(studio["port"], "/api/v1/bridge/heartbeat", {"extension_version": "2.7.0", "page_kind": "feed"})
        assert status == 200, text
        kinds, took = stream.change(timeout=3.0)
        assert "heartbeat" in kinds, kinds
        assert took < 1.0
    finally:
        stream.close()


def test_a_burst_is_one_message_not_ten(studio):
    """
    Ten captures in a burst reach the window as one message per quarter second
    the burst lasted, never one each. The bound is taken from how long the
    burst really took: 2.9.0's macOS runner stretched ten 10 ms sleeps past one
    window and sent three messages, which a fixed "at most two" called a fault.
    """
    from routers import events as events_route

    stream = Stream(studio["port"])
    try:
        stream.event()
        started = time.monotonic()
        for _ in range(10):
            changes.publish("capture")
            time.sleep(0.01)
        lasted = time.monotonic() - started
        messages = [stream.change(timeout=3.0)[0]]
        try:
            while True:
                messages.append(stream.change(timeout=1.0)[0])
        except (EOFError, socket.timeout, TimeoutError, OSError):
            pass
        assert all(kinds == ["capture"] for kinds in messages), messages
        # Each message closes a window that opened at the first change after
        # the last one, so a burst lasting `lasted` spans at most this many.
        windows = math.ceil(lasted / events_route.COALESCE_S) + 1
        assert len(messages) <= windows, (
            f"a burst of ten over {lasted:.2f} s reached the window as {len(messages)} messages, "
            f"more than its {windows} coalescing windows")
        assert len(messages) < 10, "the burst was not coalesced at all"
    finally:
        stream.close()


def test_a_write_the_bus_was_not_told_about_is_still_noticed(studio):
    """The CLI, a second studio or an unhooked path: data_version sees it."""
    stream = Stream(studio["port"])
    try:
        stream.event()
        conn = database.get_db()
        try:
            with conn:
                conn.execute("INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) "
                             "VALUES ('2026-10-26T10:00:00+00:00', '2.7.0', 'cli')")
        finally:
            conn.close()
        kinds, took = stream.change(timeout=4.0)
        assert kinds == ["database"], kinds
        assert took < changes.WATCH_EVERY_S + 1.0, f"the backstop took {took:.2f} s"
    finally:
        stream.close()


def test_a_write_from_another_process_is_noticed(studio):
    """The command line or a second studio: a process the bus cannot hear at all."""
    import subprocess

    stream = Stream(studio["port"])
    try:
        stream.event()
        writer = (
            "import sqlite3, sys\n"
            "conn = sqlite3.connect(sys.argv[1], timeout=10)\n"
            "conn.execute(\"INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) "
            "VALUES ('2026-10-26T10:02:00+00:00', '2.7.0', 'other process')\")\n"
            "conn.commit()\n"
            "conn.close()\n"
        )
        done = subprocess.run([sys.executable, "-c", writer, paths.get_db_path()],
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        kinds, took = stream.change(timeout=4.0)
        assert kinds == ["database"], kinds
        assert took < changes.WATCH_EVERY_S + 1.0, f"the backstop took {took:.2f} s"
    finally:
        stream.close()


def test_an_announced_write_is_not_announced_twice(studio):
    """A hooked write changes data_version too; the backstop must not repeat it."""
    stream = Stream(studio["port"])
    try:
        stream.event()
        _post(studio["port"], "/api/v1/bridge/heartbeat", {"extension_version": "2.7.0", "page_kind": "feed"})
        kinds, _took = stream.change(timeout=3.0)
        assert "heartbeat" in kinds
        with pytest.raises((EOFError, socket.timeout, TimeoutError, OSError)):
            kinds, _took = stream.change(timeout=changes.WATCH_EVERY_S + 1.0)
            pytest.fail(f"the backstop repeated an announced write as {kinds}")
    finally:
        stream.close()


def test_a_reconnect_is_told_whether_anything_changed_while_it_was_away(studio):
    first = Stream(studio["port"])
    try:
        _name, event_id, _data = first.event()
    finally:
        first.close()
    quiet = Stream(studio["port"], since=event_id)
    try:
        assert json.loads(quiet.event()[2])["changed"] is False
    finally:
        quiet.close()
    changes.publish("posts")
    later = Stream(studio["port"], since=event_id)
    try:
        assert json.loads(later.event()[2])["changed"] is True
    finally:
        later.close()
    # A browser's own reconnect names the last id in a header instead.
    browser = Stream(studio["port"], last_event_id=event_id)
    try:
        assert json.loads(browser.event()[2])["changed"] is True
    finally:
        browser.close()
    # An id from a studio that has since restarted counts as changed, even
    # when its count happens to match this process's count.
    restarted = Stream(studio["port"], since="0badb007-" + changes.current_id().split("-", 1)[1])
    try:
        assert json.loads(restarted.event()[2])["changed"] is True
    finally:
        restarted.close()


def test_a_write_while_nobody_listened_is_reported_on_return(studio):
    """A hidden window closes its stream; the hello on return says what it missed."""
    first = Stream(studio["port"])
    try:
        _name, event_id, _data = first.event()
    finally:
        first.close()
    assert _wait_until(lambda: changes.subscriber_count() == 0, timeout=5.0)
    conn = database.get_db()
    try:
        with conn:
            conn.execute("INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) "
                         "VALUES ('2026-10-26T10:01:00+00:00', '2.7.0', 'cli')")
    finally:
        conn.close()
    back = Stream(studio["port"], since=event_id)
    try:
        assert json.loads(back.event()[2])["changed"] is True
    finally:
        back.close()


# ---------------------------------------------------------------------------
# Every ingest path names what it changed. Without its one line the backstop
# would still notice the write, as "database", so each test asserts the kind.
# ---------------------------------------------------------------------------

ME = "t2-show-creator"


def _urn(days_ago, salt=0):
    from datetime import datetime, timedelta, timezone

    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture(scope="module")
def creator(studio):
    """A confirmed creator with one post of theirs, as Setup leaves one."""
    port = studio["port"]
    for path, body in (
        ("/api/v1/bridge/heartbeat", {"extension_version": "2.7.0", "page_kind": "feed"}),
        ("/api/v1/identity/observe", {"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                      "display_name": "Test Creator", "headline": "Engineer"}),
        ("/api/v1/identity/confirm", {"vanity": ME}),
    ):
        status, text = _post(port, path, body)
        assert status == 200, (path, text)
    urn = _urn(3)
    status, text = _post(port, "/api/v1/self/posts/ingest", {"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": "A post of my own.", "reactions": 4, "comments": 1}]})
    assert status == 200, text
    return {"urn": urn}


def _published_by(port, path, body):
    stream = Stream(port)
    try:
        stream.event()
        status, text = _post(port, path, body)
        assert status == 200, text
        kinds, took = stream.change(timeout=3.0)
        assert took < 1.0, f"{path} took {took:.2f} s to reach the stream"
        return kinds
    finally:
        stream.close()


def test_the_creators_posts_say_posts(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/self/posts/ingest", {"author": ME, "posts": [
        {"activity_urn": _urn(2, 1), "actor": ME, "text": "Another post of mine.", "reactions": 2}]})
    assert "posts" in kinds, kinds


def test_a_posts_analytics_page_says_readings(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/self/posts/analytics", {
        "author": ME, "activity_urn": creator["urn"], "metrics": {"impressions": 120, "reactions": 5}})
    assert "readings" in kinds, kinds


def test_a_network_reading_says_readings(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/bridge/voyager-ingest", {
        "schema_name": "feed_updates", "data": [{"urn": creator["urn"], "likes": 6, "comments": 1}]})
    assert "readings" in kinds, kinds


def test_the_creators_outbound_activity_says_outbound(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/self/outbound/ingest", {"actor": ME, "items": [
        {"kind": "reaction", "target_activity_urn": _urn(1, 7), "target_author": "Someone Else",
         "reaction_kind": "LIKE"}]})
    assert "outbound" in kinds, kinds


def test_the_creators_analytics_page_says_account(studio, creator):
    """The daily totals' own writer. It said nothing, so the backstop called it "database"."""
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    kinds = _published_by(studio["port"], "/api/analytics/ingest", {
        "author": ME, "period_label": "1d", "series": [{"date": today, "impressions": 900, "reactions": 9,
                                                        "followers": 400}]})
    assert kinds == ["account"], kinds


def test_a_network_reading_of_the_account_says_account(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/bridge/voyager-ingest", {
        "schema_name": "creator_analytics", "vanity": ME, "data": [{"followers": 401}]})
    assert kinds == ["account"], kinds


def test_an_engagement_on_the_creators_post_says_people(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/crm/interactions/ingest", {
        "full_name": "Test Person", "profile_url": "https://www.linkedin.com/in/test-person-t2",
        "headline": "Engineer", "company": "Example", "interaction_type": "COMMENT",
        "comment_text": "A comment for the stream.", "post_urn": creator["urn"], "post_author": ME})
    assert kinds == ["people"], kinds


def test_the_creators_own_profile_page_says_identity(studio, creator):
    kinds = _published_by(studio["port"], "/api/v1/identity/observe", {
        "vanity": ME, "self_evidence": ["owner_edit_controls"], "display_name": "Test Creator",
        "headline": "Engineer, now at a new place"})
    assert kinds == ["identity"], kinds


def test_an_import_event_says_imports(studio, creator):
    status, text = _post(studio["port"], "/api/v1/self/imports", {"kind": "posts"})
    assert status == 200, text
    request_id = json.loads(text)["id"]
    kinds = _published_by(studio["port"], "/api/v1/self/imports/event", {"id": request_id, "event": "started"})
    assert kinds == ["imports"], kinds


def _notes_from(port, path, body):
    stream = Stream(port)
    try:
        stream.event()
        status, text = _post(port, path, body)
        assert status == 200, text
        _kinds, notes, _took = stream.change_notes(timeout=3.0)
        return notes
    finally:
        stream.close()


def test_a_capture_names_its_reader_and_whether_it_drifted(studio):
    notes = _notes_from(studio["port"], "/api/v1/bridge/capture", {
        "extractor": "engagers", "page_kind": "post", "items_seen": 3, "items_kept": 0, "drift": ["name"]})
    assert len(notes) == 1, notes
    minute = notes[0].pop("minute")
    assert notes == [{"kind": "capture", "extractor": "engagers", "drift": True}], notes
    assert len(minute) == 16 and minute[10] == "T", minute


def test_a_heartbeat_says_whether_it_carried_a_waiting_count(studio):
    beat = {"extension_version": "2.7.0", "page_kind": "feed"}
    assert _notes_from(studio["port"], "/api/v1/bridge/heartbeat", beat) == [{"kind": "heartbeat", "waiting": False}]
    assert _notes_from(studio["port"], "/api/v1/bridge/heartbeat", {**beat, "waiting_captures": 2}) == [
        {"kind": "heartbeat", "waiting": True}]


def test_a_posts_reading_names_the_post(studio, creator):
    notes = _notes_from(studio["port"], "/api/v1/self/posts/analytics", {
        "author": ME, "activity_urn": creator["urn"], "metrics": {"impressions": 130, "reactions": 6}})
    assert notes == [{"kind": "readings", "post": creator["urn"]}], notes


def test_an_engagement_says_how_on_which_post_and_who_by_id_only(studio, creator):
    notes = _notes_from(studio["port"], "/api/v1/crm/interactions/ingest", {
        "full_name": "Second Person", "profile_url": "https://www.linkedin.com/in/second-person-t2",
        "headline": "Designer", "company": "Example", "interaction_type": "LIKE", "post_urn": creator["urn"],
        "post_author": ME})
    assert len(notes) == 1, notes
    note = notes[0]
    assert note["kind"] == "people" and note["interaction"] == "reaction" and note["post"] == creator["urn"]
    assert note["lead"].startswith("lead-"), note
    assert "Second Person" not in json.dumps(notes) and "Designer" not in json.dumps(notes)


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request("GET", path, headers={security.TOKEN_HEADER: security.get_or_create_token()})
    response = conn.getresponse()
    response.read()
    conn.close()
    return response.status


def _changes_for(stream, seconds):
    notes = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            _kinds, more, _took = stream.change_notes(timeout=max(0.2, deadline - time.monotonic()))
        except (EOFError, socket.timeout, TimeoutError, OSError):
            break
        notes.extend(more)
    return notes


def _stale_scores():
    conn = database.get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM leads WHERE icp_stale != 0").fetchone()[0]
    finally:
        conn.close()


def _engaged_and_left_to_catch_up(port, creator, monkeypatch, name):
    """
    An engagement the reader names only REACTION, kept as a comment without
    text: its person's score is left for a reader to bring up to date.
    """
    import post_summary

    monkeypatch.setattr(post_summary, "_CATCH_UP_SETTLE_S", 60.0)
    status, text = _post(port, "/api/v1/crm/interactions/ingest", {
        "full_name": name, "profile_url": f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}-t2",
        "headline": "Someone", "company": "Co", "interaction_type": "REACTION",
        "post_urn": creator["urn"], "post_author": ME})
    assert status == 200, text


def test_a_read_that_brings_derived_figures_up_to_date_wakes_nobody(studio, creator, monkeypatch):
    """
    Today's brief recomputes the post summaries and the scores an engagement
    left stale, and writes them. Nothing new happened: the engagement was
    announced. It was announced again as "database", and every panel read.
    """
    stream = Stream(studio["port"])
    try:
        stream.event()
        _engaged_and_left_to_catch_up(studio["port"], creator, monkeypatch, "Fourth Person")
        assert "people" in stream.change(timeout=3.0)[0]
        # Past the backstop's next look, so the engagement's own announcement
        # cannot be what explains the read's write.
        time.sleep(changes.WATCH_EVERY_S + 0.5)
        assert _stale_scores() >= 1
        assert _get(studio["port"], "/api/v1/today") == 200
        assert _stale_scores() == 0, "the read did not bring the score up to date, so this tested nothing"
        notes = _changes_for(stream, 2.5)
        assert not any(note["kind"] == "database" for note in notes), notes
    finally:
        stream.close()


def test_the_score_catch_up_wakes_nobody(studio, creator, monkeypatch):
    """The same recompute when a catch-up, rather than a screen, gets there first."""
    import crm

    stream = Stream(studio["port"])
    try:
        stream.event()
        _engaged_and_left_to_catch_up(studio["port"], creator, monkeypatch, "Fifth Person")
        assert "people" in stream.change(timeout=3.0)[0]
        time.sleep(changes.WATCH_EVERY_S + 0.5)
        assert _stale_scores() >= 1
        conn = database.get_db()
        try:
            crm.scores_current(conn)
        finally:
            conn.close()
        assert _stale_scores() == 0
        notes = _changes_for(stream, 2.5)
        assert not any(note["kind"] == "database" for note in notes), notes
    finally:
        stream.close()


def test_the_summary_catch_up_wakes_nobody(studio, creator):
    """A post's summary recomputed by the catch-up is a derived write too."""
    import post_summary

    stream = Stream(studio["port"])
    try:
        stream.event()
        conn = database.get_db()
        try:
            with conn:
                conn.execute("UPDATE post_engagement SET stale = 1 WHERE post_urn = ?", (creator["urn"],))
        finally:
            conn.close()
        # The mark itself is a write nothing named, and is reported as one.
        assert stream.change(timeout=changes.WATCH_EVERY_S + 2.0)[0] == ["database"]
        time.sleep(changes.WATCH_EVERY_S + 0.5)
        conn = database.get_db()
        try:
            assert post_summary.catch_up(conn) >= 1
        finally:
            conn.close()
        notes = _changes_for(stream, 2.5)
        assert not any(note["kind"] == "database" for note in notes), notes
    finally:
        stream.close()


def test_a_change_never_carries_a_name_or_text():
    note = changes.note_of("people", {"lead": "Jane Doe", "post": "a post's text", "interaction": "LIKE",
                                      "full_name": "Jane Doe", "extractor": "engagers"})
    assert note == {"kind": "people", "extractor": "engagers"}, note


def test_the_account_and_content_pages_say_account(studio, creator):
    """Release 2.8.0's reader of the creator's own account pages (track 5, phase 2)."""
    kinds = _published_by(studio["port"], "/api/analytics/page-figures", {
        "author": ME, "page": "profile_views", "readings": [{"period_label": "90d", "figures": {"profile_views": 4}}]})
    assert kinds == ["account"], kinds


def test_a_post_the_phone_asked_about_says_desk(studio, creator):
    """Track 6: a post shared from the phone becomes a request Today shows."""
    import desk_requests

    stream = Stream(studio["port"])
    try:
        stream.event()
        conn = database.get_db()
        try:
            desk_requests.record(conn, creator["urn"])
        finally:
            conn.close()
        assert stream.change(timeout=3.0)[0] == ["desk"]
    finally:
        stream.close()


def test_the_daily_section_and_its_marks_say_ideas(studio, creator):
    """Track 7: the day's cards, and a keep or skip on one of them."""
    import record_daily

    stream = Stream(studio["port"])
    try:
        stream.event()
        built = record_daily.run_today()
        assert built["status"] in ("built", "carried"), built
        assert "ideas" in stream.change(timeout=3.0)[0]
        # Only a card that is shown can be kept or skipped.
        card = next(c for c in record_daily.read_today()["cards"] if c["status"] == "shown")
        status, text = _post(studio["port"], "/api/v1/record/marks",
                             {"day": card["day"], "card_id": card["card_id"], "mark": "keep"})
        assert status == 200, text
        assert stream.change(timeout=3.0)[0] == ["ideas"]
    finally:
        stream.close()


# What the extension writes through, and what each says. A path the extension
# starts relaying has to be added here, announced or with the reason it is not.
EXTENSION_WRITES = {
    "/api/analytics/ingest": "account",
    "/api/analytics/page-figures": "account",
    "/api/v1/crm/interactions/ingest": "people",
    "/api/v1/bridge/heartbeat": "heartbeat",
    "/api/v1/bridge/capture": "capture",
    "/api/v1/bridge/voyager-ingest": "readings or account",
    "/api/v1/identity/observe": "identity",
    "/api/v1/self/posts/ingest": "posts",
    "/api/v1/self/posts/analytics": "readings",
    "/api/v1/self/outbound/ingest": "outbound",
    "/api/v1/self/imports/event": "imports",
    # Not announced, each for its reason; the backstop reports them as
    # "database", which every screen reads as "anything may have changed".
    "/api/v1/posts/bind-urn": "unannounced: writes only when a post binds, which is rare",
    "/api/v1/bridge/schema-drift": "unannounced: no studio screen shows drift events",
    "/api/v1/identity/me": "unannounced: a read",
    "/api/v1/self/imports/pending": "unannounced: a read that may expire an old request",
}


def test_every_path_the_extension_writes_through_is_accounted_for():
    import re as _re

    with open(os.path.join(REPO_ROOT, "studio", "extension", "background.js"), encoding="utf-8") as handle:
        source = handle.read()
    relayed = set()
    for name in ("RELAYABLE_PATHS", "KEEP_WHEN_BUSY"):
        block = _re.search(name + r" = new Set\(\[(.*?)\]\)", source, _re.S)
        assert block, f"{name} is no longer where this test reads it"
        relayed |= set(_re.findall(r'"(/api/[^"]+)"', block.group(1)))
    missing = sorted(relayed - set(EXTENSION_WRITES))
    assert not missing, f"the extension writes through paths this test does not account for: {missing}"


def test_a_post_the_queue_marks_due_says_queue(studio):
    from datetime import datetime, timedelta, timezone

    import scheduler

    due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    conn = database.get_db()
    try:
        with conn:
            conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'scheduled', ?)",
                         ("t2-show-due", "A post that comes due.", due))
    finally:
        conn.close()
    stream = Stream(studio["port"])
    try:
        stream.event()
        actions = scheduler.native_scheduler.check_scheduled_queue()
        assert any(action.get("post_id") == "t2-show-due" for action in actions), actions
        kinds, took = stream.change(timeout=3.0)
        assert "queue" in kinds, kinds
    finally:
        stream.close()
        conn = database.get_db()
        try:
            with conn:
                conn.execute("DELETE FROM posts WHERE id = 't2-show-due'")
        finally:
            conn.close()


def test_a_queue_check_that_moved_nothing_says_nothing(studio):
    """The check runs every 30 seconds; a check with nothing due is not a change."""
    import scheduler

    before = changes.sequence()
    assert scheduler.native_scheduler.check_scheduled_queue() == []
    assert changes.sequence() == before


# ---------------------------------------------------------------------------
# Lifetimes: a gone client, a stopping server, a restore
# ---------------------------------------------------------------------------

def test_a_client_that_goes_away_is_let_go(studio):
    stream = Stream(studio["port"])
    stream.event()
    assert changes.subscriber_count() >= 1
    stream.close()
    assert _wait_until(lambda: changes.subscriber_count() == 0, timeout=5.0), \
        f"{changes.subscriber_count()} subscribers still held after the client closed"


def test_nothing_watches_the_database_while_nobody_listens(studio, monkeypatch):
    """
    The watcher looks once a second while a window listens, not at all once
    none does, and lets go of the file a short while after that.
    """
    monkeypatch.setattr(changes, "IDLE_CLOSE_S", 2.0)
    stream = Stream(studio["port"])
    try:
        stream.event()
        assert changes.watch_state()["ticking"] and changes.watch_state()["open"]
        looked = changes.watch_state()["looks"]
        time.sleep(changes.WATCH_EVERY_S * 2 + 0.3)
        assert changes.watch_state()["looks"] > looked, "the watcher did not look while a window listened"
    finally:
        stream.close()
    assert _wait_until(lambda: changes.subscriber_count() == 0, timeout=5.0)
    stopped = changes.watch_state()["looks"]
    time.sleep(changes.WATCH_EVERY_S * 2 + 0.3)
    assert changes.watch_state()["looks"] == stopped, "the watcher went on looking with nobody listening"
    assert _wait_until(lambda: not changes.watch_state()["open"] and not changes.watch_state()["ticking"],
                       timeout=changes.IDLE_CLOSE_S + changes.WATCH_EVERY_S + 2.0), \
        f"the watcher kept the file open with nobody listening: {changes.watch_state()}"


def test_a_window_back_after_the_watcher_let_go_is_told_to_read_again(studio, monkeypatch):
    """Once the connection is closed nothing is known about the gap, and unknown is changed."""
    monkeypatch.setattr(changes, "IDLE_CLOSE_S", 1.0)
    first = Stream(studio["port"])
    try:
        _name, event_id, _data = first.event()
    finally:
        first.close()
    assert _wait_until(lambda: not changes.watch_state()["open"], timeout=6.0)
    back = Stream(studio["port"], since=event_id)
    try:
        assert json.loads(back.event()[2])["changed"] is True
    finally:
        back.close()


def test_the_server_stops_promptly_with_a_stream_open():
    """
    uvicorn waits for every in-flight response before it exits, and a stream
    that never ends would hold a reload or a Ctrl+C for ever. The stop a
    reload sends is a signal; this is the same path.
    """
    import app as app_module

    server, thread, port = _serve(app_module.app)
    stream = Stream(port)
    try:
        stream.event()
        server.handle_exit(signal.SIGTERM, None)
        thread.join(timeout=5)
        assert not thread.is_alive(), "the server did not stop within five seconds while a stream was open"
        with pytest.raises((EOFError, OSError)):
            while True:
                stream.event(timeout=2.0)
    finally:
        stream.close()
        if thread.is_alive():
            server.should_exit = True
            thread.join(timeout=5)


def test_the_watcher_is_put_down_for_a_restore_and_picks_up_after(studio):
    """
    Windows refuses to replace a file any handle holds, and the watcher holds
    one for as long as a window listens. The restore puts it down with the
    rest of the studio's background database work, and lets it go after.
    """
    import support

    stream = Stream(studio["port"])
    try:
        stream.event()
        assert _wait_until(lambda: changes.watch_state()["open"], timeout=3.0)
        support._put_the_database_down()
        assert changes.watch_state()["open"] is False
        # Down stays down: the watcher does not reopen while a restore swaps files.
        time.sleep(changes.WATCH_EVERY_S + 0.5)
        assert changes.watch_state()["open"] is False
        support._let_the_database_go()
        kinds, _took = stream.change(timeout=changes.WATCH_EVERY_S + 2.0)
        assert kinds == ["database"], "a reopened watcher tells the windows to read again"
        assert changes.watch_state()["open"] is True
    finally:
        changes.let_go()
        stream.close()


def test_a_fresh_home_is_left_alone_until_init_db_has_set_it_up(studio, monkeypatch):
    """
    2.9.0's Windows run: a test switched INOX_HYDRA_HOME to a brand-new home,
    and init_db failed inside get_db with "database is locked". The watcher,
    following the active database, opened the new file the moment it existed,
    while init_db was switching it to WAL and running the migrations, and
    Windows refuses that work while another connection holds the file. The
    product's case is creating or switching to a new creator profile.

    Here the watcher looks every 10 ms while a window listens, init_db runs on
    a fresh home in another thread, and every database the watcher opens is
    checked: it must never open one whose schema is not there yet, init_db must
    succeed, and the watcher must follow the new database once it is ready.
    """
    import sqlite_open

    monkeypatch.setattr(changes, "WATCH_EVERY_S", 0.01)
    real_connect = sqlite_open.connect
    opened = []

    def watched_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        if threading.current_thread().name == "studio-changes-watch":
            opened.append((str(args[0]), int(conn.execute("PRAGMA user_version").fetchall()[0][0])))
        return conn

    monkeypatch.setattr(sqlite_open, "connect", watched_connect)
    stream = Stream(studio["port"])
    try:
        stream.event()
        assert _wait_until(lambda: changes.watch_state()["ticking"], timeout=3.0)
        # Past any one second sleep the thread was already in, and looking
        # every 10 ms, so it cannot sleep through init_db's tens of milliseconds.
        time.sleep(changes.IDLE_CLOSE_S and 1.2)
        before = changes.watch_state()["looks"]
        time.sleep(0.2)
        assert changes.watch_state()["looks"] - before >= 5, "the watcher is not looking fast enough to test this"
        fresh = tempfile.mkdtemp(prefix="inox_t2_fresh_home_")
        monkeypatch.setenv("INOX_HYDRA_HOME", fresh)
        # The file exists, in WAL, and its schema is not there yet: held open
        # long enough that a watcher looking every 10 ms cannot miss it.
        real_ensure = database.ensure_schema

        def slow_ensure(*args, **kwargs):
            time.sleep(0.2)
            return real_ensure(*args, **kwargs)

        monkeypatch.setattr(database, "ensure_schema", slow_ensure)
        failure = []

        def set_up():
            try:
                database.init_db()
            except Exception as error:  # pragma: no cover - the fault this test exists for
                failure.append(error)

        worker = threading.Thread(target=set_up)
        worker.start()
        worker.join(timeout=60)
        assert not worker.is_alive() and not failure, f"init_db on a fresh home failed: {failure}"
        new_path = paths.get_db_path()
        assert _wait_until(lambda: changes.watch_state()["path"] == new_path and changes.watch_state()["open"],
                           timeout=5.0), f"the watcher did not follow the new database: {changes.watch_state()}"
        early = [(path, version) for path, version in opened if version == 0]
        assert not early, f"the watcher opened a database before its schema was there: {early}"
    finally:
        stream.close()
        monkeypatch.undo()


def test_the_watcher_creates_no_database_file(studio, monkeypatch):
    """A home whose database does not exist yet is never given one by the watcher."""
    empty = tempfile.mkdtemp(prefix="inox_t2_no_db_")
    monkeypatch.setenv("INOX_HYDRA_HOME", empty)
    target = paths.get_db_path()
    assert not os.path.exists(target)
    changes._watch.look()
    assert not os.path.exists(target), "the watcher created a database file"
    assert changes.watch_state()["open"] is False


def test_the_test_client_can_read_the_stream_too(studio):
    """
    The in-process client the rest of the suite uses sees the same first
    event. It runs a response to completion before returning any of it, so a
    stream is ended from beside it, the way a stopping server ends one.
    """
    client = TestClient(studio["app"])
    done = threading.Event()

    def end_it():
        while not done.wait(0.1):
            if changes.subscriber_count():
                changes.close_all()

    closer = threading.Thread(target=end_it, daemon=True)
    closer.start()
    try:
        response = client.get(EVENTS)
    finally:
        done.set()
        closer.join(timeout=5)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.startswith("retry: ")
    assert "event: hello\n" in response.text


def test_a_stopping_server_ends_only_its_own_streams(studio):
    """Several servers run in one test process; one stopping leaves the rest alone."""
    import app as app_module

    other, thread, port = _serve(app_module.app)
    mine = Stream(studio["port"])
    theirs = Stream(port)
    try:
        mine.event()
        theirs.event()
        other.should_exit = True
        thread.join(timeout=5)
        assert not thread.is_alive()
        changes.publish("posts")
        kinds, _took = mine.change(timeout=3.0)
        assert kinds == ["posts"], "a stream on the server still running was ended by the other one stopping"
    finally:
        mine.close()
        theirs.close()
