"""
Day 03 Implementation Verification Suite: Passive Telemetry & Asymmetric Sync.
================================================================================
Validates all mandates from Day 03 specification:
1. SQLite viral_templates relational schema, velocity indexes, and DDL.
2. Day 03 Post Kit seeding ("Passive Telemetry & Internal Voyager APIs") with 2-tier fold safety.
3. Strict Zero Em-Dash compliance (\\u2014 is strictly illegal across all code, drafts, and tests).
4. IntelligenceSyncEngine asymmetric sync, HTTP 304 ETag caching, 0-byte verification, and offline fallback.
5. FastAPI endpoints: POST /api/v1/intelligence/sync, GET /api/v1/intelligence/templates, GET /api/v1/intelligence/status.
6. Extension Manifest V3 background listener for voyager telemetry and INGEST_ANALYTICS action.
"""

import os
import sys
import json
import sqlite3
from unittest.mock import patch, MagicMock
import pytest
import requests
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db, seed_day03_draft
import hook_forms
from hook_forms import FALLBACK_TEMPLATES

client = TestClient(app)


# -------------------------------------------------------------
# TASK 1: SQLite Schema & viral_templates Table DDL
# -------------------------------------------------------------
def test_viral_templates_table_schema_and_indexes():
    """Validates that viral_templates table and velocity indexes exist with correct schemas."""
    init_db()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in c.fetchall()}
    assert "viral_templates" in tables, "Missing viral_templates table in SQLite"

    c.execute("PRAGMA table_info(viral_templates)")
    cols = {r["name"]: r["type"] for r in c.fetchall()}
    required_cols = [
        "id", "archetype", "hook_text", "velocity_score",
        "engagement_multiplier", "pacing_style", "example_post_id", "updated_at"
    ]
    for col in required_cols:
        assert col in cols, f"Missing required column in viral_templates: {col}"

    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {r[0] for r in c.fetchall()}
    assert "idx_viral_templates_velocity" in indexes, "Missing idx_viral_templates_velocity index"
    assert "idx_viral_templates_archetype" in indexes, "Missing idx_viral_templates_archetype index"

    conn.close()


# -------------------------------------------------------------
# TASK 2: Day 03 Post Kit Seeding & Mobile Fold Safety
# -------------------------------------------------------------
def test_day03_draft_seeding_and_mobile_fold_safety():
    """Validates that Day 03 Post is properly seeded with correct fold metrics and status."""
    init_db()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, title, raw_content, lines_above_fold, pre_fold_chars, is_pre_fold_safe, status, tags FROM drafts WHERE title LIKE '%Passive Telemetry%'")
    draft = c.fetchone()
    assert draft is not None, "Day 03 draft was not seeded in drafts table"

    assert draft["title"] == "Passive Telemetry & Internal Voyager APIs"
    assert draft["status"] == "DRAFT"
    assert draft["lines_above_fold"] == 3
    assert draft["pre_fold_chars"] == 121
    assert draft["is_pre_fold_safe"] == 1
    assert len(draft["raw_content"]) > 500

    tags = json.loads(draft["tags"])
    assert "#passiveTelemetry" in tags
    assert "#voyagerAPI" in tags
    assert "#engineering" in tags

    # Verify post entry
    c.execute("SELECT id, status, tags FROM posts WHERE id LIKE 'post-day03-%'")
    post = c.fetchone()
    assert post is not None, "Day 03 post was not seeded in posts table"
    assert post["status"] == "scheduled"

    conn.close()


