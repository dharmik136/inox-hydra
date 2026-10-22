"""
Publishing from the studio reaches everything an imported post reaches.
=======================================================================

Measured before this batch, with the same trace the research used: publishing
a post moved two tables, posts and search_docs, and that was all. No
publication record, so Insights, Patterns, Evidence, the Voice pack and the
Analytics overview could not see the post; no fingerprint armed, so binding it
later depended on recomputing one; no engagement row, so the Posts screen had
nowhere to read. The only way a published post became a first class post was
for the creator to open their own activity page with the extension running and
let LinkedIn hand it back.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import post_identity
import post_summary
from app import app
from database import get_db

client = TestClient(app)

TEXT = ("We moved the status page off the cluster it was reporting on, which is a sentence "
        "that should never have needed writing, and here is what the week after looked like.")


@pytest.fixture
def published():
    """A post written in the studio and published from it."""
    created = client.post("/api/posts", json={"content": TEXT, "status": "draft"}).json()
    post_id = created["id"]
    answer = client.post(f"/api/posts/{post_id}/publish-now").json()
    assert answer["status"] == "success", answer
    yield post_id, answer
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM own_posts WHERE post_id = ?", (post_id,))
            conn.execute("DELETE FROM post_engagement WHERE post_urn = ?", (post_identity.local_urn(post_id),))
            conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    finally:
        conn.close()


def _one(sql, params=()):
    conn = get_db()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_publishing_writes_the_publication_record(published):
    post_id, answer = published
    urn = answer["publication_urn"]
    assert urn == post_identity.local_urn(post_id), answer

    publication = _one("SELECT * FROM own_posts WHERE activity_urn = ?", (urn,))
    assert publication is not None, "the studio still cannot see its own published post"
    assert publication["post_id"] == post_id
    assert publication["text"] == TEXT
    assert publication["published_at_source"] == "studio"
    # Nothing has read the figures yet, so they are unset, not zero.
    for column in ("impressions", "reactions", "comments", "reposts"):
        assert publication[column] is None, column


def test_publishing_arms_the_fingerprint_that_binds_the_post_later(published):
    post_id, answer = published
    row = _one("SELECT content_fingerprint FROM posts WHERE id = ?", (post_id,))
    assert row["content_fingerprint"] == post_identity.content_fingerprint(TEXT)
    assert answer["content_fingerprint"] == row["content_fingerprint"]


def test_publishing_creates_the_engagement_row_the_posts_screen_reads(published):
    post_id, answer = published
    row = _one("SELECT * FROM post_engagement WHERE post_urn = ?", (answer["publication_urn"],))
    assert row is not None, "the Posts screen has nowhere to read this post's summary"
    assert row["people"] == 0 and row["commenters"] == 0


def test_publishing_puts_the_post_in_the_search_index(published):
    post_id, answer = published
    assert _one("SELECT 1 FROM search_docs WHERE kind = 'post' AND ref = ?", (post_id,)) is not None
    assert _one("SELECT 1 FROM search_docs WHERE kind = 'own_post' AND ref = ?",
                (answer["publication_urn"],)) is not None


def test_the_summary_surfaces_name_a_studio_published_post(published):
    post_id, answer = published
    posts = client.get("/api/v1/insights/posts").json()
    urns = [p["activity_urn"] for p in posts.get("posts", [])]
    assert answer["publication_urn"] in urns, "Insights cannot see a post published from the studio"

    mine = [p for p in posts["posts"] if p["activity_urn"] == answer["publication_urn"]][0]
    # A local key is not a LinkedIn address, and nothing invented goes on screen.
    assert mine["url"] is None, mine["url"]


def test_a_post_published_here_is_not_published_twice_when_linkedin_hands_it_back(published, confirmed_creator):
    """
    The post comes back from the extension under LinkedIn's own id. That is
    the same post, so it keeps one publication record, with the real URN.
    """
    post_id, answer = published
    urn = f"urn:li:activity:739000000000000{uuid.uuid4().int % 1000:03d}"

    bound = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": urn, "post_text": TEXT, "post_author": confirmed_creator,
    }).json()
    assert bound["status"] == "bound" and bound["post_id"] == post_id, bound

    conn = get_db()
    try:
        publications = [r[0] for r in conn.execute(
            "SELECT activity_urn FROM own_posts WHERE post_id = ?", (post_id,))]
        local_left = conn.execute(
            "SELECT 1 FROM own_posts WHERE activity_urn = ?", (post_identity.local_urn(post_id),)).fetchone()
        engagement_rows = [r[0] for r in conn.execute(
            "SELECT post_urn FROM post_engagement WHERE post_urn IN (?, ?)",
            (urn, post_identity.local_urn(post_id)))]
    finally:
        conn.close()

    assert publications == [urn], publications
    assert local_left is None, "the local publication outlived the real one"
    assert post_identity.local_urn(post_id) not in engagement_rows

    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM own_posts WHERE activity_urn = ?", (urn,))
            conn.execute("DELETE FROM post_engagement WHERE post_urn = ?", (urn,))
    finally:
        conn.close()


def test_publishing_a_post_that_does_not_exist_is_refused():
    assert client.post("/api/posts/post-nope-t1/publish-now").status_code == 404
