"""
The per-post summary is the raw rows, counted once.
==================================================

Cycle 2, batch R3 (DATA-02).

Posts, Analytics, Patterns (attribution and evidence), Outbound and Today read
every one of 500,000 interactions into Python on every load: 0.4 to 1.9 s a
screen on three years of one prolific creator. They now read post_engagement,
one row per post (studio/backend/post_summary.py), built by migration 21 and
kept current by triggers that mark rows stale, by the capture and reading
writers that refresh what they marked, and by every reader catching up.

Two kinds of test:
- consistency: after every way the raw rows change, the table equals a fresh
  computation from them;
- the same answers: each screen's numbers equal what the old full scan
  computed, written out here as it was, on a history built to have ties.
"""

import json
import os
import shutil
import statistics
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_sum_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    # The scores the fixture wrote into the column are derived values, and
    # since batch T2 a derived value that has not been recomputed is marked
    # stale and brought current by the first reader. Doing it here leaves the
    # history as a real install's would be, so the tests below compare two
    # computations over the same scores rather than racing the catch-up.
    import crm
    crm.catch_up_scores(conn)
    conn.close()
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _db():
    from database import get_db
    return get_db()


def _consistent(conn):
    import post_summary
    problems = post_summary.differences(conn)
    assert problems == [], problems[:10]


# ---------------------------------------------------------------------------
# Built by the migration, and kept true to the raw rows
# ---------------------------------------------------------------------------

def test_migration_21_builds_every_post(monkeypatch):
    """A database that already holds a history gets every row at migration time."""
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_mig_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    try:
        import migrations
        from database import init_db, get_db
        init_db()
        conn = get_db()
        qc2_r3_data.build(conn)
        # Back to version 20 with no summary, as an existing install is.
        conn.execute("DROP TABLE post_engagement")
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger' "
                                    "AND name LIKE 'post_engagement_%'").fetchall():
            conn.execute(f"DROP TRIGGER {name}")
        conn.execute("PRAGMA user_version = 20")
        conn.commit()
        report = migrations.ensure_schema(conn, take_backup=False)
        assert 21 in [m["version"] for m in report["applied"]]
        # The migration marks every post; the summary computes them straight
        # after, as database.init_db does.
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] > 50
        import post_summary
        post_summary.catch_up(conn, batch=500)
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM post_engagement").fetchone()[0] > 50
        _consistent(conn)
        # Idempotent: run again over the same rows, the same table.
        before = conn.execute("SELECT * FROM post_engagement ORDER BY post_urn").fetchall()
        with conn:
            for statement in dict((v, p) for v, _d, p in migrations.MIGRATIONS)[21]:
                conn.execute(statement)
        post_summary.catch_up(conn, batch=500)
        assert [tuple(r) for r in conn.execute("SELECT * FROM post_engagement ORDER BY post_urn")] == \
            [tuple(r) for r in before]
        conn.close()
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_the_thresholds_are_the_crms():
    import crm
    import post_summary
    assert post_summary.VIP_SCORE == crm.VIP_THRESHOLD
    assert post_summary.QUALIFIED_SCORE == crm.QUALIFIED_THRESHOLD


def test_a_capture_leaves_the_summary_current(home):
    """
    The captured post is current when the capture returns; the person's other
    posts, marked when their score moved, are caught up just after, outside
    the capture's transaction (tests/test_qc2_r3_capture.py).
    """
    import crm
    import post_summary
    post = home["own"][-1]
    for n in range(3):
        crm.reverse_crm.ingest_interaction(
            full_name=f"New Person {n}", linkedin_urn=f"https://www.linkedin.com/in/new-{n}",
            headline="CTO at Newco", interaction_type="COMMENT", comment_text="Is pricing per seat?",
            post_urn=post)
    # The same person again, now a VIP by a new headline: their score moves
    # on every post they engaged with.
    crm.reverse_crm.ingest_interaction(
        full_name="New Person 0", linkedin_urn="https://www.linkedin.com/in/new-0",
        headline="Founder and CEO", interaction_type="LIKE", post_urn=home["own"][-2])
    conn = _db()
    try:
        assert conn.execute("SELECT stale FROM post_engagement WHERE post_urn = ?",
                            (home["own"][-2],)).fetchone()[0] == 0
        assert post_summary.wait_for_catch_up(10)
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] == 0
        _consistent(conn)
    finally:
        conn.close()