# -------------------------------------------------------------
# TASK 3: Strict Zero Em-Dashes Compliance
# -------------------------------------------------------------
def test_day03_strict_zero_em_dashes():
    """Validates that the character \\u2014 is 100% absent across Day 03 codebase, drafts, and templates."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, raw_content FROM drafts WHERE title LIKE '%Passive Telemetry%'")
    draft = c.fetchone()
    assert draft is not None
    assert "\u2014" not in draft["title"], "Em-dash detected in Day 03 draft title"
    assert "\u2014" not in draft["raw_content"], "Em-dash detected in Day 03 draft content"

    c.execute("SELECT hook_text, archetype, pacing_style FROM viral_templates")
    for row in c.fetchall():
        assert "\u2014" not in row["hook_text"], f"Em-dash detected in hook: {row['hook_text']}"
        assert "\u2014" not in row["archetype"], f"Em-dash detected in archetype: {row['archetype']}"
        assert "\u2014" not in row["pacing_style"], f"Em-dash detected in pacing: {row['pacing_style']}"
    conn.close()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
    files_to_check = [
        os.path.join(backend_dir, "hook_forms.py"),
        os.path.join(backend_dir, "database.py"),
        os.path.join(backend_dir, "app.py"),
        os.path.abspath(os.path.join(backend_dir, "..", "extension", "background.js")),
        os.path.abspath(os.path.join(backend_dir, "..", "extension", "sidepanel.js")),
    ]
    for path in files_to_check:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "\u2014" not in content, f"Em-dash character \\u2014 found in {path}"


# -------------------------------------------------------------
# TASK 4: The hook forms seed themselves on an empty library
# -------------------------------------------------------------
# The network sync these tested (304, 200 with an ETag file, a failed fetch
# falling back) was intelligence_sync.py's, deleted in cycle 4, track 7
# (ideas report decision 10): nothing called it, the bundle was unsigned, and
# its answer replaced the creator's whole hook library. The signed library
# channel that replaces it is tested in tests/test_qc4_t7_library_bundle.py.
def test_the_hook_forms_seed_an_empty_library():
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM viral_templates")
    conn.commit()
    conn.close()

    templates = hook_forms.get_templates()
    assert len(templates) >= len(FALLBACK_TEMPLATES)
    velocities = [t["velocity_score"] for t in templates]
    rated = [v for v in velocities if v is not None]
    assert rated == sorted(rated, reverse=True)
    assert velocities[: len(rated)] == rated
    assert hook_forms.get_total_count() >= len(FALLBACK_TEMPLATES)


# -------------------------------------------------------------
# TASK 5: Day 03 API Endpoints
# -------------------------------------------------------------
def test_intelligence_api_endpoints():
    """Validates the hook forms route; the sync status route went with the sync (cycle 4, track 7)."""
    assert client.get("/api/v1/intelligence/status").status_code == 404

    # GET /api/v1/intelligence/templates
    res_templates = client.get("/api/v1/intelligence/templates?limit=10")
    assert res_templates.status_code == 200
    data_templates = res_templates.json()
    assert data_templates["status"] == "success"
    assert "templates" in data_templates
    assert data_templates["count"] > 0
    first_item = data_templates["templates"][0]
    assert "velocity_score" in first_item
    assert "archetype" in first_item

    # POST /api/v1/intelligence/sync was removed in cycle 2 (D1): nothing called it.


# -------------------------------------------------------------
# TASK 6: Extension Bridge Configuration
# -------------------------------------------------------------
def test_extension_manifest_and_passive_background():
    """Validates Chrome Extension MV3 manifest and background passive observation listener."""
    extension_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "extension"))
    manifest_path = os.path.join(extension_dir, "manifest.json")
    bg_path = os.path.join(extension_dir, "background.js")

    assert os.path.exists(manifest_path)
    assert os.path.exists(bg_path)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["manifest_version"] == 3
    assert "webRequest" in manifest["permissions"]
    assert "alarms" in manifest["permissions"]
    assert "sidePanel" in manifest["permissions"]
    assert "http://127.0.0.1:8000/*" in manifest["host_permissions"]

    with open(bg_path, "r", encoding="utf-8") as f:
        bg_content = f.read()

    assert "voyager/api/identity/dash/creatorAnalytics" in bg_content
    assert "INGEST_ANALYTICS" in bg_content
    # Same endpoint, now reached through the token aware helper.
    assert 'STUDIO_ORIGIN = "http://127.0.0.1:8000"' in bg_content
    assert 'studioFetch("/api/analytics/ingest"' in bg_content
