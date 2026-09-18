"""
Enterprise Reverse CRM & Deterministic ICP Scoring Deep-Dive Test Suite.
========================================================================
Validates:
1. 4-factor deterministic scoring math: Ws, Wi, Wc, Wq and contribution points.
2. Boundary clamping: [0.0, 100.0] floor and ceiling guarantees.
3. Intent signal extraction & qualification tiers (TIER_1_VIP, QUALIFIED, NURTURE, DISQUALIFIED).
4. Contextual anti-slop DM variants (3 distinct strategic angles) with zero em-dashes.
5. Macro CRM telemetry engine: totals, funnel, seniority, and inquiry metrics.
6. FastAPI endpoints: /api/v1/crm/telemetry, /api/v1/crm/dm/variants, /api/v1/crm/score-preview.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from crm import ICPScoringEngine, ReverseCRMManager, reverse_crm
from database import get_db, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_db_initialized():
    """Ensure database tables and schema migrations are initialized."""
    init_db()


def test_icp_factor_weights_and_clamping():
    """Validates individual factor weights and deterministic [0.0, 100.0] clamping."""
    # 1. Seniority weights (W_s: -40.0 to 100.0)
    assert ICPScoringEngine.calculate_seniority_weight("Founder & CEO") == 100.0
    assert ICPScoringEngine.calculate_seniority_weight("Chief Technology Officer") == 90.0
    assert ICPScoringEngine.calculate_seniority_weight("VP of Engineering") == 75.0
    assert ICPScoringEngine.calculate_seniority_weight("Staff Software Engineer") == 50.0
    assert ICPScoringEngine.calculate_seniority_weight("Software Engineer") == 20.0
    assert ICPScoringEngine.calculate_seniority_weight("Student Intern") == -40.0

    # 2. Interaction depth weights (W_i: 15.0 to 100.0)
    long_comment = "This is a detailed technical analysis comparing SQLite write path with cloud Postgres RDS latency benchmarks for our stack."
    assert ICPScoringEngine.calculate_interaction_weight("COMMENT", long_comment) == 100.0
    medium_comment = "How do you handle WAL checkpoints?"
    assert ICPScoringEngine.calculate_interaction_weight("COMMENT", medium_comment) == 60.0
    short_comment = "Great post!"
    assert ICPScoringEngine.calculate_interaction_weight("COMMENT", short_comment) == 30.0
    assert ICPScoringEngine.calculate_interaction_weight("REPOST") == 50.0
    assert ICPScoringEngine.calculate_interaction_weight("LIKE") == 15.0

    # 3. Company weights (W_c: 0.0 to 80.0)
    assert ICPScoringEngine.calculate_company_weight("Scale AI") == 80.0
    assert ICPScoringEngine.calculate_company_weight("Fintech Infra Labs") == 80.0
    assert ICPScoringEngine.calculate_company_weight("Retail Store") == 50.0
    assert ICPScoringEngine.calculate_company_weight("") == 0.0
    assert ICPScoringEngine.calculate_company_weight(None) == 0.0

    # 4. Question weights (W_q: 0.0 or 100.0)
    assert ICPScoringEngine.calculate_question_weight("Can we run this locally?") == 100.0
    assert ICPScoringEngine.calculate_question_weight("Looks solid.") == 0.0

    # 5. Boundary clamping guarantees
    # Negative raw score clamped to 0.0
    neg_score = ICPScoringEngine.calculate_icp_score(
        headline="Student seeking opportunities",
        company=None,
        comment_text=None,
        interaction_type="LIKE"
    )
    assert neg_score == 0.0

    # Maximum score bounded at [0.0, 100.0]
    high_comment = "We benchmarked this across 1000 nodes on production, but how do you handle concurrent WAL checkpoints without any write lock contention?"
    max_score = ICPScoringEngine.calculate_icp_score(
        headline="Founder & CEO",
        company="Enterprise AI Systems",
        comment_text=high_comment,
        interaction_type="COMMENT"
    )
    # Ws (100*0.45=45) + Wi (100*0.30=30) + Wc (80*0.15=12) + Wq (100*0.10=10) = 97.0
    assert max_score == 97.0
    assert 0.0 <= max_score <= 100.0


def test_icp_breakdown_contributions_and_intent_signals():
    """Validates granular point breakdown, qualification tiers, and intent signal extraction."""
    # VIP Enterprise Founder inquiry
    comment = "How does your local SQLite engine maintain consistency during high frequency concurrent ingress?"
    breakdown = ICPScoringEngine.calculate_icp_breakdown(
        headline="Founder & Chief Executive Officer",
        company="Fintech Scale Platform",
        comment_text=comment,
        interaction_type="COMMENT"
    )

    assert breakdown["seniority_level"] == "Founder"
    assert breakdown["qualification_tier"] == "TIER_1_VIP"
    assert breakdown["icp_score"] >= 80.0
    assert breakdown["contributions"]["seniority_points"] == 45.0  # 100.0 * 0.45
    assert breakdown["contributions"]["interaction_points"] == 60.0 * 0.30  # 12 words -> 60 * 0.30 = 18.0
    assert breakdown["contributions"]["company_points"] == 80.0 * 0.15  # 12.0
    assert breakdown["contributions"]["question_points"] == 100.0 * 0.10  # 10.0

    # Intent signals verification
    signals = breakdown["intent_signals"]
    assert "EXECUTIVE_DECISION_MAKER" in signals
    assert "DIRECT_BUYING_INQUIRY" in signals
    assert "TIER_1_ENTERPRISE_AFFINITY" in signals

    # Disqualified student lead
    student_breakdown = ICPScoringEngine.calculate_icp_breakdown(
        headline="University Student Intern",
        company=None,
        comment_text="Nice",
        interaction_type="COMMENT"
    )
    assert student_breakdown["qualification_tier"] == "DISQUALIFIED"
    assert "STUDENT_OR_SEEKER" in student_breakdown["intent_signals"]


def test_anti_slop_dm_variants_and_zero_em_dashes():
    """Validates 3 anti-slop DM angles, personalizations, and strict zero em-dash compliance."""
    variants = ICPScoringEngine.generate_anti_slop_dm_variants(
        lead_name="Alexander Hamilton",
        comment_text="What is the average latency for local IPC messages?",
        post_topic="sovereign desktop architecture",
        custom_insight="We measured 0.4ms round-trip via local loopback sockets."
    )

    assert len(variants) == 3
    angles = [v["angle"] for v in variants]
    assert "Direct Technical Perspective" in angles
    assert "Architecture Teardown" in angles
    assert "Peer-to-Peer Exchange" in angles

    for v in variants:
        dm_text = v["dm_text"]
        # Invariant: Strictly zero em-dashes
        assert "\u2014" not in dm_text, f"Found illegal em-dash in variant {v['angle']}: {dm_text}"
        # Invariant: Personalized with first name
        assert "Alexander" in dm_text

    # Invariant: Quoting comment excerpt in direct technical and architectural angles
    assert "latency" in variants[0]["dm_text"].lower()
    assert "latency" in variants[1]["dm_text"].lower()


def test_macro_crm_telemetry_aggregation():
    """Validates ReverseCRMManager.get_crm_telemetry on ingested leads and interactions."""
    # Ingest distinct test leads
    v1 = reverse_crm.ingest_interaction(
        full_name="Sarah Connor",
        linkedin_urn="urn:li:person:sarah_telemetry_test",
        headline="CTO & Co-Founder",
        company="Cloud Security Systems",
        interaction_type="COMMENT",
        comment_text="How do you manage cryptographic key rotation on Windows?",
        post_topic="Windows DPAPI Security"
    )

    v2 = reverse_crm.ingest_interaction(
        full_name="John Doe",
        linkedin_urn="urn:li:person:john_telemetry_test",
        headline="Staff Platform Engineer",
        company="Enterprise Scale Corp",
        interaction_type="COMMENT",
        comment_text="Excellent teardown of the WAL concurrency model.",
        post_topic="SQLite Concurrency"
    )

    v3 = reverse_crm.ingest_interaction(
        full_name="Junior Dev",
        linkedin_urn="urn:li:person:junior_telemetry_test",
        headline="Student seeking internship",
        company=None,
        interaction_type="LIKE"
    )

    telemetry = reverse_crm.get_crm_telemetry()
    assert telemetry["status"] == "success"

    summary = telemetry["summary"]
    assert summary["total_leads"] >= 3
    assert summary["high_value_leads"] >= 1
    assert summary["avg_icp_score"] > 0.0
    assert summary["avg_interactions_per_lead"] > 0.0

    funnel = telemetry["funnel"]
    for expected_key in ["NEW", "ENGAGED", "DM_DRAFTED", "DM_SENT", "CONVERTED", "ARCHIVED"]:
        assert expected_key in funnel

    inquiry = telemetry["inquiry_telemetry"]
    assert inquiry["total_interactions"] >= 3
    assert inquiry["questions_count"] >= 1
    assert inquiry["question_inquiry_rate_pct"] > 0.0

    sen_dist = telemetry["seniority_distribution"]
    assert "C-Suite" in sen_dist or "Founder" in sen_dist
    assert "Student/Intern" in sen_dist


def test_fastapi_crm_endpoints():
    """Validates FastAPI CRM endpoints: /telemetry, /dm/variants, and /score-preview."""
    # 1. Telemetry endpoint
    r_telem = client.get("/api/v1/crm/telemetry")
    assert r_telem.status_code == 200
    t_data = r_telem.json()
    assert t_data["status"] == "success"
    assert "summary" in t_data
    assert "funnel" in t_data
    assert "seniority_distribution" in t_data
    assert "inquiry_telemetry" in t_data

    # 2. DM Variants endpoint
    r_dm = client.post("/api/v1/crm/dm/variants", json={
        "lead_name": "Elena Rostova",
        "comment_text": "Is SQLite WAL fast enough for real-time telemetry streaming?",
        "post_topic": "real-time telemetry"
    })
    assert r_dm.status_code == 200
    dm_data = r_dm.json()
    assert dm_data["status"] == "success"
    assert len(dm_data["variants"]) == 3
    for var in dm_data["variants"]:
        assert "\u2014" not in var["dm_text"]

    # 3. Enhanced Score Preview endpoint
    r_score = client.post("/api/v1/crm/score-preview", json={
        "headline": "Managing Director & Partner",
        "company": "Enterprise Fintech Labs",
        "comment_text": "Could you share the memory profiling numbers?",
        "interaction_type": "COMMENT"
    })
    assert r_score.status_code == 200
    s_data = r_score.json()
    assert s_data["status"] == "success"
    assert s_data["icp_score"] >= 80.0
    assert s_data["qualification_tier"] == "TIER_1_VIP"
    assert "contributions" in s_data
    assert "intent_signals" in s_data
    assert "EXECUTIVE_DECISION_MAKER" in s_data["intent_signals"]
    assert "DIRECT_BUYING_INQUIRY" in s_data["intent_signals"]
