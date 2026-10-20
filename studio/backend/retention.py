"""
Retention: What the Studio Keeps, for How Long, and What It Asks First.
=======================================================================
Nothing used to expire except three logs. After three heavy years one creator
profile held 363,000 post readings, 500,000 engagements, 167,000 telemetry
events and every backup ever made, and a person the creator forgot stayed in
all of those backups for ever. This module holds the rules that bound that,
and the Storage and privacy panel in Brand Studio shows them.

The rules (owner decisions, cycle 2):

  daily backup      on; rotation keeps about 14 (studio/backend/support.py)
  telemetry         kept 30 days (7, 30 or 90)
  post readings     after 30 days, the last reading of each day is kept,
                    and every reading from a post's comparison window, so
                    Today's two-day comparison is exactly what it was
  reactions         older than 24 months, folded into per-post counts;
                    comments are always kept
  silent leads      never acted on and silent for 24 months: listed for
                    review, and forgotten only when the creator says so
  connections       kept as they are

Every cleanup here can be previewed (preview()), is logged (retention_log),
is idempotent (running it twice removes nothing more), never runs inside a
migration, and has a verified backup behind it: the creator's own runs take
one first, and the daily run reuses the backup it has just made, which holds
everything a cleanup can remove. Readings and reactions that already exist
are folded or rolled up only after the creator confirms a preview; the
migration that added these rules starts them at "ask" wherever there was data.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- A cleanup removes rows in batches, each its own transaction, so a stop part
  way leaves a consistent database that the next run finishes.
- A number that was not measured is None, never 0.
"""

import functools
import json
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from . import paths, sqlite_open, support
    from .crm import reverse_crm
    from .database import get_db
    from .migrations import SCHEMA_VERSION
    from .today import COMPARE_WINDOW
except ImportError:  # top-level import mode
    import paths
    import sqlite_open
    import support
    from crm import reverse_crm
    from database import get_db
    from migrations import SCHEMA_VERSION
    from today import COMPARE_WINDOW

try:
    from studio.core.telemetry_shard import TELEMETRY_DB_FILENAME
except ImportError:
    try:
        from core.telemetry_shard import TELEMETRY_DB_FILENAME
    except ImportError:
        TELEMETRY_DB_FILENAME = "analytics_telemetry.db"

logger = logging.getLogger("studio.retention")

BATCH = 500
LEAD_SILENT_DAYS = 730          # 24 months
REACTION_FOLD_DAYS = 730        # 24 months

# Each rule: the settings key, the value used when none is stored, the values
# accepted, and the default as the panel states it.
RULES: Dict[str, Dict[str, Any]] = {
    "daily_backup": {"key": "retention_daily_backup", "fallback": "on", "options": ["on", "off"],
                     "default": "on"},
    "telemetry_days": {"key": "retention_telemetry_days", "fallback": "30", "options": ["7", "30", "90"],
                       "default": "30"},
    # "ask" is set by migration 20 where readings or reactions already existed,
    # and replaced only by the creator: "on" through run() after a preview, or "off".
    "readings": {"key": "retention_readings", "fallback": "ask", "options": ["on", "off", "ask"],
                 "default": "on"},
    "readings_days": {"key": "retention_readings_days", "fallback": "30", "options": ["30", "90", "365"],
                      "default": "30"},
    "fold_reactions": {"key": "retention_fold_reactions", "fallback": "ask", "options": ["on", "off", "ask"],
                       "default": "on"},
    "lead_review": {"key": "retention_lead_review", "fallback": "ask", "options": ["ask", "off"],
                    "default": "ask"},
}

LAST_BACKUP_KEY = "retention_last_daily_backup"

JOBS = ("telemetry", "readings", "reactions")
# The jobs the daily run may do on its own, and the rule that switches each on.
_JOB_SWITCH = {"readings": "readings", "reactions": "fold_reactions"}


class RetentionRefused(ValueError):
    """A request this module will not carry out, with the reason to show."""


# A cleanup the creator starts may run behind a checked backup made this long
# ago, rather than write another full copy (about 190 MB at three years).
REUSE_BACKUP_WITHIN = timedelta(minutes=60)


def _taking_turns(func):
    """
    Runs a cleanup, a forget, a scrub or a compact only when no restore,
    archive import or other backup or cleanup is running (support.FILES_LOCK).
    """
    @functools.wraps(func)
    def turn(*args, **kwargs):
        try:
            with support.maintenance_turn():
                return func(*args, **kwargs)
        except support.MaintenanceBusy as busy:
            raise RetentionRefused(f"Not now: {busy}. Nothing was changed; try again when it has finished.") from busy
    return turn


# ---------------------------------------------------------------------------
# Settings and the log
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: Optional[datetime] = None) -> str:
    return (moment or _now()).strftime("%Y-%m-%d %H:%M:%S")


def _read_setting(conn, key: str) -> Optional[str]:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def _write_setting(conn, key: str, value: Optional[str]) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        return
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP",
        (key, value))


