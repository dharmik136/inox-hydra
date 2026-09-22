"""
Tests for the Developer Tools surface.
======================================

The thing worth protecting here is the boundary. A consumer build must not
expose the element picker, the annotation ledger, or any inspector, and it must
not expose them at the HTTP layer either, since hiding a button leaves the
endpoint answering to anything that can reach the port.

Validates:
1. The gate: 404 without INOX_DEV_MODE, 200 with it, on every route.
2. That the database can never talk a consumer install into enabling itself.
3. Screen and section resolution, including the unmapped marker.
4. Capture scrubbing and bounding, so a console line cannot carry a key into
   an exported sheet.
5. Reproduction fingerprints colliding for the same failure.
6. Migration 8 columns and the inspectors that read them.
7. Round tripping the annotation ledger through JSON export and import.
8. That the shipped launcher clears the flag.
9. Strict Zero Em-Dash invariant.
"""

import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db, init_db
import devtools
from internal_sheet import internal_sheet_manager

client = TestClient(app)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Every maintainer route. A new one added without a line here is a new hole.
GATED_ROUTES = [
    ("get", "/api/v1/internal-sheet/issues"),
    ("get", "/api/v1/internal-sheet/issues/1"),
    ("get", "/api/v1/internal-sheet/export.csv"),
    ("get", "/api/v1/devtools/state"),
    ("get", "/api/v1/devtools/migrations"),
    ("get", "/api/v1/devtools/coverage"),
    ("get", "/api/v1/devtools/sheet/export.json"),
]


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    conn = get_db()
    conn.execute("DELETE FROM internal_sheet_issues WHERE title LIKE '%[DEVTEST]%'")
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM internal_sheet_issues WHERE title LIKE '%[DEVTEST]%'")
    conn.commit()
    conn.close()


@pytest.fixture
def dev_mode(monkeypatch):
    monkeypatch.setenv("INOX_DEV_MODE", "1")
    yield


@pytest.fixture
def consumer_mode(monkeypatch):
    monkeypatch.delenv("INOX_DEV_MODE", raising=False)
    yield


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path", GATED_ROUTES)
def test_consumer_build_hides_every_maintainer_route(consumer_mode, method, path):
    """
    A build without the flag answers 404, not 403. 403 advertises that
    something is there, which is exactly what a consumer build should not do.
    """
    res = getattr(client, method)(path)
    assert res.status_code == 404, f"{path} leaked in a consumer build"


def test_consumer_build_refuses_annotation_writes(consumer_mode):
    res = client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".card",
        "title": "[DEVTEST] should never be written",
        "description": "A consumer build has no annotation ledger.",
    })
    assert res.status_code == 404

    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) FROM internal_sheet_issues WHERE title LIKE '%should never be written%'"
    ).fetchone()
    conn.close()
    assert row[0] == 0


def test_status_endpoint_answers_honestly_in_both_builds(consumer_mode):
    """
    The one route that stays reachable. The interface has to be able to ask
    whether the surface exists before deciding whether to render it, so this
    answers rather than 404ing and leaving the frontend guessing.
    """
    res = client.get("/api/v1/devtools/status")
    assert res.status_code == 200
    assert res.json()["dev_mode"] is False
    assert res.json()["capabilities"] == []


def test_maintainer_build_exposes_the_surface(dev_mode):
    res = client.get("/api/v1/devtools/status")
    assert res.status_code == 200
    body = res.json()
    assert body["dev_mode"] is True
    assert len(body["capabilities"]) >= 5
    assert len(body["screens"]) == 8


def test_database_cannot_enable_dev_mode_on_a_consumer_install(consumer_mode):
    """
    The environment is the outer gate. A settings row can close it but never
    open it, so a write to the database is not an escalation path.
    """
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')",
        (devtools.DEV_MODE_SETTING_KEY,),
    )
    conn.commit()
    conn.close()

    assert devtools.is_dev_mode() is False
    assert devtools.set_runtime_dev_mode(True) is False
    assert client.get("/api/v1/devtools/state").status_code == 404


