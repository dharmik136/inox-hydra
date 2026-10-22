"""
The capture gate asks the database once, instead of reading every post.
=======================================================================

Cycle 3, batch T4 (P-11). `onboarding.engagement_gate` decides whether a
captured engager may be stored, and it did so by reading every row of
own_posts into Python and running a regex on each. Measured on 1,417 posts:
0.33 ms to read plus 0.30 ms of regex per capture, before any write, against
0.011 ms for the indexed lookup it could be, and it grew with the creator's
history. At the 30 captures the extension sends for one post that was 19 ms
of pure overhead.

own_posts.activity_urn is the table's primary key, and both writers store it
as `urn:li:<kind>:<digits>` with the kind one of the three LinkedIn uses
(onboarding._ACTIVITY_URN, archive_import._urn), so asking for the three
spellings of one activity id is the same question the scan answered.
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

ENGAGER = "https://www.linkedin.com/in/someone-else"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t4_gate_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    data = qc2_r3_data.build(conn)
    # The archive names a post by its share or ugcPost id, so own_posts holds
    # all three spellings.
    with conn:
        for kind, digits in (("share", "7111111111111111111"), ("ugcPost", "7222222222222222222")):
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                         "first_seen_at, last_seen_at) VALUES (?, 'From the archive', '2026-01-01T00:00:00+00:00', "
                         "'archive', '2026-01-01 00:00:00', '2026-01-01 00:00:00')",
                         (f"urn:li:{kind}:{digits}",))
    conn.close()
    data["spellings"] = ["7111111111111111111", "7222222222222222222"]
    yield data
    shutil.rmtree(path, ignore_errors=True)


def _old_gate(engager_profile, post_urn, post_author):
    """engagement_gate as it stood before T4: every own_posts row, one regex each."""
    import onboarding
    from database import get_db
    import ingest_contract
    me = onboarding.confirmed_vanity()
    if not me:
        return ingest_contract.GATE_SETUP_FIRST
    if onboarding.normalise_vanity(engager_profile) == me:
        return ingest_contract.GATE_THAT_IS_YOU
    if onboarding.normalise_vanity(post_author) == me:
        return None
    wanted = onboarding._activity_id(post_urn)
    if wanted:
        conn = get_db()
        try:
            for row in conn.execute("SELECT activity_urn FROM own_posts"):
                if onboarding._activity_id(row["activity_urn"]) == wanted:
                    return None
        finally:
            conn.close()
    # Batch T3 replaced the gate's words with the ingest contract's reason
    # catalogue. This reference exists to prove the indexed lookup reaches the
    # same verdict as reading every row, so it speaks the same catalogue: the
    # wording is T3's to own, the verdict is what is compared here.
    return ingest_contract.GATE_NOT_YOUR_POST


def test_the_gate_does_not_read_every_post_to_judge_one_capture(home, monkeypatch):
    import onboarding
    from database import get_db
    seen = []

    def traced():
        conn = get_db()
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(onboarding, "get_db", traced)
    assert onboarding.engagement_gate(ENGAGER, home["own"][3], None) is None
    monkeypatch.undo()

    scans = [s for s in seen if "own_posts" in s and "activity_urn IN" not in s and "WHERE" not in s]
    assert not scans, f"the gate still reads every post: {scans}"
    asked = [s for s in seen if "own_posts" in s]
    assert len(asked) == 1, asked

    conn = get_db()
    try:
        plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + asked[0]))
        assert "SEARCH" in plan and "SCAN own_posts" not in plan, plan
    finally:
        conn.close()


def test_the_gate_gives_the_same_verdict_as_reading_every_post(home):
    import onboarding
    cases = []
    for urn in home["own"][:20]:
        cases.append((ENGAGER, urn, None))
        cases.append((ENGAGER, f"https://www.linkedin.com/feed/update/{urn}/", None))
    for digits in home["spellings"]:
        for kind in ("activity", "share", "ugcPost"):
            cases.append((ENGAGER, f"urn:li:{kind}:{digits}", None))
    cases += [
        (ENGAGER, "urn:li:activity:9999999999999999999", None),
        (ENGAGER, None, None),
        (ENGAGER, "", None),
        (ENGAGER, "not a urn at all", None),
        (ENGAGER, "urn:li:activity:9999999999999999999", qc2_r3_data.ME),
        (f"https://www.linkedin.com/in/{qc2_r3_data.ME}", home["own"][0], None),
    ]
    for engager, urn, author in cases:
        assert onboarding.engagement_gate(engager, urn, author) == _old_gate(engager, urn, author), (engager, urn)
    # The three spellings of a post the studio holds are accepted, and an
    # activity id it has never seen is refused, so the cases above are not all
    # the same answer.
    assert onboarding.engagement_gate(ENGAGER, f"urn:li:activity:{home['spellings'][0]}", None) is None
    import ingest_contract
    assert onboarding.engagement_gate(ENGAGER, "urn:li:activity:9999999999999999999", None) == (
        ingest_contract.GATE_NOT_YOUR_POST)
