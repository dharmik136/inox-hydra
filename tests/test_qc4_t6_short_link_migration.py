"""
2.10.1's migration: a short link from the phone waits for the post it opens.
===========================================================================

Asserted by name and by the column it adds, never by its number: the
coordinator numbers each track's migration at integration in merge order.

desk_requests gains `link`, the lnkd.in short link the phone sent, which the
studio never follows; a request made from it keeps activity_urn '' until the
post it opens is reported or the creator presses Done. Every request made
before keeps `link` NULL: nothing is filled in.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import migrations  # noqa: E402


def _ours():
    found = [entry for entry in migrations.MIGRATIONS if "short link" in entry[1].lower()]
    assert len(found) == 1, f"expected one migration named for a short link, found {len(found)}"
    return found[0]


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


@pytest.fixture
def before(tmp_path):
    """desk_requests as track 6's first migration left it, with one request in it."""
    conn = sqlite3.connect(os.path.join(str(tmp_path), "before.db"))
    conn.execute("""
        CREATE TABLE desk_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, activity_urn TEXT NOT NULL, asked_at TEXT NOT NULL,
            done_at TEXT, note TEXT, source TEXT NOT NULL DEFAULT 'telegram', state TEXT NOT NULL DEFAULT 'open'
        )
    """)
    conn.execute("INSERT INTO desk_requests (activity_urn, asked_at) VALUES ('urn:li:activity:1', '2026-10-26')")
    conn.commit()
    yield conn
    conn.close()


def test_the_migration_is_named_for_what_it_changes():
    _version, description, payload = _ours()
    assert callable(payload)
    assert "phone" in description.lower() and "desk request" in description.lower()


def test_it_adds_the_link_and_fills_nothing_in(before):
    _version, _description, payload = _ours()
    payload(before.cursor())
    assert "link" in _columns(before, "desk_requests")
    assert before.execute("SELECT activity_urn, link, state FROM desk_requests").fetchone() == (
        "urn:li:activity:1", None, "open"), "a request made from a full link changed"


def test_running_it_twice_changes_nothing(before):
    _version, _description, payload = _ours()
    payload(before.cursor())
    payload(before.cursor())
    assert "link" in _columns(before, "desk_requests")


def test_a_fresh_database_has_the_column(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    import database
    import paths
    database.init_db()
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert "link" in _columns(conn, "desk_requests")
        assert migrations.get_schema_version(conn) == migrations.SCHEMA_VERSION
    finally:
        conn.close()
