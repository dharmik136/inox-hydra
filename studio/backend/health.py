"""
Health: is the bridge reading, what did each reader read this week, and what
could it not read?
=============================================================================

The one new field the Health section needs, beside the routes the studio
already answered (extension health, schema status, the backup schedule, the
update preference): the run rows per reader. capture_health reads each reader
with LIMIT 1 and keeps only its state, so a creator could see that a reader
was "working" and not how often it ran, how much it saw, or how much it kept.

Every figure here carries its window, because the windows differ and none of
them is "ever":

  run rows     the capture log, which record_capture prunes to seven days on
               every write (onboarding.CAPTURE_RETENTION); the label says
               "last 7 days" because of that prune, not by choice
  day rows     one row per reader per day, rolled up by the migration's
               trigger and kept migrations.CAPTURE_DAYS_KEPT days
  heartbeats   bridge_heartbeats, which record_heartbeat prunes to
               onboarding.HEARTBEAT_RETENTION

A count that no run of the window measured stays None rather than reading as
zero: a reader that ran and found nothing to count is a different fact from
a reader whose runs did not count.

Strict Invariants:
- Zero em-dashes.
- No network request. Everything here is read from what the extension sent.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import migrations, onboarding
    from .database import get_db
except ImportError:
    import migrations
    import onboarding
    from database import get_db

# All readers by day, on the first view: this many days, newest first.
BY_DAY_SHOWN = 14

# The newest runs a reader's detail lists. The count beside them is the whole
# window's; the rows are a page of it, so a reader that ran four hundred
# times this week does not send four hundred rows to the screen.
RUN_ROWS_PER_READER = 20


def _reader_rows(conn, extractor: str, since: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT observed_at, page_kind, items_seen, items_kept, drift, extension_version FROM captures "
        "WHERE extractor = ? AND observed_at >= ? ORDER BY observed_at DESC",
        (extractor, since)).fetchall()
    return [{
        "observed_at": r["observed_at"],
        "page_kind": r["page_kind"],
        "items_seen": r["items_seen"],
        "items_kept": r["items_kept"],
        "drift": json.loads(r["drift"]) if r["drift"] else [],
        "extension_version": r["extension_version"],
    } for r in rows]


def _reader_days(conn, extractor: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(
        "SELECT day, runs, items_seen, items_kept, drift_runs, first_run_at, last_run_at FROM capture_days "
        "WHERE extractor = ? ORDER BY day DESC", (extractor,))]


def _heartbeats(conn, since: str, window_days: int) -> Dict[str, Any]:
    """
    How often the bridge was heard from, by which versions, and the longest
    silence between two heartbeats. Counted in SQL. Three tabs open for a
    week is about thirty thousand rows, and the whole summary then takes
    about 30 ms, most of it the window that finds the longest silence.
    """
    count, first, last = conn.execute(
        "SELECT COUNT(*), MIN(seen_at), MAX(seen_at) FROM bridge_heartbeats WHERE seen_at >= ?", (since,)).fetchone()
    versions = [{"extension_version": r["extension_version"], "first_seen_at": r["first_seen_at"],
                 "last_seen_at": r["last_seen_at"], "count": r["count"]} for r in conn.execute(
        "SELECT extension_version, MIN(seen_at) AS first_seen_at, MAX(seen_at) AS last_seen_at, COUNT(*) AS count "
        "FROM bridge_heartbeats WHERE seen_at >= ? GROUP BY extension_version ORDER BY first_seen_at", (since,))]
    page_kinds = {(r["page_kind"] or "unknown"): r["count"] for r in conn.execute(
        "SELECT page_kind, COUNT(*) AS count FROM bridge_heartbeats WHERE seen_at >= ? GROUP BY page_kind", (since,))}
    # The longest silence: each heartbeat against the one before it. None
    # with fewer than two heartbeats, because no gap can be measured.
    gap = conn.execute(
        "SELECT seen_at, gap FROM ("
        "  SELECT seen_at, (julianday(seen_at) - julianday(LAG(seen_at) OVER (ORDER BY seen_at))) * 1440.0 AS gap"
        "  FROM bridge_heartbeats WHERE seen_at >= ?"
        ") WHERE gap IS NOT NULL ORDER BY gap DESC, seen_at LIMIT 1", (since,)).fetchone()
    return {
        "window_days": window_days,
        "label": f"last {window_days} days",
        "count": count,
        "first_seen_at": first,
        "last_seen_at": last,
        "versions": versions,
        "page_kinds": page_kinds,
        "longest_silence_minutes": round(gap["gap"]) if gap else None,
        "longest_silence_ended_at": gap["seen_at"] if gap else None,
    }


def _windows() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    window_days = onboarding.CAPTURE_RETENTION.days
    return {
        "now": now,
        "since": (now - onboarding.CAPTURE_RETENTION).isoformat(),
        "window": {"days": window_days, "label": f"last {window_days} days",
                   "since": (now - onboarding.CAPTURE_RETENTION).isoformat()},
        "days_window": {"days": migrations.CAPTURE_DAYS_KEPT, "label": f"kept {migrations.CAPTURE_DAYS_KEPT} days"},
    }


def _listed(states: Dict[str, Dict[str, Any]]) -> List[str]:
    """
    The readers the screen lists, in the order the extension's table names
    them. The rule Setup's list followed (cycle 2, SETUP-17): a
    network-reading part is listed only once it has run. Network reading is
    off unless the creator switches it on, so listed always it read NOT SEEN
    YET for everyone, and the advice for that, open the matching page, does
    nothing for it. The header's network-reading sentence speaks for it
    until then. tests/test_qc4_t4_health.py holds this list to the
    onboarding state's, so the two cannot disagree about which readers exist.
    """
    return [extractor for extractor in onboarding.EXTRACTORS
            if not (extractor in onboarding.OPT_IN_EXTRACTORS and states[extractor]["state"] == "never_run")]


def readers() -> Dict[str, Any]:
    """
    The first view: per reader, its state as capture_health decides it and
    its runs in the prune's window, as counts; then the heartbeat summary over
    the same week. The runs themselves and the day rows are one level down,
    in reader(), so the first paint stays small however long the studio runs.
    """
    windows = _windows()
    states = {entry["extractor"]: entry for entry in onboarding.capture_health()}
    conn = get_db()
    try:
        # SUM is NULL when no run of the window measured the count, which is
        # the "not measured" the screen prints, never a zero it made up.
        week = {r["extractor"]: r for r in conn.execute(
            "SELECT extractor, COUNT(*) AS runs, SUM(items_seen) AS items_seen, SUM(items_kept) AS items_kept, "
            "SUM(CASE WHEN drift IS NULL THEN 0 ELSE 1 END) AS drift_runs "
            "FROM captures WHERE observed_at >= ? GROUP BY extractor", (windows["since"],))}
        held = {r["extractor"]: r["n"] for r in conn.execute(
            "SELECT extractor, COUNT(*) AS n FROM capture_days GROUP BY extractor")}
        listed = []
        for extractor in _listed(states):
            state = states[extractor]
            counted = week.get(extractor)
            listed.append({
                "extractor": extractor,
                "label": onboarding.EXTRACTORS[extractor],
                "opt_in": extractor in onboarding.OPT_IN_EXTRACTORS,
                "state": state["state"],
                "last_run_at": state["last_run_at"],
                "last_good_at": state["last_good_at"],
                "drift": state["drift"],
                "runs": counted["runs"] if counted else 0,
                "items_seen": counted["items_seen"] if counted else None,
                "items_kept": counted["items_kept"] if counted else None,
                "drift_runs": counted["drift_runs"] if counted else 0,
                "days_held": held.get(extractor, 0),
            })
        heartbeat_days = onboarding.HEARTBEAT_RETENTION.days
        beats = _heartbeats(conn, (windows["now"] - onboarding.HEARTBEAT_RETENTION).isoformat(), heartbeat_days)
        by_day = _by_day(conn, windows["now"])
    finally:
        conn.close()
    return {
        "status": "success",
        "window": windows["window"],
        "days_window": windows["days_window"],
        "readers": listed,
        "by_day": by_day,
        "heartbeats": beats,
    }


def _by_day(conn, now: datetime) -> Dict[str, Any]:
    """
    Every reader together, one row per UTC day for the last BY_DAY_SHOWN
    days, from the day rows the migration keeps. A day with no row after the
    first day held is a day the bridge read nothing; a day before it is a day
    the studio was not yet keeping, and says so rather than reading as silence.
    """
    first_held = conn.execute("SELECT MIN(day) FROM capture_days").fetchone()[0]
    since = (now.date() - timedelta(days=BY_DAY_SHOWN - 1)).isoformat()
    held = {r["day"]: r for r in conn.execute(
        "SELECT day, SUM(runs) AS runs, SUM(items_seen) AS items_seen, SUM(items_kept) AS items_kept, "
        "SUM(drift_runs) AS drift_runs FROM capture_days WHERE day >= ? GROUP BY day", (since,))}
    rows = []
    for n in range(BY_DAY_SHOWN):
        day = (now.date() - timedelta(days=n)).isoformat()
        row = held.get(day)
        state = "read" if row else ("nothing_read" if first_held and day >= first_held else "not_kept")
        rows.append({"day": day, "state": state,
                     "runs": row["runs"] if row else None, "items_seen": row["items_seen"] if row else None,
                     "items_kept": row["items_kept"] if row else None, "drift_runs": row["drift_runs"] if row else None})
    return {"days": BY_DAY_SHOWN, "label": f"last {BY_DAY_SHOWN} days", "first_held": first_held, "rows": rows}


def reader(extractor: str) -> Optional[Dict[str, Any]]:
    """
    One reader, one level down: its newest runs in the prune's window, with
    the window's count beside them, and every day row the studio keeps for it.
    None for a name the extension does not report on.
    """
    if extractor not in onboarding.EXTRACTORS:
        return None
    windows = _windows()
    conn = get_db()
    try:
        rows = _reader_rows(conn, extractor, windows["since"])
        days = _reader_days(conn, extractor)
    finally:
        conn.close()
    return {
        "status": "success",
        "extractor": extractor,
        "label": onboarding.EXTRACTORS[extractor],
        "window": windows["window"],
        "days_window": windows["days_window"],
        "runs": len(rows),
        "rows": rows[:RUN_ROWS_PER_READER],
        "days": days,
    }
