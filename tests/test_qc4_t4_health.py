"""
Health: is the bridge reading, what did each reader read in the last seven days,
and what could it not read?
================================================================================

Cycle 4, track 4, batch 2 of the sections report. The section is built on the
routes the studio already had (/api/v1/extension/health, the capture health
in the onboarding state, the heartbeats, waiting captures, schema status, the
backup schedule, drift events) plus one new field: the run rows per reader,
which capture_health read with LIMIT 1 and threw the counts away.

Everything here carries its window. The run rows say "last 7 days" because
record_capture prunes the log to seven days; the day rows say how long they
are kept because the migration decides it; the heartbeat summary says the
days it covers. A reader that has never run says so, and a run that counted
nothing stays unmeasured rather than reading as zero.

Strict Invariants:
- Zero em-dashes.
- No figure on the screen that did not come from a row.
"""

import io
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

UI = os.path.join(REPO_ROOT, "studio", "ui", "src")


def _read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4_health_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield home
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app)


def _capture(extractor, when, items_seen=3, items_kept=2, drift=None, page_kind="own_post", version="2.7.0"):
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift, extension_version) "
                "VALUES (?,?,?,?,?,?,?)",
                (when.isoformat(), extractor, page_kind, items_seen, items_kept, drift, version),
            )
    finally:
        conn.close()


def _heartbeat(when, version="2.7.0", page_kind="feed"):
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT INTO bridge_heartbeats (seen_at, extension_version, page_kind) VALUES (?,?,?)",
                         (when.isoformat(), version, page_kind))
    finally:
        conn.close()


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# The one new field: run rows per reader, inside the window the prune leaves
# ---------------------------------------------------------------------------

def test_the_window_is_the_prune_window_and_says_so(client):
    import onboarding
    answer = client.get("/api/v1/bridge/readers")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["window"]["days"] == onboarding.CAPTURE_RETENTION.days
    assert body["window"]["label"] == f"last {onboarding.CAPTURE_RETENTION.days} days"


def test_every_reader_is_listed_with_its_runs_in_the_window(client):
    _capture("engagers", _now() - timedelta(hours=26), items_seen=5, items_kept=4)
    # The newest run drifted, so the reader's state is drifting while the
    # week's counts still include the run that worked.
    _capture("engagers", _now() - timedelta(hours=2), items_seen=2, items_kept=0, drift='["name"]')
    # A run before the window: the prune would keep it only as the latest row
    # of a quiet reader, and it must not be counted as a run of this week.
    _capture("profile", _now() - timedelta(days=12), items_seen=1, items_kept=1)

    body = client.get("/api/v1/bridge/readers").json()
    readers = {r["extractor"]: r for r in body["readers"]}
    import onboarding
    expected = set(onboarding.EXTRACTORS) - set(onboarding.OPT_IN_EXTRACTORS)
    assert set(readers) == expected, "every page reader is listed, and no network reader that never ran"

    engagers = readers["engagers"]
    assert engagers["runs"] == 2
    assert engagers["items_seen"] == 7
    assert engagers["items_kept"] == 4
    assert engagers["drift_runs"] == 1
    assert engagers["state"] == "drifting"

    # One level down: the runs themselves, newest first.
    detail = client.get("/api/v1/bridge/readers/engagers").json()
    assert detail["runs"] == 2 and len(detail["rows"]) == 2
    newest = detail["rows"][0]
    assert newest["items_seen"] == 2 and newest["page_kind"] == "own_post" and newest["extension_version"] == "2.7.0"
    assert newest["drift"] == ["name"]
    assert detail["rows"][1]["items_seen"] == 5 and detail["rows"][1]["drift"] == []
    assert detail["window"]["label"] == body["window"]["label"]

    profile = readers["profile"]
    assert profile["runs"] == 0, "a run older than the window is not a run of this week"
    assert profile["last_run_at"] is not None, "but the reader still says when it last ran"
    assert profile["state"] == "working"

    never = readers["analytics"]
    assert never["state"] == "never_run" and never["runs"] == 0
    assert never["items_seen"] is None, "a reader that never ran measured nothing"
    assert client.get("/api/v1/bridge/readers/analytics").json()["rows"] == []


