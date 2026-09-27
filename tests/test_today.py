"""
Today, and the per-post readings it stands on.
==============================================

Two rules carry this screen, and each has a test:

  People are ordered by what they did, never by the ICP score: repeat
  engagement with your posts first, then a comment over a reaction, then
  recency. Anyone you have already answered drops off.

  Your latest post is compared with your usual only at the same age, about two
  days old, and only against enough earlier posts to mean something. When it
  cannot be compared fairly, the screen says why instead of showing a number.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from crm import reverse_crm
from database import get_db

client = TestClient(app_module.app)
ME = "today-probe-creator"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "self_import_requests",
          "bridge_heartbeats", "captures")


def urn_days_ago(days, salt=0):
    """A real-shaped activity URN whose embedded timestamp is `days` ago."""
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        with conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            ids = [r[0] for r in conn.execute("SELECT id FROM leads WHERE name LIKE 'TodayProbe%'")]
            for lead_id in ids:
                conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
                conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.close()
    wipe()
    yield
    wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Today Probe"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})


def _posts(*urns):
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": u, "actor": ME, "text": f"Post {i}"} for i, u in enumerate(urns)]})


def _reading(urn, age_hours, **metrics):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions, reactions, comments) VALUES (?,?,?,?,?,?,?,?)",
            (urn, datetime.now(timezone.utc).isoformat(), f"probe-{urn}-{age_hours}", age_hours, "activity_page",
             metrics.get("impressions"), metrics.get("reactions"), metrics.get("comments")))
    conn.close()


def _today():
    return client.get("/api/v1/today").json()


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------

def test_importing_posts_keeps_a_reading_with_the_posts_age():
    _confirm()
    urn = urn_days_ago(2)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "reactions": 30, "comments": 4}]})
    readings = app_module.onboarding.post_readings(urn)
    assert len(readings) == 1
    assert 47 <= readings[0]["age_hours"] <= 49
    assert readings[0]["reactions"] == 30 and readings[0]["impressions"] is None


def test_rereading_within_the_hour_does_not_add_readings():
    _confirm()
    urn = urn_days_ago(2)
    for count in (30, 31, 32):
        client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
            {"activity_urn": urn, "actor": ME, "reactions": count}]})
    readings = app_module.onboarding.post_readings(urn)
    assert len(readings) == 1 and readings[0]["reactions"] == 32


def test_post_analytics_are_kept_only_for_your_recorded_posts():
    _confirm()
    mine = urn_days_ago(1)
    _posts(mine)
    ok = client.post("/api/v1/self/posts/analytics", json={
        "author": ME, "activity_urn": mine, "metrics": {"impressions": 4100, "members_reached": 2900, "saves": 12}})
    assert ok.json()["recorded"] is True
    stranger = client.post("/api/v1/self/posts/analytics", json={
        "author": ME, "activity_urn": urn_days_ago(3), "metrics": {"impressions": 99}})
    assert stranger.status_code == 409


# ---------------------------------------------------------------------------
# Who to reply to
# ---------------------------------------------------------------------------

def _engage(name, urn, kind="COMMENT", text="Good point."):
    return reverse_crm.ingest_interaction(
        name, f"https://www.linkedin.com/in/{name.lower().replace(' ', '-')}", "Engineer", None,
        kind, text if kind == "COMMENT" else None, post_urn=urn)["lead_id"]


def test_repeat_engagers_come_first_and_the_score_plays_no_part():
    _confirm()
    a, b = urn_days_ago(3, 1), urn_days_ago(6, 2)
    _posts(a, b)
    _engage("TodayProbe Once", a)
    _engage("TodayProbe Twice", a)
    _engage("TodayProbe Twice", b)

    names = [p["name"] for p in _today()["reply_to"]]
    assert names[:2] == ["TodayProbe Twice", "TodayProbe Once"]


def test_someone_you_answered_drops_off():
    _confirm()
    post = urn_days_ago(2, 3)
    _posts(post)
    lead_id = _engage("TodayProbe Answered", post)
    conn = get_db()
    with conn:
        conn.execute("UPDATE leads SET lead_status = 'DM_SENT' WHERE id = ?", (lead_id,))
    conn.close()
    assert "TodayProbe Answered" not in [p["name"] for p in _today()["reply_to"]]


def test_engagement_on_other_peoples_posts_is_not_listed():
    _confirm()
    _posts(urn_days_ago(2, 4))
    _engage("TodayProbe Elsewhere", urn_days_ago(5, 9))
    assert _today()["reply_to"] == []


# ---------------------------------------------------------------------------
# Your latest post against your usual
# ---------------------------------------------------------------------------

def test_the_latest_post_is_compared_at_the_same_age():
    _confirm()
    earlier = [urn_days_ago(d, d) for d in (10, 14, 18, 22)]
    latest = urn_days_ago(2.5, 7)
    _posts(latest, *earlier)
    for urn, reactions in zip(earlier, (20, 30, 40, 50)):
        _reading(urn, 47.0, reactions=reactions, impressions=reactions * 50)
        _reading(urn, 600.0, reactions=reactions * 3)   # later readings must not be used
    _reading(latest, 49.0, reactions=70, impressions=3500)

    compared = _today()["latest_post"]["comparison"]["reactions"]
    assert compared["this_post"] == 70
    assert compared["your_usual"] == 35, "the usual must be read at the same age, not at the latest reading"
    assert compared["posts_compared"] == 4
    assert compared["ratio"] == 2.0


def test_too_few_earlier_posts_is_said_not_shown():
    _confirm()
    earlier = urn_days_ago(10, 1)
    latest = urn_days_ago(2, 2)
    _posts(latest, earlier)
    _reading(earlier, 48.0, reactions=10)
    _reading(latest, 48.0, reactions=90)

    post = _today()["latest_post"]
    assert post["comparison"] is None
    assert "earlier posts" in post["not_compared_because"]


def test_a_new_post_is_too_new_to_compare():
    _confirm()
    _posts(urn_days_ago(0.2, 5))
    assert "too new" in _today()["latest_post"]["not_compared_because"]


# ---------------------------------------------------------------------------
# One page to open
# ---------------------------------------------------------------------------

def test_before_setup_the_only_thing_to_open_is_setup():
    assert _today()["open_next"]["action"] == "setup"


def test_a_fresh_post_sends_you_to_its_analytics_page():
    _confirm()
    latest = urn_days_ago(1, 6)
    _posts(latest)
    client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO self_import_requests (kind, requested_at, finished_at, outcome) "
                     "VALUES ('posts', ?, ?, 'completed')", (datetime.now(timezone.utc).isoformat(),) * 2)
    conn.close()

    step = _today()["open_next"]
    assert step["action"] == "open"
    assert step["url"].endswith(f"/analytics/post-summary/{latest}/")


def test_an_old_post_is_not_sent_to_read_its_analytics_too_late():
    """
    Found on a live install: a 13 day old post was told to open its analytics
    "to read it now", which cannot produce a two day reading.
    """
    _confirm()
    _posts(urn_days_ago(13, 8))
    reason = _today()["latest_post"]["not_compared_because"]
    assert "read it now" not in reason and "next post" in reason