def rules(conn=None) -> Dict[str, str]:
    """Each rule's current value, the fallback where none is stored or it is not one of its options."""
    own = conn is None
    conn = conn or get_db()
    try:
        out = {}
        for name, rule in RULES.items():
            value = _read_setting(conn, rule["key"])
            out[name] = value if value in rule["options"] else rule["fallback"]
        return out
    finally:
        if own:
            conn.close()


def set_rules(changes: Dict[str, Any]) -> Dict[str, str]:
    """
    Changes rules. RetentionRefused for an unknown rule or value.

    Readings and reactions cannot be switched on here: that is run(), after
    the creator has seen what it removes, because switching them on is what
    lets the daily run remove the rows that already exist.
    """
    if not isinstance(changes, dict) or not changes:
        raise RetentionRefused("name a rule to change")
    for name, value in changes.items():
        rule = RULES.get(name)
        if rule is None:
            raise RetentionRefused(f"there is no rule called {name!r}")
        if str(value) not in rule["options"] or str(value) == "ask":
            raise RetentionRefused(f"{name} can be {', '.join(o for o in rule['options'] if o != 'ask')}")
        if name in _JOB_SWITCH.values() and str(value) == "on":
            raise RetentionRefused(f"{name} is switched on by confirming its preview, so you see what it removes first")
    conn = get_db()
    try:
        with conn:
            for name, value in changes.items():
                _write_setting(conn, RULES[name]["key"], str(value))
        return rules(conn)
    finally:
        conn.close()


def _log(job: str, started: datetime, outcome: str, removed: int = 0,
         backup: Optional[str] = None, detail: Optional[Dict[str, Any]] = None) -> None:
    conn = get_db()
    try:
        with conn:
            conn.execute(
                "INSERT INTO retention_log (job, started_at, finished_at, outcome, removed, backup, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job, _stamp(started), _stamp(), outcome, removed,
                 os.path.basename(backup) if backup else None, json.dumps(detail or {}, default=str)))
    finally:
        conn.close()
    logger.info("Retention %s: %s, %s removed%s.", job, outcome, removed,
                f", backup {os.path.basename(backup)}" if backup else "")


