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
    assert detail["per_post"]["followers_gained"]["value"] == 12
    assert detail["per_post"]["in_network_pct"]["value"] == 62.0
    assert detail["per_post"]["followers_gained"]["read_at_age_hours"] == pytest.approx(30, abs=1)
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


# ---------------------------------------------------------------------------
# Item 21: the decay sentence and the reach half-life
# ---------------------------------------------------------------------------

def _movement(urn, metric="impressions"):
    import results
    conn = _db()
    try:
        return results.movement(conn, urn, metric)
    finally:
        conn.close()


def _half_life(urn, metric="impressions"):
    import results
    conn = _db()
    try:
        return results.half_life(conn, urn, metric)
    finally:
        conn.close()


def test_one_reading_cannot_move_and_the_engine_says_so(client):
    import results
    mine = urn_hours_ago(30)
    _posts(client, mine)
    _reading(mine, 26.0, impressions=1200)
    moved = _movement(mine)
    assert moved["verdict"] == "too_few_readings" and moved["readings"] == 1
    assert moved["min_readings"] == results.MIN_READINGS_TO_MOVE == 2
    assert "one reading" in moved["sentence"]
    today = client.get("/api/v1/today").json()["latest_post"]
    assert today["movement"]["verdict"] == "too_few_readings"
    assert _movement(urn_hours_ago(99, 9))["verdict"] == "too_few_readings", "a post never read has no readings"


def test_the_decay_sentence_names_the_change_the_interval_and_its_reading_count(client):
    mine = urn_hours_ago(52)
    _posts(client, mine)
    _reading(mine, 26.0, precision="exact", impressions=1200, reactions=40)
    _reading(mine, 50.0, precision="exact", impressions=1250, reactions=41)
    moved = _movement(mine)
    assert moved["verdict"] == "moving"
    assert (moved["change"], moved["hours_between"], moved["readings"]) == (50, 24.0, 2)
    assert moved["approximate"] is False
    # The brief's form: "+N since the reading K hours ago, over M readings", with the latest named.
    assert moved["sentence"] == ("still moving: +50 impressions since the reading 26 hours ago, "
                                 "over 2 readings on its analytics page, the latest 2 hours ago")
    # What is usual at this age rests on the settle curve, which holds one post here: this one.
    assert moved["usual"]["verdict"] == "too_few_posts" and moved["usual"]["posts"] == 1
    assert "not enough posts" in moved["usual"]["sentence"] and "(1 of 20)" in moved["usual"]["sentence"]
    # Today carries the same sentence, computed by the same function.
    today = client.get("/api/v1/today").json()["latest_post"]
    assert today["movement"]["sentence"] == moved["sentence"]
    # A figure that did not change says so; it never says "still moving".
    _reading(mine, 51.0, precision="exact", impressions=1250, reactions=41)
    assert _movement(mine)["verdict"] == "unchanged"
    assert _movement(mine)["sentence"] == ("unchanged since the reading 2 hours ago, over 3 readings on its analytics "
                                           "page, the latest 1 hour ago")


def test_rounded_readings_make_the_sentence_say_about_or_abstain(client):
    mine = urn_hours_ago(52)
    _posts(client, mine)
    _reading(mine, 26.0, precision="rounded", impressions=12000)
    _reading(mine, 50.0, precision="rounded", impressions=14000)
    moved = _movement(mine)
    assert moved["verdict"] == "moving" and moved["approximate"] is True
    assert moved["sentence"].startswith("still moving: about +2,000 impressions")
    # 12K then 13K is a change the two readings cannot separate from their rounding.
    other = urn_hours_ago(53, 3)
    _posts(client, other)
    _reading(other, 26.0, precision="rounded", impressions=12000)
    _reading(other, 50.0, precision="rounded", impressions=13000)
    held = _movement(other)
    assert held["verdict"] == "within_rounding" and held["within_rounding"] is True
    assert "cannot separate" in held["sentence"] and "still moving" not in held["sentence"]
    # Review N5: one rounded reading is enough, and the sentence does not say "two".
    one = urn_hours_ago(54, 4)
    _posts(client, one)
    _reading(one, 26.0, precision="exact", impressions=12345)
    _reading(one, 50.0, precision="rounded", impressions=12000)
    assert "cannot separate" in _movement(one)["sentence"] and "two rounded" not in _movement(one)["sentence"]


def _curve_posts(count, days_old_from=40, first=0):
    """`count` posts whose readings put the settle curve at 60% by 24 h and 90% by 48 h."""
    conn = _db()
    with conn:
        for n in range(first, first + count):
            published = NOW - timedelta(days=days_old_from + n)
            urn = f"urn:li:activity:{7200000000000000000 + n}"
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                         "VALUES (?, 'p', ?, ?, ?)", (urn, published.isoformat(), published.isoformat(),
                                                       published.isoformat()))
            for age, impressions, reactions in ((24.0, 600, 6), (48.0, 900, 9), (336.0, 1000, 10)):
                moment = published + timedelta(hours=age)
                conn.execute(
                    "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                    "source, impressions, reactions) VALUES (?, ?, ?, ?, 'post_analytics', ?, ?)",
                    (urn, moment.isoformat(), moment.strftime("%Y-%m-%dT%H"), age, impressions, reactions))
    conn.close()


def test_the_usual_at_an_age_is_the_curve_and_abstains_below_twenty_posts(home):
    import results
    _curve_posts(10)
    results.forget_cache()
    conn = _db()
    try:
        few = results.usual_at_age(conn, 50.0)
        assert few["verdict"] == "too_few_posts" and few["posts"] == 10 and few["bucket_hours"] == 48
        assert few["sentence"] == "not enough posts read at about 48 hours old to say what is usual (10 of 20)"
    finally:
        conn.close()
    _curve_posts(15, days_old_from=400, first=10)
    results.forget_cache()
    conn = _db()
    try:
        enough = results.usual_at_age(conn, 50.0)
        assert enough["verdict"] == "measured" and enough["posts"] == 25 and enough["share"] == 0.9
        assert enough["sentence"] == ("your posts usually have 90% of their two-week impressions by 48 hours, "
                                      "measured on 25 posts")
        assert results.usual_at_age(conn, 50.0, "reactions")["share"] == 0.9
        # No bucket near 1,000 hours: the curve stops at two weeks.
        assert results.usual_at_age(conn, 1000.0)["verdict"] == "no_bucket"
    finally:
        conn.close()


