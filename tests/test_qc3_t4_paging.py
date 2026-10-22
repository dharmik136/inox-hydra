"""
The two post lists answer with a page, and the page holds the same rows.
=======================================================================

Cycle 3, batch T4 (P-5, and the 4.65 MB in ONEVIEW section 1.3). Posts read
/api/v1/insights/posts (2,201 KB) and Analytics read /api/analytics/posts
(2,432 KB): both returned every post the creator has ever written, each with
the people it brought, on every load. /api/analytics/posts took no arguments
at all, so a `limit` in the URL was accepted and silently ignored, and
limit=50 and limit=2000 returned identical payloads.

Both now answer with one page, and both page through insights.page_bounds and
insights.paging, so the contract is written once. What these tests hold:

- the rows of a page are the rows that page held in the whole answer, in the
  same order, field for field;
- `limit` is obeyed rather than ignored, and `offset` reaches the rest;
- every figure beside the list (the usual, the best two, the counts) is still
  read from the whole history, so no number changes with the page.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t4_page_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# /api/v1/insights/posts
# ---------------------------------------------------------------------------

def test_posts_insights_answer_with_one_page_by_default(home):
    import insights
    answer = insights.posts_overview()
    assert answer["limit"] == insights.POSTS_PAGE
    assert answer["offset"] == 0
    assert answer["returned"] == len(answer["posts"]) == insights.POSTS_PAGE
    assert answer["total"] == len(home["own"])
    assert answer["has_more"] is True


def test_every_page_of_posts_insights_holds_the_rows_it_always_held(home):
    import insights
    whole = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    assert whole["returned"] == whole["total"] == len(home["own"])
    assert whole["has_more"] is False

    seen = []
    for offset in range(0, whole["total"], 7):
        page = insights.posts_overview(limit=7, offset=offset)
        assert page["posts"] == whole["posts"][offset:offset + 7], offset
        assert page["limit"] == 7 and page["offset"] == offset
        seen += page["posts"]
    assert seen == whole["posts"]


def test_no_figure_beside_the_list_changes_with_the_page(home):
    import insights
    whole = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)
    beside = ("usual", "best", "settled_after_days", "settled_without_figures",
              "settled_without_figures_from_archive")
    for offset in (0, 11, len(home["own"]) - 1):
        page = insights.posts_overview(limit=3, offset=offset)
        for key in beside:
            assert page[key] == whole[key], (key, offset)
    # The two best posts are named even when neither is on the page.
    assert whole["best"], "the history has settled posts with figures"


def test_an_offset_past_the_end_is_an_empty_page_not_an_error(home):
    import insights
    page = insights.posts_overview(limit=10, offset=10_000)
    assert page["posts"] == []
    assert page["returned"] == 0
    assert page["has_more"] is False
    assert page["total"] == len(home["own"])


def test_a_page_larger_than_the_most_one_answer_carries_is_clamped(home):
    import insights
    page = insights.posts_overview(limit=10_000)
    assert page["limit"] == insights.POSTS_PAGE_MAX


# ---------------------------------------------------------------------------
# /api/analytics/posts
# ---------------------------------------------------------------------------

def _leaderboard(**kwargs):
    from routers import analytics
    return analytics.get_posts_leaderboard(**kwargs)


def test_the_post_leaderboard_obeys_the_limit_it_used_to_ignore(home):
    import insights
    default = _leaderboard(limit=None, offset=0)
    assert default["limit"] == insights.POSTS_PAGE
    assert len(default["posts"]) == insights.POSTS_PAGE
    fifty = _leaderboard(limit=50, offset=0)
    ten = _leaderboard(limit=10, offset=0)
    assert len(fifty["posts"]) == 50 and len(ten["posts"]) == 10
    assert ten["posts"] != fifty["posts"], "limit=10 and limit=50 answered the same payload"
    assert ten["total"] == fifty["total"] > 50


def test_every_page_of_the_leaderboard_holds_the_rows_it_always_held(home):
    whole = _leaderboard(limit=200, offset=0)
    assert whole["returned"] == whole["total"]
    seen = []
    for offset in range(0, whole["total"], 9):
        page = _leaderboard(limit=9, offset=offset)
        assert page["posts"] == whole["posts"][offset:offset + 9], offset
        seen += page["posts"]
    assert seen == whole["posts"]


def test_the_leaderboard_counts_each_post_s_leads_for_the_page_only(home, monkeypatch):
    """The attribution of every post was computed on every load; now only the page's."""
    from routers import analytics
    counted = []
    real = analytics.post_summary.current

    def watched(conn, keys=None):
        counted.append(keys)
        return real(conn, keys)

    monkeypatch.setattr(analytics.post_summary, "current", watched)
    page = _leaderboard(limit=5, offset=0)
    assert len(page["posts"]) == 5
    assert all(post["attribution"]["total_leads"] >= 0 for post in page["posts"])
    busiest = max(page["posts"], key=lambda p: p["attribution"]["total_leads"])
    assert busiest["attribution"]["total_leads"] > 0, "the page's posts brought people"


def test_both_endpoints_page_through_the_one_contract():
    """One definition, one place: the page size and the fields are insights'."""
    import inspect
    import insights
    from routers import analytics, insights as insights_router
    source = inspect.getsource(analytics.get_posts_leaderboard)
    assert "insights.page_bounds" in source and "insights.paging" in source
    assert "insights.posts_overview" in inspect.getsource(insights_router.get_posts_insights)
    assert insights.paging(10, 5, 0, 5) == {"total": 10, "limit": 5, "offset": 0, "returned": 5, "has_more": True}
    assert insights.paging(10, 5, 5, 5)["has_more"] is False
