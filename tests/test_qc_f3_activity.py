"""
The creator's own activity pages: what is filed as theirs.
==========================================================

BRIDGE-09  On the comments activity page, a stranger's comment that the
           creator replied to was saved as the creator's own comment: "• You"
           was looked for anywhere in the comment, the nested reply included.
BRIDGE-10  On the rebuilt activity layout a post the creator reposted was
           imported as one they wrote, because the header fallback never
           looked for "reposted" and an unread author was taken to be the
           creator.
BRIDGE-22  A card that carries only a ugcPost or share id was saved under an
           activity id LinkedIn never issued (the same digits, relabelled).
BRIDGE-25  A short post that mentions a number of impressions or comments had
           that number stored as its own figures: the count reader scanned the
           post's own text before the real counts.

These run the shipped own_pages.js in headless Chromium (see qc_f3_pages.py)
on the creator's activity pages, with the studio confirming "test-creator".
"""

import pytest

from qc_f3_pages import Pages, page_html

SCRIPTS = ("voyager_schema.js", "content.js", "own_pages.js")


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _read(pages, path, body, title):
    page = pages.open(path, page_html(body, title=title, lang="en"), scripts=SCRIPTS)
    page.clock.run_for(4000)
    return page


COMMENTS = """
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000301">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/stranger-author/"><span class="update-components-actor__title">Stranger Author</span></a></div>
   <div class="update-components-text">Remote work is overrated and here is my data.</div>
   <article class="comments-comment-item" data-id="urn:li:comment:(activity:7386000000000000301,111)">
     <a href="https://www.linkedin.com/in/stranger-commenter/">Stranger Commenter</a> <span>• 2nd</span>
     <div class="comments-comment-item__main-content">I completely disagree, our team doubled output after going remote.</div>
     <article class="comments-comment-item" data-id="urn:li:comment:(activity:7386000000000000301,112)">
       <a href="https://www.linkedin.com/in/test-creator/">Test Creator</a> <span>• You</span>
       <div class="comments-comment-item__main-content">Fair point, thanks for the pushback.</div>
     </article>
   </article>
 </div>
</main>"""


def test_a_stranger_comment_you_replied_to_is_not_saved_as_yours(pages):
    page = _read(pages, "/in/test-creator/recent-activity/comments/", COMMENTS, "Test Creator | Comments | LinkedIn")
    items = [i for body in pages.sent(page, "/api/v1/self/outbound/ingest") for i in body["items"]]
    assert [i["my_text"] for i in items] == ["Fair point, thanks for the pushback."]


def test_your_comment_with_a_strangers_reply_inside_keeps_only_your_words(pages):
    mine_first = COMMENTS.replace("stranger-commenter", "SWAP").replace(
        'href="https://www.linkedin.com/in/test-creator/">Test Creator</a> <span>• You</span>',
        'href="https://www.linkedin.com/in/stranger-commenter/">Stranger Commenter</a> <span>• 2nd</span>').replace(
        "SWAP/\">Stranger Commenter</a> <span>• 2nd</span>", "test-creator/\">Test Creator</a> <span>• You</span>")
    page = _read(pages, "/in/test-creator/recent-activity/comments/", mine_first, "Test Creator | Comments | LinkedIn")
    items = [i for body in pages.sent(page, "/api/v1/self/outbound/ingest") for i in body["items"]]
    assert [i["my_text"] for i in items] == ["I completely disagree, our team doubled output after going remote."]


POSTS = """
<main>
 <div id="expanded-1-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000005">
   <div><span>Test Creator reposted this</span></div>
   <div><a href="https://www.linkedin.com/in/stranger-author/"><span>Stranger Author</span></a><span>Founder at Northwind</span></div>
   <div data-testid="expandable-text-box">Hiring is broken and every founder I know agrees with me on this one point.</div>
   <button aria-label="57 reactions">57</button>
 </div>
 <div id="expanded-2-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:activity:7386000000000000006">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">My own post about shipping a local-first app, written by me.</div>
   <button aria-label="9 reactions">9</button>
 </div>
 <div id="expanded-3-FeedType_MEMBER_ACTIVITY" data-urn="urn:li:ugcPost:7386000000000000777">
   <div><a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a></div>
   <div data-testid="expandable-text-box">A document post of mine whose card carries only its ugcPost id.</div>
 </div>
</main>"""


