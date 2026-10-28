"""
The phase 2 readers on fixture pages: what each sends, and what it never does.
==============================================================================

Cycle 4, track 5, phase 2. These run the shipped scripts in headless
Chromium (see qc_f3_pages.py) with own_insights.js loaded after the others,
as the manifest loads it. Every page's markup and labels are unverified
against 2026 pages, so each reader sends only what it can read without
guessing, a count only with the window its page names, and nothing about
another member: a viewer's or a searcher's name, headline, company or
profile link is never sent.
"""

import json

import pytest

from qc_f3_pages import Pages, page_html

SCRIPTS = ("content.js", "own_pages.js", "own_insights.js")
SIGNED_IN = {"signedInVanity": "test-creator"}
FIGURES = "/api/analytics/page-figures"


@pytest.fixture(scope="module")
def pages():
    p = Pages()
    yield p
    p.close()


def _read(pages, path, body, run=4000):
    page = pages.open(path, page_html(body, title="LinkedIn", lang="en"), scripts=SCRIPTS, storage=SIGNED_IN)
    page.clock.run_for(run)
    return page


def _sent(pages, page):
    return pages.sent(page, FIGURES)


def _card(label, figure, extra=""):
    return f'<li class="card"><p class="figure">{figure}</p><p class="label">{label}</p>{extra}</li>'


# ---------------------------------------------------------------------------
# The analytics dashboard: profile views, search appearances, new followers
# ---------------------------------------------------------------------------

DASHBOARD = """<main><ul>
  <li><h2>Profile viewers</h2><p>412</p><p>Past 90 days</p></li>
  <li><h2>Search appearances</h2><p>1.2K</p><p>Past 7 days</p></li>
  <li><h2>Post impressions</h2><p>9,000</p><p>Past 7 days</p></li>
</ul>
<section><h3>New followers</h3>
  <div role="img" aria-label="New followers chart">
    <span aria-label="Oct 20, 2026: 12 new followers"></span>
    <span aria-label="Oct 21, 2026: 9 new followers"></span>
    <span aria-label="Most viewed: 3 posts"></span>
  </div>
</section></main>"""


def test_the_dashboard_sends_each_account_figure_with_its_own_window(pages):
    page = _read(pages, "/dashboard/", DASHBOARD)
    sent = _sent(pages, page)
    assert len(sent) == 1, sent
    body = sent[0]
    assert body["author"] == "test-creator" and body["page"] == "account_analytics"
    readings = {r["period_label"]: r for r in body["readings"]}
    assert readings["90d"]["figures"] == {"profile_views": 412} and readings["90d"]["precision"] == "exact"
    assert readings["7d"]["figures"] == {"search_appearances": 1200} and readings["7d"]["precision"] == "rounded"
    assert body["points"] == [
        {"date": "2026-10-20", "figure": "new_followers", "value": 12, "precision": "exact"},
        {"date": "2026-10-21", "figure": "new_followers", "value": 9, "precision": "exact"},
    ]


def test_a_count_whose_window_cannot_be_read_is_not_sent(pages):
    page = _read(pages, "/analytics/creator/audience/", """<main><ul>
      <li><h2>Profile viewers</h2><p>412</p></li></ul></main>""")
    assert _sent(pages, page) == [], "a count with no window it names is not a figure the studio can keep"


# ---------------------------------------------------------------------------
# Who viewed your profile, and search appearances: counts and windows only
# ---------------------------------------------------------------------------

PROFILE_VIEWS = """<main><h1>Who viewed your profile</h1>
  <section><p>412</p><p>Profile viewers in the past 90 days</p></section>
  <ul>
    <li><a href="https://www.linkedin.com/in/stranger-one/"><span>Stranger One</span></a><span>Founder at Acme</span></li>
    <li><span>Someone at Northwind</span><span>Viewed 2 days ago</span></li>
  </ul></main>"""


def test_the_profile_views_page_sends_the_count_and_its_window_and_no_viewer(pages):
    page = _read(pages, "/me/profile-views/", PROFILE_VIEWS)
    sent = _sent(pages, page)
    assert [(b["page"], b["readings"]) for b in sent] == [
        ("profile_views", [{"period_label": "90d", "precision": "exact", "figures": {"profile_views": 412}}])]
    every_message = json.dumps(pages.sent(page))
    for other in ("Stranger One", "stranger-one", "Acme", "Northwind"):
        assert other not in every_message, f"{other!r} reached the studio"


def test_the_search_appearances_page_sends_the_count_and_its_window_and_no_searcher(pages):
    page = _read(pages, "/me/search-appearances/", """<main>
      <section><h2>Search appearances</h2><p>57</p><p>Previous week</p></section>
      <section><h3>Where your searchers work</h3><ul><li>Acme Corp</li><li>Northwind</li></ul></section></main>""")
    assert [(b["page"], b["readings"]) for b in _sent(pages, page)] == [
        ("search_appearances", [{"period_label": "7d", "precision": "exact", "figures": {"search_appearances": 57}}])]
    assert "Acme" not in json.dumps(pages.sent(page))


# ---------------------------------------------------------------------------
# Own content: an article and a newsletter
# ---------------------------------------------------------------------------

