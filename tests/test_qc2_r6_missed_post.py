"""
A queued post missed while the machine slept becomes due at its own time.
=========================================================================

BE-02 / FRONTEND D-7: a queued post more than two hours late, for example
because the laptop was asleep at 08:30, was moved to the next free slot with
nothing but a log line and a server-sent event nobody listens to. Today and
the Queue then showed the new time as though the creator had chosen it.

Owner decision: the post keeps its time and becomes due, Today says it was
missed, and offers Post now or Move to next slot. Nothing moves on its own.
"""

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402
from scheduler import native_scheduler, parse_datetime_flexible  # noqa: E402

client = TestClient(app_module.app)


@pytest.fixture
def missed_post():
    post_id = f"qc2r6_missed_{uuid.uuid4().hex[:6]}"
    when = (datetime.now(timezone.utc) - timedelta(hours=5)).replace(microsecond=0).isoformat()
    conn = get_db()
    try:
        conn.execute("DELETE FROM settings WHERE key = 'queue_status'")
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'scheduled', ?)",
            (post_id, "QC2 R6 the Monday launch post, missed while asleep", when),
        )
        conn.commit()
    finally:
        conn.close()
    yield post_id, when
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.execute("DELETE FROM settings WHERE key LIKE ?", (f"%{post_id}",))
        conn.commit()
    finally:
        conn.close()


def _row(post_id):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


def test_a_missed_post_becomes_due_at_its_original_time(missed_post):
    post_id, when = missed_post
    actions = [a for a in native_scheduler.check_scheduled_queue() if a["post_id"] == post_id]

    assert [a["action"] for a in actions] == ["missed_due"]
    row = _row(post_id)
    assert row["status"] == "due", "a missed post was not made due"
    assert parse_datetime_flexible(row["scheduled_for"]) == parse_datetime_flexible(when), (
        "a missed post was moved off the time the creator chose"
    )


def test_today_says_it_was_missed_with_its_original_time(missed_post):
    post_id, when = missed_post
    native_scheduler.check_scheduled_queue()

    due = client.get("/api/v1/today").json()["queue"]["due"]
    mine = [d for d in due if d["post_id"] == post_id]
    assert mine, "Today does not list the missed post"
    missed = mine[0].get("missed")
    assert missed, "Today lists the post as due without saying it was missed"
    assert parse_datetime_flexible(missed["scheduled_for"]) == parse_datetime_flexible(when)
    assert missed["late_minutes"] >= 4 * 60


def test_a_post_due_on_time_is_not_called_missed():
    post_id = f"qc2r6_ontime_{uuid.uuid4().hex[:6]}"
    conn = get_db()
    try:
        conn.execute("DELETE FROM settings WHERE key = 'queue_status'")
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, 'QC2 R6 on time', 'scheduled', ?)",
            (post_id, (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()),
        )
        conn.commit()
        native_scheduler.check_scheduled_queue()
        due = client.get("/api/v1/today").json()["queue"]["due"]
        mine = [d for d in due if d["post_id"] == post_id]
        assert mine and not mine[0].get("missed")
    finally:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        conn.close()


def test_move_to_next_slot_queues_it_again_and_clears_the_notice(missed_post):
    post_id, when = missed_post
    native_scheduler.check_scheduled_queue()

    response = client.post(f"/api/posts/{post_id}/move-to-next-slot")
    assert response.status_code == 200, response.text
    body = response.json()
    row = _row(post_id)
    assert row["status"] == "scheduled"
    moved_to = parse_datetime_flexible(row["scheduled_for"])
    assert moved_to > datetime.now(timezone.utc)
    assert parse_datetime_flexible(body["scheduled_for"]) == moved_to
    assert body["message"], "the move does not say where the post went"

    due = client.get("/api/v1/today").json()["queue"]["due"]
    assert not [d for d in due if d["post_id"] == post_id]


def test_move_to_next_slot_refuses_a_post_that_is_not_due():
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO posts (id, content, status) VALUES ('qc2r6_notdue', 'QC2 R6 draft', 'draft')")
        conn.commit()
    finally:
        conn.close()
    try:
        assert client.post("/api/posts/qc2r6_notdue/move-to-next-slot").status_code == 409
        assert client.post("/api/posts/qc2r6_absent/move-to-next-slot").status_code == 404
    finally:
        conn = get_db()
        conn.execute("DELETE FROM posts WHERE id = 'qc2r6_notdue'")
        conn.commit()
        conn.close()
