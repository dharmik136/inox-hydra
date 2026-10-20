"""
The hot reads use an index, and give the same answers.
======================================================

Cycle 2, batch R3 (DATA-02, DATA-04 workaround, DATA-08).

On three years of one prolific creator (500,000 interactions, 49,142 leads)
Today took 424 ms and one post's leads 386 ms, because both scanned every
lead: lead_interactions.lead_id is declared INTEGER while leads.id is TEXT,
so a join written l.id = i.lead_id could use no index from the interaction
side, and Today's window and one post's engagers had no index at all. Nothing
had ever run ANALYZE either.

Migration 20 adds the two indexes and the statistics. These tests hold the
plans (an index search, never a scan of leads) and hold the answers to what
the old queries returned, ties included, on a history built to have ties.
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
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_idx_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _traced(conn):
    seen = []
    conn.set_trace_callback(seen.append)
    return seen


def _plan(conn, sql, params):
    return " | ".join(row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def test_migration_20_adds_the_indexes_and_statistics(home):
    from database import get_db
    conn = get_db()
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"idx_interactions_post", "idx_interactions_engaged"} <= names
        assert conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 'sqlite_stat1'").fetchone()[0] == 1
    finally:
        conn.close()


def test_migration_20_is_idempotent():
    import migrations
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE lead_interactions (id INTEGER PRIMARY KEY, lead_id INTEGER, post_urn TEXT, "
                 "first_seen_at TEXT, interacted_at TEXT)")
    payload = dict((v, p) for v, _d, p in migrations.MIGRATIONS)[20]
    for _ in range(2):
        for statement in payload:
            conn.execute(statement)


# ---------------------------------------------------------------------------
# Today: people to reply to
# ---------------------------------------------------------------------------

OLD_REPLY_SQL = """
    SELECT i.lead_id, i.post_urn, i.comment_text, i.interaction_type,
           COALESCE(i.first_seen_at, i.interacted_at) AS engaged_at,
           COALESCE(i.last_seen_at, i.interacted_at) AS seen_at,
           COALESCE(l.full_name, l.name) AS name, l.headline, l.lead_status
    FROM lead_interactions i JOIN leads l ON l.id = i.lead_id
    WHERE COALESCE(i.first_seen_at, i.interacted_at) >= ?
