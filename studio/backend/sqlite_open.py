"""
One Way to Open the Studio's Databases.
=======================================
DATA-01. A delete in SQLite only marks pages free unless secure_delete is on,
and Python's Windows build compiles it off. Every connection that can delete
(forget, reset, migrations, cleanups) is opened here, so a forgotten person,
or a session cookie a reset cleared, is overwritten in the file and not just
unlisted. tests/test_qc2_r4_secure_delete.py holds every opener in the studio
to this.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
"""

import sqlite3


def secure(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Turns secure_delete on for a connection made elsewhere, and returns it."""
    conn.execute("PRAGMA secure_delete = ON")
    return conn


def connect(path: str, **kwargs) -> sqlite3.Connection:
    """sqlite3.connect, with secure_delete on."""
    return secure(sqlite3.connect(path, **kwargs))
