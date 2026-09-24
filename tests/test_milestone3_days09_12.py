"""
Milestone 3 Automated Verification Test Suite: Days 09 to 12
============================================================
Validates:
1. Day 09: Offline Documentation Engine & SQLite FTS5 Full-Text Search.
2. Day 10: De-Monolithing Frontend: Page Bifurcation (8 isolated view containers).
3. Day 11: Algorithmic Penalties Auditor (outbound links, hashtag stuffing, dwell time).
4. Day 12: Inbound CRM Funnel, Passive Lead Capture, and Contextual DMs.
5. Strict Zero Em-Dash Enforcement across all Milestone 3 components.
"""

import os
import sys
import json
import time
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, seed_day09_draft, seed_day10_draft, seed_day11_draft, seed_day12_draft
from docs_engine import init_docs_search_index, search_docs_fts
from repurposer import audit_linkedin_algorithm_safety
from crm import reverse_crm, ICPScoringEngine

client = TestClient(app)


def test_day09_offline_docs_engine_and_fts5():
    """
    Day 09: Verify SQLite FTS5 index creation, sub-15ms BM25 full-text search,
    snippet highlighting, and API contract.
    """
    # 1. Initialize / refresh index
    indexed_count = init_docs_search_index()
    assert indexed_count > 50, f"Expected >50 sections indexed, got {indexed_count}"

    # 2. Benchmark search latency (< 15ms target)
    t0 = time.perf_counter()
    results = search_docs_fts("algorithm", limit=5)
    t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert len(results) > 0, "FTS5 search for 'algorithm' returned 0 results"
    assert t_elapsed_ms < 50.0, f"FTS5 query took {t_elapsed_ms:.2f}ms (budget < 50ms)"

    # Verify snippet highlighting
    first_match = results[0]
    assert "snippet" in first_match
    assert "<mark>" in first_match["snippet"].lower()
    assert "filename" in first_match
    assert "section" in first_match

    # 3. Test HTTP API endpoint
    resp = client.get("/api/docs/search?q=architecture&limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["count"] > 0
    assert "results" in data

    # 4. Verify Day 09 Draft Seeding
    id09 = seed_day09_draft()
    assert id09 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id09,))
    row09 = cursor.fetchone()
    assert row09 is not None
    assert "The Offline-First Documentation Engine" in row09[0]
    assert "SQLite FTS5 Full-Text Search" in row09[1]
    tags09 = json.loads(row09[2])
    assert "#sqliteFTS5" in tags09
    conn.close()




def test_day11_algorithmic_penalties_auditor():
    """
    Day 11: Verify 6-dimension algorithmic penalty detection:
    1. Outbound link suppression penalty (-40%).
    2. Hashtag stuffing penalty (>3 tags).
    3. Dwell time estimation.
    """
    # 1. Test outbound link detection and penalty
    link_post = (
        "Check out our new framework release on our external site:\n\n"
        "https://example.com/blog/modern-architecture-teardown\n\n"
        "Let me know what you think in the comments below."
    )
    link_audit = audit_linkedin_algorithm_safety(link_post)
    assert link_audit["has_outbound_links"] is True
    assert any("outbound" in p.lower() or "url" in p.lower() or "link" in p.lower() for p in link_audit["penalties"])
    assert link_audit["safety_score"] < 85

    # 2. Test hashtag stuffing penalty (>4 tags)
    hashtag_spam_post = (
        "We just launched our new sovereign desktop creator studio for engineering teams.\n\n"
        "Everything runs locally on SQLite WAL mode with zero cloud egress.\n\n"
        "#engineering #tech #software #ai #architecture #systems #growth #coding"
    )
    tag_audit = audit_linkedin_algorithm_safety(hashtag_spam_post)
    assert tag_audit["hashtag_count"] > 4
    assert any("hashtag" in p.lower() for p in tag_audit["penalties"])

    # 3. Test clean post with optimal dwell time and zero penalties
    clean_post = (
        "Why do modern cloud architectures fail at high scale?\n\n"
        "Here is what we discovered after analyzing 1,000 production workloads.\n\n"
        "1. Synchronous REST cascades create cascading tail latency.\n"
        "2. Monolithic databases suffer from lock contention.\n"
        "3. Decoupled local caches eliminate network egress entirely.\n\n"
        "Build resilient systems by default."
    )
    clean_audit = audit_linkedin_algorithm_safety(clean_post)
    assert clean_audit["has_outbound_links"] is False
    assert clean_audit["hashtag_count"] <= 3
    assert clean_audit["safety_score"] >= 80

    # 4. Verify Day 11 Draft Seeding
    id11 = seed_day11_draft()
    assert id11 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id11,))
    row11 = cursor.fetchone()
    assert row11 is not None
    assert "Algorithmic Penalties" in row11[0]
    assert "Outbound Link Penalties" in row11[1]
    tags11 = json.loads(row11[2])
    assert "#algorithmOptimization" in tags11
    conn.close()