def test_a_reading_leaves_the_summary_current(home):
    import onboarding
    import post_summary
    post = home["own"][-1]
    conn = _db()
    try:
        with conn:
            onboarding._record_observation(conn, post, "post_analytics", {"impressions": 4321, "reactions": 77})
        row = conn.execute("SELECT stale, latest_reading FROM post_engagement WHERE post_urn = ?", (post,)).fetchone()
        assert row["stale"] == 0
        assert post_summary.reading_of(dict(row), "latest_reading")["impressions"] == 4321
        _consistent(conn)
    finally:
        conn.close()


@pytest.mark.parametrize("change", [
    "UPDATE leads SET lead_status = 'ENGAGED' WHERE id IN (SELECT id FROM leads LIMIT 40)",
    "UPDATE leads SET icp_score = 91 WHERE rowid % 5 = 0",
    "UPDATE leads SET icp_score = NULL WHERE rowid % 7 = 0",
    "UPDATE leads SET full_name = 'Aaron Aardvark' WHERE rowid % 9 = 0",
    "UPDATE leads SET name = 'Zed' WHERE full_name IS NULL",
    "DELETE FROM leads WHERE rowid % 4 = 0",
    "DELETE FROM lead_interactions WHERE id % 3 = 0",
    "UPDATE OR IGNORE lead_interactions SET post_urn = (SELECT activity_urn FROM own_posts LIMIT 1) WHERE id % 11 = 0",
    "UPDATE OR IGNORE lead_interactions SET interaction_type = 'COMMENT' WHERE id % 6 = 0",
    "UPDATE OR IGNORE lead_interactions SET lead_id = 'lead-0001' WHERE id % 13 = 0 AND lead_id != 'lead-0001'",
    "DELETE FROM post_metric_observations WHERE id % 2 = 0",
    "UPDATE post_metric_observations SET age_hours = 48 WHERE id % 17 = 0",
    "DELETE FROM lead_interactions",
])
def test_any_change_to_the_raw_rows_is_caught_up(home, change):
    """Direct SQL, as a forget, an import undo or a future writer would do it."""
    conn = _db()
    try:
        with conn:
            conn.execute(change)
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] > 0
        _consistent(conn)
    finally:
        conn.close()


def test_forgetting_and_archiving_are_caught_up(home):
    import crm
    for lead_id in home["leads"][:30]:
        crm.reverse_crm.purge_lead(lead_id)
    conn = _db()
    try:
        with conn:
            conn.execute("UPDATE leads SET updated_at = '2020-01-01 00:00:00'")
    finally:
        conn.close()
    crm.reverse_crm.archive_inactive_leads(90)
    conn = _db()
    try:
        _consistent(conn)
    finally:
        conn.close()


def test_a_reader_never_waits_on_a_writer(home):
    """With the write lock held elsewhere, a read computes the stale rows itself."""
    import post_summary
    writer = _db()
    reader = _db()
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute("UPDATE leads SET lead_status = 'CONVERTED' WHERE id = ?", (home["leads"][1],))
        writer.commit()
        writer.execute("BEGIN IMMEDIATE")
        rows = post_summary.current(reader)
        writer.rollback()
        fresh = post_summary.compute(reader)
        assert {u: r["conversations"] for u, r in rows.items()} == {u: r["conversations"] for u, r in fresh.items()}
        assert reader.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] > 0
        post_summary.current(reader)
        assert reader.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] == 0
    finally:
        writer.close()
        reader.close()


def test_lead_ids_round_trip_whatever_they_contain():
    import post_summary
    for ids in (["lead-1", "lead_2"], ["odd\x1fid", "x"], ["\x1estart", "y"], []):
        encoded = post_summary._encode_ids(ids)
        assert post_summary.lead_ids_of({"lead_ids": encoded}) == ids


# ---------------------------------------------------------------------------
# The same answers as the full scans they replace
# ---------------------------------------------------------------------------

def _old_engagers(conn):
    """insights.posts_overview's scan before R3, in the order its plan read rows."""
    import onboarding
    engagers = {}
    for row in conn.execute(
            "SELECT i.post_urn, i.lead_id, i.interaction_type, COALESCE(l.full_name, l.name) AS name, l.lead_status "
            "FROM leads l JOIN lead_interactions i ON l.id = i.lead_id WHERE i.post_urn IS NOT NULL "
            "ORDER BY l.rowid, i.lead_id, i.interacted_at DESC, i.id"):
        engagers.setdefault(onboarding._activity_id(row["post_urn"]), []).append(dict(row))
    return engagers


