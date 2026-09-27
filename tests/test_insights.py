"""
Posts and Outbound, and the lead history they stand on.
=======================================================

The rules each screen keeps:

  Posts     a post is compared with your own median only once it is a week
            old, the median is taken from week-old posts only, and "worth
            repurposing" goes to the two furthest above it.
  Outbound  "one-way" is not said until the studio has read who engaged with
            at least half your posts. Measured on the first live install: one
            engager captured, and every top account would have been listed.
  Leads     a status change is kept as history, and Posts counts the people
            from each post who reached Connected or Meeting Booked.
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
from leads import update_lead_status

client = TestClient(app_module.app)
ME = "insights-probe-creator"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "outbound_engagements", "lead_stage_events")


def urn_days_ago(days, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        with conn:
            for table in TABLES:
                conn.execute(f"DELETE FROM {table}")
            for (lead_id,) in conn.execute("SELECT id FROM leads WHERE name LIKE 'InsightProbe%'").fetchall():
                conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
                conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.close()
    wipe()
    yield
    wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"]})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})


def _post(urn, reactions):
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": f"Post with {reactions}", "reactions": reactions}]})


def test_the_usual_is_the_median_of_settled_posts_only():
    _confirm()
    for i, reactions in enumerate((10, 20, 30, 40)):
        _post(urn_days_ago(20 + i, i), reactions)
    _post(urn_days_ago(1, 9), 900)   # a young post, not yet part of the usual

    data = client.get("/api/v1/insights/posts").json()
    assert data["usual"]["reactions"]["median"] == 25
    young = next(p for p in data["posts"] if p["reactions"] == 900)
    assert young["settled"] is False and young["against_usual"] is None


def test_the_best_two_settled_posts_are_worth_repurposing():
    _confirm()
    urns = [urn_days_ago(20 + i, i) for i in range(4)]
    for urn, reactions in zip(urns, (10, 60, 30, 45)):
        _post(urn, reactions)
    assert client.get("/api/v1/insights/posts").json()["best"] == [urns[1], urns[3]]


def test_one_way_is_not_said_before_the_studio_has_looked():
    _confirm()
    _post(urn_days_ago(20, 1), 10)
    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(3, i), "kind": "reaction", "target_author": "Frequent Author"}
        for i in range(5)]})
    data = client.get("/api/v1/insights/outbound").json()
    assert data["authors"][0]["name"] == "Frequent Author" and data["authors"][0]["total"] == 5
    assert data["coverage"]["one_way_judged"] is False
    assert data["one_way"] == []


def test_one_way_is_said_once_your_posts_have_been_read():
    _confirm()
    post = urn_days_ago(20, 1)
    _post(post, 10)
    reverse_crm.ingest_interaction("InsightProbe Reader", "https://www.linkedin.com/in/insightprobe-reader",
                                   "Engineer", None, "COMMENT", "Nice.", post_urn=post)
    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(3, i), "kind": "reaction", "target_author": "Frequent Author"}
        for i in range(3)] + [
        {"target_activity_urn": urn_days_ago(4, 9), "kind": "reaction", "target_author": "InsightProbe Reader"}]})
    data = client.get("/api/v1/insights/outbound").json()
    assert data["coverage"]["one_way_judged"] is True
    assert "Frequent Author" in data["one_way"]
    assert "InsightProbe Reader" in data["reciprocal"]


def test_a_status_change_is_kept_and_counted_against_its_post():
    _confirm()
    post = urn_days_ago(20, 2)
    _post(post, 10)
    lead_id = reverse_crm.ingest_interaction(
        "InsightProbe Talker", "https://www.linkedin.com/in/insightprobe-talker", "Engineer", None,
        "COMMENT", "How did you do it?", post_urn=post)["lead_id"]

    update_lead_status(lead_id, "Outreach Sent")
    update_lead_status(lead_id, "Connected")
    update_lead_status(lead_id, "Connected")   # re-selecting is not a change

    history = client.get(f"/api/v1/crm/leads/{lead_id}/timeline").json()["stage_history"]
    assert [e["to_status"] for e in history] == ["Outreach Sent", "Connected"]

    row = next(p for p in client.get("/api/v1/insights/posts").json()["posts"] if p["activity_urn"] == post)
    assert row["people_count"] == 1 and row["conversations"] == 1
