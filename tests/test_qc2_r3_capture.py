"""
A capture stays cheap, however many posts the person engaged with.
==================================================================

Cycle 2, batch R3, review of DATA-02.

The capture wrote a provisional score for the lead, which marked every post
the lead had ever engaged with in the per-post summary, then recomputed all of
those rows inside its own transaction: a lead on 1,136 posts cost 1.1 s a
capture, holding the write lock, and 30 such captures at once (what the
extension sends for one post's engagers) failed 25 times with "database is
locked". A capture now writes the final score once, recomputes only the
captured post's row, and leaves any other marked rows to a short background
step and to the readers, in small transactions of their own.
"""

import os
import shutil
import sys
import tempfile
import threading

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_capture_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    conn.close()
    yield data
    import post_summary
    post_summary.wait_for_catch_up(10)
    shutil.rmtree(path, ignore_errors=True)


def _db():
    from database import get_db
    return get_db()


def _busiest(n=1):
    conn = _db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT l.id, l.full_name, l.linkedin_urn, l.headline, l.company, l.icp_score, x.posts FROM leads l JOIN "
            "(SELECT CAST(lead_id AS TEXT) AS lid, COUNT(DISTINCT post_urn) AS posts FROM lead_interactions "
            "GROUP BY lead_id) x ON x.lid = l.id WHERE l.linkedin_urn IS NOT NULL ORDER BY x.posts DESC LIMIT ?", (n,))]
    finally:
        conn.close()


def _recomputed(monkeypatch):
    """The size of every recompute the capture's own transaction makes."""
    import post_summary
    sizes = []
    real = post_summary._recompute

    def counting(conn, marked):
        if conn.in_transaction:
            sizes.append(len(marked))
        return real(conn, marked)

    monkeypatch.setattr(post_summary, "_recompute", counting)
    monkeypatch.setattr(post_summary, "catch_up_later", lambda *a, **k: None)
    return sizes


def _capture(lead, post, kind="LIKE", headline=None):
    import crm
    return crm.reverse_crm.ingest_interaction(
        full_name=lead["full_name"], linkedin_urn=lead["linkedin_urn"],
        headline=headline if headline is not None else lead["headline"], company=lead["company"],
        interaction_type=kind, comment_text="Thanks, useful" if kind == "COMMENT" else None, post_urn=post)


def test_a_capture_recomputes_only_the_captured_post(home, monkeypatch):
    import post_summary
    lead = _busiest()[0]
    assert lead["posts"] > 20, "the history has a busy lead"
    # The first capture settles the stored score and name, which the test
    # history wrote by hand; after it, nothing about the person changes.
    _capture(lead, home["own"][-2], "COMMENT")
    assert post_summary.wait_for_catch_up(10)
    sizes = _recomputed(monkeypatch)
    for kind in ("LIKE", "COMMENT"):
        _capture(lead, home["own"][-1], kind)
    assert sizes and max(sizes) <= 1, f"a capture recomputed {sizes} summary rows in its transaction"
    conn = _db()
    try:
        stale = conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0]
        assert stale == 0, "an unchanged score marked the lead's other posts"
    finally:
        conn.close()


def test_a_changed_score_is_caught_up_outside_the_capture(home, monkeypatch):
    import post_summary
    lead = _busiest()[0]
    sizes = _recomputed(monkeypatch)
    _capture(lead, home["own"][-1], "COMMENT", headline="Founder and CEO at Newco")
    assert max(sizes) <= 1
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] > 10
        caught = post_summary.catch_up(conn, batch=7)
        assert caught > 10
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] == 0
        assert post_summary.differences(conn) == []
    finally:
        conn.close()


def test_the_background_step_catches_up(home):
    import post_summary
    lead = _busiest()[0]
    _capture(lead, home["own"][-1], "COMMENT", headline="Chief Executive Officer")
    assert post_summary.wait_for_catch_up(10), "the background catch-up did not finish"
    conn = _db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM post_engagement WHERE stale != 0").fetchone()[0] == 0
        assert post_summary.differences(conn) == []
    finally:
        conn.close()


def test_the_score_is_what_it_was(home):
    """The final score, written once, is the one the provisional write used to settle on."""
    import crm
    lead = _busiest()[0]
    result = _capture(lead, home["own"][-1], "LIKE", headline="Student")
    conn = _db()
    try:
        rows = conn.execute("SELECT interaction_type, comment_text FROM lead_interactions WHERE lead_id = ?",
                            (lead["id"],)).fetchall()
        expected = max(crm.ICPScoringEngine.calculate_icp_score("Student", lead["company"], r[1], r[0]) for r in rows)
        stored = conn.execute("SELECT icp_score FROM leads WHERE id = ?", (lead["id"],)).fetchone()[0]
    finally:
        conn.close()
    assert result["icp_score"] == stored == expected


def test_thirty_busy_captures_at_once_all_succeed(home):
    leads = _busiest(30)
    errors = []

    def capture(k, lead):
        try:
            _capture(lead, home["own"][k % len(home["own"])], "LIKE")
        except Exception as exc:  # pragma: no cover - the failure being tested for
            errors.append(repr(exc))

    threads = [threading.Thread(target=capture, args=(k, lead)) for k, lead in enumerate(leads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert errors == []
    import post_summary
    post_summary.wait_for_catch_up(10)
    conn = _db()
    try:
        assert post_summary.differences(conn) == []
    finally:
        conn.close()