def test_posts_screen_people_are_the_same(home):
    import insights
    import onboarding
    conn = _db()
    try:
        with conn:
            # Give the conversations count something to count.
            conn.execute("UPDATE leads SET lead_status = 'ENGAGED' WHERE rowid % 6 = 0")
        old = _old_engagers(conn)
    finally:
        conn.close()
    result = insights.posts_overview()
    checked = 0
    for post in result["posts"]:
        by_person = {}
        for p in old.get(onboarding._activity_id(post["activity_urn"]), []):
            person = by_person.setdefault(str(p["lead_id"]), {
                "lead_id": str(p["lead_id"]), "name": p["name"], "commented": False, "status": p["lead_status"]})
            if p["interaction_type"] == "COMMENT":
                person["commented"] = True
        assert post["people"] == sorted(by_person.values(),
                                        key=lambda p: (not p["commented"], p["name"] or ""))[:12], post["activity_urn"]
        assert post["people_count"] == len(by_person)
        assert post["conversations"] == sum(1 for p in by_person.values()
                                            if (p["status"] or "") in ("ENGAGED", "CONVERTED"))
        checked += bool(by_person)
    assert checked > 40


def test_analytics_attribution_is_the_same(home):
    from fastapi.testclient import TestClient
    import app as app_module
    from crm import VIP_THRESHOLD
    conn = _db()
    try:
        scores, people = {}, {}
        for r in conn.execute("""
            SELECT li.post_urn AS post_key, l.id AS lead_id, l.icp_score
            FROM leads l CROSS JOIN lead_interactions li ON li.lead_id = l.id
            WHERE li.post_urn IS NOT NULL AND li.post_urn != ''
            UNION ALL
            SELECT post_id, id, icp_score FROM leads WHERE post_id IS NOT NULL AND post_id != ''"""):
            scores[r["lead_id"]] = r["icp_score"]
            people.setdefault(r["post_key"], set()).add(r["lead_id"])
        studio_ids = {r["activity_urn"]: r["id"] for r in conn.execute("SELECT id, activity_urn FROM posts")}
    finally:
        conn.close()
    body = TestClient(app_module.app).get("/api/analytics/posts").json()
    tied = 0
    for post in body["posts"]:
        key = str(studio_ids.get(post["activity_urn"]) or post["id"]) if post.get("activity_urn") else str(post["id"])
        brought = people.get(key, set()) | people.get(post.get("activity_urn") or "", set())
        known = [scores[lead] for lead in brought if scores[lead] is not None]
        assert post["attribution"] == {
            "total_leads": len(brought),
            "vip_leads": sum(1 for s in known if s >= VIP_THRESHOLD),
            "avg_icp": round(sum(known) / len(known), 1) if known else 0.0,
        }, post["id"]
        tied += key in people and key != post.get("activity_urn")
    assert tied, "the lead tied to a post by leads.post_id was not exercised"


def test_topic_attribution_is_the_same(home):
    import evidence_briefing
    conn = _db()
    try:
        with conn:
            conn.execute("UPDATE leads SET status = 'Connected' WHERE rowid % 10 = 0")
            conn.execute("UPDATE leads SET lead_status = 'converted' WHERE rowid % 15 = 0")
        people_per_post, qualified = {}, set()
        for row in conn.execute("SELECT i.post_urn, l.id, l.icp_score, l.lead_status, l.status "
                                "FROM lead_interactions i JOIN leads l ON l.id = i.lead_id WHERE i.post_urn IS NOT NULL"):
            icp = row["icp_score"] or 0
            people_per_post.setdefault(row["post_urn"], set()).add(row["id"])
            if icp >= 60.0 or (row["lead_status"] or "").upper() in ("ENGAGED", "CONVERTED") or \
                    "connected" in (row["status"] or "").lower() or "meeting" in (row["status"] or "").lower():
                qualified.add(row["id"])
        posts = [dict(r) for r in conn.execute("SELECT activity_urn, text FROM own_posts WHERE text IS NOT NULL")]
    finally:
        conn.close()
    vocabulary = evidence_briefing.derive_topic_vocabulary([p["text"] for p in posts])
    expected = {}
    for p in posts:
        topic = evidence_briefing.classify_post_topic(p["text"], vocabulary)
        expected.setdefault(topic, set()).update(people_per_post.get(p["activity_urn"], set()))
    result = evidence_briefing.get_topic_attribution_map()
    got = {t["topic"]: (t["people_engaged"], t["qualified_leads"]) for t in result["topics"]}
    assert got == {topic: (len(people), len(people & qualified)) for topic, people in expected.items()}
    assert any(q for _p, q in got.values())


