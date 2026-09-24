"""
CRM & Leads Module Production Hardening Test Suite.
====================================================
Validates:
1. Field length limits on add_lead() (name, headline, company, notes).
2. update_lead_status() not-found detection and status validation.
3. delete_lead() not-found detection via API 404.
4. batch_add_leads() cap at 500 leads per request.
5. ingest_interaction() field length sanitization.
6. archive_inactive_leads() minimum 7-day safety bound.
7. list_high_value_leads() query limit cap at 500.
8. Full lead lifecycle: create, update status, generate DM, delete.
9. Purge non-existent lead returns 404 (regression guard).
10. Strict zero em-dash compliance across all modified files.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from leads import (
    add_lead, batch_add_leads, update_lead_status, delete_lead,
    MAX_NAME_LENGTH, MAX_BATCH_SIZE, VALID_LEAD_STATUSES,
)
from crm import (
    reverse_crm, ICPScoringEngine,
    MAX_CRM_NAME_LENGTH, MAX_CRM_COMMENT_LENGTH,
    MIN_ARCHIVE_INACTIVE_DAYS, MAX_HIGH_VALUE_QUERY_LIMIT,
)
from database import get_db, init_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def ensure_db_initialized():
    """Ensure database tables and schema migrations are initialized."""
    init_db()


# ---------------------------------------------------------------
# 1. Field length limits on add_lead()
# ---------------------------------------------------------------
def test_add_lead_field_length_limits():
    """Validates that add_lead() silently truncates oversized fields."""
    import uuid
    unique_url = f"https://linkedin.com/in/field-length-{uuid.uuid4().hex[:8]}"
    oversized_name = "A" * 500
    oversized_headline = "B" * 1000
    oversized_company = "C" * 800
    oversized_notes = "D" * 5000

    result = add_lead({
        "name": oversized_name,
        "headline": oversized_headline,
        "company": oversized_company,
        "notes": oversized_notes,
        "profile_url": unique_url,
    })
    assert result["status"] == "success"
    assert result["action"] == "created"

    # Verify truncation via DB read
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, headline, company, notes FROM leads WHERE id = ?", (result["id"],))
    row = c.fetchone()
    conn.close()

    assert row is not None
    assert len(row["name"]) <= MAX_NAME_LENGTH
    assert len(row["headline"]) <= 500
    assert len(row["company"]) <= 300
    assert len(row["notes"]) <= 2000


# ---------------------------------------------------------------
# 2. update_lead_status() not-found and status validation
# ---------------------------------------------------------------
def test_update_lead_status_nonexistent_id_returns_not_found():
    """Validates that updating a non-existent lead returns not_found."""
    result = update_lead_status("lead_nonexistent_xyz_999", "Connected")
    assert result["status"] == "not_found"
    assert result["id"] == "lead_nonexistent_xyz_999"


def test_update_lead_status_invalid_status_rejected():
    """Validates that invalid status strings are rejected."""
    # First create a real lead
    lead = add_lead({"name": "Status Validation Test"})
    assert lead["status"] == "success"

    # Try invalid status
    result = update_lead_status(lead["id"], "HACKED_STATUS")
    assert result["status"] == "error"
    assert "Invalid status" in result["message"]

    # Valid status should work
    result2 = update_lead_status(lead["id"], "Connected")
    assert result2["status"] == "success"
    assert result2["new_status"] == "Connected"


def test_update_lead_status_api_returns_404():
    """Validates that PUT /api/leads/{id}/status returns 404 for non-existent leads."""
    res = client.put("/api/leads/lead_ghost_abc/status", json={"status": "Connected"})
    assert res.status_code == 404


def test_update_lead_status_api_returns_400_invalid_status():
    """Validates that PUT /api/leads/{id}/status returns 400 for invalid status."""
    lead = add_lead({"name": "API Status Validation"})
    res = client.put(f"/api/leads/{lead['id']}/status", json={"status": "INVALID_VALUE"})
    assert res.status_code == 400


# ---------------------------------------------------------------
# 3. delete_lead() not-found detection
# ---------------------------------------------------------------
def test_delete_lead_nonexistent_id_returns_not_found():
    """Validates that deleting a non-existent lead returns not_found."""
    result = delete_lead("lead_does_not_exist_xyz")
    assert result["status"] == "not_found"


def test_delete_lead_api_returns_404():
    """Validates that DELETE /api/leads/{id} returns 404 for non-existent leads."""
    res = client.delete("/api/leads/lead_phantom_999")
    assert res.status_code == 404


# ---------------------------------------------------------------
# 4. batch_add_leads() cap at 500
# ---------------------------------------------------------------
def test_batch_add_leads_cap_500():
    """Validates that batch_add_leads rejects batches exceeding MAX_BATCH_SIZE."""
    oversized_batch = [{"name": f"Lead {i}"} for i in range(MAX_BATCH_SIZE + 1)]
    result = batch_add_leads(oversized_batch)
    assert result["status"] == "error"
    assert "exceeds maximum" in result["message"]

    # Just under the limit should work
    ok_batch = [{"name": f"Batch OK {i}", "headline": "Engineer"} for i in range(3)]
    result2 = batch_add_leads(ok_batch)
    assert result2["status"] == "success"
    assert result2["added"] >= 0


def test_batch_add_leads_api_returns_400():
    """Validates that POST /api/leads/batch returns 400 for oversized batches."""
    oversized = [{"name": f"API Batch {i}"} for i in range(MAX_BATCH_SIZE + 1)]
    res = client.post("/api/leads/batch", json={"leads": oversized})
    assert res.status_code == 400


# ---------------------------------------------------------------
# 5. ingest_interaction() field length sanitization
# ---------------------------------------------------------------
def test_ingest_interaction_field_length_validation():
    """Validates that ingest_interaction truncates oversized fields."""
    result = reverse_crm.ingest_interaction(
        full_name="X" * 500,
        linkedin_urn="urn:li:person:field_length_crm_test",
        headline="Y" * 1000,
        company="Z" * 800,
        interaction_type="COMMENT",
        comment_text="W" * 10000,
        post_topic="field length test"
    )
    assert result["lead_id"] is not None

    # Verify truncation via DB read
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, headline, company FROM leads WHERE id = ?", (result["lead_id"],))
    row = c.fetchone()
    conn.close()

    assert row is not None
    assert len(row["name"]) <= MAX_CRM_NAME_LENGTH
    assert len(row["headline"]) <= 500
    assert len(row["company"]) <= 300


# ---------------------------------------------------------------
# 6. archive_inactive_leads() minimum 7-day safety bound
# ---------------------------------------------------------------
def test_archive_inactive_minimum_7_days():
    """Validates that archive rejects inactive_days < MIN_ARCHIVE_INACTIVE_DAYS."""
    result = reverse_crm.archive_inactive_leads(inactive_days=0)
    assert result["status"] == "error"
    assert "must be >=" in result["message"]

    result2 = reverse_crm.archive_inactive_leads(inactive_days=3)
    assert result2["status"] == "error"

    result3 = reverse_crm.archive_inactive_leads(inactive_days=6)
    assert result3["status"] == "error"

    # At minimum threshold should work
    result4 = reverse_crm.archive_inactive_leads(inactive_days=MIN_ARCHIVE_INACTIVE_DAYS)
    assert result4["status"] == "success"


def test_archive_inactive_api_returns_400():
    """Validates that POST /api/v1/crm/leads/archive-inactive returns 400 for < 7 days."""
    res = client.post("/api/v1/crm/leads/archive-inactive", json={"inactive_days": 2})
    assert res.status_code == 400


# ---------------------------------------------------------------
# 7. list_high_value_leads() query limit cap
# ---------------------------------------------------------------
def test_high_value_leads_limit_capped_at_500():
    """Validates that list_high_value_leads caps limit at MAX_HIGH_VALUE_QUERY_LIMIT."""
    # This should not crash or return millions of rows
    leads = reverse_crm.list_high_value_leads(min_icp_score=0.0, limit=99999)
    # The function should have capped internally, so result count <= 500
    assert isinstance(leads, list)
    assert len(leads) <= MAX_HIGH_VALUE_QUERY_LIMIT


# ---------------------------------------------------------------
# 8. Full lead lifecycle: create -> update -> DM -> delete
# ---------------------------------------------------------------
def test_lead_lifecycle_full_pipeline():
    """End-to-end lifecycle: create, update status, generate DM, delete."""
    # Create
    res = client.post("/api/leads", json={
        "name": "Lifecycle Test Lead",
        "headline": "VP of Engineering at Scale Corp",
        "company": "Scale Corp",
        "profile_url": "https://linkedin.com/in/lifecycle-test",
        "engagement_type": "Commented",
        "notes": "Engaged on architecture post"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    lead_id = data["id"]

    # Update status
    res2 = client.put(f"/api/leads/{lead_id}/status", json={"status": "Outreach Sent"})
    assert res2.status_code == 200
    assert res2.json()["new_status"] == "Outreach Sent"

    # Generate DM script
    res3 = client.get(f"/api/leads/{lead_id}/dm-script?style=value_add")
    assert res3.status_code == 200
    dm_data = res3.json()
    assert dm_data["status"] == "success"
    assert "Lifecycle" in dm_data["dm_script"]
    assert "\u2014" not in dm_data["dm_script"]

    # Delete
    res4 = client.delete(f"/api/leads/{lead_id}")
    assert res4.status_code == 200
    assert res4.json()["status"] == "success"

    # Verify deleted (should 404 now)
    res5 = client.delete(f"/api/leads/{lead_id}")
    assert res5.status_code == 404


# ---------------------------------------------------------------
# 9. Purge non-existent lead returns 404 (regression guard)
# ---------------------------------------------------------------
def test_purge_nonexistent_lead_returns_404():
    """Validates that DELETE /api/v1/crm/leads/{id}/purge returns 404 for missing leads."""
    res = client.delete("/api/v1/crm/leads/lead_nonexistent_purge_test/purge")
    assert res.status_code == 404


# ---------------------------------------------------------------
# 10. Strict zero em-dash compliance
# ---------------------------------------------------------------
def test_zero_em_dash_compliance():
    """Audits all modified files for zero occurrences of the em-dash character."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    targets = [
        os.path.join(base_dir, "studio", "backend", "leads.py"),
        os.path.join(base_dir, "studio", "backend", "crm.py"),
        os.path.join(base_dir, "studio", "backend", "app.py"),
        os.path.join(base_dir, "tests", "test_crm_leads_hardening.py"),
    ]

    for path in targets:
        assert os.path.exists(path), f"Target file does not exist: {path}"
        text = open(path, "r", encoding="utf-8").read()
        assert "\u2014" not in text, f"Illegal em-dash (\\u2014) found in: {path}"
