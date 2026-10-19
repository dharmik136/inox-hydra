"""
Whose post an engager engaged with, read from fixture feed pages.
================================================================

A lead is someone who engaged with the creator's own post. The engager
readers in content.js decide whose post a reactor or commenter belongs to,
and the studio keeps the person only when that post is the creator's. These
drive the shipped content.js in headless Chromium (see qc_f3_pages.py).

BRIDGE-01  LinkedIn renders a post's reactions list as a modal outside the
           feed card. The reader could not find the card and took the author
           of the FIRST post in the feed, so reactors of a stranger's post
           became the creator's leads whenever the creator's post was first.
BRIDGE-02  In the rebuilt comment layout every comment list on the page was
           filed under the first list's author, with no post URN.
BRIDGE-20  A reactions list that finished loading inside the 4 s throttle was
           not read until something else on the page changed.
BRIDGE-21  Engagers seen while the studio was unreachable were marked as seen
           and never sent again on that page.
"""

import pytest

from qc_f3_pages import Pages, page_html

INGEST = "/api/v1/crm/interactions/ingest"

FEED = page_html("""
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7385000000000000001">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text">Three things I learned shipping a local-first app this year.</div>
   <button id="mine-count" class="social-details-social-counts__reactions-count">4</button>
 </div>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7385000000000000077">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/stranger-author/">Stranger Author</a></div>
   <div class="update-components-text">Hot take from somebody else entirely, about hiring.</div>
   <button id="stranger-count" class="social-details-social-counts__reactions-count">57</button>
 </div>
</main>
<div id="artdeco-modal-outlet"></div>
""", title="(3) Feed | LinkedIn")

MODAL = """
<div class="artdeco-modal" role="dialog">
  <div class="artdeco-modal__header"><h2>Reactions</h2></div>
  <div class="social-details-reactors-tab">
   <ul>
    <li class="social-details-reactors-tab__item"><a href="https://www.linkedin.com/in/reactor-one/"><div class="artdeco-entity-lockup__title">Reactor One</div><div class="artdeco-entity-lockup__subtitle">CTO at Acme</div></a></li>
    <li class="social-details-reactors-tab__item"><a href="https://www.linkedin.com/in/reactor-two/"><div class="artdeco-entity-lockup__title">Reactor Two</div><div class="artdeco-entity-lockup__subtitle">Recruiter at Globex</div></a></li>
   </ul>
  </div>
</div>
"""

OPEN_MODAL = "(html) => { document.getElementById('artdeco-modal-outlet').innerHTML = html; }"
CLOSE_MODAL = "() => { document.getElementById('artdeco-modal-outlet').innerHTML = ''; }"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _feed(pages):
    page = pages.open("/feed/", FEED)
    page.clock.run_for(5000)
    return page


def test_reactors_of_a_strangers_post_are_never_filed_as_the_creators(pages):
    page = _feed(pages)
    page.evaluate("() => document.getElementById('stranger-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)

    sent = pages.sent(page, INGEST)
    assert sent, "the stranger's reactors were not read at all"
    assert all(body["post_author"] != "test-creator" for body in sent), sent
    assert {body["post_urn"] for body in sent} == {"urn:li:activity:7385000000000000077"}
    assert {body["post_author"] for body in sent} == {"stranger-author"}


def test_reactors_of_the_creators_post_carry_its_urn_and_author(pages):
    page = _feed(pages)
    page.evaluate("() => document.getElementById('mine-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)

    sent = pages.sent(page, INGEST)
    assert {body["full_name"] for body in sent} == {"Reactor One", "Reactor Two"}
    assert {body["post_urn"] for body in sent} == {"urn:li:activity:7385000000000000001"}
    assert {body["post_author"] for body in sent} == {"test-creator"}


def test_the_second_list_opened_is_filed_under_its_own_post(pages):
    page = _feed(pages)
    page.evaluate("() => document.getElementById('mine-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)
    page.evaluate(CLOSE_MODAL)
    page.clock.run_for(5000)
    page.evaluate("() => document.getElementById('stranger-count').click()")
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)

    sent = pages.sent(page, INGEST)
    by_post = {}
    for body in sent:
        by_post.setdefault(body["post_urn"], set()).add((body["full_name"], body["post_author"]))
    assert by_post["urn:li:activity:7385000000000000001"] == {("Reactor One", "test-creator"), ("Reactor Two", "test-creator")}
    assert by_post["urn:li:activity:7385000000000000077"] == {("Reactor One", "stranger-author"), ("Reactor Two", "stranger-author")}


def test_a_reactions_list_of_unknown_origin_is_not_sent(pages):
    # Nothing on the page says whose post this list belongs to: no permalink,
    # and the creator clicked no post's counts. The first post in the feed is
    # the creator's, which is exactly the guess that must not be made.
    page = _feed(pages)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)

    sent = pages.sent(page, INGEST)
    assert not [body for body in sent if body["post_author"] == "test-creator"], sent
    assert sent == [], "a list whose post is unknown must not be filed at all"


def test_on_a_permalink_the_url_names_the_post(pages):
    html = FEED.replace('data-urn="urn:li:activity:7385000000000000077"', 'data-urn="x"')
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", html)
    page.clock.run_for(5000)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)

    sent = pages.sent(page, INGEST)
    assert {body["post_urn"] for body in sent} == {"urn:li:activity:7385000000000000001"}
    assert {body["post_author"] for body in sent} == {"test-creator"}


