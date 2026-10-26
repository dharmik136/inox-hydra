"""
The capture log says how long a reader took, and a refused run is a run.
========================================================================

Cycle 4, track 1, phase 1 (the capture report, items 1 and 5, and the
sections report's capture_health row):

  item 1   nothing in the bridge was timed. Each reader now reports how long
           it took and how many of its reads since the last report took over
           50 ms, and the row keeps both, so a later "smoother" claim can be
           checked against a figure rather than a feeling.
  item 5   a creator analytics reading refused for identity raised before
           the captures row was written, so the reader read NOT SEEN YET
           while it was running and being refused. The row is written first.
           The schema names the extension sends and the names EXTRACTORS
           lists disagreed: three of the five were recorded under names no
           screen listed.
  health   a reader whose latest run read nothing was shown as WORKING. It
           now says so, as its own state, and keeps the date it last worked.

Strict Invariants:
- Zero em-dashes.
- A count never read is NULL, never 0.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
EXT = os.path.join(REPO_ROOT, "studio", "extension")
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def studio(monkeypatch):
    """A throwaway install, so the session's own captures cannot stand in."""
    home = tempfile.mkdtemp(prefix="inox_t1_rows_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    yield
    shutil.rmtree(home, ignore_errors=True)


def _columns(table):
    from database import get_db
    conn = get_db()
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _health(extractor):
    import onboarding
    return {entry["extractor"]: entry for entry in onboarding.capture_health()}[extractor]


def _row(extractor):
    from database import get_db
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM captures WHERE extractor = ? ORDER BY id DESC LIMIT 1",
                           (extractor,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The migration: named for what it changes, asserted by name and columns
# ---------------------------------------------------------------------------

def test_the_migration_is_named_for_what_it_records(studio):
    import migrations
    entries = [m for m in migrations.MIGRATIONS if m[2] is migrations._migrate_reader_timing_and_network_reading]
    assert len(entries) == 1, "the track's one migration is not registered"
    description = entries[0][1]
    assert "reader" in description.lower() and "network reading" in description.lower(), description
    assert "every publication has its post" in description.lower(), description


def test_the_migration_adds_the_timing_and_heartbeat_columns(studio):
    captures = _columns("captures")
    for column in ("duration_ms", "reads", "slow_reads", "long_tasks", "long_task_ms", "refused"):
        assert column in captures, f"captures has no {column} column"
    heartbeats = _columns("bridge_heartbeats")
    for column in ("network_reading", "voyager_calls"):
        assert column in heartbeats, f"bridge_heartbeats has no {column} column"


# ---------------------------------------------------------------------------
# Item 1: the reader's own timing lands on its row
# ---------------------------------------------------------------------------

def test_a_timed_run_keeps_its_duration_and_its_slow_read_count(studio):
    import onboarding
    onboarding.record_capture({
        "extractor": "engagers", "page_kind": "feed", "items_seen": 4, "items_kept": 2,
        "duration_ms": 61.4, "reads": 7, "slow_reads": 2, "long_tasks": 1, "long_task_ms": 58.0,
    })
    row = _row("engagers")
    assert row["duration_ms"] == pytest.approx(61.4)
    assert row["reads"] == 7 and row["slow_reads"] == 2
    assert row["long_tasks"] == 1 and row["long_task_ms"] == pytest.approx(58.0)
    entry = _health("engagers")
    assert entry["duration_ms"] == pytest.approx(61.4)
    assert entry["slow_reads"] == 2 and entry["reads"] == 7


def test_an_untimed_run_is_not_measured_rather_than_zero(studio):
    """An older extension sends no timing; the row and the health say so."""
    import onboarding
    onboarding.record_capture({"extractor": "profile", "page_kind": "profile", "items_seen": 3, "items_kept": 3})
    row = _row("profile")
    assert row["duration_ms"] is None and row["slow_reads"] is None and row["reads"] is None
    entry = _health("profile")
    assert entry["duration_ms"] is None and entry["slow_reads"] is None


def test_a_nonsense_timing_is_refused_not_stored(studio):
    import onboarding
    onboarding.record_capture({"extractor": "profile", "items_seen": 1, "items_kept": 1,
                               "duration_ms": -5, "slow_reads": "many", "reads": 2.5})
    row = _row("profile")
    assert row["duration_ms"] is None and row["slow_reads"] is None
    assert row["reads"] == 2, "a fractional count is read as whole reads"


# ---------------------------------------------------------------------------
# Item 5: a refused network reading is a run that was refused
# ---------------------------------------------------------------------------

def test_a_creator_analytics_reading_refused_for_identity_leaves_a_refused_row(studio):
    import onboarding
    with pytest.raises(onboarding.RefusedCapture):
        onboarding.record_voyager_ingest({
            "schema_name": "creator_analytics", "vanity": "nobody-confirmed",
            "data": [{"followers": 10}], "extension_version": "test",
        })
    entry = _health("voyager_creator_analytics")
    assert entry["state"] == "refused", "a refused reading still reads as never run"
    assert entry["refused"] == "identity"
    assert entry["last_run_at"] is not None
    assert entry["last_good_at"] is None, "a refused run is not a good run"


def test_the_schema_names_the_extension_sends_are_the_names_the_health_lists(studio):
    """
    voyager_schema.js names five schemas and content.js sends each as
    voyager_<name>. Every one is listed, opt-in, or the health cannot show it.
    """
    import onboarding
    with open(os.path.join(EXT, "voyager_schema.js"), encoding="utf-8") as handle:
        schema = handle.read()
    registry = schema[schema.index("const VOYAGER_SCHEMAS = {"):schema.index("};", schema.index("const VOYAGER_SCHEMAS = {"))]
    sent = {"voyager_" + name for name in re.findall(r"^  ([a-z_]+): \{", registry, flags=re.MULTILINE)}
    assert len(sent) == 5, sent
    listed = {name for name in onboarding.EXTRACTORS if name.startswith("voyager_")}
    assert sent == listed, f"sent {sorted(sent)} but listed {sorted(listed)}"
    assert sent <= set(onboarding.OPT_IN_EXTRACTORS), "a network reading part is listed as if it ran for everyone"


def test_a_schema_name_the_registry_does_not_know_is_refused(studio):
    import onboarding
    with pytest.raises(onboarding.RefusedCapture):
        onboarding.record_voyager_ingest({"schema_name": "something_else", "data": []})
    assert _row("voyager_something_else") is None


def test_an_accepted_network_reading_still_records_its_run(studio):
    import onboarding
    onboarding.record_voyager_ingest({"schema_name": "feed_updates", "data": []})
    entry = _health("voyager_feed_updates")
    assert entry["state"] == "read_nothing"
    assert entry["refused"] is None


# ---------------------------------------------------------------------------
# The sections report's row: WORKING shown for a reader that read nothing
# ---------------------------------------------------------------------------

def _age(extractor, days, **fields):
    from database import get_db
    when = datetime.now(timezone.utc) - timedelta(days=days)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift) "
                "VALUES (?,?,?,?,?,?)",
                (when.isoformat(), extractor, "own_profile",
                 fields.get("items_seen", 1), fields.get("items_kept", 1), fields.get("drift")),
            )
    finally:
        conn.close()
    return when


def test_a_reader_whose_latest_run_read_nothing_does_not_say_working(studio):
    worked = _age("activity_posts", days=3, items_seen=6, items_kept=6)
    _age("activity_posts", days=1, items_seen=0, items_kept=0)
    entry = _health("activity_posts")
    assert entry["state"] == "read_nothing", "a run that read nothing is reported as working"
    assert entry["last_good_at"] == worked.isoformat(), "the date it last worked is lost outside the drifting state"


def test_a_reader_that_read_something_is_working(studio):
    _age("activity_posts", days=1, items_seen=6, items_kept=0)
    assert _health("activity_posts")["state"] == "working"


def test_every_state_is_one_the_screens_know(studio):
    """The states a row can produce, in one place, so a screen cannot meet one it does not draw."""
    import onboarding
    assert set(onboarding.CAPTURE_STATES) == {"never_run", "working", "drifting", "read_nothing", "refused"}
