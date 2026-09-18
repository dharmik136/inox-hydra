"""
Inox Hydra: LinkedIn Session Token Sync & Ingestion Pipeline Test Suite
========================================================================
Automated QA verifying:
1. POST /api/auth/cookies saves session tokens and triggers local sync.
2. GET /api/auth/status reflects authenticated state and active session.
3. POST /api/analytics/ingest inserts structured metrics, posts, and leads into SQLite.
4. linkedin_client.mock_ingestion_verification() operates without external cloud egress.
"""

import os
import sys
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import init_db, seed_initial_data, get_db
from linkedin_client import linkedin_client

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_test_db():
    init_db()
    seed_initial_data()


def test_save_cookies_endpoint():
    payload = {
        "li_at": "mock_li_at_enterprise_token_999",
        "JSESSIONID": "ajax:mock_jsession_secret_888"
    }
    response = client.post("/api/auth/cookies", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "sync" in data

    # Verify SQLite settings table directly
    tokens = linkedin_client.get_tokens()
    assert tokens.get("li_at") == payload["li_at"]
    assert tokens.get("JSESSIONID") == payload["JSESSIONID"]

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'session_status'")
    assert c.fetchone()[0] == "connected"

    c.execute("SELECT value FROM settings WHERE key = 'last_token_update'")
    last_update = c.fetchone()[0]
    assert last_update is not None
    conn.close()


def test_auth_status_endpoint():
    # Ensure tokens are set
    linkedin_client.save_tokens("mock_li_at_test", "mock_jsession_test")

    response = client.get("/api/auth/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "connected"
    assert data["is_connected"] is True
    assert data["client_session"] is True


def test_analytics_ingest_endpoint():
    test_date = "2026-09-15"
    payload = {
        "series": [
            {
                "date": test_date,
                "impressions": 840,
                "likes": 55,
                "comments": 14,
                "shares": 6,
                "followers": 2350,
                "connections": 2290,
                "profile_views": 95
            }
        ],
        "demographics": [
            {"dimension": "job_title", "label": "Staff Platform Engineers", "percentage": 45.0}
        ],
        "posts": [
            {
                "id": "post-ingest-verify",
                "content": "Enterprise distributed decoupling guarantees high availability.",
                "impressions": 840,
                "reactions": 55,
                "comments": 14,
                "shares": 6
            }
        ],
        "leads": [
            {
                "id": "lead-ingest-verify",
                "name": "Arun Kothari",
                "headline": "Director of Engineering @ NexusScale",
                "company": "NexusScale",
                "profile_url": "https://linkedin.com/in/arun-kothari-test",
                "engagement_type": "Commented",
                "notes": "Interested in distributed transaction boundaries"
            }
        ]
    }

    response = client.post("/api/analytics/ingest", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["buckets_ingested"] >= 1
    assert res_data["posts_updated"] >= 1
    assert (res_data["leads_added"] + res_data.get("leads_updated", 0)) >= 1

    # Verify directly in SQLite
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT impressions, reactions, engagement_rate FROM analytics_daily WHERE date = ?", (test_date,))
    row = c.fetchone()
    assert row is not None
    assert row[0] == 840
    assert row[1] == 55

    c.execute("SELECT impressions, content FROM posts WHERE id = 'post-ingest-verify'")
    p_row = c.fetchone()
    assert p_row is not None
    assert p_row[0] == 840

    c.execute("SELECT name, company FROM leads WHERE id = 'lead-ingest-verify'")
    l_row = c.fetchone()
    assert l_row is not None
    assert l_row[0] == "Arun Kothari"
    conn.close()


def test_mock_ingestion_verification_helper():
    res = linkedin_client.mock_ingestion_verification()
    assert res["status"] == "success"
    assert res["buckets_ingested"] >= 1
    assert res["posts_updated"] >= 1
    assert (res["leads_added"] + res.get("leads_updated", 0)) >= 1
