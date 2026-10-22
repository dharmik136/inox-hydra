"""
One identity for a post, and one function that resolves it.
===========================================================

Four tables held "something the creator wrote" and they disagreed. The cost a
creator paid, measured on a three year install:

- 523 of 1,417 own_posts had no posts row, which stranded 182,115 of 500,061
  captured interactions. GET /api/v1/posts/{id}/engagers takes a studio id, so
  for those posts there was no id to ask with: the busiest post in the install
  answered 404 while Analytics showed it and its leads.
- Two binders decided "which studio row is this LinkedIn post", with
  different candidate sets and different tie breaks, so a post could bind one
  way and not the other.

These tests ask for one post by every identifier the product uses and expect
one answer, and they ask the engagers endpoint about a post the studio knows
only from LinkedIn.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import time
import uuid

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import post_identity
from app import app
from database import get_db

client = TestClient(app)

TEXT = ("The deploy that taught me to read our own dashboards before anyone else did, "
        "and what we changed the week after.")
URN = "urn:li:activity:7390000000000000777"
SHARE_URN = "urn:li:share:7390000000000000777"


@pytest.fixture
def rows():
    """Everything a test wrote, removed afterwards whatever it asserted."""
    made = {"posts": [], "own_posts": [], "leads": []}
    yield made
    conn = get_db()
    try:
        with conn:
            for post_id in made["posts"]:
                conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
            for urn in made["own_posts"]:
                conn.execute("DELETE FROM lead_interactions WHERE post_urn = ?", (urn,))
                conn.execute("DELETE FROM own_posts WHERE activity_urn = ?", (urn,))
                conn.execute("DELETE FROM post_engagement WHERE post_urn = ?", (urn,))
            for lead in made["leads"]:
                conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead,))
                conn.execute("DELETE FROM leads WHERE id = ?", (lead,))
    finally:
        conn.close()


def _imported_post(rows, urn=URN, text=TEXT):
    """
    A post the extension imported from LinkedIn and bound to its posts row,
    which is the state migration 26 leaves every publication in.
    """
    post_id = f"post-t1-{uuid.uuid4().hex[:8]}"
    rows["posts"].append(post_id)
    rows["own_posts"].append(urn)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO posts (id, content, status, activity_urn, content_fingerprint, published_at, source) "
                "VALUES (?, ?, 'published', ?, ?, '2026-09-01T09:00:00+00:00', 'linkedin')",
                (post_id, text, urn, post_identity.content_fingerprint(text)),
            )
            conn.execute(
                "INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                "first_seen_at, last_seen_at, post_id) "
                "VALUES (?, ?, '2026-09-01T09:00:00+00:00', 'urn_decode', '2026-09-02', '2026-09-02', ?)",
                (urn, text, post_id),
            )
    finally:
        conn.close()
    return post_id


def _engager(rows, urn, name="T1 Engager"):
    lead_id = f"lead-t1-{uuid.uuid4().hex[:8]}"
    rows["leads"].append(lead_id)
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO leads (id, name, full_name, headline, icp_score) VALUES (?, ?, ?, 'VP Platform', 72.0)",
                (lead_id, name, name),
            )
            # lead_id is declared INTEGER and holds the leads TEXT key, which
            # is why every join site casts. The capture writes it this way.
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at) "
                "VALUES (?, ?, 'COMMENT', '2026-09-02T10:00:00+00:00')",
                (lead_id, urn),
            )
    finally:
        conn.close()
    return lead_id


# ---------------------------------------------------------------------------
# One function resolves a post from any identifier
# ---------------------------------------------------------------------------

def test_every_identifier_the_product_uses_resolves_to_the_same_post(rows):
    post_id = _imported_post(rows)
    conn = get_db()
    try:
        asked = {
            "studio id": post_id,
            "activity urn": URN,
            "share urn": SHARE_URN,
            "ugcPost urn": URN.replace("activity", "ugcPost"),
            "permalink": f"https://www.linkedin.com/feed/update/{URN}/",
            "slug": "https://www.linkedin.com/posts/someone_slug-activity-7390000000000000777-AbCd",
            "bare id": "7390000000000000777",
            "fingerprint": post_identity.content_fingerprint(TEXT),
        }
        answers = {label: post_identity.resolve(conn, value) for label, value in asked.items()}
    finally:
        conn.close()

    for label, answer in answers.items():
        assert answer is not None, f"{label} resolved to nothing"
        assert answer["post_id"] == post_id, f"{label} resolved to {answer['post_id']}"
        assert answer["publication_urn"] == URN, label


def test_an_unknown_identifier_resolves_to_nothing():
    conn = get_db()
    try:
        for value in (None, "", "   ", "post-does-not-exist", "urn:li:activity:1", "banana"):
            assert post_identity.resolve(conn, value) is None, value
    finally:
        conn.close()


def test_two_posts_that_open_the_same_way_resolve_to_neither(rows):
    """A wrong answer credits one post's engagers to another."""
    fingerprint = post_identity.content_fingerprint(TEXT)
    conn = get_db()
    try:
        with conn:
            for _ in range(2):
                post_id = f"post-t1-{uuid.uuid4().hex[:8]}"
                rows["posts"].append(post_id)
                conn.execute(
                    "INSERT INTO posts (id, content, status, content_fingerprint) VALUES (?, ?, 'injected', ?)",
                    (post_id, TEXT, fingerprint),
                )
        assert post_identity.resolve(conn, fingerprint) is None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The engagers endpoint answers for every post
# ---------------------------------------------------------------------------

