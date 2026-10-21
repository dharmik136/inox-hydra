"""
Thirty Captures at Once, on a Machine With No Patience (CI-WIN2-01).
====================================================================

The Windows job of CI run 39613386365 lost three of the thirty captures the
extension sends for one post's engagers: each was refused with
"database is locked", and those three people were simply not on the post,
with nothing said. SQLite's busy handler polls, so a writer in a crowd can
lose every poll for the whole busy timeout while the queue it waits in is
only a few hundred milliseconds long.

This machine is about twice as fast as that runner, so it is made harsher
instead: the captures are given a few hundred milliseconds of patience
rather than the product's five seconds, and the write transaction is slowed
from inside.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
"""

import logging
import os
import sqlite3
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
for entry in (REPO_ROOT, BACKEND, os.path.dirname(__file__)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from studio.backend import app as app_module  # noqa: E402
from studio.backend import database, paths  # noqa: E402

# ---------------------------------------------------------------------------
# CI-WIN2-01: thirty captures at once, on a machine with no patience
# ---------------------------------------------------------------------------

@pytest.fixture
def busy_home(monkeypatch):
    """A studio with a small history of posts and leads to capture onto."""
    import shutil
    import tempfile

    import qc2_r3_data
    path = tempfile.mkdtemp(prefix="inox_qc2_ci_win2_")
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


def _both_flavours():
    """
    The studio's modules as both studio.backend.x and x.

    The engine imports them one way and the suite the other, and a patch on
    one copy does not reach the other, so a test that means to change the
    product's behaviour has to say so for both.
    """
    import crm as crm_alone
    import database as database_alone
    from studio.backend import crm as crm_package
    from studio.backend import database as database_package
    return [database_alone, database_package, crm_alone, crm_package]


def _impatient(monkeypatch, milliseconds):
    """
    Every connection opened from here on waits `milliseconds` for the lock.

    The runner is about twice as slow as this machine, so the way to see what
    it saw is to ask for less patience than the product allows, not more time.
    """
    real = database.get_db

    def open_impatiently():
        conn = real()
        conn.execute(f"PRAGMA busy_timeout = {int(milliseconds):d}")
        return conn

    for module in _both_flavours():
        monkeypatch.setattr(module, "get_db", open_impatiently, raising=False)


def _busiest(n):
    conn = database.get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT l.id, l.full_name, l.linkedin_urn, l.headline, l.company FROM leads l JOIN "
            "(SELECT CAST(lead_id AS TEXT) AS lid, COUNT(DISTINCT post_urn) AS posts FROM lead_interactions "
            "GROUP BY lead_id) x ON x.lid = l.id WHERE l.linkedin_urn IS NOT NULL ORDER BY x.posts DESC LIMIT ?",
            (n,))]
    finally:
        conn.close()


