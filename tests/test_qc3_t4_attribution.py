"""
Per post lead attribution: the shape, and the statistics the index needs.
=========================================================================

Cycle 3, batch T4, and DERIVED.md section 4. Written the obvious way, one
correlated subquery per post over an unindexed post_urn, attributing people to
ten posts of a three year history cost 334 seconds. Three things make that
number, and this module holds all three:

1. The shape. The studio filters to the posts it is answering for and groups
   once, and it joins leads through post_summary.LEAD_JOIN, the one join that
   can use an index on this schema. Measured on the three year dataset (1,417
   posts, 500,000 interactions, 49,142 leads), ten posts: 4.8 ms for that
   shape, 141.7 ms for the same query with the join written l.id = i.lead_id,
   and 10,031 ms for that join when the statistics are gone. The shape the
   studio runs is the only one of the three that does not depend on the
   planner's statistics at all.
2. The index. idx_interactions_post is what makes 4.8 ms possible.
3. The statistics. An index with no statistics is a 35 fold regression for the
   other shapes, so the index and the ANALYZE must never be separable: they
   are one migration, and this holds them there.
"""

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t4_attr_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _plan(conn, sql, params=()):
    return " | ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


# ---------------------------------------------------------------------------
# The index and the statistics, in one migration
# ---------------------------------------------------------------------------

def test_the_index_on_post_urn_and_its_analyze_are_one_migration():
    import migrations
    payloads = {version: payload for version, _description, payload in migrations.MIGRATIONS}
    holding = [version for version, payload in payloads.items()
               if isinstance(payload, tuple)
               and any("idx_interactions_post" in str(statement) for statement in payload)]
    assert holding, "no migration creates idx_interactions_post"
    for version in holding:
        statements = [str(s).strip().upper() for s in payloads[version]]
        assert any(s.startswith("ANALYZE") for s in statements), (
            f"migration {version} adds idx_interactions_post without the ANALYZE it needs: "
            "an index with no statistics made the same attribution 35 times slower")


def _interaction_statistics():
    from database import get_db
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'").fetchone()[0] == 1, (
            "the migration run left the planner with no statistics at all")
        return dict(conn.execute("SELECT idx, stat FROM sqlite_stat1 WHERE tbl = 'lead_interactions'").fetchall())
    finally:
        conn.close()


def test_the_planner_gets_statistics_for_the_interactions_once_there_are_any(home):
    """
    A fresh install runs the migrations on empty tables, so ANALYZE has
    nothing to measure and writes no row for lead_interactions; the history
    arrives afterwards, from the bridge or the archive. The refresh
    (database.optimize_db, after each migration run and hourly while the
    studio is open) is what gives the planner the index it will be reading by.
    """
    from database import optimize_db
    optimize_db()
    rows = _interaction_statistics()
    assert "idx_interactions_post" in rows, rows
    assert int(rows["idx_interactions_post"].split()[0]) > 0, rows


# ---------------------------------------------------------------------------
# The shape
# ---------------------------------------------------------------------------

def test_attribution_for_the_posts_asked_for_is_read_by_index(home):
    import post_summary
    from database import get_db
    conn = get_db()
    try:
        seen = []
        conn.set_trace_callback(seen.append)
        post_summary.compute(conn, home["own"][:10])
        conn.set_trace_callback(None)
        people = next(s for s in seen if "MAX(i.interaction_type" in s)
        plan = _plan(conn, people)
        assert "idx_interactions_post" in plan, plan
        assert "SCAN l" not in plan, f"attribution scans every lead: {plan}"
        assert "SCAN i" not in plan, f"attribution scans every interaction: {plan}"
    finally:
        conn.close()


