"""
Asking for the newest draft answers the same post however you ask.
==================================================================

This batch gave /api/posts an optional limit, so the interface could stop
reading all 259 KB of drafts to reopen one of them. The limited read took the
newest rows with ORDER BY ... DESC and the unlimited read listed them ASC,
and neither broke a tie, so on an install whose 150 drafts were migrated in
one go and share a created_at, SQLite was free to order the tied rows as it
liked: the Composer reopened a 1,644 character draft where it used to reopen
a 788 character one. Found while re-measuring for the review, not by the
tests, because both answers are "a newest draft".

The id breaks the tie in both directions now, so the two reads agree and the
answer is the same post every time it is asked for.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402
from database import get_db  # noqa: E402

client = TestClient(app_module.app, base_url="http://127.0.0.1")

PREFIX = "post_qc3_t5_tie_"
# One timestamp for all of them, which is what a migration that moved every
# draft in one transaction leaves behind.
SAME_MOMENT = "2026-03-01 09:00:00"


@pytest.fixture
def tied_drafts():
    conn = get_db()
    try:
        with conn:
            for index in range(8):
                conn.execute(
                    "INSERT INTO posts (id, content, status, created_at) VALUES (?, ?, 'draft', ?)",
                    (f"{PREFIX}{index}", f"Draft number {index}, tied with the rest.", SAME_MOMENT),
                )
    finally:
        conn.close()
    yield
    conn = get_db()
    try:
        with conn:
            conn.execute(f"DELETE FROM posts WHERE id LIKE '{PREFIX}%'")
    finally:
        conn.close()


def _ours(posts):
    return [post for post in posts if post["id"].startswith(PREFIX)]


def test_the_whole_list_and_the_limited_read_name_the_same_newest_draft(tied_drafts):
    whole = client.get("/api/posts?status=draft").json()["posts"]
    one = client.get("/api/posts?status=draft&limit=1").json()["posts"]
    assert len(one) == 1, one
    # fetchLatestDraft reads the last row of whatever it is given.
    assert whole[-1]["id"] == one[-1]["id"], (
        "the newest draft depends on how many were asked for: "
        f"{whole[-1]['id']} unlimited against {one[-1]['id']} limited"
    )


def test_a_limited_read_is_the_tail_of_the_whole_list(tied_drafts):
    whole = client.get("/api/posts?status=draft").json()["posts"]
    few = client.get("/api/posts?status=draft&limit=5").json()["posts"]
    assert [post["id"] for post in few] == [post["id"] for post in whole[-5:]]


def test_the_order_is_the_same_on_every_read(tied_drafts):
    first = [post["id"] for post in _ours(client.get("/api/posts?status=draft").json()["posts"])]
    for _ in range(3):
        again = [post["id"] for post in _ours(client.get("/api/posts?status=draft").json()["posts"])]
        assert again == first, "tied drafts come back in a different order each time"
    assert len(first) == 8
