"""
Frontend to Backend Contract Guards
===================================
Python tests all passed while the scheduling UI told the author a rejected
time was "100% Safe", because nothing checked that the fields app.js reads
are fields the API actually sends. The UI branched on two keys the backend
has never returned.

These tests pin the seams where the two halves meet:
1. The cadence validation payload really carries the fields the UI reads.
2. app.js does not read fields the backend does not send.
3. Every element id app.js looks up exists in index.html, except a frozen
   list of already dead ids, so no new ones can be introduced.
4. Requests go through API_BASE rather than a bare relative path.
"""

import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP_JS_PATH = os.path.join(REPO_ROOT, "studio", "frontend", "app.js")
INDEX_HTML_PATH = os.path.join(REPO_ROOT, "studio", "frontend", "index.html")

# Element ids app.js looks up that index.html does not define. Every entry is
# pre-existing dead code. The list is frozen: shrink it by fixing a lookup,
# never grow it.
KNOWN_DEAD_ELEMENT_IDS = {
    "carousel-deck-brand",
    "crm-connected-count",
    "crm-meeting-count",
    "crm-outreach-count",
    "crm-total-leads",
    "draft-title",
    "editor-hook-desc",
    "kpi-impressions",
    "post-content",
    "post-title-input",
    "sim-fold-marker",
}


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_cadence_validation_sends_the_fields_the_ui_reads():
    """Verifies the cadence payload carries every field the scheduling modal renders."""
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    res = client.post("/api/queue/validate-cadence", json={"scheduled_for": past})
    assert res.status_code == 200
    rejected = res.json()["validation"]
    assert rejected["valid"] is False, "A past time must be reported as invalid"
    assert rejected.get("error"), "A rejected time must carry the reason the UI displays"

    base = (datetime.now(timezone.utc) + timedelta(days=45)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    probe_id = f"contract_{uuid.uuid4().hex[:8]}"
    conn = get_db()
    conn.execute(
        "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, 'contract probe', 'scheduled', ?)",
        (probe_id, base.isoformat())
    )
    conn.commit()
    conn.close()

    try:
        collision = client.post(
            "/api/queue/validate-cadence",
            json={"scheduled_for": (base + timedelta(hours=3)).isoformat()}
        ).json()["validation"]
        assert collision["valid"] is True
        assert collision["has_collision"] is True
        assert collision.get("warning"), "A collision must carry the warning the UI displays"

        safe = client.post(
            "/api/queue/validate-cadence",
            json={"scheduled_for": (base + timedelta(hours=30)).isoformat()}
        ).json()["validation"]
        assert safe["has_collision"] is False
        assert safe["cadence_health_score"] == 100
        assert safe.get("distance_to_nearest_hours") is not None, (
            "The UI renders spacing from distance_to_nearest_hours"
        )
    finally:
        conn = get_db()
        conn.execute("DELETE FROM posts WHERE id = ?", (probe_id,))
        conn.commit()
        conn.close()


def test_scheduling_ui_reads_no_phantom_cadence_fields():
    """Verifies app.js does not branch on cadence fields the backend never sends."""
    content = _read(APP_JS_PATH)
    for phantom in ("is_past", "nearest_gap_hours"):
        assert phantom not in content, (
            f"app.js reads '{phantom}', which validate_schedule_cadence never returns. "
            f"That branch is dead and the UI falls through to the wrong state."
        )


def test_scheduling_ui_honours_the_valid_flag():
    """Verifies the modal checks validity rather than assuming every answer is schedulable."""
    content = _read(APP_JS_PATH)
    assert "v.valid === false" in content, (
        "validateScheduleInput must handle valid === false, otherwise a time the "
        "backend rejected renders as safe and the save fails afterwards."
    )


def test_cadence_score_of_zero_is_not_treated_as_one_hundred():
    """Verifies the score is read with an explicit undefined check, not a falsy ||."""
    content = _read(APP_JS_PATH)
    assert "v.cadence_health_score || 100" not in content, (
        "|| turns a legitimate score of 0 into 100, so the worst cadence reads as perfect."
    )


def test_every_element_id_the_javascript_looks_up_exists():
    """Verifies app.js does not query element ids that index.html never defines."""
    js = _read(APP_JS_PATH)
    html = _read(INDEX_HTML_PATH)

    html_ids = set(re.findall(r'id="([^"]+)"', html))
    js_created = set(re.findall(r'\.id\s*=\s*"([^"]+)"', js)) | set(re.findall(r'id="([^"]+)"', js))
    referenced = set(re.findall(r'getElementById\("([^"]+)"\)', js))

    missing = referenced - html_ids - js_created - KNOWN_DEAD_ELEMENT_IDS
    assert not missing, (
        f"app.js looks up element ids that do not exist in index.html: {sorted(missing)}. "
        f"These lookups silently return null and the feature does nothing."
    )

    resurrected = {i for i in KNOWN_DEAD_ELEMENT_IDS if i in html_ids}
    assert not resurrected, (
        f"These ids now exist in index.html and must be removed from "
        f"KNOWN_DEAD_ELEMENT_IDS: {sorted(resurrected)}"
    )


def test_api_calls_go_through_api_base():
    """Verifies no request uses a bare relative path while API_BASE is an absolute origin."""
    js = _read(APP_JS_PATH)
    assert 'const API_BASE = "http://127.0.0.1:8000/api"' in js

    relative_calls = re.findall(r'fetch\(\s*"(/api/[^"]*)"', js)
    assert not relative_calls, (
        f"These calls use a relative path while every other call is absolute: {relative_calls}. "
        f"They only resolve when the page happens to be served from the API origin."
    )


def test_toast_severity_argument_is_not_discarded():
    """Verifies showToast renders the severity its callers pass rather than ignoring it."""
    js = _read(APP_JS_PATH)
    assert re.search(r'function showToast\(msg,\s*type\)', js), (
        "showToast takes a severity argument: 13 call sites pass one, and when the "
        "parameter was missing every failure looked exactly like a success."
    )

    typed_calls = re.findall(r'showToast\([^;]*?,\s*"(error|success|warning|info)"\s*\)', js)
    assert typed_calls, "Expected call sites passing a severity"

    css = _read(os.path.join(REPO_ROOT, "studio", "frontend", "styles.css"))
    for severity in sorted(set(typed_calls)):
        assert f".toast-{severity}" in css, f"No .toast-{severity} rule for a severity that is passed"