def test_evidence_exemplars_are_the_same(home):
    import evidence_briefing
    import results
    conn = _db()
    try:
        # The people each exemplar brought, counted the way the old full scan
        # counted them. The order is results.best's since batch T2: the panel
        # ranked raw reactions with no settled rule, so it named posts no
        # other screen named and could feed the copilot a post three hours
        # old. What has to stay the same is the count beside each exemplar.
        qualified = {r["activity_urn"]: r["qualified_leads"] for r in conn.execute("""
            SELECT p.activity_urn,
                   COUNT(DISTINCT CASE WHEN q.icp_score >= :qualified
                                       OR UPPER(COALESCE(q.lead_status, '')) IN ('ENGAGED', 'CONVERTED')
                                       THEN q.lead_id END) AS qualified_leads
            FROM own_posts p
            LEFT JOIN (SELECT li.post_urn, l.id AS lead_id, l.icp_score, l.lead_status
                       FROM leads l CROSS JOIN lead_interactions li ON li.lead_id = l.id) q
                   ON q.post_urn = p.activity_urn
            WHERE p.text IS NOT NULL
            GROUP BY p.activity_urn""", {"qualified": results.QUALIFIED_SCORE})}
        order = results.ranking(conn)["order"]
    finally:
        conn.close()
    result = evidence_briefing.get_retrieval_evidence_brief(limit_top=len(order), limit_bottom=0)
    assert [p["activity_urn"] for p in result["top_exemplars"]] == order
    for post in result["top_exemplars"]:
        assert post["qualified_leads"] == qualified[post["activity_urn"]], post["activity_urn"]


def test_outbound_reciprocity_is_the_same(home):
    """
    The screen's reciprocity number is the one the interactions say, for the
    person the name resolves to.

    Cycle 3 batch T7 sharpened what the name means. This used to add together
    every captured person who answered to the author's display name, which on
    this three year history merged dozens of strangers into one row (one read
    533 of the creator's posts) and cost 51 seconds to compute. A name that
    belongs to exactly one captured person is that person's; a name that
    belongs to several is reported as several rather than as a number, and
    `named_people` is how the screen knows which it has.
    """
    import insights
    import onboarding
    # Every generated name in this history belongs to several captured people,
    # so one person of their own name is added: without them the matched path
    # has nothing to check.
    conn = _db()
    try:
        urn = conn.execute("SELECT activity_urn FROM own_posts LIMIT 1").fetchone()[0]
        with conn:
            conn.execute("INSERT INTO leads (id, name, headline, status) "
                         "VALUES ('lead-only-one-of-these', 'Solveig Ravnsborg', 'Founder', 'New Lead')")
            conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at) "
                         "VALUES ('lead-only-one-of-these', ?, 'COMMENT', '2026-10-01T00:00:00')", (urn,))
            conn.execute("INSERT INTO outbound_engagements (target_activity_urn, target_author, kind, "
                         "my_text_key, first_seen_at, last_seen_at) "
                         "VALUES ('urn:li:activity:7399999999999999999', 'Solveig Ravnsborg', 'reaction', "
                         "'', '2026-10-02T00:00:00', '2026-10-02T00:00:00')")
    finally:
        conn.close()

    conn = _db()
    try:
        own_ids = onboarding._own_activity_ids(conn)
        people = {}
        for row in conn.execute("SELECT l.id AS lead_id, COALESCE(l.full_name, l.name) AS name, i.post_urn "
                                "FROM lead_interactions i JOIN leads l ON l.id = i.lead_id "
                                "WHERE i.post_urn IS NOT NULL"):
            post = onboarding._activity_id(row["post_urn"])
            if post in own_ids:
                people.setdefault(row["lead_id"], set()).add(post)
        by_name = {}
        for row in conn.execute("SELECT id, COALESCE(full_name, name) AS name FROM leads"):
            by_name.setdefault(insights._name_key(row["name"]), []).append(row["id"])
        read_posts = {onboarding._activity_id(r[0]) for r in conn.execute(
            "SELECT DISTINCT post_urn FROM lead_interactions WHERE post_urn IS NOT NULL")}
    finally:
        conn.close()
    result = insights.outbound_overview()
    assert result["authors"], "the history has outbound authors"
    matched = 0
    for author in result["authors"]:
        ids = by_name.get(insights._name_key(author["name"]), [])
        assert author["named_people"] == len(ids), author
        if len(ids) == 1:
            matched += 1
            assert author["engaged_back"] == len(people.get(ids[0], ())), author
        else:
            assert author["engaged_back"] == 0, author
    assert matched, "no author name resolved to one person, so nothing was checked"
    assert any(a["engaged_back"] for a in result["authors"])
    conn = _db()
    try:
        engaged_posts = [r[0] for r in conn.execute(
            "SELECT activity_urn FROM own_posts WHERE COALESCE(reactions, 0) + COALESCE(comments, 0) > 0")]
    finally:
        conn.close()
    assert result["coverage"]["posts_read"] == sum(1 for u in engaged_posts if onboarding._activity_id(u) in read_posts)