def recent_log(limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT job, started_at, finished_at, outcome, removed, backup, detail FROM retention_log "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["detail"] = json.loads(item["detail"] or "{}")
        except ValueError:
            item["detail"] = {}
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Sizes
# ---------------------------------------------------------------------------

CATEGORIES = (
    ("posts", "Your posts, drafts and queue",
     ("drafts", "posts", "own_posts", "queue_items", "queue_slots", "media_assets", "viral_templates",
      "creator_identity", "creator_positions", "creator_education", "creator_skills", "creator_accounts")),
    ("readings", "Post readings", ("post_metric_observations",)),
    ("audience", "Leads and their engagement",
     ("leads", "lead_interactions", "lead_stage_events", "lead_enrichments", "reaction_folds",
      "lead_retention_keeps")),
    ("outbound", "Your comments and reactions on other posts", ("outbound_engagements",)),
    ("connections", "Connections from your LinkedIn archive", ("connections", "archive_imports")),
    ("analytics", "Daily analytics", ("analytics_daily", "audience_demographics")),
    ("logs", "Capture, health and cleanup logs",
     ("bridge_heartbeats", "captures", "schema_drift_events", "retention_log", "generation_tasks",
      "self_import_requests", "internal_sheet_issues", "gstack_backlog")),
    ("help", "Help search index", ("docs_index",)),
    ("settings", "Settings", ("settings",)),
)


def _category_of(table: str) -> str:
    if table.startswith("docs_index"):
        return "help"  # the FTS table and its shadow tables
    for key, _label, tables in CATEGORIES:
        if table in tables:
            return key
    return "other"


def _folder_bytes(folder: str) -> Optional[int]:
    if not os.path.isdir(folder):
        return 0
    total = 0
    for dirpath, _, filenames in os.walk(folder):
        for name in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return total


def sizes() -> Dict[str, Any]:
    """
    Bytes per category inside the database (dbstat), and the files beside it.

    dbstat is not in every SQLite build. Without it each category's size is
    None, "not measured", and the file sizes are still real.
    """
    conn = get_db()
    try:
        owner = {r[0]: r[1] for r in conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type IN ('table', 'index')")}
        per_category: Dict[str, Optional[int]] = {key: 0 for key, _, _ in CATEGORIES}
        per_category["other"] = 0
        measured = True
        try:
            for name, size in conn.execute("SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"):
                table = owner.get(name, name)
                category = _category_of(table)
                per_category[category] = (per_category.get(category) or 0) + int(size or 0)
        except sqlite3.OperationalError:
            measured = False
            per_category = {key: None for key in per_category}
        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        free_pages = conn.execute("PRAGMA freelist_count").fetchone()[0]
        rows = {}
        for key, _label, tables in CATEGORIES:
            count = 0
            for table in tables:
                if table in owner and owner[table] == table:
                    count += conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            rows[key] = count
    finally:
        conn.close()

    db = paths.get_db_path()
    telemetry = os.path.join(paths.get_data_dir(), TELEMETRY_DB_FILENAME)
    labels = {key: label for key, label, _ in CATEGORIES}
    labels["other"] = "Everything else"
    return {
        "measured": measured,
        "categories": [{"key": key, "label": labels[key], "bytes": per_category.get(key),
                        "rows": rows.get(key)} for key in list(labels)],
        "database_bytes": os.path.getsize(db) if os.path.exists(db) else 0,
        "free_bytes": free_pages * page_size,
        "telemetry_bytes": os.path.getsize(telemetry) if os.path.exists(telemetry) else 0,
        "media_bytes": _folder_bytes(paths.get_assets_dir()),
        "backups_bytes": _folder_bytes(paths.get_backups_dir()),
    }


# ---------------------------------------------------------------------------
# The cleanups: preview and run
# ---------------------------------------------------------------------------

def _bytes_per_row(conn, table: str) -> Optional[float]:
    """Average bytes a row of `table` takes with its indexes, or None without dbstat."""
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE tbl_name = ?", (table,))]
        total = sum(conn.execute("SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name = ?", (n,)).fetchone()[0]
                    for n in names)
    except sqlite3.OperationalError:
        return None
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return total / count if count else None


def _estimate(per_row: Optional[float], rows: int) -> Optional[int]:
    return int(per_row * rows) if per_row is not None else None


def _telemetry_path() -> str:
    return os.path.join(paths.get_data_dir(), TELEMETRY_DB_FILENAME)


def _telemetry_connect() -> Optional[sqlite3.Connection]:
    path = _telemetry_path()
    if not os.path.exists(path):
        return None
    conn = sqlite_open.connect(path, timeout=10.0)
    conn.execute("PRAGMA busy_timeout = 5000")
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "telemetry_events" not in tables:
        conn.close()
        return None
    return conn


def _telemetry_cutoff(days: int) -> str:
    return _stamp(_now() - timedelta(days=days))


def _preview_telemetry(rule: Dict[str, str]) -> Dict[str, Any]:
    days = int(rule["telemetry_days"])
    cut = _telemetry_cutoff(days)
    conn = _telemetry_connect()
    if conn is None:
        return {"job": "telemetry", "rows": 0, "bytes": 0, "older_than_days": days, "total_rows": 0}
    try:
        events = conn.execute("SELECT COUNT(*) FROM telemetry_events WHERE created_at < ?", (cut,)).fetchone()[0]
        dwell = conn.execute("SELECT COUNT(*) FROM post_dwell_metrics WHERE created_at < ?", (cut,)).fetchone()[0] \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'post_dwell_metrics'").fetchone() else 0
        total = conn.execute("SELECT COUNT(*) FROM telemetry_events").fetchone()[0]
    finally:
        conn.close()
    size = os.path.getsize(_telemetry_path())
    return {"job": "telemetry", "rows": events + dwell, "older_than_days": days, "total_rows": total,
            "bytes": int(size * events / total) if total else 0}


def _run_telemetry(rule: Dict[str, str]) -> int:
    cut = _telemetry_cutoff(int(rule["telemetry_days"]))
    conn = _telemetry_connect()
    if conn is None:
        return 0
    removed = 0
    try:
        tables = ["telemetry_events"]
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'post_dwell_metrics'").fetchone():
            tables.append("post_dwell_metrics")
        for table in tables:
            while True:
                with conn:
                    done = conn.execute(
                        f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE created_at < ? LIMIT ?)",
                        (cut, BATCH)).rowcount
                removed += done
                if done < BATCH:
                    break
    finally:
        conn.close()
    return removed


_READINGS_TO_ROLL_UP = """
    SELECT id, activity_urn FROM (
        SELECT id, activity_urn, observed_hour, age_hours,
               ROW_NUMBER() OVER (PARTITION BY activity_urn, source, substr(observed_hour, 1, 10)
                                  ORDER BY observed_hour DESC, observed_at DESC, id DESC) AS rank_in_day
        FROM post_metric_observations
    )
    WHERE rank_in_day > 1 AND observed_hour < ?
      AND NOT (age_hours IS NOT NULL AND age_hours BETWEEN ? AND ?)
"""


def _readings_cutoff(days: int) -> str:
    """Readings from before this hour (observed_hour, UTC) are rolled up."""
    return (_now() - timedelta(days=days)).strftime("%Y-%m-%dT%H")


def _readings_to_roll_up(conn, rule: Dict[str, str]) -> List[tuple]:
    """
    Every reading the roll-up removes: from before the cutoff, not the last of
    its post's day for its source, and not inside Today's comparison window.

    Kept, so every screen reads what it read before: the last reading of each
    day (so the latest reading of every post), every reading at 36 to 72 hours
    old (Today compares posts at two days old, picking the reading closest to
    48 hours from that window), and at least one reading of each post from
    each source (Today asks whether a post's own analytics page was read).
    """
    cut = _readings_cutoff(int(rule["readings_days"]))
    return [(r[0], r[1]) for r in conn.execute(_READINGS_TO_ROLL_UP, (cut, *COMPARE_WINDOW))]


def _preview_readings(rule: Dict[str, str]) -> Dict[str, Any]:
    conn = get_db()
    try:
        ids = _readings_to_roll_up(conn, rule)
        total = conn.execute("SELECT COUNT(*) FROM post_metric_observations").fetchone()[0]
        posts = len({urn for _, urn in ids})
        per_row = _bytes_per_row(conn, "post_metric_observations")
    finally:
        conn.close()
    return {"job": "readings", "rows": len(ids), "total_rows": total, "posts": posts,
            "older_than_days": int(rule["readings_days"]), "bytes": _estimate(per_row, len(ids)),
            "compare_window_hours": list(COMPARE_WINDOW)}


def _delete_ids(table: str, ids: List[int]) -> int:
    removed = 0
    conn = get_db()
    try:
        for start in range(0, len(ids), BATCH):
            chunk = ids[start:start + BATCH]
            with conn:
                removed += conn.execute(
                    f"DELETE FROM {table} WHERE id IN ({','.join('?' for _ in chunk)})", chunk).rowcount
    finally:
        conn.close()
    return removed


def _run_readings(rule: Dict[str, str]) -> int:
    conn = get_db()
    try:
        ids = [reading_id for reading_id, _ in _readings_to_roll_up(conn, rule)]
    finally:
        conn.close()
    return _delete_ids("post_metric_observations", ids)


_FOLDABLE = ("FROM lead_interactions WHERE interaction_type = 'LIKE' "
             "AND COALESCE(last_seen_at, first_seen_at, interacted_at) < ?")


def _fold_cutoff() -> str:
    return _stamp(_now() - timedelta(days=REACTION_FOLD_DAYS))


def _preview_reactions(rule: Dict[str, str]) -> Dict[str, Any]:
    cut = _fold_cutoff()
    conn = get_db()
    try:
        rows, posts, people = conn.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT COALESCE(post_urn, '')), COUNT(DISTINCT lead_id) {_FOLDABLE}",
            (cut,)).fetchone()
        # People whose every recorded engagement is a reaction being folded:
        # they stay as leads, with nothing captured left to show.
        left_empty = conn.execute(
            f"SELECT COUNT(*) FROM (SELECT DISTINCT lead_id {_FOLDABLE}) f WHERE NOT EXISTS ("
            "SELECT 1 FROM lead_interactions i WHERE i.lead_id = f.lead_id AND NOT ("
            "i.interaction_type = 'LIKE' AND COALESCE(i.last_seen_at, i.first_seen_at, i.interacted_at) < ?))",
            (cut, cut)).fetchone()[0]
        comments = conn.execute("SELECT COUNT(*) FROM lead_interactions WHERE interaction_type = 'COMMENT'").fetchone()[0]
        per_row = _bytes_per_row(conn, "lead_interactions")
    finally:
        conn.close()
    return {"job": "reactions", "rows": rows, "posts": posts if rows else 0, "people": people,
            "people_left_without_engagement": left_empty, "comments_kept": comments,
            "older_than_days": REACTION_FOLD_DAYS, "bytes": _estimate(per_row, rows)}


