"""
A post marked published here and not yet seen on LinkedIn is on Posts.
=====================================================================

Review round 2, B2 (b). Analytics' post table listed the creator's LinkedIn
posts and, beside them, any post marked published in the studio that no
LinkedIn post had been matched to yet. Posts lists publications (own_posts),
and such a post has none: a post sent to LinkedIn is marked published by the
scheduler at its time, and the bridge records it only once it reads it on
LinkedIn. When the table moved to Posts, these posts went onto no list.

They are back, as a short group of their own on Posts, with the sentence
that says why they have no figures. A post published through the studio's
own I posted it has a publication record from that moment, so it is in the
table itself and not in the group.
"""

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

POSTS = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PostsSurface.tsx")
GROUP = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PublishedNotYetSeen.tsx")


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_unseen_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    yield TestClient(app_module.app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    shutil.rmtree(home, ignore_errors=True)


def _post(post_id, content, status):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, published_at) VALUES (?, ?, ?, ?)",
                     (post_id, content, status, datetime.now(timezone.utc).isoformat() if status == "published" else None))
    conn.close()


def _unseen(client):
    answer = client.get("/api/v1/posts/published-not-seen")
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_post_marked_published_with_no_publication_is_listed(studio):
    """The reviewer's case, and the scheduler's for a post sent to LinkedIn."""
    _post("studio-pub-1", "Marked posted in the studio.\n\nBody.", "published")
    body = _unseen(studio)
    assert [post["id"] for post in body["posts"]] == ["studio-pub-1"], body
    assert body["posts"][0]["excerpt"].startswith("Marked posted in the studio.")
    assert body["posts"][0]["published_at"]
    insights = studio.get("/api/v1/insights/posts").json()
    assert not any(row["activity_urn"] == "studio-pub-1" for row in insights["posts"]), "it is on Posts' table too"


def test_a_post_published_with_i_posted_it_is_in_the_table_and_not_the_group(studio):
    _post("studio-pub-2", "Posted with I posted it.\n\nBody.", "scheduled")
    answer = studio.post("/api/posts/studio-pub-2/publish-now")
    assert answer.status_code == 200, answer.text
    assert _unseen(studio)["posts"] == [], "a post with its publication record is listed twice"
    insights = studio.get("/api/v1/insights/posts").json()
    assert any("Posted with I posted it." in (row.get("excerpt") or "") for row in insights["posts"]), (
        "the published post is on neither list")


def test_drafts_and_queued_posts_are_not_listed(studio):
    _post("draft-1", "A draft.", "draft")
    _post("queued-1", "A queued post.", "scheduled")
    assert _unseen(studio)["posts"] == []


def test_posts_draws_the_group_with_its_sentence_even_when_nothing_is_imported():
    surface = open(POSTS, encoding="utf-8").read()
    assert surface.count("<PublishedNotYetSeen") == 2, "the group is not drawn under both the table and the empty state"
    group = " ".join(open(GROUP, encoding="utf-8").read().split())
    assert "/api/v1/posts/published-not-seen" not in group and "fetchPublishedNotSeen" in group
    assert "not yet seen on LinkedIn" in group
    assert re.search(r"no figures and no people", group), "the group does not say why it has no figures"