def test_todays_comparison_reads_the_same_readings(home):
    import today
    conn = _db()
    try:
        posts = conn.execute("SELECT activity_urn FROM own_posts WHERE published_at IS NOT NULL "
                             "ORDER BY published_at DESC LIMIT 21").fetchall()

        def old_at_age(urn):
            rows = conn.execute("SELECT age_hours, impressions, reactions, comments FROM post_metric_observations "
                                "WHERE activity_urn = ? AND age_hours BETWEEN 36 AND 72 ORDER BY observed_at, id",
                                (urn,)).fetchall()
            return dict(min(rows, key=lambda r: abs(r["age_hours"] - 48.0))) if rows else None

        old = [old_at_age(p[0]) for p in posts]
        import results
        figure = results.figures(conn, [posts[0][0]])[posts[0][0]]
        latest = today._latest_post(conn)
    finally:
        conn.close()
    assert old[0] and sum(1 for r in old if r) > 10, "the history has readings at two days"
    assert old[0]["age_hours"] == 47.5, "the tie at 47.5 and 48.5 hours goes to the earlier reading"
    # What the post is doing now is results.figures, the one answer every
    # screen reads. Today showed the two day old reading as the post's current
    # figures, so one post read 19,943 impressions here and 50,118 on Posts in
    # the same minute. The comparison below is still made at two days old.
    assert latest["current"] == figure
    assert latest["current"]["impressions"] != old[0]["impressions"], (
        "the history's latest reading differs from its two day reading, which is the point")
    usual = [r for r in old[1:] if r]
    assert latest["comparison"], latest["not_compared_because"]
    for metric, entry in latest["comparison"].items():
        assert entry["this_post"] == old[0][metric]
        theirs = [r[metric] for r in usual if r[metric] is not None]
        assert entry["your_usual"] == statistics.median(theirs)
        assert entry["posts_compared"] == len(theirs)


def _old_lead_review(onboarding):
    """onboarding.lead_review before R3: every interaction classified one by one."""
    conn = _db()
    try:
        own_ids = onboarding._own_activity_ids(conn)
        complete = onboarding.post_history_complete(conn)
        leads = {r["id"]: dict(r) for r in conn.execute(
            "SELECT id, COALESCE(full_name, name) AS name, headline, created_at FROM leads")}
        origins = {lead_id: [] for lead_id in leads}
        for row in conn.execute("SELECT lead_id, post_urn FROM lead_interactions"):
            if str(row["lead_id"]) in origins:
                origins[str(row["lead_id"])].append(onboarding._origin(row["post_urn"], own_ids, complete))
    finally:
        conn.close()
    groups = {"yours": [], "not_yours": [], "unknown": []}
    for lead_id, seen in origins.items():
        verdict = ("yours" if "yours" in seen else
                   "not_yours" if seen and all(o == "not_yours" for o in seen) else "unknown")
        groups[verdict].append({**leads[lead_id], "interactions": len(seen)})
    return {"status": "success", "history_complete": complete, "counts": {k: len(v) for k, v in groups.items()},
            "not_yours": sorted(groups["not_yours"], key=lambda l: l.get("created_at") or "")}