def _capture_all(home, leads):
    """Every lead captured onto a post at the same moment. Returns the refusals."""
    import crm
    errors = []

    def capture(k, lead):
        try:
            crm.reverse_crm.ingest_interaction(
                full_name=lead["full_name"], linkedin_urn=lead["linkedin_urn"], headline=lead["headline"],
                company=lead["company"], interaction_type="LIKE", comment_text=None,
                post_urn=home["own"][k % len(home["own"])])
        except Exception as exc:  # pragma: no cover - the failure being tested for
            errors.append(repr(exc))

    threads = [threading.Thread(target=capture, args=(k, lead)) for k, lead in enumerate(leads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    return errors


def test_thirty_captures_at_once_survive_an_impatient_database(busy_home, monkeypatch):
    """
    Thirty captures at once, each waiting 50 ms for the lock instead of the
    product's five seconds, and three such bursts, which is what the
    extension sends while the creator scrolls three posts' engagers. Nine of
    the first thirty were refused before the retry, and which writer loses is
    chance, so the bursts are repeated.
    """
    _impatient(monkeypatch, 50)
    leads = _busiest(30)
    for burst in range(3):
        assert _capture_all(busy_home, leads) == [], f"burst {burst + 1}"
    import post_summary
    post_summary.wait_for_catch_up(10)
    conn = database.get_db()
    try:
        assert post_summary.differences(conn) == []
    finally:
        conn.close()


def test_captures_survive_a_slow_write_transaction(busy_home, monkeypatch):
    """
    The same thirty, with every capture holding the write lock a tenth of a
    second longer than it needs to, which is what a slow runner, a scanner
    reading the file or a fuller database does to the queue.
    """
    import post_summary
    real_refresh = post_summary.refresh

    def slowly(conn, keys=None):
        time.sleep(0.1)
        return real_refresh(conn, keys)

    monkeypatch.setattr(post_summary, "refresh", slowly)
    _impatient(monkeypatch, 1000)
    assert _capture_all(busy_home, _busiest(30)) == []


def test_the_same_capture_sent_twice_is_one_engagement(busy_home):
    """
    What the extension's retry and its queue rest on (CI-WINDOWS2-N1): a
    payload that arrives a second time, because the first answer was lost or
    the capture was kept and sent again, must not count as a second
    engagement or a second person. The unique key from migration 11 holds
    the row; seen_count is how often the capture has read the same thing, as
    reopening the post already does.
    """
    import crm
    lead = _busiest(1)[0]
    post = busy_home["own"][-1]
    conn = database.get_db()
    try:
        before = conn.execute("SELECT COUNT(*) FROM lead_interactions").fetchone()[0]
        leads_before = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()

    def capture():
        return crm.reverse_crm.ingest_interaction(
            full_name=lead["full_name"], linkedin_urn=lead["linkedin_urn"], headline=lead["headline"],
            company=lead["company"], interaction_type="COMMENT", comment_text="Thanks, useful", post_urn=post)

    first, again = capture(), capture()
    assert first["lead_id"] == again["lead_id"]
    assert first["interaction_id"] == again["interaction_id"]
    assert first["icp_score"] == again["icp_score"]
    conn = database.get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM lead_interactions").fetchone()[0] == before + 1
        assert conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == leads_before
        row = conn.execute(
            "SELECT seen_count FROM lead_interactions WHERE id = ?", (first["interaction_id"],)).fetchone()
        assert row["seen_count"] == 2, "the repeat was not recorded as the same engagement seen again"
        import post_summary
        post_summary.wait_for_catch_up(10)
        people = post_summary.current(conn, [post])[post]["people"]
    finally:
        conn.close()
    conn = database.get_db()
    try:
        counted = conn.execute(
            "SELECT COUNT(DISTINCT CAST(lead_id AS TEXT)) FROM lead_interactions WHERE post_urn = ?", (post,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert people == counted, "the post counts the repeated capture as another person"


def test_a_write_that_stays_locked_is_refused_in_a_bounded_number_of_tries(busy_home, monkeypatch, caplog):
    """
    A database somebody else holds for good is not retried for ever: the
    write is attempted WRITE_ATTEMPTS times, each attempt is logged with its
    number, and the last one raises so the route can answer.
    """
    _impatient(monkeypatch, 50)
    import crm
    for module in _both_flavours():
        monkeypatch.setattr(module, "WRITE_WAIT_S", 0.001, raising=False)
    other = sqlite3.connect(paths.get_db_path(), timeout=0.1)
    other.execute("BEGIN EXCLUSIVE")
    tries = []
    real = database.write_with_retry

    def counted(what, write, attempts=None):
        def counting():
            tries.append(what)
            return write()
        return real(what, counting, attempts)

    monkeypatch.setattr(crm, "write_with_retry", counted)
    try:
        with caplog.at_level(logging.WARNING, logger="studio.database"):
            with pytest.raises(sqlite3.OperationalError):
                crm.reverse_crm.ingest_interaction(
                    full_name="Lockedout Person", linkedin_urn="https://www.linkedin.com/in/lockedout-x",
                    headline="Engineer at Example", company="Example", interaction_type="LIKE",
                    post_urn=busy_home["own"][0])
    finally:
        other.rollback()
        other.close()
    assert len(tries) == database.WRITE_ATTEMPTS, tries
    said = "\n".join(record.getMessage() for record in caplog.records)
    assert "Capturing an engagement" in said
    assert "attempt 1 of" in said and "stayed locked" in said


def test_a_capture_that_cannot_be_saved_says_the_studio_is_busy(busy_home, monkeypatch):
    """
    A refused write is not a 500 with nothing a person can do: the capture
    endpoint answers 503 studio_busy with Retry-After, and nothing is written.
    """
    _impatient(monkeypatch, 50)
    for module in _both_flavours():
        monkeypatch.setattr(module, "WRITE_ATTEMPTS", 2, raising=False)
        monkeypatch.setattr(module, "WRITE_WAIT_S", 0.001, raising=False)
    client = TestClient(app_module.app, raise_server_exceptions=False)
    other = sqlite3.connect(paths.get_db_path(), timeout=0.1)
    other.execute("BEGIN EXCLUSIVE")
    try:
        answer = client.post("/api/v1/crm/interactions/ingest", json={
            "full_name": "Busy Person", "linkedin_urn": "https://www.linkedin.com/in/busy-person-x",
            "headline": "Engineer at Example", "interaction_type": "LIKE",
            "post_urn": busy_home["own"][0]})
    finally:
        other.rollback()
        other.close()
    assert answer.status_code == 503, answer.text
    body = answer.json()
    assert body["detail"]["code"] == "studio_busy", body
    assert answer.headers.get("Retry-After")
    conn = database.get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM leads WHERE full_name = 'Busy Person'").fetchone()[0] == 0
    finally:
        conn.close()
