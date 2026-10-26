"""
Routes arrive by the Navigation API, and no first capture is lost at the gate.
==============================================================================

Cycle 4, track 1, items 7 and 5 (the extension side).

  item 7  In-app navigation was noticed by comparing location.href on every
          DOM mutation batch and on a 1 s poll, because a content script
          cannot see LinkedIn's pushState. The Navigation API delivers
          `currententrychange` and `navigate` to the isolated world (a
          ten-minute spike on Chromium 153 confirmed it, recorded in
          docs/quality/cycle4/t1-bridge.md), so the route is seen in the same
          task as the pushState, the documentElement observer is gone, and
          the poll is a 5 s net behind feature detection.
  item 5  content.js read the network-reading switch asynchronously and
          dropped every interceptor message that arrived before the read
          resolved. They are queued and handled once it has. The interceptor
          marks the document, so the isolated world can say whether the page
          carries it.

These run the shipped scripts in headless Chromium (see qc_f3_pages.py).
"""

import os
import re

import pytest

from qc_f3_pages import EXT, Pages, page_html


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _source(name):
    with open(os.path.join(EXT, name), encoding="utf-8") as handle:
        return handle.read()


COUNT_ROUTES = """() => {
  window.__routes = 0;
  window.addEventListener('studio:locationchange', () => { window.__routes += 1; });
}"""


def test_a_push_state_is_announced_in_the_same_task_without_a_mutation(pages):
    page = pages.open("/feed/", page_html("<main></main>"), before=COUNT_ROUTES)
    assert page.evaluate("() => 'navigation' in window"), "this Chromium has no Navigation API; the test cannot judge"
    routes = page.evaluate("() => { history.pushState({}, '', '/in/test-creator/'); return window.__routes; }")
    assert routes == 1, "the route change was not seen when pushState returned"


def test_a_replace_state_and_a_traversal_are_announced_too(pages):
    page = pages.open("/feed/", page_html("<main></main>"), before=COUNT_ROUTES)
    page.evaluate("() => history.pushState({}, '', '/in/test-creator/')")
    page.evaluate("() => history.replaceState({}, '', '/in/test-creator/recent-activity/all/')")
    assert page.evaluate("() => window.__routes") == 2
    page.go_back()
    page.wait_for_timeout(100)
    assert page.evaluate("() => window.__routes") == 3


def test_the_same_route_is_not_announced_twice(pages):
    page = pages.open("/feed/", page_html("<main></main>"), before=COUNT_ROUTES)
    page.evaluate("() => history.pushState({}, '', '/in/test-creator/')")
    page.evaluate("() => history.replaceState({}, '', '/in/test-creator/')")
    assert page.evaluate("() => window.__routes") == 1


def test_the_document_observer_is_gone_and_the_poll_is_a_five_second_net():
    content = _source("content.js")
    # An observer of the whole document's subtree is what cost every tab.
    for found in re.finditer(r"observe\(document\.(documentElement|body),\s*\{([^}]*)\}", content):
        assert "subtree" not in found.group(2) or found.group(1) == "body", (
            "the whole-document route observer is still there")
    block = content[content.index("function checkForNavigation()"):content.index("maybeExtractAnalytics();")]
    assert '"navigation" in window' in block, "the Navigation API is not feature-detected"
    assert "currententrychange" in block
    # The navigate listener announced an event on LinkedIn's window that no
    # reader used and LinkedIn's own scripts could hear (the review's N7 and
    # S7); it is gone until a reader needs it.
    assert '"navigate"' not in block and "studio:navigating" not in content
    polls = re.findall(r"setInterval\([\s\S]*?\}, (\d+)\);", block)
    assert polls == ["5000"], f"the fallback poll is {polls}, not a 5 s net"


def test_without_the_navigation_api_the_poll_still_sees_the_route(pages):
    # window.navigation lives on the prototype, so it is blanked rather than deleted.
    page = pages.open("/feed/", page_html("<main></main>"),
                      before="() => { Object.defineProperty(window, 'navigation', { value: undefined, configurable: true }); "
                             + COUNT_ROUTES[7:])
    page.evaluate("() => history.pushState({}, '', '/in/test-creator/')")
    assert page.evaluate("() => window.__routes") == 0
    page.clock.run_for(5100)
    assert page.evaluate("() => window.__routes") == 1


# ---------------------------------------------------------------------------
# Item 5: the gate and the marker
# ---------------------------------------------------------------------------

