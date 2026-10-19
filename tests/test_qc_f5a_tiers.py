"""
VIP means one thing everywhere.
===============================

The CRM, the CSV and the dossier call a lead VIP from an ICP score of 80. A
post's attribution and the Analytics leaderboard counted VIPs from 75, and
also from seniority labels ("VP / SVP / EVP", "Founder / Owner") the scorer
never produces. A 75.8 lead was VIP on the post and QUALIFIED in the same
response.
"""

import os
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

POST_ID = "post-qc-tiers"
POST_URN = "urn:li:activity:7382000000000000001"


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_tiers_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import get_db, init_db
    from crm import reverse_crm
    from fastapi.testclient import TestClient
    import app as app_module

    init_db()
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (id, content, status, published_at, impressions, activity_urn) "
        "VALUES (?, 'A post', 'published', '2026-10-01T10:00:00Z', 900, ?)",
        (POST_ID, POST_URN),
    )
    conn.commit()
    conn.close()
    lead = reverse_crm.ingest_interaction(
        full_name="Dana Head",
        linkedin_urn="https://www.linkedin.com/in/dana-head",
        headline="Head of Data at Cloud Platform",
        company="Cloud Platform",
        interaction_type="COMMENT",
        comment_text="This matches what we saw when we rebuilt our pipeline last quarter across three regions and two vendors",
        post_urn=POST_URN,
    )
    assert 75 <= lead["icp_score"] < 80 and lead["tier"] == "QUALIFIED", lead
    return TestClient(app_module.app)


def test_a_qualified_lead_is_not_a_vip_on_the_post(client):
    summary = client.get(f"/api/v1/analytics/posts/{POST_ID}/leads").json()
    assert summary["leads"][0]["qualification_tier"] == "QUALIFIED"
    assert summary["attribution_summary"]["vip_leads_count"] == 0, summary["attribution_summary"]


def test_a_qualified_lead_is_not_a_vip_on_the_leaderboard(client):
    posts = client.get("/api/analytics/posts").json()["posts"]
    row = next(p for p in posts if p["id"] == POST_ID)
    assert row["attribution"]["total_leads"] == 1
    assert row["attribution"]["vip_leads"] == 0, row["attribution"]


def test_a_c_suite_title_alone_is_not_a_vip(client):
    """Seniority was a second, undocumented route to VIP; the tier is the only rule."""
    from crm import reverse_crm

    reverse_crm.ingest_interaction(
        full_name="Casey Chief",
        linkedin_urn="https://www.linkedin.com/in/casey-chief",
        headline="CEO",
        interaction_type="LIKE",
        post_urn=POST_URN,
    )
    summary = client.get(f"/api/v1/analytics/posts/{POST_ID}/leads").json()
    casey = next(l for l in summary["leads"] if l["name"] == "Casey Chief")
    assert casey["seniority_level"] == "C-Suite" and casey["qualification_tier"] != "TIER_1_VIP"
    assert summary["attribution_summary"]["vip_leads_count"] == 0
