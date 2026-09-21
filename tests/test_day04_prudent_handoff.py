"""
Day 04 Implementation Verification Suite: G-Stack Multi-Agent Governance.
==========================================================================
Validates all mandates from Day 04 specification:
1. SQLite gstack_backlog relational schema and role indexes.
2. Day 04 Post Kit seeding ("G-Stack in Practice: Running a 6-Role Virtual Team") with 2-tier fold safety.
3. Strict Zero Em-Dash compliance (\\u2014 is strictly prohibited across all code, drafts, and tests).
4. GStackGovernanceEngine 6-role virtual team registry and multi-gate anti-slop audit engine.
5. FastAPI endpoints: GET /api/v1/gstack/roles, GET/POST /api/v1/gstack/backlog, PATCH /api/v1/gstack/backlog/{id}, POST /api/v1/gstack/audit.
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
from database import get_db, init_db, seed_day04_draft
from gstack_governance import GStackGovernanceEngine, gstack_engine, GSTACK_ROLES

client = TestClient(app)


# -------------------------------------------------------------
# TASK 1: SQLite Schema & gstack_backlog Table DDL
# -------------------------------------------------------------
def test_gstack_backlog_table_schema_and_indexes():
    """Validates that gstack_backlog table and role indexes exist with correct schemas."""
    init_db()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in c.fetchall()}
    assert "gstack_backlog" in tables, "Missing gstack_backlog table in SQLite"

    c.execute("PRAGMA table_info(gstack_backlog)")
    cols = {r["name"]: r["type"] for r in c.fetchall()}
    required_cols = [
        "id", "role", "title", "specification", "status",
        "anti_slop_check", "created_at", "updated_at"
    ]
    for col in required_cols:
        assert col in cols, f"Missing required column in gstack_backlog: {col}"

    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {r[0] for r in c.fetchall()}
    assert "idx_gstack_role" in indexes, "Missing idx_gstack_role index"

    conn.close()


# -------------------------------------------------------------
# TASK 2: Day 04 Post Kit Seeding & Mobile Fold Safety
# -------------------------------------------------------------
def test_day04_draft_seeding_and_mobile_fold_safety():
    """Validates that Day 04 Post is properly seeded with correct fold metrics and status."""
    init_db()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT id, title, raw_content, lines_above_fold, pre_fold_chars, is_pre_fold_safe, status, tags FROM drafts WHERE title LIKE '%G-Stack in Practice%'")
    draft = c.fetchone()
    assert draft is not None, "Day 04 draft was not seeded in drafts table"

    assert draft["title"] == "G-Stack in Practice: Running a 6-Role Virtual Team"
    assert draft["status"] == "DRAFT"
    assert draft["lines_above_fold"] == 3
    assert draft["pre_fold_chars"] == 130
    assert draft["is_pre_fold_safe"] == 1
    assert len(draft["raw_content"]) > 500

    tags = json.loads(draft["tags"])
    assert "#GStack" in tags
    assert "#soloDeveloper" in tags
    assert "#engineering" in tags
    assert "#YC" in tags

    # Verify post entry
    c.execute("SELECT id, status, tags FROM posts WHERE id LIKE 'post-day04-%'")
    post = c.fetchone()
    assert post is not None, "Day 04 post was not seeded in posts table"
    assert post["status"] == "scheduled"

    conn.close()


# -------------------------------------------------------------
# TASK 3: Strict Zero Em-Dashes Compliance
# -------------------------------------------------------------
def test_day04_strict_zero_em_dashes():
    """Validates that the character \\u2014 is 100% absent across Day 04 codebase and drafts."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, raw_content FROM drafts WHERE title LIKE '%G-Stack in Practice%'")
    draft = c.fetchone()
    assert draft is not None
    assert "\u2014" not in draft["title"], "Em-dash detected in Day 04 draft title"
    assert "\u2014" not in draft["raw_content"], "Em-dash detected in Day 04 draft content"

    c.execute("SELECT title, specification FROM gstack_backlog")
    for row in c.fetchall():
        assert "\u2014" not in row["title"], f"Em-dash detected in backlog title: {row['title']}"
        assert "\u2014" not in row["specification"], f"Em-dash detected in backlog spec: {row['specification']}"
    conn.close()

    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
    files_to_check = [
        os.path.join(backend_dir, "gstack_governance.py"),
        os.path.join(backend_dir, "database.py"),
        os.path.join(backend_dir, "app.py")
    ]
    for path in files_to_check:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "\u2014" not in content, f"Em-dash character \\u2014 found in {path}"


