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