def test_the_half_life_needs_three_readings_and_a_day_seven_point(client):
    import results
    mine = urn_hours_ago(400)
    _posts(client, mine)
    _reading(mine, 2.0, precision="exact", impressions=1000)
    _reading(mine, 24.0, precision="exact", impressions=6000)
    short = _half_life(mine)
    assert short["verdict"] == "too_few_readings" and short["readings"] == 2
    assert short["min_readings"] == results.MIN_READINGS_FOR_HALF_LIFE == 3
    _reading(mine, 100.0, precision="exact", impressions=9000)
    young = _half_life(mine)
    assert young["verdict"] == "too_young" and young["latest_age_hours"] == 100.0
    assert "at or after 7 days" in young["sentence"]
    _reading(mine, 170.0, precision="exact", impressions=10000)
    measured = _half_life(mine)
    assert measured["verdict"] == "measured"
    # Half of 10,000 is 5,000, reached between 1,000 at 2 h and 6,000 at 24 h: 2 + 4/5 of 22.
    assert measured["hours"] == 19.6 and measured["between_hours"] == [2.0, 24.0]
    assert measured["denominator"] == {"value": 10000, "age_hours": 170.0, "precision": "exact"}
    assert measured["source"] == "post_analytics"
    assert measured["approximate"] is False and measured["readings"] == 4
    assert measured["sentence"] == ("20 hours to half of the 10,000 impressions it had at 170 hours old, "
                                    "interpolated between readings at 2 and 24 hours, over 4 readings on its "
                                    "analytics page")
    detail = client.get(f"/api/v1/insights/posts/{mine}").json()
    assert detail["half_life"]["hours"] == 19.6 and detail["movement"]["readings"] == 4


def test_a_half_life_reached_before_the_first_reading_is_an_upper_bound(client):
    mine = urn_hours_ago(400)
    _posts(client, mine)
    _reading(mine, 20.0, precision="rounded", impressions=8000)
    _reading(mine, 48.0, precision="exact", impressions=9500)
    _reading(mine, 180.0, precision="exact", impressions=10000)
    bound = _half_life(mine)
    assert bound["verdict"] == "before_first_reading" and bound["hours"] == 20.0
    assert bound["approximate"] is True, "8K is a rounded figure"
    assert bound["sentence"] == ("under 20 hours to half of the 10,000 impressions it had at 180 hours old: "
                                 "its first reading already held about half, over 3 readings on its analytics page")


def test_readings_from_different_pages_are_never_mixed(client):
    """
    The feed card and the post's own analytics page count different things,
    so a series is one page's: the page that read the figure most often
    (review S2), here the Activity tab's two readings, never 10 -> 20 -> 30
    across both pages.
    """
    mine = urn_hours_ago(52)
    _posts(client, mine)
    _reading(mine, 26.0, source="activity_page", reactions=10)
    _reading(mine, 40.0, source="activity_page", reactions=20)
    _reading(mine, 50.0, source="post_analytics", reactions=30)
    moved = _movement(mine, "reactions")
    assert moved["source"] == "activity_page" and moved["readings"] == 2
    assert moved["change"] == 10 and "on your Activity tab" in moved["sentence"]


def test_half_lives_are_compared_through_spread_and_difference(home):
    import results
    conn = _db()
    with conn:
        for n in range(20):
            urn = f"urn:li:activity:{7300000000000000000 + n}"
            published = NOW - timedelta(days=40 + n)
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                         "VALUES (?, 'p', ?, ?, ?)", (urn, published.isoformat(), published.isoformat(),
                                                       published.isoformat()))
            # Even posts reach half by about 6 hours, odd ones by about 30.
            points = ((2.0, 2000), (6.0, 5000), (170.0, 10000)) if n % 2 == 0 else ((2.0, 1000), (30.0, 5000),
                                                                                     (170.0, 10000))
            for age, impressions in points:
                moment = published + timedelta(hours=age)
                conn.execute(
                    "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                    "source, impressions) VALUES (?, ?, ?, ?, 'post_analytics', ?)",
                    (urn, moment.isoformat(), moment.strftime("%Y-%m-%dT%H"), age, impressions))
    conn.close()
    results.forget_cache()
    conn = _db()
    try:
        lives = results.half_lives(conn)
        assert len(lives) == 20 and lives["urn:li:activity:7300000000000000000"]["hours"] == 6.0
        quick = [u for u in lives if lives[u]["hours"] == 6.0]
        slow = [u for u in lives if lives[u]["hours"] == 30.0]
        assert len(quick) == 10 and len(slow) == 10
        verdict = results.half_life_spread(conn, {"quick": quick, "slow": slow})
        assert verdict["verdict"] == "differs" and verdict["groups"] == 2
        assert verdict["medians"] == {"quick": 6.0, "slow": 30.0}
        pair = results.half_life_difference(conn, quick, slow)
        assert pair["verdict"] in ("more", "fewer") and pair["n_with"] == 10 and pair["n_without"] == 10
        assert pair["ratio"] == 0.2
        # Below the engine's minimum per side, it abstains like every other comparison.
        assert results.half_life_difference(conn, quick[:3], slow)["verdict"] == "too_few_posts"
        assert results.half_life_spread(conn, {"quick": quick[:2], "slow": slow})["verdict"] == "too_few_groups"
    finally:
        conn.close()


DERIVATIONS = ("movement", "half_life", "half_lives", "half_life_spread", "half_life_difference", "usual_at_age",
               "growth", "readings_of", "series_source", "series_words", "rounding_half_width",
               "reading_half_width", "approximate_fields")
