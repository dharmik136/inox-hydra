"""
Nothing May Hold the Database When a Restore Swaps It (CI-WIN2-02).
====================================================================

The Windows job of CI run 39613386365 could not restore a backup after a
lead had been forgotten: "[WinError 5] Access is denied" on the move that
puts the backup's database in place. Windows refuses to replace a file any
handle holds, and the studio's background summary catch-up, which a capture
or a forget starts, keeps a connection open for as long as it has rows to
recompute. A restore is the one way out of safe mode, so this is a creator
with a damaged database and no way back.

Measured on Linux as the descriptors open on the database when the swap
begins, the way tests/test_qc2_ci_windows.py measures the connection commit
45b94be closed.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
"""

import os
import sqlite3
import sys
import time

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
for entry in (REPO_ROOT, BACKEND, os.path.dirname(__file__)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, paths, support  # noqa: E402

RESTORE = "/api/v1/support/restore"

# ---------------------------------------------------------------------------
# CI-WIN2-02: nothing may hold the database when the restore swaps it
# ---------------------------------------------------------------------------

def _open_on(path):
    """The descriptors this process holds on the database, where /proc says so."""
    fds = "/proc/self/fd"
    if not os.path.isdir(fds):
        return []
    held = []
    for entry in os.listdir(fds):
        try:
            target = os.readlink(os.path.join(fds, entry))
        except OSError:
            continue
        if target in (path, path + "-wal", path + "-shm"):
            held.append(os.path.basename(target))
    return sorted(held)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    database.init_db()
    for name in os.listdir(paths.get_backups_dir()):
        os.remove(os.path.join(paths.get_backups_dir(), name))
    return TestClient(app_module.app)


def _watch_the_swap(monkeypatch, during=None):
    """
    What the database holds open as the swap begins, and which of the
    studio's own threads are still on it. `during` is called inside the swap,
    between the moves, where Windows refused the second one.
    """
    import threading
    seen = {}
    real = support._swap

    def watched(plan, staging):
        import post_summary
        seen["held"] = _open_on(paths.get_db_path())
        seen["workers"] = [name for name, worker in post_summary._catch_up_threads.items()
                           if worker.is_alive()]
        seen["threads"] = [t.name for t in threading.enumerate()]
        if during is not None:
            seen["during"] = during()
        return real(plan, staging)

    monkeypatch.setattr(support, "_swap", watched)
    return seen


def _lead(name):
    from studio.backend.crm import reverse_crm
    reverse_crm.ingest_interaction(full_name=name, linkedin_urn=f"https://www.linkedin.com/in/{name.lower()}-x",
                                   headline="Engineer at Example", company="Example",
                                   interaction_type="COMMENT", comment_text="Good one.")
    conn = sqlite3.connect(paths.get_db_path())
    try:
        return conn.execute("SELECT id FROM leads WHERE full_name = ? OR name = ?", (name, name)).fetchone()[0]
    finally:
        conn.close()


def test_nothing_holds_the_database_when_a_restore_swaps_it(client, monkeypatch):
    """
    The exact sequence the Windows job failed on: forget a lead, then restore
    a backup made before. Windows refuses to replace a file any handle holds,
    so the swap must begin with none, and with no thread of the studio's own
    left that is about to open one.
    """
    from studio.backend.crm import reverse_crm
    seen = _watch_the_swap(monkeypatch)

    kept, gone = _lead("Keptperson"), _lead("Goneperson")
    archive = support.create_backup("manual")
    assert reverse_crm.purge_lead(gone)["lead_deleted"]

    answer = client.post(RESTORE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 200, answer.text
    assert seen["held"] == [], f"the swap began with {seen['held']} still open on the database"
    assert seen["workers"] == [], "the background summary catch-up was still on the database"
    assert "inox-summary-catch-up" not in seen["threads"], seen["threads"]
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert gone not in {row[0] for row in conn.execute("SELECT id FROM leads")}
        assert kept in {row[0] for row in conn.execute("SELECT id FROM leads")}
    finally:
        conn.close()


def test_a_reader_that_arrives_during_the_swap_waits_for_it(client, monkeypatch):
    """
    A screen read, or anything else that opens the database, arriving while
    the swap runs must not take a handle on the file being replaced: it
    waits. On Windows such a handle is the whole defect, and a connection
    opened after the live file was moved aside recreates an empty database at
    the path the swap is about to fill.
    """
    import threading

    from studio.backend import sqlite_open
    swap_done = threading.Event()
    opened = {}
    seen = {}
    real = support._swap

    def watched(plan, staging):
        def read():
            conn = sqlite_open.connect(paths.get_db_path(), timeout=10.0)
            try:
                opened["after_the_swap"] = swap_done.is_set()
            finally:
                conn.close()

        reader = threading.Thread(target=read, name="a-reader", daemon=True)
        reader.start()
        time.sleep(0.3)
        seen["held_during"] = _open_on(paths.get_db_path())
        seen["reader"] = reader
        try:
            return real(plan, staging)
        finally:
            swap_done.set()

    monkeypatch.setattr(support, "_swap", watched)
    archive = support.create_backup("manual")
    answer = client.post(RESTORE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 200, answer.text
    seen["reader"].join(10)
    assert seen["held_during"] == [], \
        f"{seen['held_during']} was opened while the swap was replacing the database"
    assert opened.get("after_the_swap") is True, "the database was opened during the swap"


def test_a_replace_a_scanner_holds_for_a_moment_still_restores(client, monkeypatch):
    """
    A virus scanner or the search indexer holds a file for a moment and
    Windows refuses the replace with WinError 5 or 32. The restore waits and
    asks again rather than putting everything back and refusing.
    """
    _add = sqlite3.connect(paths.get_db_path())
    _add.execute("INSERT INTO posts (id, content, status) VALUES ('before-backup', 'x', 'draft')")
    _add.commit()
    _add.close()
    archive = support.create_backup("manual")

    refusals = {"left": 2}
    real = os.replace

    def refused_at_first(src, dst, **kwargs):
        if str(dst).endswith(paths.DB_FILENAME) and str(src).endswith(paths.DB_FILENAME) \
                and refusals["left"] > 0:
            refusals["left"] -= 1
            raise PermissionError(5, "Access is denied")
        return real(src, dst, **kwargs)

    monkeypatch.setattr(support.os, "replace", refused_at_first)
    monkeypatch.setattr(support, "REPLACE_WAIT_S", 0.001)
    answer = client.post(RESTORE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 200, answer.text
    assert refusals["left"] == 0, "the replace was not tried again"
    conn = sqlite3.connect(paths.get_db_path())
    try:
        assert conn.execute("SELECT COUNT(*) FROM posts WHERE id = 'before-backup'").fetchone()[0] == 1
    finally:
        conn.close()


def test_a_replace_that_stays_refused_puts_everything_back(client, monkeypatch):
    """A half applied restore is still impossible: the retry is bounded and rolls back."""
    _add = sqlite3.connect(paths.get_db_path())
    _add.execute("INSERT INTO posts (id, content, status) VALUES ('live-now', 'x', 'draft')")
    _add.commit()
    _add.close()
    archive = support.create_backup("manual")
    _add = sqlite3.connect(paths.get_db_path())
    _add.execute("INSERT INTO posts (id, content, status) VALUES ('after-backup', 'x', 'draft')")
    _add.commit()
    _add.close()

    real = os.replace

    def always_refused(src, dst, **kwargs):
        # Only the move that puts the backup's database in place, the one
        # Windows refused; putting the original back must still work.
        if str(dst).endswith(paths.DB_FILENAME) and str(src).endswith(paths.DB_FILENAME):
            raise PermissionError(5, "Access is denied")
        return real(src, dst, **kwargs)

    monkeypatch.setattr(support.os, "replace", always_refused)
    monkeypatch.setattr(support, "REPLACE_WAIT_S", 0.001)
    answer = client.post(RESTORE, json={"name": os.path.basename(archive)})
    assert answer.status_code == 500, answer.text
    assert "put back" in answer.json()["detail"]
    conn = sqlite3.connect(paths.get_db_path())
    try:
        ids = {row[0] for row in conn.execute("SELECT id FROM posts")}
    finally:
        conn.close()
    assert "after-backup" in ids and "live-now" in ids, "the restore was half applied"
