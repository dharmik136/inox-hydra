"""
The figures track 5's phase 2 reads, drawn where a creator looks for them.
==========================================================================

For 2.9.0 (cycle 4, track 4 after the merge with release 2.8.0). Track 5's
second phase reads the creator's own surfaces nothing read before, and keeps
every count with the window its page named. These hold where each is drawn,
in its smallest honest form:

  Analytics    profile views and search appearances, the latest reading of
               each in the range, with its window, the day and the page it
               was read from, and "not read in this range" when none was
  Posts        a post's detail: when it was first seen marked edited, and a
               video's watch time and average with the day it was read
  Posts        your reposts with their own figures, and your articles and
               newsletters with theirs, each figure with its window, and
               "not read" for one the page did not show

Strict Invariants:
- Zero em-dashes.
- No figure on screen that did not come from a row; absent is "not read".
"""

import io
import os
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

from qc2_r5_live import open_section, seed_creator, server, studio  # noqa: E402,F401


def _now(hours_ago=0):
    return datetime.now(timezone.utc) - timedelta(hours=hours_ago)


def _reading(conn, page, content_urn="", period_label="", **figures):
    when = _now(2)
    columns = ", ".join(figures)
    marks = ", ".join("?" for _ in figures)
    conn.execute(
        f"INSERT INTO insight_readings (page, content_urn, observed_at, observed_hour, period_label, precision, {columns}) "
        f"VALUES (?, ?, ?, ?, ?, 'exact', {marks})",
        (page, content_urn, when.isoformat(), when.strftime("%Y-%m-%dT%H"), period_label, *figures.values()))


def test_analytics_draws_profile_views_with_the_window_its_page_named(studio):
    from database import get_db
    seed_creator(studio["client"])
    conn = get_db()
    with conn:
        _reading(conn, "account_analytics", period_label="90d", profile_views=412)
    conn.close()
    page = open_section(studio, "analytics")
    panel = page.locator("aside section", has_text="Profile views and search appearances")
    expect(panel).to_be_visible(timeout=10000)
    expect(panel).to_contain_text("412 over the past 90 days")
    expect(panel).to_contain_text("YOUR ANALYTICS DASHBOARD")
    # No page carried search appearances: said, never 0.
    expect(panel.locator("div", has_text="Search appearances").first).to_contain_text("not read in this range")
    assert studio["errors"] == [], studio["errors"]


def test_a_posts_detail_says_it_was_edited_and_how_long_it_was_watched(studio):
    from database import get_db
    urns = seed_creator(studio["client"])
    urn = urns[0]
    conn = get_db()
    with conn:
        conn.execute("UPDATE own_posts SET edited_first_seen_at = ? WHERE activity_urn = ?", (_now(30).isoformat(), urn))
        when = _now(1)
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions, watch_time_seconds, average_watch_seconds) VALUES (?, ?, ?, 50, 'post_analytics', 900, 754, 21)",
            (urn, when.isoformat(), when.strftime("%Y-%m-%dT%H")))
    conn.close()
    page = open_section(studio, "posts")
    page.get_by_role("button", name="Your on-call rota is a culture document.").first.click()
    dialog = page.locator('div[role="dialog"][aria-label="Post detail"]')
    expect(dialog).to_contain_text("MARKED EDITED ON LINKEDIN, FIRST SEEN", timeout=10000)
    expect(dialog).to_contain_text("WATCH TIME 12 MIN 34 S")
    expect(dialog).to_contain_text("AVERAGE 21 S")
    assert studio["errors"] == [], studio["errors"]


def test_posts_lists_your_reposts_and_articles_with_their_own_figures(studio):
    from database import get_db
    seed_creator(studio["client"])
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO own_reposts (activity_urn, reposted_at, reactions, comments, reposts, impressions, "
            "first_seen_at, last_seen_at) VALUES ('urn:li:activity:7300000000000000001', ?, 12, NULL, 1, NULL, ?, ?)",
            (_now(48).isoformat(), _now(48).isoformat(), _now(3).isoformat()))
        _reading(conn, "article_analytics", content_urn="urn:li:linkedInArticle:7300000000000000002",
                 views=300, reactions=9)
        _reading(conn, "newsletter_analytics", content_urn="urn:li:fsd_newsletter:7300000000000000003",
                 period_label="30d", subscribers=120)
    conn.close()
    page = open_section(studio, "posts")
    reposts = page.locator("section", has_text="Your reposts")
    expect(reposts).to_be_visible(timeout=10000)
    expect(reposts).to_contain_text("12 REACTIONS · COMMENTS NOT READ · 1 REPOSTS · IMPRESSIONS NOT READ")
    articles = page.locator("section", has_text="Your articles and newsletters")
    expect(articles).to_contain_text("300 ARTICLE VIEWS AS ITS PAGE SHOWED IT")
    expect(articles).to_contain_text("MEMBERS REACHED NOT READ")
    expect(articles).to_contain_text("120 SUBSCRIBERS OVER THE PAST 30 DAYS")
    assert studio["errors"] == [], studio["errors"]


def test_with_nothing_read_the_posts_screen_adds_nothing(studio):
    seed_creator(studio["client"])
    page = open_section(studio, "posts")
    expect(page.locator("h1")).to_have_text("What worked, and who it brought", timeout=10000)
    page.wait_for_timeout(500)
    assert page.locator("section", has_text="Your reposts").count() == 0
    assert page.locator("section", has_text="Your articles and newsletters").count() == 0


def test_the_help_no_longer_says_profile_views_are_not_drawn():
    for name in ("read-your-analytics.md", "why-is-my-analytics-chart-empty.md"):
        with io.open(os.path.join(REPO_ROOT, "docs", "help", name), encoding="utf-8") as handle:
            text = handle.read()
        assert "does not draw them yet" not in text and "No screen shows these figures yet" not in text, name
        assert "Profile views and search appearances" in text, name