def test_the_rollup_over_every_post_is_one_pass_not_one_query_per_post(home):
    """With no posts named it is the grouped rewrite: one pass, 347 ms on three years."""
    import post_summary
    from database import get_db
    conn = get_db()
    try:
        seen = []
        conn.set_trace_callback(seen.append)
        rows = post_summary.compute(conn)
        conn.set_trace_callback(None)
        assert len(rows) > 10
        people = [s for s in seen if "MAX(i.interaction_type" in s]
        assert len(people) == 1, f"the roll-up ran {len(people)} per-post queries"
    finally:
        conn.close()


# The obvious way to attribute people to posts, which costs 334 seconds on
# three years: one correlated subquery per post, over post_urn.
CORRELATED = """
    SELECT o.activity_urn,
           (SELECT COUNT(DISTINCT i.lead_id) FROM lead_interactions i
             WHERE i.post_urn = o.activity_urn) AS people,
           (SELECT COUNT(DISTINCT i.lead_id) FROM lead_interactions i
             JOIN leads l ON l.id = CAST(i.lead_id AS TEXT)
             WHERE i.post_urn = o.activity_urn AND l.icp_score >= ?) AS vip
    FROM own_posts o WHERE o.activity_urn IN (SELECT value FROM json_each(?))
"""


def test_the_studio_counts_the_same_people_the_obvious_shape_counts(home):
    """The fast shape is a rewrite, not a different answer."""
    import json
    import post_summary
    from database import get_db
    conn = get_db()
    try:
        asked = home["own"][:10]
        fast = post_summary.compute(conn, asked)
        obvious = {r["activity_urn"]: (r["people"], r["vip"]) for r in conn.execute(
            CORRELATED, (post_summary.VIP_SCORE, json.dumps(asked)))}
        assert len(obvious) == len(asked)
        for urn, (people, vip) in obvious.items():
            row = fast.get(urn)
            assert (row["people"] if row else 0) == people, urn
            assert (row["vip"] if row else 0) == vip, urn
        assert sum(people for people, _vip in obvious.values()) > 0, "the posts asked for brought people"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# At volume
# ---------------------------------------------------------------------------

def _volume(conn, posts=2000, leads=4000):
    """Enough posts and people that a query per post would be visible."""
    with conn:
        for i in range(posts):
            urn = f"urn:li:activity:{7000000000000000000 + i * 1000}"
            conn.execute(
                "INSERT OR IGNORE INTO own_posts (activity_urn, text, published_at, published_at_source, reactions, "
                "comments, reposts, impressions, first_seen_at, last_seen_at) "
                "VALUES (?, ?, ?, 'activity', ?, ?, 0, ?, '2026-01-01', '2026-01-01')",
                (urn, f"Volume post {i} " + "word " * 40,
                 f"2026-01-{(i % 28) + 1:02d}T09:00:00+00:00", i % 90, i % 9, i % 900))
        for i in range(leads):
            conn.execute("INSERT OR IGNORE INTO leads (id, name, full_name, icp_score) VALUES (?, ?, ?, ?)",
                         (f"vol-lead-{i:05d}", f"Person {i}", f"Person {i}", float(i % 100)))
            for j in range(3):
                conn.execute(
                    "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_key) "
                    "VALUES (?, ?, ?, ?)",
                    (f"vol-lead-{i:05d}", f"urn:li:activity:{7000000000000000000 + ((i * 7 + j) % posts) * 1000}",
                     "COMMENT" if j else "LIKE", f"k{i}{j}"))


def test_one_page_of_posts_with_their_people_answers_fast_at_volume(home):
    import time
    import insights
    from database import get_db
    conn = get_db()
    try:
        _volume(conn)
    finally:
        conn.close()
    started = time.perf_counter()
    answer = insights.posts_overview()
    elapsed = (time.perf_counter() - started) * 1000
    assert answer["total"] > 2000
    assert answer["returned"] == insights.POSTS_PAGE
    # Measured at 132 ms on the three year dataset; the bound is loose on
    # purpose so a slow CI machine does not fail it.
    assert elapsed < 1500, f"one page of posts took {elapsed:.0f} ms at {answer['total']} posts"
    assert any(post["people_count"] for post in answer["posts"]), "the page carries who engaged"