# The sentence's wording, which may live in results.py only. Compared with
# whitespace, quotes and plus signs removed, so a sentence split across
# string literals ("still " + "moving") is the same sentence.
SENTENCE_PHRASES = ("still moving", "since the reading", "the readings' rounding cannot separate",
                    "interpolated between readings", "its first reading already held", "a half-life needs",
                    "the half-life waits")
UI_SRC = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _flat(text):
    return re.sub(r"[\s'\"`+]", "", text.lower())


def _python_strings(tree):
    """Every string literal in source order, docstrings left out: a docstring may describe a sentence."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    found = [node for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
    return [node.value for node in sorted(found, key=lambda n: (n.lineno, n.col_offset))]


def _python_bindings(relative, tree):
    """
    A derivation defined or bound outside results.py: a def or class of its
    name anywhere, a lambda bound to it anywhere, or a module or class level
    binding that is not an alias to the engine (results.<name>). A local
    holding the engine's answer (half_life = results.half_life(...)) is not one.
    """
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name in DERIVATIONS:
            found.append(f"{relative}:{node.lineno}: def {node.name}")
    top = list(tree.body)
    for node in list(top):
        if isinstance(node, ast.ClassDef):
            top.extend(node.body)
        if isinstance(node, (ast.If, ast.Try)):
            for field in ("body", "orelse", "finalbody"):
                top.extend(getattr(node, field, []) or [])
    top_ids = {id(node) for node in top}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or node.value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name)]
        alias = (isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name)
                 and node.value.value.id == "results")
        for name in names:
            if name in DERIVATIONS and (isinstance(node.value, ast.Lambda) or (id(node) in top_ids and not alias)):
                found.append(f"{relative}:{node.lineno}: {name} bound outside results.py")
    return found


def _ui_text(source):
    """Interface source with its comments taken out: a comment may describe a sentence."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(?m)//.*$", "", source)


def _one_definition_offences(py_sources, ts_sources):
    offenders = []
    for relative, text in py_sources.items():
        tree = ast.parse(text)
        offenders += _python_bindings(relative, tree)
        flat = _flat("".join(_python_strings(tree)))
        offenders += [f"{relative}: prints the engine's sentence ({phrase!r})" for phrase in SENTENCE_PHRASES
                      if _flat(phrase) in flat]
    for relative, text in ts_sources.items():
        flat = _flat(_ui_text(text))
        offenders += [f"{relative}: builds the engine's sentence ({phrase!r})" for phrase in SENTENCE_PHRASES
                      if _flat(phrase) in flat]
    return offenders


def _backend_sources():
    out = {}
    for root, _dirs, files in os.walk(BACKEND):
        for name in sorted(files):
            if name.endswith(".py"):
                path = os.path.join(root, name)
                relative = os.path.relpath(path, BACKEND)
                if relative == "results.py":
                    continue
                with open(path, encoding="utf-8") as handle:
                    out[relative] = handle.read()
    return out


def _ui_sources():
    out = {}
    for root, _dirs, files in os.walk(UI_SRC):
        for name in sorted(files):
            if name.endswith((".ts", ".tsx")):
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    out[os.path.relpath(path, UI_SRC)] = handle.read()
    return out


def test_the_decay_sentence_and_the_half_life_have_one_definition():
    """
    The guard: the derivations and the sentence's wording live in results.py
    and nowhere else in studio/backend or studio/ui/src. A second copy is how
    screens come to disagree.
    """
    offenders = _one_definition_offences(_backend_sources(), _ui_sources())
    assert not offenders, "a module derives or words for itself what results.py owns:\n" + "\n".join(offenders)
    with open(os.path.join(BACKEND, "today.py"), encoding="utf-8") as handle:
        assert "results.movement(" in handle.read(), "Today prints a sentence it did not ask the engine for"
    with open(os.path.join(BACKEND, "routers", "insights.py"), encoding="utf-8") as handle:
        source = handle.read()
    assert "results.movement(" in source and "results.half_life(" in source


def test_the_one_definition_guard_is_not_vacuous():
    """Planted defects are detected, so the guard above can fail; a docstring that only describes the sentence is not one."""
    planted = {"today.py": "def half_life(conn, urn):\n    return None\n",
               "routers/insights.py": 'SENTENCE = "still moving: +1"\n',
               "fine.py": 'def tell():\n    """Says whether it is still moving."""\n    return None\n'}
    found = _one_definition_offences(planted, {})
    assert any("def half_life" in f for f in found) and any("insights.py: prints" in f for f in found)
    assert not any(f.startswith("fine.py") for f in found)


# ---------------------------------------------------------------------------
# Item 22: a format per post, compared through the contrast engine
# ---------------------------------------------------------------------------

def test_the_archives_media_field_names_a_format_or_says_unknown():
    """
    The archive's MediaUrl and SharedUrl shapes are not verified against a
    real export, so only a marker that says what the post carries names a
    format. Everything else is unknown: a post with neither field could be
    text, a poll or an event, and nothing here guesses which.
    """
    import post_format
    assert post_format.from_archive("https://media.licdn.com/dms/image/sample/1", "") == "image"
    assert post_format.from_archive("https://www.linkedin.com/dms/prv/vid/v2/D4E05AQ/abc", "") == "video"
    assert post_format.from_archive("https://media.licdn.com/dms/document/pdf/v2/C4D1F/deck.pdf", "") == "document"
    assert post_format.from_archive("", "https://www.linkedin.com/feed/update/urn:li:activity:7100000000000000000") \
        == "repost"
    assert post_format.from_archive("", "https://www.linkedin.com/pulse/pricing-lessons-t5-creator") == "article"
    assert post_format.from_archive("", "https://www.linkedin.com/newsletters/the-pricing-letter-7000") == "newsletter"
    assert post_format.from_archive("", "") == "unknown", "no media is not proof of a text post"
    assert post_format.from_archive("https://media.licdn.com/dms/something-new/1", "") == "unknown"
    assert post_format.from_archive("", "https://example.com/my-blog-post") == "unknown", "a link is not a format here"
    assert set(post_format.FORMATS) == {"text", "image", "document", "video", "poll", "article", "newsletter",
                                        "repost"}


