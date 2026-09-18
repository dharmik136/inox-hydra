"""
Milestone 2 Automated Verification Test Suite: Days 05 to 08
============================================================
Validates:
1. Day 05: Mobile Fold Physics (140-char cutoff, air gap detection, 5 PRD hook archetypes).
2. Day 06: Asymmetric Intelligence Architecture (bundle export, <50KB bundle size, ETag caching, 304 Not Modified, air-gapped bundle import).
3. Day 07 & Day 08: Zero-Cost CDN & Zero-Egress Sovereign BYO-AI draft & post integrity in SQLite.
4. Zero Em-Dash Enforcement across all Milestone 2 components.
"""

import os
import sys
import json
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, seed_day05_draft, seed_day06_draft, seed_day07_draft, seed_day08_draft
from formatters import analyze_hook
from intelligence_sync import intelligence_sync_engine, FALLBACK_TEMPLATES

client = TestClient(app)


def test_day05_mobile_fold_physics_and_archetypes():
    """
    Day 05: Verify 140-character mobile feed cutoff physics,
    air gap detection, and 5 PRD hook archetype classifications.
    """
    # 1. Compliant mobile hook with air gap (< 140 chars across first 3 lines)
    good_hook_text = (
        "I spent $2,400 on creator SaaS before realizing this one uncomfortable truth:\n\n"
        "Here is what happened."
    )
    analysis = analyze_hook(good_hook_text)
    assert analysis["pre_fold_length"] <= 140
    assert analysis["has_air_gap"] is True
    assert analysis["is_pre_fold_safe"] is True
    assert analysis["archetype"] == "The Contrarian Confession"

    # 2. Architectural Breakdown Archetype
    arch_hook = (
        "90% of software engineers misunderstand local-first architectures. Here is how it actually works:\n\n"
        "Most teams default to cloud-first databases because they have never benchmarked local SQLite WAL mode."
    )
    analysis_arch = analyze_hook(arch_hook)
    assert analysis_arch["has_air_gap"] is True
    assert analysis_arch["archetype"] == "The Architectural Breakdown"

    # 3. Concrete Proof Archetype
    proof_hook = (
        "We analyzed 10,000 requests and benchmarked SQLite WAL vs Postgres on localhost:\n\n"
        "The latency numbers shocked our infrastructure lead."
    )
    analysis_proof = analyze_hook(proof_hook)
    assert analysis_proof["archetype"] == "The Concrete Proof"

    # 4. Step-by-Step Teardown Archetype
    teardown_hook = (
        "Step-by-step teardown of how to eliminate cloud egress costs completely:\n\n"
        "Step 1: Replace outbound REST polling with asymmetric GitHub CDN release bundles."
    )
    analysis_teardown = analyze_hook(teardown_hook)
    assert analysis_teardown["archetype"] == "The Step-by-Step Teardown"

    # 5. Direct Vulnerability Archetype
    vuln_hook = (
        "Our first ingestion worker crashed at 10,000 events. Here is what broke and how we fixed it:\n\n"
        "We forgot to configure write serialization on our SQLite transaction lock."
    )
    analysis_vuln = analyze_hook(vuln_hook)
    assert analysis_vuln["archetype"] == "The Direct Vulnerability"

    # 6. Hook that exceeds 140 characters before line break (mobile truncation violation)
    long_hook_text = (
        "This is an extraordinarily long opening sentence that exceeds one hundred and forty characters without any break, "
        "meaning it will be brutally truncated by LinkedIn mobile feed algorithm before the reader even understands the context or value proposition.\n\n"
        "Second line after the air gap."
    )
    analysis_long = analyze_hook(long_hook_text)
    assert analysis_long["pre_fold_length"] > 140
    assert analysis_long["is_pre_fold_safe"] is False