CAPTURE = {
    "type": "INOX_VOYAGER_CAPTURE", "source": "inox-voyager-interceptor",
    "payload": {"url": "https://www.linkedin.com/voyager/api/feed/updatesV2", "method": "GET", "status": 200,
                "timestamp": "2026-10-26T10:00:00.000Z", "captureId": "capture_1",
                "body": {"elements": [{"entityUrn": "urn:li:activity:7385000000000000001",
                                       "socialDetail": {"totalSocialActivityCounts": {"numLikes": 3}}}]}},
}


# The fake storage is made to hold its answer until the test releases it, as
# a real page where LinkedIn's first responses arrive before chrome.storage
# has answered.
HOLD_STORAGE = """() => {
  const real = chrome.storage.local.get;
  window.__release = [];
  chrome.storage.local.get = (keys, cb) => real(keys, (out) => { window.__release.push(() => cb(out)); });
}"""


def test_a_capture_that_arrives_before_the_switch_is_read_is_kept(pages):
    page = pages.open("/feed/", page_html("<main></main>"), storage={"networkReading": True}, before=HOLD_STORAGE)
    page.evaluate("(m) => window.postMessage(m, window.location.origin)", CAPTURE)
    page.wait_for_timeout(50)
    assert not pages.sent(page, "/api/v1/bridge/voyager-ingest"), "sent before the switch was known"
    page.evaluate("() => window.__release.splice(0).forEach((f) => f())")
    page.wait_for_timeout(50)
    sent = pages.sent(page, "/api/v1/bridge/voyager-ingest")
    assert len(sent) == 1 and sent[0]["schema_name"] == "feed_updates"


def test_a_capture_that_arrives_before_a_switch_that_is_off_is_dropped(pages):
    page = pages.open("/feed/", page_html("<main></main>"), storage={"networkReading": False}, before=HOLD_STORAGE)
    page.evaluate("(m) => window.postMessage(m, window.location.origin)", CAPTURE)
    page.evaluate("() => window.__release.splice(0).forEach((f) => f())")
    page.wait_for_timeout(50)
    assert not pages.sent(page, "/api/v1/bridge/voyager-ingest")


def test_the_interceptor_answers_the_isolated_world_and_marks_nothing(pages):
    """
    The isolated world asks whether the page carries the interceptor; it used
    to read an attribute the interceptor wrote on LinkedIn's root element
    (the review's S7).
    """
    page = pages.open("/feed/", page_html("<main></main>"), scripts=("voyager_interceptor.js",),
                      before="() => { window.__heard = []; window.addEventListener('message', (e) => window.__heard.push(e.data)); }")
    page.evaluate("() => window.postMessage({ type: 'INOX_VOYAGER_PING', source: 'inox-bridge' }, window.location.origin)")
    page.wait_for_timeout(50)
    heard = page.evaluate("() => window.__heard")
    assert {"type": "INOX_VOYAGER_PRESENT", "source": "inox-voyager-interceptor"} in heard
    assert page.evaluate("() => document.documentElement.getAttributeNames()") == []


def test_a_response_about_other_members_never_leaves_the_page(pages):
    """
    Profiles, reactions on posts and comments are about other members. The
    page counts the call and sends nothing of the response, neither its data
    nor its drift.
    """
    page = pages.open("/feed/", page_html("<main></main>"), storage={"networkReading": True})
    page.clock.run_for(100)
    others = (
        ("https://www.linkedin.com/voyager/api/socialActions/urn:li:activity:7385000000000000001/likes",
         {"elements": [{"actor": {"urn": "urn:li:fsd_profile:ACoAAexample", "name": "Some One"},
                        "reactionType": "LIKE"}]}),
        ("https://www.linkedin.com/voyager/api/feed/comments",
         {"elements": [{"commenter": {"name": "Some One", "publicIdentifier": "someone-else"}}]}),
        ("https://www.linkedin.com/voyager/api/identity/profiles",
         {"elements": [{"publicIdentifier": "someone-else", "firstName": "Some", "lastName": "One"}]}),
    )
    for url, body in others:
        message = {**CAPTURE, "payload": {**CAPTURE["payload"], "url": url, "body": body}}
        page.evaluate("(m) => window.postMessage(m, window.location.origin)", message)
    page.wait_for_timeout(100)
    assert not pages.sent(page, "/api/v1/bridge/voyager-ingest"), "a response about other members was sent"
    assert not pages.sent(page, "/api/v1/bridge/schema-drift")
    # The feed itself still goes, for the studio to keep the creator's own posts from.
    page.evaluate("(m) => window.postMessage(m, window.location.origin)", CAPTURE)
    page.wait_for_timeout(100)
    assert len(pages.sent(page, "/api/v1/bridge/voyager-ingest")) == 1
