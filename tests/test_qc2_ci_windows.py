"""
What Windows does differently, reproduced where the suite runs. [CI-WINDOWS]

The Windows job of the CI run on abdad1e failed fourteen tests and errored
twice while Linux passed. Every one of those is covered here or in the test it
belongs to, and the Windows behaviour is simulated rather than skipped: a
connection that is dropped instead of refused, a plain bind that refuses the
TIME_WAIT connections the studio itself left behind, and a file another handle
in this process holds, which Windows will not let anyone rename.

Strict Invariants:
- Zero em-dashes.
"""

import http.client
import os
import socket
import sqlite3
import sys
import threading

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import database  # noqa: E402
import paths  # noqa: E402
from studio.backend import desktop  # noqa: E402
from test_qc2_r2_safe_mode import _damage  # noqa: E402


def _free_port():
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# The launcher's port probe
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failure", [
    TimeoutError("timed out"),
    ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host"),
    ConnectionAbortedError(10053, "An established connection was aborted"),
    OSError(10060, "A connection attempt failed because the connected party did not properly respond"),
])
def test_a_connection_that_fails_any_other_way_is_still_an_empty_port(monkeypatch, failure):
    """
    Windows does not always refuse a connection to a port nothing listens on.

    Only ConnectionRefusedError counted as "nothing is there", so on Windows
    every port of the range read as another program's and the launcher said
    all ten were in use without starting anything.
    """
    port = _free_port()

    def connect(self):
        raise failure

    monkeypatch.setattr(http.client.HTTPConnection, "connect", connect)
    assert desktop.probe_port(port, timeout=0.5) == ("free", None)


def test_the_studios_own_lingering_connections_are_not_another_program(monkeypatch):
    """
    [INS-08 on Windows] A plain bind on Windows refuses a port whose only
    traces are TIME_WAIT connections, so stopping the studio and starting it
    again at once would have moved it off 8000 and told the user that another
    program held it. Nothing is listening there, so the port is free.
    """
    port = _free_port()
    monkeypatch.setattr(desktop, "is_windows", lambda: True)
    monkeypatch.setattr(desktop, "_can_bind", lambda _port: False)
    assert desktop.probe_port(port, timeout=0.5) == ("free", None)


def test_a_port_this_computer_refuses_outright_is_taken(monkeypatch):
    """A port inside a Windows reserved range: no bind of any kind succeeds."""
    port = _free_port()
    monkeypatch.setattr(desktop, "is_windows", lambda: True)
    monkeypatch.setattr(desktop, "_can_bind", lambda _port: False)
    monkeypatch.setattr(desktop, "_holds_only_lingering_connections", lambda _port: False)
    assert desktop.probe_port(port, timeout=0.5) == ("taken", None)


def test_a_program_that_answers_nothing_still_holds_its_port():
    """
    A connection that opens and then says nothing is another program, not a
    free port: accepting the connection is what proves something is there.
    """
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    held = []

    def hold():
        try:
            conn, _ = listener.accept()
            held.append(conn)
        except OSError:
            pass

    thread = threading.Thread(target=hold, daemon=True)
    thread.start()
    try:
        assert desktop.probe_port(port, timeout=0.5) == ("taken", None)
    finally:
        for conn in held:
            conn.close()
        listener.close()
        thread.join(timeout=2)


# ---------------------------------------------------------------------------
# A file another handle holds, which Windows will not let anyone rename
# ---------------------------------------------------------------------------

def _handles_on(path: str):
    """The file descriptors this process holds on path, where /proc says so."""
    fds = "/proc/self/fd"
    if not os.path.isdir(fds):
        return []
    held = []
    for entry in os.listdir(fds):
        try:
            target = os.readlink(os.path.join(fds, entry))
        except OSError:
            continue
        if target == path:
            held.append(entry)
    return held


def test_opening_a_damaged_database_leaves_no_handle_on_it(tmp_path, monkeypatch):
    """
    Opening a damaged database failed on its first PRAGMA and left the
    connection, and so a handle on the file, its WAL and its shared memory
    file, open. Windows refuses to rename a file any handle holds, so the
    restore that safe mode offers answered "The process cannot access the
    file because it is being used by another process" and the one way out of
    safe mode did not work. Measured on Linux as the descriptors left behind,
    and on every platform as the rename Windows refused.
    """
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    db = paths.get_db_path()
    _damage(db)

    with pytest.raises(sqlite3.DatabaseError):
        database.get_db()

    for path in (db, db + "-wal", db + "-shm"):
        assert _handles_on(path) == [], f"{os.path.basename(path)} is still open"
    # What support._swap does to every live file, and what Windows refused.
    os.replace(db, db + ".moved")