"""


def _old_reply_to(conn):
    """today._reply_to as it stood before R3, on a schema without the new indexes."""
    import onboarding
    import today
    from datetime import datetime, timezone
    own_ids = onboarding._own_activity_ids(conn)
    since = (datetime.now(timezone.utc) - today.REPLY_WINDOW).strftime("%Y-%m-%d %H:%M:%S")
    people = {}
    for row in conn.execute(OLD_REPLY_SQL, (since,)).fetchall():
        if onboarding._activity_id(row["post_urn"]) not in own_ids:
            continue
        if (row["lead_status"] or "").upper() in today.ANSWERED_STATUSES:
            continue
        person = people.setdefault(str(row["lead_id"]), {
            "lead_id": str(row["lead_id"]), "name": row["name"], "headline": row["headline"],
            "posts_engaged": set(), "engaged_at": None, "last_seen_at": None, "latest_comment": None,
            "commented": False})
        person["posts_engaged"].add(onboarding._activity_id(row["post_urn"]))
        person["last_seen_at"] = max(person["last_seen_at"] or "", row["seen_at"] or "") or None
        if row["interaction_type"] != "COMMENT":
            continue
        person["commented"] = True
        if (row["engaged_at"] or "") >= (person["engaged_at"] or ""):
            person["engaged_at"] = row["engaged_at"]
            if row["comment_text"]:
                person["latest_comment"] = row["comment_text"][:200]
    ranked = sorted((p for p in people.values() if p["commented"]),
                    key=lambda p: (len(p["posts_engaged"]), p["engaged_at"] or ""), reverse=True)[:today.REPLY_LIMIT]
    for person in ranked:
        person["posts_engaged"] = len(person["posts_engaged"])
    return ranked


def _without_new_indexes(conn):
    """The database as it was before migration 20, so the old query runs its old plan."""
    conn.execute("DROP INDEX IF EXISTS idx_interactions_post")
    conn.execute("DROP INDEX IF EXISTS idx_interactions_engaged")
    conn.execute("DROP TABLE IF EXISTS sqlite_stat1")
    conn.commit()


def test_today_reads_the_window_by_index_not_every_lead(home):
    import today
    from database import get_db
    conn = get_db()
    try:
        seen = _traced(conn)
        today._reply_to(conn)
        conn.set_trace_callback(None)
        query = next(s for s in seen if "first_seen_at, i.interacted_at) >=" in s)
        plan = _plan(conn, query, ())
        assert "idx_interactions_engaged" in plan, plan
        assert "SCAN l" not in plan, f"Today scans every lead: {plan}"
    finally:
        conn.close()


def test_today_lists_the_same_people_in_the_same_order(home):
    import today
    from database import get_db
    conn = get_db()
    try:
        # Equal engagement times, so the order of ties is exercised.
        conn.execute("UPDATE lead_interactions SET first_seen_at = NULL, "
                     "interacted_at = datetime('now', '-1 day') WHERE id % 3 = 0")
        conn.commit()
        new = today._reply_to(conn)
        _without_new_indexes(conn)
        assert new == _old_reply_to(conn)
        assert new, "the history has people to reply to"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# One post's leads
# ---------------------------------------------------------------------------

OLD_ATTRIBUTION_SQL = """
    SELECT l.id as lead_id, COALESCE(l.full_name, l.name) as name, l.headline, l.company,
           COALESCE(l.seniority_level, 'Unknown') as seniority_level, COALESCE(l.icp_score, 0.0) as icp_score,
           COALESCE(l.lead_status, 'NEW') as lead_status, l.profile_url, li.id as interaction_id,
           li.interaction_type, li.comment_text, li.suggested_dm_reply, li.interacted_at
    FROM leads l
    LEFT JOIN lead_interactions li ON l.id = li.lead_id AND li.post_urn IN ({p})
    WHERE li.post_urn IN ({p}) OR l.post_id IN ({p})
    ORDER BY l.icp_score DESC, li.interacted_at DESC
"""


def _attribution_rows(monkeypatch, post):
    import crm
    from database import get_db
    captured = {}

    def traced():
        conn = get_db()
        captured["conn"] = conn
        captured["seen"] = _traced(conn)
        return conn

    monkeypatch.setattr(crm, "get_db", traced)
    result = crm.reverse_crm.get_post_attribution(post)
    monkeypatch.setattr(crm, "get_db", get_db)
    return result, captured["seen"]


def test_one_posts_leads_are_read_by_index(home, monkeypatch):
    from database import get_db
    _result, seen = _attribution_rows(monkeypatch, home["studio"][1])
    query = next(s for s in seen if "UNION ALL" in s)
    conn = get_db()
    try:
        plan = _plan(conn, query, ())
    finally:
        conn.close()
    assert "idx_interactions_post" in plan, plan
    assert "SCAN l" not in plan.split("UNION")[0], plan


def test_one_posts_leads_are_the_same_as_before(home, monkeypatch):
    import crm
    from database import get_db
    posts = home["studio"] + home["own"][:12] + ["no-such-post", "urn:li:activity:999"]
    new = {p: crm.reverse_crm.get_post_attribution(p) for p in posts}
    conn = get_db()
    _without_new_indexes(conn)
    conn.close()

    real_execute = sqlite3.Cursor.execute

    class OldCursor(sqlite3.Cursor):
        def execute(self, sql, params=()):
            if "UNION ALL" in sql and "lead_interactions li" in sql:
                keys = params[: len(params) // 3]
                sql = OLD_ATTRIBUTION_SQL.format(p=", ".join("?" for _ in keys))
            return real_execute(self, sql, params)

    class Wrapped:
        def __init__(self, conn):
            self._conn = conn

        def cursor(self):
            return self._conn.cursor(OldCursor)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setattr(crm, "get_db", lambda: Wrapped(get_db()))
    old = {p: crm.reverse_crm.get_post_attribution(p) for p in posts}
    assert any(r["leads"] for r in new.values()), "the history gives posts leads"
    for p in posts:
        assert new[p] == old[p], p


# ---------------------------------------------------------------------------
# Statistics kept current
# ---------------------------------------------------------------------------

def test_optimize_runs_after_migrations_and_then_hourly(home, monkeypatch):
    import database
    from paths import get_db_path
    calls = []
    monkeypatch.setattr(database, "optimize_db", lambda path=None: calls.append(path))
    monkeypatch.setattr(database, "_optimize_due", {})
    import time as time_module
    clock = [1000.0]
    monkeypatch.setattr(time_module, "monotonic", lambda: clock[0])
    database.get_db().close()
    assert calls == [], "optimize ran on the first connection, before anything was read"
    clock[0] += database.OPTIMIZE_EVERY_SECONDS + 1
    database.get_db().close()
    for thread in __import__("threading").enumerate():
        if thread.name == "inox-optimize":
            thread.join(5)
    assert calls == [get_db_path()]
    database.get_db().close()
    assert len(calls) == 1, "optimize ran again within the hour"


def test_optimize_db_runs_on_this_sqlite(home):
    import database
    database.optimize_db()
    conn = database.get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM sqlite_stat1").fetchone()[0] > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Activity: the most recently engaged leads
# ---------------------------------------------------------------------------

OLD_ACTIVITY_SQL = """
    SELECT l.id FROM leads l
    ORDER BY COALESCE(
        (SELECT MAX(COALESCE(i.first_seen_at, i.interacted_at)) FROM lead_interactions i WHERE i.lead_id = l.id),
        l.created_at) DESC, l.created_at DESC
    LIMIT ?