def _run_reactions(rule: Dict[str, str]) -> int:
    """
    Folds reactions older than 24 months into reaction_folds, batch by batch.

    Each batch adds its counts and deletes its rows in one transaction, so a
    reaction is counted exactly once whatever stops the run.
    """
    cut = _fold_cutoff()
    removed, after = 0, 0
    conn = get_db()
    try:
        while True:
            batch = conn.execute(
                f"SELECT id, COALESCE(post_urn, '') AS post, COALESCE(last_seen_at, first_seen_at, interacted_at) AS at "
                f"{_FOLDABLE} AND id > ? ORDER BY id LIMIT ?", (cut, after, BATCH)).fetchall()
            if not batch:
                break
            counts: Dict[str, List[Any]] = {}
            for row in batch:
                entry = counts.setdefault(row["post"], [0, ""])
                entry[0] += 1
                entry[1] = max(entry[1], row["at"] or "")
            with conn:
                for post, (count, through) in counts.items():
                    conn.execute(
                        "INSERT INTO reaction_folds (post_urn, reactions, folded_through, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(post_urn) DO UPDATE SET reactions = reaction_folds.reactions + excluded.reactions, "
                        "folded_through = MAX(COALESCE(reaction_folds.folded_through, ''), excluded.folded_through), "
                        "updated_at = excluded.updated_at",
                        (post, count, through, _stamp()))
                ids = [row["id"] for row in batch]
                removed += conn.execute(
                    f"DELETE FROM lead_interactions WHERE id IN ({','.join('?' for _ in ids)})", ids).rowcount
            after = batch[-1]["id"]
    finally:
        conn.close()
    return removed


_PREVIEWS = {"telemetry": _preview_telemetry, "readings": _preview_readings, "reactions": _preview_reactions}
_RUNS = {"telemetry": _run_telemetry, "readings": _run_readings, "reactions": _run_reactions}


