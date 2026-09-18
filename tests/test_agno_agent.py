"""
Inox Hydra: Agno Autonomous Lead Enrichment Multi-Agent Test Suite
===================================================================
Automated verification for:
1. LeadResearchAgent role taxonomy and enterprise friction identification.
2. IcebreakerAgent 3-angle generation and strict zero em-dash compliance.
3. EnrichmentOrchestrator SQLite persistence and dual-mode fallback.
4. REST API contract endpoints (POST /api/leads/{id}/enrich and GET /api/leads/{id}/enrichment).
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import init_db, seed_initial_data, get_db
from agno_agent import (
    LeadResearchAgent,
    IcebreakerAgent,
    EnrichmentOrchestrator,
    clean_no_em_dashes,
    agno_orchestrator
)

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    seed_initial_data()


def test_zero_em_dash_cleaner():
    dirty = "Architecture is key\u2014especially when decoupling legacy databases -- with zero downtime."
    cleaned = clean_no_em_dashes(dirty)
    assert "\u2014" not in cleaned
    assert "--" not in cleaned
    assert "especially when" in cleaned


def test_lead_research_agent():
    researcher = LeadResearchAgent()
    lead = {
        "name": "David Lin",
        "headline": "VP of Engineering at DataMesh",
        "company": "DataMesh",
        "notes": "Discussed distributed observability pipelines",
        "engagement_type": "Commented"
    }
    research = researcher.research(lead)
    assert research["name"] == "David Lin"
    assert research["company"] == "DataMesh"
    assert research["role_category"] == "engineering_leadership"
    assert "Kafka" in research["estimated_tech_stack"] or "Kubernetes" in research["estimated_tech_stack"]
    assert len(research["key_topics"]) >= 3
    assert len(research["friction_points"]) > 20
    assert "\u2014" not in research["friction_points"]


def test_icebreaker_agent_zero_em_dashes():
    researcher = LeadResearchAgent()
    icebreaker = IcebreakerAgent()
    lead = {
        "name": "Sarah Jenkins",
        "headline": "Principal Enterprise Architect at FinNexus",
        "company": "FinNexus",
        "notes": "Looking into zero downtime schema migration",
        "engagement_type": "Liked"
    }
    research = researcher.research(lead)
    angles = icebreaker.generate_icebreakers(research)

    assert len(angles) == 3, f"Expected 3 icebreaker angles, got {len(angles)}"
    for idx, angle in enumerate(angles):
        assert "\u2014" not in angle, f"Angle {idx+1} contains forbidden em-dash!"
        assert "--" not in angle, f"Angle {idx+1} contains forbidden double-dash!"
        assert len(angle) > 40, f"Angle {idx+1} unexpectedly short"


def test_orchestrator_enrichment_persistence():
    orchestrator = EnrichmentOrchestrator()
    # Test existing seeded lead
    res = orchestrator.enrich_lead("lead-1")
    assert res["status"] == "success"
    enrichment = res["enrichment"]
    assert enrichment["lead_id"] == "lead-1"
    assert len(enrichment["icebreakers"]) == 3
    assert enrichment["enriched_by"] in ["agno_local", "gemini_2_5_flash"]

    # Verify directly from SQLite
    saved = orchestrator.get_enrichment("lead-1")
    assert saved is not None
    assert saved["lead_id"] == "lead-1"
    assert isinstance(saved["key_topics"], list)
    assert isinstance(saved["icebreakers"], list)
    assert len(saved["icebreakers"]) == 3


def test_api_enrich_endpoints_contract():
    # 1. Trigger enrichment on lead-2
    enrich_resp = client.post("/api/leads/lead-2/enrich")
    assert enrich_resp.status_code == 200
    data = enrich_resp.json()
    assert data["status"] == "success"
    assert "enrichment" in data
    assert data["enrichment"]["lead_id"] == "lead-2"

    # 2. Fetch enriched dossier
    get_resp = client.get("/api/leads/lead-2/enrichment")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["status"] == "success"
    assert get_data["enrichment"]["lead_id"] == "lead-2"
    assert len(get_data["enrichment"]["icebreakers"]) == 3

    # 3. 404 for invalid lead
    bad_resp = client.post("/api/leads/nonexistent-lead-999/enrich")
    assert bad_resp.status_code == 404
