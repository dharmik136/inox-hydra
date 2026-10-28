"""
Own-page items are marked sent only when the studio has answered.
=================================================================

Cycle 4, track 1, item 4. sendActivity() added each item's key to sentKeys
before the studio had answered, so a worker terminated mid-relay or a studio
restarting during an import silently dropped those items for the rest of
the page session. The engagers path already held an undecided person for
30 s; own pages now do the same thing: a key is remembered on ok, kept or a
decided refusal, and an unreachable answer leaves it for the next read.
"""

import pytest

from qc_f3_pages import Pages, page_html

SCRIPTS = ("content.js", "own_pages.js")
INGEST = "/api/v1/self/posts/ingest"

POSTS = page_html("""
<main>
 <div id="expanded-2-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000006">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">My own post about shipping a local-first app, written by me.</div>
   <button aria-label="9 reactions">9</button>
 </div>
</main>""", title="Test Creator | Activity | LinkedIn", lang="en")


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _scroll(page):
    page.evaluate("() => window.dispatchEvent(new Event('scroll'))")
    page.clock.run_for(2000)


def test_items_the_studio_never_answered_are_offered_again(pages):
    page = pages.open("/in/test-creator/recent-activity/all/", POSTS, scripts=SCRIPTS)
    page.evaluate("() => { window.__answers['%s'] = 'unreachable'; }" % INGEST)
    page.clock.run_for(4000)
    assert len(pages.sent(page, INGEST)) == 1
    _scroll(page)
    assert len(pages.sent(page, INGEST)) == 2, "the item was marked sent while the studio never answered"
    page.evaluate("() => { delete window.__answers['%s']; }" % INGEST)
    _scroll(page)
    assert len(pages.sent(page, INGEST)) == 3
    _scroll(page)
    assert len(pages.sent(page, INGEST)) == 3, "an item the studio took was sent again"


def test_items_the_studio_kept_or_refused_are_not_sent_again(pages):
    page = pages.open("/in/test-creator/recent-activity/all/", POSTS, scripts=SCRIPTS)
    page.evaluate("() => { window.__answers['%s'] = { httpStatus: 409, data: { reason: 'not_your_data', message: 'no' } }; }" % INGEST)
    page.clock.run_for(4000)
    assert len(pages.sent(page, INGEST)) == 1
    _scroll(page)
    assert len(pages.sent(page, INGEST)) == 1, "a decided refusal was asked again"


def test_an_import_while_the_studio_is_down_counts_each_item_once_and_ends(pages):
    """
    The import adds what each round sends to its running total, and ends when
    a round adds nothing. Items the studio never answered are offered again
    every round, which is right, and were counted again every round, which
    kept the stall check from ending the import: it scrolled all 250 rounds
    and reported a total many times the posts on the page.
    """
    hold = """() => {
      window.__answers['/api/v1/self/imports/pending'] = { status: 'success', request: { id: 7, kind: 'posts' } };
      window.__answers['%s'] = 'unreachable';
    }""" % INGEST
    page = pages.open("/in/test-creator/recent-activity/all/", POSTS, scripts=SCRIPTS, before=hold)
    page.clock.run_for(60000)
    events = pages.sent(page, "/api/v1/self/imports/event")
    finished = [e for e in events if e.get("event") == "finished"]
    assert finished, "the import never ended while the studio was down"
    assert finished[0]["items_seen"] == 1, f"one post was counted {finished[0]['items_seen']} times"
    assert len(pages.sent(page, INGEST)) >= 3, "an item the studio never answered was not offered again"
