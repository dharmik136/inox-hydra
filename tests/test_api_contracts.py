"""
Inox Hydra: Comprehensive API Contract & End-to-End QA Test Suite
=================================================================
Automated test suite verifying all REST API endpoints, edge cases,
data contracts, algorithmic safety rules, and zero em-dash compliance.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import init_db, seed_initial_data

client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure clean database initialization before tests execute."""
    init_db()
    seed_initial_data()


# -------------------------------------------------------------
# 1. Analytics Endpoints Contract Tests
# -------------------------------------------------------------
def test_analytics_kpis_contract():
    for r in ["7d", "14d", "30d", "90d"]:
        response = client.get(f"/api/analytics/kpis?range={r}")
        assert response.status_code == 200
        data = response.json()
        assert data["range"] == r
        assert "impressions" in data
        assert "impressions_delta_pct" in data
        assert "total_followers" in data
        assert "profile_views" in data


def test_analytics_overview_contract():
    response = client.get("/api/analytics/overview?range=30d")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "series" in data
    assert len(data["series"]) >= 28


def test_analytics_demographics_contract():
    response = client.get("/api/analytics/demographics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "demographics" in data


def test_analytics_export_csv():
    response = client.get("/api/analytics/export")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "date" in response.text
    assert "impressions" in response.text
    assert "reactions" in response.text


# -------------------------------------------------------------
# 2. Post Studio Lifecycle & Validation Tests
# -------------------------------------------------------------
def test_post_lifecycle():
    # 1. Create a draft post
    payload = {
        "content": "Testing enterprise decoupling architecture for high-scale systems.",
        "media_urls": ["/assets/motadata_to_enterprise_4k_flawless.jpg"],
        "status": "draft",
        "tags": ["architecture", "systems"]
    }
    create_resp = client.post("/api/posts", json=payload)
    assert create_resp.status_code == 200
    post_data = create_resp.json()
    assert post_data["status"] == "success"
    post_id = post_data["id"]
    assert post_id is not None

    # 2. List posts and verify created post content
    get_resp = client.get("/api/posts")
    assert get_resp.status_code == 200
    posts = get_resp.json()["posts"]
    created_post = next((p for p in posts if p["id"] == post_id), None)
    assert created_post is not None
    assert created_post["content"] == payload["content"]

    # 3. Update post content
    updated_content = "Refined systems architecture post with verified zero downtime."
    update_resp = client.put(f"/api/posts/{post_id}", json={"content": updated_content})
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "success"

    # 4. Reschedule post
    future_time = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d 14:30:00")
    resched_resp = client.post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": future_time})
    assert resched_resp.status_code == 200
    assert resched_resp.json()["status"] == "success"

    # 5. Delete post
    del_resp = client.delete(f"/api/posts/{post_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "success"

    # 6. Verify post was removed
    get_after = client.get("/api/posts")
    assert not any(p["id"] == post_id for p in get_after.json()["posts"])


# -------------------------------------------------------------
# 3. Formatting, Unicode & Algorithmic Audit Tests
# -------------------------------------------------------------
def test_unicode_sans_bold_formatter():
    resp = client.post("/api/format/bold", json={"text": "Architecture Matters"})
    assert resp.status_code == 200
    bold_text = resp.json()["formatted"]
    assert "𝗔𝗿𝗰𝗵𝗶𝘁𝗲𝗰𝘁𝘂𝗿𝗲" in bold_text


def test_clean_text_scrubber():
    dirty_text = "Scaling enterprise systems \u2014 zero downtime – resilient architecture."
    resp = client.post("/api/format/clean", json={"text": dirty_text})
    assert resp.status_code == 200
    cleaned = resp.json()["cleaned"]
    assert "\u2014" not in cleaned
    assert "–" not in cleaned


def test_algorithmic_safety_audit_rules():
    # Outbound URL penalty test
    bad_post = "Check our tool at https://example.com #a #b #c #d #e #f #g comment 'yes' below"
    resp = client.post("/api/format/algorithm-audit", json={"text": bad_post})
    assert resp.status_code == 200
    audit = resp.json()
    assert audit["has_outbound_links"] is True
    assert audit["safety_score"] < 70
    assert audit["status_label"] in ["High Penalty Risk", "Moderate Risk"]


# -------------------------------------------------------------
# 4. Carousel 1080×1080 PDF Builder Tests
# -------------------------------------------------------------
def test_carousel_builder_contract():
    slides_payload = {
        "slides": [
            {"tag": "COVER", "title": "The Decoupled Enterprise", "body": "Why modern data pipelines avoid centralized schemas."},
            {"tag": "POINT 1", "title": "Immutable State", "body": "Treat every event as an append-only log record."},
            {"tag": "SUMMARY", "title": "Key Takeaway", "body": "Architecture empowers teams to operate autonomously."}
        ],
        "theme": "dark_slate",
        "author_name": "Dharmik Shingala",
        "author_title": "Content Strategist & Enterprise Systems Practitioner"
    }
    resp = client.post("/api/carousel/generate", json=slides_payload)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert len(resp.content) > 10000


# -------------------------------------------------------------
# 5. Inbound CRM Leads & DM Generation Tests
# -------------------------------------------------------------
def test_crm_leads_contract():
    leads_resp = client.get("/api/leads")
    assert leads_resp.status_code == 200
    leads = leads_resp.json()["leads"]
    assert len(leads) >= 4

    # Test DM generation for prospect across all 3 styles
    first_lead_id = leads[0]["id"]
    for style in ["value_add", "resource_share", "quick_chat"]:
        dm_resp = client.get(f"/api/leads/{first_lead_id}/dm-script?style={style}")
        assert dm_resp.status_code == 200
        dm_data = dm_resp.json()
        assert dm_data["status"] == "success"
        script = dm_data["dm_script"]
        assert "\u2014" not in script
        assert "--" not in script
        assert len(script) > 40


def test_crm_leads_csv_export():
    resp = client.get("/api/leads/export/csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "ID,Name,Headline,Company" in resp.text


# -------------------------------------------------------------
# 6. AI Command Engine Tests
# -------------------------------------------------------------
def test_ai_status_contract():
    resp = client.get("/api/ai/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider" in data
    assert "capabilities" in data


def test_ai_command_execution():
    resp = client.post("/api/ai/command", json={"command": "Write 10 hooks about enterprise event-driven architecture"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "output" in data
    assert "\u2014" not in data["output"]


# -------------------------------------------------------------
# 7. Documentation Suite API Tests
# -------------------------------------------------------------
def test_docs_modules_contract():
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] >= 7
    module_ids = [m["id"] for m in data["modules"]]
    assert "studio-editor" in module_ids
    assert "viral-swipe-file" in module_ids
    assert "analytics" in module_ids


def test_docs_individual_module_retrieval():
    resp = client.get("/api/docs/studio-editor")
    assert resp.status_code == 200
    data = resp.json()
    assert "Algorithmic Safety Audit" in data["content"]
    assert "Pre-Fold Hook" in data["content"]

    resp_agno = client.get("/api/docs/viral-swipe-file")
    assert resp_agno.status_code == 200
    assert "Agno" in resp_agno.json()["content"]

    # 404 test
    resp_invalid = client.get("/api/docs/non-existent-module")
    assert resp_invalid.status_code == 404