def test_card_markers_name_a_format_only_when_they_agree():
    """The contract for the card reader's markers (wiring is Track 1's region; see the record)."""
    import post_format
    assert post_format.from_markers(["document"]) == "document"
    assert post_format.from_markers(["image", "image"]) == "image"
    assert post_format.from_markers(["image", "video"]) == "unknown", "two markers that disagree say nothing"
    assert post_format.from_markers([]) == "unknown"
    assert post_format.from_markers(["sparkles"]) == "unknown"
    assert post_format.from_markers(None) == "unknown"


SHARES = "Date,ShareLink,ShareCommentary,SharedUrl,MediaUrl,Visibility\n"


def _snow(moment, salt):
    return (int(moment.timestamp() * 1000) << 22) | (salt & ((1 << 22) - 1))


def _share(moment, salt, text="", shared="", media="", kind="share"):
    link = f"https://www.linkedin.com/feed/update/urn%3Ali%3A{kind}%3A{_snow(moment, salt)}"
    quoted = '"' + text.replace('"', '""') + '"' if text else ""
    return f"{moment.strftime('%Y-%m-%d %H:%M:%S')},{link},{quoted},{shared},{media},MEMBER_NETWORK\n"


def _import_shares(client, shares):
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Shares.csv", SHARES + shares)
    uploaded = client.post("/api/v1/archive/upload", content=buffer.getvalue(), headers={
        "Content-Type": "application/zip", "X-Archive-Name": "Complete_LinkedInDataExport_10-19-2026.zip"})
    assert uploaded.status_code == 200, uploaded.text
    done = client.post("/api/v1/archive/import", json={"source": uploaded.json()["source"], "include": ["posts"],
                                                       "confirm_owner": True})
    assert done.status_code == 200, done.text
    return done.json()


def test_an_archive_import_records_each_posts_format(client, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from datetime import datetime as dt_
    days = [dt_(2024, 3, d, 9, 0, tzinfo=timezone.utc) for d in (4, 5, 6, 7)]
    # A post the bridge already holds, under its activity id, as the archive's twin by id and time.
    bridge = f"urn:li:activity:{_snow(days[3], 4242)}"
    conn = _db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                     "first_seen_at, last_seen_at) VALUES (?, NULL, ?, 'urn_decode', 3, 'x', 'x')",
                     (bridge, days[3].isoformat()))
    conn.close()
    _import_shares(client, "".join((
        _share(days[0], 1, text="A photo from the offsite", media="https://media.licdn.com/dms/image/sample/1"),
        _share(days[1], 2, text="Our pricing deck", media="https://media.licdn.com/dms/document/pdf/v2/deck.pdf"),
        _share(days[2], 3, text="Just words, or a poll: the archive cannot say"),
        _share(days[3], 4242, media="https://media.licdn.com/dms/image/sample/2", kind="ugcPost"),
    )))
    conn = _db()
    try:
        formats = {r["text"]: r["format"] for r in conn.execute("SELECT text, format FROM own_posts")}
        assert formats["A photo from the offsite"] == "image"
        assert formats["Our pricing deck"] == "document"
        assert formats["Just words, or a poll: the archive cannot say"] == "unknown"
        assert conn.execute("SELECT format FROM own_posts WHERE activity_urn = ?", (bridge,)).fetchone()[0] == "image"
        # A known format is never overwritten by a later, vaguer read.
        with conn:
            conn.execute("UPDATE own_posts SET format = 'video' WHERE activity_urn = ?", (bridge,))
    finally:
        conn.close()
    _import_shares(client, _share(days[3], 4242, media="https://media.licdn.com/dms/image/sample/2", kind="ugcPost"))
    conn = _db()
    try:
        assert conn.execute("SELECT format FROM own_posts WHERE activity_urn = ?", (bridge,)).fetchone()[0] == "video"
    finally:
        conn.close()
    assert client.get(f"/api/v1/insights/posts/{bridge}").json()["format"] == "video"


def _formatted_posts(groups):
    """Settled posts with reactions read, `groups` maps a format to (count, reactions each)."""
    conn = _db()
    n = 0
    with conn:
        for fmt, (count, reactions) in groups.items():
            for _ in range(count):
                published = NOW - timedelta(days=30 + n)
                urn = f"urn:li:activity:{7400000000000000000 + n}"
                conn.execute(
                    "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                    "first_seen_at, last_seen_at, format) VALUES (?, ?, ?, 'activity', ?, ?, ?, ?)",
                    (urn, None if fmt == "image" else f"post {n}", published.isoformat(), reactions,
                     published.isoformat(), published.isoformat(), fmt))
                n += 1
    conn.close()


def test_format_comparisons_run_through_the_contrast_engine_with_its_abstentions(home):
    import contrast_engine
    import results
    _formatted_posts({"image": (10, 90), "document": (9, 30), "video": (5, 30), "unknown": (6, 500)})
    out = contrast_engine.compute_all_contrasts()
    by_format = {c["format"]: c for c in out["format_contrasts"]}
    assert set(by_format) == set(contrast_engine.post_format.FORMATS)
    image = by_format["image"]
    # Image posts against every other known format; the six unknown posts are on neither side.
    assert (image["n_with"], image["n_without"], image["n_unknown"]) == (10, 14, 6)
    assert image["status"] == "conclusive" and image["ratio"] == 3.0
    assert image["difference"]["verdict"] == "more" and image["min_required"] == results.MIN_PER_SIDE
    # Captionless image posts count: the seven text features skip posts with no text, formats do not.
    video = by_format["video"]
    assert video["status"] == "not_enough_data" and video["difference"]["verdict"] == "too_few_posts"
    assert by_format["poll"]["n_with"] == 0 and by_format["poll"]["status"] == "not_enough_data"
    assert out["format_coverage"] == {"settled_posts": 30, "format_known": 24, "format_unknown": 6,
                                      "by_format": {"image": 10, "document": 9, "video": 5}}
    # The seven text features are untouched by the format comparisons.
    assert [c["key"] for c in out["contrasts"]] == [key for key, _label, _test in results.BINARY_FEATURES]


