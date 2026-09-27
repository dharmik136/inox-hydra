"""
The KPI cards sum days, so only days may be summed.
===================================================

Audit W9 to W12.

W9. A capture whose window could not be read is stored labelled "unknown", on
purpose: a labelled row beats no row. get_kpis then summed it as a day, so a 28
day card total became one day's impressions.

W10. The extractor ran on any path containing "/analytics", including a single
post's summary page, whose figures were written as the account's day.

W11. With the window's first day missing, follower growth used today's figure
as the start, and reported a measured "no change" made from one reading.

W12. Comments and shares, which the creator analytics card never shows, were
stored as 0 on every captured day.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from fastapi.testclient import TestClient

import app as app_module
from database import get_db
from linkedin_client import linkedin_client

client = TestClient(app_module.app)

# Far in the future, so these rows are the latest and anchor the window, and so
# they cannot collide with the demo series.
DAYS = ["2031-03-01", "2031-03-02", "2031-03-03"]
CONTENT_JS = os.path.join(os.path.dirname(__file__), "..", "studio", "extension", "content.js")


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


def _capture(day, period, **metrics):
    bucket = {"date": day, "period_label": period, "precision": "exact", **metrics}
    return linkedin_client.ingest_analytics_payload({"series": [bucket]})


def _kpis(range_="7d"):
    return client.get(f"/api/analytics/kpis?range={range_}").json()


def test_a_day_of_unknown_window_is_not_summed_as_a_day():
    _capture(DAYS[0], "1d", impressions=100)
    _capture(DAYS[1], "1d", impressions=120)
    _capture(DAYS[2], None, impressions=41000)  # a 28 day card total, window unread

    kpis = _kpis()
    assert kpis["impressions"] == 220, "a multi-day total was added as one day"
    assert kpis["days_counted"] == 2
    assert kpis["days_excluded_unknown_window"] == 1


def test_no_daily_rows_means_unknown_totals_not_zero():
    _capture(DAYS[2], None, impressions=41000)
    kpis = _kpis()
    assert kpis["impressions"] is None and kpis["total_engagements"] is None


def test_nothing_to_compare_with_is_not_a_hundred_percent_rise():
    _capture(DAYS[2], "1d", impressions=300, reactions=12)
    kpis = _kpis()
    assert kpis["impressions_delta_pct"] is None, "no previous window read as doubling"


def test_a_missing_start_day_is_not_zero_growth():
    _capture(DAYS[2], "1d", impressions=10, followers=4200)
    assert _kpis()["follower_growth"] is None, "one reading was reported as a measured change of zero"


def test_an_unread_metric_is_stored_as_unknown():
    _capture(DAYS[2], "1d", impressions=10, reactions=3)
    conn = get_db()
    row = conn.execute("SELECT comments, shares FROM analytics_daily WHERE date = ?", (DAYS[2],)).fetchone()
    conn.close()
    assert row["comments"] is None and row["shares"] is None


def test_only_account_analytics_pages_are_read():
    with open(CONTENT_JS, encoding="utf-8") as handle:
        source = handle.read()
    gate = source[source.index("function maybeExtractAnalytics"):]
    gate = gate[:gate.index("\n}")]
    assert 'path.startsWith("/analytics/creator")' in gate, (
        "the analytics extractor runs outside the account's creator analytics, "
        "so a single post's figures can be written as the account's day"
    )
    assert not re.search(r'path\.includes\("/analytics"\)', gate)
