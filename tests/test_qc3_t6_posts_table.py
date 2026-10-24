"""
Posts is a table, and the screens read the one engine rather than their page.
============================================================================

Cycle 3, batch T6 (sections B: Posts, Analytics, Patterns), and the two
review findings against the state T4 left:

1. T4 gave /api/v1/insights/posts a page of 50 and the Posts screen showed
   those 50 of 1,417 with no control that reached the rest. The table now
   sorts, filters and searches the whole history and pages through it, with
   the count on screen; these tests hold that a sort reaches the post that
   is not on page one, that a filter and a search move the count the screen
   prints, and that nothing beside the table (the usual, the best two) is
   computed from a page, a filter or a search.
2. AnalyticsSurface picked its "strongest post" out of the rows its page had
   fetched. /api/analytics/posts answers with results.best over the whole
   history, and these tests hold that the answer does not move with the page.

Plus the UI side of "one definition, one place": the backend guard
(test_results_is_one_number.py) reads Python, so these read the three screens
of this batch and fail if one of them works out settled, qualified or best
for itself rather than printing what the engine said.
"""

import os
import re
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402

UI = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")
SCREENS = ("PostsSurface.tsx", "AnalyticsSurface.tsx", "PatternsSurface.tsx", "PostDetail.tsx")


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t6_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _source(name):
    with open(os.path.join(UI, name), encoding="utf-8") as handle:
        return handle.read()


# ---------------------------------------------------------------------------
# The table: sorted, filtered, searched, and paged through the whole history
# ---------------------------------------------------------------------------

def test_sorting_by_a_metric_reaches_the_post_that_is_not_on_page_one(home):
    """
    A sort is of the whole history, not of the page.

    Sorting the fifty rows a page had already fetched is how the screen came
    to name the best post on page one: the creator's actual top post is
    usually somewhere else entirely.
    """
    import insights
    import results
    from database import get_db
    page_size = 5

    # The creator's strongest post is one of their oldest, which is where a
    # three year history usually keeps it: nothing on the newest-first page
    # the screen opens on can reach it.
    oldest_read = next(p for p in insights.posts_overview(limit=insights.POSTS_PAGE_MAX, sort="oldest")["posts"]
                       if p["reactions"] is not None)
    conn = get_db()
    with conn:
        conn.execute("UPDATE post_metric_observations SET reactions = 9999 WHERE activity_urn = ?",
                     (oldest_read["activity_urn"],))
        conn.execute("UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = ?",
                     (oldest_read["activity_urn"],))
    conn.close()
    results.forget_cache()

    newest_page = insights.posts_overview(limit=page_size)["posts"]
    assert oldest_read["activity_urn"] not in [p["activity_urn"] for p in newest_page]

    first_page = insights.posts_overview(limit=page_size, sort="reactions")
    assert first_page["sort"] == "reactions"
    assert first_page["posts"][0]["activity_urn"] == oldest_read["activity_urn"]
    assert first_page["posts"][0]["reactions"] == 9999
    everything = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    read = [p for p in everything["posts"] if p["reactions"] is not None]
    assert len(read) > page_size, "the history is longer than one page"
    # Descending, and a post whose reactions were never read is last rather
    # than being ranked as a zero.
    values = [p["reactions"] for p in first_page["posts"]]
    assert values == sorted(values, reverse=True)

    tail = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, sort="reactions")
    assert tail["posts"][-1]["reactions"] is None or tail["posts"][-1]["reactions"] == min(
        p["reactions"] for p in read)


def test_the_newest_first_page_is_still_the_page_it_always_held(home):
    """T4's contract: the default order and the default page do not move."""
    import insights
    default = insights.posts_overview()
    assert default["sort"] == "newest"
    assert default["limit"] == insights.POSTS_PAGE
    assert default["total"] == len(home["own"])
    dates = [p["published_at"] for p in default["posts"]]
    assert dates == sorted(dates, reverse=True)
    second = insights.posts_overview(limit=insights.POSTS_PAGE, offset=insights.POSTS_PAGE)
    assert second["offset"] == insights.POSTS_PAGE
    assert not {p["activity_urn"] for p in second["posts"]} & {p["activity_urn"] for p in default["posts"]}


