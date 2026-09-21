"""
Schema Migration Ledger: Forward-Only, Transactional, Backed Up.
================================================================
Decides whether this product can ever ship an update to a stranger.

Before this module, schema evolution worked by sniffing `PRAGMA table_info` and
conditionally issuing `ALTER TABLE`. That is idempotent, which is why it worked,
but it has no concept of which version a given database is. There was no way to
answer "can this build safely open that file", which is the only question that
matters when the file is on a machine nobody can reach.

The model:

  - `PRAGMA user_version` is the database's schema version. SQLite reserves it
    for applications and never interprets it.
  - Version 1 is the BASELINE: the schema produced by `database.init_db()` as it
    stood when the ledger was adopted. Existing databases already have that
    schema, so adopting the ledger only stamps them, it does not rebuild them.
  - Every later change is a numbered entry in MIGRATIONS. Entries are immutable
    once shipped. Editing one that a user has already applied means their
    database and the ledger disagree forever.
  - Each migration and its version bump commit in ONE transaction. A failure
    rolls back both, so a database is never left at a version it does not match.
  - A timestamped backup is taken before the first migration of any run.
  - A database newer than this build is refused rather than opened, which
    protects the user who installs an update and then rolls back.

Strict Invariants:
- Zero em-dashes in any code, docstring, or comment.
- Never edit a shipped migration. Add a new one.
- Never put schema changes in init_db() again. They belong here.
"""

import os
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

try:
    from .paths import get_backups_dir, get_db_path
except ImportError:
    from paths import get_backups_dir, get_db_path

# The schema as produced by init_db() at the moment the ledger was adopted.
# Databases created before the ledger existed already match this, so they are
# stamped rather than migrated.
BASELINE_VERSION = 1

# Oldest schema this build knows how to bring forward. Raise this only when
# dropping support for very old databases, and say so in the changelog.
MIN_SUPPORTED_SCHEMA = 1

