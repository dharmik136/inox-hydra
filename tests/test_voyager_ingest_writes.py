"""
A Voyager capture that is kept is actually written.
===================================================

record_voyager_ingest inserted creator analytics into a column named
observation_window. analytics_daily has no such column: migration 5 is called
_migrate_observation_window, and the column it adds is period_label. SQLite
refused the statement, the transaction rolled back, and the capture-health row
written in the same transaction went with it. Every creator analytics reading
the interceptor delivered was lost, and capture health never said so.

The impressions half of the same reading is deliberately not stored.
impressionAggregate is a total over a window the response does not name, and
writing it as today's impressions is the defect migration 5 was written to undo.

These drive the function against the real schema, which is the only thing that
could have caught a column name that reads plausibly.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from database import get_db, init_db  # noqa: E402
from onboarding import record_voyager_ingest  # noqa: E402


def _today_row():
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db()
    try:
        return conn.execute(
            "SELECT followers, impressions, period_label, precision FROM analytics_daily WHERE date = ?",
            (today,),
        ).fetchone()
    finally:
        conn.close()


def _voyager_captures():
    conn = get_db()
    try:
        return conn.execute(
            "SELECT items_seen, items_kept FROM captures WHERE extractor = 'voyager_creator_analytics'"
        ).fetchall()
    finally:
        conn.close()


def _clear_today():
    from datetime import datetime, timezone

    conn = get_db()
    try:
        with conn:
            conn.execute(
                "DELETE FROM analytics_daily WHERE date = ?",
                (datetime.now(timezone.utc).strftime("%Y-%m-%d"),),
            )
    finally:
        conn.close()


def test_the_follower_count_from_the_network_is_stored_for_today(confirmed_creator):
    init_db()
    _clear_today()
    before = len(_voyager_captures())

    result = record_voyager_ingest({
        "schema_name": "creator_analytics",
        "data": [{"followers": 1234, "impressions": 5678}],
        # The signed-in account the bridge names; see test_qc_f3_analytics_owner.
        "vanity": confirmed_creator,
        "extension_version": "test",
    })

    assert result["items_kept"] == 1
    row = _today_row()
    assert row is not None, "the reading was reported as kept and nothing was written"
    assert row["followers"] == 1234
    assert row["period_label"] == "1d"
    assert row["precision"] == "exact"
    assert len(_voyager_captures()) == before + 1, "capture health did not record the reading"


def test_an_aggregate_of_unknown_window_is_not_stored_as_a_day(confirmed_creator):
    init_db()
    _clear_today()
    record_voyager_ingest({"schema_name": "creator_analytics", "vanity": confirmed_creator,
                           "data": [{"followers": 900, "impressions": 40000}]})

    row = _today_row()
    assert row["impressions"] is None, (
        "impressionAggregate covers an unnamed window and was stored as today's impressions"
    )


def test_a_reading_without_followers_writes_nothing(confirmed_creator):
    init_db()
    _clear_today()
    result = record_voyager_ingest({"schema_name": "creator_analytics", "vanity": confirmed_creator,
                                    "data": [{"impressions": 41}]})

    assert result["items_kept"] == 0
    assert _today_row() is None