def _posts(pages, body=POSTS):
    page = _read(pages, "/in/test-creator/recent-activity/all/", body, "Test Creator | Activity | LinkedIn")
    return page, [p for b in pages.sent(page, "/api/v1/self/posts/ingest") for p in b["posts"]]


def test_a_repost_is_never_sent_as_your_post(pages):
    _, posts = _posts(pages)
    repost = [p for p in posts if p["activity_urn"] == "urn:li:activity:7386000000000000005"]
    assert repost and repost[0]["actor"] != "test-creator"
    own = [p for p in posts if p["activity_urn"] == "urn:li:activity:7386000000000000006"]
    assert own and own[0]["actor"] == "test-creator"


def test_a_repost_header_alone_marks_a_repost(pages):
    # No author link at all: the header is the only sign.
    body = POSTS.replace('<div><a href="https://www.linkedin.com/in/stranger-author/"><span>Stranger Author</span></a><span>Founder at Northwind</span></div>', "")
    _, posts = _posts(pages, body)
    repost = [p for p in posts if p["activity_urn"] == "urn:li:activity:7386000000000000005"]
    assert repost and repost[0]["actor"] != "test-creator"


def test_a_repost_whose_header_links_the_creator_is_still_a_repost(pages):
    body = POSTS.replace("<div><span>Test Creator reposted this</span></div>",
                         '<div><a href="https://www.linkedin.com/in/test-creator/">Test Creator</a> reposted this</div>')
    _, posts = _posts(pages, body)
    repost = [p for p in posts if p["activity_urn"] == "urn:li:activity:7386000000000000005"]
    assert repost and repost[0]["actor"] == "stranger-author"


def test_cards_whose_author_cannot_be_read_report_drift(pages):
    body = POSTS.replace('<a href="https://www.linkedin.com/in/test-creator/"><span>Test Creator</span></a>', "<span>Test Creator</span>") \
        .replace('<a href="https://www.linkedin.com/in/stranger-author/"><span>Stranger Author</span></a>', "<span>Stranger Author</span>")
    page, _ = _posts(pages, body)
    captures = [c for c in pages.sent(page, "/api/v1/bridge/capture") if c["extractor"] == "activity_posts"]
    assert captures and captures[0]["drift"] == ["post_author"]


def test_a_ugcpost_id_is_kept_as_linkedin_names_it(pages):
    _, posts = _posts(pages)
    urns = {p["activity_urn"] for p in posts}
    assert "urn:li:activity:7386000000000000777" not in urns
    assert "urn:li:ugcPost:7386000000000000777" in urns


def test_a_cards_activity_id_is_preferred_to_its_ugcpost_id(pages):
    body = POSTS.replace(
        '<div data-testid="expandable-text-box">A document post',
        '<a href="https://www.linkedin.com/feed/update/urn:li:activity:7386000000000000900/">1w</a>'
        '<div data-testid="expandable-text-box">A document post')
    _, posts = _posts(pages, body)
    urns = {p["activity_urn"] for p in posts}
    assert "urn:li:activity:7386000000000000900" in urns
    assert not [u for u in urns if u.endswith("7386000000000000777")]


COUNTED = """
<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000041">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text"><span>We just crossed 10,000 impressions on one post!</span></div>
   <span class="social-details-social-counts__reactions-count">57</span>
   <button aria-label="9 comments">9 comments</button>
   <span>2 reposts</span>
   <a href="/analytics/post-summary/urn:li:activity:7386000000000000041/"><span>1,912 impressions</span></a>
 </div>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000042">
   <div class="update-components-actor"><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div class="update-components-text"><span>My last post got 48,000 impressions and 310 comments.</span></div>
   <span class="social-details-social-counts__reactions-count">12</span>
 </div>
</main>"""