def test_runtime_toggle_can_close_the_surface(dev_mode):
    """A maintainer can turn it off without restarting, and back on again."""
    assert devtools.set_runtime_dev_mode(False) is False
    assert devtools.is_dev_mode() is False
    assert client.get("/api/v1/devtools/state").status_code == 404

    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')",
        (devtools.DEV_MODE_SETTING_KEY,),
    )
    conn.commit()
    conn.close()
    assert devtools.is_dev_mode() is True


# ---------------------------------------------------------------------------
# Screens and sections
# ---------------------------------------------------------------------------

def test_screen_registry_matches_the_markup_that_exists():
    """
    The registry claims eight screens. If index.html renames one and this is
    not updated, every annotation filed there resolves to 'unknown'.
    """
    index_html = io.open(
        os.path.join(REPO_ROOT, "studio", "frontend", "index.html"), encoding="utf-8"
    ).read()
    assert devtools.verify_screen_registry(index_html) == []


def test_labelled_section_wins_over_ancestor_ids():
    screen, section = devtools.resolve_location(
        "tab-studio", "studio.editor", ["editor-card", "tab-studio"]
    )
    assert screen == "studio"
    assert section == "studio.editor"


def test_unlabelled_region_is_marked_unmapped_not_guessed():
    """
    An unlabelled area reads as a gap. Recording the raw id as though it were a
    section name would make the coverage report claim work that never happened.
    """
    screen, section = devtools.resolve_location("tab-crm", None, ["dossier-notes-body"])
    assert screen == "crm"
    assert section.startswith(devtools.UNMAPPED_PREFIX)
    assert "dossier-notes-body" in section


def test_unknown_tab_does_not_invent_a_screen():
    screen, _ = devtools.resolve_location("tab-that-does-not-exist", None, [])
    assert screen == "unknown"


# ---------------------------------------------------------------------------
# Capture handling
# ---------------------------------------------------------------------------

def test_scrub_redacts_credential_shaped_strings():
    """
    An exported sheet is a file somebody can mail. A console line in this
    application can carry a key, so scrubbing happens on the way in.
    """
    assert "sk-" not in devtools.scrub("failed with sk-abcdefghijklmnopqrstuv")
    assert "AIza" not in devtools.scrub("GET ...?key=AIzaSyABCDEFGHIJKLMNOPQRSTUV")
    assert "[redacted]" in devtools.scrub("Authorization: Bearer abcdefghijklmnop")


def test_capture_is_bounded_on_the_way_in():
    """A noisy page must not turn one annotation into a megabyte."""
    noisy = {
        "console": [{"level": "log", "message": "x" * 5000} for _ in range(500)],
        "network": [{"method": "GET", "url": "/a", "status": 500} for _ in range(500)],
        "breadcrumbs": [{"kind": "click", "label": "b"} for _ in range(500)],
    }
    clean = devtools.normalize_capture(noisy)
    assert len(clean["console"]) == devtools.MAX_CONSOLE_ENTRIES
    assert len(clean["network"]) == devtools.MAX_NETWORK_ENTRIES
    assert len(clean["breadcrumbs"]) == devtools.MAX_BREADCRUMB_ENTRIES
    assert all(len(c["message"]) <= devtools.MAX_ENTRY_CHARS + 20 for c in clean["console"])


def test_normalize_capture_tolerates_absent_input():
    clean = devtools.normalize_capture(None)
    assert clean == {"console": [], "network": [], "breadcrumbs": [], "a11y": []}


def test_same_failure_in_the_same_place_collides():
    console = [{"level": "error", "message": "TypeError: cannot read length of undefined"}]
    a = devtools.repro_fingerprint("studio", "studio.editor", "bug", console)
    b = devtools.repro_fingerprint("studio", "studio.editor", "bug", console)
    c = devtools.repro_fingerprint("queue", "queue.list", "bug", console)
    assert a == b
    assert a != c


# ---------------------------------------------------------------------------
# Annotation records
# ---------------------------------------------------------------------------