def test_format_comparisons_flag_different_periods(home):
    import contrast_engine
    conn = _db()
    with conn:
        for n in range(20):
            # Image posts two years before the others: the difference may be about when, not how.
            days_old = 30 + n + (730 if n < 10 else 0)
            published = NOW - timedelta(days=days_old)
            conn.execute(
                "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                "first_seen_at, last_seen_at, format) VALUES (?, 'p', ?, 'activity', ?, ?, ?, ?)",
                (f"urn:li:activity:{7500000000000000000 + n}", published.isoformat(), 90 if n < 10 else 30,
                 published.isoformat(), published.isoformat(), "image" if n < 10 else "document"))
    conn.close()
    image = next(c for c in contrast_engine.compute_all_contrasts()["format_contrasts"] if c["format"] == "image")
    assert image["status"] == "different_period" and image["difference"]["notable"] is False


def test_a_window_row_never_moves_the_daily_range(client):
    """
    Found by the full suite: the overview was anchored on the latest day of
    either table, so a 28 day reading dated after the last daily row moved
    the chart's range away from every daily figure, while get_kpis, anchored
    on the daily rows, still covered them. The chart and the figures above it
    must cover the same days.
    """
    from linkedin_client import linkedin_client
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": "2031-03-01", "period_label": "1d", "precision": "exact", "impressions": 410}]})
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": "2031-07-07", "period_label": "28d", "impressions": 90000}]})
    overview = client.get("/api/analytics/overview?range=30d").json()
    assert [row["date"] for row in overview["series"]] == ["2031-03-01"]
    assert overview["windows"] == [], "a window outside the daily range is not listed in it"
    # With no daily row at all, the windows are still shown, from their own latest day.
    conn = _db()
    with conn:
        conn.execute("DELETE FROM analytics_daily")
    conn.close()
    alone = client.get("/api/analytics/overview?range=30d").json()
    assert alone["series"] == [] and [w["date"] for w in alone["windows"]] == ["2031-07-07"]


# ---------------------------------------------------------------------------
# The owner's decision of 2026-10-26: an unverified label that is absent is
# not drift. Only the seven labels the reader had before this cycle can
# drift; how long each new one has gone unread is derived from the readings.
# ---------------------------------------------------------------------------

OWN_PAGES = os.path.join(REPO_ROOT, "studio", "extension", "own_pages.js")
# The seven labels in POST_METRIC_LABELS on main before this cycle, measured on
# a live page in cycle 2. Nothing added in cycle 4 may drift.
VERIFIED_LABELS = {"members_reached", "impressions", "reactions", "comments", "reposts", "saves", "sends"}


def _labels_that_can_drift(source):
    match = re.search(r"const POST_LABELS_ON_EVERY_POST = \[(.*?)\];", source, re.DOTALL)
    assert match, "POST_LABELS_ON_EVERY_POST is gone from own_pages.js, so nothing says which labels drift"
    return set(re.findall(r'"([a-z_]+)"', match.group(1)))


def test_only_the_labels_read_before_this_cycle_can_drift():
    with open(OWN_PAGES, encoding="utf-8") as handle:
        listed = _labels_that_can_drift(handle.read())
    assert listed, "no label can drift, so a changed page would read as working"
    assert listed <= VERIFIED_LABELS, f"a label added this cycle can drift: {sorted(listed - VERIFIED_LABELS)}"


def test_the_drift_guard_is_not_vacuous():
    """A planted new label is found, so the guard above can fail."""
    with open(OWN_PAGES, encoding="utf-8") as handle:
        source = handle.read()
    planted = source.replace("const POST_LABELS_ON_EVERY_POST = [", 'const POST_LABELS_ON_EVERY_POST = ["followers_gained", ', 1)
    assert planted != source
    assert "followers_gained" in _labels_that_can_drift(planted) - VERIFIED_LABELS


def test_sightings_say_how_long_each_new_field_has_gone_unread(client):
    """
    A label that never appears is still visible: per new field, when a post
    analytics page last carried it and how many have been read since,
    derived from the readings and nothing else.
    """
    import onboarding
    posts = [urn_hours_ago(30 + i, i) for i in range(5)]
    _posts(client, *posts)
    # A reading from the activity page is not a post analytics page, and is not counted.
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": posts[0], "actor": ME, "reactions": 30}]})

    def page(urn, **metrics):
        answer = client.post("/api/v1/self/posts/analytics", json={
            "author": ME, "activity_urn": urn, "metrics": {"impressions": 1000, **metrics}}).json()
        assert answer["recorded"] is True

    def seen():
        out = onboarding.post_analytics_sightings()
        return out, {f["field"]: f for f in out["fields"]}

    out, fields = seen()
    assert out["post_analytics_readings"] == 0
    assert fields["followers_gained"]["sentence"] == "followers gained from this post: no post analytics page read yet"

    page(posts[0], followers_gained=3, demographics=[{"dimension": "job_title", "label": "Founder", "percentage": 21}])
    page(posts[1], profile_viewers=5)
    page(posts[2])
    page(posts[3])
    out, fields = seen()
    assert out["post_analytics_readings"] == 4
    assert set(fields) == {"followers_gained", "profile_viewers", "link_visits", "article_views", "video_views",
                           "in_network_pct", "out_of_network_pct", "demographics",
                           # Phase 2: a video's watch time joins the same rule.
                           "watch_time_seconds", "average_watch_seconds"}
    followers = fields["followers_gained"]
    assert followers["readings_since"] == 3 and followers["last_read_at"]
    assert followers["sentence"] == ("followers gained from this post: not read on any of the last 3 post analytics "
                                     f"pages, last read {followers['last_read_at'][:10]}")
    assert fields["demographics"]["readings_since"] == 3
    assert fields["profile_viewers"]["readings_since"] == 2
    assert fields["link_visits"]["last_read_at"] is None and fields["link_visits"]["readings_since"] == 4
    assert fields["link_visits"]["sentence"] == "link visits: not read on any of the 4 post analytics pages read so far"
    # Absent is stored as nothing: the reading has no value for it, never a 0.
    assert onboarding.post_readings(posts[2])[-1]["followers_gained"] is None

    # Seen once and then not again; seen again on the latest page.
    page(posts[4], followers_gained=1)
    out, fields = seen()
    assert fields["followers_gained"]["readings_since"] == 0
    assert fields["followers_gained"]["sentence"] == "followers gained from this post: read on the latest post analytics page"
    assert fields["profile_viewers"]["readings_since"] == 3
    assert fields["demographics"]["readings_since"] == 4

    route = client.get("/api/analytics/post-field-sightings").json()
    assert route["status"] == "success" and route["post_analytics_readings"] == 5
    assert {f["field"]: f["readings_since"] for f in route["fields"]} == {
        f: fields[f]["readings_since"] for f in fields}
    assert "may not show" in route["meaning"] and "label may have changed" in route["meaning"]


