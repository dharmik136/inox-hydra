"""
A post's people are listed whether or not the studio holds a row for it.
=======================================================================

Review round 2, B2 (a). A post first captured after migration 26 has no
`posts` row: the migration gave one to every publication it found, and the
own-posts ingest binds a capture only to a studio record that already
matches it. post_identity.resolve needs that row, so the engagers route
answered 404 for every such post, and Posts' detail said "nobody captured"
beside a row that counted the post's people. The Analytics drawer, which
read the people by URN, was the one way to them, and track 3 removed it.

Track 1 heals the missing rows in its migration. This is the defence in
depth in this track's own route: when no studio row resolves, the people
filed under the post's URN are listed, as the attribution route always did.
An identifier no publication carries still answers 404.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

ME = "t3-engagers-creator"


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_engagers_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import app as app_module
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    client = TestClient(app_module.app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    assert client.post("/api/v1/bridge/heartbeat", json={"extension_version": "2.7.0", "page_kind": "feed"}).status_code == 200
    assert client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                         "display_name": "T3", "headline": "H", "location": "L",
                                                         "current_company": "C", "follower_count": 1}).status_code == 200
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200
    yield client
    shutil.rmtree(home, ignore_errors=True)


def _captured_post(client, days_ago=9, salt=1):
    when = datetime.now(timezone.utc) - timedelta(days=days_ago)
    urn = "urn:li:activity:" + str((int(when.timestamp() * 1000) << 22) + salt)
    answer = client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": "A post.\n\nBody.", "reactions": 12, "comments": 1, "reposts": 0}]})
    assert answer.status_code == 200, answer.text
    return urn


def test_a_post_with_no_studio_row_lists_its_people(studio):
    from database import get_db
    urn = _captured_post(studio)
    engaged = studio.post("/api/v1/crm/interactions/ingest", json={
        "full_name": "Ana Example", "profile_url": "https://www.linkedin.com/in/ana-example-x",
        "headline": "Head of Platform", "company": "Example", "interaction_type": "COMMENT",
        "comment_text": "Good point?", "post_urn": urn, "post_author": ME})
    assert engaged.status_code == 200, engaged.text
    # Every path now gives a publication its post (track 1's fix, one rule in
    # post_identity), so the state this route defends against exists only in
    # a database from before that fix, and is made here directly.
    conn = get_db()
    with conn:
        conn.execute("UPDATE own_posts SET post_id = NULL WHERE activity_urn = ?", (urn,))
        conn.execute("DELETE FROM posts WHERE activity_urn = ?", (urn,))
    try:
        rows = conn.execute("SELECT COUNT(*) FROM posts WHERE activity_urn = ?", (urn,)).fetchone()[0]
    finally:
        conn.close()
    assert rows == 0, "the fixture no longer reproduces a post with no studio row"
    answer = studio.get(f"/api/v1/posts/{urn}/engagers")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert [person["full_name"] for person in body["engagers"]] == ["Ana Example"], body
    assert body["activity_urn"] == urn


def test_its_folded_people_reach_the_detail_too(studio):
    from database import get_db
    urn = _captured_post(studio, salt=2)
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO reaction_folds (post_urn, reactions, people, vip, qualified, icp_known, icp_sum, "
                     "conversations, folded_through, updated_at) VALUES (?, 5, 4, 0, 0, 0, 0, 0, '2024-01-01', '2026-10-01')",
                     (urn,))
    conn.close()
    body = studio.get(f"/api/v1/posts/{urn}/engagers").json()
    assert body["folded"] == {"people": 4, "reactions": 5}, body


def test_a_post_no_publication_carries_is_still_not_found(studio):
    answer = studio.get("/api/v1/posts/urn:li:activity:7111111111111111111/engagers")
    assert answer.status_code == 404, answer.text
