"""
Analytics hands the post table to Posts.
========================================

Analytics drew a five-column, fourteen-row "Post comparison" over the posts
the Posts screen tables in full, reading a different join for the same rows,
while its own comment called it "a summary, not a second copy of the Posts
table" (cycle 4, track 3, batch 1). The table, its pager and its per-row
attribution are gone from Analytics; the aside still names the posts the
engine ranks best and weakest, read on their own from /api/analytics/best
rather than beside a page of rows, and links into Posts.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "AnalyticsSurface.tsx")
API = os.path.join(REPO_ROOT, "studio", "ui", "src", "lib", "api.ts")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t3_analytics_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        for n in range(6):
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, reactions, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, '2026-08-01T09:00:00+00:00', ?, '2026-10-01', '2026-10-01')",
                         (f"urn:li:activity:738000000000000{n:04d}", f"Post {n}.", 10 + n * 7))
    conn.close()
    import app as app_module
    from fastapi.testclient import TestClient
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def test_the_aside_reads_the_engines_answer_on_its_own(studio):
    import results
    from database import get_db
    answer = studio.get("/api/analytics/best")
    assert answer.status_code == 200, answer.text
    conn = get_db()
    try:
        expected = results.best(conn, limit=2)
    finally:
        conn.close()
    assert answer.json()["best"] == expected
    assert answer.json()["best"]["best"], "six settled posts name no best post"
    # The same answer the post table's route carried beside its rows.
    assert studio.get("/api/analytics/posts?limit=1").json()["best"] == expected


def test_analytics_keeps_no_table_and_no_reader_for_one():
    surface = _read(SURFACE)
    for gone in ("ANALYTICS_PAGE_SIZE", "<table", "PostTable", "Next posts", "fetchAnalyticsPosts",
                 "fetchPostAttribution"):
        assert gone not in surface, f"Analytics still carries {gone!r}"
    assert "fetchAnalyticsBest" in surface and 'href="#/posts"' in surface
    api = _read(API)
    assert "fetchAnalyticsPosts" not in api and "fetchPostAttribution" not in api, (
        "the interface still has readers for a table no screen draws"
    )


def test_a_posts_people_kept_only_as_counts_reach_its_detail(studio):
    """
    The drawer under Analytics' table said how many of a post's people the
    retention job had folded into counts. The table moved to Posts, so the
    engagers route the Posts detail reads carries the count instead.
    """
    from database import get_db
    urn = "urn:li:activity:7380000000000000003"
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, activity_urn) VALUES ('post-folded', 'Post 3.', 'published', ?)",
                     (urn,))
        conn.execute("INSERT INTO reaction_folds (post_urn, reactions, people, vip, qualified, icp_known, icp_sum, "
                     "conversations, folded_through, updated_at) VALUES (?, 9, 7, 0, 0, 0, 0, 0, '2024-01-01', '2026-10-01')",
                     (urn,))
    conn.close()
    answer = studio.get("/api/v1/posts/post-folded/engagers")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["engagers"] == [], "nobody engaged in the live rows"
    assert body["folded"] == {"people": 7, "reactions": 9}, body