def preview(job: str) -> Dict[str, Any]:
    """What `job` would remove now, without removing anything."""
    if job not in _PREVIEWS:
        raise RetentionRefused(f"there is no cleanup called {job!r}")
    current = rules()
    out = _PREVIEWS[job](current)
    switch = _JOB_SWITCH.get(job)
    out["state"] = current[switch] if switch else "on"
    return out


def folded_reactions() -> Dict[str, int]:
    """Reactions folded per post: {post_urn: count}. A post with none is absent."""
    conn = get_db()
    try:
        return {r[0]: r[1] for r in conn.execute("SELECT post_urn, reactions FROM reaction_folds")}
    finally:
        conn.close()


def _backup_first(backup: Optional[str]) -> str:
    """
    The verified backup a cleanup runs behind: the one given, else one made in
    the last hour that holds the studio as it is now, else a new one, which
    is then rotated with the rest so cleanups do not pile up full copies.
    """
    if backup and os.path.exists(backup):
        return backup
    reused = support.reusable_backup(REUSE_BACKUP_WITHIN)
    if reused:
        return reused
    made = support.create_backup("pre_cleanup")
    support.rotate_backups()
    return made


@_taking_turns
def run(job: str, backup: Optional[str] = None, confirmed: bool = True) -> Dict[str, Any]:
    """
    Runs one cleanup now, behind a verified backup, and logs it.

    For readings and reactions this is the creator confirming the preview, so
    it also switches the rule on: from now on the daily run does it too. With
    nothing to remove, no backup is taken.
    """
    if job not in _RUNS:
        raise RetentionRefused(f"there is no cleanup called {job!r}")
    started = _now()
    switch = _JOB_SWITCH.get(job)
    if switch and confirmed:
        conn = get_db()
        try:
            with conn:
                _write_setting(conn, RULES[switch]["key"], "on")
        finally:
            conn.close()
    if not _PREVIEWS[job](rules())["rows"]:
        _log(job, started, "nothing to do")
        return {"job": job, "removed": 0, "backup": None, "free_bytes": sizes()["free_bytes"]}
    try:
        backup = _backup_first(backup)
    except Exception as error:
        _log(job, started, "not run: the backup before it failed", detail={"error": str(error)})
        raise RetentionRefused(f"Nothing was removed: the backup taken first failed ({error}).") from error
    try:
        removed = _RUNS[job](rules())
    except Exception as error:
        _log(job, started, "stopped", backup=backup, detail={"error": str(error)})
        raise
    _log(job, started, "done", removed=removed, backup=backup)
    return {"job": job, "removed": removed, "backup": os.path.basename(backup), "free_bytes": sizes()["free_bytes"]}


# ---------------------------------------------------------------------------
# Leads silent for 24 months: a review list, never automatic
# ---------------------------------------------------------------------------

_SILENT_LEADS = """
    SELECT * FROM (
        SELECT l.id, COALESCE(l.full_name, l.name) AS name, l.headline, l.company, l.created_at,
               COALESCE(s.interactions, 0) AS interactions,
               MAX(COALESCE(s.last_at, ''), COALESCE(l.updated_at, ''), COALESCE(l.created_at, '')) AS last_activity
        FROM leads l
        LEFT JOIN (
            SELECT lead_id, COUNT(*) AS interactions,
                   MAX(COALESCE(last_seen_at, first_seen_at, interacted_at)) AS last_at
            FROM lead_interactions GROUP BY lead_id
        ) s ON s.lead_id = l.id
        WHERE COALESCE(l.lead_status, 'NEW') = 'NEW'
          AND COALESCE(TRIM(l.notes), '') = ''
          AND NOT EXISTS (SELECT 1 FROM lead_stage_events e WHERE e.lead_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM lead_enrichments x WHERE x.lead_id = l.id)
          AND NOT EXISTS (SELECT 1 FROM lead_retention_keeps k WHERE k.lead_id = l.id)
    )
    WHERE last_activity < ?
    ORDER BY last_activity, id
"""


def _silent_leads(conn) -> List[Dict[str, Any]]:
    cut = _stamp(_now() - timedelta(days=LEAD_SILENT_DAYS))
    return [dict(r) for r in conn.execute(_SILENT_LEADS, (cut,))]


def review_list(limit: int = 200) -> Dict[str, Any]:
    """
    Leads the creator never acted on, silent for 24 months: still New, no
    notes, no stage change, no enrichment, not kept, and nothing recorded
    from them since. Listed so the creator can choose; nothing is removed.
    """
    conn = get_db()
    try:
        leads = _silent_leads(conn)
        state = rules(conn)["lead_review"]
    finally:
        conn.close()
    return {"count": len(leads), "silent_days": LEAD_SILENT_DAYS, "state": state,
            "leads": leads[:max(1, min(int(limit), 1000))]}


def _ids(lead_ids: Any) -> List[str]:
    if not isinstance(lead_ids, list) or not lead_ids:
        raise RetentionRefused("name the people to forget or keep")
    return list(dict.fromkeys(str(i) for i in lead_ids[:5000]))


