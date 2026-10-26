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
    from . import sqlite_open
except ImportError:
    from paths import get_backups_dir, get_db_path
    import sqlite_open

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


def _migrate_template_provenance(cursor: sqlite3.Cursor) -> None:
    """
    Migration 9:
    Records where a swipe specimen came from.

    viral_templates ships 36 rows in the box, each carrying a hook, a
    velocity score and engagement counts in the thousands. The surface drew
    them exactly as it would draw a post the creator had captured, because
    nothing on the row distinguished the two. A card reading 9,800 REACTIONS
    was a number no one measured, presented as one someone had.

    analytics_daily learned this lesson at migration 4 and the swipe file did
    not, so the same product held two surfaces to different standards. Three
    values are meaningful:

      'shipped'   written by the offline seeder, in the box
      'synced'    pulled from a bundle feed
      'imported'  read from a bundle file the creator supplied
      NULL        written before this column existed, origin unknown

    None of the three is a post anyone measured. The table has no reaction or
    comment columns at all, which is why the endpoint that serves it reports
    neither: the counts it used to emit were computed at render time.

    Existing rows are left NULL rather than guessed at, for the same reason
    migration 4 left its own alone: this database cannot know which of its
    rows were seeded, and inventing a classification here would be the exact
    mistake the column exists to prevent.
    """
    cursor.execute("PRAGMA table_info(viral_templates)")
    columns = {row[1] for row in cursor.fetchall()}
    if "origin" not in columns:
        cursor.execute("ALTER TABLE viral_templates ADD COLUMN origin TEXT")


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


def _migrate_annotation_context(cursor: sqlite3.Cursor) -> None:
    """
    Migration 8:
    Gives an annotation everything needed to reproduce what it describes.

    Until now a record held a selector and two sentences. A selector stops
    resolving the first time somebody restyles the card it pointed at, and two
    sentences do not tell a maintainer which build, which schema, or which
    failing request was on screen when it was written.

      screen_key       the tab pane the element lived in, which survives a
                       restyle because it is an identity, not a path
      section_key      the nearest labelled region, or an 'unmapped:' marker so
                       an unlabelled area reads as a gap instead of a guess
      console_capture  the console ring buffer at the moment of capture
      network_capture  requests that failed or ran slow, same window
      breadcrumbs      the actions leading up to it, which is the part that
                       makes an intermittent bug reproducible
      env_snapshot     app version, schema version, platform
      a11y_findings    contrast, label and target size checks on the element
      repro_hash       collides when two reports describe the same failure

    All capture columns hold JSON written by devtools.normalize_capture, which
    bounds and scrubs them first. Nothing here is read by a consumer build.
    """
    cursor.execute("PRAGMA table_info(internal_sheet_issues)")
    columns = {row[1] for row in cursor.fetchall()}

    for column in (
        "screen_key",
        "section_key",
        "console_capture",
        "network_capture",
        "breadcrumbs",
        "env_snapshot",
        "a11y_findings",
        "repro_hash",
    ):
        if column not in columns:
            cursor.execute(f"ALTER TABLE internal_sheet_issues ADD COLUMN {column} TEXT")

    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_internal_sheet_screen "
        "ON internal_sheet_issues(screen_key, section_key)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_internal_sheet_repro "
        "ON internal_sheet_issues(repro_hash) WHERE repro_hash IS NOT NULL"
    )


def _migrate_creator_self(cursor: sqlite3.Cursor) -> None:
    """
    Migration 10:
    Gives the studio a record of who its creator is on LinkedIn.

    Until now every capture path read "a LinkedIn page" and never "my LinkedIn
    page", because nothing stored which member the creator is. So the profile
    page was excluded wholesale (a stranger's and the creator's look alike to
    code that does not know the difference), the creator's own posts could not
    be recognised, and the creator's likes and comments on other people's
    posts were stored as the creator being somebody's lead.

    creator_identity holds one row, the creator, with what their own profile
    shows. The candidate columns hold what a capture believes, and confirmed_at
    is set only when the creator says "yes, that is me". Every table below
    trusts a capture only once that has happened.
    """
    statements = [
        # grain: one row per install, the creator. id is always 1.
        """
        CREATE TABLE IF NOT EXISTS creator_identity (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            vanity TEXT,
            profile_url TEXT,
            display_name TEXT,
            headline TEXT,
            location TEXT,
            about TEXT,
            current_company TEXT,
            follower_count INTEGER,
            connection_count INTEGER,
            email TEXT,
            phone TEXT,
            birthday TEXT,
            websites TEXT,
            profile_observed_at TEXT,
            contact_observed_at TEXT,
            candidate_vanity TEXT,
            candidate_evidence TEXT,
            candidate_observed_at TEXT,
            confirmed_at TEXT
        )
        """,
        # grain: one row per position on the creator's profile, as last seen.
        """
        CREATE TABLE IF NOT EXISTS creator_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordinal INTEGER NOT NULL,
            title TEXT,
            company TEXT,
            date_range TEXT,
            location TEXT,
            description TEXT,
            observed_at TEXT NOT NULL
        )
        """,
        # grain: one row per education entry on the creator's profile, as last seen.
        """
        CREATE TABLE IF NOT EXISTS creator_education (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordinal INTEGER NOT NULL,
            school TEXT,
            degree TEXT,
            date_range TEXT,
            observed_at TEXT NOT NULL
        )
        """,
        # grain: one row per skill on the creator's profile, as last seen.
        """
        CREATE TABLE IF NOT EXISTS creator_skills (
            skill TEXT PRIMARY KEY,
            observed_at TEXT NOT NULL
        )
        """,
        # grain: one row per LinkedIn post the creator authored, keyed by URN.
        # Counts are the latest reading and NULL when never read, never 0.
        """
        CREATE TABLE IF NOT EXISTS own_posts (
            activity_urn TEXT PRIMARY KEY,
            text TEXT,
            published_at TEXT,
            published_at_source TEXT,
            reactions INTEGER,
            comments INTEGER,
            reposts INTEGER,
            impressions INTEGER,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        )
        """,
        # grain: one row per thing the creator did to someone else's post:
        # a reaction, or one comment they wrote.
        """
        CREATE TABLE IF NOT EXISTS outbound_engagements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_activity_urn TEXT NOT NULL,
            target_author TEXT,
            target_excerpt TEXT,
            kind TEXT NOT NULL CHECK (kind IN ('reaction', 'comment')),
            reaction_kind TEXT,
            my_text TEXT,
            my_text_key TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE (target_activity_urn, kind, my_text_key)
        )
        """,
        # grain: one row per heartbeat from the browser extension. Pruned to
        # the last week on write.
        """
        CREATE TABLE IF NOT EXISTS bridge_heartbeats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seen_at TEXT NOT NULL,
            extension_version TEXT,
            page_kind TEXT
        )
        """,
        # grain: one row per history import the creator asked for.
        """
        CREATE TABLE IF NOT EXISTS self_import_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('posts', 'comments', 'reactions')),
            requested_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            items_seen INTEGER,
            outcome TEXT
        )
        """,
    ]
    for statement in statements:
        cursor.execute(statement)


INTERACTION_PLACEHOLDERS = ("reacted to post on linkedin", "commented on post")


