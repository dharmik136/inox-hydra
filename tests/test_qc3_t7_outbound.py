"""
Outbound: who has gone quiet.
==============================

Cycle 3, batch T7, decision D4. The research found target_author NULL in
all 44,000 archive-imported outbound_engagements rows (archive_import.py
hard-codes it, because LinkedIn's Comments.csv and Reactions.csv carry no
author), but own_pages.js's live DOM capture (cardActorName, read while the
creator's own Activity page is open) does send one, and onboarding.py's
ingest_outbound writes whatever it is sent. So the gap is the archive leg
only, and the section is rebuilt rather than cut.

This adds the one thing the rebuilt section needed and did not have:
"gone quiet", someone who has engaged back before but not on any of your
posts in a while. It needs the same coverage requirement as "one-way"
(test_insights.py), because the studio cannot call an account quiet from
engagers it never read, and it must not be said about someone who has never
once engaged back, which is "one-way"'s claim, not this one's.
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
ME = "outbound-quiet-probe-creator"
TABLES = ("creator_identity", "own_posts", "post_metric_observations", "outbound_engagements")


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
            for (lead_id,) in conn.execute("SELECT id FROM leads WHERE name LIKE 'QuietProbe%'").fetchall():
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


def _age_lead_interaction(name, days):
    stamp = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = get_db()
    with conn:
        conn.execute(
            "UPDATE lead_interactions SET interacted_at = ? "
            "WHERE lead_id IN (SELECT id FROM leads WHERE name = ?)",
            (stamp, name),
        )
    conn.close()


def test_gone_quiet_is_not_said_before_the_studio_has_looked():
    _confirm()
    reverse_crm.ingest_interaction("QuietProbe Stranger", "https://www.linkedin.com/in/quietprobe-stranger",
                                    "Engineer", None, "COMMENT", "Nice.", post_urn=urn_days_ago(20, 1))
    _age_lead_interaction("QuietProbe Stranger", 90)
    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(3, 1), "kind": "reaction", "target_author": "QuietProbe Stranger"}]})
    data = client.get("/api/v1/insights/outbound").json()
    assert data["coverage"]["one_way_judged"] is False
    assert data["gone_quiet"] == []


def test_gone_quiet_names_someone_who_used_to_engage_back_and_stopped():
    _confirm()
    post = urn_days_ago(60, 1)
    _post(post, 10)
    # The interaction that both makes the studio count this post's engagers
    # as read (for coverage) and makes QuietProbe Regular's engagement a
    # reciprocal one (it is on your post).
    reverse_crm.ingest_interaction("QuietProbe Regular", "https://www.linkedin.com/in/quietprobe-regular",
                                    "Engineer", None, "COMMENT", "Great post.", post_urn=post)
    _age_lead_interaction("QuietProbe Regular", 90)
    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(3, i), "kind": "reaction", "target_author": "QuietProbe Regular"}
        for i in range(2)]})

    data = client.get("/api/v1/insights/outbound").json()
    assert data["coverage"]["one_way_judged"] is True
    quiet = {row["name"]: row["days_since"] for row in data["gone_quiet"]}
    assert "QuietProbe Regular" in quiet, data["gone_quiet"]
    assert quiet["QuietProbe Regular"] >= 45
    assert "QuietProbe Regular" in data["reciprocal"], "quiet is still reciprocal: they did come back, once"
    assert data["gone_quiet_days"] == 45


def test_gone_quiet_is_not_said_about_someone_who_never_engaged_back():
    _confirm()
    post = urn_days_ago(60, 1)
    _post(post, 10)
    reverse_crm.ingest_interaction("QuietProbe Anchor", "https://www.linkedin.com/in/quietprobe-anchor",
                                    "Engineer", None, "COMMENT", "Great post.", post_urn=post)
    client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": [
        {"target_activity_urn": urn_days_ago(3, i), "kind": "reaction", "target_author": "QuietProbe Never Back"}
        for i in range(5)]})
    data = client.get("/api/v1/insights/outbound").json()
    assert data["coverage"]["one_way_judged"] is True
    assert "QuietProbe Never Back" not in {row["name"] for row in data["gone_quiet"]}
    assert "QuietProbe Never Back" in data["one_way"]
