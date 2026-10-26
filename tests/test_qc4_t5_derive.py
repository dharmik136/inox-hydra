"""
Derive: what the readings already held can say, honestly.
=========================================================

Cycle 4, track 5. The capture report's items 18 to 22:

  18  a reading says how precisely it was read, so growth between two
      rounded readings is "approximate", never a measured difference
  19  the seven post analytics figures the reader walked past, a percentage
      parser for the network split, and demographics with a date
  20  followers as a series, a weekly card kept as weekly, and a roll-up
      that keeps the first reading of each day as well as the last
  21  the decay sentence and the reach half-life, computed in results.py and
      nowhere else, abstaining below the engine's minimums
  22  a format per post, compared through the contrast engine's abstentions

Each test runs in a throwaway home of its own.
"""

import ast
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

ME = "t5-creator"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def urn_hours_ago(hours, salt=0):
    """A real-shaped activity URN whose embedded timestamp is `hours` ago."""
    moment = NOW - timedelta(hours=hours)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc4_t5_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    import results
    init_db()
    results.forget_cache()
    yield path
    results.forget_cache()
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(home):
    from fastapi.testclient import TestClient
    import app as app_module
    c = TestClient(app_module.app)
    c.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                             "display_name": "T5 Creator"})
    c.post("/api/v1/identity/confirm", json={"vanity": ME})
    return c


def _db():
    from database import get_db
    return get_db()


def _posts(client, *urns):
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": u, "actor": ME, "text": f"Post {i} about pricing"} for i, u in enumerate(urns)]})


def _reading(urn, age_hours, source="post_analytics", precision=None, observed_at=None, **metrics):
    """One reading, written the way a capture writes it, at the post's age."""
    published = datetime.fromtimestamp((int(urn.rsplit(":", 1)[1]) >> 22) / 1000.0, tz=timezone.utc)
    moment = observed_at or (published + timedelta(hours=age_hours))
    columns = ["activity_urn", "observed_at", "observed_hour", "age_hours", "source", "precision"] + list(metrics)
    conn = _db()
    with conn:
        conn.execute(
            f"INSERT INTO post_metric_observations ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)})",
            (urn, moment.isoformat(), moment.strftime("%Y-%m-%dT%H") + f"-{age_hours}", age_hours, source,
             precision, *metrics.values()))
    conn.close()


# ---------------------------------------------------------------------------
# Item 18: the precision column
# ---------------------------------------------------------------------------

def test_the_track_has_one_migration_named_for_what_it_changes(home):
    """Found by name, never by number: the coordinator renumbers at integration."""
    import migrations
    mine = [m for m in migrations.MIGRATIONS if "precision on post readings" in m[1].lower()]
    assert len(mine) == 1, "exactly one migration for the track"
    conn = _db()
    try:
        readings = {r[1] for r in conn.execute("PRAGMA table_info(post_metric_observations)")}
        assert {"precision", "followers_gained", "profile_viewers", "link_visits", "article_views", "video_views",
                "in_network_pct", "out_of_network_pct"} <= readings
        assert "format" in {r[1] for r in conn.execute("PRAGMA table_info(own_posts)")}
        demographics = {r[1] for r in conn.execute("PRAGMA table_info(audience_demographic_readings)")}
        assert {"observed_on", "activity_urn", "dimension", "label", "percentage"} <= demographics
        windows = {r[1] for r in conn.execute("PRAGMA table_info(analytics_windows)")}
        assert {"date", "period_label", "impressions", "precision"} <= windows
    finally:
        conn.close()


def test_a_rounded_reading_is_stored_as_rounded_and_an_unsaid_one_as_unknown(client):
    mine = urn_hours_ago(30)
    _posts(client, mine)
    ok = client.post("/api/v1/self/posts/analytics", json={
        "author": ME, "activity_urn": mine, "metrics": {"impressions": 12000, "reactions": 41, "precision": "rounded"}})
    assert ok.json()["recorded"] is True
    conn = _db()
    try:
        row = conn.execute("SELECT impressions, precision FROM post_metric_observations WHERE activity_urn = ?",
                           (mine,)).fetchone()
        assert (row["impressions"], row["precision"]) == (12000, "rounded")
    finally:
        conn.close()
    # The activity page's counts arrive with no flag: unknown is NULL, never a claim of exactness.
    other = urn_hours_ago(40, 1)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": other, "actor": ME, "reactions": 30}]})
    conn = _db()
    try:
        assert conn.execute("SELECT precision FROM post_metric_observations WHERE activity_urn = ?",
                            (other,)).fetchone()[0] is None
    finally:
        conn.close()


