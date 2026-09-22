"""
The queue reports what happened, not what was asked for.
========================================================

Two controls told the creator something the studio had not established.

  Pausing the queue discarded the write result, published queue_status_changed
  and returned success regardless. A failed write therefore reported the queue
  as paused while the dispatcher went on publishing, which is the single
  outcome that control exists to prevent. is_queue_paused also returned False
  on a read failure, so an unreadable setting meant "not paused", which means
  "publish".

  calculate_next_smart_slot's fallback returned cooldown_satisfied True and
  hours_clearance 24.0 without consulting a single post. With a congested
  calendar it handed back a time that had a post sitting on it. Measured: 60
  posts every 6 hours produced a slot with 0.0 hours of clearance, reported as
  a full day. The "Use Next Smart Slot" button fills the picker with it.

24 hours from the cursor says nothing about the distance from the nearest
post. Those are different numbers and only one of them is the cooldown.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from database import get_db
from scheduler import native_scheduler

CONGEST_PREFIX = "congestprobe-"


@pytest.fixture
def congested_calendar():
    """A post every six hours for fifteen days, so every slot collides."""
    conn = get_db()
    try:
        base = datetime.now(timezone.utc)
        for index in range(60):
            conn.execute(
                "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?,?,?,?)",
                (CONGEST_PREFIX + str(index), "probe", "scheduled",
                 (base + timedelta(hours=6 * index)).isoformat()),
            )
        conn.commit()
    finally:
        conn.close()

    yield

    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id LIKE ?", (CONGEST_PREFIX + "%",))
        conn.commit()
    finally:
        conn.close()


def test_the_fallback_slot_reports_its_real_clearance(congested_calendar):
    """
    It used to assert 24.0 hours without measuring. The number now comes from
    the nearest actual post.
    """
    result = native_scheduler.calculate_next_smart_slot()

    clearance = result["hours_clearance"]
    assert clearance is not None, "no clearance was reported at all"
    assert clearance < 24.0, (
        f"the fallback reported {clearance} hours of clearance on a calendar "
        f"with a post every six hours, which cannot be true"
    )


def test_a_colliding_fallback_does_not_claim_the_cooldown_is_satisfied(congested_calendar):
    result = native_scheduler.calculate_next_smart_slot()

    if result["hours_clearance"] < native_scheduler.min_cooldown_hours:
        assert result["cooldown_satisfied"] is False, (
            "a slot inside the cooldown was reported as satisfying it, and the "
            "picker is filled from this value"
        )


def test_the_label_says_so_when_the_buffer_is_not_clear(congested_calendar):
    result = native_scheduler.calculate_next_smart_slot()
    if not result["cooldown_satisfied"]:
        assert "cooldown" in result["label"].lower()


def test_an_empty_calendar_still_reports_a_clear_slot():
    """The honest path must not now report false collisions."""
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE status = 'scheduled'"
        ).fetchone()[0]
    finally:
        conn.close()
    if existing:
        pytest.skip("the sandbox already holds scheduled posts")

    result = native_scheduler.calculate_next_smart_slot()
    assert result["cooldown_satisfied"] is True


def test_setting_the_pause_state_reports_whether_it_wrote():
    """
    It returned `paused` on success and False on failure, so
    set_queue_paused(False) gave False either way and a caller could not tell
    "resumed" from "could not write".
    """
    try:
        assert native_scheduler.set_queue_paused(True) is True
        assert native_scheduler.set_queue_paused(False) is True, (
            "resuming the queue reported failure, because the return value "
            "carried the state rather than the outcome"
        )
    finally:
        native_scheduler.set_queue_paused(False)


def test_an_unreadable_setting_counts_as_paused(monkeypatch):
    """
    Fail closed. Returning False means "not paused", which means the
    dispatcher publishes, so a locked database decided on the creator's behalf
    that their queue was running. Publishing to someone's professional network
    when the studio cannot tell whether they asked for it is the worse error.
    """
    import scheduler

    def broken_db():
        raise RuntimeError("database is locked")

    monkeypatch.setattr(scheduler, "get_db", broken_db)
    assert native_scheduler.is_queue_paused() is True


def test_a_failed_pause_write_is_not_reported_as_success(monkeypatch):
    """The route reads the state back rather than echoing the request."""
    from fastapi.testclient import TestClient
    import app as app_module

    monkeypatch.setattr(
        app_module.native_scheduler, "set_queue_paused", lambda paused: False
    )
    monkeypatch.setattr(
        app_module.native_scheduler, "is_queue_paused", lambda: False
    )

    client = TestClient(app_module.app)
    response = client.post("/api/queue/toggle-pause", json={"paused": True})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error", (
        "a write that failed was reported as success, so the creator believes "
        "the queue is paused while it keeps publishing"
    )
    assert body["queue_paused"] is False, "the reported state is not the real one"
