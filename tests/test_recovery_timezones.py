"""
The recovery check subtracts two times that can actually be subtracted.
=======================================================================

evaluate_schedule_recovery did (now - scheduled_at) with now defaulting to
datetime.now(), which is naive. Every stored schedule time goes through
normalize_datetime_to_utc_iso, which always writes an offset, so scheduled_at
is aware. Python refuses to subtract the two:

    TypeError: can't subtract offset-naive and offset-aware datetimes

and /api/v1/scheduler/recovery/evaluate answered 500 on the ordinary case.
The path that worked was the one where the caller happened to pass a naive
time, which is the path that means something different.

The second half is the peak window. It was built by calling .replace(hour=13)
on whatever `now` was. Do the arithmetic in UTC, as the fix requires, and that
becomes 13:15 UTC, which is a quarter to seven in the evening in Mumbai. The
window is a claim about the creator's working day, so it is built in the
frame the caller handed over and carries its offset in the answer.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from linkedin_client import linkedin_client

client = TestClient(app_module.app)

IST = timezone(timedelta(hours=5, minutes=30))


def test_an_aware_schedule_against_the_default_now_does_not_raise():
    """
    The exact shape stored in the posts table: an ISO string with a +00:00
    offset, evaluated with no current_time supplied.
    """
    stored = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()

    recovery = linkedin_client.evaluate_schedule_recovery(datetime.fromisoformat(stored))

    assert recovery["status"] == "GRACE_PERIOD_ELIGIBLE"
    assert recovery["delay_minutes"] == 20


def test_a_naive_schedule_against_the_default_now_measures_the_same_delay():
    """
    A naive value comes off the creator's own clock or their picker, so it is
    read as local time. Twenty minutes ago is twenty minutes late either way,
    and must not pick up the UTC offset as delay.
    """
    naive = (datetime.now() - timedelta(minutes=20)).isoformat()

    recovery = linkedin_client.evaluate_schedule_recovery(datetime.fromisoformat(naive))

    assert recovery["status"] == "GRACE_PERIOD_ELIGIBLE"
    assert recovery["delay_minutes"] == 20


@pytest.mark.parametrize(
    "scheduled, now",
    [
        # Both aware, the same zone.
        (datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)),
        # Both aware, different zones.
        (datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 17, 15, 30, tzinfo=IST)),
        # Aware schedule, naive now.
        (datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),
         datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
         + timedelta(hours=2)),
        # Naive schedule, aware now.
        ((datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc) - timedelta(hours=2))
         .astimezone().replace(tzinfo=None),
         datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)),
        # Both naive.
        (datetime(2026, 9, 17, 8, 0), datetime(2026, 9, 17, 10, 0)),
    ],
)
def test_two_hours_late_is_two_hours_late_in_every_combination(scheduled, now):
    """
    The delay is a duration, so it cannot depend on how either instant was
    labelled. Every pair above is the same two hours.
    """
    recovery = linkedin_client.evaluate_schedule_recovery(scheduled, current_time=now)

    assert recovery["delay_minutes"] == 120, (
        f"{scheduled.isoformat()} against {now.isoformat()} measured "
        f"{recovery['delay_minutes']} minutes rather than 120"
    )
    assert recovery["status"] == "AUTO_RESCHEDULED"


def test_the_peak_window_is_the_creators_afternoon_not_utcs():
    """
    13:15 is a statement about the creator's day. Computed in UTC it lands at
    18:45 for a creator in India, which is the opposite of a peak window.
    """
    now = datetime(2026, 9, 17, 10, 0, tzinfo=IST)
    scheduled = (now - timedelta(hours=2)).astimezone(timezone.utc)

    recovery = linkedin_client.evaluate_schedule_recovery(scheduled, current_time=now)

    rescheduled = datetime.fromisoformat(recovery["rescheduled_to"])
    assert (rescheduled.hour, rescheduled.minute) == (13, 15)
    assert rescheduled.utcoffset() == IST.utcoffset(None), (
        "the window was moved into another zone, so the creator is told a "
        "time that is not the one they will post at"
    )


def test_the_answer_says_which_clock_it_is_on():
    """
    A bare "13:15" leaves the client to guess a zone, which is how the naive
    and aware values got mixed to begin with.
    """
    now = datetime(2026, 9, 17, 10, 0, tzinfo=IST)
    recovery = linkedin_client.evaluate_schedule_recovery(
        now - timedelta(hours=2), current_time=now
    )

    assert recovery["current_time"].endswith("+05:30")
    assert recovery["rescheduled_to"].endswith("+05:30")


def test_a_future_schedule_is_still_on_time_across_zones():
    """The early return runs before the subtraction, so it needs the guard too."""
    now = datetime(2026, 9, 17, 10, 0, tzinfo=timezone.utc)
    future = datetime(2026, 9, 17, 17, 0, tzinfo=IST)  # 11:30 UTC

    recovery = linkedin_client.evaluate_schedule_recovery(future, current_time=now)

    assert recovery["status"] == "ON_SCHEDULE"
    assert recovery["delay_minutes"] == 0


def test_the_route_answers_a_stored_schedule_time():
    """
    The end to end case that returned 500: the string the posts table holds,
    posted to the endpoint with no current_time.
    """
    stored = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()

    response = client.post(
        "/api/v1/scheduler/recovery/evaluate", json={"scheduled_at": stored}
    )

    assert response.status_code == 200, response.text
    assert response.json()["recovery"]["status"] == "GRACE_PERIOD_ELIGIBLE"


def test_a_malformed_current_time_is_a_bad_request_not_a_crash():
    """It was parsed with no guard, so the caller's typo became our 500."""
    response = client.post(
        "/api/v1/scheduler/recovery/evaluate",
        json={
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "current_time": "yesterday afternoon",
        },
    )

    assert response.status_code == 400
