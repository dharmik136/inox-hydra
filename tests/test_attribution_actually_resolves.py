"""
Attribution: does the chain the commit message describes actually close?
=======================================================================

Commit 9553e39 ("bind a post to the LinkedIn activity it became") says three
attribution surfaces "have returned zero for their entire existence" and that
"the chain now has all three links". It added posts.activity_urn and fixed one
surface. The other two kept joining posts.id against lead_interactions.post_urn,
which are different namespaces, so they went on returning zero and the commit
message was not true of them.

These tests walk the real chain end to end rather than asserting a query shape:
publish a post, bind it to an activity URN the way the extension does, ingest
an engagement against that URN, then ask each surface who engaged. A surface
that returns zero here is a surface where the feature does not exist.
"""

import os
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
from database import get_db
from crm import reverse_crm

client = TestClient(app)

ACTIVITY_URN = "urn:li:activity:9000000000000000001"


@pytest.fixture
def published_post_with_engager():
    """
    The state the product exists to produce: a published post bound to its
    LinkedIn activity, and a real person who commented on it.

    The engagement is created through the ingest endpoint the extension calls
    rather than by raw INSERT, so the ids and the foreign key relationship are
    exactly what the running product makes. leads.id is a TEXT primary key and
    lead_interactions.lead_id is INTEGER, so hand written fixtures do not
    reproduce what the application actually stores.
    """
    post_id = f"post-attr-{uuid.uuid4().hex[:8]}"
    profile = f"https://www.linkedin.com/in/attrtest-{uuid.uuid4().hex[:8]}"

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO posts (id, content, status, impressions, reactions, comments, shares, activity_urn) "
            "VALUES (?, ?, 'published', 500, 20, 5, 2, ?)",
            (post_id, "[ATTRTEST] A post that earned a comment.", ACTIVITY_URN),
        )
        conn.commit()
    finally:
        conn.close()

    res = client.post("/api/v1/crm/interactions/ingest", json={
        "full_name": "[ATTRTEST] Priya Raman",
        "linkedin_urn": profile,
        "profile_url": profile,
        "headline": "VP Platform Engineering",
        "company": "Northwind",
        "interaction_type": "COMMENT",
        "comment_text": "This matches our incident review exactly.",
        "post_urn": ACTIVITY_URN,
    })
    assert res.status_code == 200, f"the ingest path itself failed: {res.text}"

    yield post_id, profile

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM lead_interactions WHERE post_urn = ?", (ACTIVITY_URN,))
        cur.execute("DELETE FROM leads WHERE profile_url = ? OR linkedin_urn = ?", (profile, profile))
        cur.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
    finally:
        conn.close()


def _engager_names(leads):
    return " ".join(str(l.get("name") or l.get("full_name") or "") for l in leads)


def test_the_crm_surface_finds_the_engager(published_post_with_engager):
    """
    Surface one. Called with posts.id, which is what every caller holds,
    because that is what the analytics table renders into data-post-id.
    """
    post_id, _profile = published_post_with_engager
    result = reverse_crm.get_post_attribution(post_id)

    assert "Priya Raman" in _engager_names(result.get("leads", [])), (
        "A commenter captured against this post's activity URN did not appear "
        "when the post was looked up by its own id. The chain is still broken."
    )


def test_the_analytics_endpoint_finds_the_engager(published_post_with_engager):
    """Surface two, the route the attribution modal calls."""
    post_id, _profile = published_post_with_engager
    res = client.get(f"/api/v1/analytics/posts/{post_id}/leads")
    assert res.status_code == 200

    assert "Priya Raman" in _engager_names(res.json().get("leads", [])), (
        f"the attribution endpoint returned no engagers for {post_id}"
    )


def test_the_leaderboard_badge_counts_the_engager(published_post_with_engager):
    """
    Surface three. This is the one that renders a number next to every post,
    so a wrong answer here is visible on the main analytics screen.
    """
    post_id, _profile = published_post_with_engager
    res = client.get("/api/analytics/posts")
    assert res.status_code == 200

    rows = [p for p in res.json().get("posts", []) if p["id"] == post_id]
    assert rows, "the published post is missing from the leaderboard"
    assert rows[0]["attribution"]["total_leads"] >= 1, (
        "the leaderboard badge reports zero attributed leads for a post that "
        "has one. This is the number a creator sees on the analytics screen."
    )


def test_lookup_by_urn_also_resolves(published_post_with_engager):
    """A caller holding the URN rather than the id gets the same answer."""
    _post_id, _profile = published_post_with_engager
    result = reverse_crm.get_post_attribution(ACTIVITY_URN)
    assert "Priya Raman" in _engager_names(result.get("leads", []))


def test_an_unrelated_post_attributes_nothing(published_post_with_engager):
    """
    The join must not be so loose that it attributes everything to everything.
    A post with no bound URN has no engagers.
    """
    conn = get_db()
    other = f"post-attr-none-{uuid.uuid4().hex[:8]}"
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO posts (id, content, status, activity_urn) VALUES (?, ?, 'published', NULL)",
            (other, "[ATTRTEST] An unbound post."),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        result = reverse_crm.get_post_attribution(other)
        assert not result.get("leads"), (
            "an unbound post claimed attributed leads, so the match is too loose"
        )
    finally:
        conn = get_db()
        try:
            conn.execute("DELETE FROM posts WHERE id = ?", (other,))
            conn.commit()
        finally:
            conn.close()