def test_annotation_records_location_and_evidence(dev_mode):
    res = client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".editor-card textarea",
        "title": "[DEVTEST] Editor loses focus on paste",
        "description": "Focus jumps to the toolbar after pasting.",
        "category": "bug",
        "severity": "high",
        "tab_id": "tab-studio",
        "section_hint": "studio.editor",
        "ancestor_ids": ["editor-card", "tab-studio"],
        "capture": {
            "console": [{"level": "error", "message": "TypeError in paste handler"}],
            "network": [{"method": "POST", "url": "/api/v1/drafts", "status": 500, "ms": 30}],
            "breadcrumbs": [{"kind": "click", "label": "Repurpose"}],
            "a11y": [{"rule": "target-below-24px", "detail": "18x18"}],
        },
    })
    assert res.status_code == 200
    issue = res.json()["issue"]

    assert issue["screen_key"] == "studio"
    assert issue["section_key"] == "studio.editor"
    assert issue["repro_hash"]
    assert issue["console_capture"][0]["level"] == "error"
    assert issue["network_capture"][0]["status"] == "500"
    assert issue["breadcrumbs"][0]["label"] == "Repurpose"
    assert issue["env_snapshot"]["app_version"]
    assert issue["a11y_findings"][0]["rule"] == "target-below-24px"


def test_duplicate_reports_are_surfaced_not_silently_filed(dev_mode):
    payload = {
        "target_selector": ".queue-card",
        "title": "[DEVTEST] Queue card shows the wrong time",
        "description": "Scheduled time renders an hour early.",
        "category": "bug",
        "tab_id": "tab-queue",
        "section_hint": "queue.list",
        "capture": {"console": [{"level": "error", "message": "Invalid Date"}]},
    }
    first = client.post("/api/v1/internal-sheet/issues", json=payload)
    assert first.json()["duplicates"] == []

    second = client.post("/api/v1/internal-sheet/issues", json=payload)
    duplicates = second.json()["duplicates"]
    assert len(duplicates) == 1
    assert duplicates[0]["id"] == first.json()["issue"]["id"]


def test_promoted_backlog_task_carries_the_evidence(dev_mode):
    res = client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".analytics-chart",
        "title": "[DEVTEST] Chart renders empty",
        "description": "No bars drawn despite rows present.",
        "tab_id": "tab-analytics",
        "promote_to_backlog": True,
        "capture": {
            "console": [{"level": "error", "message": "Cannot read property datasets"}],
            "breadcrumbs": [{"kind": "navigate", "label": "tab-analytics"}],
        },
    })
    assert res.status_code == 200
    issue = res.json()["issue"]
    assert issue["gstack_task_id"]

    conn = get_db()
    row = conn.execute(
        "SELECT specification FROM gstack_backlog WHERE id = ?", (issue["gstack_task_id"],)
    ).fetchone()
    conn.close()

    spec = row["specification"]
    assert "Screen: analytics" in spec
    assert "Cannot read property datasets" in spec
    assert "tab-analytics" in spec


# ---------------------------------------------------------------------------
# Inspectors
# ---------------------------------------------------------------------------

def test_migration_inspector_reports_a_current_schema(dev_mode):
    res = client.get("/api/v1/devtools/migrations")
    assert res.status_code == 200
    m = res.json()["migrations"]
    assert m["up_to_date"] is True
    assert m["current_version"] == m["expected_version"]
    assert m["integrity_check"] == "ok"
    assert any(entry["version"] == 8 for entry in m["ledger"])


def test_state_inspector_counts_real_tables(dev_mode):
    res = client.get("/api/v1/devtools/state")
    assert res.status_code == 200
    state = res.json()["state"]
    names = {t["table"] for t in state["tables"]}
    assert "leads" in names
    assert "internal_sheet_issues" in names
    assert state["environment"]["schema_version"] == state["environment"]["schema_expected"]


def test_coverage_separates_labelled_regions_from_unmapped(dev_mode):
    client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".a", "title": "[DEVTEST] labelled", "description": "d",
        "tab_id": "tab-studio", "section_hint": "studio.editor",
    })
    client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".b", "title": "[DEVTEST] unmapped", "description": "d",
        "tab_id": "tab-studio", "ancestor_ids": ["some-unlabelled-div"],
    })

    coverage = client.get("/api/v1/devtools/coverage").json()["coverage"]
    assert coverage["labelled"] >= 1
    assert coverage["unmapped"] >= 1