def test_oldest_first_is_the_other_end_of_the_same_list(home):
    import insights
    newest = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, sort="newest")
    oldest = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, sort="oldest")
    assert [p["activity_urn"] for p in oldest["posts"]] == [p["activity_urn"] for p in newest["posts"]][::-1]


def test_the_settle_filter_moves_the_count_the_screen_prints(home):
    """
    "50 of 1,417" has to be 50 of what the filter left, or the pager walks
    past the end of a shorter list.
    """
    import insights
    everything = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    settled = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, settled_state="settled")
    growing = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, settled_state="growing")
    assert settled["settled_state"] == "settled"
    assert all(p["settled"] for p in settled["posts"])
    assert all(not p["settled"] for p in growing["posts"])
    assert settled["total"] + growing["total"] == everything["total"]
    assert settled["total"] == len(settled["posts"])


def test_a_search_narrows_the_table_and_its_count(home):
    import insights
    answer = insights.posts_overview(limit=insights.POSTS_PAGE_MAX, q="sourdough")
    assert answer["q"] == "sourdough"
    assert answer["total"] == len(answer["posts"])
    assert answer["posts"], "the seeded history mentions sourdough"
    everything = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    assert answer["total"] < everything["total"]
    # A search nothing matches is an empty table, not an error and not every post.
    nothing = insights.posts_overview(q="chrysanthemum-pricing-sourdough")
    assert nothing["posts"] == [] and nothing["total"] == 0 and nothing["has_more"] is False


def test_a_search_for_a_wildcard_searches_for_that_character(home):
    """
    LIKE reads % and _ as wildcards, so a creator searching for "50%" would
    have matched every post they have ever written.
    """
    import insights
    everything = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    assert everything["total"] > 0, "the seeded history holds posts"
    assert not any("%" in (p["excerpt"] or "") for p in everything["posts"]), "no seeded post holds a per cent sign"
    for wildcard in ("%", "_"):
        answer = insights.posts_overview(q=wildcard)
        assert answer["total"] == 0, f"LIKE read the creator's {wildcard} as a wildcard"


def test_nothing_beside_the_table_is_computed_from_the_sort_the_filter_or_the_search(home):
    """
    The creator's usual and the two posts worth repurposing are the whole
    history's, whichever rows the table is showing. A median of the posts a
    search happened to match is a different number, not the same number
    read faster.
    """
    import insights
    beside = ("usual", "best", "worst", "metric", "ranked_posts", "settled_after_days",
              "settled_without_figures", "settled_without_figures_from_archive")
    whole = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    for narrowed in (insights.posts_overview(sort="reactions", limit=3),
                     insights.posts_overview(settled_state="growing", limit=3),
                     insights.posts_overview(q="pricing", limit=3),
                     insights.posts_overview(limit=3, offset=17)):
        for key in beside:
            assert narrowed[key] == whole[key], key


def test_an_unknown_sort_or_filter_is_the_default_not_an_error(home):
    import insights
    answer = insights.posts_overview(sort="whatever", settled_state="maybe")
    assert answer["sort"] == "newest" and answer["settled_state"] is None
    assert answer["total"] == len(home["own"])


def test_a_row_carries_reach_and_response_as_a_pair_and_a_settle_state(home):
    """Both numbers of the pair, or neither, and the settle state per post."""
    import insights
    answer = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    paired = [p for p in answer["posts"] if p["reach_and_response"]]
    assert paired, "the seeded history has readings at comparable ages"
    for post in paired:
        pair = post["reach_and_response"]
        assert pair["reach"]["percentile"] is not None and pair["response"]["percentile"] is not None
        assert pair["posts_compared"] >= 3 and pair["shape"]
    assert all(isinstance(p["settled"], bool) for p in answer["posts"])
    assert answer["settled_after"]["measured"] in (True, False)


# ---------------------------------------------------------------------------
# One post opens into its detail, rather than the table rendering everything
# ---------------------------------------------------------------------------

def test_one_post_opens_into_its_whole_text(home):
    """
    The table carries a 140 character excerpt per row; the detail carries the
    post. Rendering every post's whole text down one column is what made the
    screen 324,344 characters and 176 screens tall.
    """
    import insights
    row = insights.posts_overview(limit=1, sort="reactions")["posts"][0]
    detail = insights.post_detail(row["activity_urn"])
    assert detail is not None
    assert detail["text"] and len(detail["text"]) >= len(row["excerpt"] or "")
    assert detail["text"].startswith("Post ")
    # The excerpt is one line of the text with its whitespace folded; the
    # detail keeps the post as it was written.
    assert "\n" in detail["text"] and "\n" not in (row["excerpt"] or "")


