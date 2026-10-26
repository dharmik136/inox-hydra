"""
Migration: reply marks, and a day of each reader's runs kept past the week.
===========================================================================

Cycle 4, track 4 (the sections report, decisions 9 and 11).

Replies needs a state the studio can stand behind. Whether a creator answered
a comment is not derivable from anything the bridge reads (crm.py writes the
interaction and nothing about the reply), so the only honest state is the one
the creator sets: a row in reply_marks, keyed the way lead_interactions keys
a comment. A forgotten lead takes their marks with them, as migration 19
does for everything else about a person.

Health reads the capture log, which record_capture prunes to seven days. The
screen says "last 7 days" because of that prune; what a reader did in the
weeks before is gone. A per-reader daily summary row is rolled up by a trigger
as each capture lands and is kept for CAPTURE_DAYS_KEPT days, so the log stays
bounded and the longer history survives it. The trigger lives in the schema
rather than in record_capture so the roll-up cannot be forgotten by a writer.

The tests assert the migration's name and the columns it adds, never its
number: the coordinator renumbers at integration.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import migrations  # noqa: E402

NAME_WORDS = ("marked answered", "reader")


def _the_migration():
    found = [entry for entry in migrations.MIGRATIONS if all(word in entry[1] for word in NAME_WORDS)]
    assert len(found) == 1, f"expected one migration named for reply marks and reader days, found {found}"
    return found[0]


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4_migration_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield home
    shutil.rmtree(home, ignore_errors=True)


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_the_migration_is_named_for_what_it_changes():
    _version, name, _payload = _the_migration()
    assert "answered" in name and "reader" in name, name


def test_reply_marks_is_keyed_the_way_a_comment_is(studio):
    """One mark per comment: the lead, the post and the comment key, as lead_interactions keys them."""
    from database import get_db
    conn = get_db()
    try:
        assert _columns(conn, "reply_marks") == {"lead_id", "post_urn", "comment_key", "marked_at"}
        conn.execute("INSERT INTO reply_marks (lead_id, post_urn, comment_key, marked_at) VALUES ('lead-1', 'urn:li:activity:1', 'k', '2026-10-20T00:00:00+00:00')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO reply_marks (lead_id, post_urn, comment_key, marked_at) VALUES ('lead-1', 'urn:li:activity:1', 'k', '2026-10-21T00:00:00+00:00')")
    finally:
        conn.close()


def test_a_forgotten_lead_takes_their_marks_with_them(studio):
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT INTO leads (id, name) VALUES ('lead-gone', 'Someone')")
            conn.execute("INSERT INTO reply_marks (lead_id, post_urn, comment_key, marked_at) VALUES ('lead-gone', 'urn:li:activity:1', 'k', '2026-10-20T00:00:00+00:00')")
            conn.execute("DELETE FROM leads WHERE id = 'lead-gone'")
        left = conn.execute("SELECT COUNT(*) FROM reply_marks WHERE lead_id = 'lead-gone'").fetchone()[0]
    finally:
        conn.close()
    assert left == 0, "a forgotten lead's reply marks outlived them"


def test_capture_days_holds_one_row_per_reader_per_day(studio):
    from database import get_db
    conn = get_db()
    try:
        assert _columns(conn, "capture_days") == {
            "day", "extractor", "runs", "items_seen", "items_kept", "drift_runs", "first_run_at", "last_run_at",
        }
    finally:
        conn.close()


def _capture(extractor, when, items_seen=3, items_kept=2, drift=None):
    from database import get_db
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO captures (observed_at, extractor, page_kind, items_seen, items_kept, drift) "
                "VALUES (?,?,?,?,?,?)",
                (when.isoformat(), extractor, "own_profile", items_seen, items_kept, drift),
            )
    finally:
        conn.close()


def test_each_capture_rolls_into_its_reader_day(studio):
    """Two runs on one day become one row that counts both; a drifting run is counted as such."""
    from database import get_db
    day = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    _capture("engagers", day, items_seen=3, items_kept=2)
    _capture("engagers", day + timedelta(hours=5), items_seen=4, items_kept=0, drift='["name"]')
    _capture("profile", day + timedelta(hours=1), items_seen=1, items_kept=1)
    conn = get_db()
    try:
        rows = {(r["day"], r["extractor"]): dict(r) for r in conn.execute("SELECT * FROM capture_days")}
    finally:
        conn.close()
    engagers = rows[("2026-10-20", "engagers")]
    assert engagers["runs"] == 2
    assert engagers["items_seen"] == 7
    assert engagers["items_kept"] == 2
    assert engagers["drift_runs"] == 1
    assert engagers["first_run_at"] == day.isoformat()
    assert engagers["last_run_at"] == (day + timedelta(hours=5)).isoformat()
    assert rows[("2026-10-20", "profile")]["runs"] == 1


def test_a_run_that_counted_nothing_leaves_the_day_unmeasured_rather_than_zero(studio):
    """items_seen NULL on every run stays NULL on the day: an unmeasured day is not a day of zero."""
    from database import get_db
    day = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    _capture("profile", day, items_seen=None, items_kept=None)
    conn = get_db()
    try:
        row = conn.execute("SELECT items_seen, items_kept, runs FROM capture_days WHERE extractor = 'profile'").fetchone()
    finally:
        conn.close()
    assert row["runs"] == 1
    assert row["items_seen"] is None and row["items_kept"] is None


def test_the_day_outlives_the_seven_day_prune(studio):
    """The whole point: record_capture prunes the log, and the day row stays."""
    import onboarding
    from database import get_db
    old = datetime.now(timezone.utc) - timedelta(days=30)
    _capture("engagers", old)
    _capture("engagers", old + timedelta(days=1))
    # A fresh capture through the real writer runs the prune.
    onboarding.record_capture({"extractor": "engagers", "items_seen": 1, "items_kept": 1})
    conn = get_db()
    try:
        log = conn.execute("SELECT COUNT(*) FROM captures WHERE observed_at < ?",
                           ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),)).fetchone()[0]
        days = conn.execute("SELECT COUNT(*) FROM capture_days WHERE extractor = 'engagers' AND day < ?",
                            ((datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d"),)).fetchone()[0]
    finally:
        conn.close()
    assert log <= 1, "the log kept more old rows than the prune allows (one latest-good row may stay)"
    assert days == 2, "the per-reader day rows did not outlive the prune"


def test_days_older_than_the_kept_window_age_out(studio):
    from database import get_db
    ancient = datetime.now(timezone.utc) - timedelta(days=migrations.CAPTURE_DAYS_KEPT + 5)
    _capture("engagers", ancient)
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM capture_days").fetchone()[0] == 1
    finally:
        conn.close()
    _capture("engagers", datetime.now(timezone.utc))
    conn = get_db()
    try:
        days = [r[0] for r in conn.execute("SELECT day FROM capture_days ORDER BY day")]
    finally:
        conn.close()
    assert ancient.strftime("%Y-%m-%d") not in days, "a day past the kept window was not removed"
    assert len(days) == 1


def test_the_kept_window_is_one_number(studio):
    """The trigger's window and the constant a screen reads are the same number."""
    from database import get_db
    conn = get_db()
    try:
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'capture_day_rolled_up'").fetchone()[0]
    finally:
        conn.close()
    assert f"-{migrations.CAPTURE_DAYS_KEPT} days" in sql, sql
    assert migrations.CAPTURE_DAYS_KEPT > 7


def test_rows_already_in_the_log_are_rolled_up_when_the_migration_runs(studio):
    """An install that upgrades keeps the week it already holds as days, not just the runs from now on."""
    from database import get_db
    _version, _name, payload = _the_migration()
    conn = get_db()
    try:
        with conn:
            conn.execute("DROP TRIGGER capture_day_rolled_up")
            conn.execute("DELETE FROM capture_days")
            when = datetime.now(timezone.utc) - timedelta(days=2)
            conn.execute("INSERT INTO captures (observed_at, extractor, items_seen, items_kept) VALUES (?, 'profile', 2, 2)",
                         (when.isoformat(),))
            cursor = conn.cursor()
            payload(cursor)
        row = conn.execute("SELECT runs, items_seen FROM capture_days WHERE extractor = 'profile'").fetchone()
    finally:
        conn.close()
    assert row is not None and row["runs"] == 1 and row["items_seen"] == 2
