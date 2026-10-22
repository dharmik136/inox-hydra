"""
The hourly backup survives a sleeping machine, and an old backup is a fault.
===========================================================================

Cycle 3, batch T4 (P-1). Both background jobs were registered with
APScheduler's default misfire_grace_time of one second, so every run that came
due while the machine was asleep was dropped with "Run time of job ... was
missed by ..." and the next one was a full interval later. For the hourly
backup and retention job that interval is an hour: a creator who opened the
studio, slept the laptop and woke it an hour later got no backup, no reaction
folding and no retention cleanup. Nothing treated the old backup date as a
problem either, so weeks could pass with nothing to restore from.

The first test proves the mechanism with APScheduler itself: a job whose run
time has already passed, registered the way the studio registers its own, runs
on the wake; registered with the old default it is skipped. The second holds
the judgement a stale backup now carries into /api/v1/storage.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

from apscheduler.schedulers.background import BackgroundScheduler  # noqa: E402

# How late the run is when the machine wakes. Ten seconds is what the auditor
# froze a process for; an hour is what a real sleep costs.
MISSED_BY = timedelta(seconds=10)


def _runs_when_woken(grace, coalesce=True):
    """Whether an interval job whose run time has passed is taken, with this grace."""
    ran = threading.Event()
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        ran.set,
        "interval",
        hours=1,
        next_run_time=datetime.now() - MISSED_BY,
        id="woken",
        replace_existing=True,
        max_instances=1,
        coalesce=coalesce,
        misfire_grace_time=grace,
    )
    scheduler.start()
    try:
        return ran.wait(timeout=5.0)
    finally:
        scheduler.shutdown(wait=False)


def test_a_run_missed_while_the_machine_slept_is_taken_on_the_wake():
    import scheduler
    assert not _runs_when_woken(1), "APScheduler's default would have run a job it should skip"
    assert _runs_when_woken(scheduler.MISFIRE_GRACE), "a missed hourly run is still skipped"


def test_both_background_jobs_are_registered_to_survive_a_sleep():
    import scheduler
    native = scheduler.native_scheduler
    native.start()
    try:
        jobs = {job.id: job for job in native.scheduler.get_jobs()}
        assert set(jobs) == {"queue_checker", "daily_backup_and_retention"}, sorted(jobs)
        for job_id, job in jobs.items():
            assert job.misfire_grace_time is scheduler.MISFIRE_GRACE, job_id
            assert job.coalesce is True, job_id
    finally:
        native.shutdown()


# ---------------------------------------------------------------------------
# A stale backup is visible
# ---------------------------------------------------------------------------

@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t4_sched_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _backup_made(days_ago):
    """A backup ZIP named the way the studio names its automatic ones."""
    import paths
    import support
    made = datetime.now() - timedelta(days=days_ago)
    name = f"inox_backup_automatic_{made.strftime('%Y%m%d_%H%M%S')}.zip"
    full = os.path.join(paths.get_backups_dir(), name)
    with open(full, "wb") as handle:
        handle.write(b"PK\x05\x06" + b"\0" * 18)
    return support.backup_schedule(enabled=True)


def test_a_backup_from_today_is_not_called_stale(home):
    schedule = _backup_made(0)
    assert schedule["stale"] is False
    assert schedule["never"] is False
    assert schedule["age_hours"] < 24


def test_a_backup_older_than_two_days_is_reported_as_a_problem(home):
    schedule = _backup_made(3)
    assert schedule["stale"] is True, schedule
    assert schedule["age_hours"] >= 48
    assert schedule["stale_after_hours"] == 48


def test_a_profile_with_no_backup_yet_says_so_without_calling_it_stale(home):
    import support
    schedule = support.backup_schedule(enabled=True)
    assert schedule["never"] is True
    assert schedule["stale"] is False
    assert schedule["age_hours"] is None


def test_the_storage_endpoint_carries_the_judgement(home):
    import retention
    _backup_made(5)
    backups = retention.overview()["backups"]
    assert backups["stale"] is True
    assert backups["age_hours"] >= 48


def test_backups_turned_off_are_not_a_stale_backup(home):
    import support
    _backup_made(10)
    assert support.backup_schedule(enabled=False)["stale"] is False