# ---------------------------------------------------------------------------
# Review S2 and Track 6's finding: a newer reading never erases what older
# readings say. Each figure's latest value is the newest reading that has
# it; a derivation reads one page's series per figure.
# ---------------------------------------------------------------------------

def _figures_both_ways(urn):
    """results.figures read before and after the per-post summary is rebuilt: the two paths must agree."""
    import post_summary
    import results
    conn = _db()
    try:
        raw = results.figures(conn, [urn])[urn]
        with conn:
            post_summary.refresh(conn, [urn])
        summary = results.figures(conn, [urn])[urn]
    finally:
        conn.close()
    assert raw == summary, (raw, summary)
    return raw


def test_a_newer_reading_that_lacks_a_figure_keeps_the_older_value(client):
    import results
    mine = urn_hours_ago(300)
    _posts(client, mine)
    _reading(mine, 48.0, precision="exact", impressions=1000, reactions=40, comments=4)
    _reading(mine, 100.0, source="activity_page", reactions=45, comments=5)
    figure = _figures_both_ways(mine)
    assert (figure["impressions"], figure["reactions"], figure["comments"]) == (1000, 45, 5)
    assert figure["by_figure"]["impressions"]["source"] == "post_analytics"
    assert figure["by_figure"]["reactions"]["source"] == "activity_page"
    assert figure["source"] == "activity_page", "the newest reading is still named as the newest"
    # A rate never mixes two readings: impressions and reactions came from two.
    assert results.engagement_rate(figure) == (None, "different_readings")
    assert "different readings" in results.rate_reason_sentence("different_readings")


def test_a_newer_reading_from_another_source_does_not_make_a_figure_unmeasured(client):
    """Track 6's case: an export row, merged, became the newest reading and reactions read not measured."""
    import results
    mine = urn_hours_ago(300)
    _posts(client, mine)
    _reading(mine, 48.0, precision="exact", impressions=1000, reactions=40)
    _reading(mine, 120.0, source="analytics_export", impressions=1200)
    figure = _figures_both_ways(mine)
    assert (figure["impressions"], figure["reactions"]) == (1200, 40)
    assert figure["by_figure"]["impressions"]["source"] == "analytics_export"
    assert figure["by_figure"]["reactions"]["source"] == "post_analytics"
    # One reading with both still gives its rate.
    _reading(mine, 130.0, source="analytics_export", impressions=1300, reactions=52)
    assert results.engagement_rate(_figures_both_ways(mine)) == (4.0, None)


def test_one_stray_reading_from_another_page_never_displaces_a_series(client):
    """Review S2: one Activity-tab reading that printed impressions erased a measured half-life."""
    import results
    mine = urn_hours_ago(400)
    _posts(client, mine)
    _reading(mine, 2.0, precision="exact", impressions=1000)
    _reading(mine, 24.0, precision="exact", impressions=6000)
    _reading(mine, 170.0, precision="exact", impressions=10000)
    _reading(mine, 200.0, source="activity_page", impressions=10500)
    life = _half_life(mine)
    assert life["verdict"] == "measured" and life["hours"] == 19.6 and life["readings"] == 3
    assert life["source"] == "post_analytics" and "over 3 readings on its analytics page" in life["sentence"]
    moved = _movement(mine)
    assert moved["readings"] == 3 and moved["source"] == "post_analytics"
    assert moved["change"] == 4000 and "over 3 readings on its analytics page" in moved["sentence"]
    conn = _db()
    try:
        results.forget_cache()
        assert mine in results.half_lives(conn)
    finally:
        conn.close()


def test_the_denser_page_is_the_series_and_the_sentence_names_it(client):
    mine = urn_hours_ago(300)
    _posts(client, mine)
    _reading(mine, 30.0, precision="exact", reactions=20)
    _reading(mine, 60.0, precision="exact", reactions=30)
    for age, reactions in ((40.0, 22), (70.0, 31), (100.0, 35), (130.0, 38)):
        _reading(mine, age, source="activity_page", reactions=reactions)
    moved = _movement(mine, "reactions")
    assert moved["source"] == "activity_page" and moved["readings"] == 4
    assert moved["change"] == 3 and "over 4 readings on your Activity tab" in moved["sentence"]


def test_per_post_figures_come_from_the_newest_page_reading_that_has_each(client):
    """Review N7: a figure read at 26 hours and absent at 50 showed as not read."""
    mine = urn_hours_ago(60)
    _posts(client, mine)
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 900, "followers_gained": 4}})
    conn = _db()
    with conn:
        conn.execute("UPDATE post_metric_observations SET observed_hour = 'earlier', "
                     "observed_at = ? WHERE activity_urn = ?", ((NOW - timedelta(hours=24)).isoformat(), mine))
    conn.close()
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 1400, "profile_viewers": 9}})
    per_post = client.get(f"/api/v1/insights/posts/{mine}").json()["per_post"]
    assert per_post["followers_gained"]["value"] == 4 and per_post["profile_viewers"]["value"] == 9
    assert per_post["followers_gained"]["read_at"] < per_post["profile_viewers"]["read_at"]


