"""
Binding a post that left the studio by any route, and inserting without lying.
=============================================================================

WRITE-09: bind-urn only considered rows carrying a stored fingerprint, and only
side-panel injection stored one. A post marked as published, queued, or sent to
LinkedIn from the Composer could never bind when the creator opened it.

BRIDGE-03 / WRITE-19: inserting from the side panel recorded a 'published' row
stamped with the moment of insertion, before anything was posted, and for a
queued post it created a second row beside the queued one.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)

TEXT = (
    "Binding probe: the week we stopped estimating in story points, the team "
    "shipped more and argued less. Here is what changed on the Monday after."
)
# A real-shaped activity id whose time bits land in 2025.
URN = "urn:li:activity:7300000000000000201"


def _row(post_id):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


def _rows_with(text):
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM posts WHERE content = ?", (text,))]
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    yield
    conn = get_db()
    try:
        conn.execute("DELETE FROM posts WHERE content LIKE 'Binding probe:%'")
        conn.execute("DELETE FROM posts WHERE activity_urn = ?", (URN,))
        conn.commit()
    finally:
        conn.close()


def _draft(text=TEXT):
    return client.post("/api/posts", json={"content": text, "status": "draft"}).json()["id"]


def _bind(text=TEXT):
    return client.post("/api/v1/posts/bind-urn", json={"activity_urn": URN, "post_text": text}).json()


# ---------------------------------------------------------------------------
# WRITE-09
# ---------------------------------------------------------------------------

def test_a_post_marked_as_published_binds_when_opened():
    post_id = _draft()
    assert client.post(f"/api/posts/{post_id}/publish-now").status_code == 200
    bound = _bind(TEXT + "\n\n#teams")
    assert bound["status"] == "bound", bound
    assert bound["post_id"] == post_id
    assert _row(post_id)["activity_urn"] == URN


def test_a_queued_post_binds_and_is_then_published():
    post_id = _draft()
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    assert client.post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": when}).status_code == 200
    bound = _bind()
    assert bound["status"] == "bound", bound
    row = _row(post_id)
    # LinkedIn has it, so the queue must not later remind the creator to post it.
    assert row["status"] == "published"
    assert row["published_at"]


def test_a_plain_draft_is_not_bound_by_whatever_post_is_opened():
    """A draft can hold someone else's words (a swipe); opening their post must not claim it."""
    _draft()
    assert _bind()["status"] == "no_match"


def test_two_matching_posts_bind_neither():
    first, second = _draft(), _draft()
    client.post(f"/api/posts/{first}/publish-now")
    client.post(f"/api/posts/{second}/publish-now")
    assert _bind()["bound"] is False
    assert _row(first)["activity_urn"] is None and _row(second)["activity_urn"] is None

def test_a_legacy_insert_copy_binds_rather_than_going_ambiguous():
    """
    Databases from before BRIDGE-03's fix hold a queued post and a second,
    armed 'published' copy the old insert route made of it. Opening the post
    must still bind the armed copy, as it did before, not neither.
    """
    import post_identity

    queued = _draft()
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    client.post(f"/api/posts/{queued}/reschedule", json={"scheduled_for": when})
    copy = "post-legacycopy1"
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, published_at, content_fingerprint) VALUES (?, ?, 'published', ?, ?)",
            (copy, TEXT, datetime.now(timezone.utc).isoformat(), post_identity.content_fingerprint(TEXT)),
        )
        conn.commit()
    finally:
        conn.close()
    bound = _bind()
    assert bound["status"] == "bound", bound
    assert bound["post_id"] == copy


def test_two_armed_matches_still_bind_neither():
    import post_identity

    conn = get_db()
    try:
        for pid in ("post-armed-a", "post-armed-b"):
            conn.execute(
                "INSERT INTO posts (id, content, status, content_fingerprint) VALUES (?, ?, 'injected', ?)",
                (pid, TEXT, post_identity.content_fingerprint(TEXT)),
            )
        conn.commit()
    finally:
        conn.close()
    assert _bind()["status"] == "ambiguous"


# ---------------------------------------------------------------------------
# BRIDGE-03 / WRITE-19
# ---------------------------------------------------------------------------

def test_an_insert_is_not_recorded_as_published():
    injected = client.post("/api/v1/posts/injected", json={"content": TEXT}).json()
    assert injected["status"] == "recorded"
    row = _row(injected["post_id"])
    assert row["status"] != "published"
    assert row["published_at"] is None
    listed = client.get("/api/posts?status=published").json()["posts"]
    assert injected["post_id"] not in [p["id"] for p in listed]


def test_an_insert_of_a_queued_post_arms_that_post_instead_of_copying_it():
    post_id = _draft()
    when = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    client.post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": when})

    injected = client.post("/api/v1/posts/injected", json={"content": TEXT, "post_id": post_id}).json()
    assert injected["post_id"] == post_id
    rows = _rows_with(TEXT)
    assert len(rows) == 1, rows
    assert rows[0]["status"] == "scheduled"

    # Without the id the text alone still finds it.
    again = client.post("/api/v1/posts/injected", json={"content": TEXT}).json()
    assert again["post_id"] == post_id
    assert len(_rows_with(TEXT)) == 1


def test_an_inserted_post_is_published_once_linkedin_shows_it():
    injected = client.post("/api/v1/posts/injected", json={"content": TEXT}).json()
    bound = _bind()
    assert bound["status"] == "bound"
    row = _row(injected["post_id"])
    assert row["status"] == "published"
    # The time LinkedIn's own id carries, not the moment of insertion.
    assert row["published_at"].startswith("2025-")


def test_an_insert_does_not_count_against_the_cadence():
    client.post("/api/v1/posts/injected", json={"content": TEXT})
    when = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
    verdict = client.post("/api/queue/validate-cadence", json={"scheduled_for": when}).json()["validation"]
    conflict = verdict.get("nearest_conflict") or {}
    assert not (verdict["has_collision"] and conflict.get("status") == "injected")
    ids = [r["id"] for r in _rows_with(TEXT)]
    assert conflict.get("id") not in ids
