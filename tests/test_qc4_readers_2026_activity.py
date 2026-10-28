"""
The Activity reader on LinkedIn's 2026 Activity list (2.10.1).
=============================================================

On the owner's own Activity page (2026-10-28) the posts reader ran once,
2.5 s after the route change, found no card and logged items_seen 0, while
the card stamper saw 38 cards a second later: the list is a LazyColumn
(data-testid "ProfileRecentActivityAll-<vanity>", role "list") that fills
after the route settles. Each post is a div[data-urn] whose id starts
"expanded" and ends "FeedType_"; its words are the expandable text box; the
comment and repost counts are the bare figure inside the buttons named
"Comment" and "Repost"; "6 reactions" and "499 impressions" are plain text.

The fixtures are rebuilt from the owner's sanitised outline (element types,
stable attributes, label and figure words) with invented text and an
invented vanity, and run the shipped scripts in headless Chromium through
qc_f3_pages.py.
"""

import json

import pytest

ME = "ada-example"
SCRIPTS = ("content.js", "own_pages.js", "own_insights.js")


@pytest.fixture(scope="module")
def pages():
    # Imported here, so a run without a browser skips these and nothing else.
    pytest.importorskip("playwright.sync_api")
    from qc_f3_pages import Pages
    p = Pages()
    yield p
    p.close()


def page_html(body, title, lang="en"):
    from qc_f3_pages import page_html as html
    return html(body, title=title, lang=lang)


def _captures(pages, page, extractor):
    return [c for c in pages.sent(page, "/api/v1/bridge/capture") if c.get("extractor") == extractor]


def _post_2026(n, words, comments="2", reposts="1", reactions="6 reactions", impressions="499 impressions",
               more=True, comment_tools=""):
    rest = ("<br>A second line of it.<button data-testid=\"expandable-text-button\"><span><span><span>&hellip;</span>"
            "<span>more</span></span></span></button>") if more else ""
    return f"""
<div><div><div data-urn="urn:li:activity:739100000000000000{n}" componentkey="p{n}" id="expandedQUJD{n}RkVFRA==FeedType_">
  <div role="listitem" componentkey="li{n}">
    <div>
      <div componentkey="hd{n}">
        <h2><span>Feed post</span><span></span></h2>
        <div>
          <div><div><a componentkey="av{n}" href="https://www.linkedin.com/in/{ME}/"><figure componentkey="f{n}"><svg role="img" aria-label="View profile"></svg><img alt=""></figure></a></div></div>
          <div><div><div><div><a componentkey="nm{n}" href="https://www.linkedin.com/in/{ME}/"><div componentkey="nn{n}"><div></div></div></a></div></div>
            <div><p><span>Ada Example</span></p></div><div><div></div></div>
            <div><p componentkey="ag{n}"><span>1w &bull;</span></p></div></div></div>
        </div>
        <button aria-label="Open the control menu for this post" componentkey="mn{n}"><span><svg></svg></span></button>
      </div>
      <p componentkey="tx{n}"><span data-testid="expandable-text-box">{words}{rest}</span></p>
      <div>
        <div><div><div><button aria-label="React with a like" componentkey="lk{n}"><span><svg></svg><div><span></span></div></span></button></div>
          <button aria-label="Open reactions menu"><span><svg></svg></span></button></div>
          <button aria-label="Comment" componentkey="cm{n}"><span><svg></svg><div><span><span><span>{comments}</span></span></span></div></span></button>
          <button aria-label="Repost" componentkey="rp{n}"><span><svg></svg><div><span><span><span>{reposts}</span></span></span></div></span></button>
          <a aria-label="Send" componentkey="sd{n}"><span><svg></svg><div><span><span><span></span></span></span></div></span></a>
          <div></div>
          <a componentkey="rc{n}"><div>{reactions}</div><div componentkey="rl{n}"><ul role="presentation"><li><svg></svg></li></ul></div></a>
        </div>
      </div>
    </div>
    <div><div><svg></svg><div><p>{impressions}</p><div><a componentkey="va{n}"><p componentkey="vp{n}"><span>View analytics</span><span>of this post</span></p></a></div></div></div>
      <div><a componentkey="cs{n}"><span><span>Share</span></span></a></div></div>
    <div componentkey="ct{n}" id="QUJD{n}-replaceableCommentToolsQUJD">{comment_tools}</div>
    <div></div>
  </div>
</div></div></div>"""