@pytest.mark.parametrize("complete", [False, True])
def test_the_leads_review_is_the_same(home, monkeypatch, complete):
    import onboarding
    monkeypatch.setattr(onboarding, "post_history_complete", lambda conn: complete)
    conn = _db()
    try:
        with conn:
            # People who engaged only with someone else's post, some of them also without a post.
            for n in range(12):
                conn.execute("INSERT INTO leads (id, name, full_name, status, lead_status, created_at) "
                             "VALUES (?, ?, ?, 'New Lead', 'NEW', '2026-01-01 00:00:00')",
                             (f"lead-away-{n}", f"Away {n}", f"Away {n}"))
                conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_key) "
                             "VALUES (?, 'urn:li:activity:123456789', 'LIKE', '')", (f"lead-away-{n}",))
                if n % 3 == 0:
                    conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_key) "
                                 "VALUES (?, NULL, 'LIKE', '')", (f"lead-away-{n}",))
    finally:
        conn.close()
    new = onboarding.lead_review()
    assert new == _old_lead_review(onboarding)
    assert bool(new["not_yours"]) == complete and new["counts"]["yours"] > 100


# ---------------------------------------------------------------------------
# Reactions folded by the retention job (batch R4)
# ---------------------------------------------------------------------------

def _fold(monkeypatch, ids):
    """
    Batch R4's fold (retention._run_reactions), as the Storage and privacy
    panel runs it, over these reactions only: they are dated past the 24
    month cutoff, and the cutoff is set so that nothing else is.
    """
    import retention
    conn = _db()
    try:
        with conn:
            conn.execute("UPDATE lead_interactions SET last_seen_at = '2001-01-01T00:00:00+00:00' "
                         "WHERE id IN (SELECT value FROM json_each(?))", (json.dumps(ids),))
    finally:
        conn.close()
    monkeypatch.setattr(retention, "_fold_cutoff", lambda: "2002-01-01T00:00:00+00:00")
    return retention._run_reactions(retention.rules())


def _likes_with_a_comment(conn, ids):
    """How many of these likes were by someone who also commented on that post."""
    return conn.execute("""
        SELECT COUNT(*) FROM lead_interactions i WHERE i.id IN (SELECT value FROM json_each(?))
          AND EXISTS (SELECT 1 FROM lead_interactions o WHERE o.lead_id = i.lead_id
                      AND o.post_urn = i.post_urn AND o.interaction_type = 'COMMENT')""",
                        (json.dumps(ids),)).fetchone()[0]


def test_folded_reactions_still_count_on_the_posts_screen(home, monkeypatch):
    """
    A folded reaction loses its person, not its post: the Posts screen counts
    the same people for a post after the fold as before it, including the
    people who also commented, who are counted once (retention.folded_counts
    keeps how many folded reactors did nothing else on the post).
    """
    import insights
    import post_summary

    def shown():
        # Every post, not the first page of them: the Posts screen answers
        # with one page since batch T4, and this counts the whole history.
        return {p["activity_urn"]: (p["people_count"], p["conversations"])
                for p in insights.posts_overview(limit=insights.POSTS_PAGE_MAX)["posts"]}

    before = shown()
    conn = _db()
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM lead_interactions WHERE interaction_type = 'LIKE' AND post_urn != '' "
            "ORDER BY id LIMIT 400")]
        assert _likes_with_a_comment(conn, ids) > 10, "some folded reactors also commented on the post"
    finally:
        conn.close()
    assert _fold(monkeypatch, ids) == len(ids)
    conn = _db()
    try:
        folded = dict(conn.execute("SELECT post_urn, reactions FROM reaction_folds").fetchall())
        assert sum(folded.values()) == len(ids)
        _consistent(conn)
        rows = post_summary.current(conn)
        assert all(rows[urn]["folded_reactions"] == n for urn, n in folded.items())
    finally:
        conn.close()
    after = insights.posts_overview(limit=insights.POSTS_PAGE_MAX)["posts"]
    assert {p["activity_urn"]: (p["people_count"], p["conversations"]) for p in after} == before
    assert sum(p["folded_reactions"] for p in after) == sum(n for urn, n in folded.items() if urn in home["own"]) > 300


