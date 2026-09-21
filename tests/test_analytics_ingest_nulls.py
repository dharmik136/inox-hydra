"""
Passive Analytics Ingest: Null Column Regression
================================================
The extension observes /voyager/api/identity/profiles and forwards a payload
that carries profile views and nothing else. Ingesting that on a day with no
analytics row wrote followers and connections as NULL, because those two
columns were the only ones selected without a COALESCE. get_kpis subtracts one
day's follower count from another, so the next dashboard load raised a
TypeError on None and the endpoint answered HTTP 500.

These tests run against an isolated database so they never touch real
creator state.
"""

import importlib
import os
import sys
import tempfile
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


@pytest.fixture
def isolated_studio():
    """Points the whole backend at a throwaway INOX_HYDRA_HOME."""
    previous = os.environ.get("INOX_HYDRA_HOME")
    with tempfile.TemporaryDirectory() as home:
        os.environ["INOX_HYDRA_HOME"] = home

        import paths
        importlib.reload(paths)
        import database
        importlib.reload(database)
        import linkedin_client
        importlib.reload(linkedin_client)

        database.init_db()
        yield database, linkedin_client

    if previous is None:
        os.environ.pop("INOX_HYDRA_HOME", None)
    else:
        os.environ["INOX_HYDRA_HOME"] = previous

    import paths
    importlib.reload(paths)
    import database
    importlib.reload(database)
    import linkedin_client
    importlib.reload(linkedin_client)


def test_profile_views_only_payload_never_writes_null_columns(isolated_studio):
    """Verifies a profile views only ingest leaves no NULL in followers or connections."""
    database, linkedin_client = isolated_studio
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conn = database.get_db()
    conn.execute("DELETE FROM analytics_daily")
    conn.commit()
    conn.close()

    result = linkedin_client.linkedin_client.ingest_analytics_payload({"profile_views": 42})
    assert result["status"] == "success"

    conn = database.get_db()
    row = conn.execute(
        "SELECT followers, connections, profile_views FROM analytics_daily WHERE date = ?",
        (today,)
    ).fetchone()
    conn.close()

    assert row is not None, "The ingest should have created today's row"
    assert row["profile_views"] == 42
    assert row["followers"] is not None, "followers must never be written as NULL"
    assert row["connections"] is not None, "connections must never be written as NULL"


def test_profile_views_ingest_carries_forward_the_last_known_counts(isolated_studio):
    """Verifies the carried forward values come from the most recent known day."""
    database, linkedin_client = isolated_studio
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conn = database.get_db()
    conn.execute("DELETE FROM analytics_daily")
    conn.execute(
        "INSERT INTO analytics_daily (date, followers, connections, profile_views) VALUES ('2020-01-01', 7777, 555, 10)"
    )
    conn.commit()
    conn.close()

    linkedin_client.linkedin_client.ingest_analytics_payload({"profile_views": 99})

    conn = database.get_db()
    row = conn.execute(
        "SELECT followers, connections FROM analytics_daily WHERE date = ?", (today,)
    ).fetchone()
    conn.close()

    assert row["followers"] == 7777, "The last known follower count should carry forward"
    assert row["connections"] == 555


def test_kpi_dashboard_survives_a_profile_views_only_ingest(isolated_studio):
    """Verifies the analytics dashboard still answers 200 after a partial ingest."""
    database, linkedin_client = isolated_studio

    conn = database.get_db()
    conn.execute("DELETE FROM analytics_daily")
    conn.commit()
    conn.close()

    linkedin_client.linkedin_client.ingest_analytics_payload({"profile_views": 42})

    from fastapi.testclient import TestClient
    import app as app_module
    importlib.reload(app_module)

    client = TestClient(app_module.app, raise_server_exceptions=False)
    res = client.get("/api/analytics/kpis")
    assert res.status_code == 200, (
        f"The KPI dashboard returned {res.status_code} after a profile views only ingest"
    )


def test_kpi_dashboard_handles_historical_null_followers_gracefully(isolated_studio):
    """Verifies that get_kpis returns 200 even if database has rows with NULL followers."""
    database, _ = isolated_studio
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    conn = database.get_db()
    conn.execute("DELETE FROM analytics_daily")
    conn.execute(
        "INSERT INTO analytics_daily (date, followers, connections, profile_views) VALUES (?, NULL, 100, NULL)",
        (today,)
    )
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    import app as app_module
    importlib.reload(app_module)

    client = TestClient(app_module.app, raise_server_exceptions=False)
    res = client.get("/api/analytics/kpis")
    assert res.status_code == 200
    data = res.json()
    assert "total_followers" in data
    assert data["total_followers"] == 2412
    assert "follower_growth" in data
    assert isinstance(data["follower_growth"], (int, float))