def test_growth_between_two_rounded_readings_is_approximate_never_measured():
    import results
    exact = results.growth({"value": 1912, "precision": "exact"}, {"value": 2200, "precision": "exact"})
    assert exact["change"] == 288 and exact["approximate"] is False and exact["within_rounding"] is False

    rounded = results.growth({"value": 12000, "precision": "rounded"}, {"value": 14000, "precision": "rounded"})
    assert rounded["change"] == 2000 and rounded["approximate"] is True and rounded["within_rounding"] is False
    assert rounded["slack"] == 1000, "12K and 14K are each anything within 500 of what was stored"

    # 12K read twice is no change the readings can separate, and neither is
    # 12K then 13K: 12,499 then 12,500 prints exactly that.
    same = results.growth({"value": 12000, "precision": "rounded"}, {"value": 12000, "precision": "rounded"})
    assert same["within_rounding"] is True and same["approximate"] is True
    step = results.growth({"value": 12000, "precision": "rounded"}, {"value": 13000, "precision": "rounded"})
    assert step["within_rounding"] is True

    # 12,500 cannot be how LinkedIn wrote a rounded figure, so it is exact whatever the row says.
    written = results.growth({"value": 12500, "precision": "rounded"}, {"value": 12600, "precision": "rounded"})
    assert written["approximate"] is False
    # One rounded reading is enough to make the pair approximate.
    mixed = results.growth({"value": 1200, "precision": "rounded"}, {"value": 1260, "precision": "exact"})
    assert mixed["approximate"] is True and mixed["within_rounding"] is False


def test_the_posts_detail_says_about_where_a_reading_is_rounded(client):
    mine = urn_hours_ago(200)
    _posts(client, mine)
    _reading(mine, 48.0, precision="rounded", impressions=12000, reactions=41)
    detail = client.get(f"/api/v1/insights/posts/{mine}").json()
    assert detail["figures_precision"] == "rounded"
    assert detail["approximate"] == ["impressions"], "41 reactions were written out in full; 12K was not"
    exact = urn_hours_ago(210, 2)
    _posts(client, exact)
    _reading(exact, 48.0, precision="exact", impressions=12000, reactions=41)
    assert client.get(f"/api/v1/insights/posts/{exact}").json()["approximate"] == []


def test_the_rounding_width_has_one_definition():
    """The router's function is the engine's: a second copy would drift."""
    import results
    from routers import analytics
    assert analytics.rounding_half_width is results.rounding_half_width
    assert results.rounding_half_width(12000, "rounded") == 500
    assert results.rounding_half_width(12000, None) == 0.0, "unknown precision claims nothing either way"


# ---------------------------------------------------------------------------
# Item 19: the seven missing fields, the network split and dated demographics
# ---------------------------------------------------------------------------

def test_the_new_post_figures_and_the_network_split_land_in_the_reading(client):
    import onboarding
    mine = urn_hours_ago(30)
    _posts(client, mine)
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "followers_gained": 12, "profile_viewers": 38, "link_visits": 21, "article_views": 15,
        "video_views": 0, "in_network_pct": 62, "out_of_network_pct": 38, "precision": "exact"}})
    readings = onboarding.post_readings(mine)
    assert len(readings) == 1
    reading = readings[0]
    assert (reading["followers_gained"], reading["profile_viewers"], reading["link_visits"]) == (12, 38, 21)
    assert (reading["article_views"], reading["video_views"]) == (15, 0)
    assert (reading["in_network_pct"], reading["out_of_network_pct"]) == (62.0, 38.0)
    detail = client.get(f"/api/v1/insights/posts/{mine}").json()
    assert detail["per_post"]["followers_gained"] == 12 and detail["per_post"]["in_network_pct"] == 62.0
    assert detail["per_post"]["read_at_age_hours"] == pytest.approx(30, abs=1)
    assert detail["readings"][0]["out_of_network_pct"] == 38.0
    # A reading from the activity page carries none of them, and says so with NULL.
    other = urn_hours_ago(40, 1)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": other, "actor": ME, "reactions": 30}]})
    assert client.get(f"/api/v1/insights/posts/{other}").json()["per_post"] is None


def test_a_share_outside_the_range_or_a_percentage_sent_as_a_count_is_not_stored(client):
    import onboarding
    mine = urn_hours_ago(30)
    _posts(client, mine)
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "in_network_pct": 162, "out_of_network_pct": -3, "followers_gained": "62%"}})
    reading = onboarding.post_readings(mine)[0]
    assert reading["impressions"] == 4100
    assert reading["in_network_pct"] is None and reading["out_of_network_pct"] is None
    assert reading["followers_gained"] is None