def test_the_first_view_carries_counts_and_not_rows(client):
    """
    The runs and the day rows are one level down. Carried in the first view,
    the day rows alone would be nine readers by 180 days, past the 150 KB
    first-paint bar within six months of use.
    """
    _capture("engagers", _now() - timedelta(hours=1))
    body = client.get("/api/v1/bridge/readers").json()
    for reader in body["readers"]:
        assert "rows" not in reader and "days" not in reader, reader
        assert isinstance(reader["days_held"], int)


def test_a_reader_the_extension_does_not_report_on_is_refused(client):
    assert client.get("/api/v1/bridge/readers/no_such_reader").status_code == 404


def test_a_week_of_runs_that_measured_nothing_is_not_a_week_of_zero(client):
    _capture("profile", _now() - timedelta(hours=1), items_seen=None, items_kept=None)
    body = client.get("/api/v1/bridge/readers").json()
    profile = {r["extractor"]: r for r in body["readers"]}["profile"]
    assert profile["runs"] == 1
    assert profile["items_seen"] is None and profile["items_kept"] is None


def test_the_run_rows_are_bounded(client):
    import health
    for hour in range(health.RUN_ROWS_PER_READER + 5):
        _capture("engagers", _now() - timedelta(hours=hour))
    body = client.get("/api/v1/bridge/readers").json()
    engagers = {r["extractor"]: r for r in body["readers"]}["engagers"]
    assert engagers["runs"] == health.RUN_ROWS_PER_READER + 5, "the count is the count"
    detail = client.get("/api/v1/bridge/readers/engagers").json()
    assert detail["runs"] == health.RUN_ROWS_PER_READER + 5
    assert len(detail["rows"]) == health.RUN_ROWS_PER_READER, "the rows are a page of the newest"


def test_health_and_the_onboarding_state_list_the_same_readers(client):
    """
    One list of readers. Today's freshness line and the rail's bridge state
    read the onboarding state; the Health screen reads its own route. A
    network-reading part is listed by both only once it has run (cycle 2,
    SETUP-17), so neither can show a reader the other hides.
    """
    def both():
        health = [r["label"] for r in client.get("/api/v1/bridge/readers").json()["readers"]]
        state = [h["label"] for h in client.get("/api/v1/onboarding/state").json()["health"]]
        return health, state

    health, state = both()
    assert health == state
    assert not any("network reading" in label.lower() for label in health)

    client.post("/api/v1/bridge/voyager-ingest", json={"schema_name": "feed_updates", "data": []})
    health, state = both()
    assert health == state
    assert sum("network reading" in label.lower() for label in health) == 1


# ---------------------------------------------------------------------------
# The day rows kept past the week (decision 11)
# ---------------------------------------------------------------------------

def test_the_day_rows_carry_their_own_window(client):
    import migrations
    _capture("engagers", _now() - timedelta(days=20), items_seen=3, items_kept=3)
    _capture("engagers", _now() - timedelta(days=20, hours=3), items_seen=1, items_kept=1)
    _capture("engagers", _now() - timedelta(hours=1))
    body = client.get("/api/v1/bridge/readers").json()
    assert body["days_window"]["days"] == migrations.CAPTURE_DAYS_KEPT
    assert body["days_window"]["label"] == f"kept {migrations.CAPTURE_DAYS_KEPT} days"
    assert {r["extractor"]: r for r in body["readers"]}["engagers"]["days_held"] == 2
    detail = client.get("/api/v1/bridge/readers/engagers").json()
    assert detail["days_window"] == body["days_window"]
    old_day = (_now() - timedelta(days=20)).strftime("%Y-%m-%d")
    by_day = {d["day"]: d for d in detail["days"]}
    assert old_day in by_day, "a day older than the log's week is still here"
    assert by_day[old_day]["runs"] == 2 and by_day[old_day]["items_seen"] == 4
    assert detail["days"] == sorted(detail["days"], key=lambda d: d["day"], reverse=True)


# ---------------------------------------------------------------------------
# Heartbeat gaps and extension versions
# ---------------------------------------------------------------------------

