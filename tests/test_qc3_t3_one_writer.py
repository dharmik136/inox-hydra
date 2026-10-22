"""
One writer, and the README says what it is.
===========================================

`SingleWriterActor` was built at import in `studio/core/rate_limiter.py`, its
thread started immediately, and nothing ever submitted a task to it: measured
on the three-year dataset, `write_actor.get_metrics()` read
`tasks_processed: 0` after a full `import app`. Its one former consumer,
`GET /api/v1/rate-limiter/single-writer/metrics`, was removed in cycle 2.
Meanwhile `README.md:36` told a buyer the studio had "single-writer
serialization".

The thing it was built for was measurable. Thirty engagers of one post arrive
at once, which is exactly what the extension sends, and SQLite's busy handler
polls, so each writer waits for the whole queue rather than for its turn:

                            wall      mean per request   max
    30 sequential          1,318 ms        43.9 ms       63 ms
    30 concurrent, before  6,047 ms     5,776.0 ms    6,046 ms
    30 concurrent, after   1,522 ms       939.0 ms    1,515 ms

Measured on a copy of the three-year dataset (1,417 own_posts, 500,061
interactions) through the sandbox wrapper on port 8313. The extension's inline
retry budget is three attempts capped at 2,000 ms each, about 6 s, so before
this a real burst landed exactly on the edge of being pushed into the
keep-and-resend queue; now it finishes inside a sixth of that.

Captures go through the actor; `database.write_with_retry` stays the outer
guard, because a second studio window or the CLI holds the lock from another
process and an in-process queue cannot serialize that.
"""

import os
import re
import sys
import threading
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "studio", "backend"))

import app as app_module
import ingest_contract
import onboarding
from database import get_db
from rate_limiter import write_actor

client = TestClient(app_module.app)

ME = "t3-writer-88"
URN = "urn:li:activity:" + str(int(datetime(2025, 6, 6, tzinfo=timezone.utc).timestamp() * 1000) << 22)


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        try:
            with conn:
                conn.execute("DELETE FROM lead_interactions WHERE lead_id IN "
                             "(SELECT id FROM leads WHERE name LIKE 'T3W %')")
                conn.execute("DELETE FROM leads WHERE name LIKE 'T3W %'")
                conn.execute("DELETE FROM own_posts")
                conn.execute("DELETE FROM creator_identity")
        finally:
            conn.close()
    wipe()
    yield
    wipe()


def _confirm_with_a_post():
    assert onboarding.observe_profile({
        "vanity": ME, "display_name": "T3 Writer",
        "self_evidence": ["owner_edit_controls"],
    })["status"] == "candidate"
    onboarding.confirm_identity(ME)
    written = onboarding.ingest_own_posts(ME, [{"activity_urn": URN, "actor": ME,
                                                "text": "A post of mine with a busy comment section.",
                                                "reactions": 30}])
    assert written["written"] == 1, written


def _capture(n):
    return client.post("/api/v1/crm/interactions/ingest", json={
        "full_name": f"T3W Person {n}",
        "linkedin_urn": f"https://www.linkedin.com/in/t3w-person-{n}/",
        "headline": "VP Engineering at TraceCo",
        "interaction_type": "COMMENT",
        "comment_text": f"A comment from person {n}.",
        "post_urn": URN,
        "contract_version": ingest_contract.CONTRACT_VERSION,
    })


def test_a_capture_goes_through_the_single_writer():
    """
    The finding in one assertion: the actor had processed zero tasks ever.
    """
    _confirm_with_a_post()
    before = write_actor.get_metrics()["tasks_processed"]
    assert _capture(1).status_code == 200
    after = write_actor.get_metrics()["tasks_processed"]
    assert after > before, "the capture did not go through the single writer"
    assert write_actor.get_metrics()["is_alive"] is True


def test_thirty_captures_at_once_all_land_and_none_is_lost():
    """
    Serializing must not cost correctness. Thirty people, thirty rows, one
    row each, every request answered.
    """
    _confirm_with_a_post()
    answers = {}
    lock = threading.Lock()

    def one(n):
        answer = _capture(n)
        with lock:
            answers[n] = answer.status_code

    threads = [threading.Thread(target=one, args=(n,)) for n in range(100, 130)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started

    assert set(answers.values()) == {200}, answers
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM lead_interactions WHERE post_urn = ?", (URN,)).fetchone()[0]
    finally:
        conn.close()
    assert rows == 30, f"{rows} interaction rows for thirty captures"
    # Generous, because the suite runs beside other batches on a shared
    # machine. The measured figure on the three-year dataset is in the
    # docstring; this only has to fail if serialization is lost and thirty
    # writers queue behind the busy handler again.
    assert wall < 30.0, f"thirty concurrent captures took {wall:.1f}s"


def test_the_same_capture_sent_twice_is_still_one_engagement():
    """
    The keep-and-resend queue depends on this, and the writer must not change
    it: the capture runs inside the actor but in its own transaction.
    """
    _confirm_with_a_post()
    first = _capture(7).json()
    second = _capture(7).json()
    assert first["interaction"]["interaction_id"] == second["interaction"]["interaction_id"]
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM lead_interactions WHERE post_urn = ?", (URN,)).fetchone()[0]
    finally:
        conn.close()
    assert rows == 1


def test_a_write_still_happens_if_the_actor_cannot_take_it():
    """
    The capture is the creator's whether or not the queue is available, so a
    shut down or full actor means the write runs here, not that it is lost.
    """
    from studio.core.rate_limiter import SingleWriterActor
    spare = SingleWriterActor()
    spare.stop(timeout=2.0)
    done = []
    saved = ingest_contract.write_actor
    try:
        ingest_contract.write_actor = spare
        result = ingest_contract.through_the_writer("a probe", lambda: done.append(1) or "ran")
    finally:
        ingest_contract.write_actor = saved
    assert result == "ran" and done == [1]


def test_the_readme_describes_what_the_writer_actually_does():
    """
    README.md:36 sold "single-writer serialization" while the thread had never
    run a task. It is true now, and says what it serializes.
    """
    with open(os.path.join(REPO, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()
    row = [line for line in readme.splitlines() if "Request Pacing" in line]
    assert len(row) == 1, row
    assert "serializes capture writes" in row[0], row[0]
    assert "single-writer serialization" not in readme, (
        "the README still makes the claim that was not true")


def test_the_single_writer_metrics_route_is_still_gone():
    """Cycle 2 removed it; wiring the actor is not a reason to bring it back."""
    assert client.get("/api/v1/rate-limiter/single-writer/metrics").status_code == 404