def test_the_engagers_of_a_post_the_studio_knows_only_from_linkedin(rows):
    """
    The S1: a post imported from LinkedIn had no studio id, so the endpoint
    that takes one answered 404 for 36% of the captured engagement.
    """
    post_id = _imported_post(rows)
    _engager(rows, URN)

    by_studio_id = client.get(f"/api/v1/posts/{post_id}/engagers").json()
    assert by_studio_id["status"] == "success", by_studio_id
    assert by_studio_id["count"] == 1, by_studio_id

    by_urn = client.get(f"/api/v1/posts/{URN}/engagers").json()
    assert by_urn["status"] == "success", by_urn
    assert by_urn["count"] == 1, by_urn
    assert by_urn["post_id"] == post_id


def test_the_engagers_of_a_post_captured_under_another_namespace(rows):
    """
    The archive names a post by its share id and the page names it by its
    activity id. The engagement is filed under whichever was captured.
    """
    post_id = _imported_post(rows, urn=SHARE_URN)
    rows["own_posts"].append(SHARE_URN)
    _engager(rows, SHARE_URN)

    answer = client.get(f"/api/v1/posts/{URN}/engagers").json()
    assert answer["status"] == "success", answer
    assert answer["count"] == 1, answer
    assert answer["post_id"] == post_id


def test_a_post_with_no_urn_says_so_rather_than_404(rows):
    post_id = f"post-t1-{uuid.uuid4().hex[:8]}"
    rows["posts"].append(post_id)
    conn = get_db()
    try:
        with conn:
            conn.execute("INSERT INTO posts (id, content, status) VALUES (?, ?, 'draft')", (post_id, TEXT))
    finally:
        conn.close()
    answer = client.get(f"/api/v1/posts/{post_id}/engagers").json()
    assert answer["status"] == "unbound", answer


def test_the_engagers_query_reads_the_interactions_index_not_every_lead():
    """
    lead_interactions.lead_id is declared INTEGER and leads.id is TEXT, so a
    join written l.id = i.lead_id applies numeric affinity to the leads
    primary key and scans every lead: 64x slower than the join
    post_summary documents, measured on the busiest post of a three year
    install. The plan is the assertion, because the timing of a small test
    database would not show it.
    """
    import post_summary

    conn = get_db()
    try:
        plan = "\n".join(str(tuple(r)) for r in conn.execute(
            f"EXPLAIN QUERY PLAN SELECT l.id FROM lead_interactions i {post_summary.LEAD_JOIN} "
            "WHERE i.post_urn IN (?)", (URN,)))
    finally:
        conn.close()
    assert "SCAN l" not in plan, plan
    assert "idx_interactions_post" in plan or "SEARCH i" in plan, plan


def test_the_engagers_endpoint_answers_quickly_on_its_own_dataset(rows):
    """
    The bar is under 100 ms on the three year dataset, which is measured in
    the report. Here the assertion is only that the route itself is not the
    slow part: a post with a hundred engagers answers well inside it.
    """
    post_id = _imported_post(rows)
    for n in range(100):
        _engager(rows, URN, name=f"T1 Engager {n}")

    started = time.perf_counter()
    answer = client.get(f"/api/v1/posts/{post_id}/engagers").json()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert answer["count"] == 100, answer
    assert elapsed_ms < 100.0, f"{elapsed_ms:.1f} ms"


# ---------------------------------------------------------------------------
# One binder
# ---------------------------------------------------------------------------

def test_the_permalink_route_and_the_history_import_bind_with_one_function():
    """
    Both callers go through post_identity.bind_activity_urn. A second
    implementation is how the two disagreed, so its absence is the assertion,
    the way tests/test_fold_is_one_number.py asserts one fold.
    """
    import inspect

    import onboarding
    from routers import posts as posts_router

    for module, name in ((posts_router, "bind_post_urn"), (onboarding, "_bind_to_studio")):
        source = inspect.getsource(getattr(module, name))
        assert "bind_activity_urn" in source, f"{name} does not use the one binder"
        assert "fingerprint_matches" not in source, f"{name} still matches posts itself"
        assert "UPDATE posts SET activity_urn" not in source, f"{name} still binds for itself"


def test_a_studio_post_binds_to_the_urn_the_creator_opened(rows, confirmed_creator):
    created = client.post("/api/posts", json={"content": TEXT, "status": "draft"}).json()
    rows["posts"].append(created["id"])
    client.post(f"/api/posts/{created['id']}/publish-now")
    rows["own_posts"].append(post_identity.local_urn(created["id"]))
    rows["own_posts"].append(URN)

    bound = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": URN, "post_text": TEXT, "post_author": confirmed_creator,
    }).json()
    assert bound["status"] == "bound", bound
    assert bound["post_id"] == created["id"]

    # And the publication it was recorded under at publish time is now that
    # post's one publication, under LinkedIn's own id.
    conn = get_db()
    try:
        publications = conn.execute(
            "SELECT activity_urn FROM own_posts WHERE post_id = ?", (created["id"],)).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in publications] == [URN], [r[0] for r in publications]


def test_a_post_on_someone_elses_page_is_not_claimed(rows, confirmed_creator):
    created = client.post("/api/posts", json={"content": TEXT, "status": "draft"}).json()
    rows["posts"].append(created["id"])
    client.post(f"/api/posts/{created['id']}/publish-now")
    rows["own_posts"].append(post_identity.local_urn(created["id"]))

    answer = client.post("/api/v1/posts/bind-urn", json={
        "activity_urn": URN, "post_text": TEXT, "post_author": "somebody-else",
    }).json()
    assert answer["status"] == "not_yours", answer
    assert answer["bound"] is False
