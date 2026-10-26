"""
Today asks for the readings a settle curve needs, from visits made anyway.
==========================================================================

Cycle 4, track 1, item 10. Four points matter for a post: about 2 hours,
24 hours, 48 hours and 7 days. The natural visits give the first three; the
day-7 point and the Activity page visit were never asked for. Two rules in
_open_next now ask for them, and the first-hours ask says what it is for.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from database import get_db

client = TestClient(app_module.app)
ME = "cadence-probe-creator"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "self_import_requests",
          "bridge_heartbeats", "captures")


def urn_hours_ago(hours, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(hours=hours)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        with conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
        conn.close()
    wipe()
    yield
    wipe()


def _ready(latest_hours):
    """A confirmed creator whose history is read, the bridge alive, one post."""
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Cadence Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    urn = urn_hours_ago(latest_hours, 3)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'A post', ?, ?, ?)",
                     (urn, (datetime.now(timezone.utc) - timedelta(hours=latest_hours)).isoformat(), now, now))
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, finished_at, items_seen, outcome) "
                     "VALUES ('posts', ?, ?, 5, 'end_of_list')", (now, now))
    conn.close()
    return urn


def _reading(urn, age_hours, hours_ago=None, source="post_analytics"):
    observed = datetime.now(timezone.utc) - timedelta(hours=hours_ago if hours_ago is not None else 0)
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, "
                     "source, impressions) VALUES (?, ?, ?, ?, ?, 100)",
                     (urn, observed.isoformat(), observed.strftime("%Y-%m-%dT%H"), age_hours, source))
    conn.close()


def _good_activity_read(days_ago):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept) "
                     "VALUES (?, 'activity_posts', 'activity_posts', 8, 8)", (when.isoformat(),))
    conn.close()


def _open_next():
    return client.get("/api/v1/today").json()["open_next"]


def test_a_post_with_no_reading_yet_is_asked_for_in_its_first_hours():
    urn = _ready(latest_hours=3)
    _good_activity_read(1)
    step = _open_next()
    assert step["action"] == "open" and step["url"].endswith(f"/analytics/post-summary/{urn}/")
    assert "first hours" in step["reason"]


def test_a_week_old_post_without_a_week_old_reading_is_asked_for():
    urn = _ready(latest_hours=170)
    _good_activity_read(1)
    _reading(urn, age_hours=48.0, hours_ago=122)
    step = _open_next()
    assert step["action"] == "open" and step["url"].endswith(f"/analytics/post-summary/{urn}/")
    assert "week" in step["reason"] and "settle" in step["reason"]


def test_a_week_old_post_already_read_at_a_week_is_not_asked_again():
    urn = _ready(latest_hours=170)
    _good_activity_read(1)
    _reading(urn, age_hours=48.0, hours_ago=122)
    _reading(urn, age_hours=150.0, hours_ago=20)
    step = _open_next()
    assert "settle" not in step["reason"]


def test_a_post_older_than_ten_days_is_past_the_week_ask():
    urn = _ready(latest_hours=260)
    _good_activity_read(1)
    step = _open_next()
    assert "settle" not in step["reason"]


def test_the_activity_page_is_asked_for_weekly():
    _ready(latest_hours=400)
    _good_activity_read(8)
    step = _open_next()
    assert step["action"] == "open"
    assert step["url"].endswith(f"/in/{ME}/recent-activity/all/")
    assert "week" in step["reason"].lower()


def test_an_activity_page_read_this_week_is_not_asked_for():
    _ready(latest_hours=400)
    _good_activity_read(2)
    step = _open_next()
    assert "recent-activity" not in step.get("url", "")


def test_the_day_seven_ask_comes_before_the_weekly_activity_ask():
    """A post at its one week point is the scarcer reading."""
    urn = _ready(latest_hours=170)
    _good_activity_read(9)
    step = _open_next()
    assert step["url"].endswith(f"/analytics/post-summary/{urn}/")