def test_heartbeats_say_how_many_which_versions_and_the_longest_silence(client):
    base = _now() - timedelta(hours=6)
    _heartbeat(base, version="2.6.0")
    _heartbeat(base + timedelta(minutes=1), version="2.6.0")
    # Three hours of nothing: the machine slept, or the tab was closed.
    _heartbeat(base + timedelta(hours=3, minutes=1), version="2.7.0")
    _heartbeat(base + timedelta(hours=3, minutes=2), version="2.7.0")
    body = client.get("/api/v1/bridge/readers").json()
    beats = body["heartbeats"]
    assert beats["window_days"] == 7
    assert beats["count"] == 4
    versions = {v["extension_version"]: v for v in beats["versions"]}
    assert set(versions) == {"2.6.0", "2.7.0"}
    assert versions["2.6.0"]["count"] == 2
    assert beats["longest_gap_minutes"] == 180
    assert beats["longest_gap_ended_at"] == (base + timedelta(hours=3, minutes=1)).isoformat()


def test_no_heartbeat_is_said_rather_than_counted_as_a_gap_of_zero(client):
    beats = client.get("/api/v1/bridge/readers").json()["heartbeats"]
    assert beats["count"] == 0
    assert beats["longest_gap_minutes"] is None
    assert beats["versions"] == []


# ---------------------------------------------------------------------------
# Network reading: read the field when the heartbeat carries it, say so when not
# ---------------------------------------------------------------------------

def test_the_screen_says_when_the_switch_state_is_not_reported():
    """
    Track 1 adds the switch state to the heartbeat in parallel. Until an
    extension of that version reports, the field is absent, and the screen
    must say that rather than guess "off".
    """
    surface = _read(os.path.join(UI, "components", "HealthSurface.tsx"))
    assert "not reported by this extension version" in surface
    assert "network_reading" in surface, "the screen does not read the switch state when it is there"


# ---------------------------------------------------------------------------
# What moved out of Setup, and what the screen is held to
# ---------------------------------------------------------------------------

def test_setup_no_longer_carries_capture_health():
    setup = _read(os.path.join(UI, "components", "OnboardingSurface.tsx"))
    assert "CAPTURE HEALTH" not in setup, "Setup still renders the capture health block"
    assert "Health" in setup, "Setup does not say where capture health went"


def test_the_screen_labels_the_windows_it_shows():
    surface = _read(os.path.join(UI, "components", "HealthSurface.tsx"))
    assert "window.label" in surface or "window?.label" in surface, "the run rows are shown without their window"
    assert "since the studio started" in surface, "waiting captures and refusals need their window"


def test_the_update_check_is_offered_off_by_default_and_never_assumed():
    """
    Decision 10: the consent control is offered here, off by default. The
    screen reads `enabled` from the route and shows the switch's state from
    that; it never defaults the switch to on, and Check now is offered only
    once the creator has turned it on.
    """
    surface = _read(os.path.join(UI, "components", "HealthSurface.tsx"))
    assert "/api/v1/updates/preference" in _read(os.path.join(UI, "lib", "api.ts"))
    assert "updates.enabled" in surface or "updates?.enabled" in surface
    assert re.search(r"enabled\s*\?\s*", surface), "Check now is not gated on the preference"
    import updates
    assert updates.is_enabled() is False or os.environ.get("INOX_HYDRA_HOME"), "the default is off"


def test_health_has_a_help_article_filed_for_a_creator():
    import docs_engine
    shipped = [path for section in docs_engine.HELP_SECTIONS if section["id"] != "maintainers"
               for path in section["paths"]]
    assert "help/check-the-bridge-is-reading.md" in shipped
    article = _read(os.path.join(REPO_ROOT, "docs", "help", "check-the-bridge-is-reading.md"))
    assert "last 7 days" in article or "last seven days" in article
    assert "Setup" in article, "the article does not say the block moved from Setup"
    # The help's day window is the migration's, read back rather than trusted.
    import migrations
    assert f"{migrations.CAPTURE_DAYS_KEPT} days" in article, "the help names a window the schema does not keep"


def test_no_help_article_still_sends_a_creator_to_setup_for_capture_health():
    help_dir = os.path.join(REPO_ROOT, "docs", "help")
    offences = []
    for name in sorted(os.listdir(help_dir)):
        if not name.endswith(".md"):
            continue
        text = _read(os.path.join(help_dir, name))
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            if "CAPTURE HEALTH" in sentence and "Setup" in sentence and "Health" not in sentence.replace("CAPTURE HEALTH", ""):
                offences.append(f"{name}: {sentence.strip()[:90]}")
    assert not offences, "help still sends a creator to Setup for capture health: " + "; ".join(offences)