def test_day06_asymmetric_bundle_export_import_and_etags():
    """
    Day 06: Verify asymmetric intelligence bundle export (<50KB),
    ETag generation, HTTP 304 conditional request, and air-gapped bundle import.
    """
    # Ensure default templates are seeded
    intelligence_sync_engine.seed_offline_templates()

    # 1. Export bundle via API
    resp = client.get("/api/v1/intelligence/bundle/export")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    bundle = data["bundle"]
    assert bundle["format"] == "asymmetric_intelligence_bundle"
    assert "version" in bundle
    assert "templates" in bundle
    assert len(bundle["templates"]) >= len(FALLBACK_TEMPLATES)

    # Verify bundle payload size is strictly < 50KB
    bundle_bytes = json.dumps(bundle).encode("utf-8")
    assert len(bundle_bytes) < 50 * 1024, f"Bundle size {len(bundle_bytes)} bytes exceeds 50KB limit"

    # Verify ETag header is present in response
    etag = resp.headers.get("ETag") or data.get("etag")
    assert etag is not None and len(etag) > 0

    # 2. Test HTTP Conditional Request (If-None-Match -> 304 Not Modified)
    cond_resp = client.get(
        "/api/v1/intelligence/bundle/export",
        headers={"If-None-Match": etag}
    )
    assert cond_resp.status_code == 304
    assert cond_resp.text == ""

    # 3. Test Air-gapped Import endpoint
    test_bundle = {
        "version": "2026.09.2",
        "format": "asymmetric_intelligence_bundle",
        "generated_at": "2026-09-18T00:00:00Z",
        "templates": [
            {
                "archetype": "The Architectural Breakdown",
                "hook_text": "How we achieved sub-millisecond local ICP calculation with zero external APIs:",
                "velocity_score": 9.7,
                "engagement_multiplier": "3.5x",
                "pacing_style": "1-line hook + blank line + 3 bullet points",
                "example_post_id": "test-airgap-1"
            }
        ]
    }
    import_resp = client.post("/api/v1/intelligence/bundle/import", json={"bundle": test_bundle})
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["status"] == "success"
    assert import_data["imported_count"] == 1
    assert import_data["version"] == "2026.09.2"

    # Verify template was inserted into SQLite
    templates = intelligence_sync_engine.get_templates()
    assert any(t["example_post_id"] == "test-airgap-1" for t in templates)

    # Re-seed default offline templates to keep environment clean
    intelligence_sync_engine.seed_offline_templates()


def test_day07_day08_draft_and_post_integrity():
    """
    Day 07 & Day 08: Verify Launch Kit post drafts for Zero-Cost CDN
    and Zero-Egress BYO-AI are seeded with correct metadata and tags.
    """
    # Trigger seed functions
    seed_day05_draft()
    seed_day06_draft()
    id07 = seed_day07_draft()
    id08 = seed_day08_draft()

    assert id07 is not None
    assert id08 is not None

    conn = get_db()
    cursor = conn.cursor()

    # Verify Day 07 Draft
    cursor.execute("SELECT title, raw_content, tags, archetype FROM drafts WHERE id = ?", (id07,))
    row07 = cursor.fetchone()
    assert row07 is not None
    assert "Zero-Cost Cloud Distribution" in row07[0]
    assert "Fastly CDN" in row07[1]
    assert "304 Not Modified" in row07[1]
    tags07 = json.loads(row07[2])
    assert "#cloudEconomics" in tags07
    assert "#githubCDN" in tags07

    # Verify Day 08 Draft
    cursor.execute("SELECT title, raw_content, tags, archetype FROM drafts WHERE id = ?", (id08,))
    row08 = cursor.fetchone()
    assert row08 is not None
    assert "Zero Cloud Egress" in row08[0]
    assert "Bring-Your-Own-AI" in row08[0]
    assert "Sovereign Key Vaulting" in row08[1]
    tags08 = json.loads(row08[2])
    assert "#sovereignAI" in tags08
    assert any("byoai" in t.lower() for t in tags08)

    # Verify corresponding entries exist in posts table
    cursor.execute("SELECT id, content FROM posts WHERE id = ?", (f"post-day07-{id07}",))
    post07 = cursor.fetchone()
    assert post07 is not None

    cursor.execute("SELECT id, content FROM posts WHERE id = ?", (f"post-day08-{id08}",))
    post08 = cursor.fetchone()
    assert post08 is not None

    conn.close()


def test_milestone2_zero_em_dashes():
    """
    Verify strict zero em-dash compliance across all Milestone 2 backend and test files.
    """
    files_to_check = [
        "studio/backend/formatters.py",
        "studio/backend/intelligence_sync.py",
        "studio/backend/database.py",
        "studio/backend/app.py",
        "tests/test_milestone2_days05_08.py"
    ]
    # Literal em-dash character represented via unicode escape to prevent violation
    forbidden_char = "\u2014"

    for file_path in files_to_check:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            count = content.count(forbidden_char)
            assert count == 0, f"Violation: Found {count} em-dash characters in {file_path}"
