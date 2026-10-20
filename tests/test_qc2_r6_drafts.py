"""
Drafts: delete only a draft, and say so when there is nothing to delete.
========================================================================

FRONTEND D-1 needs a delete control in the drafts list, the Composer's first
destructive control. The route behind it (BE-18) answered 200 "Post deleted"
for an id that did not exist, and removed published and LinkedIn-held posts
without a check. The drafts list deletes drafts, so the route refuses
what has gone out (published, sent, or held by LinkedIn's scheduler) and
answers 404 for nothing.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app)


@pytest.fixture
def posts():
    conn = get_db()
    conn.executemany(
        "INSERT OR REPLACE INTO posts (id, content, status) VALUES (?, ?, ?)",
        [("qc2r6-d1", "QC2 R6 a draft to delete about zanzibarquill", "draft"),
         ("qc2r6-p1", "QC2 R6 a published post", "published"),
         ("qc2r6-q1", "QC2 R6 a queued post", "scheduled"),
         ("qc2r6-h1", "QC2 R6 a post LinkedIn holds", "scheduled")],
    )
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('linkedin_holds:qc2r6-h1', 'urn:li:share:1')")
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM posts WHERE id LIKE 'qc2r6-%'")
    conn.execute("DELETE FROM settings WHERE key = 'linkedin_holds:qc2r6-h1'")
    conn.commit()
    conn.close()


def _ids():
    conn = get_db()
    try:
        return {r["id"] for r in conn.execute("SELECT id FROM posts WHERE id LIKE 'qc2r6-%'")}
    finally:
        conn.close()


def test_a_draft_is_deleted(posts):
    response = client.delete("/api/posts/qc2r6-d1")
    assert response.status_code == 200
    assert "qc2r6-d1" not in _ids()


def test_nothing_to_delete_is_a_404_not_a_success(posts):
    assert client.delete("/api/posts/qc2r6-absent").status_code == 404


@pytest.mark.parametrize("post_id", ["qc2r6-p1", "qc2r6-h1"])
def test_a_post_that_has_gone_out_is_kept(posts, post_id):
    response = client.delete(f"/api/posts/{post_id}")
    assert response.status_code == 409
    assert "not a draft" in response.json()["detail"]
    assert post_id in _ids()


def test_a_queued_post_that_has_not_gone_out_can_still_be_deleted(posts):
    assert client.delete("/api/posts/qc2r6-q1").status_code == 200
    assert "qc2r6-q1" not in _ids()


def test_search_finds_a_draft_by_a_word_in_it(posts):
    results = client.get("/api/v1/search?q=zanzibarquill").json()
    found = [r for r in results["groups"]["posts"] if r.get("id") == "qc2r6-d1"]
    assert found and found[0]["opens"] == "composer"