def _activity_page(posts, fill_after_ms=3500):
    rows = "".join(posts)
    return f"""<main>
<aside aria-label="Profile"><div><div><div><p>Followers</p><a><p>1,234</p></a></div></div></div></aside>
<section aria-label="All activity">
 <div><div componentkey="ac"><div><div><h2>All activity</h2></div>
  <nav><ul><li><a><span><span>Posts</span></span></a></li><li><a><span><span>Comments</span></span></a></li>
           <li><a><span><span>Videos</span></span></a></li><li><a><span><span>Reactions</span></span></a></li></ul></nav>
  <div><div><div data-testid="ProfileRecentActivityAll-{ME}" data-component-type="LazyColumn" role="list" componentkey="lc">
    <div><div></div></div>
  </div></div></div>
 </div></div></div>
</section></main>
<script>
  setTimeout(() => {{
    document.querySelector('[data-component-type="LazyColumn"]').insertAdjacentHTML("beforeend", {json.dumps(rows)});
  }}, {fill_after_ms});
</script>"""


def _activity(pages, body, run=10000):
    page = pages.open(f"/in/{ME}/recent-activity/all/", page_html(body, title="Ada Example | Activity", lang="en"),
                      scripts=SCRIPTS, me=ME)
    page.clock.run_for(run)
    posts = {p["activity_urn"]: p for b in pages.sent(page, "/api/v1/self/posts/ingest") for p in b["posts"]}
    return page, posts


def test_the_activity_reader_waits_for_the_lazy_list_and_reads_each_2026_post(pages):
    page, posts = _activity(pages, _activity_page([
        _post_2026(1, "Shipping small changes often keeps a team honest."),
        _post_2026(2, "What we learned from a slow release.", comments="14", reposts="", reactions="31 reactions",
                   impressions="2,204 impressions"),
    ]))
    first, second = posts["urn:li:activity:7391000000000000001"], posts["urn:li:activity:7391000000000000002"]
    assert first["actor"] == ME
    assert first["text"].startswith("Shipping small changes often keeps a team honest.\nA second line of it.")
    assert (first["reactions"], first["comments"], first["reposts"], first["impressions"]) == (6, 2, 1, 499)
    assert (second["reactions"], second["comments"], second["reposts"], second["impressions"]) == (31, 14, None, 2204)
    reports = _captures(pages, page, "activity_posts")
    assert reports and reports[0]["items_seen"] == 2, "the first report waited for the cards"


def test_cards_that_arrive_after_the_first_read_are_read_too(pages):
    late = _post_2026(3, "A third post that the list renders later.")
    body = _activity_page([_post_2026(1, "Shipping small changes often keeps a team honest.")]).replace(
        "</script>", f"""setTimeout(() => {{
    document.querySelector('[data-component-type="LazyColumn"]').insertAdjacentHTML("beforeend", {json.dumps(late)});
  }}, 6500);
</script>""")
    _page, posts = _activity(pages, body, run=14000)
    assert {"urn:li:activity:7391000000000000001", "urn:li:activity:7391000000000000003"} <= set(posts)


def test_a_post_whose_own_words_are_a_count_is_not_its_count(pages):
    # The post's whole text is a count, so the paragraph holding it reads as
    # one: skipped because it holds the post's words (BRIDGE-25, again).
    _page, posts = _activity(pages, _activity_page([
        _post_2026(4, "500 impressions", more=False, impressions="1,050 impressions")]))
    assert posts["urn:li:activity:7391000000000000004"]["impressions"] == 1050


def test_a_line_that_only_starts_with_a_count_is_not_the_cards_count(pages):
    # No impressions line on this card (LinkedIn shows none on a repost);
    # somebody's sentence further down is not one.
    _page, posts = _activity(pages, _activity_page([
        _post_2026(5, "A post of mine.", impressions="", comment_tools="<p>500 impressions in a day, wow</p>")]))
    assert posts["urn:li:activity:7391000000000000005"]["impressions"] is None


def test_a_list_with_rows_none_of_which_is_a_post_reports_drift(pages):
    body = _activity_page([]).replace("<div><div></div></div>\n  </div>",
                                      "<div><div><p>Something LinkedIn has not shown before</p></div></div>\n  </div>")
    page, posts = _activity(pages, body, run=20000)
    assert posts == {}
    report = _captures(pages, page, "activity_posts")[-1]
    assert report["drift"] == ["post_cards"] and report["items_seen"] == 1 and report["items_kept"] == 0


def test_a_list_that_never_fills_is_read_as_empty_not_as_drift(pages):
    page, posts = _activity(pages, _activity_page([]), run=20000)
    assert posts == {}
    reports = _captures(pages, page, "activity_posts")
    assert reports and reports[-1]["items_seen"] == 0 and not reports[-1]["drift"]