def interaction_comment_key(comment_text) -> str:
    """
    What makes one comment the same comment when it is read again.

    Whitespace and case are normalised, because LinkedIn re-renders both. Empty
    for a reaction, which has no words.
    """
    import hashlib

    text = " ".join((comment_text or "").split()).lower()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24] if text else ""


def _migrate_interaction_grain(cursor: sqlite3.Cursor) -> None:
    """
    Migration 11:
    One row per interaction, not one row per time the page was loaded.

    The extension re-sends what is on screen every time a post is opened, and
    every send inserted a row. So "most engaged" meant "most often reopened",
    and a creator checking the same post five times gave one commenter five
    interactions. The revisit is kept as seen_count and last_seen_at, which is
    the signal worth having, without being counted as engagement.

    It also removes the capture's placeholders. A reaction was stored with the
    comment text "Reacted to post on LinkedIn", which the interface then showed
    as words the person had written.
    """
    cursor.execute("PRAGMA table_info(lead_interactions)")
    columns = {row[1] for row in cursor.fetchall()}
    for name, ddl in (
        ("comment_key", "TEXT NOT NULL DEFAULT ''"),
        ("first_seen_at", "TIMESTAMP"),
        ("last_seen_at", "TIMESTAMP"),
        ("seen_count", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if name not in columns:
            cursor.execute(f"ALTER TABLE lead_interactions ADD COLUMN {name} {ddl}")

    placeholders = ",".join("?" for _ in INTERACTION_PLACEHOLDERS)
    cursor.execute(
        f"UPDATE lead_interactions SET comment_text = NULL "
        f"WHERE lower(trim(comment_text)) IN ({placeholders})",
        INTERACTION_PLACEHOLDERS,
    )

    rows = cursor.execute(
        "SELECT id, lead_id, COALESCE(post_urn, '') AS post_urn, interaction_type, comment_text, "
        "interacted_at FROM lead_interactions ORDER BY id"
    ).fetchall()
    groups = {}
    for row in rows:
        key = (row[1], row[2], row[3], interaction_comment_key(row[4]))
        groups.setdefault(key, []).append(row)

    for (_lead, _urn, _type, comment_key), members in groups.items():
        keep = members[0]
        seen = [m[5] for m in members if m[5]]
        cursor.execute(
            "UPDATE lead_interactions SET comment_key = ?, seen_count = ?, "
            "first_seen_at = ?, last_seen_at = ? WHERE id = ?",
            (comment_key, len(members), min(seen) if seen else None, max(seen) if seen else None, keep[0]),
        )
        for duplicate in members[1:]:
            cursor.execute("DELETE FROM lead_interactions WHERE id = ?", (duplicate[0],))

    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_interactions_grain ON lead_interactions "
        "(lead_id, COALESCE(post_urn, ''), interaction_type, comment_key)"
    )


def _migrate_capture_log(cursor: sqlite3.Cursor) -> None:
    """
    Migration 12:
    A record of each extractor run, so a broken capture is visible.

    Every capture reads LinkedIn's markup, which is undocumented and changes.
    When a selector stops matching, the extractor finds nothing and says
    nothing, and the creator sees a lead list that has gone quiet and cannot
    tell a slow week from a broken bridge. Each run now leaves a row: what it
    looked at, how much it found, and which required fields it could not read
    on a page that plainly had them.
    """
    # grain: one row per extractor run on one page view. Pruned to a week.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS captures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            extractor TEXT NOT NULL,
            page_kind TEXT,
            items_seen INTEGER,
            items_kept INTEGER,
            drift TEXT,
            extension_version TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_captures_extractor ON captures(extractor, observed_at DESC)")


def _migrate_post_metric_observations(cursor: sqlite3.Cursor) -> None:
    """
    Migration 13:
    Readings of each of the creator's posts over time, not one mutable number.

    posts.impressions and own_posts.reactions each hold one value, overwritten
    by every read, so "how did this post do by day two" could not be asked:
    the day-two figure was replaced on day three. And comparing a post read at
    six hours with one read at six weeks says nothing about either.

    Each reading is kept with when it was taken and how old the post was, so a
    post can be compared with the creator's others at the same age. Counts not
    shown on the page are NULL, never 0.
    """
    # grain: one row per reading of one post's figures. At most one per post
    # per source per hour, so re-reading a page does not multiply readings.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS post_metric_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_urn TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            observed_hour TEXT NOT NULL,
            age_hours REAL,
            source TEXT NOT NULL,
            impressions INTEGER,
            members_reached INTEGER,
            reactions INTEGER,
            comments INTEGER,
            reposts INTEGER,
            saves INTEGER,
            sends INTEGER,
            UNIQUE (activity_urn, source, observed_hour)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_post_metrics_urn ON post_metric_observations(activity_urn, observed_at)"
    )


def _migrate_lead_stage_events(cursor: sqlite3.Cursor) -> None:
    """
    Migration 14:
    A history of each lead's status, not only the latest value.

    Moving a lead from Outreach Sent to Connected overwrote the status, so the
    studio could say where a lead is but never that it had got there, when, or
    from which post. "Which of my posts brought people I ended up talking to"
    needs the history, and a conversion rate needs to know a change happened.
    """
    # grain: one row per status change of one lead.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_stage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT NOT NULL,
            changed_at TEXT NOT NULL
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_stage_events_lead ON lead_stage_events(lead_id, changed_at)")


def _migrate_schema_drift_events(cursor: sqlite3.Cursor) -> None:
    """
    Migration 15:
    Record schema drift events from Voyager network interception.

    When LinkedIn modifies their internal Voyager API response JSON structure,
    network interception records which fields could not be extracted, the
    observed schema version, and top-level response keys. This allows the studio
    to monitor API stability and serve schema patches without requiring an
    extension store re-approval.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_drift_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observed_at TEXT NOT NULL,
            schema_name TEXT NOT NULL,
            schema_version TEXT NOT NULL,
            drift_fields TEXT,
            confidence REAL,
            success INTEGER,
            source_url TEXT,
            response_top_keys TEXT,
            extension_version TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_schema_drift_name ON schema_drift_events(schema_name, observed_at DESC)")


def _migrate_creator_accounts(cursor: sqlite3.Cursor) -> None:
    """
    Migration 16:
    Create creator_accounts table for enterprise multi-tenant account switching.

    Allows managing multiple LinkedIn creator profiles within one local studio instance.
    Each profile retains its own account_id, name, headline, vanity, and active status.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creator_accounts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            vanity TEXT,
            headline TEXT,
            avatar_initials TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_default ON creator_accounts(is_default)")

    cursor.execute("SELECT COUNT(*) FROM creator_accounts WHERE id = 'default'")
    if cursor.fetchone()[0] == 0:
        name = "Default Profile"
        vanity = ""
        headline = "Creator"
        try:
            cursor.execute("SELECT display_name, vanity, headline FROM creator_identity WHERE id = 1")
            row = cursor.fetchone()
            if row and row[0]:
                name = row[0]
                vanity = row[1] or ""
                headline = row[2] or "Creator"
        except Exception:
            pass

        parts = name.split()
        initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else ""))[:2].upper() if parts else "DP"

        cursor.execute("""
            INSERT INTO creator_accounts (id, name, vanity, headline, avatar_initials, is_default)
            VALUES ('default', ?, ?, ?, ?, 1)
        """, (name, vanity, headline, initials))