def test_demographics_are_a_dated_series(client):
    mine = urn_hours_ago(30)
    _posts(client, mine)
    first = client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "demographics": [
            {"dimension": "job_title", "label": "Founder", "percentage": 21},
            {"dimension": "job_title", "label": "Software Engineer", "percentage": 14},
            {"dimension": "job_title", "label": "Broken", "percentage": "many"}]}})
    assert first.json()["demographics_recorded"] == 2, "an entry with no readable percentage is not stored"
    # The same day again: the row is refreshed, not duplicated.
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4200, "demographics": [{"dimension": "job_title", "label": "Founder", "percentage": 25}]}})
    today = NOW.strftime("%Y-%m-%d")
    conn = _db()
    try:
        rows = conn.execute("SELECT observed_on, label, percentage FROM audience_demographic_readings "
                            "WHERE activity_urn = ? ORDER BY label", (mine,)).fetchall()
        assert [(r["observed_on"], r["label"], r["percentage"]) for r in rows] == [
            (today, "Founder", 25.0), (today, "Software Engineer", 14.0)]
        # Another day's reading is another point.
        with conn:
            conn.execute("INSERT INTO audience_demographic_readings (observed_at, observed_on, activity_urn, source, "
                         "dimension, label, percentage) VALUES (?, ?, ?, 'post_analytics', 'job_title', 'Founder', 18)",
                         ((NOW - timedelta(days=30)).isoformat(), (NOW - timedelta(days=30)).strftime("%Y-%m-%d"),
                          mine))
    finally:
        conn.close()
    series = client.get(f"/api/v1/insights/posts/{mine}").json()["demographics"]
    founder = [(e["observed_on"], e["percentage"]) for e in series if e["label"] == "Founder"]
    assert founder == [((NOW - timedelta(days=30)).strftime("%Y-%m-%d"), 18.0), (today, 25.0)]


# ---------------------------------------------------------------------------
# Item 20: the account series
# ---------------------------------------------------------------------------

def _daily_row(day):
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM analytics_daily WHERE date = ?", (day,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_a_profile_read_writes_followers_and_connections_to_the_daily_series(client):
    """
    The monthly profile visit used to overwrite one number in creator_identity
    and leave no history. It is a point in the same series the analytics
    page's follower card feeds, so Analytics can plot followers over time.
    """
    import onboarding
    today = NOW.strftime("%Y-%m-%d")
    onboarding.observe_profile({"vanity": ME, "follower_count": 8210, "connection_count": 1240})
    row = _daily_row(today)
    assert (row["followers"], row["connections"], row["period_label"], row["source"]) == (8210, 1240, "1d", "observed")
    assert row["impressions"] is None, "a profile read says nothing about impressions, so the day holds none"
    # The identity row keeps the latest count, as before; the series is where history lives.
    conn = _db()
    try:
        assert conn.execute("SELECT follower_count FROM creator_identity WHERE id = 1").fetchone()[0] == 8210
    finally:
        conn.close()
    # Read again the same day: the day's point moves, nothing is duplicated,
    # and a count the page did not show keeps the earlier one.
    onboarding.observe_profile({"vanity": ME, "follower_count": 8215})
    row = _daily_row(today)
    assert (row["followers"], row["connections"]) == (8215, 1240)
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM analytics_daily").fetchone()[0] == 1
    finally:
        conn.close()


def test_a_profile_read_does_not_disturb_a_daily_figure_already_stored(client):
    import onboarding
    from linkedin_client import linkedin_client
    today = NOW.strftime("%Y-%m-%d")
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": today, "period_label": "1d", "precision": "exact", "impressions": 410, "reactions": 9}]})
    onboarding.observe_profile({"vanity": ME, "follower_count": 8210})
    row = _daily_row(today)
    assert (row["impressions"], row["reactions"], row["followers"], row["period_label"]) == (410, 9, 8210, "1d")


DAY = "2031-03-20"


