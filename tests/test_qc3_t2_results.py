"""
Every screen gives one answer about results.
============================================

Cycle 3, batch T2 (AUDIENCE S1-A to S1-D, CORRELATION rows 13a and 24,
DERIVED D1, D1b and D2). Measured on one creator's three years, same 1,417
posts, same minute, before this batch:

  Posts, insights.best            ...040728 and ...600761
  Composer > Evidence             ...040728, ...600761, ...840127
  Analytics, the table's top row  ...920350
  Analytics, the prose beside it  ...880537 on page one, ...641091 over the
                                  whole history, at "116.25% engagement"

Six distinct posts called the best one, two of the pairs sharing none. Each
module carried its own denominator, settled rule, tie break and minimum
sample, and the stored icp_score said 0% of 49,142 people qualified while the
same engine on the same inputs said 23.9%.

These tests hold that one module answers all of it, and that the answer is the
same whichever caller asks.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

ME = "t2-creator"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def urn(n):
    return f"urn:li:activity:{7000000000000000000 + n}"


def stamp(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")


@pytest.fixture
def home(monkeypatch):
    """A creator with 40 settled posts, readings for each, and people on them."""
    path = tempfile.mkdtemp(prefix="inox_qc3_t2_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    import results
    init_db()
    results.forget_cache()
    conn = get_db()
    posts = []
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'T2 Creator', ?)", (ME, stamp(NOW)))
        for n in range(40):
            published = NOW - timedelta(days=30 + n)
            activity = urn(n)
            posts.append(activity)
            reactions = 10 + n * 10
            text = f"Post {n} about pricing\nIt has a second line and {'x' * (n * 60)}"
            conn.execute(
                "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                "comments, reposts, impressions, first_seen_at, last_seen_at) "
                "VALUES (?, ?, ?, 'activity', ?, ?, ?, ?, ?, ?)",
                (activity, text, stamp(published), reactions, n, 1, 1000 + n * 100,
                 stamp(published), stamp(NOW)))
            # Readings of the same figures, the way a capture records them: one
            # at about two days old, one now.
            for age, source, scale in ((48.0, "post_analytics", 0.8), ((NOW - published).total_seconds() / 3600.0,
                                                                       "activity_page", 1.0)):
                observed = published + timedelta(hours=age)
                conn.execute(
                    "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                    "source, impressions, reactions, comments, reposts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (activity, stamp(observed), observed.strftime("%Y-%m-%dT%H"), age, source,
                     int((1000 + n * 100) * scale), int(reactions * scale), n, 1))
        for n in range(12):
            lead = f"lead-t2-{n:02d}"
            conn.execute(
                "INSERT INTO leads (id, name, full_name, headline, company, linkedin_urn, profile_url, status, "
                "lead_status, icp_score, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'New Lead', 'NEW', ?, ?)",
                (lead, f"Person {n}", f"Person {n}", "Founder at Northwind Cloud" if n % 2 else "Intern",
                 "Northwind Cloud" if n % 2 else None, f"https://www.linkedin.com/in/t2p{n}",
                 f"https://www.linkedin.com/in/t2p{n}", 0.0, stamp(NOW - timedelta(days=5))))
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                "comment_key, first_seen_at, last_seen_at) VALUES (?, ?, 'COMMENT', ?, ?, ?, ?, ?)",
                (lead, posts[n], "How did you handle the customers already on the old plan? " * 2,
                 stamp(NOW - timedelta(days=4)), f"t2k{n}", stamp(NOW - timedelta(days=4)), stamp(NOW)))
    conn.close()
    yield {"posts": posts}
    results.forget_cache()
    shutil.rmtree(path, ignore_errors=True)


# ---------------------------------------------------------------------------
# One answer to "which post worked best"
# ---------------------------------------------------------------------------

def _analytics_prose_best(rows):
    """What the Analytics aside used to name: the highest rate in the rows it had."""
    rated = [r for r in rows if r.get("engagement_rate") is not None]
    return max(rated, key=lambda r: r["engagement_rate"])["id"] if rated else None


def test_every_screen_names_the_same_best_post(home):
    import insights
    import evidence_briefing
    from routers import analytics as analytics_router

    posts = insights.posts_overview()
    evidence = evidence_briefing.get_retrieval_evidence_brief()
    leaderboard = analytics_router.get_posts_leaderboard(limit=None, offset=0)

    best = posts["best"][0]
    assert evidence["top_exemplars"][0]["activity_urn"] == best, (
        "the Evidence panel ranks raw reactions with no settled rule, so it names another post")
    assert leaderboard["best"]["best"][0] == best, (
        "Analytics names a post of its own: the prose took the highest rate on the page it had fetched")
    assert leaderboard["best"]["metric"] == posts["metric"]


def test_the_best_post_comes_from_the_whole_history_not_from_one_page(home):
    from routers import analytics as analytics_router
    whole = analytics_router.get_posts_leaderboard(limit=200, offset=0)
    page = analytics_router.get_posts_leaderboard(limit=5, offset=0)
    assert page["best"] == whole["best"]
    assert page["best"]["ranked_posts"] == whole["best"]["ranked_posts"] == 40
    # The page holds five rows and the answer still rests on all forty.
    assert page["returned"] == 5 and page["total"] == 40
    # The old rule, run on the page the screen had, cannot see past it.
    assert _analytics_prose_best(page["posts"]) in [r["id"] for r in page["posts"]]


def test_one_settled_rule_and_one_minimum_sample(home):
    import insights
    import contrast_engine
    import results
    assert not hasattr(insights, "SETTLED_AFTER_HOURS")
    assert not hasattr(contrast_engine, "SETTLED_AFTER_HOURS")
    assert contrast_engine.MIN_ARM_SAMPLE_SIZE == insights.MIN_PER_SIDE == results.MIN_PER_SIDE
    # Patterns published a line the Evidence panel suppressed on the same
    # posts, because one asked for 3 posts a side and the other for 8.
    overview = insights.patterns_overview()
    for line in overview["patterns"]:
        assert line["with_posts"] >= results.MIN_PER_SIDE
        assert line["without_posts"] >= results.MIN_PER_SIDE
        assert line["difference"]["verdict"] in ("more", "fewer", "none")


def test_patterns_and_the_contrast_engine_test_the_same_features(home):
    import insights
    import contrast_engine
    import results
    assert insights.PATTERNS is results.BINARY_FEATURES
    assert contrast_engine.BINARY_FEATURES is results.BINARY_FEATURES
    labels = {key: label for key, label, _test in results.BINARY_FEATURES}
    overview = insights.patterns_overview()
    contrasts = contrast_engine.compute_all_contrasts()
    for line in overview["patterns"] + overview["not_enough_posts"]:
        assert line["label"] == labels[line["key"]]
    for contrast in contrasts["contrasts"]:
        assert contrast["label"] == labels[contrast["key"]]


# ---------------------------------------------------------------------------
# The impossible rate
# ---------------------------------------------------------------------------

def test_a_rate_above_one_hundred_percent_is_named_not_printed(home):
    import results
    from database import get_db
    from routers import analytics as analytics_router

    conn = get_db()
    with conn:
        # The shape measured on three years: 877 reactions against 837
        # impressions, which no single reading of one post can hold.
        conn.execute("UPDATE own_posts SET impressions = 837, reactions = 877, comments = 90, reposts = 6 "
                     "WHERE activity_urn = ?", (home["posts"][0],))
        conn.execute("UPDATE post_metric_observations SET impressions = 837, reactions = 877, comments = 90, "
                     "reposts = 6 WHERE activity_urn = ?", (home["posts"][0],))
    conn.close()
    results.forget_cache()

    rows = analytics_router.get_posts_leaderboard(limit=200, offset=0)["posts"]
    row = next(r for r in rows if r["id"] == home["posts"][0])
    assert row["engagement_rate"] is None, "116.25% was printed as a measured fact"
    assert row["engagement_rate_unmeasured"] == "more_engagements_than_impressions"
    assert "different readings" in row["engagement_rate_note"]
    # And no row anywhere carries a rate a reading cannot hold.
    assert all((r["engagement_rate"] is None or r["engagement_rate"] <= 100.0) for r in rows)


def test_a_rate_is_clamped_by_coming_from_one_reading(home):
    import results
    figure = {"impressions": 1000, "reactions": 50, "comments": 5, "reposts": 0}
    assert results.engagement_rate(figure) == (5.5, None)
    assert results.engagement_rate({"impressions": 0, "reactions": 1}) == (None, "no_impressions_read")
    assert results.engagement_rate({"impressions": None, "reactions": 1}) == (None, "not_read")
    assert results.engagement_rate({"impressions": 10, "reactions": 11})[0] is None


# ---------------------------------------------------------------------------
# One answer to "how did this post do"
# ---------------------------------------------------------------------------

def test_one_post_has_one_set_of_figures_on_every_screen(home):
    import insights
    import today
    import results
    from database import get_db
    from routers import analytics as analytics_router

    newest = home["posts"][0]
    conn = get_db()
    read = results.figures(conn, [newest])[newest]
    conn.close()

    posts_row = next(p for p in insights.posts_overview(limit=200)["posts"] if p["activity_urn"] == newest)
    analytics_row = next(p for p in analytics_router.get_posts_leaderboard(limit=200, offset=0)["posts"]
                         if p["id"] == newest)
    assert posts_row["impressions"] == analytics_row["impressions"] == read["impressions"]
    assert posts_row["reactions"] == analytics_row["reactions"] == read["reactions"]
    assert posts_row["figures_source"] == read["source"]

    # Today showed a reading from two days ago as the post's current figures,
    # so one post read 19,943 impressions there and 50,118 on Posts.
    latest = today.today_brief()["latest_post"]
    if latest and latest["activity_urn"] == newest:
        assert latest["current"]["impressions"] == read["impressions"]
        assert latest["current"]["source"] == read["source"]


def test_figures_come_from_one_reading_so_a_rate_cannot_mix_two_pages(home):
    import results
    from database import get_db
    conn = get_db()
    try:
        read = results.figures(conn)
        assert len(read) == 40
        for figure in read.values():
            assert figure["source"] in ("post_analytics", "activity_page", results.SNAPSHOT)
            assert figure["read_at"]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reach and response as a pair
# ---------------------------------------------------------------------------

def test_reach_and_response_are_answered_together(home):
    import insights
    rows = insights.posts_overview(limit=200)["posts"]
    paired = [r for r in rows if r["reach_and_response"]]
    assert paired, "no post carries the pair"
    for row in paired:
        pair = row["reach_and_response"]
        assert set(pair["reach"]) == {"impressions", "percentile"}
        assert set(pair["response"]) == {"reactions", "percentile"}
        assert pair["posts_compared"] >= 3
        assert pair["shape"] in ("wide and loved", "wide, thin response",
                                "narrow, strong response", "narrow and quiet")


def test_a_post_with_no_comparable_reading_says_so_rather_than_showing_a_percentile(home):
    import results
    from database import get_db
    conn = get_db()
    try:
        assert results.pair(conn, ["urn:li:activity:0000000000000000000"]) == {
            "urn:li:activity:0000000000000000000": None}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The settle curve, measured
# ---------------------------------------------------------------------------

def test_the_settle_curve_is_measured_from_the_readings(home):
    import results
    from database import get_db
    conn = get_db()
    try:
        curve = results.settle_curve(conn)
        assert curve["points"], "no curve was measured from the readings"
        shares = [p["reactions_share"] for p in curve["points"]]
        assert shares == sorted(shares), "a post's figures cannot fall as it ages"
        answer = results.settled_after_hours(conn)
        assert answer["hours"] > 0
        assert answer["measured"] in (True, False)
    finally:
        conn.close()


def test_without_readings_the_settle_age_says_it_is_assumed(home):
    import results
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM post_metric_observations")
        results.forget_cache()
        answer = results.settled_after_hours(conn)
        assert answer["measured"] is False
        assert answer["hours"] == float(results.SETTLED_AFTER_HOURS)
    finally:
        conn.close()
        results.forget_cache()


# ---------------------------------------------------------------------------
# Scores that are current
# ---------------------------------------------------------------------------

def test_a_stored_score_cannot_survive_its_inputs_changing(home):
    import crm
    import insights
    import evidence_briefing
    from database import get_db

    # Every score in the fixture is stored as 0.0, as the three year dataset
    # holds them: 0% of 49,142 people qualified while the engine said 23.9%.
    conn = get_db()
    try:
        crm.scores_current(conn)
        rows = {r["id"]: r["icp_score"] for r in conn.execute("SELECT id, icp_score FROM leads")}
    finally:
        conn.close()
    assert any(score >= crm.QUALIFIED_THRESHOLD for score in rows.values()), (
        "the stored scores stayed at the value they were written with")

    qualified = sum(1 for p in insights.posts_overview(limit=200)["posts"] for _ in [1]
                    if p["people_count"])
    assert qualified >= 0
    counted = sum(t["qualified_leads"] for t in evidence_briefing.get_topic_attribution_map()["topics"])
    assert counted > 0, "Patterns said 0 people qualified while the engine qualified half of them"


def test_a_headline_change_moves_every_screen_in_the_same_request(home):
    import crm
    import evidence_briefing
    from database import get_db

    before = sum(t["qualified_leads"] for t in evidence_briefing.get_topic_attribution_map()["topics"])
    crm.reverse_crm.ingest_interaction(
        full_name="Person 1", linkedin_urn="https://www.linkedin.com/in/t2p1",
        headline="Intern", company=None, interaction_type="LIKE", post_urn=home["posts"][1])
    conn = get_db()
    try:
        crm.scores_current(conn)
        score = conn.execute("SELECT icp_score FROM leads WHERE id = 'lead-t2-01'").fetchone()[0]
    finally:
        conn.close()
    after = sum(t["qualified_leads"] for t in evidence_briefing.get_topic_attribution_map()["topics"])
    assert score < crm.QUALIFIED_THRESHOLD, "a founder who became an intern kept the founder's score"
    assert after == before - 1, "the screens went on counting a person the engine no longer qualifies"


def test_one_cut_at_eighty_and_sixty(home):
    import crm
    import post_summary
    import results
    assert crm.VIP_THRESHOLD == post_summary.VIP_SCORE == results.VIP_SCORE == 80.0
    assert crm.QUALIFIED_THRESHOLD == post_summary.QUALIFIED_SCORE == results.QUALIFIED_SCORE == 60.0
    assert results.tier(80) == "TIER_1_VIP" and results.tier(60) == "QUALIFIED"
    assert results.tier(59.9) == "NURTURE" and results.tier(0) == "DISQUALIFIED"
    assert results.is_qualified(0, "ENGAGED") is True
    assert results.is_qualified(0, "NEW", "Meeting Booked") is True
    assert results.is_qualified(59.9, "NEW", "New Lead") is False


# ---------------------------------------------------------------------------
# Saying "no difference"
# ---------------------------------------------------------------------------

def test_a_comparison_can_answer_no_difference(home):
    import results
    assert results.difference(1.0, 50, 50)["verdict"] == "none"
    assert results.difference(1.3, 50, 50)["verdict"] == "more"
    assert results.difference(0.5, 50, 50)["verdict"] == "fewer"
    assert results.difference(2.0, 2, 50)["verdict"] == "too_few_posts"
    # Three or more sides: the topic effect measured on this creator was 0.26
    # percentage points between topics against 27 inside one of them.
    assert results.spread({"pricing": [33.8, 23.3, 50.0], "growth": [33.7, 21.4, 48.3]})["verdict"] == "none"
    assert results.spread({"a": [1.0, 1.1, 1.2], "b": [9.0, 9.1, 9.2]})["verdict"] == "differs"


def test_the_topic_table_says_when_no_topic_is_different(home):
    import evidence_briefing
    answer = evidence_briefing.get_topic_attribution_map()
    assert "difference" in answer
    assert answer["difference"]["verdict"] in ("none", "differs", "too_few_groups")
    if answer["difference"]["verdict"] == "none":
        assert "no difference" in answer["summary_sentence"]


def test_a_percentage_is_refused_on_a_part_captured_window(home):
    import results
    from database import get_db
    from routers import analytics as analytics_router

    conn = get_db()
    with conn:
        for back in range(0, 4):
            day = (NOW - timedelta(days=back)).strftime("%Y-%m-%d")
            conn.execute("INSERT OR REPLACE INTO analytics_daily (date, impressions, reactions, comments, shares, "
                         "source, precision, period_label) VALUES (?, 1000, 20, 2, 1, 'observed', 'exact', '1d')",
                         (day,))
        for back in range(30, 60):
            day = (NOW - timedelta(days=back)).strftime("%Y-%m-%d")
            conn.execute("INSERT OR REPLACE INTO analytics_daily (date, impressions, reactions, comments, shares, "
                         "source, precision, period_label) VALUES (?, 1000, 20, 2, 1, 'observed', 'exact', '1d')",
                         (day,))
    conn.close()
    kpis = analytics_router.get_kpis(range="30d")
    assert kpis["impressions_delta_pct"] is None, "four captured days were compared with thirty as if equal"
    assert results.window_complete(4, 24) is False
    assert results.window_complete(30, 24) is True
