"""
At its time a queued post is due, not published.
================================================

WRITE-15 / UX-04: the queue posts nothing, yet at a post's time it wrote status
'published' stamped with that time. The post left the Queue, Analytics listed
it as one of the creator's published posts, and it was never on LinkedIn. It is
now 'due': listed on the Queue for the creator to post, and published only
when they say they posted it.
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
from scheduler import native_scheduler  # noqa: E402

client = TestClient(app_module.app)


@pytest.fixture
def due_post():
    post_id = f"qcf1b_due_{uuid.uuid4().hex[:6]}"
    when = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, 'QC F1B due post', 'scheduled', ?)",
            (post_id, when),
        )
        conn.execute("DELETE FROM settings WHERE key = 'queue_status'")
        conn.commit()
    finally:
        conn.close()
    yield post_id
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()


def _row(post_id):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, published_at FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


def test_a_post_whose_time_has_come_is_due_not_published(due_post):
    actions = [a for a in native_scheduler.check_scheduled_queue() if a["post_id"] == due_post]
    assert [a["action"] for a in actions] == ["due_on_time"]
    row = _row(due_post)
    assert row["status"] == "due"
    assert row["published_at"] is None


def test_a_due_post_is_not_counted_as_published(due_post):
    native_scheduler.check_scheduled_queue()
    published = client.get("/api/analytics/posts").json().get("posts", [])
    assert due_post not in [p.get("id") for p in published]
    assert due_post in [p["id"] for p in client.get("/api/posts?status=due").json()["posts"]]


def test_i_posted_it_publishes_a_due_post(due_post):
    native_scheduler.check_scheduled_queue()
    assert client.post(f"/api/posts/{due_post}/publish-now").status_code == 200
    row = _row(due_post)
    assert row["status"] == "published" and row["published_at"]


def test_a_post_linkedin_holds_is_published_at_its_time_not_due(monkeypatch):
    post_id = f"qcf1b_held_{uuid.uuid4().hex[:6]}"
    conn = get_db()
    try:
        conn.execute("INSERT INTO posts (id, content, status) VALUES (?, 'QC F1B held post', 'draft')", (post_id,))
        conn.execute("DELETE FROM settings WHERE key = 'queue_status'")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(
        app_module.linkedin_client, "schedule_norm_share",
        lambda **kwargs: {"status": "success", "mode": "live", "scheduled_urn": "urn:li:share:9"},
    )
    try:
        when = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        # The account the session belongs to, as BE-09 requires; this test is
        # about what the queue does afterwards.
        monkeypatch.setattr(app_module.linkedin_client, "session_account",
                            lambda: {"vanity": "test-creator", "member_urn": "urn:li:fsd_profile:ACoAATEST123"})
        monkeypatch.setattr(app_module.linkedin_client, "is_authenticated", lambda: True)
        monkeypatch.setattr(app_module.onboarding, "confirmed_vanity", lambda: "test-creator")
        sent = client.post(f"/api/v1/posts/{post_id}/stage-to-linkedin",
                           json={"scheduled_at": when, "confirm": True, "confirm_account": "test-creator"})
        assert sent.status_code == 200, sent.text
        # Its time comes, three hours late for this machine (it was asleep).
        past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        conn = get_db()
        try:
            conn.execute("UPDATE posts SET scheduled_for = ? WHERE id = ?", (past, post_id))
            conn.commit()
        finally:
            conn.close()
        actions = [a for a in native_scheduler.check_scheduled_queue() if a["post_id"] == post_id]
        assert [a["action"] for a in actions] == ["published_by_linkedin"]
        row = _row(post_id)
        assert row["status"] == "published"
        assert row["published_at"].startswith(past[:16])
    finally:
        conn = get_db()
        try:
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            conn.execute("DELETE FROM settings WHERE key LIKE ?", ("%" + post_id,))
            conn.commit()
        finally:
            conn.close()


def test_a_due_post_still_holds_its_place_in_the_cadence(due_post):
    native_scheduler.check_scheduled_queue()
    soon = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    verdict = native_scheduler.validate_schedule_cadence(soon)
    assert verdict["has_collision"] is True
