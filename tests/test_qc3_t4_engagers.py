"""
One post's engagers, read by index, in the order they always came out.
======================================================================

Cycle 3, batch T4 (P-4). GET /api/v1/posts/{id}/engagers joined
`leads l ON l.id = i.lead_id`, the join post_summary.py documents as the one
that cannot work: lead_interactions.lead_id is declared INTEGER and leads.id
is TEXT, so numeric affinity is applied and the leads primary key cannot
serve the comparison. Measured on three years (49,142 leads, 500,000
interactions) the route scanned every lead for one post: 7.66 ms against
0.12 ms for the same rows read through idx_interactions_post.

The rows and their order must not move, so the answer is compared with the
answer the old join gave, row for row, on a history built to have ties: many
leads share a score, several share a name, and one person engages a post more
than once.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402

# The route as it stood before this fix: the join that scans every lead.
OLD_ENGAGERS_SQL = """
    SELECT l.id, l.full_name, l.name, l.headline, l.company,
           l.seniority_level, l.icp_score, l.profile_url,
           i.interaction_type, i.comment_text, i.interacted_at
    FROM lead_interactions i
    JOIN leads l ON l.id = i.lead_id
    WHERE i.post_urn = ?
    ORDER BY l.icp_score DESC
"""


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t4_eng_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _plan(conn, sql, params):
    return " | ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def _busiest(conn):
    """The studio post whose URN holds the most interactions, which is what the route is asked for."""
    return conn.execute(
        "SELECT p.id, p.activity_urn, COUNT(*) AS n FROM posts p "
        "JOIN lead_interactions i ON i.post_urn = p.activity_urn "
        "GROUP BY p.id ORDER BY n DESC, p.id LIMIT 1").fetchone()


def test_a_post_s_engagers_are_read_by_index_and_not_by_scanning_every_lead(home, monkeypatch):
    from database import get_db
    from routers import posts as posts_router
    conn = get_db()
    try:
        post = _busiest(conn)
        assert post["n"] > 10, "the history has a busy post"
        # The route opens its own connection, so the statements are read from
        # the one it is handed.
        seen = []

        def traced():
            opened = get_db()
            opened.set_trace_callback(seen.append)
            return opened

        monkeypatch.setattr(posts_router, "get_db", traced)
        answer = posts_router.get_post_engagers(post["id"])
        assert answer["count"] == post["n"]

        query = next(s for s in seen if "l.profile_url" in s and "lead_interactions" in s)
        plan = _plan(conn, query, ())
        assert "idx_interactions_post" in plan, plan
        assert "SCAN l" not in plan, f"one post's engagers scans every lead: {plan}"
    finally:
        conn.close()


def test_the_same_engagers_come_out_in_the_same_order(home):
    from database import get_db
    from routers import posts as posts_router
    conn = get_db()
    try:
        post = _busiest(conn)
        before = [tuple(r) for r in conn.execute(OLD_ENGAGERS_SQL, (post["activity_urn"],))]
        after = [tuple(r.values()) for r in
                 (dict(row) for row in [row for row in posts_router.get_post_engagers(post["id"])["engagers"]])]
        assert after == before
        assert len({r[6] for r in before}) > 3, "the history has engagers on both sides of several scores"
    finally:
        conn.close()