def test_the_detail_and_the_row_answer_from_the_one_engine(home):
    import insights
    for row in insights.posts_overview(limit=6, sort="impressions")["posts"]:
        detail = insights.post_detail(row["activity_urn"])
        for field in ("reactions", "comments", "reposts", "impressions", "figures_source",
                      "settled", "against_usual", "reach_and_response"):
            assert detail[field] == row[field], (row["activity_urn"], field)


def test_the_detail_never_prints_a_rate_it_cannot_measure(home):
    """
    A rate the engine refuses comes back as None with the reason named, so
    the screen says it rather than printing 116.25%.
    """
    import results
    from database import get_db
    import insights
    urn = insights.posts_overview(limit=1, sort="reactions")["posts"][0]["activity_urn"]
    conn = get_db()
    with conn:
        # One reading in which reactions exceed impressions, which is what
        # two capture sources read in the same hour produced.
        conn.execute("UPDATE post_metric_observations SET reactions = impressions + 40 "
                     "WHERE activity_urn = ? AND observed_at = (SELECT MAX(observed_at) FROM "
                     "post_metric_observations WHERE activity_urn = ?)", (urn, urn))
        conn.execute("UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = ?", (urn,))
    conn.close()
    results.forget_cache()
    detail = insights.post_detail(urn)
    assert detail["engagement_rate"] is None
    assert detail["engagement_rate_unmeasured"] == "more_engagements_than_impressions"
    assert "different readings" in detail["engagement_rate_note"]


def test_a_post_the_studio_does_not_hold_is_not_invented(home):
    import insights
    from fastapi import HTTPException
    from routers import insights as insights_router
    assert insights.post_detail("urn:li:activity:0") is None
    with pytest.raises(HTTPException) as raised:
        insights_router.get_post_detail("urn:li:activity:0")
    assert raised.value.status_code == 404


# ---------------------------------------------------------------------------
# Analytics: best is the engine's, over the whole history
# ---------------------------------------------------------------------------

def _leaderboard(**kwargs):
    from routers import analytics
    return analytics.get_posts_leaderboard(**kwargs)


def test_the_strongest_post_does_not_move_with_the_page(home):
    """
    Review finding 2. The aside beside the table took the highest engagement
    rate out of the rows the page had fetched, so after T4's paging it named
    the best post on page one.
    """
    pages = [_leaderboard(limit=10, offset=offset) for offset in (0, 10, 30)]
    named = {tuple(page["best"]["best"]) for page in pages}
    assert len(named) == 1, "the best post changed with the page"
    best = pages[0]["best"]
    assert best["best"], "the history has settled posts with figures"
    # It rests on the whole history, and says so.
    assert best["ranked_posts"] > 10 and best["settled_posts"] >= best["ranked_posts"]
    assert best["metric"] == "reactions"
    # The named post's figures travel with the answer, because it is usually
    # not one of the rows the page holds.
    for urn in best["best"] + best["worst"]:
        assert urn in best["named"]
        figures = best["named"][urn]
        assert figures["reactions"] is not None and figures["against_usual"]


def test_the_comparison_table_names_the_order_it_is_actually_in(home):
    """
    The count beside the table read "best first" while the route orders by
    impressions, so the table opened on the most seen post and the engine's
    panel four inches to its right named a different one as best. One screen,
    two answers to which post is best, which is the thing this cycle removes.

    The two orders are by different metrics by design: the table is what the
    creator has been shown most, the engine's ranking is reactions against
    their own median. So the label has to name the one it is over.
    """
    page = _leaderboard(limit=14, offset=0)
    seen = [post["impressions"] for post in page["posts"] if post["impressions"] is not None]
    assert seen == sorted(seen, reverse=True), "the page is not ordered by impressions"
    # A post no impressions were read for sorts after every post that has
    # them, rather than ahead of them as a zero.
    unread = [index for index, post in enumerate(page["posts"]) if post["impressions"] is None]
    assert unread == list(range(len(seen), len(page["posts"]))), "an unmeasured post is ordered as a zero"
    # The engine ranks by another metric entirely, so "best" cannot name this
    # order whichever posts the two happen to agree on.
    assert page["best"]["metric"] == "reactions"

    source = _source("AnalyticsSurface.tsx")
    assert "most seen first" in source, "the count line names the order the rows are in"
    assert "best first" not in source.replace("read \"best first\"", ""), (
        "the screen calls this order by the engine's name for a different one")


