"""
Opening a connection while another is writing does not fail.
===========================================================

CI's Windows runner failed a thousand-capture test with "database is locked"
on `PRAGMA journal_mode = WAL`. Changing the journal mode takes a brief
exclusive lock, and get_db set it on every open, so a connection opened while
another held a write lock could not be made at all. WAL is recorded in the
database file, so it is asked for once and set only when it is something else.
"""

import os
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from studio.backend import database  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    folder = tempfile.mkdtemp(prefix="inox_wal_")
    monkeypatch.setenv("INOX_HYDRA_HOME", folder)
    database.init_db()
    return folder


def test_a_connection_opens_while_another_is_writing(home):
    holder = database.get_db()
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO settings (key, value) VALUES ('wal_test', '1')")
    try:
        opened = database.get_db()
    except sqlite3.OperationalError as refused:  # pragma: no cover
        holder.rollback()
        holder.close()
        pytest.fail(f"a second connection was refused while a write was in flight: {refused}")
    try:
        assert opened.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "wal"
    finally:
        opened.close()
        holder.rollback()
        holder.close()


def test_the_journal_mode_is_set_when_the_file_is_not_wal_yet(home):
    plain = sqlite3.connect(os.path.join(home, "data", database.DB_FILENAME))
    plain.execute("PRAGMA journal_mode = DELETE;")
    plain.close()

    conn = database.get_db()
    try:
        assert conn.execute("PRAGMA journal_mode;").fetchone()[0].lower() == "wal"
    finally:
        conn.close()
