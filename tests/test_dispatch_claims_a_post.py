"""
A due post is dispatched once, by whichever cycle claims it first.
==================================================================

check_scheduled_queue runs from two places: the APScheduler thread on its
interval, and the manual dispatch endpoint at app.py. Each one selected the
due rows, updated them unconditionally, and published a post_published event.
SQLite gives neither of them a view of the other's uncommitted write, so both
could take the same row and the creator's post went to LinkedIn twice.

The stale branch had the matching version: two cycles rolling the same missed
post forward compute two different next slots and each announces its own, so
the creator is told twice where their post went, to two different places.

The write now repeats the state it expects in the WHERE clause, which makes it
a compare and swap. The first commit changes the row and the second matches
nothing, and rowcount says which one this was. That holds across processes as
well as threads, which a lock in the scheduler module would not.
"""

import os
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import scheduler as scheduler_module
from database import get_db
from scheduler import native_scheduler

PREFIX = "claimprobe-"


def _insert(post_id, scheduled_for):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?,?,?,?)",
            (post_id, "probe", "scheduled", scheduled_for),
        )
        conn.commit()
    finally:
        conn.close()


def _status(post_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)
        ).fetchone()
        return (row["status"], row["scheduled_for"]) if row else (None, None)
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean_probes():
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()
    native_scheduler.set_queue_paused(False)


def test_two_cycles_publish_a_due_post_once_between_them():
    """
    The defining case. Both cycles see the same due row; exactly one of them
    may report publishing it.
    """
    post_id = PREFIX + "concurrent"
    _insert(post_id, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())

    results = []
    barrier = threading.Barrier(2)

    def cycle():
        barrier.wait()
        results.append(native_scheduler.check_scheduled_queue())

    threads = [threading.Thread(target=cycle) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    published = [
        action
        for actions in results
        for action in (actions or [])
        if action.get("post_id") == post_id
    ]

    assert len(published) == 1, (
        f"{len(published)} cycles each reported dispatching the same post, so "
        f"it goes to LinkedIn once per cycle that saw it"
    )
    assert _status(post_id)[0] == "due"


def test_a_second_pass_over_a_published_post_reports_nothing():
    """
    The sequential form of the same thing, and the one that actually runs
    when someone clicks dispatch right after the interval fired.
    """
    post_id = PREFIX + "sequential"
    _insert(post_id, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())

    first = native_scheduler.check_scheduled_queue()
    second = native_scheduler.check_scheduled_queue()

    assert any(a.get("post_id") == post_id for a in first)
    assert not any(a.get("post_id") == post_id for a in second), (
        "the post was dispatched a second time after it was already published"
    )


def test_a_stale_post_is_rolled_forward_once():
    """
    A missed post is claimed once. It used to be rolled forward, and two rolls
    computed two different slots; since BE-02 it is marked due at its own
    time, and two cycles must still announce it only once.
    """
    post_id = PREFIX + "stale"
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    _insert(post_id, stale_at)

    results = []
    barrier = threading.Barrier(2)

    def cycle():
        barrier.wait()
        results.append(native_scheduler.check_scheduled_queue())

    threads = [threading.Thread(target=cycle) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    missed = [
        action
        for actions in results
        for action in (actions or [])
        if action.get("post_id") == post_id and action.get("action") == "missed_due"
    ]

    assert len(missed) == 1, f"{len(missed)} cycles each announced the same missed post"
    status, scheduled_for = _status(post_id)
    assert status == "due"
    assert scheduled_for == stale_at, "the missed post was moved off its own time"


def test_a_single_cycle_still_dispatches_normally():
    """Guard against the claim rejecting the ordinary uncontended case."""
    post_id = PREFIX + "solo"
    _insert(post_id, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())

    actions = native_scheduler.check_scheduled_queue()

    assert any(a.get("post_id") == post_id for a in actions)
    assert _status(post_id)[0] == "due"


def test_a_paused_queue_dispatches_nothing():
    """The pause still outranks everything, claim or no claim."""
    post_id = PREFIX + "paused"
    _insert(post_id, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat())

    native_scheduler.set_queue_paused(True)
    try:
        assert native_scheduler.check_scheduled_queue() == []
    finally:
        native_scheduler.set_queue_paused(False)

    assert _status(post_id)[0] == "scheduled"
