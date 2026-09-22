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
from intelligence_sync import IntelligenceSyncEngine, intelligence_sync_engine, FALLBACK_TEMPLATES

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
        os.path.join(backend_dir, "intelligence_sync.py"),
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
# TASK 4: IntelligenceSyncEngine Tests
# -------------------------------------------------------------
def test_intelligence_sync_offline_fallback():
    """Verifies that IntelligenceSyncEngine seeds offline fallback templates when table is empty."""
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM viral_templates")
    conn.commit()
    conn.close()

    engine = IntelligenceSyncEngine()
    templates = engine.get_templates()
    assert len(templates) >= len(FALLBACK_TEMPLATES)

    # Verify ordered by velocity descending
    velocities = [t["velocity_score"] for t in templates]
    assert velocities == sorted(velocities, reverse=True)

    status = engine.get_status()
    assert status["status"] == "success"
    assert status["total_templates"] >= len(FALLBACK_TEMPLATES)
    assert "last_synced_at" in status


def test_intelligence_sync_http_304_not_modified():
    """Verifies HTTP 304 Not Modified handler: 0 bytes transferred, local cache remains fresh."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        etag_file = os.path.join(td, ".test_etag")
        with open(etag_file, "w", encoding="utf-8") as f:
            f.write('"etag-v1-test"')

        engine = IntelligenceSyncEngine(etag_file=etag_file)

        mock_resp = MagicMock()
        mock_resp.status_code = 304

        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = engine.sync(force=False)
            assert result["status"] == "up_to_date"
            assert result["http_code"] == 304
            assert result["bytes_transferred"] == 0
            assert result["etag"] == '"etag-v1-test"'

            # Verify If-None-Match header was passed
            mock_get.assert_called_once()
            headers_sent = mock_get.call_args[1]["headers"]
            assert headers_sent.get("If-None-Match") == '"etag-v1-test"'


def test_intelligence_sync_http_200_ok_and_etag_persistence():
    """Verifies HTTP 200 OK handler: parses categories, populates SQLite, updates ETag file."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        etag_file = os.path.join(td, ".test_etag_200")
        engine = IntelligenceSyncEngine(etag_file=etag_file)

        mock_payload = {
            "version": "2026.09.2",
            "generated_at": "2026-09-17T12:00:00Z",
            "total_hooks": 2,
            "categories": [
                {
                    "archetype": "The Micro-SaaS Reality Check",
                    "hook_text": "Most bootstrapped SaaS founders quit right before the inflection point.",
                    "velocity_score": 9.7,
                    "engagement_multiplier": "3.5x",
                    "pacing_style": "1-sentence hook + proof point",
                    "example_post_id": "urn:li:activity:998877"
                },
                {
                    "archetype": "The Clean Architecture Manifesto",
                    "hook_text": "Why we removed 40% of our dependencies and speed doubled:",
                    "velocity_score": 9.5,
                    "engagement_multiplier": "3.0x",
                    "pacing_style": "Direct claim + numerical delta",
                    "example_post_id": "urn:li:activity:998878"
                }
            ]
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_payload
        mock_resp.headers = {"ETag": '"etag-new-999"'}

        with patch("requests.get", return_value=mock_resp):
            result = engine.sync(force=True)
            assert result["status"] == "updated"
            assert result["http_code"] == 200
            assert result["hooks_count"] == 2
            assert result["etag"] == '"etag-new-999"'
            assert result["version"] == "2026.09.2"

            # Verify ETag written to disk
            assert os.path.exists(etag_file)
            with open(etag_file, "r", encoding="utf-8") as f:
                assert f.read() == '"etag-new-999"'

            # Verify items in database
            templates = engine.get_templates()
            assert len(templates) == 2
            assert templates[0]["archetype"] == "The Micro-SaaS Reality Check"
            assert templates[0]["velocity_score"] == 9.7


def test_intelligence_sync_network_failure_resilience():
    """Verifies that network exceptions fall back safely to offline templates without crashing."""
    engine = IntelligenceSyncEngine()
    with patch("requests.get", side_effect=requests.RequestException("Connection refused")):
        result = engine.sync()
        assert result["status"] == "offline_fallback"
        assert result["is_fallback"] is True
        assert "Connection refused" in result["message"]

        # Engine still serves templates safely
        templates = engine.get_templates()
        assert len(templates) > 0


# -------------------------------------------------------------
# TASK 5: Day 03 API Endpoints
# -------------------------------------------------------------
def test_intelligence_api_endpoints():
    """Validates FastAPI routes: status, templates query, and sync trigger."""
    # 1. GET /api/v1/intelligence/status
    res_status = client.get("/api/v1/intelligence/status")
    assert res_status.status_code == 200
    data_status = res_status.json()
    assert data_status["status"] == "success"
    assert "total_templates" in data_status
    assert "cdn_url" in data_status

    # 2. GET /api/v1/intelligence/templates
    res_templates = client.get("/api/v1/intelligence/templates?limit=10")
    assert res_templates.status_code == 200
    data_templates = res_templates.json()
    assert data_templates["status"] == "success"
    assert "templates" in data_templates
    assert data_templates["count"] > 0
    first_item = data_templates["templates"][0]
    assert "velocity_score" in first_item
    assert "archetype" in first_item

    # 3. POST /api/v1/intelligence/sync (with mock 304)
    mock_resp = MagicMock()
    mock_resp.status_code = 304
    with patch("requests.get", return_value=mock_resp):
        res_sync = client.post("/api/v1/intelligence/sync", json={"force": False})
        assert res_sync.status_code == 200
        data_sync = res_sync.json()
        assert data_sync["status"] == "up_to_date"
        assert data_sync["bytes_transferred"] == 0


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
