"""
A stored engagement rate agrees with the columns it is derived from.
====================================================================

`engaged` was summed from whatever metrics the CURRENT payload carried, and
COALESCE could not protect the column: the computed value is non NULL whenever
impressions are present, so it always won the merge.

Measured before the fix, against one day:

    morning, full card          1000 / 50 / 10 / 5   stored 6.5    correct
    afternoon, reactions only   1100 / 55 / 10 / 5   stored 5.0    implied 6.36
    impressions only            1200 / 55 / 10 / 5   stored 0.0    implied 5.83

The row contradicted itself, and the worst case wrote a zero over a real
figure. The rate is now derived from the merged row, so the column and its
inputs agree by construction whatever a payload omitted.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from database import get_db
from linkedin_client import linkedin_client

PROBE_DATE = "2031-03-14"


@pytest.fixture(autouse=True)
def clean_probe_row():
    def purge():
        conn = get_db()
        try:
            conn.execute("DELETE FROM analytics_daily WHERE date = ?", (PROBE_DATE,))
            conn.commit()
        finally:
            conn.close()

    purge()
    yield
    purge()


def _ingest(**metrics):
    bucket = {"date": PROBE_DATE, "period_label": "1d", "precision": "exact"}
    bucket.update(metrics)
    linkedin_client.ingest_analytics_payload({"series": [bucket]})


def _row():
    conn = get_db()
    try:
        return conn.execute(
            "SELECT impressions, reactions, comments, shares, engagement_rate "
            "FROM analytics_daily WHERE date = ?",
            (PROBE_DATE,),
        ).fetchone()
    finally:
        conn.close()


def _implied(row):
    impressions = row["impressions"] or 0
    if not impressions:
        return 0.0
    engaged = (row["reactions"] or 0) + (row["comments"] or 0) + (row["shares"] or 0)
    return round(engaged * 100.0 / impressions, 2)


def _assert_consistent(label):
    row = _row()
    assert row is not None, label + ": no row was written"
    stored = row["engagement_rate"] or 0.0
    implied = _implied(row)
    assert abs(stored - implied) < 0.01, (
        f"{label}: stored rate is {stored} but the row's own columns imply "
        f"{implied} (impressions={row['impressions']}, reactions={row['reactions']}, "
        f"comments={row['comments']}, shares={row['shares']})"
    )


def test_a_full_payload_is_consistent():
    _ingest(impressions=1000, likes=50, comments=10, shares=5)
    _assert_consistent("full payload")


def test_a_partial_payload_does_not_corrupt_the_rate():
    """
    The reported case. The afternoon sync ran while only the reactions card had
    rendered, so comments and shares were absent from the payload but present
    in the stored row.
    """
    _ingest(impressions=1000, likes=50, comments=10, shares=5)
    _ingest(impressions=1100, likes=55)
    _assert_consistent("partial payload")

    row = _row()
    assert row["comments"] == 10, "COALESCE should have preserved comments"
    assert row["shares"] == 5, "COALESCE should have preserved shares"


def test_an_impressions_only_payload_does_not_write_zero():
    """The worst case: a real rate replaced by 0.0."""
    _ingest(impressions=1000, likes=50, comments=10, shares=5)
    _ingest(impressions=1200)
    _assert_consistent("impressions only")

    row = _row()
    assert row["engagement_rate"] > 0, (
        "a payload carrying no engagement metrics wrote a zero rate over "
        "reaction columns that still hold real numbers"
    )


def test_zero_impressions_gives_a_zero_rate_not_a_crash():
    _ingest(impressions=0, likes=0)
    row = _row()
    assert (row["engagement_rate"] or 0.0) == 0.0


def test_repeated_identical_ingests_are_stable():
    """Re-syncing the same figures must not drift the rate."""
    for _ in range(3):
        _ingest(impressions=800, likes=40, comments=8, shares=2)
    _assert_consistent("repeated ingest")
    assert abs(_row()["engagement_rate"] - 6.25) < 0.01