def _migrate_inspirations(cursor: sqlite3.Cursor) -> None:
    """
    Migration 2:
    Migrates legacy inspirations records into viral_templates,
    then drops the inspirations table to eliminate third-party
    scraping liabilities and enforce structural blueprint curation.
    """
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
    if not cursor.fetchone():
        return

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS viral_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archetype TEXT NOT NULL,
        hook_text TEXT NOT NULL,
        velocity_score REAL DEFAULT 0.0,
        engagement_multiplier TEXT,
        pacing_style TEXT,
        example_post_id TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("SELECT topic, key_hook, content, likes_count, comments_count, id FROM inspirations")
    rows = cursor.fetchall()
    for row in rows:
        topic = (row[0] or "General").replace("\u2014", " - ")
        hook = (row[1] or (row[2].split("\n")[0] if row[2] else "Structural Hook")).replace("\u2014", " - ")
        cursor.execute("SELECT id FROM viral_templates WHERE hook_text = ?", (hook,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO viral_templates (
                archetype, hook_text, velocity_score, engagement_multiplier,
                pacing_style, example_post_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (topic, hook, 8.5, "2.5x", "Legacy specimen structure", f"migrated-{row[5]}"))

    cursor.execute("DROP TABLE IF EXISTS inspirations")


def _migrate_internal_sheet(cursor: sqlite3.Cursor) -> None:
    """
    Migration 3:
    Creates internal_sheet_issues table for in-app visual screen concept
    identification, bug reporting, and zero-egress internal sheet tracking.
    """
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS internal_sheet_issues (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_selector TEXT NOT NULL,
        element_tag TEXT,
        element_id TEXT,
        element_classes TEXT,
        element_text_snippet TEXT,
        tab_name TEXT NOT NULL DEFAULT 'composer',
        page_route TEXT DEFAULT '/',
        category TEXT NOT NULL DEFAULT 'bug' CHECK(category IN ('bug', 'concept', 'ux_glitch', 'copy_slop', 'data_mismatch', 'feature_request')),
        severity TEXT NOT NULL DEFAULT 'medium' CHECK(severity IN ('low', 'medium', 'high', 'critical')),
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        suggested_role TEXT DEFAULT 'ENGINEERING_MANAGER' CHECK(suggested_role IN ('CEO', 'ENGINEERING_MANAGER', 'DESIGNER', 'QA_LEAD', 'CSO', 'RELEASE_MANAGER')),
        status TEXT DEFAULT 'OPEN' CHECK(status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'WONT_FIX')),
        bounding_box TEXT,
        viewport_resolution TEXT,
        dom_path TEXT,
        gstack_task_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        resolved_at TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_sheet_status ON internal_sheet_issues(status, severity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_sheet_tab ON internal_sheet_issues(tab_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_internal_sheet_category ON internal_sheet_issues(category)")


def _migrate_provenance(cursor: sqlite3.Cursor) -> None:
    """
    Migration 4:
    Adds a provenance column to the two tables that hold observations about the
    creator's account.

    Until now nothing distinguished a row captured from LinkedIn from a row
    generated by the demo seeder, so a chart drawn from fabricated numbers was
    pixel-identical to one drawn from real capture. Three values are meaningful:

      'observed'  read from a page the creator loaded
      'seed'      generated by the demo seeder, never real
      NULL        written before this column existed, provenance unknown

    Existing rows are deliberately left NULL rather than guessed at. This
    database cannot know which of its rows were seeded, and inventing a
    classification here would repeat the exact mistake the column exists to
    prevent.
    """
    for table in ("analytics_daily", "audience_demographics"):
        cursor.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in cursor.fetchall()}
        if "source" not in columns:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT")


def _migrate_observation_window(cursor: sqlite3.Cursor) -> None:
    """
    Migration 5:
    Records which period an analytics row covers, and how precisely it was read.

    analytics_daily was keyed by date alone, with the column names promising a
    daily figure. The extension wrote whatever the creator's range selector
    happened to be showing, so a 28 day impressions total was stored as today's
    impressions and then summed across overlapping windows by the dashboard. No
    stored field could repair that after the fact, because the period was never
    recorded in the first place.

      period_label  '1d', '7d', '28d', ... or NULL when it could not be read
      precision     'exact' for a fully written figure, 'rounded' for one
                    LinkedIn abbreviated as 1.2K, NULL when unknown

    'rounded' matters because 1.2K means somewhere in [1150, 1250). Presenting
    it later as exactly 1200 would be a second, quieter fabrication.
    """
    cursor.execute("PRAGMA table_info(analytics_daily)")
    columns = {row[1] for row in cursor.fetchall()}
    if "period_label" not in columns:
        cursor.execute("ALTER TABLE analytics_daily ADD COLUMN period_label TEXT")
    if "precision" not in columns:
        cursor.execute("ALTER TABLE analytics_daily ADD COLUMN precision TEXT")


def _migrate_capture_context(cursor: sqlite3.Cursor) -> None:
    """
    Migration 6:
    Records the page path an interaction was captured from.

    The reactor scraper matched a bare list item inside any dialog on any
    LinkedIn page, so people who had never touched a post were stored as having
    reacted to one. Without a record of where a row came from, those rows cannot
    be told apart from real ones afterwards, and the only remedy is to distrust
    the whole table.
    """
    cursor.execute("PRAGMA table_info(lead_interactions)")
    columns = {row[1] for row in cursor.fetchall()}
    if "capture_context" not in columns:
        cursor.execute("ALTER TABLE lead_interactions ADD COLUMN capture_context TEXT")


def _migrate_post_identity(cursor: sqlite3.Cursor) -> None:
    """
    Migration 7:
    Gives a post the identity LinkedIn knows it by.

    Three attribution surfaces already exist and are already correct:
    crm.py:637 joins leads to posts, app.py:516 powers the leaderboard, and
    /api/v1/analytics/posts/{id}/leads answers the question this product was
    built to answer. All three have returned zero for their entire existence,
    because posts had no column holding the URN and lead_interactions was never
    sent one.

      activity_urn        the urn:li:activity: LinkedIn assigned on publish
      content_fingerprint the opening of the text, used to recognise the post
                          on its own permalink without depending on any CSS
                          class LinkedIn can rename
      draft_id            the drafts row this came from, so authored form
                          (archetype, pre_fold_chars) can be correlated with
                          outcome

    The unique index is partial. Unbound posts are the normal state, so NULL
    must not collide with NULL.
    """
    cursor.execute("PRAGMA table_info(posts)")
    columns = {row[1] for row in cursor.fetchall()}
    if "activity_urn" not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN activity_urn TEXT")
    if "content_fingerprint" not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN content_fingerprint TEXT")
    if "draft_id" not in columns:
        cursor.execute("ALTER TABLE posts ADD COLUMN draft_id INTEGER")

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_activity_urn "
        "ON posts(activity_urn) WHERE activity_urn IS NOT NULL"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_posts_fingerprint "
        "ON posts(content_fingerprint) WHERE content_fingerprint IS NOT NULL"
    )


# Migration = (version, description, payload)
# payload is either a sequence of SQL statements or a callable taking a cursor.
# Append only. Never reorder, never edit, never delete.
Payload = Union[Sequence[str], Callable[[sqlite3.Cursor], None]]
MIGRATIONS: List[Tuple[int, str, Payload]] = [
    (2, "Migrate inspirations to viral_templates and drop inspirations table", _migrate_inspirations),
    (3, "Create internal_sheet_issues table for visual screen concept identification", _migrate_internal_sheet),
    (4, "Add provenance column to analytics_daily and audience_demographics", _migrate_provenance),
    (5, "Record observation window and precision on analytics_daily", _migrate_observation_window),
    (6, "Record capture context on lead_interactions", _migrate_capture_context),
    (7, "Give a post the activity URN and fingerprint that identify it", _migrate_post_identity),
]

SCHEMA_VERSION = BASELINE_VERSION + len(MIGRATIONS)


class SchemaTooNewError(RuntimeError):
    """The database was written by a newer build than this one."""


class SchemaTooOldError(RuntimeError):
    """The database predates the oldest schema this build can migrate."""


def get_schema_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_schema_version(cursor: sqlite3.Cursor, version: int) -> None:
    """
    PRAGMA does not accept bound parameters, so the value is interpolated.
    It is validated as an integer first, which is what makes that safe.
    """
    if not isinstance(version, int) or version < 0:
        raise ValueError(f"refusing to write a non-integer schema version: {version!r}")
    cursor.execute(f"PRAGMA user_version = {version:d}")


def _database_has_tables(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()
    return int(row[0]) > 0


def check_compatibility(conn: sqlite3.Connection) -> None:
    """
    Raises when this build must not touch the database.

    Called before any write. Refusing to start is always better than silently
    operating against a schema we do not understand.
    """
    current = get_schema_version(conn)
    if current > SCHEMA_VERSION:
        raise SchemaTooNewError(
            f"This database is at schema version {current}, but this build only "
            f"understands up to {SCHEMA_VERSION}. It was almost certainly written by a "
            f"newer version of Inox Hydra. Install the newer version again, or restore "
            f"a backup from {get_backups_dir()}."
        )
    if current != 0 and current < MIN_SUPPORTED_SCHEMA:
        raise SchemaTooOldError(
            f"This database is at schema version {current}, older than the minimum "
            f"supported version {MIN_SUPPORTED_SCHEMA}. Upgrade through an intermediate "
            f"release first."
        )


def pending_migrations(conn: sqlite3.Connection) -> List[Tuple[int, str, Payload]]:
    """Migrations this database has not yet had applied, in order."""
    current = get_schema_version(conn)
    return [m for m in MIGRATIONS if m[0] > current]


def backup_database(reason: str = "migration") -> Optional[str]:
    """
    Copies the database aside before it is altered.

    Returns the backup path, or None when there is nothing to back up yet.
    Uses the SQLite backup API so the copy is consistent even under WAL with
    other readers active, which a plain file copy cannot guarantee.
    """
    db_path = get_db_path()
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return None

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"linkedin_studio_{reason}_{stamp}.db"
    target = os.path.join(get_backups_dir(), name)

    source = sqlite3.connect(db_path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def _apply(cursor: sqlite3.Cursor, payload: Payload) -> None:
    if callable(payload):
        payload(cursor)
        return
    for statement in payload:
        cursor.execute(statement)


def ensure_schema(conn: sqlite3.Connection, take_backup: bool = True) -> Dict[str, Any]:
    """
    Brings the database up to SCHEMA_VERSION, or raises without touching it.

    Assumes the baseline DDL has already run (init_db does this), so a database
    that has tables but no version stamp is adopted at BASELINE_VERSION rather
    than being rebuilt.

    Returns a report suitable for logging and for the diagnostics bundle.
    """
    check_compatibility(conn)

    started_at = get_schema_version(conn)
    report: Dict[str, Any] = {
        "from_version": started_at,
        "to_version": started_at,
        "target_version": SCHEMA_VERSION,
        "applied": [],
        "backup_path": None,
        "baselined": False,
    }

    # Manual transaction control. The default isolation handling does not open a
    # transaction for DDL, which would let a migration commit without its
    # version bump.
    previous_isolation = conn.isolation_level
    conn.isolation_level = None
    cursor = conn.cursor()

    try:
        if started_at == 0:
            if not _database_has_tables(conn):
                # A genuinely empty file. init_db has not run yet, so there is
                # nothing to adopt. Caller is responsible for creating the schema.
                return report
            # Pre-ledger database carrying the baseline schema. Stamp it.
            cursor.execute("BEGIN IMMEDIATE")
            try:
                _set_schema_version(cursor, BASELINE_VERSION)
                cursor.execute("COMMIT")
            except Exception:
                cursor.execute("ROLLBACK")
                raise
            report["baselined"] = True
            report["to_version"] = BASELINE_VERSION

        outstanding = pending_migrations(conn)
        if not outstanding:
            report["to_version"] = get_schema_version(conn)
            return report

        if take_backup:
            report["backup_path"] = backup_database("premigration")

        for version, description, payload in outstanding:
            cursor.execute("BEGIN IMMEDIATE")
            try:
                _apply(cursor, payload)
                _set_schema_version(cursor, version)
                cursor.execute("COMMIT")
            except Exception as exc:
                cursor.execute("ROLLBACK")
                raise RuntimeError(
                    f"Migration {version} ({description}) failed and was rolled back. "
                    f"The database is still at version {get_schema_version(conn)}. "
                    f"A backup was saved to {report['backup_path']}. Original error: {exc}"
                ) from exc
            report["applied"].append({"version": version, "description": description})
            report["to_version"] = version

        return report
    finally:
        conn.isolation_level = previous_isolation


def describe(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Schema status for the diagnostics bundle and the status endpoint."""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(get_db_path())
        should_close = True
    try:
        current = get_schema_version(conn)
        return {
            "current_version": current,
            "target_version": SCHEMA_VERSION,
            "baseline_version": BASELINE_VERSION,
            "min_supported_version": MIN_SUPPORTED_SCHEMA,
            "pending": [{"version": v, "description": d} for v, d, _ in pending_migrations(conn)],
            "up_to_date": current == SCHEMA_VERSION,
            "too_new": current > SCHEMA_VERSION,
        }
    finally:
        if should_close:
            conn.close()
