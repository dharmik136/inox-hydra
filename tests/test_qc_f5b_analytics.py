"""
Analytics says only what the captured days support.
===================================================

Quality cycle 2026-10, batch F5b.

AUDIENCE-05. "What changed" compared a fully captured period with whatever
days of the previous one happened to exist. Two weeks after install the
previous 30 days held four captured days, so a flat 1,000 impressions a day
was reported as +650%.

Each test runs in a throwaway home of its own, so the session's demo rows
cannot anchor or pad a window.
"""

import datetime as dt
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

from fastapi.testclient import TestClient  # noqa: E402

END = dt.date(2031, 3, 31)


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc_f5b_analytics_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _days(client, count, precision="exact", **metrics):
    """`count` consecutive daily captures ending at END, every day the same."""
    series = []
    for back in range(count - 1, -1, -1):
        day = END - dt.timedelta(days=back)
        row = {"date": day.isoformat(), "period_label": "1d", "precision": precision}
        row.update({k: (v(back) if callable(v) else v) for k, v in metrics.items()})
        series.append(row)
    res = client.post("/api/analytics/ingest", json={"series": series})
    assert res.status_code == 200, res.text


def _kpis(client, range_="30d"):
    res = client.get(f"/api/analytics/kpis?range={range_}")
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# AUDIENCE-05: a thinly captured previous period gets no percentage change
# ---------------------------------------------------------------------------

def test_flat_days_against_a_partly_captured_period_are_not_a_rise(studio):
    _days(studio, 34, impressions=1000, reactions=20, comments=2, shares=1)
    kpis = _kpis(studio, "30d")
    assert kpis["days_counted"] == 30
    assert kpis["previous_days_counted"] == 4, "the screen cannot say how much of the previous period it has"
    assert kpis["impressions_delta_pct"] is None, "four captured days were compared with thirty as if equal"
    assert kpis["engagements_delta_pct"] is None
    assert kpis["engagement_rate_delta"] is None


def test_two_fully_captured_flat_periods_are_no_change(studio):
    _days(studio, 60, impressions=1000, reactions=20, comments=2, shares=1)
    kpis = _kpis(studio, "30d")
    assert kpis["impressions_delta_pct"] == 0.0
    assert kpis["engagements_delta_pct"] == 0.0


def test_a_few_missing_days_compare_the_daily_level_not_the_sum(studio):
    # 30 days now at 1,200 a day; the previous period has 25 of its 30 days at
    # 1,000. The daily level rose 20 percent. Summing would say 44 percent.
    _days(studio, 30, impressions=1200)
    series = []
    for back in range(30, 55):
        series.append({"date": (END - dt.timedelta(days=back)).isoformat(), "period_label": "1d",
                       "precision": "exact", "impressions": 1000})
    assert studio.post("/api/analytics/ingest", json={"series": series}).status_code == 200
    kpis = _kpis(studio, "30d")
    assert kpis["previous_days_counted"] == 25
    assert kpis["impressions_delta_pct"] == 20.0


# ---------------------------------------------------------------------------
# AUDIENCE-10: a figure LinkedIn rounded (2.4K) is approximate, and is not
# compared with an exact one as if it were exact
# ---------------------------------------------------------------------------

def _rounded_today(client, **metrics):
    row = {"date": END.isoformat(), "period_label": "1d", "precision": "rounded", **metrics}
    assert client.post("/api/analytics/ingest", json={"series": [row]}).status_code == 200


def test_growth_to_a_rounded_follower_count_is_marked_approximate(studio):
    _days(studio, 34, impressions=1000, followers=lambda back: 2033 - back)
    _rounded_today(studio, followers=2400)
    kpis = _kpis(studio, "7d")
    assert kpis["total_followers"] == 2400
    assert "total_followers" in kpis["approximate"], "a 2.4K reading was reported as exactly 2,400"
    assert kpis["follower_growth"] == 2400 - 2027
    assert "follower_growth" in kpis["approximate"], "a change to a rounded reading was reported as exact"


def test_a_change_smaller_than_the_rounding_is_not_reported(studio):
    # "2K" is anything from 1,500 to 2,499 as far as the studio can tell, so a
    # reading of 2K a week after an exact 2,027 says nothing about growth.
    _days(studio, 34, impressions=1000, followers=lambda back: 2033 - back)
    _rounded_today(studio, followers=2000)
    kpis = _kpis(studio, "7d")
    assert kpis["follower_growth"] is None, "a rounding difference was reported as a loss of followers"
    assert "follower_growth" in kpis["within_rounding"]


def test_exact_figures_are_not_marked(studio):
    _days(studio, 34, impressions=1000, reactions=20, followers=lambda back: 2033 - back)
    kpis = _kpis(studio, "30d")
    assert kpis["approximate"] == [] and kpis["within_rounding"] == []


def test_a_rounded_impressions_day_makes_the_total_and_its_change_approximate(studio):
    _days(studio, 60, impressions=1000)
    _rounded_today(studio, impressions=1200)
    kpis = _kpis(studio, "30d")
    assert kpis["impressions"] == 30200
    assert "impressions" in kpis["approximate"]
    assert kpis["impressions_delta_pct"] == 0.7
    assert "impressions_delta_pct" in kpis["approximate"]


def test_a_change_inside_the_rounding_of_a_rounded_day_is_not_reported(studio):
    # Fourteen exact days of 1,180, then today read as 1.2K. The daily level
    # moved by less than the 50 either way that 1.2K can hide, spread over the
    # week, so no change is claimed.
    _days(studio, 14, impressions=1180)
    _rounded_today(studio, impressions=1200)
    kpis = _kpis(studio, "7d")
    assert kpis["impressions_delta_pct"] is None
    assert "impressions_delta_pct" in kpis["within_rounding"]