def _migrate_lead_engagement_labels(cursor: sqlite3.Cursor) -> None:
    """
    Migration 17:
    A captured lead says how they actually engaged, and where their profile is.

    The capture path created leads without an engagement_type, so the schema
    default 'Commented' applied to people who had only reacted, and the first
    message draft read it: "I saw you commented on my post" to someone who had
    liked it. The same path left profile_url empty and kept the URL in
    linkedin_urn.

    Both are derived from what is already recorded, and only for leads that
    have interactions, which is every lead the capture created. A lead entered
    by hand or by a batch import has no interaction rows and keeps the label
    it was given.
    """
    cursor.execute("""
        UPDATE leads SET engagement_type = (
            SELECT CASE
                WHEN SUM(CASE WHEN li.interaction_type = 'COMMENT' THEN 1 ELSE 0 END) > 0 THEN 'Commented'
                WHEN SUM(CASE WHEN li.interaction_type = 'REPOST' THEN 1 ELSE 0 END) > 0 THEN 'Reposted'
                ELSE 'Liked'
            END
            FROM lead_interactions li WHERE li.lead_id = leads.id
        )
        WHERE EXISTS (SELECT 1 FROM lead_interactions li WHERE li.lead_id = leads.id)
    """)
    cursor.execute("""
        UPDATE leads SET profile_url = linkedin_urn
        WHERE (profile_url IS NULL OR profile_url = '')
          AND lower(COALESCE(linkedin_urn, '')) LIKE 'http%'
    """)


