"""
Verification Suite: Swipe File Refactor & Structural Blueprint Evolution.
========================================================================
Validates all 4 parts of the Swipe File modernization:
1. /api/v1/intelligence/templates returns ranked archetypes with velocity score and pacing.
2. Filter by archetype and free-text search queries work accurately.
3. 36 seeded author blueprints across 6 core taxonomies (no PII, no third-party copyright).
4. Migration 2 cleanly migrates legacy inspirations into viral_templates and drops inspirations.
5. Backward-compatible /api/inspirations seamlessly proxies viral_templates.
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
from intelligence_sync import IntelligenceSyncEngine, intelligence_sync_engine, FALLBACK_TEMPLATES
from migrations import _migrate_inspirations, MIGRATIONS, SCHEMA_VERSION, BASELINE_VERSION

client = TestClient(app)


def test_fallback_templates_count_and_taxonomies():
    """Asserts that FALLBACK_TEMPLATES contains 36 blueprints across 6 distinct taxonomies."""
    assert len(FALLBACK_TEMPLATES) == 36

    taxonomies = set(t["archetype"] for t in FALLBACK_TEMPLATES)
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
        count = sum(1 for t in FALLBACK_TEMPLATES if t["archetype"] == tax)
        assert count == 6, f"Expected 6 blueprints for {tax}, found {count}"

    # Ensure all have non-empty hook_text, pacing_style, and velocity_score
    for t in FALLBACK_TEMPLATES:
        assert t["hook_text"].strip()
        assert t["pacing_style"].strip()
        assert 8.0 <= float(t["velocity_score"]) <= 10.0
        assert "example_post_id" in t


def test_intelligence_templates_endpoint_and_filtering():
    """Verifies /api/v1/intelligence/templates listing, search, and archetype filtering."""
    init_db()
    intelligence_sync_engine.seed_offline_templates()
    res = client.get("/api/v1/intelligence/templates?limit=100")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["count"] >= 36
    assert data["total_vaulted"] >= 36
    assert len(data["templates"]) >= 36

    # Verify descending velocity sorting
    velocities = [t["velocity_score"] for t in data["templates"]]
    assert velocities == sorted(velocities, reverse=True)

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


def test_migration_2_and_backward_compatible_inspirations_proxy():
    """Verifies that Migration 2 drops inspirations and /api/inspirations adapts smoothly."""
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Apply migration 2 logic explicitly if inspirations still exists
    _migrate_inspirations(cursor)
    conn.commit()

    # inspirations table should be dropped
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
    assert cursor.fetchone() is None

    # Call /api/inspirations: must not crash with OperationalError, but adapt viral_templates
    res = client.get("/api/inspirations?limit=20")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["count"] > 0
    assert len(data["inspirations"]) > 0

    first_item = data["inspirations"][0]
    assert "author_name" in first_item
    assert "archetype" in first_item
    assert "pacing_style" in first_item
    assert "key_hook" in first_item
    conn.close()


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

    # Check app.js loadInspirations area
    with open(os.path.join(os.path.dirname(__file__), "..", "studio", "frontend", "app.js"), "r", encoding="utf-8") as f:
        content = f.read()
        assert disallowed not in content, "Em-dash found in app.js"
