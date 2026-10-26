"""
Track 6's migration: a desk request from the phone, and a home for the
analytics export's totals.
===================================================================

Asserted by name and by the columns it adds, never by its number: the
coordinator renumbers each track's migration at integration in merge order.

What it has to leave behind:

  desk_requests        one row per post link the phone sent: the post's
                       URN, when it was asked, when it was done, its state
                       (open, read, expired, dismissed, or refused for a
                       post that is not the creator's), a note, and where it
                       came from
  analytics_daily      new_followers: the export gives new followers a day,
                       not a follower count. Its daily engagements go where
                       the page reader's engagements card always has, in
                       reactions, so the table gains no engagements column
  post_metric_observations
                       engagements: per post the export gives one total,
                       and a post's readings keep reactions, comments and
                       reposts apart

Strict Invariants:
- Zero em-dashes.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import migrations  # noqa: E402

NAME_WORDS = ("desk request", "analytics export")


def _ours():
    found = [entry for entry in migrations.MIGRATIONS
             if all(word in entry[1].lower() for word in NAME_WORDS)]
    assert len(found) == 1, f"expected one migration named for {NAME_WORDS}, found {len(found)}"
    return found[0]


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


@pytest.fixture
def before(tmp_path):
    """A database as it stands just before this track's migration."""
    _version, _description, _payload = _ours()
    conn = sqlite3.connect(os.path.join(str(tmp_path), "before.db"))
    conn.execute("""
        CREATE TABLE analytics_daily (
            date TEXT PRIMARY KEY, followers INTEGER, connections INTEGER, profile_views INTEGER,
            impressions INTEGER DEFAULT 0, unique_members_reached INTEGER, reactions INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, engagement_rate REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, source TEXT, period_label TEXT, precision TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE post_metric_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, activity_urn TEXT NOT NULL, observed_at TEXT NOT NULL,
            observed_hour TEXT NOT NULL, age_hours REAL, source TEXT NOT NULL, impressions INTEGER,
            members_reached INTEGER, reactions INTEGER, comments INTEGER, reposts INTEGER, saves INTEGER,
            sends INTEGER, UNIQUE (activity_urn, source, observed_hour)
        )
    """)
    conn.execute("INSERT INTO analytics_daily (date, impressions, source) VALUES ('2026-10-01', 120, 'observed')")
    conn.commit()
    yield conn
    conn.close()


def test_the_migration_is_named_for_what_it_changes():
    _version, description, payload = _ours()
    assert callable(payload)
    assert "phone" in description.lower()


def test_it_creates_the_desk_requests_table(before):
    _version, _description, payload = _ours()
    payload(before.cursor())
    assert _columns(before, "desk_requests") >= {"id", "activity_urn", "asked_at", "done_at", "note", "source", "state"}
    before.execute("INSERT INTO desk_requests (activity_urn, asked_at) VALUES ('urn:li:activity:1', '2026-10-26')")
    assert before.execute("SELECT state FROM desk_requests").fetchone()[0] == "open", "a new request is not open"
    indexes = {row[1] for row in before.execute("PRAGMA index_list(desk_requests)")}
    assert any("desk_requests" in name for name in indexes), "the open requests have no index to be found by"


def test_it_gives_the_export_totals_a_home_and_keeps_what_was_there(before):
    _version, _description, payload = _ours()
    payload(before.cursor())
    assert "new_followers" in _columns(before, "analytics_daily")
    assert "engagements" not in _columns(before, "analytics_daily"), (
        "a second home for the daily engagements figure: the page reader keeps it in reactions")
    assert "engagements" in _columns(before, "post_metric_observations")
    row = before.execute("SELECT impressions, new_followers, source FROM analytics_daily").fetchone()
    assert row == (120, None, "observed"), "an existing day's figures changed, or the new column is not NULL"


def test_running_it_twice_changes_nothing(before):
    _version, _description, payload = _ours()
    payload(before.cursor())
    payload(before.cursor())
    assert "new_followers" in _columns(before, "analytics_daily")
    assert "engagements" in _columns(before, "post_metric_observations")


def test_a_fresh_database_has_the_table(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    import database
    import paths
    database.init_db()
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert "activity_urn" in _columns(conn, "desk_requests")
        assert "new_followers" in _columns(conn, "analytics_daily")
        assert migrations.get_schema_version(conn) == migrations.SCHEMA_VERSION
    finally:
        conn.close()