# ---------------------------------------------------------------------------
# Portability
# ---------------------------------------------------------------------------

def test_sheet_survives_an_export_and_import_round_trip(dev_mode):
    client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".portable", "title": "[DEVTEST] Carries across machines",
        "description": "Evidence must survive the move.",
        "tab_id": "tab-crm", "section_hint": "crm.dossier",
        "capture": {"console": [{"level": "error", "message": "boom"}]},
    })

    exported = client.get("/api/v1/devtools/sheet/export.json").json()
    assert exported["format"] == "inox-internal-sheet"
    assert exported["count"] >= 1

    # Importing what this machine already holds must be a no-op, not a
    # duplicate of every row.
    again = client.post("/api/v1/devtools/sheet/import", json={"payload": exported})
    assert again.status_code == 200
    assert again.json()["imported"] == 0
    assert again.json()["skipped"] >= 1


def test_import_rejects_a_file_that_is_not_a_sheet(dev_mode):
    res = client.post("/api/v1/devtools/sheet/import", json={"payload": {"format": "something-else"}})
    assert res.status_code == 400


def test_import_survives_a_bad_row_without_losing_the_good_ones(dev_mode):
    payload = {
        "format": "inox-internal-sheet",
        "format_version": 1,
        "issues": [
            {"title": "", "target_selector": ".x"},
            "not even a dict",
            {
                "title": "[DEVTEST] Good row",
                "target_selector": ".good",
                "description": "survives",
                "category": "bug",
                "severity": "low",
                "suggested_role": "DESIGNER",
                "status": "OPEN",
                "screen_key": "studio",
                "section_key": "studio.editor",
                "repro_hash": "abc123",
            },
        ],
    }
    result = client.post("/api/v1/devtools/sheet/import", json={"payload": payload}).json()
    assert result["imported"] == 1
    assert result["rejected"] == 2


def test_csv_export_leads_with_screen_and_section(dev_mode):
    client.post("/api/v1/internal-sheet/issues", json={
        "target_selector": ".csv", "title": "[DEVTEST] CSV shape",
        "description": "d", "tab_id": "tab-queue", "section_hint": "queue.list",
    })
    res = client.get("/api/v1/internal-sheet/export.csv")
    assert res.status_code == 200
    header = res.text.split("\n")[0]
    assert "Screen" in header
    assert "Section" in header
    assert "Repro Hash" in header


# ---------------------------------------------------------------------------
# Distribution and invariants
# ---------------------------------------------------------------------------

def test_shipped_launcher_clears_the_dev_flag():
    """
    A folder a stranger double clicks must never come up with the element
    picker visible, including when it inherits the variable from the shell that
    launched it.
    """
    builder = io.open(
        os.path.join(REPO_ROOT, "tools", "build_portable.py"), encoding="utf-8"
    ).read()
    assert "set INOX_DEV_MODE=" in builder


def test_devtools_surface_holds_the_zero_em_dash_invariant():
    targets = [
        os.path.join(REPO_ROOT, "studio", "backend", "devtools.py"),
        os.path.join(REPO_ROOT, "studio", "backend", "internal_sheet.py"),
        os.path.join(REPO_ROOT, "tests", "test_devtools.py"),
    ]
    for path in targets:
        content = io.open(path, encoding="utf-8").read()
        # Never typed literally here, or this file would violate the rule
        # it exists to enforce.
        assert chr(8212) not in content, f"{os.path.basename(path)} contains an em-dash"


def test_frontend_gates_the_maintainer_surface():
    """
    The drawer section must be hidden in the markup and revealed only by the
    status check, and the picker must refuse to start when the surface is off.
    """
    index_html = io.open(
        os.path.join(REPO_ROOT, "studio", "frontend", "index.html"), encoding="utf-8"
    ).read()
    assert 'id="devtools-drawer-section" hidden' in index_html

    app_js = io.open(
        os.path.join(REPO_ROOT, "studio", "frontend", "app.js"), encoding="utf-8"
    ).read()
    assert "if (!devtoolsState.enabled) return;" in app_js
    assert "devtools/status" in app_js
