"""
What an idle screen costs the database, counted rather than estimated.
=====================================================================

Cycle 4, track 2 (the show path). Setup read /api/v1/onboarding/state every
3 seconds, Activity its stream every 2.5 seconds and Today its brief every
30 seconds, each poll re-running the whole onboarding aggregate: about seven
connection opens and dozens of statements to learn, almost always, that
nothing had changed. The capture report put Setup at about 660 SELECTs a
minute from the code alone; nothing had counted.

This counts. Every connection the studio opens is traced through
sqlite3.connect, one poll of each screen's route is made through the
application, and the statements are sorted by their first word. The steady
cost per minute is then that count times the number of polls a minute, read
from the interval each screen declares in its own source, plus what the
change stream's data_version watcher runs on its one long-lived connection.
The figure is a product of two measured quantities, not a timing.

The ceiling is the guard: it was falsified by putting Setup's interval back
to 3 seconds (1,700 against 400) and Activity's back to 2.5 seconds (1,080).
A wall-clock minute in a real browser, recorded in
docs/quality/cycle4/t2-show.md, agrees: Setup 1,743 statements before and
273 after, Activity 1,123 and 193.
"""

import os
import re
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app import app  # noqa: E402

UI = os.path.join(REPO_ROOT, "studio", "ui", "src", "components")

# Each screen, the route its refresh reads, and the call that schedules it.
# The interval is read from the component rather than written here, because a
# number that lives in two places is a number that will disagree.
SCREENS = {
    "setup": ("/api/v1/onboarding/state", "OnboardingSurface.tsx", r"useRefresh\(refresh, BACKSTOP_MS, ANY_CHANGE\)"),
    "activity": ("/api/v1/self/activity-stream?limit=12", "ActivitySurface.tsx",
                 r"useRefresh\(loadData, autoRefresh \? BACKSTOP_MS : undefined, autoRefresh \? ANY_CHANGE : undefined\)"),
    "today": ("/api/v1/today", "TodaySurface.tsx", r"useRefresh\(load, BACKSTOP_MS, ANY_CHANGE\)"),
}

# The most an idle Setup or Activity may cost the database in a minute, all
# statements counted, the watcher's included. Counted before this track at
# 1,700 (Setup) and 1,080 (Activity); after it, 230 and 150, of which 60 are
# the watcher's one look a second.
STEADY_CEILING_PER_MINUTE = 400


def interval_ms(screen):
    _route, component, call = SCREENS[screen]
    with open(os.path.join(UI, component), encoding="utf-8") as handle:
        source = handle.read()
    # The screen schedules its read with the stream and the named backstop,
    # so the constant read below is the interval the screen really uses.
    assert re.search(call, source), f"{component} no longer refreshes the way this test reads it"
    match = re.search(r"const BACKSTOP_MS = ([\d_]+);", source)
    assert match, f"{component} no longer declares BACKSTOP_MS"
    return int(match.group(1).replace("_", ""))


def watcher_statements_per_minute():
    """The data_version poll the change stream runs while any window listens."""
    try:
        import changes
    except ImportError:
        return 0
    return int(round(60.0 / changes.WATCH_EVERY_S))


@pytest.fixture
def traced(monkeypatch):
    """Every statement on every connection the studio opens, by first word."""
    counts = {}
    real_connect = sqlite3.connect

    def record(statement):
        word = statement.strip().split(None, 1)[0].upper() if statement.strip() else "?"
        counts[word] = counts.get(word, 0) + 1
        counts["total"] = counts.get("total", 0) + 1

    def traced_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        conn.set_trace_callback(record)
        counts["opens"] = counts.get("opens", 0) + 1
        return conn

    monkeypatch.setattr(sqlite3, "connect", traced_connect)
    return counts


def one_poll(counts, route):
    client = TestClient(app)
    # The first call pays for things kept afterwards (the planner statistics,
    # the page cache), so the poll that is measured is the second.
    assert client.get(route).status_code == 200
    counts.clear()
    assert client.get(route).status_code == 200
    return dict(counts)


def steady_cost(screen, per_poll):
    polls_per_minute = 60_000.0 / interval_ms(screen)
    return int(round(per_poll.get("total", 0) * polls_per_minute)) + watcher_statements_per_minute()


@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_steady_cost_of_an_idle_screen_is_counted(traced, screen):
    route = SCREENS[screen][0]
    per_poll = one_poll(traced, route)
    assert per_poll.get("SELECT", 0) > 0, f"{route} ran no SELECT, so the trace is not seeing its connections"
    per_minute = steady_cost(screen, per_poll)
    sys.stderr.write(
        f"\n[t2-show] {screen}: {per_poll.get('opens', 0)} opens, {per_poll.get('SELECT', 0)} SELECT, "
        f"{per_poll.get('PRAGMA', 0)} PRAGMA, {per_poll.get('total', 0)} statements per poll; "
        f"interval {interval_ms(screen)} ms; watcher {watcher_statements_per_minute()} a minute; "
        f"steady {per_minute} statements a minute\n"
    )
    assert per_minute > 0


@pytest.mark.parametrize("screen", ["setup", "activity"])
def test_an_idle_screen_stays_under_the_ceiling(traced, screen):
    per_minute = steady_cost(screen, one_poll(traced, SCREENS[screen][0]))
    assert per_minute <= STEADY_CEILING_PER_MINUTE, (
        f"{screen} costs {per_minute} statements a minute while idle, over the {STEADY_CEILING_PER_MINUTE} "
        f"this track brought it under; the interval is {interval_ms(screen)} ms"
    )