_MIGRATION_18_ARCHIVE = (
    # grain: one row per first-degree connection, as LinkedIn's data archive
    # lists them. Keyed by profile URL. No email column: the archive carries an
    # address only for connections who chose to share it, and nothing in the
    # product needs one.
    """
    CREATE TABLE IF NOT EXISTS connections (
        profile_url TEXT PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        company TEXT,
        position TEXT,
        connected_on TEXT,
        source TEXT NOT NULL DEFAULT 'archive',
        imported_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_connections_name ON connections(last_name, first_name)",
    # grain: one row per archive the creator imported, with what was read.
    """
    CREATE TABLE IF NOT EXISTS archive_imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        archive_name TEXT NOT NULL,
        archive_bytes INTEGER,
        imported_at TEXT NOT NULL,
        summary TEXT NOT NULL
    )
    """,
)


_MIGRATION_19_FORGET = (
    # Forgetting a lead used to leave their stage history behind:
    # lead_stage_events has no foreign key and no removal path deleted from it,
    # so the rows stayed in the database and every export, and because a lead's
    # id is a hash of their profile, reattached to them if they engaged again.
    # A trigger rather than a fix in each caller, because there are three
    # callers today and the next one should not have to remember.
    """
    CREATE TRIGGER IF NOT EXISTS lead_forgotten AFTER DELETE ON leads
    BEGIN
        DELETE FROM lead_stage_events WHERE lead_id = OLD.id;
        DELETE FROM lead_interactions WHERE lead_id = OLD.id;
        DELETE FROM lead_enrichments WHERE lead_id = OLD.id;
    END
    """,
    # What older versions left behind is about people already forgotten.
    "DELETE FROM lead_stage_events WHERE lead_id NOT IN (SELECT id FROM leads)",
    "DELETE FROM lead_interactions WHERE lead_id NOT IN (SELECT id FROM leads)",
    "DELETE FROM lead_enrichments WHERE lead_id NOT IN (SELECT id FROM leads)",
)


_MIGRATION_20_INDEXES = (
    # One post's engagers: the post's leads in Analytics, and every per-post
    # count. Without it each was a scan of every interaction (386 ms for one
    # post at 500,000 interactions).
    "CREATE INDEX IF NOT EXISTS idx_interactions_post ON lead_interactions(post_urn, lead_id)",
    # Today's people to reply to: engagements first seen in the last two
    # weeks. The expression is the one today.py filters on, so the index
    # serves it (424 ms at 500,000 interactions, from scanning every lead).
    "CREATE INDEX IF NOT EXISTS idx_interactions_engaged ON lead_interactions(COALESCE(first_seen_at, interacted_at))",
    # Statistics for the planner, once. Nothing had ever run ANALYZE, so it
    # chose plans without knowing a single table's size. PRAGMA optimize keeps
    # them current from here on (database.optimize_db).
    "ANALYZE",
)


# Migrations 21, 22 and 24 are SQL frozen here as it was written. They used
# to run post_summary's and universal_search's live code, so a later edit to
# either module would have changed what an old migration does to a database
# that upgrades through it.

# Migration 21: one summary row per post (post_summary.py), with the
# triggers that mark a row stale when anything it is computed from changes.
# Every post with engagement or readings is marked, and the summary computes
# them right after the migration run (database.init_db), and on first read.
_MIGRATION_21_SUMMARY = (
    """
    CREATE TABLE IF NOT EXISTS post_engagement (
        post_urn TEXT PRIMARY KEY,
        people INTEGER NOT NULL DEFAULT 0,
        commenters INTEGER NOT NULL DEFAULT 0,
        vip INTEGER NOT NULL DEFAULT 0,
        qualified INTEGER NOT NULL DEFAULT 0,
        icp_known INTEGER NOT NULL DEFAULT 0,
        icp_sum REAL NOT NULL DEFAULT 0,
        conversations INTEGER NOT NULL DEFAULT 0,
        folded_reactions INTEGER NOT NULL DEFAULT 0,
        people_json TEXT,
        lead_ids TEXT,
        reading_48h TEXT,
        latest_reading TEXT,
        stale INTEGER NOT NULL DEFAULT 0
    ) WITHOUT ROWID
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_added AFTER INSERT ON lead_interactions
    WHEN NEW.post_urn IS NOT NULL AND NEW.post_urn != ''
    BEGIN
        INSERT INTO post_engagement (post_urn, stale) VALUES (NEW.post_urn, 1)
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 1;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_removed AFTER DELETE ON lead_interactions
    WHEN OLD.post_urn IS NOT NULL AND OLD.post_urn != ''
    BEGIN
        UPDATE post_engagement SET stale = stale | 1 WHERE post_urn = OLD.post_urn AND (stale & 1) = 0;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_interaction_changed
    AFTER UPDATE OF post_urn, lead_id, interaction_type ON lead_interactions
    BEGIN
        UPDATE post_engagement SET stale = stale | 1 WHERE post_urn = OLD.post_urn AND (stale & 1) = 0;
        INSERT INTO post_engagement (post_urn, stale)
        SELECT NEW.post_urn, 1 WHERE NEW.post_urn IS NOT NULL AND NEW.post_urn != ''
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 1;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_lead_changed
    AFTER UPDATE OF full_name, name, icp_score, lead_status ON leads
    WHEN OLD.full_name IS NOT NEW.full_name OR OLD.name IS NOT NEW.name
      OR OLD.icp_score IS NOT NEW.icp_score OR OLD.lead_status IS NOT NEW.lead_status
    BEGIN
        UPDATE post_engagement SET stale = stale | 1
        WHERE (stale & 1) = 0 AND post_urn IN (SELECT post_urn FROM lead_interactions WHERE lead_id = NEW.id);
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_added AFTER INSERT ON post_metric_observations
    WHEN NEW.activity_urn != ''
    BEGIN
        INSERT INTO post_engagement (post_urn, stale) VALUES (NEW.activity_urn, 2)
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 2;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_changed AFTER UPDATE ON post_metric_observations
    BEGIN
        UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = OLD.activity_urn AND (stale & 2) = 0;
        INSERT INTO post_engagement (post_urn, stale)
        SELECT NEW.activity_urn, 2 WHERE NEW.activity_urn != ''
        ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 2;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS post_engagement_reading_removed AFTER DELETE ON post_metric_observations
    BEGIN
        UPDATE post_engagement SET stale = stale | 2 WHERE post_urn = OLD.activity_urn AND (stale & 2) = 0;
    END
    """,
    # Every post the summary will hold, marked for computing.
    "INSERT INTO post_engagement (post_urn, stale) SELECT DISTINCT post_urn, 1 FROM lead_interactions "
    "WHERE post_urn IS NOT NULL AND post_urn != '' ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 1",
    "INSERT INTO post_engagement (post_urn, stale) SELECT DISTINCT activity_urn, 2 FROM post_metric_observations "
    "WHERE activity_urn != '' ON CONFLICT(post_urn) DO UPDATE SET stale = stale | 2",
)


# Migration 22 built the first search index, contentless, whose rows could
# only be removed by repeating the exact text indexed. Migration 24 replaces
# it whole, so 22 now does nothing, and a database at 21 goes straight to
# the index 24 builds.
_MIGRATION_22_SUPERSEDED: tuple = ()


# Migration 24: the search index universal_search.py reads (posts, LinkedIn
# posts, leads and what they said), its triggers, and everything already
# held indexed. Rows written with the Composer's styled letters are queued
# on search_refold, which universal_search.refold() indexes through NFKC.
_MIGRATION_24_SEARCH = (
    "DROP TRIGGER IF EXISTS search_post_added",
    "DROP TRIGGER IF EXISTS search_post_changed",
    "DROP TRIGGER IF EXISTS search_post_removed",
    "DROP TRIGGER IF EXISTS search_own_post_added",
    "DROP TRIGGER IF EXISTS search_own_post_changed",
    "DROP TRIGGER IF EXISTS search_own_post_removed",
    "DROP TRIGGER IF EXISTS search_lead_added",
    "DROP TRIGGER IF EXISTS search_lead_changed",
    "DROP TRIGGER IF EXISTS search_lead_removed",
    "DROP TRIGGER IF EXISTS search_comment_added",
    "DROP TRIGGER IF EXISTS search_comment_changed",
    "DROP TRIGGER IF EXISTS search_comment_removed",
    "DROP TABLE IF EXISTS search_posts",
    "DROP TABLE IF EXISTS search_leads",
    "DROP TABLE IF EXISTS search_comments",
    "DROP TABLE IF EXISTS search_docs",
    """
    CREATE TABLE IF NOT EXISTS search_docs (
        docid INTEGER PRIMARY KEY,
        kind TEXT NOT NULL,
        ref TEXT NOT NULL,
        UNIQUE (kind, ref)
    )
    """,
    'CREATE TABLE IF NOT EXISTS search_refold (kind TEXT NOT NULL, ref TEXT NOT NULL, PRIMARY KEY (kind, ref)) WITHOUT ROWID',
    "CREATE VIRTUAL TABLE IF NOT EXISTS search_posts USING fts5(body, tokenize='unicode61 remove_diacritics 2')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS search_leads USING fts5(name, about, notes, tokenize='unicode61 remove_diacritics 2')",
    "CREATE VIRTUAL TABLE IF NOT EXISTS search_comments USING fts5(comment_text, tokenize='unicode61 remove_diacritics 2')",
    """
    CREATE TRIGGER IF NOT EXISTS search_post_added AFTER INSERT ON posts
    BEGIN
        INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('post', NEW.id);
        INSERT INTO search_posts (rowid, body) SELECT last_insert_rowid(), replace(replace(replace(COALESCE(NEW.content, '') || ' ' || COALESCE(NEW.tags, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') WHERE changes() > 0;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'post', NEW.id WHERE (COALESCE(NEW.content, '') || ' ' || COALESCE(NEW.tags, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_post_changed AFTER UPDATE OF content, tags, id ON posts
    WHEN OLD.content IS NOT NEW.content OR OLD.tags IS NOT NEW.tags OR OLD.id IS NOT NEW.id
    BEGIN
        DELETE FROM search_posts WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'post' AND ref = OLD.id);
        UPDATE search_docs SET ref = NEW.id WHERE kind = 'post' AND ref = OLD.id;
        INSERT INTO search_posts (rowid, body)
        SELECT docid, replace(replace(replace(COALESCE(NEW.content, '') || ' ' || COALESCE(NEW.tags, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs WHERE kind = 'post' AND ref = NEW.id;
        DELETE FROM search_refold WHERE kind = 'post' AND ref = OLD.id;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'post', NEW.id WHERE (COALESCE(NEW.content, '') || ' ' || COALESCE(NEW.tags, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_post_removed AFTER DELETE ON posts
    BEGIN
        DELETE FROM search_posts WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'post' AND ref = OLD.id);
        DELETE FROM search_docs WHERE kind = 'post' AND ref = OLD.id;
        DELETE FROM search_refold WHERE kind = 'post' AND ref = OLD.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_own_post_added AFTER INSERT ON own_posts
    BEGIN
        INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('own_post', NEW.activity_urn);
        INSERT INTO search_posts (rowid, body) SELECT last_insert_rowid(), replace(replace(replace(COALESCE(NEW.text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') WHERE changes() > 0;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'own_post', NEW.activity_urn WHERE (COALESCE(NEW.text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_own_post_changed AFTER UPDATE OF text, activity_urn ON own_posts
    WHEN OLD.text IS NOT NEW.text OR OLD.activity_urn IS NOT NEW.activity_urn
    BEGIN
        DELETE FROM search_posts WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'own_post' AND ref = OLD.activity_urn);
        UPDATE search_docs SET ref = NEW.activity_urn WHERE kind = 'own_post' AND ref = OLD.activity_urn;
        INSERT INTO search_posts (rowid, body)
        SELECT docid, replace(replace(replace(COALESCE(NEW.text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs WHERE kind = 'own_post' AND ref = NEW.activity_urn;
        DELETE FROM search_refold WHERE kind = 'own_post' AND ref = OLD.activity_urn;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'own_post', NEW.activity_urn WHERE (COALESCE(NEW.text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_own_post_removed AFTER DELETE ON own_posts
    BEGIN
        DELETE FROM search_posts WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'own_post' AND ref = OLD.activity_urn);
        DELETE FROM search_docs WHERE kind = 'own_post' AND ref = OLD.activity_urn;
        DELETE FROM search_refold WHERE kind = 'own_post' AND ref = OLD.activity_urn;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_lead_added AFTER INSERT ON leads
    BEGIN
        INSERT OR IGNORE INTO search_docs (kind, ref) VALUES ('lead', NEW.id);
        INSERT INTO search_leads (rowid, name, about, notes)
        SELECT last_insert_rowid(), replace(replace(replace(COALESCE(NEW.full_name, '') || ' ' || COALESCE(NEW.name, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(NEW.company, '') || ' ' || COALESCE(NEW.headline, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(NEW.notes, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') WHERE changes() > 0;
        INSERT INTO search_comments (rowid, comment_text)
        SELECT (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.id AS TEXT)) * 4294967296 + i.id, replace(replace(replace(COALESCE(i.comment_text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss')
        FROM lead_interactions i
        WHERE changes() > 0 AND i.lead_id = NEW.id AND i.comment_text IS NOT NULL ORDER BY i.id;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'lead', NEW.id WHERE (COALESCE(NEW.full_name, '') || ' ' || COALESCE(NEW.name, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(NEW.company, '') || ' ' || COALESCE(NEW.headline, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(NEW.notes, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
        INSERT OR IGNORE INTO search_refold (kind, ref)
        SELECT 'comment', CAST(i.id AS TEXT) FROM lead_interactions i
        WHERE i.lead_id = NEW.id AND i.comment_text IS NOT NULL AND ((COALESCE(i.comment_text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_lead_changed AFTER UPDATE OF full_name, name, company, headline, notes, id ON leads
    WHEN OLD.full_name IS NOT NEW.full_name OR OLD.name IS NOT NEW.name OR OLD.company IS NOT NEW.company OR OLD.headline IS NOT NEW.headline OR OLD.notes IS NOT NEW.notes OR OLD.id IS NOT NEW.id
    BEGIN
        DELETE FROM search_leads WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.id AS TEXT));
        UPDATE search_docs SET ref = NEW.id WHERE kind = 'lead' AND ref = OLD.id;
        INSERT INTO search_leads (rowid, name, about, notes)
        SELECT docid, replace(replace(replace(COALESCE(NEW.full_name, '') || ' ' || COALESCE(NEW.name, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(NEW.company, '') || ' ' || COALESCE(NEW.headline, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(NEW.notes, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs WHERE kind = 'lead' AND ref = NEW.id;
        DELETE FROM search_refold WHERE kind = 'lead' AND ref = OLD.id;
        INSERT OR IGNORE INTO search_refold (kind, ref) SELECT 'lead', NEW.id WHERE (COALESCE(NEW.full_name, '') || ' ' || COALESCE(NEW.name, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(NEW.company, '') || ' ' || COALESCE(NEW.headline, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(NEW.notes, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_lead_removed AFTER DELETE ON leads
    BEGIN
        DELETE FROM search_comments WHERE rowid BETWEEN (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.id AS TEXT)) * 4294967296
            AND (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.id AS TEXT)) * 4294967296 + 4294967295;
        DELETE FROM search_leads WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.id AS TEXT));
        DELETE FROM search_docs WHERE kind = 'lead' AND ref = OLD.id;
        DELETE FROM search_refold WHERE kind = 'lead' AND ref = OLD.id;
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_comment_added AFTER INSERT ON lead_interactions
    WHEN NEW.comment_text IS NOT NULL
    BEGIN
        INSERT INTO search_comments (rowid, comment_text)
        SELECT docid * 4294967296 + NEW.id, replace(replace(replace(COALESCE(NEW.comment_text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss')
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT);
        INSERT OR IGNORE INTO search_refold (kind, ref)
        SELECT 'comment', CAST(NEW.id AS TEXT) WHERE (COALESCE(NEW.comment_text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*';
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_comment_changed AFTER UPDATE OF comment_text, lead_id, id ON lead_interactions
    WHEN OLD.comment_text IS NOT NEW.comment_text OR OLD.lead_id IS NOT NEW.lead_id OR OLD.id IS NOT NEW.id
    BEGIN
        DELETE FROM search_comments WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.lead_id AS TEXT)) * 4294967296 + OLD.id;
        INSERT INTO search_comments (rowid, comment_text)
        SELECT docid * 4294967296 + NEW.id, replace(replace(replace(COALESCE(NEW.comment_text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss')
        FROM search_docs WHERE kind = 'lead' AND ref = CAST(NEW.lead_id AS TEXT) AND NEW.comment_text IS NOT NULL;
        DELETE FROM search_refold WHERE kind = 'comment' AND ref = CAST(OLD.id AS TEXT);
        INSERT OR IGNORE INTO search_refold (kind, ref)
        SELECT 'comment', CAST(NEW.id AS TEXT) WHERE NEW.comment_text IS NOT NULL AND ((COALESCE(NEW.comment_text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS search_comment_removed AFTER DELETE ON lead_interactions
    WHEN OLD.comment_text IS NOT NULL
    BEGIN
        DELETE FROM search_comments WHERE rowid = (SELECT docid FROM search_docs WHERE kind = 'lead' AND ref = CAST(OLD.lead_id AS TEXT)) * 4294967296 + OLD.id;
        DELETE FROM search_refold WHERE kind = 'comment' AND ref = CAST(OLD.id AS TEXT);
    END
    """,
    'DELETE FROM search_posts',
    'DELETE FROM search_leads',
    'DELETE FROM search_comments',
    'DELETE FROM search_docs',
    'DELETE FROM search_refold',
    "INSERT INTO search_docs (kind, ref) SELECT 'post', id FROM posts ORDER BY rowid",
    "INSERT INTO search_docs (kind, ref) SELECT 'own_post', activity_urn FROM own_posts ORDER BY rowid",
    "INSERT INTO search_docs (kind, ref) SELECT 'lead', id FROM leads ORDER BY rowid",
    "INSERT INTO search_posts (rowid, body) SELECT d.docid, replace(replace(replace(COALESCE(p.content, '') || ' ' || COALESCE(p.tags, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs d JOIN posts p ON p.id = d.ref WHERE d.kind = 'post' ORDER BY d.docid",
    "INSERT INTO search_posts (rowid, body) SELECT d.docid, replace(replace(replace(COALESCE(p.text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs d JOIN own_posts p ON p.activity_urn = d.ref WHERE d.kind = 'own_post' ORDER BY d.docid",
    "INSERT INTO search_leads (rowid, name, about, notes) SELECT d.docid, replace(replace(replace(COALESCE(p.full_name, '') || ' ' || COALESCE(p.name, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(p.company, '') || ' ' || COALESCE(p.headline, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss'), replace(replace(replace(COALESCE(p.notes, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM search_docs d JOIN leads p ON p.id = d.ref WHERE d.kind = 'lead' ORDER BY d.docid",
    "INSERT INTO search_comments (rowid, comment_text) SELECT d.docid * 4294967296 + i.id, replace(replace(replace(COALESCE(i.comment_text, ''), char(305), 'i'), char(223), 'ss'), char(7838), 'ss') FROM lead_interactions i JOIN search_docs d ON d.kind = 'lead' AND d.ref = CAST(i.lead_id AS TEXT) WHERE i.comment_text IS NOT NULL ORDER BY 1",
    "INSERT INTO search_refold (kind, ref) SELECT 'post', id FROM posts p WHERE (COALESCE(p.content, '') || ' ' || COALESCE(p.tags, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*'",
    "INSERT INTO search_refold (kind, ref) SELECT 'own_post', activity_urn FROM own_posts p WHERE (COALESCE(p.text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*'",
    "INSERT INTO search_refold (kind, ref) SELECT 'lead', id FROM leads p WHERE (COALESCE(p.full_name, '') || ' ' || COALESCE(p.name, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(p.company, '') || ' ' || COALESCE(p.headline, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*' OR (COALESCE(p.notes, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*'",
    "INSERT INTO search_refold (kind, ref) SELECT 'comment', CAST(i.id AS TEXT) FROM lead_interactions i WHERE i.comment_text IS NOT NULL AND ((COALESCE(i.comment_text, '')) GLOB '*[' || char(119808) || '-' || char(120831) || char(8448) || '-' || char(8527) || char(64256) || '-' || char(64335) || char(65280) || '-' || char(65519) || ']*')",
    "INSERT INTO search_posts (search_posts) VALUES ('optimize')",
    "INSERT INTO search_leads (search_leads) VALUES ('optimize')",
    "INSERT INTO search_comments (search_comments) VALUES ('optimize')",
)


def _migrate_retention(cursor: sqlite3.Cursor) -> None:
    """
    Empty structures for retention (studio/backend/retention.py), and nothing else.

    No row is removed here. A cleanup runs later, after a backup, and on a
    database that already holds readings or reactions only once the creator
    has confirmed its preview: so the starting state of those two rules is
    "ask" there, and "on" for a new install, which has nothing to lose.
    """
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reaction_folds (
        post_urn TEXT PRIMARY KEY,
        reactions INTEGER NOT NULL DEFAULT 0,
        people INTEGER NOT NULL DEFAULT 0,
        vip INTEGER NOT NULL DEFAULT 0,
        qualified INTEGER NOT NULL DEFAULT 0,
        icp_known INTEGER NOT NULL DEFAULT 0,
        icp_sum REAL NOT NULL DEFAULT 0,
        conversations INTEGER NOT NULL DEFAULT 0,
        folded_through TEXT,
        updated_at TEXT NOT NULL
    )
    """)
    # Per person: how many old reactions were folded, and on whose posts, so
    # every count of a person's engagement stays what it was. Which posts is
    # what a fold gives up.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lead_reaction_folds (
        lead_id TEXT PRIMARY KEY,
        reactions INTEGER NOT NULL DEFAULT 0,
        on_your_posts INTEGER NOT NULL DEFAULT 0,
        on_others_posts INTEGER NOT NULL DEFAULT 0,
        on_unknown_posts INTEGER NOT NULL DEFAULT 0,
        folded_through TEXT,
        topics TEXT
    )
    """)
    # No foreign key: a later rebuild of leads would cascade into it. The
    # trigger below removes a forgotten lead's row instead.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lead_retention_keeps (
        lead_id TEXT PRIMARY KEY,
        kept_at TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS retention_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        outcome TEXT NOT NULL,
        removed INTEGER NOT NULL DEFAULT 0,
        backup TEXT,
        detail TEXT
    )
    """)
    # Who was forgotten, held only until the creator chooses whether to remove
    # them from backups too: their copies there can be found by this id alone.
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forgotten_in_backups (
        lead_id TEXT PRIMARY KEY,
        forgotten_at TEXT NOT NULL
    )
    """)
    # Migration 19's trigger, now covering the keep list too, and noting the
    # id for backups whichever path did the forgetting.
    cursor.execute("DROP TRIGGER IF EXISTS lead_forgotten")
    cursor.execute("""
    CREATE TRIGGER lead_forgotten AFTER DELETE ON leads
    BEGIN
        DELETE FROM lead_stage_events WHERE lead_id = OLD.id;
        DELETE FROM lead_interactions WHERE lead_id = OLD.id;
        DELETE FROM lead_enrichments WHERE lead_id = OLD.id;
        DELETE FROM lead_retention_keeps WHERE lead_id = OLD.id;
        DELETE FROM lead_reaction_folds WHERE lead_id = OLD.id;
        INSERT OR REPLACE INTO forgotten_in_backups (lead_id, forgotten_at) VALUES (OLD.id, CURRENT_TIMESTAMP);
    END
    """)
    # Someone forgotten who engages again is a lead again, and the backups made
    # since hold them rightly. A lead's id is a hash of their profile.
    cursor.execute("DROP TRIGGER IF EXISTS lead_returned")
    cursor.execute("""
    CREATE TRIGGER lead_returned AFTER INSERT ON leads
    BEGIN
        DELETE FROM forgotten_in_backups WHERE lead_id = NEW.id;
    END
    """)
    starting = (
        ("retention_readings", "SELECT EXISTS (SELECT 1 FROM post_metric_observations)"),
        ("retention_fold_reactions", "SELECT EXISTS (SELECT 1 FROM lead_interactions WHERE interaction_type = 'LIKE')"),
    )
    for key, holds_data in starting:
        state = "ask" if cursor.execute(holds_data).fetchone()[0] else "on"
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, state))


# Migration = (version, description, payload)
# payload is either a sequence of SQL statements or a callable taking a cursor.
# Append only. Never reorder, never edit, never delete.
Payload = Union[Sequence[str], Callable[[sqlite3.Cursor], None]]
# A day's "members reached" was never read from LinkedIn: no writer has ever
# set it, and every insert now names it NULL. The column's old DEFAULT 0 put a
# 0 on every row written before that, and a 0 reads as measured on Analytics.
# So each one is cleared, which the F3 review asked for (AUDIENCE-26). Run
# again it finds nothing: there are no 0s left to clear.
_MIGRATION_25_UNREAD_REACH = (
    "UPDATE analytics_daily SET unique_members_reached = NULL WHERE unique_members_reached = 0",
)


# How a drafts row's status reads as a posts status. The legacy store had its
# own four, in capitals, and the queue it fed had four more.
_DRAFT_STATUS = {"DRAFT": "draft", "QUEUED": "scheduled", "PUBLISHED": "published", "ARCHIVED": "draft"}
_QUEUE_STATUS = {"PENDING": "scheduled", "NOTIFIED": "scheduled", "PUBLISHED": "published", "CANCELLED": "draft"}


def _migrate_one_post_identity(cursor: sqlite3.Cursor) -> None:
    """
    Migration 26:
    One identity for a post.

    Four tables held "something the creator wrote" and they disagreed. On a
    three year install: posts 894, own_posts 1,417, drafts 1,044 that no
    screen could show, queue_items 894 with no reachable writer or reader.
    523 own_posts had no posts row, which stranded 182,115 of 500,061
    captured interactions: the busiest post in the install answered 404 from
    the engagers endpoint while Analytics showed it and its leads.

    After this, posts is the record of what the creator wrote and own_posts is
    the record of the publication, one of each per post, joined by
    own_posts.post_id as well as by the URN:

      posts.source        where the row came from: 'studio' for one written
                          here, 'linkedin' for one reconstructed from a
                          publication the extension or the archive brought,
                          'drafts' for one carried out of the legacy store.
      own_posts.post_id   the posts row this publication belongs to.

    Nothing the creator wrote is lost and nothing is duplicated:

      1. A publication whose URN a posts row already carries keeps that row.
      2. A publication whose text matches exactly one unbound posts row binds
         to it, by post_identity.bind_activity_urn, which is the same rule the
         permalink route and the history import bind by.
      3. Any other publication gets a posts row made from it, keyed
         deterministically by its URN, so running this twice makes one row.
      4. A drafts row with no posts row beside it gets one, carrying its text,
         its tags, its date and the slot its queue_items row held, so dropping
         the dead queue loses no time a creator chose.
      5. queue_items is dropped. Every one of the 894 rows in the three year
         install named a draft that step 4 covers, and nothing a creator can
         reach wrote or read the table.

    Idempotent and resumable: every step is written as the work still to do
    (post_id IS NULL, no posts row for this draft), so a run that was
    interrupted and rolled back repeats only what it had not finished, and a
    run with nothing to do touches no row. The ledger takes the standard
    pre-migration backup before any of it.
    """
    import hashlib

    try:
        from . import post_identity
    except (ImportError, ValueError):
        import post_identity

    conn = cursor.connection

    columns = {row[1] for row in cursor.execute("PRAGMA table_info(posts)")}
    if "source" not in columns:
        # Defaulted rather than backfilled: a row written before this
        # migration came from the studio unless it says otherwise, and the
        # default says so without touching a single row the creator wrote.
        cursor.execute("ALTER TABLE posts ADD COLUMN source TEXT DEFAULT 'studio'")
    own_columns = {row[1] for row in cursor.execute("PRAGMA table_info(own_posts)")}
    if "post_id" not in own_columns:
        cursor.execute("ALTER TABLE own_posts ADD COLUMN post_id TEXT")

    # 1. The publications a posts row already carries the URN of.
    cursor.execute(
        "UPDATE own_posts SET post_id = (SELECT p.id FROM posts p WHERE p.activity_urn = own_posts.activity_urn) "
        "WHERE post_id IS NULL AND EXISTS (SELECT 1 FROM posts p WHERE p.activity_urn = own_posts.activity_urn)"
    )

    # 2 and 3. Everything else: bound by its text where exactly one unbound
    # posts row matches, else given a posts row of its own.
    orphans = cursor.execute(
        "SELECT activity_urn, text, published_at, first_seen_at FROM own_posts WHERE post_id IS NULL"
    ).fetchall()
    for urn, text, published_at, first_seen_at in orphans:
        if not urn:
            continue
        bindable = cursor.execute(
            "SELECT 1 FROM posts WHERE activity_urn IS NULL AND COALESCE(content, '') != '' LIMIT 1"
        ).fetchone()
        if bindable and text:
            result = post_identity.bind_activity_urn(
                conn, urn, text, published_at=published_at, from_history=True)
            if result.get("bound"):
                cursor.execute("UPDATE own_posts SET post_id = ? WHERE activity_urn = ?",
                               (result["post_id"], urn))
                continue
        post_id = f"post-{hashlib.sha256(urn.encode('utf-8')).hexdigest()[:12]}"
        existing = cursor.execute("SELECT activity_urn FROM posts WHERE id = ?", (post_id,)).fetchone()
        if existing is None:
            cursor.execute(
                "INSERT INTO posts (id, content, status, published_at, activity_urn, content_fingerprint, "
                "source, created_at) VALUES (?, ?, 'published', ?, ?, ?, 'linkedin', ?)",
                (post_id, text or "", published_at, urn,
                 post_identity.content_fingerprint(text or ""), first_seen_at or published_at),
            )
        elif existing[0] != urn:
            # Two posts whose URNs hash to the same twelve characters. Keep
            # the first and name the second after its own URN in full.
            post_id = f"post-{hashlib.sha256((urn + '#2').encode('utf-8')).hexdigest()[:12]}"
            cursor.execute(
                "INSERT OR IGNORE INTO posts (id, content, status, published_at, activity_urn, "
                "content_fingerprint, source, created_at) VALUES (?, ?, 'published', ?, ?, ?, 'linkedin', ?)",
                (post_id, text or "", published_at, urn,
                 post_identity.content_fingerprint(text or ""), first_seen_at or published_at),
            )
        cursor.execute("UPDATE own_posts SET post_id = ? WHERE activity_urn = ?", (post_id, urn))

    # 4. The legacy drafts store keeps no writing of its own. A row with no
    # posts row beside it becomes one, with the slot its queue row held.
    if cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'drafts'").fetchone():
        has_queue = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'queue_items'").fetchone()
        # A drafts row is already in posts when a posts row names it, or when
        # one holds the same text: the demo seeder and the Telegram ingress
        # both wrote their posts row without naming the draft. Matching the
        # text as well is also what makes running this twice a no-op.
        stranded = cursor.execute(
            "SELECT d.id, d.raw_content, d.status, d.tags, d.created_at FROM drafts d "
            "WHERE COALESCE(d.raw_content, '') != '' "
            "AND d.id NOT IN (SELECT draft_id FROM posts WHERE draft_id IS NOT NULL) "
            "AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.content = d.raw_content)"
        ).fetchall()
        for draft_id, raw_content, draft_status, tags, created_at in stranded:
            status = _DRAFT_STATUS.get((draft_status or "").upper(), "draft")
            scheduled_for = published_at = None
            if has_queue:
                slot = cursor.execute(
                    "SELECT scheduled_at, published_at, status FROM queue_items WHERE draft_id = ? "
                    "ORDER BY id DESC LIMIT 1", (draft_id,)).fetchone()
                if slot:
                    status = _QUEUE_STATUS.get((slot[2] or "").upper(), status)
                    if status == "published":
                        published_at = slot[1] or slot[0]
                    elif status == "scheduled":
                        scheduled_for = slot[0]
            cursor.execute(
                "INSERT OR IGNORE INTO posts (id, content, status, scheduled_for, published_at, tags, "
                "draft_id, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'drafts', ?)",
                (f"post-draft-{draft_id}", raw_content, status, scheduled_for, published_at,
                 tags or "[]", draft_id, created_at),
            )

    # 5. The dead queue.
    cursor.execute("DROP INDEX IF EXISTS idx_queue_scheduled")
    cursor.execute("DROP TABLE IF EXISTS queue_items")

    # Rows written before this migration came from the studio unless they say
    # otherwise, which is what the column is for.
    cursor.execute("UPDATE posts SET source = 'studio' WHERE source IS NULL")


def _migrate_current_scores(cursor: sqlite3.Cursor) -> None:
    """
    Migration 27:
    A lead's score is derived, not a snapshot, and says when it needs redoing.

    icp_score was written once at capture and never recomputed. Measured on a
    three year install: the stored scores said 0 of 49,142 people qualified
    while the product's own engine, on the same headlines and the same
    comments, qualified 11,767 of them, and every screen read the stored
    number: "0 people qualified from 1417 posts".

    So the column becomes a cache with a mark beside it. These triggers mark a
    lead whenever anything the score is computed from changes, and
    crm.catch_up_scores recomputes the marked ones (a reader before it counts,
    database.init_db after an upgrade). Every lead is marked here, so no score
    written by an import, a seeding or an older build survives.

    The per-post summary's readings are marked too: they now carry which page
    each reading came from, which the old rows do not hold.
    """
    columns = {row[1] for row in cursor.execute("PRAGMA table_info(leads)")}
    if "icp_stale" not in columns:
        cursor.execute("ALTER TABLE leads ADD COLUMN icp_stale INTEGER NOT NULL DEFAULT 0")
    # Partial, so finding the marked leads costs nothing when none are marked,
    # which is the normal case: a full scan of 49,142 rows is 3 ms and this is
    # read on every screen that counts people.
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_score_stale ON leads(icp_stale) WHERE icp_stale != 0")
    # Who the person is, which the score's seniority and company weights read.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS lead_score_profile_changed
        AFTER UPDATE OF headline, company ON leads
        WHEN OLD.headline IS NOT NEW.headline OR OLD.company IS NOT NEW.company
        BEGIN
            UPDATE leads SET icp_stale = 1 WHERE id = NEW.id AND icp_stale = 0;
        END
    """)
    # A score written by anything but the engine, including an import, a demo
    # seeding and this migration's own backfill.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS lead_score_added AFTER INSERT ON leads
        BEGIN
            UPDATE leads SET icp_stale = 1 WHERE id = NEW.id AND icp_stale = 0;
        END
    """)
    # The engagements the score is the best of. An engagement being removed
    # does not mark anything: the only thing that removes one is the retention
    # fold, which keeps the reaction as a count and the person's tier as it
    # was then (retention.py), and re-deriving the score from the rows it left
    # would quietly recompute a person from less evidence than was observed.
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS lead_score_interaction_added
        AFTER INSERT ON lead_interactions
        BEGIN
            UPDATE leads SET icp_stale = 1
            WHERE id = CAST(NEW.lead_id AS TEXT) AND icp_stale = 0;
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS lead_score_interaction_changed
        AFTER UPDATE OF lead_id, interaction_type, comment_text ON lead_interactions
        BEGIN
            UPDATE leads SET icp_stale = 1
            WHERE id IN (CAST(OLD.lead_id AS TEXT), CAST(NEW.lead_id AS TEXT)) AND icp_stale = 0;
        END
    """)
    cursor.execute("UPDATE leads SET icp_stale = 1 WHERE icp_stale = 0")
    if cursor.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'post_engagement'").fetchone():
        cursor.execute("UPDATE post_engagement SET stale = stale | 2 WHERE (stale & 2) = 0")


def _migrate_desk_requests_and_export_totals(cursor: sqlite3.Cursor) -> None:
    """
    Migration 28 (cycle 4, track 6):
    A post link shared from the phone is a desk request, and LinkedIn's
    analytics export has a home for the totals it carries.

    desk_requests: one row per post the phone asked the desk to read. The
    Telegram ingress writes it when a message carries a LinkedIn post link;
    Today surfaces the oldest open one as the page to open; it is done when
    that post's analytics page is next read after it was asked, and after a
    week unread. `note` holds the refusal sentence for a post the studio does
    not hold, rather than an invented post.

    analytics_daily.engagements and analytics_daily.new_followers: LinkedIn's
    export gives one engagements figure a day, not reactions, comments and
    reposts apart, and new followers a day, not a follower count. Neither
    fits a column that exists, and writing a total into `reactions` would be
    a figure the studio made up. post_metric_observations.engagements holds
    the same total per post from the export's top posts. Every new column is
    NULL for every row that exists: nothing is measured by this migration.
    """
    # grain: one row per request, however many times the same post is shared.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS desk_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_urn TEXT NOT NULL,
            asked_at TEXT NOT NULL,
            done_at TEXT,
            note TEXT,
            source TEXT NOT NULL DEFAULT 'telegram'
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_desk_requests_open ON desk_requests(done_at, asked_at)")
    for table, column in (("analytics_daily", "engagements"),
                          ("analytics_daily", "new_followers"),
                          ("post_metric_observations", "engagements")):
        cursor.execute(f"PRAGMA table_info({table})")
        if column not in {row[1] for row in cursor.fetchall()}:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER")


MIGRATIONS: List[Tuple[int, str, Payload]] = [
    (2, "Migrate inspirations to viral_templates and drop inspirations table", _migrate_inspirations),
    (3, "Create internal_sheet_issues table for visual screen concept identification", _migrate_internal_sheet),
    (4, "Add provenance column to analytics_daily and audience_demographics", _migrate_provenance),
    (5, "Record observation window and precision on analytics_daily", _migrate_observation_window),
    (6, "Record capture context on lead_interactions", _migrate_capture_context),
    (7, "Give a post the activity URN and fingerprint that identify it", _migrate_post_identity),
    (8, "Record screen, section and reproduction context on internal sheet issues", _migrate_annotation_context),
    (9, "Record where a swipe specimen came from", _migrate_template_provenance),
    (10, "Record who the creator is, their profile, posts and outbound activity", _migrate_creator_self),
    (11, "One lead interaction per interaction, not per page load, and no placeholder text", _migrate_interaction_grain),
    (12, "Record each capture run, so a broken selector is visible", _migrate_capture_log),
    (13, "Keep readings of each post over time, with the post's age", _migrate_post_metric_observations),
    (14, "Keep a history of each lead's status changes", _migrate_lead_stage_events),
    (15, "Record schema drift events from Voyager network interception", _migrate_schema_drift_events),
    (16, "Create creator_accounts table for enterprise multi-tenant profiles", _migrate_creator_accounts),
    (17, "A captured lead says how they engaged, and where their profile is", _migrate_lead_engagement_labels),
    (18, "Connections and archive imports, from LinkedIn's own data archive", _MIGRATION_18_ARCHIVE),
    (19, "Nothing about a forgotten lead outlives them", _MIGRATION_19_FORGET),
    (20, "Index the interactions the main screens read, and give the planner statistics", _MIGRATION_20_INDEXES),
    (21, "Keep a summary of each post's engagement and readings beside the raw rows", _MIGRATION_21_SUMMARY),
    (22, "Index posts, leads and comments for search (superseded by 24)", _MIGRATION_22_SUPERSEDED),
    (23, "Retention: reaction folds, the lead keep list and a cleanup log", _migrate_retention),
    (24, "Search folds the Composer's bold and italic letters, and removes rows by id", _MIGRATION_24_SEARCH),
    (25, "A day's members reached is not measured, so an invented 0 is cleared", _MIGRATION_25_UNREAD_REACH),
    (26, "One identity for a post: every publication has its post, and the dead queue is gone",
     _migrate_one_post_identity),
    (27, "A lead's score is recomputed when what it is computed from changes", _migrate_current_scores),
    (28, "A post link from the phone is a desk request, and the analytics export's totals have a home",
     _migrate_desk_requests_and_export_totals),
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

    source = sqlite_open.connect(db_path)
    try:
        destination = sqlite_open.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    except Exception:
        # A damaged source leaves a half written copy that would be listed,
        # and offered for restore, as if it were a backup.
        if os.path.exists(target):
            os.remove(target)
        raise
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
        # A database that does not exist yet is at version 0. Connecting to
        # the path to find that out created an empty file there, which every
        # read-only command (doctor, migrate) left behind.
        db_path = get_db_path()
        conn = sqlite3.connect(db_path if os.path.exists(db_path) else ":memory:")
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
