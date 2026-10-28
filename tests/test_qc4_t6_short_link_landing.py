"""
A short link from the phone lands on a post page carrying its fragment.
======================================================================

Today opens the phone's lnkd.in link in the creator's browser with
#inox-desk-<request id> (tests/test_qc4_t6_short_links.py). A browser keeps
a fragment across an HTTP redirect, so the post page the link lands on
carries it, and content.js reports the request id with the post that page
names, once. These load the shipped content script on fixture pages under
https://www.linkedin.com (tests/qc_f3_pages.py): nothing leaves the machine.

Measured in this Chromium while building it: a fragment survives a 301 from
one address to another, and the navigation entry keeps the landing address,
fragment included, after the page replaces its own address with
history.replaceState, as LinkedIn's routing can.

Strict Invariants:
- Zero em-dashes.
"""

import pytest

import json
import os

from qc_f3_pages import EXT, FAKE_CHROME, Pages, page_html

POST_ID = "7390000000000000103"
URN = f"urn:li:activity:{POST_ID}"
POST_PATH = f"/posts/someone_slug-activity-{POST_ID}-AbCd?utm_source=share&utm_medium=member_android"
LANDED = "/api/v1/desk-requests/landed"
BODY = page_html("<main><article><p>A post of mine</p></article></main>")


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _settle(page):
    page.clock.run_for(3000)


def test_a_post_page_that_kept_the_fragment_says_which_post_answers_the_request(pages):
    page = pages.open(POST_PATH + "#inox-desk-42", BODY)
    _settle(page)
    assert pages.sent(page, LANDED) == [{"request_id": 42, "activity_urn": URN}]


def test_the_landing_is_reported_once(pages):
    page = pages.open(POST_PATH + "#inox-desk-42", BODY)
    page.evaluate("() => { window.dispatchEvent(new HashChangeEvent('hashchange')); }")
    _settle(page)
    assert len(pages.sent(page, LANDED)) == 1


def _open_unclocked(pages, path, before):
    """
    As pages.open, without the page clock: the clock replaces the page's
    performance object, whose navigation entry is what this case reads. The
    script reports as it loads, so no timer is waited for.
    """
    context = pages.browser.new_context(service_workers="block")
    context.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html; charset=utf-8", body=BODY)
                  if r.request.url.split("?")[0] == "https://www.linkedin.com" + path.split("?")[0] else r.abort())
    context.add_init_script("window.__me = 'test-creator'; window.__initialStorage = {}; window.__initialSession = {};")
    context.add_init_script(FAKE_CHROME)
    page = context.new_page()
    page.goto("https://www.linkedin.com" + path, wait_until="load")
    page.evaluate(before)
    for name in ("content.js",):
        page.add_script_tag(path=os.path.join(EXT, name))
    return page


def test_a_fragment_the_page_dropped_is_read_from_where_the_browser_landed(pages):
    """LinkedIn's routing may rewrite the address; the navigation entry keeps the one the link landed on."""
    page = _open_unclocked(pages, POST_PATH + "#inox-desk-7",
                           "history.replaceState(null, '', '/feed/update/urn:li:activity:1111111111111111111/')")
    try:
        assert page.evaluate("location.hash") == "", "the fixture did not drop the fragment"
        sent = [m["body"] for m in page.evaluate("() => window.__sent") if m.get("path") == LANDED]
        assert sent == [{"request_id": 7, "activity_urn": URN}], (
            "the post was taken from the rewritten address, not from where the link landed: " + json.dumps(sent))
    finally:
        page.context.close()


def test_no_fragment_reports_nothing(pages):
    page = pages.open(POST_PATH, BODY)
    _settle(page)
    assert pages.sent(page, LANDED) == []


@pytest.mark.parametrize("fragment", ["#inox-desk-", "#inox-desk-12x", "#inox-desk-1;2", "#desk-12", "#inox-desk-1234567890123"])
def test_a_fragment_of_any_other_shape_reports_nothing(pages, fragment):
    page = pages.open(POST_PATH + fragment, BODY)
    _settle(page)
    assert pages.sent(page, LANDED) == []


def test_a_page_that_names_no_post_reports_nothing(pages):
    page = pages.open("/feed/?trk=x#inox-desk-42", BODY)
    _settle(page)
    assert pages.sent(page, LANDED) == []