def test_the_analytics_table_never_rates_two_readings_together(client):
    """The leaderboard rebuilt the figures for its rate, so it must carry where each came from."""
    mine = urn_hours_ago(300)
    _posts(client, mine)
    _reading(mine, 48.0, precision="exact", impressions=1000, reactions=40)
    _reading(mine, 100.0, source="activity_page", reactions=45)
    row = next(p for p in client.get("/api/analytics/posts?limit=200").json()["posts"] if p["id"] == mine)
    assert (row["impressions"], row["reactions"]) == (1000, 45)
    assert row["engagement_rate"] is None and row["engagement_rate_unmeasured"] == "different_readings"


# ---------------------------------------------------------------------------
# Review S3: a reading with no precision flag is unknown, never exact
# ---------------------------------------------------------------------------

def test_a_reading_with_no_flag_may_have_been_rounded():
    """
    Readings taken before migration 28 and every Activity-tab reading carry
    no flag. A figure that a rounded display could have printed (12,000 as
    "12K") is "about"; one it could not have printed (1,912) is exact.
    """
    import results
    assert results.reading_half_width(12000, None) == 500 and results.reading_half_width(12000, "rounded") == 500
    assert results.reading_half_width(12000, "exact") == 0 and results.reading_half_width(1912, None) == 0
    same = results.growth({"value": 12000, "precision": None}, {"value": 12000, "precision": None})
    assert same["within_rounding"] is True and same["approximate"] is True, "12K read twice is not 'unchanged'"
    step = results.growth({"value": 12000, "precision": None}, {"value": 13000, "precision": None})
    assert step["within_rounding"] is True
    written = results.growth({"value": 1912, "precision": None}, {"value": 2205, "precision": None})
    assert written["approximate"] is False and written["change"] == 293
    # 2,200 could be "2.2K", so with no flag it is about, not exact.
    assert results.growth({"value": 1912, "precision": None}, {"value": 2200, "precision": None})["approximate"]
    assert results.approximate_fields({"impressions": 12000, "reactions": 41, "precision": None}) == ["impressions"]
    # The daily analytics rows keep migration 5's convention, where the reader has flagged every row since.
    assert results.rounding_half_width(12000, None) == 0.0


def test_the_upgraded_database_case_never_reports_a_change_rounding_could_hide(client):
    """The reviewer's probe: readings stored before the flag existed, 12000 then 13000 and 12000 twice."""
    rising, flat = urn_hours_ago(52, 1), urn_hours_ago(53, 2)
    _posts(client, rising, flat)
    _reading(rising, 26.0, impressions=12000)
    _reading(rising, 50.0, impressions=13000)
    _reading(flat, 26.0, impressions=12000)
    _reading(flat, 50.0, impressions=12000)
    for urn in (rising, flat):
        moved = _movement(urn)
        assert moved["verdict"] == "within_rounding" and moved["approximate"] is True, moved["sentence"]
        assert "cannot separate" in moved["sentence"]
    written = urn_hours_ago(54, 3)
    _posts(client, written)
    _reading(written, 26.0, impressions=1912)
    _reading(written, 50.0, impressions=2205)
    exact = _movement(written)
    assert exact["verdict"] == "moving" and exact["approximate"] is False
    assert exact["sentence"].startswith("still moving: +293 impressions")
    mine = urn_hours_ago(200, 5)
    _posts(client, mine)
    _reading(mine, 48.0, impressions=12000, reactions=41)
    assert client.get(f"/api/v1/insights/posts/{mine}").json()["approximate"] == ["impressions"]


# ---------------------------------------------------------------------------
# Track 6's finding: the page reader's daily write replaced the whole row
# ---------------------------------------------------------------------------

def test_a_daily_write_never_clears_a_column_another_writer_filled(client):
    """
    Track 6 adds new_followers from the export. INSERT OR REPLACE rewrote the
    whole row, so a column another writer filled the same day was lost.
    """
    from linkedin_client import linkedin_client
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _db()
    with conn:
        if "new_followers" not in {r[1] for r in conn.execute("PRAGMA table_info(analytics_daily)")}:
            conn.execute("ALTER TABLE analytics_daily ADD COLUMN new_followers INTEGER")
        conn.execute("INSERT INTO analytics_daily (date, new_followers, impressions, reactions, comments, shares, "
                     "engagement_rate) VALUES (?, 7, NULL, NULL, NULL, NULL, NULL)", (DAY,))
        conn.execute("INSERT INTO analytics_daily (date, new_followers, followers, impressions, reactions, comments, "
                     "shares, engagement_rate) VALUES (?, 9, 2000, 400, NULL, NULL, NULL, NULL)", (today,))
    conn.close()
    # The creator analytics page reader's daily write.
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": DAY, "period_label": "1d", "precision": "exact", "impressions": 410, "reactions": 9}]})
    # The profile-views write, on a day that already has a row.
    linkedin_client.ingest_analytics_payload({"profile_views": 42})
    first, second = _daily_row(DAY), _daily_row(today)
    assert first["new_followers"] == 7 and (first["impressions"], first["reactions"]) == (410, 9)
    assert second["new_followers"] == 9 and second["profile_views"] == 42
    assert (second["followers"], second["impressions"]) == (2000, 400), "a column it did not read is left as it was"
    assert second["reactions"] is None, "a figure nobody read is never turned into a 0"


def test_a_windowed_reading_does_not_claim_a_screen_shows_it(client):
    """Review N10: the answer said weekly readings are "shown beside the daily figures"; nothing shows them yet."""
    from linkedin_client import linkedin_client
    answer = linkedin_client.ingest_analytics_payload({"series": [{
        "date": DAY, "period_label": "7d", "impressions": 5400}]})
    assert answer["windows_saved"] == 1 and "shown" not in answer["message"]


# ---------------------------------------------------------------------------
# Review S4: forgetting the identity takes the dated demographics with it
# ---------------------------------------------------------------------------

def test_forgetting_the_identity_forgets_the_dated_demographics(client):
    mine = urn_hours_ago(30)
    _posts(client, mine)
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "demographics": [{"dimension": "job_title", "label": "Founder", "percentage": 21}]}})
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM audience_demographic_readings").fetchone()[0] == 1
    finally:
        conn.close()
    assert client.delete("/api/v1/identity").json()["status"] == "forgotten"
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM post_metric_observations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audience_demographic_readings").fetchone()[0] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Review S5: the data export carries both new tables
# ---------------------------------------------------------------------------

