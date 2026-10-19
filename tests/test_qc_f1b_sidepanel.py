"""
The side panel's own page, driven in headless Chromium with a fake chrome API.
=============================================================================

Every request the page makes is answered from this file; nothing reaches the
network. The fake records each message the panel sends to its service worker,
so a test can read what the panel asked the studio to do.
"""

import json
import os
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

EXT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))
ORIGIN = "https://sidepanel.test"

FAKE_CHROME = r"""
window.__msgs = [];
window.chrome = {
  runtime: { lastError: undefined, sendMessage: (m, cb) => {
    window.__msgs.push(m);
    let resp = { ok: true, httpStatus: 200, data: {} };
    if (m.action === 'PANEL_API' && m.path.startsWith('/api/posts')) {
      resp = { ok: true, httpStatus: 200, data: { posts: window.__posts } };
    }
    if (m.action === 'PANEL_WRITE') resp = { ok: true, httpStatus: 200, data: window.__injected };
    setTimeout(() => cb && cb(resp), 5);
  } },
  tabs: {
    query: async () => [{ id: 3, url: 'https://www.linkedin.com/feed/' }],
    sendMessage: (id, m, cb) => setTimeout(() => cb({ status: 'success' }), 5),
    create: () => {},
  },
};
"""

RECORDED = {
    "status": "recorded",
    "post_id": "post-1",
    "message": "Open this post on LinkedIn once and the studio will bind its URN.",
}


def _files():
    def read(name):
        with open(os.path.join(EXT, name), encoding="utf-8") as handle:
            return handle.read()

    return {
        f"{ORIGIN}/sidepanel.html": ("text/html", read("sidepanel.html")),
        f"{ORIGIN}/sidepanel.js": ("application/javascript", read("sidepanel.js")),
    }


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def panel(browser):
    files = _files()

    def open_panel(posts=(), injected=None):
        context = browser.new_context(service_workers="block")
        context.route(
            "**/*",
            lambda route: route.fulfill(
                status=200, content_type=files[route.request.url][0], body=files[route.request.url][1]
            )
            if route.request.url in files
            else route.abort(),
        )
        page = context.new_page()
        page.add_init_script(
            "window.__posts = " + json.dumps(list(posts)) + ";"
            + "window.__injected = " + json.dumps(injected if injected is not None else RECORDED) + ";"
            + FAKE_CHROME
        )
        page.goto(f"{ORIGIN}/sidepanel.html")
        page.wait_for_timeout(150)
        opened.append(context)
        return page

    opened = []
    yield open_panel
    for context in opened:
        context.close()


def _insert(page, text):
    page.fill("#sp-text", text)
    page.click("#btn-inject-composer")
    deadline = time.time() + 2
    while time.time() < deadline:
        if any(m.get("action") == "PANEL_WRITE" for m in page.evaluate("window.__msgs")):
            break
        page.wait_for_timeout(20)
    page.wait_for_timeout(100)


# ---------------------------------------------------------------------------
# BRIDGE-07: the toast says what the studio answered
# ---------------------------------------------------------------------------

def test_an_insert_the_studio_cannot_identify_says_so(panel):
    too_short = {
        "status": "too_short",
        "message": "This text is too short to identify the post again later.",
    }
    page = panel(injected=too_short)
    _insert(page, "Short one.")
    toast = page.inner_text("#sp-toast")
    assert "too short to identify" in toast
    assert "will link it" not in toast


def test_a_recorded_insert_still_promises_the_link(panel):
    page = panel()
    _insert(page, "A post long enough to be identified again when it is opened on LinkedIn.")
    assert "will link it" in page.inner_text("#sp-toast")


# ---------------------------------------------------------------------------
# BRIDGE-03: an insert of a queued post names that post
# ---------------------------------------------------------------------------

def test_an_insert_of_the_prefilled_queued_post_names_it(panel):
    queued = {"id": "post_q1", "status": "scheduled", "scheduled_for": "2026-10-25T03:30:00+00:00",
              "content": "The queued post the panel opens with, long enough to identify again."}
    page = panel(posts=[queued])
    assert page.input_value("#sp-text") == queued["content"]
    page.click("#btn-inject-composer")
    page.wait_for_timeout(200)
    writes = [m for m in page.evaluate("window.__msgs") if m.get("action") == "PANEL_WRITE"]
    assert writes and writes[0]["body"]["post_id"] == "post_q1"


# ---------------------------------------------------------------------------
# BRIDGE-18: the Queued tab invents no time and renders text as text
# ---------------------------------------------------------------------------

def test_the_queue_tab_shows_no_invented_time_and_literal_text(panel):
    post = {"id": "post_a", "status": "scheduled", "scheduled_for": None,
            "content": "Why <b>every</b> founder should read <Thinking in Systems> before hiring\n\nPart two."}
    page = panel(posts=[post])
    page.click("#tab-queue-btn")
    page.wait_for_selector(".queue-item-mini")
    item = page.query_selector(".queue-item-mini")
    assert "No time set" in item.query_selector(".queue-item-time").inner_text()
    assert "5:30" not in item.inner_text()
    assert item.query_selector(".queue-item-text").inner_text() == (
        "Why <b>every</b> founder should read <Thinking in Systems> before hiring"
    )


# ---------------------------------------------------------------------------
# BRIDGE-19: the panel's fold verdict is the studio's
# ---------------------------------------------------------------------------

FOLD_CASES = [
    "x" * 165,  # one line past the 140 fold, which the old rule called safe
    "x" * 120,
    "Short first line.\n\nSecond paragraph that is long enough to carry the opening past the fold line of the studio, "
    "which is one hundred and forty characters.",
    "One.\nTwo.\nThree.\nFour, which is below the fold and never counts.",
    "".join(chr(0x1D5D4 + (i % 26)) for i in range(130)),  # bold letters, two UTF-16 units each
]


@pytest.mark.parametrize("text", FOLD_CASES, ids=["one-line-165", "one-line-120", "paragraphs", "four-lines", "bold-130"])
def test_the_panel_and_the_studio_agree_on_the_fold(panel, text):
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(EXT), "backend"))
    from formatters import analyze_hook

    page = panel()
    page.fill("#sp-text", text)
    verdict = page.inner_text("#sp-fold-status")
    studio_safe = analyze_hook(text)["mobile_safe"]
    assert (verdict == "Fold Safe") == studio_safe, (verdict, studio_safe)


def test_the_panel_carries_the_studios_fold_numbers():
    import re
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(EXT), "backend"))
    import fold

    with open(os.path.join(EXT, "sidepanel.js"), encoding="utf-8") as handle:
        source = handle.read()
    assert re.search(r"const MOBILE_FOLD_CHARS = (\d+);", source).group(1) == str(fold.MOBILE_FOLD_CHARS)
    assert re.search(r"const MOBILE_FOLD_LINES = (\d+);", source).group(1) == str(fold.MOBILE_FOLD_LINES)
    assert not re.search(r"length\s*[<>]=?\s*(140|180|210)\b", source), "a second fold number crept back in"