def test_analytics_and_topic_counts_are_the_same_after_a_fold(home, monkeypatch):
    """
    Folding reactions leaves every post's leads, VIP and average score in
    Analytics and in its leads drawer, and every topic's people and qualified
    people, as they were: for people who did nothing else, people who also
    commented, people who reacted to several posts of a topic, qualified
    people and a lead tied to a post by leads.post_id alike.
    """
    import crm
    import evidence_briefing
    from fastapi.testclient import TestClient
    import app as app_module
    client = TestClient(app_module.app)
    tied_post = home["studio"][2]

    def counts():
        posts = {p["id"]: (p["attribution"]["total_leads"], p["attribution"]["vip_leads"], p["attribution"]["avg_icp"])
                 for p in client.get("/api/analytics/posts").json()["posts"]}
        topics = {t["topic"]: (t["people_engaged"], t["qualified_leads"])
                  for t in evidence_briefing.get_topic_attribution_map()["topics"]}
        drawer = {}
        for post_id in home["studio"]:
            summary = crm.reverse_crm.get_post_attribution(post_id)["attribution_summary"]
            drawer[post_id] = tuple(summary[k] for k in ("total_leads_generated", "vip_leads_count", "avg_icp_score",
                                                         "likes_count", "total_interactions"))
        brief = evidence_briefing.get_retrieval_evidence_brief(limit_top=10, limit_bottom=10)
        evidence = [(p.get("activity_urn"), p.get("qualified_leads"))
                    for p in brief["top_exemplars"] + brief["bottom_exemplars"]]
        return posts, topics, drawer, evidence

    conn = _db()
    try:
        with conn:
            # A lead tied to a studio post by leads.post_id who also liked it:
            # Analytics and the drawer count them from the tie.
            conn.execute("INSERT INTO leads (id, name, full_name, status, lead_status, icp_score, post_id) "
                         "VALUES ('lead-tied', 'Tied', 'Tied', 'New Lead', 'NEW', 85, ?)", (tied_post,))
            urn = conn.execute("SELECT activity_urn FROM posts WHERE id = ?", (tied_post,)).fetchone()[0]
            conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_key) "
                         "VALUES ('lead-tied', ?, 'LIKE', '')", (urn,))
    finally:
        conn.close()
    before = counts()
    conn = _db()
    try:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM lead_interactions WHERE interaction_type = 'LIKE' AND post_urn != ''")]
        assert _likes_with_a_comment(conn, ids) > 10
        qualified = conn.execute(
            "SELECT COUNT(DISTINCT i.lead_id) FROM lead_interactions i JOIN leads l ON l.id = CAST(i.lead_id AS TEXT) "
            "WHERE i.id IN (SELECT value FROM json_each(?)) AND l.icp_score >= 60", (json.dumps(ids),)).fetchone()[0]
        assert qualified > 10, "qualified people's reactions are folded too"
        tied = conn.execute("SELECT COUNT(*) FROM lead_interactions i JOIN leads l ON l.id = CAST(i.lead_id AS TEXT) "
                            "WHERE i.interaction_type = 'LIKE' AND COALESCE(l.post_id, '') != '' AND "
                            "(l.post_id = i.post_urn OR l.post_id IN (SELECT id FROM posts WHERE activity_urn = i.post_urn))"
                            ).fetchone()[0]
    finally:
        conn.close()
    assert tied >= 1
    # The tied lead's reaction is kept as a row, so nobody is counted twice.
    assert _fold(monkeypatch, ids) == len(ids) - tied
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM lead_interactions WHERE lead_id = 'lead-tied'").fetchone()[0] == 1
        _consistent(conn)
    finally:
        conn.close()
    after = counts()
    assert after == before
    assert sum(leads for leads, _vip, _avg in after[0].values()) > 0
    assert sum(row[3] for row in after[2].values()) > 0, "the drawers count folded likes"


def test_a_post_with_only_folded_reactions_keeps_its_row(home, monkeypatch):
    import post_summary
    post = home["own"][5]
    conn = _db()
    try:
        with conn:
            conn.execute("DELETE FROM post_metric_observations WHERE activity_urn = ?", (post,))
            conn.execute("DELETE FROM lead_interactions WHERE post_urn = ? AND interaction_type != 'LIKE'", (post,))
        people = post_summary.current(conn, [post])[post]["people"]
        ids = [r[0] for r in conn.execute("SELECT id FROM lead_interactions WHERE post_urn = ?", (post,))]
    finally:
        conn.close()
    assert people > 0
    assert _fold(monkeypatch, ids) == len(ids)
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM lead_interactions WHERE post_urn = ?", (post,)).fetchone()[0] == 0
        row = post_summary.current(conn, [post])[post]
        assert row["people"] == people and row["folded_reactions"] == len(ids)
        assert post_summary.lead_ids_of(row) == []
        _consistent(conn)
    finally:
        conn.close()