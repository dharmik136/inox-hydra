"""
What the studio keeps from a creator analytics read.
====================================================

AUDIENCE-11 / BRIDGE-14  The follower total is a count at one moment, not a
    figure over a window, but a read whose range was 7, 28 or 90 days was
    refused whole, follower count included. Followers stayed "not measured"
    for everyone who leaves LinkedIn's range on its usual multi-day setting.
    The windowed figures are still refused; the follower count is kept.
AUDIENCE-26  Every captured day stored "members reached" as 0 although
    nothing ever reads it, so exports reported a measured-looking zero reach.
"""

import pytest

from database import get_db
from linkedin_client import linkedin_client

DAY = "2031-04-02"


@pytest.fixture(autouse=True)
def isolated_rows():
    conn = get_db()
    with conn:
        saved = [dict(r) for r in conn.execute("SELECT * FROM analytics_daily")]
        conn.execute("DELETE FROM analytics_daily")
    conn.close()
    yield
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM analytics_daily")
        for row in saved:
            columns = ", ".join(row)
            conn.execute(f"INSERT INTO analytics_daily ({columns}) VALUES ({', '.join('?' for _ in row)})",
                         tuple(row.values()))
    conn.close()


def _row(day=DAY):
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM analytics_daily WHERE date = ?", (day,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_a_seven_day_read_keeps_the_follower_count_and_refuses_the_rest():
    result = linkedin_client.ingest_analytics_payload({
        "period_label": "7d", "precision": "exact",
        "series": [{"date": DAY, "period_label": "7d", "precision": "exact",
                    "impressions": 5400, "reactions": 120, "followers": 2310}],
    })
    assert result["status"] == "window_mismatch"
    assert result["followers_saved"] == 1
    row = _row()
    assert row["followers"] == 2310
    assert row["impressions"] is None and row["reactions"] is None
    assert row["source"] == "observed"


def test_the_follower_count_does_not_disturb_a_daily_figure_already_stored():
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": DAY, "period_label": "1d", "precision": "exact", "impressions": 410, "reactions": 9, "followers": 2300}]})
    linkedin_client.ingest_analytics_payload({"period_label": "28d", "series": [{
        "date": DAY, "period_label": "28d", "impressions": 99000, "reactions": 2000, "followers": 2312}]})
    row = _row()
    assert row["followers"] == 2312
    assert row["impressions"] == 410 and row["reactions"] == 9
    assert row["period_label"] == "1d"


def test_a_windowed_read_with_no_follower_count_saves_nothing():
    result = linkedin_client.ingest_analytics_payload({"period_label": "90d", "series": [{
        "date": DAY, "period_label": "90d", "impressions": 99000}]})
    assert result["status"] == "window_mismatch"
    assert result["followers_saved"] == 0
    assert _row() is None


def test_members_reached_is_not_recorded_when_nobody_read_it():
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": DAY, "period_label": "1d", "precision": "exact", "impressions": 410}]})
    assert _row()["unique_members_reached"] is None
    linkedin_client.ingest_analytics_payload({"profile_views": 42})
    conn = get_db()
    try:
        today = conn.execute("SELECT unique_members_reached FROM analytics_daily WHERE profile_views = 42").fetchone()
    finally:
        conn.close()
    assert today["unique_members_reached"] is None