# -------------------------------------------------------------
# TASK 4: GStackGovernanceEngine Roles & Backlog
# -------------------------------------------------------------
def test_gstack_governance_engine_roles_and_backlog():
    """Validates that G-Stack governance engine exposes 6 roles and backlog lifecycle."""
    roles = gstack_engine.get_roles()
    assert len(roles) == 6
    expected_roles = ["CEO", "ENGINEERING_MANAGER", "DESIGNER", "QA_LEAD", "CSO", "RELEASE_MANAGER"]
    for er in expected_roles:
        assert er in roles
        assert "mandate" in roles[er]
        assert "prd_ref" in roles[er]

    backlog = gstack_engine.get_backlog()
    assert len(backlog) >= 6

    # Test adding a task
    task_id = gstack_engine.add_backlog_task(
        role="ENGINEERING_MANAGER",
        title="Benchmark SQLite Write Actor",
        specification="Measure latency of 100 serialized writes"
    )
    try:
        assert task_id > 0

        # Test updating task status
        updated = gstack_engine.update_backlog_status(task_id, "IN_PROGRESS")
        assert updated is True

        # Test invalid role or status raises ValueError
        with pytest.raises(ValueError):
            gstack_engine.add_backlog_task("INVALID_ROLE", "Bad", "Spec")

        with pytest.raises(ValueError):
            gstack_engine.update_backlog_status(task_id, "INVALID_STATUS")
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM gstack_backlog WHERE id = ?", (task_id,))
        conn.close()



# -------------------------------------------------------------
# TASK 5: G-Stack Anti-Slop Audit Engine (6 Gates)
# -------------------------------------------------------------
def test_gstack_anti_slop_audit_engine():
    """Validates the 6 G-Stack gates for anti-slop, fold limits, and security."""
    # 1. Clean post should achieve 100% score
    clean_post = (
        "How a solo developer ships at the speed of a 10-person Series A engineering team:\n\n"
        "The secret is Garry Tan's G-Stack mental model.\n\n"
        "Here is what makes it work across all six specialized cognitive modes."
    )
    result_clean = gstack_engine.audit_content_or_feature(clean_post, title="Clean Test Post")
    assert result_clean["passed"] is True
    assert result_clean["score"] == 100
    assert len(result_clean["violations"]) == 0

    # 2. Em-dash violation should fail Gate 1 (CEO)
    slop_post_emdash = clean_post + " This is a test \u2014 with an illegal em dash."
    result_emdash = gstack_engine.audit_content_or_feature(slop_post_emdash)
    assert result_emdash["passed"] is False
    assert result_emdash["gates"]["gate_1_ceo"]["passed"] is False
    assert any("em-dash" in v for v in result_emdash["violations"])

    # 3. Buzzword violation should fail Gate 1 (CEO)
    slop_post_buzz = clean_post + " This is a revolutionary game-changer tool."
    result_buzz = gstack_engine.audit_content_or_feature(slop_post_buzz)
    assert result_buzz["passed"] is False
    assert result_buzz["gates"]["gate_1_ceo"]["passed"] is False

    # 4. Secret leak should fail Gate 5 (CSO)
    slop_post_secret = clean_post + "\nli_at='AQEDAxxxxxx'"
    result_secret = gstack_engine.audit_content_or_feature(slop_post_secret)
    assert result_secret["passed"] is False
    assert result_secret["gates"]["gate_5_cso"]["passed"] is False


# -------------------------------------------------------------
# TASK 6: G-Stack API Endpoints
# -------------------------------------------------------------
def test_gstack_api_endpoints():
    """Validates FastAPI routes: roles, backlog query, task creation, and audit."""
    # 1. GET /api/v1/gstack/roles
    res_roles = client.get("/api/v1/gstack/roles")
    assert res_roles.status_code == 200
    data_roles = res_roles.json()
    assert data_roles["status"] == "success"
    assert len(data_roles["roles"]) == 6

    # 2. GET /api/v1/gstack/backlog
    res_backlog = client.get("/api/v1/gstack/backlog?role=CEO")
    assert res_backlog.status_code == 200
    data_backlog = res_backlog.json()
    assert data_backlog["status"] == "success"
    assert data_backlog["count"] >= 1

    # 3. POST /api/v1/gstack/backlog
    new_task = {
        "role": "QA_LEAD",
        "title": "Verify Day 04 Handoff Contract",
        "specification": "Validate all 6 G-Stack gates against regression suite",
        "status": "PENDING"
    }
    res_add = client.post("/api/v1/gstack/backlog", json=new_task)
    assert res_add.status_code == 200
    task_id = res_add.json()["task_id"]
    assert task_id > 0

    try:
        # 4. PATCH /api/v1/gstack/backlog/{id}
        res_patch = client.patch(f"/api/v1/gstack/backlog/{task_id}", json={"status": "IN_PROGRESS"})
        assert res_patch.status_code == 200
        assert res_patch.json()["updated"] is True
    finally:
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM gstack_backlog WHERE id = ?", (task_id,))
        conn.close()


    # 5. POST /api/v1/gstack/audit
    audit_payload = {
        "content": "Why high-contrast Swiss typography beats bubbly generic cards.\n\nHere is how to design for cognitive dwell time on mobile feed readers.",
        "title": "Swiss Design System"
    }
    res_audit = client.post("/api/v1/gstack/audit", json=audit_payload)
    assert res_audit.status_code == 200
    audit_data = res_audit.json()["audit"]
    assert audit_data["score"] >= 80
    assert "gates" in audit_data
