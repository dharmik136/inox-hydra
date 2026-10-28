"""
A database being set up is left alone by the background work until init_db is done.
===================================================================================

2.10.1's Windows run: two setups failed with "database is locked" inside
init_db's get_db, on a brand-new INOX_HYDRA_HOME, with the live server running
in the same process (tests/qc2_r5_live.py). Traced on Linux with init_db
stretched and the scheduled jobs forced: the queue pass, every 30 seconds over
every creator profile, reached the default profile, whose home was now the new
one; it read user_version 0, took the database for one older than this build,
and ran a second init_db on it while the first was still migrating. Linux lets
the two finish; a slow Windows runner held one past the other's 5 second busy
timeout. The product's case is a creator profile created or switched to while
the studio runs.

A user_version of 0 is a database being set up, not an old one. The queue pass
now leaves such a database alone, without opening it, until its schema has
been written, and remembers which database file it checked rather than which
profile id, so a profile whose home changed is checked again.
"""

import os
import sqlite3
import sys
import threading
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


def test_the_queue_pass_leaves_a_database_being_set_up_alone(monkeypatch, tmp_path):
    import database
    import paths
    import scheduler

    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    queue = scheduler.NativeScheduler()
    migrated_by = []
    real_ensure = database.ensure_schema

    def slow_ensure(*args, **kwargs):
        migrated_by.append(threading.current_thread().name)
        time.sleep(0.5)
        return real_ensure(*args, **kwargs)

    monkeypatch.setattr(database, "ensure_schema", slow_ensure)
    target = paths.get_db_path()
    opened = []
    real_connect = sqlite3.connect

    def traced(*args, **kwargs):
        if args and target in str(args[0]) and threading.current_thread().name == "queue-pass":
            opened.append(str(args[0]))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", traced)
    failed = []

    def set_up():
        try:
            database.init_db()
        except Exception as error:  # pragma: no cover - the fault this exists for
            failed.append(error)

    setup = threading.Thread(target=set_up, name="init")
    setup.start()
    deadline = time.monotonic() + 5
    while not os.path.exists(target) and time.monotonic() < deadline:
        time.sleep(0.005)
    assert os.path.exists(target), "init_db never created the database"

    during = threading.Thread(target=queue.check_every_profile, name="queue-pass")
    during.start()
    during.join(timeout=30)
    setup.join(timeout=60)
    assert not failed, f"init_db failed: {failed}"
    assert migrated_by == ["init"], f"the queue pass ran init_db on a database being set up: {migrated_by}"
    assert not opened, f"the queue pass opened a database before its schema was there: {opened}"

    # Once it is set up, the pass reads it as it always did.
    after = threading.Thread(target=queue.check_every_profile, name="queue-pass")
    after.start()
    after.join(timeout=30)
    assert opened, "the queue pass never read the database once it was set up"
    assert migrated_by == ["init"], migrated_by


def test_the_queue_pass_checks_a_profile_again_when_its_home_changes(monkeypatch, tmp_path):
    """Checked once per database file, not per profile id: a new home is a new file."""
    import database
    import paths
    import scheduler

    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    queue = scheduler.NativeScheduler()
    monkeypatch.setenv("INOX_HYDRA_HOME", str(first))
    database.init_db()
    queue.check_every_profile()
    monkeypatch.setenv("INOX_HYDRA_HOME", str(second))
    target = paths.get_db_path()
    # A file whose schema has not been written: it must not be taken as checked.
    open(target, "wb").close()
    ran = []
    monkeypatch.setattr(queue, "check_scheduled_queue", lambda: ran.append(True) or [])
    queue.check_every_profile()
    assert not ran, "the queue pass read a new home's database because the profile id was checked before"
