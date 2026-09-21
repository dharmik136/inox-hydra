"""
Tests for Internal Sheet & Visual Concept Identifier Engine.
============================================================
Validates:
1. SQLite schema migration 3: internal_sheet_issues table and indexes.
2. InternalSheetManager CRUD, status toggling, and summary calculations.
3. RFC-4180 CSV export for Google Sheets and Excel compatibility.
4. G-Stack backlog promotion bridge.
5. FastAPI REST endpoints under /api/v1/internal-sheet/*.
6. Strict Zero Em-Dash invariant across code and payloads.
"""

import csv
import io
import os
import sys
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Ensure studio/backend is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
from internal_sheet import internal_sheet_manager

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_test_issues():
    """Ensures test database starts and ends clean without leftover test issues."""
    init_db()
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM internal_sheet_issues WHERE title LIKE '%[TEST]%'")
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM internal_sheet_issues WHERE title LIKE '%[TEST]%'")
    conn.commit()
    conn.close()


def test_internal_sheet_table_schema_and_indexes():
    """Validates that internal_sheet_issues table exists with all required columns and indexes."""
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in c.fetchall()}
    assert "internal_sheet_issues" in tables, "Missing internal_sheet_issues table"

    c.execute("PRAGMA table_info(internal_sheet_issues)")
    cols = {r["name"]: r["type"] for r in c.fetchall()}
    required_cols = [
        "id", "target_selector", "element_tag", "element_id", "element_classes",
        "element_text_snippet", "tab_name", "page_route", "category",
        "severity", "title", "description", "suggested_role", "status",
        "bounding_box", "viewport_resolution", "dom_path", "gstack_task_id",
        "created_at", "updated_at", "resolved_at"
    ]
    for col in required_cols:
        assert col in cols, f"Missing required column in internal_sheet_issues: {col}"

    c.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {r[0] for r in c.fetchall()}
    assert "idx_internal_sheet_status" in indexes
    assert "idx_internal_sheet_tab" in indexes
    assert "idx_internal_sheet_category" in indexes

    conn.close()


def test_internal_sheet_manager_crud():
    """Validates creating, reading, updating, and deleting an issue via manager."""
    issue = internal_sheet_manager.create_issue(
        target_selector="#post-editor-input",
        title="[TEST] Editor Fold Warning Overlap",
        description="The fold counter badge overlaps with the line numbers on smaller viewports.",
        category="ux_glitch",
        severity="high",
        suggested_role="DESIGNER",
        element_tag="TEXTAREA",
        element_id="post-editor-input",
        element_classes="editor-textarea main-input",
        element_text_snippet="First 3 lines of copy preview...",
        tab_name="composer",
        bounding_box={"top": 120, "left": 300, "width": 640, "height": 380},
        viewport_resolution="1920x1080",
        dom_path="body > div.app-container > main > textarea#post-editor-input",
        promote_to_backlog=False,
    )

    assert issue is not None
    assert issue["id"] is not None
    assert issue["status"] == "OPEN"
    assert issue["category"] == "ux_glitch"
    assert issue["severity"] == "high"
    assert issue["suggested_role"] == "DESIGNER"
    assert issue["bounding_box"] == {"top": 120, "left": 300, "width": 640, "height": 380}

    # Retrieve issue
    fetched = internal_sheet_manager.get_issue(issue["id"])
    assert fetched["title"] == "[TEST] Editor Fold Warning Overlap"

    # Update status to RESOLVED
    updated = internal_sheet_manager.update_issue_status(issue["id"], "RESOLVED")
    assert updated is True

    resolved_issue = internal_sheet_manager.get_issue(issue["id"])
    assert resolved_issue["status"] == "RESOLVED"
    assert resolved_issue["resolved_at"] is not None

    # Delete issue
    deleted = internal_sheet_manager.delete_issue(issue["id"])
    assert deleted is True
    assert internal_sheet_manager.get_issue(issue["id"]) is None