def keep_leads(lead_ids: Any) -> Dict[str, Any]:
    """The creator keeps these people: they leave the review list for good."""
    chosen = _ids(lead_ids)
    conn = get_db()
    try:
        with conn:
            kept = 0
            for lead_id in chosen:
                if conn.execute("SELECT 1 FROM leads WHERE id = ?", (lead_id,)).fetchone():
                    kept += conn.execute(
                        "INSERT OR IGNORE INTO lead_retention_keeps (lead_id, kept_at) VALUES (?, ?)",
                        (lead_id, _stamp())).rowcount
    finally:
        conn.close()
    return {"kept": kept}


def _backup_disclosure(forgotten_at: datetime) -> Dict[str, Any]:
    """What the creator is told about the copies of forgotten people in backups."""
    found = support._backups_by_kind()
    automatic = len(found["automatic"])
    yours = len([1 for _, path in found["zip"]
                 if support._ZIP_NAME.match(os.path.basename(path)).group("label") not in support.AUTOMATIC_BACKUP_LABELS])
    copies = sum(len(v) for k, v in found.items() if k.startswith("copy:"))
    return {
        "automatic_backups": automatic,
        "your_backups": yours,
        "database_copies": copies,
        "automatic_gone_by": (forgotten_at + timedelta(days=support.ROTATION_REACH_DAYS)).date().isoformat(),
    }


@_taking_turns
def forget_leads(lead_ids: Any) -> Dict[str, Any]:
    """
    Forgets the chosen people from the review list, behind a verified backup.

    Each one is checked again first: someone who engaged, or whom the creator
    acted on, since the list was shown is kept. Forgetting goes through the
    one removal path every other forget uses (crm.purge_lead), whose trigger
    holds their ids until the creator chooses whether to remove them from
    backups too, which only those ids make possible.
    """
    chosen = _ids(lead_ids)
    started = _now()
    conn = get_db()
    try:
        eligible = {lead["id"] for lead in _silent_leads(conn)}
    finally:
        conn.close()
    doomed = [lead_id for lead_id in chosen if lead_id in eligible]
    if not doomed:
        return {"forgotten": 0, "kept_since": len(chosen), "backup": None, "backups": _backup_disclosure(started)}
    try:
        backup = _backup_first(None)
    except Exception as error:
        _log("forget_silent_leads", started, "not run: the backup before it failed", detail={"error": str(error)})
        raise RetentionRefused(f"Nobody was forgotten: the backup taken first failed ({error}).") from error

    forgotten = 0
    for lead_id in doomed:
        if reverse_crm.purge_lead(lead_id)["lead_deleted"]:
            forgotten += 1
    conn = get_db()
    try:
        # The freed pages are zeroed (secure_delete); this puts them back into
        # the database file now rather than at the next checkpoint.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    _log("forget_silent_leads", started, "done", removed=forgotten, backup=backup)
    return {"forgotten": forgotten, "kept_since": len(chosen) - len(doomed), "backup": os.path.basename(backup),
            "backups": _backup_disclosure(started), "free_bytes": sizes()["free_bytes"]}


# ---------------------------------------------------------------------------
# Removing forgotten people from backups too
# ---------------------------------------------------------------------------

def _scrub_pending(conn) -> List[str]:
    """
    Everyone forgotten, by any path, since the creator last chose: the
    lead_forgotten trigger notes each id in forgotten_in_backups, and a
    person who engages again is taken off it (migration 20).
    """
    return [r[0] for r in conn.execute("SELECT lead_id FROM forgotten_in_backups ORDER BY forgotten_at")]


def scrub_pending() -> Dict[str, Any]:
    conn = get_db()
    try:
        people, since = conn.execute("SELECT COUNT(*), MIN(forgotten_at) FROM forgotten_in_backups").fetchone()
    finally:
        conn.close()
    return {"people": people, "since": since}


def _clear_pending(lead_ids: List[str]) -> None:
    conn = get_db()
    try:
        with conn:
            conn.executemany("DELETE FROM forgotten_in_backups WHERE lead_id = ?", [(i,) for i in lead_ids])
    finally:
        conn.close()


def _scrub_database(path: str, lead_ids: List[str]) -> bool:
    """Removes the people from one database file in place. True when any were there."""
    conn = sqlite_open.connect(path)
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "leads" not in tables:
            return False
        # A temporary table, not one ? per id: thousands may be forgotten at once.
        conn.execute("CREATE TEMP TABLE scrub_ids (id TEXT PRIMARY KEY)")
        conn.executemany("INSERT OR IGNORE INTO temp.scrub_ids VALUES (?)", [(i,) for i in lead_ids])
        chosen = "(SELECT id FROM temp.scrub_ids)"
        present = conn.execute(f"SELECT COUNT(*) FROM leads WHERE id IN {chosen}").fetchone()[0]
        if "lead_interactions" in tables:
            present += conn.execute(f"SELECT COUNT(*) FROM lead_interactions WHERE lead_id IN {chosen}").fetchone()[0]
        if not present:
            return False
        with conn:
            # Explicitly, table by table: an older backup may predate the trigger.
            for table in ("lead_interactions", "lead_stage_events", "lead_enrichments", "lead_retention_keeps"):
                if table in tables:
                    conn.execute(f"DELETE FROM {table} WHERE lead_id IN {chosen}")
            conn.execute(f"DELETE FROM leads WHERE id IN {chosen}")
            # The copy's own trigger noted them; that list belongs to the live studio only.
            if "forgotten_in_backups" in tables:
                conn.execute(f"DELETE FROM forgotten_in_backups WHERE lead_id IN {chosen}")
        conn.execute("VACUUM")
        verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if verdict != "ok":
            raise sqlite3.DatabaseError(f"the rewritten copy failed its check ({verdict})")
        return True
    finally:
        conn.close()


