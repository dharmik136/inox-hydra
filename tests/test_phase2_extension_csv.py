import os
import sys
import io
import csv
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
from leads import export_leads_csv, list_leads

client = TestClient(app)


def test_phase2_leads_export_csv_endpoint():
    """Verify GET /api/v1/crm/leads/export-csv returns RFC-4180 CSV with enriched schema."""
    resp = client.get("/api/v1/crm/leads/export-csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    assert "linkedin_studio_crm_leads.csv" in resp.headers.get("content-disposition", "")

    content = resp.text
    reader = csv.reader(io.StringIO(content))
    headers = next(reader)

    expected_headers = [
        "ID", "Name", "Headline", "Company", "Seniority Level",
        "ICP Score", "Qualification Tier", "Status", "Profile URL",
        "Engagement Type", "Notes", "Created At"
    ]
    assert headers == expected_headers

    rows = list(reader)
    assert len(rows) >= 4, f"Expected >= 4 exported leads, got {len(rows)}"

    # Verify rows contain populated fields
    found_vip = False
    for row in rows:
        assert len(row) == len(expected_headers)
        # Check that ICP score is numeric
        icp_val = float(row[5])
        assert 0.0 <= icp_val <= 100.0
        # Check tier
        tier = row[6]
        assert tier in ["VIP", "TIER_1_VIP", "QUALIFIED", "NURTURE", "LOW_FIT", "DISQUALIFIED"]
        if tier in ["VIP", "TIER_1_VIP"]:
            found_vip = True

    assert found_vip, "Expected at least one VIP lead in test dataset"


def test_phase2_leads_export_csv_backward_compatible():
    """Verify GET /api/leads/export/csv backward compatibility."""
    resp = client.get("/api/leads/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    content = resp.text
    assert "ICP Score" in content
    assert "Qualification Tier" in content


def test_phase2_extension_ingest_contract():
    """Verify that extension content.js payload schema correctly maps into CRM ingest."""
    extension_payload = {
        "full_name": "Dr. Sarah Jenkins",
        "linkedin_urn": "urn:li:person:9911882233",
        "headline": "Chief AI Scientist & VP of Engineering at NeuralCore",
        "company": "NeuralCore",
        "interaction_type": "COMMENT",
        "comment_text": "Can you explain how the deterministic fold pacing compares against standard heuristics?",
        "post_topic": "sovereign creator architecture"
    }

    resp = client.post("/api/v1/crm/interactions/ingest", json=extension_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    interaction = data["interaction"]
    assert interaction["lead_name"] == "Dr. Sarah Jenkins"
    assert interaction["icp_score"] >= 65  # VP + Chief + Question should score highly qualified/VIP
    assert interaction["tier"] in ["VIP", "TIER_1_VIP", "QUALIFIED"]
    assert "suggested_dm" in interaction
    assert len(interaction["suggested_dm"]) > 30

    # Ensure no em-dash in suggested DM
    assert "\u2014" not in interaction["suggested_dm"]
    assert "--" not in interaction["suggested_dm"]

    # Verify lead is retrievable through list_leads with updated metrics
    leads = list_leads(search="Sarah Jenkins")
    assert len(leads) >= 1
    sarah = leads[0]
    assert sarah["name"] == "Dr. Sarah Jenkins"
    assert sarah["icp_score"] >= 65


def test_phase2_zero_em_dashes_in_source():
    """Strict verification: Zero literal em-dashes in modified Phase 2 files."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    phase2_files = [
        os.path.join(base_dir, "studio", "backend", "leads.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "studio", "extension", "content.js"),
        os.path.join(base_dir, "tests", "test_phase2_extension_csv.py"),
    ]

    for fpath in phase2_files:
        assert os.path.exists(fpath), f"File {fpath} does not exist"
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            assert "\u2014" not in content, f"Forbidden em-dash found in {fpath}"
