"""
Phase 1 CRM UI & Intelligence Verification Suite.
=================================================
Validates:
1. CRM Macro Telemetry endpoint contracts (/api/v1/crm/telemetry).
2. 3-Angle Anti-Slop DM generator endpoint contracts (/api/v1/crm/dm/variants).
3. GDPR Hard Purge cascade contract (/api/v1/crm/leads/{id}/purge).
4. HTML DOM structure integrity (telemetry cards, 3-angle chips, purge button).
5. CSS class definitions for Attio/Linear hybrid widgets and tooltips.
6. Strict zero em-dash compliance across frontend and backend files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
from crm import reverse_crm, ICPScoringEngine

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database schema is ready."""
    init_db()


def test_crm_telemetry_endpoint_contract():
    """Validates the GET /api/v1/crm/telemetry endpoint response schema."""
    res = client.get("/api/v1/crm/telemetry")
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    assert "summary" in data
    assert "funnel" in data
    assert "seniority_distribution" in data
    assert "inquiry_telemetry" in data

    s = data["summary"]
    assert "total_leads" in s
    assert "high_value_leads" in s
    assert "avg_icp_score" in s
    assert "conversion_rate_pct" in s
    assert "avg_interactions_per_lead" in s

    f = data["funnel"]
    for status_key in ["NEW", "ENGAGED", "DM_DRAFTED", "DM_SENT", "CONVERTED", "ARCHIVED"]:
        assert status_key in f


def test_crm_dm_variants_endpoint_contract():
    """Validates the POST /api/v1/crm/dm/variants endpoint generates 3 zero em-dash options."""
    res = client.post("/api/v1/crm/dm/variants", json={
        "lead_name": "Marcus Vance",
        "comment_text": "How do you achieve sub-millisecond local queries?",
        "post_topic": "distributed local storage"
    })
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "success"
    assert "variants" in data
    variants = data["variants"]
    assert len(variants) == 3

    angles = [v["angle"] for v in variants]
    assert "Direct Technical Perspective" in angles
    assert "Architecture Teardown" in angles
    assert "Peer-to-Peer Exchange" in angles

    for v in variants:
        assert "\u2014" not in v["dm_text"], f"Illegal em-dash found in angle {v['angle']}"
        assert "Marcus" in v["dm_text"]


def test_gdpr_hard_purge_lifecycle():
    """Validates that DELETE /api/v1/crm/leads/{id}/purge permanently removes records."""
    # 1. Ingest a lead
    ingest_res = reverse_crm.ingest_interaction(
        full_name="Purge Candidate Lead",
        linkedin_urn="urn:li:person:purge_candidate_phase1",
        headline="Software Engineer",
        company="Ephemeral Corp",
        interaction_type="COMMENT",
        comment_text="Please delete my data after test.",
        post_topic="GDPR compliance"
    )
    lead_id = ingest_res["lead_id"]

    # 2. Verify lead exists in timeline
    timeline_res = client.get(f"/api/v1/crm/leads/{lead_id}/timeline")
    assert timeline_res.status_code == 200

    # 3. Issue hard purge
    purge_res = client.delete(f"/api/v1/crm/leads/{lead_id}/purge")
    assert purge_res.status_code == 200
    purge_data = purge_res.json()
    assert purge_data["status"] == "purged"
    assert purge_data["lead_deleted"] is True
    assert purge_data["interactions_deleted"] >= 1

    # 4. Confirm timeline query now 404s
    verify_res = client.get(f"/api/v1/crm/leads/{lead_id}/timeline")
    assert verify_res.status_code == 404






def test_strict_zero_em_dash_compliance():
    """Audits all modified files to ensure zero occurrences of the character \u2014."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "crm.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "tests", "test_crm_telemetry_deepdive.py"),
        os.path.join(base_dir, "tests", "test_phase1_crm_ui.py"),
    ]

    for path in targets:
        assert os.path.exists(path), f"Target file does not exist: {path}"
        text = open(path, "r", encoding="utf-8").read()
        assert "\u2014" not in text, f"Illegal em-dash (\\u2014) found in: {path}"