def _scrub_one(path: str, lead_ids: List[str], work: str) -> str:
    """'rewritten', 'unchanged' or raises. The original stays until its replacement has passed its checks."""
    times = (os.path.getatime(path), os.path.getmtime(path))
    staged_db = os.path.join(work, "copy.db")
    if path.endswith(".db"):
        shutil.copyfile(path, staged_db)
        if not _scrub_database(staged_db, lead_ids):
            return "unchanged"
        replacement = staged_db
    else:
        with zipfile.ZipFile(path) as source:
            if "data/linkedin_studio.db" not in source.namelist():
                return "unchanged"
            with source.open("data/linkedin_studio.db") as handle, open(staged_db, "wb") as out:
                shutil.copyfileobj(handle, out, 1024 * 1024)
            if not _scrub_database(staged_db, lead_ids):
                return "unchanged"
            replacement = os.path.join(work, "copy.zip")
            with zipfile.ZipFile(replacement, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as out:
                for info in source.infolist():
                    if info.filename == "data/linkedin_studio.db":
                        out.write(staged_db, info.filename, compress_type=zipfile.ZIP_DEFLATED)
                    elif info.filename == "backup_manifest.json":
                        try:
                            manifest = json.loads(source.read(info).decode("utf-8"))
                        except ValueError:
                            manifest = {}
                        if isinstance(manifest, dict):
                            manifest.setdefault("forgotten_people_removed", []).append(
                                {"at": _stamp(), "people": len(lead_ids)})
                        out.writestr(info, json.dumps(manifest, indent=2, default=str))
                    else:
                        with source.open(info) as handle:
                            out.writestr(info, handle.read(), compress_type=info.compress_type)
        support._read_back(replacement, with_database=True)
    os.utime(replacement, times)
    os.replace(replacement, path)
    return "rewritten"


@_taking_turns
def scrub_backups() -> Dict[str, Any]:
    """
    Removes the people forgotten since the last scrub from every backup and
    database copy in this profile's backups folder, then forgets their ids.

    Each file is rewritten beside itself, checked (integrity_check, then the
    archive read back), and only then put in the original's place, with the
    original's time, so rotation still sees it as the day it was made.
    """
    started = _now()
    conn = get_db()
    try:
        lead_ids = _scrub_pending(conn)
    finally:
        conn.close()
    result = {"rewritten": 0, "unchanged": 0, "failed": []}
    if not lead_ids:
        return result
    directory = paths.get_backups_dir()
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        is_copy = support._COPY_NAME.match(name) and not name.startswith("linkedin_studio_snapshot_")
        if not os.path.isfile(path) or not (support._ZIP_NAME.match(name) or is_copy):
            continue
        work = tempfile.mkdtemp(prefix=".scrub-", dir=directory)
        try:
            result[_scrub_one(path, lead_ids, work)] += 1
        except Exception as error:
            result["failed"].append({"name": name, "error": str(error)})
        finally:
            shutil.rmtree(work, ignore_errors=True)
    if not result["failed"]:
        _clear_pending(lead_ids)
    _log("remove_from_backups", started, "done" if not result["failed"] else "partly done",
         removed=len(lead_ids), detail=result)
    return result


def leave_backups() -> Dict[str, Any]:
    """The creator chose to let rotation remove them: the held ids are dropped."""
    conn = get_db()
    try:
        _clear_pending(_scrub_pending(conn))
    finally:
        conn.close()
    return scrub_pending()


# ---------------------------------------------------------------------------
# Compacting: offered, never forced
# ---------------------------------------------------------------------------

@_taking_turns
def compact() -> Dict[str, Any]:
    """
    VACUUM, so the space freed by forgetting and by cleanups leaves the file,
    and with it any bytes freed before secure_delete was on.

    Refused without twice the database's size free on its drive, because a
    VACUUM writes a full new copy before it lets the old one go.
    """
    db = paths.get_db_path()
    before = os.path.getsize(db)
    free_disk = shutil.disk_usage(os.path.dirname(db)).free
    if free_disk < 2 * before:
        raise RetentionRefused(
            f"Compacting needs about {2 * before // 1_000_000} MB free on this drive and "
            f"{free_disk // 1_000_000} MB is. Nothing was changed.")
    started = _now()
    conn = get_db()
    try:
        conn.execute("VACUUM")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    telemetry = _telemetry_connect()
    if telemetry is not None:
        try:
            telemetry.execute("VACUUM")
        finally:
            telemetry.close()
    after = os.path.getsize(db)
    _log("compact", started, "done", detail={"before_bytes": before, "after_bytes": after})
    return {"before_bytes": before, "after_bytes": after}


# ---------------------------------------------------------------------------
# The daily run
# ---------------------------------------------------------------------------

def _record_backup(result: Dict[str, Any]) -> None:
    conn = get_db()
    try:
        with conn:
            _write_setting(conn, LAST_BACKUP_KEY, json.dumps({k: v for k, v in result.items() if k != "rotation"},
                                                             default=str))
    finally:
        conn.close()


def last_daily_backup() -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        value = _read_setting(conn, LAST_BACKUP_KEY)
    finally:
        conn.close()
    try:
        parsed = json.loads(value) if value else None
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def run_daily() -> Dict[str, Any]:
    """
    The active profile's daily work: the backup if one is due, then rotation,
    then each cleanup that is on and has something to remove.

    A cleanup never runs without a verified backup behind it. When the daily
    backup fails, nothing is removed that day.
    """
    try:
        with support.maintenance_turn():
            return _run_daily()
    except support.MaintenanceBusy as busy:
        _log("daily_backup", _now(), f"skipped: {busy}; tried again next hour")
        return {"backup": None, "jobs": {}, "skipped": str(busy)}


def _run_daily() -> Dict[str, Any]:
    report: Dict[str, Any] = {"backup": None, "jobs": {}, "skipped": None}
    current = rules()
    backup_path = None
    if current["daily_backup"] == "on":
        started = _now()
        made = support.run_daily_backup()
        if made is not None and made.get("skipped"):
            _log("daily_backup", started, f"skipped: {made['skipped']}; tried again next hour")
            report["skipped"] = made["skipped"]
            return report
        if made is not None:
            _record_backup(made)
            _log("daily_backup", started, "done" if made["ok"] else "failed",
                 removed=len((made.get("rotation") or {}).get("removed", [])),
                 backup=made.get("archive"), detail={"error": made.get("error"), "rotation": made.get("rotation")})
            report["backup"] = made
            if not made["ok"]:
                return report
            backup_path = made["archive"]
    if backup_path is None:
        # No backup was due: a checked one from within the day holds everything
        # a cleanup can remove, all of which is at least 30 days old, unless a
        # restore came after it (reusable_backup leaves those out).
        backup_path = support.reusable_backup(support.DAILY_BACKUP_EVERY)
    for job in JOBS:
        switch = _JOB_SWITCH.get(job)
        if switch and current[switch] != "on":
            report["jobs"][job] = "waiting for you" if current[switch] == "ask" else "off"
            continue
        try:
            if not _PREVIEWS[job](current)["rows"]:
                report["jobs"][job] = "nothing to do"
                continue
            result = run(job, backup=backup_path, confirmed=False)
            if result["backup"]:
                backup_path = os.path.join(paths.get_backups_dir(), result["backup"])
            report["jobs"][job] = f"removed {result['removed']}"
        except Exception as error:
            logger.warning("Retention %s failed.", job, exc_info=True)
            report["jobs"][job] = f"failed: {error}"
    return report


def run_for_every_profile() -> List[Dict[str, Any]]:
    """
    The scheduled job: run_daily for every profile the studio can open whose
    database is at this build's schema. Start-up brings every profile's
    database up to date; one that is not is left alone, never migrated here.
    """
    # Off only where INOX_SCHEDULED_MAINTENANCE says so (tests/conftest.py):
    # an app started by a test would otherwise back up into that test's home.
    if os.environ.get("INOX_SCHEDULED_MAINTENANCE") == "off":
        return []
    reports = []
    for profile_id in paths.profile_ids():
        try:
            database = os.path.join(paths.get_profile_home(profile_id), "data", paths.DB_FILENAME)
            if not os.path.exists(database):
                continue
            reader = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
            try:
                version = reader.execute("PRAGMA user_version").fetchone()[0]
            finally:
                reader.close()
            if version != SCHEMA_VERSION:
                continue
            with paths.using_profile(profile_id):
                reports.append({"profile_id": profile_id, **run_daily()})
        except Exception:
            logger.warning("Daily backup and retention failed for profile %s.", profile_id, exc_info=True)
    return reports


def overview() -> Dict[str, Any]:
    """Everything the Storage and privacy panel shows, in one read."""
    current = rules()
    return {
        "rules": current,
        "defaults": {name: rule["default"] for name, rule in RULES.items()},
        "options": {name: [o for o in rule["options"] if o != "ask"] for name, rule in RULES.items()},
        "sizes": sizes(),
        "backups": {**support.backup_schedule(enabled=current["daily_backup"] == "on"),
                    "last_daily": last_daily_backup(),
                    "rotation_reach_days": support.ROTATION_REACH_DAYS},
        "review": {"count": review_list(limit=1)["count"], "silent_days": LEAD_SILENT_DAYS,
                   "state": current["lead_review"]},
        "scrub": scrub_pending(),
        "fold_days": REACTION_FOLD_DAYS,
        "log": recent_log(),
    }