def test_the_posts_screen_and_analytics_name_the_same_best_post(home):
    import insights
    from routers import analytics
    screen = insights.posts_overview(limit=5)
    table = analytics.get_posts_leaderboard(limit=5, offset=0)
    assert screen["best"] == table["best"]["best"]
    assert screen["worst"] == table["best"]["worst"]


# ---------------------------------------------------------------------------
# The UI side of one definition, one place
# ---------------------------------------------------------------------------

def test_no_screen_in_this_batch_works_out_settled_or_a_rate_for_itself():
    """
    The backend guard reads Python. These three screens are where the numbers
    are printed, so a settle age, a qualified cut or an engagement rate
    written out here is a second definition the guard cannot see.
    """
    offenders = []
    forbidden = {
        "a settle age of its own": re.compile(r"(7\s*\*\s*24|168\s*\*\s*3600|SETTLED_AFTER)"),
        "a qualified or VIP cut of its own": re.compile(r"(icp_score|score)\s*>=?\s*(60|75|80)"),
        "an engagement rate of its own": re.compile(r"(reactions|engagements)[^\n]{0,40}\*\s*100\s*/"),
        "its own settle test": re.compile(r"age_days\s*[<>]=?\s*\d"),
    }
    for name in SCREENS:
        for number, line in enumerate(_source(name).splitlines(), 1):
            code = line.split("//")[0]
            for what, pattern in forbidden.items():
                if pattern.search(code):
                    offenders.append(f"{name}:{number} writes {what}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_analytics_reads_the_strongest_post_from_the_engine():
    source = _source("AnalyticsSurface.tsx")
    assert "best?.best?.[0]" in source, "the strongest post is the engine's first ranked post"
    # Nothing re-ranks the rows of the page to find a strongest one.
    assert not re.search(r"posts[\s\S]{0,40}\.sort\(", source), "the page's rows are re-ranked on screen"
    assert not re.search(r"engagement_rate[\s\S]{0,30}(Math\.max|reduce\()", source)
    # The impossible rate is named rather than printed.
    assert "more_engagements_than_impressions" in source


def test_the_posts_screen_shows_the_count_and_a_control_that_reaches_the_rest():
    """Review finding 1: 50 of 1,417 with nothing to reach the rest."""
    source = _source("PostsSurface.tsx")
    assert "data.total" in source, "the count of matching posts is on screen"
    assert 'aria-label="Previous page"' in source and 'aria-label="Next page"' in source
    assert "has_more" in source, "Next stops at the end of the list"
    # Native buttons, so the pager is keyboard reachable without a tabindex.
    assert source.count('type="button"') >= 5
    # The table is a table, not a column of cards.
    assert "<table" in source and "<thead" in source and "scope=\"col\"" in source
    # A row opens the detail view rather than rendering the post inline.
    assert "PostDetail" in source and "activityUrn" in source


def test_patterns_says_no_difference_plainly_and_has_more_than_two_controls():
    source = _source("PatternsSurface.tsx")
    assert "No difference your own posts can separate" in source
    # The "none" verdict is its own section, not a ranked line in the findings.
    assert 'verdict(p) === "none"' in source and 'verdict(p) !== "none"' in source
    # Controls: the order of the findings, a disclosure per line, and the
    # attribution table's sortable columns. The screen had two.
    assert source.count('type="button"') >= 3
    assert "aria-pressed" in source and "aria-expanded" in source and "aria-sort" in source


def test_the_three_screens_keep_the_repo_rules():
    for name in SCREENS:
        source = _source(name)
        assert "\u2014" not in source, f"{name} has an em-dash"
        assert source.count("<h1") <= 1, f"{name} has more than one h1"
        assert source.count("style={{") <= 7, f"{name} has more than seven inline styles"