# ---------------------------------------------------------------------------
# BRIDGE-02: the rebuilt comment layout
# ---------------------------------------------------------------------------

def _comment(vanity, name, degree, headline, age, words):
    return f"""<div class="c"><a href="https://www.linkedin.com/in/{vanity}/"><img alt=""></a>
      <div><a href="https://www.linkedin.com/in/{vanity}/"><p>{name}</p></a><p>• {degree}</p><p>{headline}</p><p>{age}</p></div>
      <p>{words}</p></div>"""


def _post(urn, vanity, name, text, comments):
    return f"""
 <div data-urn="{urn}">
  <div data-testid="commentList-{urn}">
   <div class="hdr"><a href="https://www.linkedin.com/in/{vanity}/"><p>{name}</p></a><p>{text}</p></div>
   {''.join(comments)}
  </div>
 </div>"""


NEW_LAYOUT_FEED = (
    _post("urn:li:activity:7385000000000000001", "test-creator", "Test Creator",
          "Three things I learned shipping a local-first app.",
          [_comment("alice-fan", "Alice Fan", "2nd", "Founder at Northwind", "2h", "Great points, the second one rings true.")])
    + _post("urn:li:activity:7385000000000000099", "other-creator", "Other Creator",
            "A post by somebody else about hiring.",
            [_comment("bob-stranger", "Bob Stranger", "3rd+", "Head of Talent at Initech", "5h", "We hire this way too, totally agree.")])
)


def test_each_rebuilt_comment_list_is_filed_under_its_own_post(pages):
    page = pages.open("/feed/", page_html("<main id='m'></main>", title="Feed | LinkedIn"))
    page.clock.run_for(5000)
    page.evaluate("(html) => { document.getElementById('m').innerHTML = html; }", NEW_LAYOUT_FEED)
    page.clock.run_for(6000)

    sent = {body["full_name"]: body for body in pages.sent(page, INGEST)}
    assert sent["Alice Fan"]["post_author"] == "test-creator"
    assert sent["Alice Fan"]["post_urn"] == "urn:li:activity:7385000000000000001"
    assert sent["Bob Stranger"]["post_author"] == "other-creator"
    assert sent["Bob Stranger"]["post_urn"] == "urn:li:activity:7385000000000000099"


# ---------------------------------------------------------------------------
# BRIDGE-20 and BRIDGE-21: when a read happens, and when it is repeated
# ---------------------------------------------------------------------------

def test_a_list_that_loads_just_after_its_modal_is_read_without_another_change(pages):
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", FEED)
    page.clock.run_for(5000)
    shell = MODAL.split('<div class="social-details-reactors-tab">')[0] + "</div>"
    page.evaluate(OPEN_MODAL, shell)
    page.clock.run_for(800)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(12000)

    names = {body["full_name"] for body in pages.sent(page, INGEST)}
    assert names == {"Reactor One", "Reactor Two"}


def test_engagers_seen_while_the_studio_was_down_are_sent_again(pages):
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", FEED)
    page.evaluate("() => { window.__answers['%s'] = 'unreachable'; }" % INGEST)
    page.clock.run_for(5000)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)
    first = [body["full_name"] for body in pages.sent(page, INGEST)]
    assert sorted(first) == ["Reactor One", "Reactor Two"]

    # The studio is back, and LinkedIn re-renders the list.
    page.evaluate("() => { delete window.__answers['%s']; }" % INGEST)
    page.clock.run_for(31000)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)
    every = [body["full_name"] for body in pages.sent(page, INGEST)]
    assert sorted(every) == ["Reactor One", "Reactor One", "Reactor Two", "Reactor Two"]


def test_engagers_the_studio_kept_are_not_sent_twice(pages):
    page = pages.open("/feed/update/urn:li:activity:7385000000000000001/", FEED)
    page.clock.run_for(5000)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)
    page.evaluate(OPEN_MODAL, MODAL)
    page.clock.run_for(6000)
    assert sorted(body["full_name"] for body in pages.sent(page, INGEST)) == ["Reactor One", "Reactor Two"]
