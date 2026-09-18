"""
Phase 3 Verification Suite: Post-to-Lead Attribution & Enterprise Multi-Tenancy.
================================================================================
Validates:
1. Multi-tenant account_id column migration & indexes across core tables.
2. ReverseCRMManager.get_post_attribution metrics (leads count, VIP count, avg ICP, questions).
3. GET /api/v1/analytics/posts/{post_id}/leads API endpoint contracts.
4. GET /api/analytics/posts post leaderboard attribution correlation payload.
5. Frontend DOM integrity for post-attribution modal and analytics table headers.
6. Strict zero em-dash compliance across Phase 3 files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
from crm import reverse_crm, ReverseCRMManager, ICPScoringEngine

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_db_initialized():
    """Ensure database schema and migrations are initialized."""
    init_db()


def test_phase3_multitenant_schema_migration():
    """Verify account_id column and indices exist across tables."""
    conn = get_db()
    cursor = conn.cursor()
    target_tables = ["posts", "drafts", "leads", "lead_interactions", "settings"]

    for tbl in target_tables:
        cursor.execute(f"PRAGMA table_info({tbl})")
        cols = {row["name"]: row for row in cursor.fetchall()}
        assert "account_id" in cols, f"Missing account_id column in {tbl}"
        assert cols["account_id"]["dflt_value"] in ["'default'", "default"]

    # Verify indices
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    idx_names = {row["name"] for row in cursor.fetchall()}
    assert "idx_posts_account" in idx_names
    assert "idx_drafts_account" in idx_names
    assert "idx_leads_account" in idx_names
    assert "idx_interactions_account" in idx_names
    conn.close()


def test_phase3_post_attribution_calculation():
    """Verify ReverseCRMManager.get_post_attribution calculates correct metrics."""
    test_post_urn = "urn:li:activity:990011223344"

    # Ingest 3 diverse engagers for this post
    reverse_crm.ingest_interaction(
        full_name="Elena Rostova",
        linkedin_urn="urn:li:person:elena-phase3",
        headline="Chief AI Officer & VP of Engineering at ScaleForge",
        company="ScaleForge",
        interaction_type="COMMENT",
        comment_text="How does this decoupled ingestion pipeline handle high concurrency bursts?",
        post_urn=test_post_urn,
        post_topic="distributed memory architecture"
    )

    reverse_crm.ingest_interaction(
        full_name="Marcus Vance",
        linkedin_urn="urn:li:person:marcus-phase3",
        headline="Senior Distributed Systems Architect",
        company="Nexus Infrastructure",
        interaction_type="COMMENT",
        comment_text="Great point regarding write-actor serialization.",
        post_urn=test_post_urn,
        post_topic="distributed memory architecture"
    )

    reverse_crm.ingest_interaction(
        full_name="Alex Rivera",
        linkedin_urn="urn:li:person:alex-phase3",
        headline="Software Engineering Student at Tech Academy",
        company="",
        interaction_type="LIKE",
        comment_text="",
        post_urn=test_post_urn,
        post_topic="distributed memory architecture"
    )

    # Compute attribution
    attr = reverse_crm.get_post_attribution(test_post_urn)
    assert attr["status"] == "success"
    summary = attr["attribution_summary"]

    assert summary["total_leads_generated"] >= 3
    assert summary["vip_leads_count"] >= 1  # Elena Rostova is C-level / VP
    assert summary["questions_count"] >= 1  # Elena's comment contained a question mark
    assert summary["avg_icp_score"] > 0.0
    assert summary["comments_count"] >= 2
    assert summary["likes_count"] >= 1

    # Verify leads dossier contents
    leads = attr["leads"]
    assert len(leads) >= 3
    elena = next((l for l in leads if "Elena" in l["name"]), None)
    assert elena is not None
    assert elena["qualification_tier"] in ["VIP", "TIER_1_VIP", "QUALIFIED"]
    assert elena["seniority_level"] in ["C-Suite", "VP / SVP / EVP"]
    assert len(elena["suggested_dm"]) > 20
    assert "\u2014" not in elena["suggested_dm"]


def test_phase3_api_post_attribution_endpoint():
    """Verify GET /api/v1/analytics/posts/{post_id}/leads endpoint."""
    test_post_urn = "urn:li:activity:990011223344"
    resp = client.get(f"/api/v1/analytics/posts/{test_post_urn}/leads")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert "attribution_summary" in data
    assert "leads" in data
    assert data["attribution_summary"]["total_leads_generated"] >= 3


def test_phase3_api_analytics_posts_leaderboard_attribution():
    """Verify GET /api/analytics/posts returns attribution summary for each post."""
    resp = client.get("/api/analytics/posts")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    posts = data["posts"]
    assert len(posts) >= 1

    for p in posts:
        assert "attribution" in p
        attr = p["attribution"]
        assert "total_leads" in attr
        assert "vip_leads" in attr
        assert "avg_icp" in attr


def test_phase3_frontend_dom_and_js_integrity():
    """Verify post-attribution modal and table structures in frontend files."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    html_path = os.path.join(base_dir, "studio", "frontend", "index.html")
    js_path = os.path.join(base_dir, "studio", "frontend", "app.js")

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # Modal and table headers in HTML
    assert 'id="post-attribution-modal"' in html
    assert 'id="post-attr-leads-tbody"' in html
    assert '<th>Attributed Leads</th>' in html

    # JS rendering and interaction functions
    assert "renderAnalyticsPostsTable" in js
    assert "openPostAttributionModal" in js
    assert "initPostAttributionModal" in js


def test_phase3_zero_em_dashes_compliance():
    """Strict verification: Zero literal em-dashes in Phase 3 files."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    phase3_files = [
        os.path.join(base_dir, "studio", "backend", "crm.py"),
        os.path.join(base_dir, "studio", "backend", "database.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "studio", "frontend", "index.html"),
        os.path.join(base_dir, "studio", "frontend", "app.js"),
        os.path.join(base_dir, "tests", "test_phase3_attribution_multitenancy.py"),
    ]

    for fpath in phase3_files:
        assert os.path.exists(fpath), f"File {fpath} not found"
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "\u2014" not in content, f"Forbidden em-dash character found in {fpath}"