def test_the_data_export_carries_the_dated_demographics_and_the_windows(client, tmp_path):
    import json
    import support
    from linkedin_client import linkedin_client
    mine = urn_hours_ago(30)
    _posts(client, mine)
    client.post("/api/v1/self/posts/analytics", json={"author": ME, "activity_urn": mine, "metrics": {
        "impressions": 4100, "demographics": [{"dimension": "job_title", "label": "Founder", "percentage": 21}]}})
    linkedin_client.ingest_analytics_payload({"series": [{"date": DAY, "period_label": "7d", "impressions": 5400}]})
    path = support.export_data(str(tmp_path / "export.json"), fmt="json")
    with open(path, encoding="utf-8") as handle:
        tables = json.load(handle)["tables"]
    assert [r["label"] for r in tables["audience_demographic_readings"]] == ["Founder"]
    assert [(r["date"], r["period_label"]) for r in tables["analytics_windows"]] == [(DAY, "7d")]


# ---------------------------------------------------------------------------
# Review S6: the privacy policy names every figure the reader keeps
# ---------------------------------------------------------------------------

POLICY = os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md")
# How the policy names each figure the post analytics reader keeps. A label
# added to the reader without a line here fails the test below, which is
# the point: the policy has to be told.
POLICY_WORDS = {
    "members_reached": "members reached", "impressions": "impressions", "reactions": "reactions",
    "comments": "comments", "reposts": "reposts", "saves": "saves", "sends": "sends",
    "followers_gained": "followers gained", "profile_viewers": "profile viewers", "link_visits": "link visits",
    "article_views": "article views", "video_views": "video views",
    "in_network_pct": "inside", "out_of_network_pct": "outside your network", "demographics": "demographics",
    "watch_time_seconds": "watch time", "average_watch_seconds": "average watch time",
}


def _reader_keys(source):
    keys = set()
    for name in ("POST_METRIC_LABELS", "POST_SHARE_LABELS", "POST_DURATION_LABELS"):
        match = re.search(rf"const {name} = \[(.*?)\n  \];", source, re.DOTALL)
        assert match, f"{name} is gone from own_pages.js"
        keys |= set(re.findall(r'\["[^"]+", "([a-z_]+)"\]', match.group(1)))
    if "metrics.demographics = " in source:
        keys.add("demographics")
    return keys


def _post_analytics_paragraph(policy):
    match = re.search(r"From \*\*your post analytics pages\*\*.*?(?:\n\n|\Z)", policy, re.DOTALL)
    assert match, "the policy has no paragraph for the post analytics pages"
    return " ".join(match.group(0).split()).lower()


def _policy_disagreements(source, policy):
    keys, paragraph = _reader_keys(source), _post_analytics_paragraph(policy)
    problems = [f"the reader keeps {key}, which the test does not know how the policy names" for key in
                sorted(keys - set(POLICY_WORDS))]
    problems += [f"the policy does not name {POLICY_WORDS[key]!r}" for key in sorted(keys & set(POLICY_WORDS))
                 if POLICY_WORDS[key] not in paragraph]
    if "own_pages.js" not in paragraph:
        problems.append("the paragraph does not name own_pages.js, which reads these pages")
    if "demographics" in keys and not ("aggregate percentages" in paragraph and "never names" in paragraph):
        problems.append("the paragraph does not say demographics are aggregate percentages, never names")
    return problems


def test_the_privacy_policy_names_every_figure_the_post_analytics_reader_keeps():
    with open(OWN_PAGES, encoding="utf-8") as handle:
        source = handle.read()
    with open(POLICY, encoding="utf-8") as handle:
        policy = handle.read()
    problems = _policy_disagreements(source, policy)
    assert not problems, "the policy and the reader disagree:\n" + "\n".join(problems)


def test_the_policy_guard_is_not_vacuous():
    """A label added to the reader, or a figure dropped from the paragraph, is caught."""
    with open(OWN_PAGES, encoding="utf-8") as handle:
        source = handle.read()
    with open(POLICY, encoding="utf-8") as handle:
        policy = handle.read()
    planted = source.replace('["video views", "video_views"],', '["video views", "video_views"],\n    ["watch time", "watch_time"],', 1)
    assert any("watch_time" in p for p in _policy_disagreements(planted, policy))
    start = policy.index("From **your post analytics pages**")
    end = policy.index("\n\n", start)
    assert "saves" in policy[start:end]
    dropped = policy[:start] + policy[start:end].replace("saves", "keeps", 1) + policy[end:]
    assert any("'saves'" in p for p in _policy_disagreements(source, dropped))


# ---------------------------------------------------------------------------
# Review N12 and the coordinator's item 8: the one-definition guard, widened
# ---------------------------------------------------------------------------

ESCAPES_PY = {
    "today.py": "movement = lambda conn, urn: None\n",
    "routers/insights.py": 'SENTENCE = "still " + "moving: +1"\n',
}
ESCAPE_TSX = {"components/TodaySurface.tsx": 'export const line = () => <p>{"Still " + "moving"}: +1</p>;\n'}
ALLOWED_PY = {
    "fine.py": ('def tell():\n    """Says whether it is still moving."""\n    return None\n\n'
                "rounding_half_width = results.rounding_half_width\n\n"
                "def detail(conn, urn):\n    half_life = results.half_life(conn, urn)\n    return half_life\n"),
}
ALLOWED_TSX = {"components/Fine.tsx": "// Whether it is still moving, from results.movement.\n"
                                      "{/* still moving, said by the engine */}\nexport const x = 1;\n"}


def test_the_widened_guard_catches_the_reviewers_three_escapes():
    found = _one_definition_offences(ESCAPES_PY, ESCAPE_TSX)
    assert any("today.py" in f and "movement" in f for f in found), found
    assert any("routers/insights.py" in f for f in found), found
    assert any("TodaySurface.tsx" in f for f in found), found
    assert not _one_definition_offences(ALLOWED_PY, ALLOWED_TSX), "a description, an alias or a result is not a copy"