"""


def _keyed(conn, ids):
    """Each lead's place in the old order: (key, created_at), which decides it up to exact ties."""
    return [tuple(conn.execute(
        "SELECT COALESCE((SELECT MAX(COALESCE(i.first_seen_at, i.interacted_at)) FROM lead_interactions i "
        "WHERE i.lead_id = l.id), l.created_at), l.created_at FROM leads l WHERE l.id = ?", (i,)).fetchone())
        for i in ids]


@pytest.mark.parametrize("limit", [1, 5, 25, 50, 400])
def test_activity_lists_the_same_recent_leads(home, limit):
    from fastapi.testclient import TestClient
    import app as app_module
    from database import get_db
    conn = get_db()
    try:
        with conn:
            # Leads who never engaged, newer than everyone, and one whose
            # engagement has no time at all.
            for n in range(8):
                conn.execute("INSERT INTO leads (id, name, status, lead_status, created_at) "
                             "VALUES (?, ?, 'New Lead', 'NEW', datetime('now', '+1 day'))", (f"lead-new-{n}", f"N{n}"))
            conn.execute("INSERT INTO lead_interactions (lead_id, interaction_type, interacted_at, comment_key) "
                         "VALUES ('lead-0007', 'LIKE', NULL, 'nt')")
        body = TestClient(app_module.app).get("/api/v1/self/activity-stream", params={"limit": limit}).json()
        new = [lead["id"] for lead in body["recent_leads"]]
        old = [r[0] for r in conn.execute(OLD_ACTIVITY_SQL, (limit,))]
        assert len(new) == len(old)
        assert _keyed(conn, new) == _keyed(conn, old)
        if limit >= 5:
            assert set(new[:5]) <= {f"lead-new-{n}" for n in range(8)}
    finally:
        conn.close()


def test_activity_does_not_rank_every_lead(home, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module
    import database
    seen = []
    real = database.get_db

    def traced():
        conn = real()
        conn.set_trace_callback(seen.append)
        return conn

    import routers.browser as browser_router
    monkeypatch.setattr(browser_router, "get_db", traced)
    TestClient(app_module.app).get("/api/v1/self/activity-stream", params={"limit": 25})
    ranked = [s for s in seen if "SELECT MAX(COALESCE" in s]
    assert ranked and all("json_each" in s for s in ranked), "every lead was ranked"
