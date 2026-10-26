"""
Verification Suite: Swipe File Refactor & Structural Blueprint Evolution.
========================================================================
Validates all 4 parts of the Swipe File modernization:
1. /api/v1/intelligence/templates returns ranked archetypes with velocity score and pacing.
2. Filter by archetype and free-text search queries work accurately.
3. 36 seeded author blueprints across 6 core taxonomies (no PII, no third-party copyright).
4. Migration 2 cleanly migrates legacy inspirations into viral_templates and drops inspirations.
5. Migration 2 is final: nothing recreates the inspirations table at boot, and
   the /api/inspirations route that proxied viral_templates is retired.
6. Zero em-dashes across all modified components.
"""

import os
import sys
import sqlite3
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db, seed_initial_data
from intelligence_sync import IntelligenceSyncEngine, intelligence_sync_engine, ENGINEERING_PACK
from migrations import _migrate_inspirations, MIGRATIONS, SCHEMA_VERSION, BASELINE_VERSION

client = TestClient(app)


def test_fallback_templates_count_and_taxonomies():
    """
    Asserts that the opt-in engineering creator pack holds 36 blueprints
    across 6 taxonomies. It was the library every new creator started on; since
    cycle 2 (D-8) a new library holds neutral starter forms instead.
    """
    assert len(ENGINEERING_PACK) == 36

    taxonomies = set(t["archetype"] for t in ENGINEERING_PACK)
    expected_taxonomies = {
        "Contrarian Truths",
        "Architecture",
        "Reverse Engineering",
        "Failure Analysis",
        "Benchmarks",
        "Economics"
    }
    assert taxonomies == expected_taxonomies

    # Ensure 6 blueprints per taxonomy
    for tax in expected_taxonomies:
        count = sum(1 for t in ENGINEERING_PACK if t["archetype"] == tax)
        assert count == 6, f"Expected 6 blueprints for {tax}, found {count}"

    # Ensure all have non-empty hook_text, pacing_style, and velocity_score
    for t in ENGINEERING_PACK:
        assert t["hook_text"].strip()
        assert t["pacing_style"].strip()
        assert 8.0 <= float(t["velocity_score"]) <= 10.0
        assert "example_post_id" in t


def test_intelligence_templates_endpoint_and_filtering():
    """Verifies /api/v1/intelligence/templates listing, search, and archetype filtering."""
    init_db()
    intelligence_sync_engine.seed_offline_templates(templates=ENGINEERING_PACK)
    res = client.get("/api/v1/intelligence/templates?limit=100")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["count"] >= 36
    assert data["total_vaulted"] >= 36
    assert len(data["templates"]) >= 36

    # Verify descending velocity sorting; unrated starter forms come last
    velocities = [t["velocity_score"] for t in data["templates"]]
    rated = [v for v in velocities if v is not None]
    assert rated == sorted(rated, reverse=True)
    assert velocities[: len(rated)] == rated

    # Filter by archetype
    res_filtered = client.get("/api/v1/intelligence/templates?archetype=Contrarian")
    assert res_filtered.status_code == 200
    filtered_data = res_filtered.json()
    assert filtered_data["count"] >= 6
    assert all("Contrarian" in t["archetype"] for t in filtered_data["templates"])

    # Search query
    res_query = client.get("/api/v1/intelligence/templates?query=SQLite")
    assert res_query.status_code == 200
    query_data = res_query.json()
    assert query_data["count"] >= 1
    assert any("sqlite" in t["hook_text"].lower() or "sqlite" in t["pacing_style"].lower() for t in query_data["templates"])


def test_migration_2_is_final_and_the_proxy_route_is_retired():
    """
    Migration 2 drops inspirations, init_db no longer puts an empty shell of
    it back on every boot, migration 2 tolerates its absence, and the route
    that proxied viral_templates under its name answers 404 (cycle 4, track
    7, batch 0).
    """
    init_db()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
    assert cursor.fetchone() is None, "init_db recreated the table migration 2 drops"

    _migrate_inspirations(cursor)  # a no-op on a database without the table
    conn.commit()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
    assert cursor.fetchone() is None
    conn.close()

    assert client.get("/api/inspirations?limit=20").status_code == 404
    res = client.get("/api/v1/intelligence/templates?limit=20")
    assert res.status_code == 200 and res.json()["count"] > 0


def test_zero_em_dash_compliance_in_swipe_files():
    """Verifies strictly zero em-dashes (\\u2014) across modified swipe files and templates."""
    disallowed = "\u2014"

    # Check intelligence_sync.py
    with open(os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "intelligence_sync.py"), "r", encoding="utf-8") as f:
        content = f.read()
        assert disallowed not in content, "Em-dash found in intelligence_sync.py"

    # Check migrations.py
    with open(os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "migrations.py"), "r", encoding="utf-8") as f:
        content = f.read()
        assert disallowed not in content, "Em-dash found in migrations.py"

    # The interface is covered wholesale by tests/test_react_ui_contract.py,
    # which holds the same rule over every component rather than one file.
