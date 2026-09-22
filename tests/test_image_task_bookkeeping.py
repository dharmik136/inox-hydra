"""
A status poll returns one consistent moment, and the task dict has a bound.
==========================================================================

Two problems in the image studio's in-memory task table.

  get_progress took a reference to the task dict under the lock and then
  read six fields from it outside the lock, while the worker thread was
  mutating that same dict. Nothing guarantees those reads land on the same
  side of the worker's update. A poller could see status "completed" from
  after the write and result_url None from before it, and the UI renders a
  finished generation with no image.

  The eviction path only considered tasks in "completed" or "failed". The
  semaphore caps how many run at once, not how many are submitted, so a burst
  of queued work sits in the dict as "processing" with nothing eligible to
  evict and the bound does nothing. Evicting a live task is safe because
  get_progress falls back to the generation_tasks table; the dict is a
  cache, not the record.
"""

import os
import sys
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import image_studio
from image_studio import MAX_STORED_TASKS, ImageStudioManager


def _seed(manager, task_id, **fields):
    record = {
        "task_id": task_id,
        "status": "processing",
        "progress_percent": 50,
        "status_message": "working",
        "result_url": None,
        "prompt_used": None,
        "error_message": None,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    record.update(fields)
    with manager._lock:
        manager._evict_locked()
        manager._tasks[task_id] = record
    return record


def test_a_status_poll_never_mixes_two_moments():
    """
    The worker flips status and result_url together. A reader must see both
    old or both new, never a completed task with no image.
    """
    manager = ImageStudioManager()
    record = _seed(manager, "probe")

    stop = threading.Event()

    def churn():
        while not stop.is_set():
            with manager._lock:
                record["status"] = "processing"
                record["result_url"] = None
            with manager._lock:
                record["status"] = "completed"
                record["result_url"] = "/generated/probe.png"

    writer = threading.Thread(target=churn, daemon=True)
    writer.start()
    try:
        torn = 0
        for _ in range(4000):
            status = manager.get_progress("probe")
            if status["status"] == "completed" and not status["result_url"]:
                torn += 1
        assert torn == 0, (
            f"{torn} polls reported a completed generation with no image, "
            f"because the fields were read outside the lock"
        )
    finally:
        stop.set()
        writer.join(timeout=2.0)


def test_the_task_table_is_bounded_even_when_nothing_has_finished():
    """
    The case the old eviction missed entirely. Every task is in flight, so
    none was eligible, so the dict grew without limit.
    """
    manager = ImageStudioManager()
    for index in range(MAX_STORED_TASKS + 50):
        _seed(manager, f"live-{index}", status="processing")

    assert len(manager._tasks) <= MAX_STORED_TASKS, (
        f"{len(manager._tasks)} tasks are held against a cap of "
        f"{MAX_STORED_TASKS}"
    )


def test_finished_tasks_are_evicted_before_live_ones():
    """
    Both are evictable, but a finished task has already been reported and a
    live one is still being polled, so age alone is not the right order.
    """
    manager = ImageStudioManager()
    for index in range(30):
        _seed(manager, f"done-{index}", status="completed", created_at=1000 + index)
    for index in range(MAX_STORED_TASKS):
        _seed(manager, f"live-{index}", status="processing", created_at=2000 + index)

    remaining = set(manager._tasks)
    assert len(remaining) <= MAX_STORED_TASKS
    live_left = sum(1 for key in remaining if key.startswith("live-"))
    done_left = sum(1 for key in remaining if key.startswith("done-"))
    assert live_left > done_left, (
        f"eviction kept {done_left} finished tasks and dropped live ones down "
        f"to {live_left}, so a poller loses its in flight task first"
    )


def test_an_evicted_task_is_still_answerable_from_the_database():
    """
    This is what makes evicting a live task acceptable. Without the fallback
    the bound would be bought by handing the UI "not_found" for work that is
    still running.
    """
    source = open(
        os.path.join(os.path.dirname(__file__), "..", "studio", "backend", "image_studio.py"),
        encoding="utf-8",
    ).read()
    assert "SELECT * FROM generation_tasks WHERE task_id = ?" in source, (
        "the database fallback is gone, so eviction now loses tasks outright"
    )


def test_an_unknown_task_still_reports_not_found():
    manager = ImageStudioManager()
    assert manager.get_progress("nothing-here")["status"] in ("not_found",)
    assert manager.get_progress("")["status"] == "not_found"
    assert manager.get_progress(None)["status"] == "not_found"
