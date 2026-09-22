"""
Numbers survive a re-sync, and the funnel adds up to the table.
===============================================================

Three defects of the same shape: a figure the studio already had was destroyed
by code that looked like it was only adding to it.

  INSERT OR REPLACE writes the columns it names and reverts every column it
  does not. The series upsert named twelve of fourteen, so a stored reach of
  4200 became 0 and created_at was reset to now on every re-sync of a day. The
  profile-views branch carried reach forward with COALESCE, so the two upserts
  fought and whichever ran last erased the other's figure.

  The funnel assigned instead of accumulating. GROUP BY returns NULL and the
  empty string as separate groups, and both fold to NEW, so the second
  overwrote the first. Measured: 42 leads in the table, a funnel reading 12.

  Lead ids came from hash(), which Python randomises per process. The same
  profile produced 32333, 827572 and 711202 across three runs, so re-capturing
  someone created a second lead instead of matching the first.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from crm import reverse_crm, stable_lead_key
from database import get_db
from linkedin_client import linkedin_client

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROBE_DATE = "2031-07-07"
LEAD_PREFIX = "funnelprobe-"


@pytest.fixture(autouse=True)
def clean_probes():
    def purge():
        conn = get_db()
        try:
            conn.execute("DELETE FROM analytics_daily WHERE date = ?", (PROBE_DATE,))
            conn.execute("DELETE FROM leads WHERE id LIKE ?", (LEAD_PREFIX + "%",))
            conn.commit()
        finally:
            conn.close()

    purge()
    yield
    purge()


def _row():
    conn = get_db()
    try:
        return conn.execute(
            "SELECT impressions, unique_members_reached, created_at, period_label "
            "FROM analytics_daily WHERE date = ?",
            (PROBE_DATE,),
        ).fetchone()
    finally:
        conn.close()


def _seed_day(**columns):
    names = ", ".join(columns)
    marks = ", ".join("?" for _ in columns)
    conn = get_db()
    try:
        conn.execute(
            f"INSERT OR REPLACE INTO analytics_daily (date, source, {names}) "
            f"VALUES (?, 'observed', {marks})",
            (PROBE_DATE, *columns.values()),
        )
        conn.commit()
    finally:
        conn.close()


def test_a_resync_does_not_erase_reach():
    """
    unique_members_reached is written by the profile-views branch and was not
    named by the series upsert, so an ordinary re-sync deleted it.
    """
    _seed_day(impressions=1000, reactions=50, comments=10, shares=5,
              unique_members_reached=4200, engagement_rate=6.5)

    linkedin_client.ingest_analytics_payload({"series": [{
        "date": PROBE_DATE, "impressions": 1100, "likes": 55,
        "comments": 10, "shares": 5, "period_label": "1d", "precision": "exact",
    }]})

    row = _row()
    assert row["unique_members_reached"] == 4200, (
        "a re-sync reset reach to " + str(row["unique_members_reached"])
    )


def test_a_resync_keeps_when_the_row_was_first_seen():
    _seed_day(impressions=900, created_at="2031-07-07T09:00:00")

    linkedin_client.ingest_analytics_payload({"series": [{
        "date": PROBE_DATE, "impressions": 950, "period_label": "1d", "precision": "exact",
    }]})

    assert str(_row()["created_at"]).startswith("2031-07-07"), (
        "created_at was rewritten to now, so the row lost when it was first seen"
    )


def test_an_undetected_window_is_recorded_as_unknown_not_null():
    """
    The gate deliberately lets a payload with no detected window through, on
    the reasoning that a row labelled period unknown beats no row at all. It
    then stored NULL, which is indistinguishable from a row nobody asked
    about. Writing the state down is the point of migration 5.
    """
    linkedin_client.ingest_analytics_payload({"series": [{
        "date": PROBE_DATE, "impressions": 500, "likes": 20,
    }]})
    assert _row()["period_label"] == "unknown"


def test_a_multi_day_window_is_still_refused():
    """The honesty gate must not have been loosened by the above."""
    result = linkedin_client.ingest_analytics_payload({"series": [{
        "date": PROBE_DATE, "impressions": 90000, "period_label": "28d",
    }]})
    assert result["status"] == "window_mismatch"
    assert _row() is None, "a 28 day total was stored as one day of figures"


def _insert_lead(suffix, lead_status):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO leads (id, name, status, lead_status) VALUES (?, ?, ?, ?)",
            (LEAD_PREFIX + suffix, "Probe", "New Lead", lead_status),
        )
        conn.commit()
    finally:
        conn.close()


def test_the_funnel_reconciles_with_the_table():
    """
    Every lead appears in exactly one bucket, including those whose status is
    NULL and those whose status is an empty string. Both mean NEW, and the
    second used to overwrite the first.
    """
    for index in range(30):
        _insert_lead("null-" + str(index), None)
    for index in range(12):
        _insert_lead("empty-" + str(index), "")

    conn = get_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    finally:
        conn.close()

    funnel = reverse_crm.get_crm_telemetry()["funnel"]
    counted = sum(v for v in funnel.values() if isinstance(v, int))

    assert counted == total, (
        "the table holds " + str(total) + " leads and the funnel accounts for "
        + str(counted) + ". " + str(total - counted)
        + " leads are invisible to every chart."
    )


def test_an_unknown_status_does_not_invent_a_bucket():
    _insert_lead("weird", "NOT_A_REAL_STATUS")
    funnel = reverse_crm.get_crm_telemetry()["funnel"]
    assert "NOT_A_REAL_STATUS" not in funnel, "the funnel grew a category nobody designed"


def test_a_lead_id_is_the_same_in_every_process():
    """
    hash() is randomised per process, so one person's id changed on every
    restart and re-capturing them created a duplicate rather than matching.
    """
    identity = "https://www.linkedin.com/in/stability-probe"
    expected = stable_lead_key(identity)

    code = (
        "import sys; sys.path.insert(0, 'studio/backend'); "
        "from crm import stable_lead_key; "
        "print(stable_lead_key(" + repr(identity) + "))"
    )

    seen = set()
    for _ in range(3):
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == 0, result.stderr
        seen.add(result.stdout.strip())

    assert seen == {expected}, "the id changed between processes: " + str(seen)


def test_lead_ids_have_room_to_avoid_collisions():
    """
    A million buckets puts a collision near 39 percent at a thousand leads, and
    a collision is an IntegrityError in the middle of a capture.
    """
    keys = {stable_lead_key("https://www.linkedin.com/in/person-" + str(i)) for i in range(5000)}
    assert len(keys) == 5000, str(5000 - len(keys)) + " collisions across 5000 identities"


def test_no_lead_id_is_derived_from_pythons_hash():
    """Structural, so the unstable form cannot return."""
    import re

    import tokenize
    from io import StringIO

    def live_code(source):
        """
        Source with comments and string literals removed.

        Needed because the replacement helper's own docstring explains what it
        replaced, and names it. A naive line scan reads that explanation as the
        thing it forbids.
        """
        kept = []
        try:
            for token in tokenize.generate_tokens(StringIO(source).readline):
                if token.type in (tokenize.COMMENT, tokenize.STRING):
                    continue
                kept.append(token.string)
        except tokenize.TokenError:
            return source
        return " ".join(kept)

    offenders = []
    for relative in ("studio/backend/crm.py", "studio/backend/linkedin_client.py",
                     "studio/backend/agno_agent.py"):
        source = open(os.path.join(REPO_ROOT, relative), encoding="utf-8").read()
        if re.search(r"abs\s*\(\s*hash\s*\(", live_code(source)):
            offenders.append(relative)

    assert not offenders, (
        "lead ids are being derived from Python's randomised hash again: "
        + ", ".join(offenders)
    )
