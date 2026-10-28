"""
The Queue keeps what it dispatched and missed, and shows a month of it.
=======================================================================

Batch 6 of the sections report and decision 12. The scheduler decided four
things about a post whose time came (due on time, due within the two hour
grace, missed, already published by LinkedIn) and kept none of them: the
Queue said "N posts marked due", the automatic check's answer was thrown
away, and the note that a post was missed was deleted the moment it was
posted or moved, so a missed post left no trace. A collision was a warning
string. Now every decision is a row (migration 34, queue_dispatches), kept
after the post moves on with what became of it; the due list says how late
and by which rule; a queued post says which post it is too close to; and a
Calendar sub-view draws a month of published, scheduled, due and missed
posts with the creator's own counts by weekday and month, and no best day.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
COMPONENTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_queue_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _queue(post_id, when, status="scheduled", content=None):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, ?, ?)",
                     (post_id, content or f"Words of {post_id}.", status, when.isoformat()))
    conn.close()


def _dispatches(post_id):
    from database import get_db
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT outcome, late_minutes, scheduled_for, resolved_at, resolution FROM queue_dispatches "
            "WHERE post_id = ? ORDER BY id", (post_id,))]
    finally:
        conn.close()


def test_the_migration_is_named_for_the_dispatch_history():
    import migrations
    entry = next((e for e in migrations.MIGRATIONS if "dispatched" in e[1] and "missed" in e[1]), None)
    assert entry, "no migration is named for what the queue dispatched and missed"


def test_every_decision_is_kept_with_how_late_and_by_which_rule(client):
    from scheduler import native_scheduler
    now = datetime.now(timezone.utc)
    _queue("on-time", now - timedelta(minutes=2))
    _queue("in-grace", now - timedelta(minutes=47))
    _queue("missed", now - timedelta(hours=3, minutes=10))
    native_scheduler.check_scheduled_queue()
    assert [d["outcome"] for d in _dispatches("on-time")] == ["due_on_time"]
    assert [d["outcome"] for d in _dispatches("in-grace")] == ["due_within_grace"]
    [missed] = _dispatches("missed")
    assert missed["outcome"] == "missed_due" and 185 <= missed["late_minutes"] <= 195
    assert missed["resolved_at"] is None

    due = {d["post_id"]: d for d in client.get("/api/queue/due").json()["due"]}
    assert due["in-grace"]["dispatch"]["outcome"] == "due_within_grace"
    assert 45 <= due["in-grace"]["dispatch"]["late_minutes"] <= 50


def test_a_missed_post_leaves_its_history_once_it_is_posted(client):
    from scheduler import native_scheduler
    from database import get_db
    _queue("missed", datetime.now(timezone.utc) - timedelta(hours=5))
    native_scheduler.check_scheduled_queue()
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'published', published_at = ? WHERE id = 'missed'",
                     (datetime.now(timezone.utc).isoformat(),))
    conn.close()
    native_scheduler.check_scheduled_queue()
    [kept] = _dispatches("missed")
    assert kept["outcome"] == "missed_due" and kept["resolved_at"] and kept["resolution"] == "published"


def test_a_queued_post_too_close_to_another_names_it(client):
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    _queue("first", soon, content="The first post.")
    _queue("second", soon + timedelta(hours=5), content="The second post.")
    _queue("alone", soon + timedelta(days=3), content="Far from both.")
    posts = {p["id"]: p for p in client.get("/api/queue/smart-slots").json()["scheduled_posts"]}
    assert posts["second"]["collision"]["other_id"] == "first"
    assert posts["second"]["collision"]["distance_hours"] == 5.0
    assert posts["alone"]["collision"] is None


def test_the_calendar_draws_a_month_of_published_scheduled_due_and_missed(client):
    from database import get_db
    from scheduler import native_scheduler
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES ('urn:li:activity:7390000000000000777', 'A post I published.', ?, ?, ?)",
                     (now.isoformat(), now.isoformat(), now.isoformat()))
    conn.close()
    _queue("later", now + timedelta(hours=2))
    _queue("gone", now - timedelta(hours=4))
    native_scheduler.check_scheduled_queue()
    body = client.get("/api/queue/calendar", params={"month": month}).json()
    kinds = sorted(item["kind"] for day in body["days"].values() for item in day)
    assert kinds.count("published") == 1 and kinds.count("scheduled") == 1 and kinds.count("missed") == 1
    assert body["counts"]["published"] == 1 and body["counts"]["missed"] == 1
    assert sum(body["by_weekday"]) == 1, "the weekday counts are the month's own published posts"
    assert "best" not in str(body).lower(), "the calendar names a best day"
    assert client.get("/api/queue/calendar", params={"month": "2026-13"}).status_code == 422


def test_the_queue_draws_the_calendar_the_dispatch_rule_and_the_collision():
    queue = _read(COMPONENTS, "QueueSurface.tsx")
    assert "fetchQueueCalendar" in queue and '"Calendar"' in queue
    assert "No best day is named" in queue.split("function QueueCalendar")[1]
    for words in ("WITHIN THE TWO HOUR GRACE", "ON TIME", "collision.other_at", "collision.distance_hours"):
        assert words in queue, f"the Queue does not draw {words}"