def test_an_articles_analytics_page_sends_its_figures_by_content(pages):
    path = "/analytics/article/urn:li:linkedInArticle:7390000000000000001/"
    page = _read(pages, path, "<main><ul>" + "".join(_card(label, figure) for label, figure in (
        ("Article views", "900"), ("Reactions", "12"), ("Comments", "3"))) + "</ul></main>")
    sent = _sent(pages, page)
    assert [(b["page"], b["content_urn"]) for b in sent] == [
        ("article_analytics", "urn:li:linkedInArticle:7390000000000000001")]
    assert sent[0]["readings"] == [{"period_label": "", "precision": "exact",
                                    "figures": {"views": 900, "reactions": 12, "comments": 3}}]


def test_a_newsletters_analytics_page_sends_subscribers_sends_and_its_open_rate(pages):
    path = "/analytics/newsletter/urn:li:fsd_contentSeries:7390000000000000002/"
    page = _read(pages, path, """<main><button>Past 28 days</button><ul>""" + "".join(
        _card(label, figure) for label, figure in (
            ("Subscribers", "1.2K"), ("Email sends", "800"), ("Email open rate", "42.5%"))) + "</ul></main>")
    sent = _sent(pages, page)
    assert sent[0]["page"] == "newsletter_analytics"
    assert sent[0]["readings"] == [{"period_label": "28d", "precision": "rounded",
                                    "figures": {"subscribers": 1200, "email_sends": 800, "email_open_rate_pct": 42.5}}]


def test_an_unknown_layout_sends_nothing(pages):
    page = _read(pages, "/analytics/article/urn:li:linkedInArticle:7390000000000000003/",
                 "<main><p>Something LinkedIn has not shown before</p><p>42</p></main>")
    assert _sent(pages, page) == []


# ---------------------------------------------------------------------------
# A video's watch time, on its post analytics page
# ---------------------------------------------------------------------------

SEVEN = "".join(_card(label, figure) for label, figure in (
    ("Impressions", "1,912"), ("Members reached", "1,540"), ("Reactions", "57"), ("Comments", "9"),
    ("Reposts", "2"), ("Saves", "4"), ("Sends", "1")))


def test_a_videos_watch_time_is_read_on_its_post_analytics_page(pages):
    page = _read(pages, "/analytics/post-summary/urn:li:activity:7386000000000000501/", "<main><ul>" + SEVEN +
                 _card("Video views", "900") + _card("Watch time", "12h 30m") + _card("Average watch time", "38s") +
                 "</ul></main>")
    metrics = pages.sent(page, "/api/v1/self/posts/analytics")[0]["metrics"]
    assert (metrics["video_views"], metrics["watch_time_seconds"], metrics["average_watch_seconds"]) == (900, 45000, 38)
    capture = [m["body"] for m in pages.sent(page) if m.get("path") == "/api/v1/bridge/capture"][-1]
    assert not capture["drift"], "watch time is a new label: absent or present, never drift"


# ---------------------------------------------------------------------------
# The creator's own Activity tab: their reposts and the edited mark
# ---------------------------------------------------------------------------

ACTIVITY = """<main>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000901">
   <div><span>Test Creator reposted this</span></div>
   <div class="update-components-text"><span>My own words on why this matters.</span></div>
   <div class="nested" data-urn="urn:li:activity:7386000000000000902">
     <a href="https://www.linkedin.com/in/stranger-author/"><span>Stranger Author</span></a>
     <div class="update-components-text"><span>The original author's words.</span></div>
     <span class="social-details-social-counts__reactions-count">300</span>
   </div>
   <button aria-label="4 reactions">4 reactions</button>
 </div>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000903">
   <div><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div><span>1w</span><span> • Edited</span></div>
   <div class="update-components-text"><span>A post I wrote and later fixed.</span></div>
   <span class="social-details-social-counts__reactions-count">20</span>
 </div>
 <div class="feed-shared-update-v2" data-urn="urn:li:activity:7386000000000000904">
   <div><a class="update-components-actor__meta-link" href="https://www.linkedin.com/in/test-creator/">Test Creator</a></div>
   <div><span>2w</span></div>
   <div class="update-components-text"><span>I edited the video for hours before this went out.</span></div>
   <span class="social-details-social-counts__reactions-count">31</span>
 </div>
</main>"""


def _activity(pages):
    page = pages.open("/in/test-creator/recent-activity/all/", page_html(ACTIVITY, title="Test Creator | Activity",
                                                                       lang="en"), scripts=SCRIPTS)
    page.clock.run_for(4000)
    return {p["activity_urn"]: p for b in pages.sent(page, "/api/v1/self/posts/ingest") for p in b["posts"]}


def test_an_own_repost_is_marked_with_its_own_figures_not_the_originals(pages):
    posts = _activity(pages)
    repost = posts["urn:li:activity:7386000000000000901"]
    assert repost["own_repost"] is True
    assert repost["own_figures"]["reactions"] == 4, "300 is the original's, read inside the embedded post"


def test_the_edited_mark_is_read_beside_the_time_and_never_from_the_posts_words(pages):
    posts = _activity(pages)
    assert posts["urn:li:activity:7386000000000000903"].get("edited") is True
    assert "edited" not in posts["urn:li:activity:7386000000000000904"], "the post's own words say edited; the mark does not"
    assert "own_repost" not in posts["urn:li:activity:7386000000000000903"]