def test_a_seven_day_card_is_kept_as_a_week_and_shown_as_weekly(client):
    """
    The 2026 creator analytics page opens on "Past 7 days". That card was
    refused outright, so a creator who never changes the range gave the
    studio nothing but a follower count. It is kept now as what it is: a
    reading over 7 days, keyed by the day it was read, never summed as a day.
    """
    from linkedin_client import linkedin_client
    result = linkedin_client.ingest_analytics_payload({
        "period_label": "7d", "precision": "rounded",
        "series": [{"date": DAY, "period_label": "7d", "precision": "rounded",
                    "impressions": 5400, "reactions": 120, "followers": 2310}]})
    assert result["status"] == "window_mismatch" and result["saved"] == 0, "still not a daily figure"
    assert result["windows_saved"] == 1
    daily = _daily_row(DAY)
    assert daily["impressions"] is None and daily["followers"] == 2310, "the daily row holds no weekly figure"
    conn = _db()
    try:
        window = dict(conn.execute("SELECT * FROM analytics_windows WHERE date = ?", (DAY,)).fetchone())
    finally:
        conn.close()
    assert (window["period_label"], window["impressions"], window["reactions"], window["precision"]) == (
        "7d", 5400, 120, "rounded")
    assert window["comments"] is None, "a figure the card did not show is not measured, never 0"

    # Shown as weekly, beside the daily series, and never in the daily totals.
    overview = client.get("/api/analytics/overview?range=30d").json()
    weekly = [w for w in overview["windows"] if w["period_label"] == "7d"]
    assert len(weekly) == 1 and weekly[0]["label"] == "weekly" and weekly[0]["covers"] == "7 days"
    assert weekly[0]["impressions"] == 5400 and weekly[0]["precision"] == "rounded"
    kpis = client.get("/api/analytics/kpis?range=7d").json()
    assert kpis["impressions"] is None, "a weekly reading is not a captured day"

    # Read again the same day: the window's row moves; another window is another row.
    linkedin_client.ingest_analytics_payload({"series": [{"date": DAY, "period_label": "7d", "impressions": 5600}]})
    linkedin_client.ingest_analytics_payload({"series": [{"date": DAY, "period_label": "28d", "impressions": 21000}]})
    conn = _db()
    try:
        rows = conn.execute("SELECT period_label, impressions, reactions FROM analytics_windows WHERE date = ? "
                            "ORDER BY period_label", (DAY,)).fetchall()
    finally:
        conn.close()
    assert [tuple(r) for r in rows] == [("28d", 21000, None), ("7d", 5600, 120)]


def test_a_windowed_card_with_no_window_the_reader_could_name_is_not_a_window(client):
    """"unrecognised" is not a label a row can carry: nothing is kept as a window."""
    from linkedin_client import linkedin_client
    result = linkedin_client.ingest_analytics_payload({"period_label": "unrecognised", "series": [{
        "date": DAY, "period_label": "unrecognised", "impressions": 5400, "followers": 2310}]})
    assert result["status"] == "window_mismatch" and result.get("windows_saved", 0) == 0
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM analytics_windows").fetchone()[0] == 0
    finally:
        conn.close()


def _hourly_readings(urn, days_old, days_read, source="post_analytics"):
    """A post `days_old` days old, read every hour for `days_read` days after it went out."""
    published = NOW - timedelta(days=days_old)
    conn = _db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'p', ?, ?, ?)", (urn, published.isoformat(), published.isoformat(),
                                                   published.isoformat()))
        for hour in range(1, days_read * 24):
            moment = published + timedelta(hours=hour, minutes=7)
            conn.execute(
                "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
                "impressions, reactions) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (urn, moment.isoformat(), moment.strftime("%Y-%m-%dT%H"), float(hour), source, 100 + hour * 3,
                 5 + hour))
    conn.close()


def test_the_roll_up_keeps_the_first_reading_of_each_day_as_well_as_the_last(home):
    """
    The roll-up kept the last reading of each day, so a post's 2 hour and 20
    hour readings collapsed into the later one after 30 days, and the early
    point a half-life or a decay sentence rests on was gone. The first
    reading of each day survives now too.
    """
    import retention
    urn = "urn:li:activity:7100000000000000900"
    _hourly_readings(urn, days_old=45, days_read=10)
    assert retention.rules()["readings"] == "on", "a new install rolls up"

    def per_day():
        conn = _db()
        try:
            return {r["day"]: (r["first"], r["last"], r["outside_window"]) for r in conn.execute(
                "SELECT substr(observed_hour, 1, 10) AS day, MIN(observed_hour) AS first, MAX(observed_hour) AS last, "
                "SUM(CASE WHEN age_hours BETWEEN 36 AND 72 THEN 0 ELSE 1 END) AS outside_window "
                "FROM post_metric_observations WHERE activity_urn = ? GROUP BY day", (urn,))}
        finally:
            conn.close()

    before = per_day()
    assert retention.run("readings")["removed"] > 0
    after = per_day()
    assert len(after) >= 9 and set(after) == set(before)
    for day, (first, last, outside) in after.items():
        assert (first, last) == before[day][:2], f"{day}: its first or its last reading is gone"
        # A day that lies wholly inside the comparison window keeps every
        # reading and has none outside it; any other day keeps two at most.
        assert outside <= 2, f"{day} kept {outside} readings outside the comparison window"
    # The very first reading, at one hour old, is the early point, and it survived.
    conn = _db()
    try:
        assert conn.execute("SELECT MIN(age_hours) FROM post_metric_observations WHERE activity_urn = ?",
                            (urn,)).fetchone()[0] == 1.0
    finally:
        conn.close()
    assert retention.run("readings")["removed"] == 0, "the roll-up is not idempotent"
