"""
The page heartbeat says whether network reading is on and what LinkedIn calls.
==============================================================================

Cycle 4, track 1, items 2 and 3 (the page side). The heartbeat carried the
version and the page kind and nothing about the switch, so the studio could
not tell "off" from "on and matching nothing". It now carries the switch,
whether the page carries the interceptor (it answers when asked, over the
window channel; it used to mark the document), the Resource Timing
count of the page's /voyager/api/ calls, how many match the bridge's
patterns, and the counts by path and GraphQL query name, never a query
string or a URN.
"""

import pytest

from qc_f3_pages import Pages, page_html

SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js")
HEARTBEAT = "/api/v1/bridge/heartbeat"


def _states(pages, page):
    """
    What the page told the worker about itself. Pages used to send the studio
    a heartbeat each; since cycle 4, track 1, phase 2 they tell the worker
    (PAGE_STATE), and the worker carries it on one heartbeat per browser.
    """
    return [m for m in pages.sent(page) if m.get("action") == "PAGE_STATE"]


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _serve_voyager(page):
    page.context.route("**/voyager/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))


def _fetch(page, url):
    page.evaluate("(u) => fetch(u).then(r => r.text())", url)


def _latest_beat(pages, page):
    beats = _states(pages, page)
    assert beats
    assert not pages.sent(page, HEARTBEAT), "a tab sent the studio a heartbeat of its own"
    return beats[-1]


def test_with_the_switch_off_the_heartbeat_says_off_and_counts_nothing(pages):
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": False})
    _serve_voyager(page)
    _fetch(page, "https://www.linkedin.com/voyager/api/graphql?queryId=voyagerFeedDashMainFeed.abc123&variables=(start:0)")
    page.wait_for_timeout(100)
    page.clock.run_for(61000)
    beat = _latest_beat(pages, page)
    assert beat["network_reading"]["switch"] is False
    assert beat.get("voyager_calls") is None, "the page counted LinkedIn's calls with the switch off"


def test_with_the_switch_on_the_heartbeat_counts_calls_by_path_and_query_name(pages):
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": True})
    _serve_voyager(page)
    page.clock.run_for(100)
    _fetch(page, "https://www.linkedin.com/voyager/api/graphql?queryId=voyagerFeedDashMainFeed.abc123&variables=(start:0)")
    _fetch(page, "https://www.linkedin.com/voyager/api/graphql?queryId=voyagerFeedDashMainFeed.abc123&variables=(start:10)")
    _fetch(page, "https://www.linkedin.com/voyager/api/identity/dash/profiles?q=memberIdentity&memberIdentity=someone")
    _fetch(page, "https://www.linkedin.com/voyager/api/messaging/conversations?keyVersion=LEGACY_INBOX")
    page.wait_for_timeout(200)
    page.clock.run_for(61000)
    beat = _latest_beat(pages, page)
    reading = beat["network_reading"]
    assert reading["switch"] is True
    assert reading["voyager_calls_seen"] == 4
    assert reading["matched"] == 1, "only identity/dash/profiles matches the bridge's patterns"
    assert reading["injected"] is False, "no interceptor is in this page, and the heartbeat must say so"
    calls = beat["voyager_calls"]
    assert calls == {
        "/voyager/api/graphql voyagerFeedDashMainFeed": 2,
        "/voyager/api/identity/dash/profiles": 1,
        "/voyager/api/messaging/conversations": 1,
    }
    assert not any("?" in key or "urn:" in key or "memberIdentity" in key for key in calls)


def test_an_interceptor_that_answers_is_reported_as_injected(pages):
    page = pages.open("/feed/", page_html("<main></main>"),
                      scripts=("voyager_interceptor.js",) + SCRIPTS, storage={"networkReading": True})
    page.clock.run_for(100)
    beat = _latest_beat(pages, page)
    assert beat["network_reading"]["injected"] is True


def test_a_capture_the_page_forwarded_is_dated_on_the_heartbeat(pages):
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": True})
    page.clock.run_for(100)
    page.evaluate("""(m) => window.postMessage(m, window.location.origin)""", {
        "type": "INOX_VOYAGER_CAPTURE", "source": "inox-voyager-interceptor",
        "payload": {"url": "https://www.linkedin.com/voyager/api/feed/updatesV2", "method": "GET", "status": 200,
                    "timestamp": "2026-10-26T10:00:00.000Z", "captureId": "c1",
                    "body": {"elements": [{"entityUrn": "urn:li:activity:7385000000000000001"}]}}})
    page.wait_for_timeout(100)
    page.clock.run_for(61000)
    reading = _latest_beat(pages, page)["network_reading"]
    assert reading["captured"] == 1
    assert isinstance(reading["last_capture_at"], str) and reading["last_capture_at"]


HOLD_STORAGE = """() => {
  const real = chrome.storage.local.get;
  window.__release = [];
  chrome.storage.local.get = (keys, cb) => real(keys, (out) => { window.__release.push(() => cb(out)); });
}"""


def test_the_state_is_reported_as_soon_as_the_switch_is_known(pages):
    """
    content.js and own_pages.js run in one task, so the first heartbeat leaves
    before the switch has been read and carries no state; the next one was a
    minute later.
    """
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": True},
                      before=HOLD_STORAGE)
    first = _states(pages, page)
    assert first and "network_reading" not in first[0]
    page.evaluate("() => window.__release.splice(0).forEach((f) => f())")
    page.wait_for_timeout(50)
    beats = _states(pages, page)
    assert any((b.get("network_reading") or {}).get("switch") is True for b in beats), (
        "the state waited for the next minute's heartbeat")


def test_a_call_that_names_a_member_or_a_post_is_counted_without_naming_them(pages):
    """LinkedIn's REST paths carry who or what was asked about; the meter keeps the shape only."""
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": True})
    _serve_voyager(page)
    page.clock.run_for(100)
    _fetch(page, "https://www.linkedin.com/voyager/api/identity/profiles/plainwordvanity/profileView")
    _fetch(page, "https://www.linkedin.com/voyager/api/socialActions/urn:li:activity:7385000000000000001/comments")
    _fetch(page, "https://www.linkedin.com/voyager/api/feed/updates/7385000000000000001")
    page.wait_for_timeout(200)
    page.clock.run_for(61000)
    calls = _latest_beat(pages, page)["voyager_calls"]
    assert calls == {
        "/voyager/api/identity/profiles/_id_/profileView": 1,
        "/voyager/api/socialActions/_id_/comments": 1,
        "/voyager/api/feed/updates/_id_": 1,
    }
    flat = " ".join(calls)
    assert "plainwordvanity" not in flat and "7385" not in flat and "urn" not in flat


def test_switching_off_and_on_again_does_not_count_a_call_twice(pages):
    page = pages.open("/feed/", page_html("<main></main>"), scripts=SCRIPTS, storage={"networkReading": True})
    _serve_voyager(page)
    page.clock.run_for(100)
    _fetch(page, "https://www.linkedin.com/voyager/api/graphql?queryId=voyagerFeedDashMainFeed.abc123&variables=(start:0)")
    page.wait_for_timeout(200)
    page.evaluate("() => chrome.storage.local.set({ networkReading: false })")
    page.evaluate("() => chrome.storage.local.set({ networkReading: true })")
    page.wait_for_timeout(200)
    page.clock.run_for(61000)
    assert _latest_beat(pages, page)["network_reading"]["voyager_calls_seen"] == 1