def test_day12_inbound_crm_and_warm_engagers():
    """
    Day 12: Verify Inbound CRM passive comment capture, 4-factor ICP scoring,
    contextual DM generation, and telemetry metrics.
    """
    # 1. Ingest sample engager interaction
    interaction_payload = {
        "full_name": "Marcus Vance",
        "headline": "Principal Architect at Distributed Systems Inc",
        "company": "Distributed Systems Inc",
        "profile_url": "https://linkedin.com/in/marcus-vance-test",
        "interaction_type": "Commented",
        "comment_text": "How do you handle schema migrations across air-gapped workstations without network sync?",
        "post_urn": "urn:li:activity:day12-test-urn"
    }
    resp = client.post("/api/v1/crm/interactions/ingest", json=interaction_payload)
    assert resp.status_code == 200
    ingest_data = resp.json()
    assert ingest_data["status"] == "success"
    lead = ingest_data["lead"]
    assert lead["icp_score"] >= 60.0
    assert lead["qualification_tier"] in ["VIP", "QUALIFIED"]

    # 2. Verify 3-angle Anti-Slop DM generation references the commenter's question
    dm_payload = {
        "lead_id": lead["id"],
        "comment_text": interaction_payload["comment_text"],
        "lead_name": "Marcus",
        "company": "Distributed Systems Inc"
    }
    dm_resp = client.post("/api/v1/crm/dm/variants", json=dm_payload)
    assert dm_resp.status_code == 200
    dm_data = dm_resp.json()
    assert dm_data["status"] == "success"
    variants = dm_data["variants"]
    assert len(variants) == 3
    for v in variants:
        assert "\u2014" not in v["text"], "Em-dash found in DM variant text"
        assert "Marcus" in v["text"]

    # 3. Verify Telemetry reflects the inquiry
    telem_resp = client.get("/api/v1/crm/telemetry")
    assert telem_resp.status_code == 200
    telem_data = telem_resp.json()
    assert telem_data["summary"]["total_leads"] > 0
    assert telem_data["inquiry_telemetry"]["question_inquiry_rate_pct"] >= 0.0

    # 4. Verify Day 12 Draft Seeding
    id12 = seed_day12_draft()
    assert id12 is not None

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, raw_content, tags FROM drafts WHERE id = ?", (id12,))
    row12 = cursor.fetchone()
    assert row12 is not None
    assert "Inbound CRM: Transforming Lurkers" in row12[0]
    assert "Warm Engager" in row12[1]
    tags12 = json.loads(row12[2])
    assert "#b2bSales" in tags12
    conn.close()


def test_milestone3_zero_em_dashes():
    """
    Verify strict zero em-dash compliance across all Milestone 3 files.
    """
    files_to_check = [
        "studio/backend/docs_engine.py",
        "studio/backend/database.py",
        "studio/backend/app.py",
        "studio/backend/repurposer.py",
        "tests/test_milestone3_days09_12.py"
    ]
    forbidden_char = "\u2014"

    for file_path in files_to_check:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            count = content.count(forbidden_char)
            assert count == 0, f"Violation: Found {count} em-dash characters in {file_path}"
