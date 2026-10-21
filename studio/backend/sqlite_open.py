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

import contextlib
import logging
import sqlite3
import sys
import threading
import types

_log = logging.getLogger("studio.database")

# A restore replaces the database file. Windows refuses to replace a file any
# handle holds, so while the swap runs nothing in the studio may open the
# database: a screen being read at that moment, or the background summary
# catch-up, was enough to answer "Access is denied" and leave the creator in
# safe mode with the restore button that had just failed. Every connection in
# the studio is opened through this module or through database.get_db, and
# both wait here. The thread holding the files does not wait for itself.
#
# The studio's modules are imported both as studio.backend.x and as x,
# depending on how the engine was started, so a module global here would be
# two different values and half the openers would not wait. The gate lives
# beside both copies instead, under one name in sys.modules.
_STATE = sys.modules.setdefault("_inox_database_files", types.ModuleType("_inox_database_files"))
if not hasattr(_STATE, "free"):
    _STATE.free = threading.Event()
    _STATE.free.set()
    _STATE.holders = []
# How long an opener waits for a restore's swap. The swap is a handful of
# file moves; anything longer than this means something is wrong, and a
# waiting screen must answer rather than hang for ever.
HOLD_WAIT_S = 30.0


def wait_while_held(timeout: float = HOLD_WAIT_S) -> None:
    """Waits while a restore holds the database files, unless this is the restore."""
    if _STATE.free.is_set() or threading.get_ident() in _STATE.holders:
        return
    if not _STATE.free.wait(timeout):
        _log.warning("Waited %.0f s for a restore to finish replacing the database files.", timeout)


@contextlib.contextmanager
def files_held():
    """
    Holds the database files for a restore: no other thread opens them until
    this block leaves, so the file the swap replaces has no handle on it.
    """
    _STATE.holders.append(threading.get_ident())
    _STATE.free.clear()
    try:
        yield
    finally:
        _STATE.free.set()
        _STATE.holders.remove(threading.get_ident())


def secure(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Turns secure_delete on for a connection made elsewhere, and returns it."""
    conn.execute("PRAGMA secure_delete = ON")
    return conn


def connect(path: str, **kwargs) -> sqlite3.Connection:
    """sqlite3.connect, with secure_delete on, and never while a restore swaps the files."""
    wait_while_held()
    return secure(sqlite3.connect(path, **kwargs))
