"""
Forget Means Gone From the File: secure_delete on Every Connection.
===================================================================
DATA-01. A forgotten person's name and comment stayed readable in the
database file's bytes wherever SQLite was built without SECURE_DELETE,
because the studio never set the pragma: a delete only marks pages free.
The development machine's SQLite happens to default it on, so these tests
open every connection with it forced OFF, as a build without it would, and
hold the studio to turning it on itself.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import database, paths  # noqa: E402
from studio.backend.crm import ReverseCRMManager  # noqa: E402

NAME = "Zebulon Quixotefeather"
COMMENT = "Xylophonic marmalade quorum, a sentence nobody else writes"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    real_connect = sqlite3.connect

    def connect_without_secure_delete(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.execute("PRAGMA secure_delete = OFF")
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect_without_secure_delete)
    return tmp_path


def _file_bytes():
    data = b""
    db = paths.get_db_path()
    for path in (db, db + "-wal"):
        if os.path.exists(path):
            with open(path, "rb") as handle:
                data += handle.read()
    return data


def test_get_db_turns_secure_delete_on(home):
    conn = database.get_db()
    try:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    finally:
        conn.close()


def test_a_forgotten_lead_is_not_left_in_the_file(home):
    crm = ReverseCRMManager()
    made = crm.ingest_interaction(NAME, "https://www.linkedin.com/in/zebulon-q", "Founder",
                                  interaction_type="COMMENT", comment_text=COMMENT,
                                  post_urn="urn:li:activity:1")
    conn = database.get_db()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    assert NAME.encode() in _file_bytes(), "the test lead was never written"

    assert crm.purge_lead(made["lead_id"])["lead_deleted"]
    conn = database.get_db()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()

    data = _file_bytes()
    assert NAME.encode() not in data, "the forgotten person's name is still in the database file"
    assert COMMENT.encode() not in data, "the forgotten person's comment is still in the database file"


def test_the_telemetry_shard_turns_secure_delete_on(home):
    from studio.core.telemetry_shard import TelemetryEngine

    engine = TelemetryEngine(os.path.join(str(home), "data", "shard_test.db"))
    conn = engine.get_connection()
    try:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    finally:
        conn.close()


COOKIE = "AQEDzzSealedCookieMarker" + "q" * 40


def _checkpoint():
    conn = database.get_db()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def test_reset_leaves_no_session_cookie_bytes_in_the_file(home):
    from studio.backend import support

    conn = database.get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('li_at', ?)", (COOKIE,))
    conn.commit()
    conn.close()
    _checkpoint()
    assert COOKIE.encode() in _file_bytes()

    support.reset_configuration(keep_data=True)
    _checkpoint()
    assert COOKIE.encode() not in _file_bytes(), "reset left the session cookie's bytes in the database file"


def test_the_update_check_connection_turns_it_on(home):
    from studio.backend import updates

    conn = updates._connect()
    try:
        assert conn.execute("PRAGMA secure_delete").fetchone()[0] == 1
    finally:
        conn.close()


def test_every_writing_connection_goes_through_the_one_helper():
    """
    A connection that can delete must turn secure_delete on. Every opener
    in the studio calls sqlite_open.connect (or sqlite_open.secure on a
    connection it made); the only raw opens left are read-only or :memory:.
    """
    import re

    root = os.path.join(os.path.dirname(__file__), "..", "studio")
    allowed = ("mode=ro", ":memory:")
    offenders = []
    for dirpath, _, files in os.walk(root):
        if "node_modules" in dirpath or "frontend" in dirpath:
            continue
        for name in files:
            if not name.endswith(".py") or name == "sqlite_open.py":
                continue
            path = os.path.join(dirpath, name)
            lines = open(path, encoding="utf-8").read().splitlines()
            for number, line in enumerate(lines):
                if "sqlite3.connect(" not in line or line.strip().startswith("#"):
                    continue
                window = "\n".join(lines[number:number + 12])
                if any(a in line for a in allowed) or re.search(r"secure\(|secure_delete", window):
                    continue
                offenders.append(f"{os.path.relpath(path, root)}:{number + 1}: {line.strip()}")
    assert offenders == [], "connections that can delete without secure_delete:\n" + "\n".join(offenders)