def test_internal_sheet_backlog_promotion():
    """Validates that an issue can be promoted to the G-Stack multi-agent backlog."""
    issue = internal_sheet_manager.create_issue(
        target_selector="#btn-publish",
        title="[TEST] Publish Button Missing Keyboard Shortcut",
        description="Add Cmd/Ctrl+Enter shortcut to immediately trigger mobile fold check and queue.",
        category="feature_request",
        severity="medium",
        suggested_role="ENGINEERING_MANAGER",
        promote_to_backlog=True,
    )

    assert issue["gstack_task_id"] is not None

    # Verify task exists in gstack_backlog
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM gstack_backlog WHERE id = ?", (issue["gstack_task_id"],))
    task = c.fetchone()
    assert task is not None
    assert "[FEATURE_REQUEST]" in task["title"]
    assert task["role"] == "ENGINEERING_MANAGER"
    assert task["status"] == "PENDING"
    conn.close()


def test_internal_sheet_csv_export():
    """Validates that RFC-4180 CSV export formats correctly for spreadsheet apps."""
    internal_sheet_manager.create_issue(
        target_selector="#metric-dwell-score",
        title="[TEST] Dwell Score Calculation Precision",
        description="Verify dwell score rounds to 1 decimal place instead of 4.",
        category="data_mismatch",
        severity="low",
        suggested_role="QA_LEAD",
    )

    csv_text = internal_sheet_manager.export_csv()
    assert isinstance(csv_text, str)
    assert len(csv_text) > 0

    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    header = rows[0]
    assert "Issue ID" in header
    assert "Status" in header
    assert "Target Selector" in header
    assert "Problem Description" in header

    # Verify at least one row contains our test issue
    test_rows = [r for r in rows if "[TEST] Dwell Score Calculation Precision" in r]
    assert len(test_rows) >= 1


def test_api_internal_sheet_endpoints():
    """Validates REST endpoints for issue listing, creation, status update, and CSV export."""
    # Create via API
    payload = {
        "target_selector": ".hook-card[data-id='1']",
        "title": "[TEST] Hook Card Contrast in Dark Mode",
        "description": "Increase badge contrast to meet WCAG AA standard.",
        "category": "ux_glitch",
        "severity": "medium",
        "suggested_role": "DESIGNER",
        "tab_name": "swipe",
        "page_route": "/",
        "promote_to_backlog": False,
    }
    create_res = client.post("/api/v1/internal-sheet/issues", json=payload)
    assert create_res.status_code == 200
    created_data = create_res.json()
    assert created_data["status"] == "success"
    issue_id = created_data["issue"]["id"]

    # List via API
    list_res = client.get("/api/v1/internal-sheet/issues?status=OPEN")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["status"] == "success"
    assert any(i["id"] == issue_id for i in list_data["issues"])
    assert "summary" in list_data

    # Update status via API
    patch_res = client.patch(f"/api/v1/internal-sheet/issues/{issue_id}/status", json={"status": "RESOLVED"})
    assert patch_res.status_code == 200
    assert patch_res.json()["issue"]["status"] == "RESOLVED"

    # Promote via API
    promote_res = client.post(f"/api/v1/internal-sheet/issues/{issue_id}/promote")
    assert promote_res.status_code == 200
    assert "gstack_task_id" in promote_res.json()

    # CSV Export endpoint
    csv_res = client.get("/api/v1/internal-sheet/export.csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    assert "internal_concept_sheet.csv" in csv_res.headers.get("content-disposition", "")

    # Delete via API
    del_res = client.delete(f"/api/v1/internal-sheet/issues/{issue_id}")
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True


def test_zero_em_dash_in_internal_sheet():
    """Validates that internal_sheet.py and test file strictly contain zero em-dash characters."""
    sheet_py_path = os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "internal_sheet.py")
    with open(sheet_py_path, "r", encoding="utf-8") as f:
        sheet_code = f.read()
    assert "\u2014" not in sheet_code, "Found forbidden em-dash in internal_sheet.py"

    with open(__file__, "r", encoding="utf-8") as f:
        test_code = f.read()
    assert "\u2014" not in test_code, "Found forbidden em-dash in test_internal_sheet.py"
