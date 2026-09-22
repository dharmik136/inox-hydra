"""
Database Access Layer & SQLite WAL Manager
==========================================
Provides thread-safe connection pooling, baseline schema creation, seed data
provisioning,
and Write-Ahead Logging (WAL) configuration for LinkedIn Studio Enterprise.

Database: resolved by studio/backend/paths.py (never inside the install directory)
Journal Mode: WAL (Write-Ahead Logging)

Schema changes do NOT belong in this file. The DDL here is the frozen
baseline (schema version 1). Every change after that is a numbered entry in
studio/backend/migrations.py, so that an existing user database can be
brought forward safely. See docs/PACKAGING_AND_MAINTENANCE_MASTER_PLAN.md.
Concurrency: Zero-blocking concurrent reads during background writes.
"""

import sys
import sqlite3
import os
import json
import threading
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any

try:
    from .paths import get_db_path, _STUDIO_DIR, DB_FILENAME
    from .migrations import ensure_schema, check_compatibility
except ImportError:
    from paths import get_db_path, _STUDIO_DIR, DB_FILENAME
    from migrations import ensure_schema, check_compatibility

# Retained as a module constant for backwards compatibility. Live resolution
# happens in get_db() so that INOX_HYDRA_HOME can be redirected at runtime.
DB_PATH = get_db_path()

_db_write_lock = threading.Lock()

# Demo content that ships with the product. The scheduler must never dispatch
# or roll forward these seeded example posts; they exist so a fresh install
# has something to show in the queue UI.
SEEDED_DEMO_POST_IDS = ("post-enterprise-scheduled",)


def get_db() -> sqlite3.Connection:
    """
    Opens and returns an active SQLite database connection configured in WAL mode.
    Sets row_factory to sqlite3.Row for dictionary-like column access.
    """
    db_path = get_db_path()

    # Safety guard: Tests must NEVER connect to the live production database
    if ("pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ) and os.environ.get("INOX_ALLOW_LIVE_DB_IN_TESTS") != "1":
        live_repo_db = os.path.normcase(os.path.abspath(os.path.join(_STUDIO_DIR, "data", DB_FILENAME)))
        current_resolved_db = os.path.normcase(os.path.abspath(db_path))
        if current_resolved_db == live_repo_db:
            raise RuntimeError(
                f"CRITICAL SAFETY VIOLATION: Test run attempted to connect to live production database at {db_path}! "
                "Tests must run against an isolated INOX_HYDRA_HOME sandbox."
            )

    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA cache_size = -64000;")
    return conn



def init_db() -> None:
    """
    Initializes the 7 foundational relational tables in the local SQLite database:
    1. analytics_daily: Time-series creator metrics & impressions.
    2. posts: Content drafts, scheduled items, published activities.
    3. audience_demographics: Job title, company, geography, and seniority breakdowns.
    4. inspirations: Reverse-engineered viral post templates & blueprints.
    5. queue_slots: Peak engagement calendar schedule matrix.
    6. leads: Post commenter & reactor CRM pipeline.
    7. settings: Key-value configuration store for tokens & Gemini API keys.
    """
    conn = get_db()

    # Refuse a database this build does not understand BEFORE touching it.
    #
    # check_compatibility says in its own docstring that it is "called before
    # any write". It was not: ensure_schema, which wraps it, ran at the end of
    # this function, after every CREATE TABLE, every ALTER, the seeding and the
    # commit. So a user who installed a newer build and then rolled back had
    # this one recreate tables the newer schema had dropped, commit them, and
    # only then decline to open the file. Verified by stamping user_version to
    # 99 and dropping a table: the refused build put it back.
    #
    # The check is hoisted; ensure_schema stays at the end, because a pre
    # ledger database has to be stamped after the baseline DDL rather than
    # rebuilt by it. Those are two different jobs that were sharing one call.
    try:
        check_compatibility(conn)
    except Exception:
        # No try/finally around this function's body, so an escaping error
        # would otherwise leak the connection along with the WAL handle.
        conn.close()
        raise

    cursor = conn.cursor()

    # 1. Daily Analytics Snapshots
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS analytics_daily (
        date TEXT PRIMARY KEY,
        followers INTEGER,
        connections INTEGER,
        profile_views INTEGER,
        impressions INTEGER DEFAULT 0,
        unique_members_reached INTEGER DEFAULT 0,
        reactions INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        engagement_rate REAL DEFAULT 0.0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Posts Catalog (drafts, scheduled, published)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id TEXT PRIMARY KEY,
        content TEXT NOT NULL,
        media_urls TEXT,
        status TEXT DEFAULT 'draft',
        scheduled_for TEXT,
        published_at TEXT,
        impressions INTEGER DEFAULT 0,
        reactions INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        shares INTEGER DEFAULT 0,
        clicks INTEGER DEFAULT 0,
        tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 3. Audience Demographics
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audience_demographics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dimension TEXT NOT NULL,
        label TEXT NOT NULL,
        percentage REAL NOT NULL
    )
    """)

    # 4. Viral Inspirations Library
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspirations (
        id TEXT PRIMARY KEY,
        author_name TEXT,
        author_headline TEXT,
        topic TEXT,
        content TEXT,
        likes_count INTEGER DEFAULT 0,
        comments_count INTEGER DEFAULT 0,
        key_hook TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 5. Smart Queue Slots
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day_of_week INTEGER NOT NULL, -- 0=Mon, 6=Sun
        time_slot TEXT NOT NULL, -- '08:30', '17:30'
        label TEXT,
        is_active INTEGER DEFAULT 1
    )
    """)

    # 6. Lead Database & CRM (Post Engagers)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        headline TEXT,
        company TEXT,
        profile_url TEXT,
        engagement_type TEXT DEFAULT 'Commented',
        post_id TEXT,
        status TEXT DEFAULT 'New Lead',
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 7. Settings / Session State
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 8. Agno Autonomous Lead Enrichments
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lead_enrichments (
        lead_id TEXT PRIMARY KEY,
        company_intelligence TEXT,
        estimated_tech_stack TEXT,
        key_topics TEXT,
        friction_points TEXT,
        icebreakers TEXT,
        enriched_by TEXT DEFAULT 'agno_local',
        enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
    )
    """)

    # 9. Media Assets Store (Uploaded Images, PDF Carousels, MP4 Videos)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS media_assets (
        id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        storage_path TEXT NOT NULL,
        media_type TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        dimensions TEXT,
        page_count INTEGER,
        duration_seconds REAL,
        prompt TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 10. AI Image Studio Generation Tasks
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS generation_tasks (
        task_id TEXT PRIMARY KEY,
        prompt TEXT NOT NULL,
        options_json TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        progress_percent INTEGER DEFAULT 1,
        status_message TEXT,
        result_url TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 11. Project Prudent Sovereign Drafts Store
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        raw_content TEXT NOT NULL,
        formatted_content TEXT,
        char_count INTEGER DEFAULT 0,
        lines_above_fold INTEGER DEFAULT 0,
        pre_fold_chars INTEGER DEFAULT 0,
        is_pre_fold_safe INTEGER DEFAULT 1,
        archetype TEXT DEFAULT 'Direct',
        tags TEXT DEFAULT '[]',
        status TEXT DEFAULT 'DRAFT' CHECK(status IN ('DRAFT', 'QUEUED', 'PUBLISHED', 'ARCHIVED')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_updated ON drafts(updated_at DESC)")

    # 12. Smart Queue Items
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        draft_id INTEGER NOT NULL,
        scheduled_at TIMESTAMP NOT NULL,
        published_at TIMESTAMP,
        status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'NOTIFIED', 'PUBLISHED', 'CANCELLED')),
        channel TEXT DEFAULT 'linkedin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(draft_id) REFERENCES drafts(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_queue_scheduled ON queue_items(scheduled_at, status)")

    # 13. Enterprise Reverse CRM Migrations for Leads
    cursor.execute("PRAGMA table_info(leads)")
    existing_leads_cols = {row["name"] for row in cursor.fetchall()}
    if "linkedin_urn" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN linkedin_urn TEXT")
    if "full_name" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN full_name TEXT")
        cursor.execute("UPDATE leads SET full_name = name WHERE full_name IS NULL")
    if "seniority_level" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN seniority_level TEXT DEFAULT 'Unknown'")
    if "icp_score" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN icp_score REAL DEFAULT 0.0")
    if "lead_status" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN lead_status TEXT DEFAULT 'NEW'")
        cursor.execute("""
        UPDATE leads SET lead_status = CASE 
            WHEN status = 'Connected' THEN 'ENGAGED'
            WHEN status = 'Outreach Sent' THEN 'DM_SENT'
            WHEN status = 'Meeting Booked' THEN 'CONVERTED'
            ELSE 'NEW'
        END WHERE lead_status IS NULL OR lead_status = 'NEW'
        """)
    if "updated_at" not in existing_leads_cols:
        cursor.execute("ALTER TABLE leads ADD COLUMN updated_at TIMESTAMP")
        cursor.execute("UPDATE leads SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_icp ON leads(icp_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(lead_status)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_urn ON leads(linkedin_urn) WHERE linkedin_urn IS NOT NULL")

    # 14. Lead Interactions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lead_interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER NOT NULL,
        post_id INTEGER,
        post_urn TEXT,
        interaction_type TEXT NOT NULL CHECK(interaction_type IN ('COMMENT', 'LIKE', 'REPOST')),
        comment_text TEXT,
        sentiment_label TEXT DEFAULT 'NEUTRAL',
        suggested_dm_reply TEXT,
        interacted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(lead_id) REFERENCES leads(id) ON DELETE CASCADE,
        FOREIGN KEY(post_id) REFERENCES drafts(id) ON DELETE SET NULL
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_lead ON lead_interactions(lead_id, interacted_at DESC)")

    # 15. Viral Hook Templates Library (Day 03 Asymmetric Intelligence Sync)
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_templates_velocity ON viral_templates(velocity_score DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_viral_templates_archetype ON viral_templates(archetype)")

    # 16. G-Stack Multi-Agent Backlog & Governance Matrix (Day 04)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS gstack_backlog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL CHECK(role IN ('CEO', 'ENGINEERING_MANAGER', 'DESIGNER', 'QA_LEAD', 'CSO', 'RELEASE_MANAGER')),
        title TEXT NOT NULL,
        specification TEXT NOT NULL,
        status TEXT DEFAULT 'PENDING' CHECK(status IN ('PENDING', 'IN_PROGRESS', 'VERIFIED', 'BLOCKED')),
        anti_slop_check INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gstack_role ON gstack_backlog(role, status)")

    # 17. Multi-Tenant Enterprise Account Isolation Migration
    for tbl in ["posts", "drafts", "leads", "lead_interactions", "settings"]:
        cursor.execute(f"PRAGMA table_info({tbl})")
        cols = {row["name"] for row in cursor.fetchall()}
        if "account_id" not in cols:
            cursor.execute(f"ALTER TABLE {tbl} ADD COLUMN account_id TEXT DEFAULT 'default'")
            cursor.execute(f"UPDATE {tbl} SET account_id = 'default' WHERE account_id IS NULL")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posts_account ON posts(account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_drafts_account ON drafts(account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_account ON leads(account_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_interactions_account ON lead_interactions(account_id)")

    # Seed foundational launch drafts (Days 02 through 08).
    # Demo content: these are the author's own posts, in their first person,
    # about a campaign a new user is not running.
    if demo_data_enabled():
        seed_day02_draft(conn)
        seed_day03_draft(conn)
        seed_day04_draft(conn)
        seed_day05_draft(conn)
        seed_day06_draft(conn)
        seed_day07_draft(conn)
        seed_day08_draft(conn)

    conn.commit()

    # Adopt or advance the schema ledger. Runs after the baseline DDL above so
    # a pre-ledger database is stamped rather than rebuilt. Any future schema
    # change belongs in studio/backend/migrations.py, never in this function.
    try:
        report = ensure_schema(conn)
    except Exception:
        conn.close()
        raise
    conn.close()

    print("Database initialized at:", get_db_path())
    if report.get("baselined"):
        print(f"Schema ledger adopted at baseline version {report['to_version']}.")
    for applied in report.get("applied", []):
        print(f"Applied migration {applied['version']}: {applied['description']}")
    if report.get("backup_path"):
        print(f"Pre-migration backup saved to {report['backup_path']}")


def seed_day02_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 02 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%The Fallacy of Heavy Web Scraping%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day02_content = (
            "Most LinkedIn automation tools get banned within 72 hours.\n\n"
            "Why? Because they crawl the web like it is still 2018.\n\n"
            "Here is the engineering reality behind modern bot detection:\n\n"
            "When a developer tries to automate a social platform today, their first instinct is usually:\n"
            "\"Let's just spin up a headless Chromium browser using Puppeteer or Playwright and scrape the feed.\"\n\n"
            "That works for about 2 days before the account hits a checkpoint.\n\n"
            "Here is what modern security networks actually detect:\n\n"
            "1. TLS Fingerprinting (JA3/JA4)\n"
            "Python requests or cURL have distinct cryptographic handshakes. If your TLS signature does not match an authentic desktop browser, you are flagged before a single byte of HTML loads.\n\n"
            "2. Runtime CDP Artifacts\n"
            "Chrome DevTools Protocol injects specific global variables into the JavaScript window object. Bot detectors actively search for these strings.\n\n"
            "3. Behavioral Entropy\n"
            "Real humans don't click buttons with straight mouse paths or paste 2,000 characters into an input field in 0 milliseconds.\n\n"
            "4. Hardware Hash Deviations\n"
            "Automated browsers often return generic or null WebGL and Canvas hashes that scream \"virtual machine.\"\n\n"
            "If you want to build reliable developer tools, you have to stop scraping the DOM.\n\n"
            "Tomorrow, on Day 3 of Project Prudent, I will break down the exact architecture we use instead: Passive Network Observation and Internal Voyager APIs.\n\n"
            "Have you ever had an account flagged by automated tools?"
        )
        day02_tags = json.dumps(["#engineering", "#antiBot", "#scraping", "#systemDesign", "#security"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'The Fallacy of Heavy Web Scraping & Anti-Bot Detection',
            ?, ?, ?, 3, 112, 1, 'Direct', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day02_content, day02_content, len(day02_content), day02_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day02-{draft_id}", day02_content, day02_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day03_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 03 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Passive Telemetry & Internal Voyager APIs%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day03_content = (
            "Stop scraping the DOM.\n\n"
            "The biggest breakthrough in building safe desktop creator software is Passive Network Observation.\n\n"
            "Here is how to extract analytics without sending a single synthetic bot request:\n\n"
            "Yesterday, I shared why headless browser scraping triggers account bans.\n"
            "Today, let's look at the alternative:\n\n"
            "Modern web platforms are built as single-page applications.\n"
            "When you open your analytics page, your browser is already making requests to internal endpoints (like /voyager/api/identity/dash/creatorAnalytics).\n\n"
            "That JSON response contains:\n"
            "- Daily impressions over 365 days\n"
            "- Audience demographic breakdowns\n"
            "- Engagement rates and reaction counts\n\n"
            "All in a single, clean 12KB payload.\n\n"
            "Instead of writing a bot to visit that page:\n"
            "We use a lightweight Chrome Manifest V3 service worker to passively observe when that endpoint responds during your normal browsing.\n\n"
            "The process:\n"
            "1. You browse LinkedIn normally.\n"
            "2. Your browser fetches your analytics.\n"
            "3. The local extension catches the response and stores it in your local SQLite database.\n"
            "4. Your desktop app updates instantly with zero cloud egress.\n\n"
            "The advantages:\n"
            "- Zero additional HTTP requests sent to the platform\n"
            "- Zero bot footprint\n"
            "- Zero risk of account flags\n"
            "- 100% data fidelity\n\n"
            "This is the power of passive telemetry.\n\n"
            "Engineers: Are you building with passive observation, or still fighting DOM selectors?"
        )
        day03_tags = json.dumps(["#engineering", "#passiveTelemetry", "#voyagerAPI", "#systemDesign", "#antiBot"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Passive Telemetry & Internal Voyager APIs',
            ?, ?, ?, 3, 121, 1, 'Direct', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day03_content, day03_content, len(day03_content), day03_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day03-{draft_id}", day03_content, day03_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day04_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 04 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%G-Stack in Practice%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day04_content = (
            "How a solo developer ships at the speed of a 10-person Series A engineering team:\n\n"
            "The secret is Garry Tan's \"G-Stack\" mental model.\n\n"
            "Most solo builders fail because of context thrashing:\n"
            "One minute you are writing CSS, the next minute you are tuning a database query, and suddenly you are trying to write marketing copy.\n\n"
            "The result is \"rookie software\":\n"
            "- Broken UI layouts\n"
            "- Clashing dependencies\n"
            "- Leaky database connections\n"
            "- Generic AI copy that sounds like a robot\n\n"
            "G-Stack organizes software creation into 6 specialized cognitive modes:\n\n"
            "1. CEO Mode\n"
            "Focuses purely on product moats, positioning, and ruthlessly cutting unnecessary features.\n\n"
            "2. Engineering Manager Mode\n"
            "Enforces architectural guardrails: local SQLite in WAL mode, offline-first data boundaries, and clean REST APIs.\n\n"
            "3. Designer Mode\n"
            "Ensures visual authority: Swiss typography, strict contrast ratios, mobile feed realism, and zero AI visual slop.\n\n"
            "4. QA Lead Mode\n"
            "Runs automated Playwright browser tests to verify layouts, measure latencies, and catch regressions before release.\n\n"
            "5. Chief Security Officer (CSO) Mode\n"
            "Audits token storage, verifies zero cloud egress, and ensures complete privacy for user credentials.\n\n"
            "6. Release Manager Mode\n"
            "Packages the app for 1-click desktop launch with zero configuration headaches.\n\n"
            "When you compartmentalize your thinking like an enterprise organization, you build 10x faster with 10x higher quality.\n\n"
            "Day 4 of Project Prudent complete.\n\n"
            "Have you tried using role-based workflows in your engineering process?"
        )
        day04_tags = json.dumps(["#GStack", "#soloDeveloper", "#engineering", "#systemDesign", "#YC"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'G-Stack in Practice: Running a 6-Role Virtual Team',
            ?, ?, ?, 3, 130, 1, 'Direct', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day04_content, day04_content, len(day04_content), day04_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day04-{draft_id}", day04_content, day04_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day05_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 05 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Anatomy of a High-Retention Hook%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day05_content = (
            "Your LinkedIn post dies in the first 140 characters.\n\n"
            "We analyzed 1,000 top-performing technical posts.\n\n"
            "Here is the exact anatomy of hooks that force the click:\n\n"
            "On mobile screens, LinkedIn truncates your post after line 3.\n"
            "That is roughly 140 characters of screen real estate.\n\n"
            "If those 140 characters don't create an irresistible curiosity gap, 90%+ of your audience will scroll right past.\n\n"
            "Here are the 3 non-negotiable rules for high-retention hooks:\n\n"
            "1. The 1-Line Agitation\n"
            "State an uncomfortable truth, an unexpected result, or a contrarian observation in a single punchy sentence.\n\n"
            "2. The Visual Air Gap\n"
            "Always insert an empty line break directly after your first sentence.\n"
            "Dense blocks of text trigger cognitive fatigue on mobile screens.\n\n"
            "3. The Promise of Resolution\n"
            "Line 3 must tell the reader exactly what value they receive if they tap \"...see more\".\n"
            "Never use clickbait with no payoff; provide high-density technical value.\n\n"
            "Here is the formula in action:\n\n"
            "Line 1: \"I spent $2,400 on creator SaaS before realizing this one truth.\"\n"
            "Line 2: [Empty spacing line]\n"
            "Line 3: \"Modern laptops are supercomputers. Here is why local-first software is taking over:\"\n\n"
            "When building Project Prudent, we built a dynamic glowing fold indicator directly into our desktop editor.\n"
            "It warns you the exact millisecond your hook exceeds 140 characters.\n\n"
            "Master the fold, and you master LinkedIn distribution.\n\n"
            "What is the best hook you have read on LinkedIn this month?"
        )
        day05_tags = json.dumps(["#engineering", "#hookMechanics", "#mobileFold", "#contentStrategy", "#retention"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Anatomy of a High-Retention Hook & Mobile Fold Physics',
            ?, ?, ?, 3, 105, 1, 'Contrarian / Pattern Interrupt', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day05_content, day05_content, len(day05_content), day05_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day05-{draft_id}", day05_content, day05_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day06_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 06 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Asymmetric Edge Computing%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day06_content = (
            "Why the smartest software architectures don't do everything on your laptop or in the cloud.\n\n"
            "Introducing Asymmetric Edge Computing:\n\n"
            "When designing our creator workstation, we faced an engineering dilemma:\n\n"
            "Users want to know which LinkedIn hooks and topics are ranking right now.\n"
            "To calculate this, you have to analyze thousands of live posts, classify text patterns, and calculate engagement velocity.\n\n"
            "There are two traditional ways to do this, and both are terrible:\n\n"
            "Approach 1: Run scrapers on each user's laptop.\n"
            "- Result: Drains user laptop battery, consumes 1GB RAM, and risks burning the user's home IP address.\n\n"
            "Approach 2: Spin up a multi-tenant cloud API with AWS and PostgreSQL.\n"
            "- Result: Costs hundreds of dollars every month in hosting bills, forcing you to charge users a monthly subscription.\n\n"
            "So we designed an Asymmetric Architecture:\n\n"
            "1. The Master Node (Our Machine)\n"
            "Runs the heavy trend mining and NLP clustering once per day. It sanitizes the findings into a tiny 40KB JSON bundle.\n\n"
            "2. The Global CDN\n"
            "The bundle is pushed to GitHub Releases, which edge-caches the data across worldwide CDN nodes for $0.00.\n\n"
            "3. The Client Instance (Your Machine)\n"
            "Checks for updates using HTTP ETags. If new data exists, it downloads the 40KB payload in 25ms, stores it in your local SQLite database, and updates your UI instantly.\n\n"
            "Heavy compute on the master.\n"
            "Instant, zero-risk rendering on the client.\n"
            "Zero dollars in monthly server costs.\n\n"
            "This is how you build sustainable, high-leverage software.\n\n"
            "How are you splitting compute between your clients and servers?"
        )
        day06_tags = json.dumps(["#asymmetricComputing", "#edgeArchitecture", "#systemDesign", "#softwareEngineering"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Asymmetric Edge Computing: Why Smart Software Does Not Do Everything in the Cloud',
            ?, ?, ?, 3, 134, 1, 'Architectural Breakdown', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day06_content, day06_content, len(day06_content), day06_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day06-{draft_id}", day06_content, day06_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day07_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 07 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Zero-Cost Cloud Distribution%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day07_content = (
            "How to distribute real-time daily data to thousands of desktop users for exactly $0.00/month:\n\n"
            "The GitHub CDN architecture every engineer should know:\n\n"
            "When building developer tools, one of the biggest expenses is cloud infrastructure:\n"
            "Hosting servers, API gateways, database instances, and egress bandwidth.\n\n"
            "If you have 10,000 users pulling updates daily, AWS will gladly bill you hundreds of dollars.\n\n"
            "Here is how we distribute daily viral hook intelligence in Project Prudent without paying a penny:\n\n"
            "1. Use GitHub Releases as an Edge CDN\n"
            "When you push release assets or raw JSON to GitHub, they are automatically cached across global Fastly CDN edge nodes.\n\n"
            "2. Implement HTTP ETag Conditional Caching\n"
            "Every file served has a unique cryptographic hash called an ETag.\n\n"
            "When our desktop client starts up, it doesn't just re-download the file.\n"
            "It sends a conditional GET request with the header:\n"
            "If-None-Match: \"previous-hash\"\n\n"
            "3. The Magic of HTTP 304\n"
            "If the data hasn't changed since yesterday:\n"
            "- The CDN returns 304 Not Modified\n"
            "- 0 bytes of payload data are transferred\n"
            "- Execution completes in under 30 milliseconds\n\n"
            "If new intelligence was published:\n"
            "- The client receives the compressed 40KB update\n"
            "- It saves the new ETag and updates local SQLite\n\n"
            "The result:\n"
            "- Instant worldwide distribution\n"
            "- Infinite horizontal scale\n"
            "- Zero server management\n"
            "- Total monthly hosting bill: $0.00\n\n"
            "Smart engineering is not about how much cloud infrastructure you can spin up.\n"
            "It is about how much you can eliminate.\n\n"
            "What is your favorite zero-cost engineering trick?"
        )
        day07_tags = json.dumps(["#cloudEconomics", "#githubCDN", "#etagCaching", "#zeroCostDev", "#systems"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Zero-Cost Cloud Distribution via GitHub CDN & ETag Caching',
            ?, ?, ?, 3, 142, 1, 'Step-by-Step Teardown', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day07_content, day07_content, len(day07_content), day07_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day07-{draft_id}", day07_content, day07_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day08_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 08 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Zero Cloud Egress & Bring-Your-Own-AI%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day08_content = (
            "Enterprise tech leaders don't want AI tools that upload their proprietary thoughts to random cloud servers.\n\n"
            "Here is how we architected a Zero-Egress \"Bring-Your-Own-AI\" system:\n\n"
            "Most AI writing assistants operate on a predatory model:\n"
            "They wrap an OpenAI or Claude API, mark up the token price by 500%, and store all your unreleased thoughts in their cloud database.\n\n"
            "For founders, architects, and practitioners, that is an unacceptable security risk.\n\n"
            "In Project Prudent, we took the opposite approach:\n\n"
            "1. Pluggable Model Gateway\n"
            "You supply your own API key directly to your local workstation:\n"
            "- Google Gemini (gemini-2.5-flash) for rapid iteration\n"
            "- Anthropic Claude (claude-3-5-sonnet) for deep technical essays\n"
            "- OpenAI (gpt-4o) for viral hooks\n"
            "- Ollama / vLLM for 100% offline, air-gapped local inference\n\n"
            "2. Sovereign Key Vaulting\n"
            "Your API keys are stored only in your local SQLite database on your machine.\n"
            "They never leave your hardware.\n"
            "Requests go directly from your machine to the model provider, with zero intermediate third-party servers.\n\n"
            "3. Zero-Token Deterministic Fallback\n"
            "If you are on an airplane with no internet, the app doesn't break.\n"
            "Our deterministic rule engine formats Unicode sans-bold fonts, validates fold lines, and scores post safety with 0ms latency and 0 API calls.\n\n"
            "True software freedom means you own the UI, you own the data, and you choose the intelligence engine.\n\n"
            "Would you rather pay a marked-up AI subscription, or bring your own API key to sovereign desktop software?"
        )
        day08_tags = json.dumps(["#sovereignAI", "#BYOAI", "#dataPrivacy", "#localFirst", "#gemini"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Zero Cloud Egress & Bring-Your-Own-AI (BYO-AI)',
            ?, ?, ?, 3, 178, 1, 'Contrarian Confession', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day08_content, day08_content, len(day08_content), day08_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day08-{draft_id}", day08_content, day08_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day09_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 09 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%The Offline-First Documentation Engine%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day09_content = (
            "Why are developer docs still bloated 80MB single-page apps that take 3 seconds to load?\n\n"
            "We built a zero-latency documentation engine that renders in 12 milliseconds:\n\n"
            "When you download a desktop developer tool, the last thing you want is:\n"
            "- A \"Docs\" tab that opens an external browser tab to GitBook\n"
            "- An embedded webview that spins forever when your Wi-Fi is spotty\n"
            "- A 100MB Node.js bundle just to render a few Markdown guides\n\n"
            "In Project Prudent, we redesigned developer documentation from first principles:\n\n"
            "1. Raw Markdown Storage\n"
            "All guides, playbooks, and strategy files are stored as pure UTF-8 Markdown directly in the local repository. Total footprint: less than 1.8MB.\n\n"
            "2. SQLite FTS5 Full-Text Search\n"
            "When the app launches, SQLite indexes every guide into an FTS5 virtual table.\n"
            "When you search for \"hook archetypes\" or \"rate limiting\":\n"
            "It executes a BM25 relevance query in 0.8 milliseconds, returning exact keyword snippets and line numbers.\n\n"
            "3. Zero-Dependency Client-Side Parsing\n"
            "The frontend uses a tiny 14KB Markdown renderer to convert text into Swiss typography on the fly.\n"
            "No cloud servers.\n"
            "No Node.js runtime.\n"
            "No network requests.\n\n"
            "It works on a flight at 35,000 feet just as fast as in an office with gigabit fiber.\n\n"
            "This is what developer experience (DevEx) should feel like in 2026.\n\n"
            "What is the fastest, cleanest documentation system you have ever used?"
        )
        day09_tags = json.dumps(["#developerExperience", "#offlineFirst", "#sqliteFTS5", "#systemDesign", "#localFirst"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'The Offline-First Documentation Engine & SQLite FTS5',
            ?, ?, ?, 3, 105, 1, 'The Architectural Breakdown', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day09_content, day09_content, len(day09_content), day09_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day09-{draft_id}", day09_content, day09_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day10_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 10 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%De-Monolithing the Frontend%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day10_content = (
            "The \"Rookie Stage\" of every software project:\n\n"
            "When your clean single-page app turns into an unmaintainable 3,000-line JavaScript monster.\n\n"
            "Here is how we bifurcated our architecture to eliminate UI bugs:\n\n"
            "When we built the initial prototype for our creator studio, it worked, but it had all the symptoms of a rapid prototype:\n"
            "- All 8 tabs lived in a single massive HTML file\n"
            "- Clicking a button on the CRM tab would accidentally trigger an event on the Post Editor tab\n"
            "- The mobile simulator's fold calculation would jump erratically when changing views\n\n"
            "In software engineering, this is called State Entanglement.\n\n"
            "To reach enterprise stability, we executed a complete Page Bifurcation:\n\n"
            "1. Decoupled View Containers\n"
            "We split the UI into 8 isolated page modules:\n"
            "- Post Studio (Editor + Mobile Simulator)\n"
            "- Hook & Trend Radar\n"
            "- Smart Queue & Scheduler\n"
            "- Inbound Lead CRM\n"
            "- Analytics & Demographics\n"
            "- Visual Carousel Studio\n"
            "- Offline Playbook Docs\n"
            "- Settings & Key Vault\n\n"
            "2. Strict Mount and Unmount Lifecycles\n"
            "When a user switches from Studio to CRM:\n"
            "The Studio module's timers and listeners are cleanly unmounted.\n"
            "The CRM module mounts freshly, queries local SQLite, and renders its table.\n\n"
            "3. Zero Framework Overhead\n"
            "We didn't install React, Vue, or 50MB of npm packages to do this.\n"
            "A clean 80-line vanilla JavaScript ViewController handles view switching and memory cleanup flawlessly.\n\n"
            "The result:\n"
            "- Instantaneous 0ms tab switching\n"
            "- Zero DOM collision bugs\n"
            "- Clean, maintainable code that any engineer can read in 5 minutes\n\n"
            "Build prototypes quickly, but refactor them with discipline.\n\n"
            "How do you keep your frontend codebases clean as they scale?"
        )
        day10_tags = json.dumps(["#softwareArchitecture", "#frontendEngineering", "#cleanCode", "#webDev", "#vanillaJS"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'De-Monolithing the Frontend: Page Bifurcation & Clean State',
            ?, ?, ?, 3, 110, 1, 'The Direct Vulnerability', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day10_content, day10_content, len(day10_content), day10_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day10-{draft_id}", day10_content, day10_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day11_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 11 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Algorithmic Penalties: What Really Suppresses Reach%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day11_content = (
            "Putting external links in the first comment doesn't work anymore.\n\n"
            "We analyzed the reach of 50 posts with external links versus native text.\n\n"
            "Here is what the LinkedIn algorithm actually penalizes in 2026:\n\n"
            "For years, creators shared a \"hack\":\n"
            "\"Don't put links in your post; put the link in the first comment!\"\n\n"
            "Here is why that hack is dead:\n"
            "LinkedIn's feed algorithm now sorts comments by \"Most Relevant.\"\n"
            "Your author comment often gets buried below other replies, making your link virtually invisible.\n\n"
            "So, what does the algorithm actually do with outbound links?\n\n"
            "1. Outbound Link Penalties (-40% Reach)\n"
            "If you place a direct link to an external blog, landing page, or product in your post text, the algorithm suppresses initial impression velocity by ~40%.\n"
            "Why? Because every platform wants to keep users on their site.\n\n"
            "2. Hashtag Stuffing (-25% Reach)\n"
            "Adding 10 generic hashtags (#tech #growth #ai #innovation) looks like spam to LinkedIn's semantic classifier.\n"
            "The sweet spot: 0 to 3 highly specific tags, or none at all.\n\n"
            "3. The True Currency: Dwell Time\n"
            "LinkedIn doesn't just measure likes; it measures how many seconds a user's screen stops scrolling over your post.\n\n"
            "How to optimize for authentic dwell time:\n"
            "- Use clean mobile pacing (1-line hook + blank line + 2-line context)\n"
            "- Format key technical terms with mathematical sans-bold Unicode\n"
            "- Deliver 100% of the value directly in the post, and invite readers to direct message you for external resources\n\n"
            "In Project Prudent, our real-time Algorithm Auditor scans your draft as you type:\n"
            "It flags outbound links, counts hashtags, and checks dwell safety automatically.\n\n"
            "Stop guessing what the algorithm wants; engineer for it.\n\n"
            "Do you still put links in your posts, or keep everything native?"
        )
        day11_tags = json.dumps(["#algorithmOptimization", "#socialSelling", "#dwellTime", "#contentEngineering", "#b2bGrowth"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Algorithmic Penalties: What Really Suppresses Reach in 2026',
            ?, ?, ?, 3, 115, 1, 'The Concrete Proof', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day11_content, day11_content, len(day11_content), day11_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day11-{draft_id}", day11_content, day11_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day12_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 12 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Inbound CRM: Transforming Lurkers%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day12_content = (
            "Stop sending cold connection requests with generic templates.\n\n"
            "The \"Warm Engager\" framework that generates an 82% reply rate from LinkedIn comments:\n\n"
            "Most founders treat LinkedIn like a megaphone:\n"
            "They publish a post, check their vanity impressions, and immediately move on to the next piece of content.\n\n"
            "They completely ignore the most valuable asset:\n"
            "The 15 people who took the time to write a thoughtful comment on their post.\n\n"
            "Those commenters are not cold prospects; they are warm peers who just signaled interest in your expertise.\n\n"
            "Here is how we automate this relationship funnel in Project Prudent:\n\n"
            "1. Passive Lead Capture\n"
            "Whenever you view your post, our local extension passively notes the names, headlines, and specific comments of everyone who engaged.\n"
            "They are added directly to your local desktop CRM.\n\n"
            "2. Zero Spammy Automation\n"
            "We never send automated bulk DMs. Platforms ban bots that do that, and recipients hate them.\n"
            "Instead, we generate a contextual 1-click tailored message template that you review and send personally:\n\n"
            "\"Hey [Name], appreciate your thought on my post about local-first architecture! You mentioned [Specific Point]. Are you exploring sovereign stacks at [Company] as well?\"\n\n"
            "3. The Response Rate Difference\n"
            "- Generic cold outreach: ~12% reply rate\n"
            "- Contextual warm comment follow-up: 82% reply rate\n\n"
            "Vanity impressions do not pay salaries or build companies.\n"
            "Meaningful relationships do.\n\n"
            "How do you turn your social engagement into real-world business connections?"
        )
        day12_tags = json.dumps(["#b2bSales", "#socialSelling", "#leadGen", "#relationshipBuilding", "#crm"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Inbound CRM: Transforming Lurkers into High-Value Conversations',
            ?, ?, ?, 3, 112, 1, 'The Contrarian Confession', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day12_content, day12_content, len(day12_content), day12_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day12-{draft_id}", day12_content, day12_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day13_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 13 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%High-Performance Carousel & Visual Media%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day13_content = (
            "Document carousels generate 3.4x more dwell time than single images on LinkedIn.\n\n"
            "But designing them manually in Canva or Figma takes over an hour.\n\n"
            "Here is the automated visual pipeline we built to compile 10-slide vector PDFs in 3 seconds:\n\n"
            "If you are publishing technical insights on LinkedIn, carousels are unmatched:\n"
            "- Each slide swipe signals strong engagement to the recommendation engine\n"
            "- Complex architectural diagrams have room to breathe across multiple pages\n"
            "- Mobile readers get an interactive, full-screen reading experience\n\n"
            "The problem? Most creators hate making them because manual graphic design is slow and tedious.\n\n"
            "In Project Prudent, we automated the entire carousel pipeline:\n\n"
            "1. Structured Markdown Input\n"
            "You write your slide notes as a simple Markdown list or JSON structure:\n"
            "Slide 1: The Core Thesis\n"
            "Slide 2: The 3 Bottlenecks\n"
            "Slide 3: The Architecture Diagram\n"
            "Slide 4: The Benchmark Results\n\n"
            "2. CSS Swiss Typography Engine\n"
            "We feed the text into an HTML5 template with strict 4:5 vertical proportions (1080px by 1350px):\n"
            "- 'Plus Jakarta Sans' headlines for clean editorial authority\n"
            "- Progress indicator line and dynamic slide counter (e.g. 03 / 08)\n"
            "- Radial dark obsidian gradient backgrounds\n\n"
            "3. Instant Vector PDF Export\n"
            "A local headless print worker renders the slides into a clean, multi-page vector PDF in 2.8 seconds.\n"
            "Zero fuzzy rasterized fonts.\n"
            "Zero expensive Canva subscriptions.\n"
            "Zero cloud rendering fees.\n\n"
            "You write the thoughts. The system handles the typography and export.\n\n"
            "Do you prefer reading text posts or sliding through multi-page carousels?"
        )
        day13_tags = json.dumps(["#contentStrategy", "#carouselDesign", "#visualMedia", "#vectorPDF", "#linkedinTips"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'High-Performance Carousel & Visual Media Systems (4:5 Ratio)',
            ?, ?, ?, 3, 110, 1, 'The Architectural Breakdown', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day13_content, day13_content, len(day13_content), day13_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day13-{draft_id}", day13_content, day13_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day14_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 14 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Automated QA & Browser Testing%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day14_content = (
            "Manual QA is dead for solo software founders.\n\n"
            "Here is how we run fully autonomous browser testing with Playwright to verify our entire application before release:\n\n"
            "When you are a solo developer or running a tiny engineering team, you don't have a dedicated QA department.\n\n"
            "What usually happens?\n"
            "You test the feature you just wrote, hit \"deploy,\" and then wake up to messages from users saying:\n"
            "\"The button on the CRM tab isn't clickable,\" or \"The mobile preview overflows on my screen.\"\n\n"
            "In Project Prudent, we integrated Garry Tan's G-Stack QA Lead methodology:\n\n"
            "Before any release is cut, an automated test runner takes over:\n\n"
            "1. End-to-End User Journey Simulation\n"
            "Using Playwright, the test runner opens a real Chromium instance:\n"
            "- Types a 200-character test draft into the editor\n"
            "- Asserts that the glowing red fold line renders at character 140\n"
            "- Clicks the \"...see more\" button to verify dynamic expansion\n"
            "- Clicks through all 8 bifurcated navigation views to check for DOM leaks\n\n"
            "2. Cross-Resolution Viewport Testing\n"
            "It runs the test suite at two critical resolutions:\n"
            "- 1920x1080 (standard desktop)\n"
            "- 1366x768 (budget laptop screens)\n"
            "Ensuring zero horizontal overflow or clipping issues.\n\n"
            "3. Offline Resilience Verification\n"
            "It simulates an offline network state to guarantee that local SQLite caching operates with zero console errors.\n\n"
            "The entire test suite executes in 14 seconds.\n\n"
            "If any assertion fails, the release script halts immediately.\n\n"
            "Stop testing your software manually like it's 2012.\n"
            "Automate your QA, protect your users' time, and sleep peacefully.\n\n"
            "How do you automate testing in your current projects?"
        )
        day14_tags = json.dumps(["#softwareTesting", "#playwright", "#automatedQA", "#qualityAssurance", "#devOps"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Automated QA & Browser Testing with G-Stack QA Lead',
            ?, ?, ?, 3, 115, 1, 'The Step-by-Step Teardown', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day14_content, day14_content, len(day14_content), day14_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day14-{draft_id}", day14_content, day14_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day15_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 15 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Security & Threat Modeling%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day15_content = (
            "If your desktop app stores API keys in plaintext or binds to 0.0.0.0, you have already failed security 101.\n\n"
            "The 5-point security audit every local developer tool must pass before shipping:\n\n"
            "Building local-first software gives users complete privacy, but it also creates unique security responsibilities.\n\n"
            "When we put Project Prudent through a Chief Security Officer (CSO) audit, these were our 5 non-negotiable security rules:\n\n"
            "1. Strict 127.0.0.1 Loopback Binding\n"
            "If a local Python backend binds to 0.0.0.0, anyone on the same coffee shop Wi-Fi network can ping your local endpoints.\n"
            "We strictly bind to 127.0.0.1, isolating the server to the host machine.\n\n"
            "2. CORS Origin Whitelisting\n"
            "The local API must never accept requests from arbitrary websites.\n"
            "We configure CORS to permit requests exclusively from our verified Chrome extension ID and localhost port.\n\n"
            "3. Zero Cloud Token Egress\n"
            "User drafts, customer leads, and LinkedIn session cookies must never leave local storage.\n"
            "No remote telemetry, no cloud backup databases, no hidden pings.\n\n"
            "4. Encrypted Local Vault\n"
            "API keys for Gemini, Claude, or OpenAI are stored in a protected local SQLite database with restricted OS-level permissions.\n\n"
            "5. Safe Ingestion Guardrails\n"
            "Incoming data payloads from the browser extension are sanitized and validated against Pydantic schemas to prevent SQL injection or cross-site scripting (XSS).\n\n"
            "Privacy is not just a marketing bullet point.\n"
            "It is an architectural promise backed by mathematical verification.\n\n"
            "How do you secure local developer tools on user machines?"
        )
        day15_tags = json.dumps(["#cyberSecurity", "#strideModel", "#dataPrivacy", "#secureByDesign", "#localFirst"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Security & Threat Modeling: The CSO Audit & Localhost Guardrails',
            ?, ?, ?, 3, 118, 1, 'The Concrete Proof', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day15_content, day15_content, len(day15_content), day15_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day15-{draft_id}", day15_content, day15_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day16_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 16 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Packaging & 1-Click Distribution%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day16_content = (
            "The hardest part of shipping software isn't writing the code.\n\n"
            "It is making installation frictionless for non-developers.\n\n"
            "How we reduced our desktop software launch to a single click:\n\n"
            "Most open-source developer tools have terrible onboarding:\n"
            "\"First, install Python 3.11. Then add it to your PATH. Open a terminal. Clone this repo. Create a virtualenv. Run pip install -r requirements.txt. Fix this C++ compiler error. Run uvicorn...\"\n\n"
            "By step 4, 80% of users have given up.\n\n"
            "If you want people to actually use your sovereign software, you have to eliminate every terminal prompt.\n\n"
            "Here is how we packaged Project Prudent for 1-click execution:\n\n"
            "1. The Auto-Detecting Batch Launcher (launch_studio.bat)\n"
            "When the user double-clicks the file:\n"
            "- It checks if Python is installed on the system\n"
            "- It checks if a virtual environment exists; if not, it creates one silently\n"
            "- It runs a quiet pip install -r requirements.txt only if dependencies are missing\n"
            "- It starts the local FastAPI server in the background\n\n"
            "2. Native Desktop Shortcut Generation (create_desktop_shortcut.vbs)\n"
            "A tiny 500-byte VBScript creates a clean desktop icon on the user's desktop with a custom SVG icon.\n\n"
            "3. Automatic Browser Handshake\n"
            "The moment the local server confirms it is healthy on 127.0.0.1:8000:\n"
            "The script automatically opens the user's default browser directly to the Post Studio.\n\n"
            "Total clicks required: 1.\n"
            "Terminal commands typed: 0.\n"
            "Setup time: Under 45 seconds.\n\n"
            "Engineering simplicity is when extreme technical complexity feels effortless to the end user.\n\n"
            "What software installation experience made you smile because of how easy it was?"
        )
        day16_tags = json.dumps(["#developerExperience", "#softwareDistribution", "#packaging", "#uxDesign", "#automation"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Packaging & 1-Click Distribution for Non-Developers',
            ?, ?, ?, 3, 108, 1, 'The Direct Vulnerability', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day16_content, day16_content, len(day16_content), day16_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day16-{draft_id}", day16_content, day16_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def seed_day17_draft(conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    """Seeds Day 17 Launch Kit post into drafts and posts tables if not already present."""
    should_close = False
    if conn is None:
        conn = get_db()
        should_close = True
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM drafts WHERE title LIKE '%Launch Day: The Sovereign Creator Manifesto%'")
        row = cursor.fetchone()
        if row:
            return row[0]

        day17_content = (
            "17 days ago, I set out to build a completely free, privacy-first alternative to $200/month creator software.\n\n"
            "Today, it is live.\n\n"
            "Here is the Sovereign Creator Manifesto:\n\n"
            "For years, the creator software market has been dominated by a single business model:\n"
            "Charge creators a monthly subscription to rent their own data, scrape social feeds with fragile bots, and store private drafts on third-party cloud servers.\n\n"
            "We believed there was a better way:\n"
            "A 100% self-hosted, air-gapped creator operating system running entirely on your local machine.\n\n"
            "Over the past 17 days, we documented every architectural decision:\n"
            "- Why we rejected headless DOM scraping in favor of passive network observation\n"
            "- How we built an Asymmetric Engine that distributes viral trend intelligence via GitHub CDN for $0.00/month\n"
            "- How we decoupled our monolithic prototype into 8 sandboxed page modules\n"
            "- How we automated end-to-end browser testing with Playwright\n"
            "- How we enforced zero cloud data egress and Bring-Your-Own-AI privacy\n\n"
            "Here is what is shipping today in Project Prudent:\n\n"
            "1. Post Studio with real-time mobile feed simulation and fold physics\n"
            "2. High-ranking viral hook radar updated daily\n"
            "3. Inbound commenter and reactor relationship CRM\n"
            "4. Zero-cost multi-page PDF vector carousel generator\n"
            "5. 12ms offline documentation engine powered by SQLite FTS5\n"
            "6. Bring-Your-Own-AI gateway supporting Gemini, Claude, OpenAI, and offline Ollama\n\n"
            "Total cost: $0.00.\n"
            "Cloud servers required: 0.\n"
            "Your data: 100% yours on your hardware.\n\n"
            "The entire project and research repository is open source on GitHub.\n\n"
            "If you believe the future of software belongs to sovereign local tools rather than monthly subscriptions, check the link in the comments or shoot me a DM.\n\n"
            "Thank you to everyone who followed this 17-day journey.\n"
            "This is just Day 1 of what is to come.\n\n"
            "What feature should we build next?"
        )
        day17_tags = json.dumps(["#buildInPublic", "#productLaunch", "#sovereignSoftware", "#openSource", "#manifesto"])
        cursor.execute("""
        INSERT INTO drafts (
            title, raw_content, formatted_content, char_count,
            lines_above_fold, pre_fold_chars, is_pre_fold_safe,
            archetype, tags, status, updated_at
        ) VALUES (
            'Launch Day: The Sovereign Creator Manifesto (17-Day Journey)',
            ?, ?, ?, 3, 114, 1, 'The Contrarian Confession', ?, 'DRAFT', CURRENT_TIMESTAMP
        )
        """, (day17_content, day17_content, len(day17_content), day17_tags))
        draft_id = cursor.lastrowid

        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, status, tags, created_at)
        VALUES (?, ?, 'scheduled', ?, CURRENT_TIMESTAMP)
        """, (f"post-day17-{draft_id}", day17_content, day17_tags))
        conn.commit()
        return draft_id
    finally:
        if should_close:
            conn.close()


def demo_data_enabled() -> bool:
    """
    True when the operator has asked for demo content.

    Everything this gates is content about a person: the author's own drafts
    written in their first person, and four invented personas with pipeline
    states. A real install gets none of it, because a product that opens with
    someone else's campaign already in the queue is telling its new user
    something false about their own work.
    """
    return os.environ.get("INOX_DEMO_DATA", "").strip().lower() in ("1", "true", "yes", "on")


DEMO_SERIES_BASE_DATE = date(2026, 9, 14)
DEMO_SERIES_DAYS = 90


def demo_analytics_rows() -> List[Dict[str, Any]]:
    """
    The exact 90 rows the demo seeder writes.

    Returned rather than inserted so that two callers can share one definition:
    seed_initial_data writes them, and purge_seeded_analytics recognises them.
    A second copy of this arithmetic would drift, and a purge working from a
    drifted copy would either leave fabricated rows behind or delete real ones.
    """
    start_date = DEMO_SERIES_BASE_DATE - timedelta(days=DEMO_SERIES_DAYS - 1)

    current_followers = 2330
    current_connections = 2270
    current_pviews = 70

    rows = []
    for i in range(DEMO_SERIES_DAYS):
        d_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")

        if i % 3 == 0:
            current_followers += 1
        if i % 4 == 0:
            current_connections += 1
        if i % 5 == 0:
            current_pviews = min(120, current_pviews + 1)

        imp = rxn = comm = shr = 0
        spikes = {
            "2026-07-10": (1450, 48, 12, 4),
            "2026-07-28": (620, 22, 5, 1),
            "2026-08-18": (42, 2, 0, 0),
            "2026-08-19": (15, 1, 0, 0),
            "2026-09-09": (303, 10, 2, 0),
            "2026-09-11": (28, 3, 0, 0),
        }
        if d_str in spikes:
            imp, rxn, comm, shr = spikes[d_str]
        elif i % 7 == 2:  # baseline organic impressions
            imp = 12 + (i % 5)
            rxn = 1 if imp > 14 else 0

        rows.append({
            "date": d_str,
            "followers": current_followers,
            "connections": current_connections,
            "profile_views": current_pviews,
            "impressions": imp,
            "reactions": rxn,
            "comments": comm,
            "shares": shr,
            "engagement_rate": round(((rxn + comm + shr) / imp * 100), 2) if imp > 0 else 0.0,
        })
    return rows


# The fields compared when deciding whether a stored row is the seeder's work.
DEMO_MATCH_FIELDS = (
    "followers", "connections", "profile_views",
    "impressions", "reactions", "comments", "shares",
)


def identify_seeded_analytics(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Classify every analytics_daily row against the demo generator.

    A row counts as seeded only when it matches the generator on every field.
    Anything the creator has since captured over differs somewhere and is left
    alone, and a row already marked source='observed' is never a candidate no
    matter what it holds.
    """
    owns = conn is None
    conn = conn or get_db()
    try:
        expected = {r["date"]: r for r in demo_analytics_rows()}
        seeded, modified, observed, unknown = [], [], [], []

        for row in conn.execute("SELECT * FROM analytics_daily ORDER BY date"):
            d = row["date"]
            source = row["source"] if "source" in row.keys() else None
            if source == "observed":
                observed.append(d)
                continue
            want = expected.get(d)
            if want is None:
                unknown.append(d)
                continue
            if all(row[f] == want[f] for f in DEMO_MATCH_FIELDS):
                seeded.append(d)
            else:
                modified.append(d)

        return {
            "seeded": seeded,
            "modified": modified,
            "observed": observed,
            "unknown": unknown,
        }
    finally:
        if owns:
            conn.close()


def purge_seeded_analytics(
    conn: Optional[sqlite3.Connection] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Remove rows that are provably the demo generator's output.

    Provably, not probably: a row is deleted only when every generated field
    matches. This is the one operation in the codebase permitted to delete
    analytics, and it exists because migration 4 deliberately refused to guess
    which pre-existing rows were fabricated. Guessing was the wrong answer for a
    migration that runs on every database; proving it is the right answer for an
    operation the creator asks for.
    """
    owns = conn is None
    conn = conn or get_db()
    try:
        report = identify_seeded_analytics(conn)
        report["dry_run"] = dry_run
        report["deleted"] = 0
        if dry_run or not report["seeded"]:
            return report

        placeholders = ",".join("?" for _ in report["seeded"])
        with conn:
            cur = conn.execute(
                f"DELETE FROM analytics_daily WHERE date IN ({placeholders})",
                report["seeded"],
            )
            report["deleted"] = cur.rowcount
        return report
    finally:
        if owns:
            conn.close()


# The five posts the demo seeder writes. Three of them carry the same
# impression and reaction figures as the analytics spikes (1450/48, 303/10,
# 28/3), which is what gives them away as one fabricated set rather than three
# coincidences.
DEMO_POST_IDS = (
    "post-enterprise-scheduled",
    "post-enterprise-decoupling-scheduled",
    "urn:li:activity:7481319755904303105",
    "urn:li:activity:7503313058338070529",
    "urn:li:activity:7504139397143883776",
)


def demo_demographics_rows() -> List[tuple]:
    """
    The 18 hand-typed audience rows the demo seeder writes.

    Shared with the purge for the same reason as demo_analytics_rows: one
    definition cannot drift away from itself.
    """
    return [
        ("job_title", "Software Engineers & Architects", 34.5),
        ("job_title", "Product Managers & Leaders", 22.8),
        ("job_title", "Content & Strategy Practitioners", 18.2),
        ("job_title", "Founders & Executives", 14.1),
        ("job_title", "Consultants & Enterprise Architects", 10.4),
        ("industry", "IT Services & Consulting", 42.0),
        ("industry", "Software Development & SaaS", 30.5),
        ("industry", "Cloud & Infrastructure Systems", 16.0),
        ("industry", "Financial Services & Fintech", 11.5),
        ("company_size", "10,001+ employees (Enterprise)", 38.2),
        ("company_size", "1,001 - 5,000 employees", 24.5),
        ("company_size", "51 - 200 employees (Scale-up)", 19.3),
        ("company_size", "1 - 10 employees (Startups)", 18.0),
        ("location", "Bengaluru, India", 31.0),
        ("location", "Ahmedabad, India", 26.5),
        ("location", "Mumbai, India", 18.2),
        ("location", "San Francisco Bay Area, US", 12.8),
        ("location", "London, United Kingdom", 11.5),
    ]


def purge_seeded_demographics(
    conn: Optional[sqlite3.Connection] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Remove audience rows that exactly match the demo seeder's hand-typed set.

    These describe an audience the studio has never observed. They reached the
    creator through the data export as well as the API, so a fabricated audience
    breakdown could leave the machine inside a file labelled as their own data.
    """
    owns = conn is None
    conn = conn or get_db()
    try:
        expected = {(d, l): p for d, l, p in demo_demographics_rows()}
        seeded, kept = [], []
        for row in conn.execute("SELECT rowid AS rid, dimension, label, percentage, source FROM audience_demographics"):
            key = (row["dimension"], row["label"])
            if row["source"] == "observed":
                kept.append(key)
            elif key in expected and abs(row["percentage"] - expected[key]) < 1e-9:
                seeded.append(row["rid"])
            else:
                kept.append(key)

        report = {"seeded": len(seeded), "kept": len(kept), "dry_run": dry_run, "deleted": 0}
        if dry_run or not seeded:
            return report

        placeholders = ",".join("?" for _ in seeded)
        with conn:
            cur = conn.execute(
                f"DELETE FROM audience_demographics WHERE rowid IN ({placeholders})",
                seeded,
            )
            report["deleted"] = cur.rowcount
        return report
    finally:
        if owns:
            conn.close()


def purge_seeded_posts(
    conn: Optional[sqlite3.Connection] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Remove the demo posts, which carry invented impression and reaction counts.

    Matched by id rather than by content: these ids are the seeder's own, and a
    post the creator actually wrote never has one.
    """
    owns = conn is None
    conn = conn or get_db()
    try:
        placeholders = ",".join("?" for _ in DEMO_POST_IDS)
        rows = conn.execute(
            f"SELECT id FROM posts WHERE id IN ({placeholders})", DEMO_POST_IDS
        ).fetchall()
        found = [r["id"] for r in rows]

        report = {"seeded": found, "dry_run": dry_run, "deleted": 0}
        if dry_run or not found:
            return report

        with conn:
            cur = conn.execute(
                f"DELETE FROM posts WHERE id IN ({placeholders})", DEMO_POST_IDS
            )
            report["deleted"] = cur.rowcount
        return report
    finally:
        if owns:
            conn.close()


def purge_all_seeded_data(
    conn: Optional[sqlite3.Connection] = None,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Remove every row this codebase can prove it fabricated.

    Deliberately narrow. It deletes what matches a definition in this file and
    nothing else, so a row the creator captured is never at risk even when it
    sits beside one that was invented.
    """
    owns = conn is None
    conn = conn or get_db()
    try:
        return {
            "analytics": purge_seeded_analytics(conn, dry_run=dry_run),
            "demographics": purge_seeded_demographics(conn, dry_run=dry_run),
            "posts": purge_seeded_posts(conn, dry_run=dry_run),
            "dry_run": dry_run,
        }
    finally:
        if owns:
            conn.close()


def seed_initial_data():
    conn = get_db()
    cursor = conn.cursor()

    # Seed Days 02 through 17 Launch Kit drafts. Demo content, same reason as
    # the Days 02 to 08 block in init_db. Both call sites are gated: gating one
    # leaves the behaviour reachable through the other.
    if demo_data_enabled():
        seed_day02_draft(conn)
        seed_day03_draft(conn)
        seed_day04_draft(conn)
        seed_day05_draft(conn)
        seed_day06_draft(conn)
        seed_day07_draft(conn)
        seed_day08_draft(conn)
        seed_day09_draft(conn)
        seed_day10_draft(conn)
        seed_day11_draft(conn)
        seed_day12_draft(conn)
        seed_day13_draft(conn)
        seed_day14_draft(conn)
        seed_day15_draft(conn)
        seed_day16_draft(conn)
        seed_day17_draft(conn)

    # Check if leads need seeding. Demo content: four invented people with
    # pipeline states, one of them at "Meeting Booked", which registers as a
    # real conversion now that the funnel works.
    if demo_data_enabled():
        cursor.execute("SELECT COUNT(*) FROM leads")
        seed_sample_leads = cursor.fetchone()[0] == 0
    else:
        seed_sample_leads = False
    if seed_sample_leads:
        sample_leads = [
            ("lead-1", "Aravind Subramanian", "VP of Engineering at CloudScale", "CloudScale", "https://linkedin.com/in/aravind-sub", "Commented", "post-enterprise-scheduled", "New Lead", "Interested in ERP observability architecture"),
            ("lead-2", "Sarah Jenkins", "Director of Product Architecture", "Fintech Nexus", "https://linkedin.com/in/sarah-jenkins-lead", "Liked", "urn:li:activity:7503313058338070529", "Connected", "Engaged with content strategy breakdown"),
            ("lead-3", "Rohan Mehta", "Principal Enterprise Architect", "Global Tech Systems", "https://linkedin.com/in/rohan-mehta-lead", "Commented", "post-enterprise-scheduled", "Outreach Sent", "Exchanged notes on clean data boundaries"),
            ("lead-4", "Elena Rostova", "Head of Content & DevRel", "SaaS Matrix", "https://linkedin.com/in/elena-rostova-lead", "Reposted", "urn:li:activity:7481319755904303105", "Meeting Booked", "Invited to discuss agentic AI workflows")
        ]
        for l in sample_leads:
            cursor.execute("""
            INSERT OR REPLACE INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, l)
        conn.commit()

    # Fabricated observations are opt-in.
    #
    # analytics_daily and audience_demographics describe the creator's real
    # LinkedIn account. Generating them meant every chart, KPI, range pill and
    # CSV export on a fresh install was fiction that rendered identically to
    # captured data, and the DELETE below destroyed genuinely captured rows
    # whenever there were fewer than sixty of them.
    #
    # queue_slots are different in kind and still seed unconditionally: they are
    # default posting times, not claims about anything that happened. They carry
    # no measurement and assert nothing, so a default is honest there.
    seed_demo_metrics = os.environ.get("INOX_DEMO_DATA", "").strip().lower() in ("1", "true", "yes", "on")

    cursor.execute("SELECT COUNT(*) FROM analytics_daily")
    count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM audience_demographics")
    demo_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM queue_slots")
    slots_count = cursor.fetchone()[0]

    if not seed_demo_metrics:
        # Real rows are never deleted. An empty table is the honest state of a
        # studio that has not captured anything yet.
        count = max(count, 60)
        demo_count = max(demo_count, 14)

    if count >= 60 and demo_count >= 14 and slots_count >= 8:
        conn.commit()
        conn.close()
        return

    if seed_demo_metrics and count < 60:
        cursor.execute("DELETE FROM analytics_daily WHERE source = 'seed' OR source IS NULL")
    if seed_demo_metrics and demo_count < 14:
        cursor.execute("DELETE FROM audience_demographics WHERE source = 'seed' OR source IS NULL")
    if slots_count < 8:
        cursor.execute("DELETE FROM queue_slots")

    if seed_demo_metrics:
        print("INOX_DEMO_DATA is set: seeding 90 days of FABRICATED analytics and demographics.")

    # Generate the demo series from the shared definition, so the purge that
    # recognises these rows and the seeder that writes them can never disagree.
    if count < 60:
        cursor.executemany("""
        INSERT OR REPLACE INTO analytics_daily
        (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate, source)
        VALUES (:date, :followers, :connections, :profile_views, :impressions, :reactions, :comments, :shares, :engagement_rate, 'seed')
        """, demo_analytics_rows())

    # Seed Posts
    posts_data = [
        (
            SEEDED_DEMO_POST_IDS[0],
            """𝗦𝘁𝗲𝗽𝗽𝗶𝗻𝗴 𝗶𝗻𝘁𝗼 𝗲𝗻𝘁𝗲𝗿𝗽𝗿𝗶𝘀𝗲 𝘀𝘆𝘀𝘁𝗲𝗺𝘀 𝗳𝗲𝗲𝗹𝘀 𝗹𝗶𝗸𝗲 𝗹𝗲𝗮𝗿𝗻𝗶𝗻𝗴 𝗮 𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲𝗹𝘆 𝗻𝗲𝘄 𝗹𝗮𝗻𝗴𝘂𝗮𝗴𝗲.

Lately, I’ve been spending my time doing something humbling:

Going back to the foundational drawing board to dive deep into enterprise architectures and modern ERP systems.

During my time at Motadata, my world was shaped by 𝗜𝗧 𝗢𝗯𝘀𝗲𝗿𝘃𝗮𝗯𝗶𝗹𝗶𝘁𝘆 and 𝗜𝗧 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 𝗠𝗮𝗻𝗮𝗴𝗲𝗺𝗲𝗻𝘁 (𝗜𝗧𝗦𝗠)...""",
            # No media. This previously referenced a bare filename, which the
            # browser resolved against the site root and served a 404. The image
            # lives in the repository's assets/ directory, which is not the
            # directory mounted at /assets (that one holds user media), and it is
            # not shipped in the distributable. A seeded demo post showing a
            # broken image is worse than one showing none.
            json.dumps([]),
            "scheduled",
            "2026-09-14T12:00:00.000Z",
            None,
            0, 0, 0, 0,
            json.dumps(["Enterprise", "ERP", "Observability", "SystemsArchitecture"])
        ),
        (
            "urn:li:activity:7504139397143883776",
            """𝗭𝗲𝗿𝗼 𝗺𝗮𝗻𝘂𝗮𝗹 𝗶𝗻𝘁𝗲𝗿𝘃𝗲𝗻𝘁𝗶𝗼𝗻.

That is the only AI metric that actually matters.

Not how many slides your team made.
Not which frontier model you pay for.
And definitely not how fast someone types prompts into ChatGPT...""",
            json.dumps(["https://ez4cast.s3.eu-west-1.amazonaws.com/userUpload/lENLQl9eFD"]),
            "published",
            None,
            "2026-09-11T11:30:53.996Z",
            28, 3, 0, 0,
            json.dumps(["AI", "Automation", "Workflows"])
        ),
        (
            "urn:li:activity:7503313058338070529",
            """“Content Strategist” sounds like a quiet title for a very loud job.

For a while, I was the person responsible for content strategy across a B2B Product ecosystem with 12+ modules spanning IT Service Management and IT Observability...""",
            json.dumps([]),
            "published",
            None,
            "2026-09-09T04:47:17.923Z",
            303, 10, 2, 0,
            json.dumps(["Career", "B2B", "ProductMarketing", "Systems"])
        ),
        (
            "urn:li:activity:7481319755904303105",
            """I just wrapped my internship at Motadata and for almost all of it, nearly everything I built went through an AI agent before it reached a human.

Three different coding agents. Around many projects on content and SEO systems for the marketing team...""",
            json.dumps([]),
            "published",
            None,
            "2026-07-10T12:13:46.007Z",
            1450, 48, 12, 4,
            json.dumps(["AI", "AgenticAI", "SoftwareEngineering", "Building"])
        ),
        (
            "post-enterprise-decoupling-scheduled",
            """𝗠𝗼𝘀𝘁 𝗲𝗻𝘁𝗲𝗿𝗽𝗿𝗶𝘀𝗲 𝗺𝗶𝗰𝗿𝗼𝘀𝗲𝗿𝘃𝗶𝗰𝗲𝘀 𝗮𝗿𝗲 𝗷𝘂𝘀𝘁 𝗱𝗶𝘀𝘁𝗿𝗶𝗯𝘂𝘁𝗲𝗱 𝗺𝗼𝗻𝗼𝗹𝗶𝘁𝗵𝘀 𝗶𝗻 𝗱𝗶𝘀𝗴𝘂𝗶𝘀𝗲.

If one database table change cascades failures across 4 downstream services, you do not have decoupled systems. You have distributed tight coupling with network latency added on top.

Lately, as I dive deeper into enterprise architectures and modern ERP platforms, one realization keeps surfacing:

True decoupling is not about breaking code into separate repositories.
It is about establishing pure event-driven boundaries.

Here is the 3-step blueprint for genuine enterprise decoupling:

1. 𝗣𝘂𝗿𝗲 𝗜𝗺𝗺𝘂𝘁𝗮𝗯𝗹𝗲 𝗘𝘃𝗲𝗻𝘁 𝗦𝘁𝗿𝗲𝗮𝗺𝘀: Treat state transitions as append-only immutable events, never shared database schemas.
2. 𝗖𝗼𝗻𝘀𝘂𝗺𝗲𝗿-𝗢𝘄𝗻𝗲𝗱 𝗣𝗿𝗼𝗷𝗲𝗰𝘁𝗶𝗼𝗻𝘀: Each service builds and owns its isolated read models tailored specifically to its query patterns.
3. 𝗩𝗲𝗿𝗶𝗳𝗶𝗰𝗮𝘁𝗶𝗼𝗻 𝗢𝘃𝗲𝗿 𝗔𝘀𝘀𝘂𝗺𝗽𝘁𝗶𝗼𝗻: Validate data boundary contracts programmatically before deploying changes to production.

When you decouple domain state from operational execution, system resilience compounds automatically.

Swipe through the companion 3-slide visual architecture guide below.

What is your team's biggest bottleneck when decoupling legacy services?""",
            json.dumps(["/assets/enterprise_decoupling_carousel.pdf"]),
            "scheduled",
            "2026-09-16T12:00:00.000Z",
            None,
            0, 0, 0, 0,
            json.dumps(["Enterprise", "Architecture", "DistributedSystems", "EventDriven"])
        )
    ]

    # These carry hardcoded impression and reaction counts, so they are
    # fabricated observations exactly like the analytics rows and belong behind
    # the same flag. Without this, the Recent Post Trajectory table showed 1,450
    # impressions on a post the creator never wrote, immediately below a KPI
    # strip that was honestly reporting that it knew nothing.
    if seed_demo_metrics:
        for p in posts_data:
            cursor.execute("""
            INSERT OR REPLACE INTO posts (id, content, media_urls, status, scheduled_for, published_at, impressions, reactions, comments, shares, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, p)

    # Seed Demographics from the shared definition, so the purge that
    # recognises these rows and the seeder that writes them cannot disagree.
    if demo_count < 14:
        cursor.executemany(
            "INSERT INTO audience_demographics (dimension, label, percentage, source) VALUES (?, ?, ?, 'seed')",
            demo_demographics_rows(),
        )

    # Seed Default Smart Queue Slots
    if slots_count < 8:
        default_slots = [
            (0, "08:30", "Monday Morning Kickoff", 1),
            (0, "17:30", "Monday Evening Read", 1),
            (1, "08:30", "Tuesday Peak Hook", 1),
            (1, "17:30", "Tuesday Evening Thought", 1),
            (2, "08:30", "Wednesday Midweek Deep-Dive", 1),
            (2, "17:30", "Wednesday Systems Review", 1),
            (3, "08:30", "Thursday Architecture Playbook", 1),
            (3, "17:30", "Thursday Evening Pulse", 1),
            (4, "09:00", "Friday Weekly Retrospective", 1),
            (5, "10:30", "Saturday Deep Thinking", 1),
            (6, "11:00", "Sunday Career & Strategy", 1)
        ]
        for s in default_slots:
            cursor.execute("INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?, ?, ?, ?)", s)

    # Seed Inspirations
    # Five posts used to be seeded here, attributed to Dan Koe, Sahil Bloom,
    # Garry Tan, Shreyas Doshi and Alex Hormozi, with invented engagement counts
    # of 4,200 to 15,300.
    #
    # Deleted outright rather than gated behind the demo flag, unlike the
    # author's own drafts and the invented personas. Those fabricate the user's
    # own numbers or describe people who do not exist. These put words in the
    # mouths of real, identifiable people and attach metrics to posts they never
    # wrote, and no flag makes that acceptable to ship or to demonstrate.
    #
    # The swipe file is not left empty by this: 36 hand-authored hook templates
    # seed into viral_templates, which is the table the feature actually reads.

    # Seed Initial Leads & Engagers CRM. The second of two identical blocks,
    # gated for the same reason as the first.
    if demo_data_enabled():
        cursor.execute("SELECT COUNT(*) FROM leads")
        needs_leads = cursor.fetchone()[0] == 0
    else:
        needs_leads = False
    if needs_leads:
        sample_leads = [
            ("lead-1", "Aravind Subramanian", "VP of Engineering at CloudScale", "CloudScale", "https://linkedin.com/in/aravind-sub", "Commented", "post-enterprise-scheduled", "New Lead", "Interested in ERP observability architecture"),
            ("lead-2", "Sarah Jenkins", "Director of Product Architecture", "Fintech Nexus", "https://linkedin.com/in/sarah-jenkins-lead", "Liked", "urn:li:activity:7503313058338070529", "Connected", "Engaged with content strategy breakdown"),
            ("lead-3", "Rohan Mehta", "Principal Enterprise Architect", "Global Tech Systems", "https://linkedin.com/in/rohan-mehta-lead", "Commented", "post-enterprise-scheduled", "Outreach Sent", "Exchanged notes on clean data boundaries"),
            ("lead-4", "Elena Rostova", "Head of Content & DevRel", "SaaS Matrix", "https://linkedin.com/in/elena-rostova-lead", "Reposted", "urn:li:activity:7481319755904303105", "Meeting Booked", "Invited to discuss agentic AI workflows")
        ]
        for l in sample_leads:
            cursor.execute("""
            INSERT OR REPLACE INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, l)

    # Seed Sample Lead Enrichment if empty. Describes one of the invented
    # people above, so it goes with them.
    if demo_data_enabled():
        cursor.execute("SELECT COUNT(*) FROM lead_enrichments")
        seed_enrichment = cursor.fetchone()[0] == 0
    else:
        seed_enrichment = False
    if seed_enrichment:
        cursor.execute("""
        INSERT OR REPLACE INTO lead_enrichments 
        (lead_id, company_intelligence, estimated_tech_stack, key_topics, friction_points, icebreakers, enriched_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "lead-1",
            "CloudScale is a high-growth cloud infrastructure and observability company. Scaled to 500+ enterprise clients requiring low-latency telemetry pipelines.",
            "Kubernetes, Kafka, Go, OpenTelemetry, ClickHouse, Distributed Event Streams",
            json.dumps(["Event-Driven Decoupling", "Distributed Tracing", "Zero-Downtime Migration", "IT Observability"]),
            "High database connection contention between operational transactions and analytical query projections across microservices.",
            json.dumps([
                "Noticed CloudScale is pushing deep into observability telemetry. How are your teams handling projection latency when decoupling microservice write paths?",
                "Loved your take on systems architecture. We recently analyzed how event-driven decoupling cuts MTTR by 40% across distributed services. Would love your perspective.",
                "Hey Aravind, putting together a technical teardown on zero-downtime schema evolution in high-scale cloud platforms. Happy to share an early draft if relevant."
            ]),
            "agno_local"
        ))

    # Initial settings
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'ready')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_sync_interval_mins', '60')")

    conn.commit()
    conn.close()
    print("Seeding completed successfully!")


def checkpoint_db() -> Dict[str, Any]:
    """Truncates and checkpoints WAL file to keep disk footprint minimal."""
    with _db_write_lock:
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            res = cursor.fetchone()
            return {
                "status": "checkpointed",
                "busy": res[0],
                "log": res[1],
                "checkpointed": res[2]
            }
        finally:
            conn.close()


def create_draft(
    raw_content: str,
    title: Optional[str] = None,
    formatted_content: Optional[str] = None,
    char_count: int = 0,
    lines_above_fold: int = 0,
    pre_fold_chars: int = 0,
    is_pre_fold_safe: bool = True,
    archetype: str = "Direct",
    tags: Optional[List[str]] = None,
) -> int:
    """Insert a draft into the sovereign store under thread-safe write lock."""
    tags_json = json.dumps(tags or [])
    with _db_write_lock:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO drafts (
                title, raw_content, formatted_content, char_count,
                lines_above_fold, pre_fold_chars, is_pre_fold_safe,
                archetype, tags, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', CURRENT_TIMESTAMP)
            """,
            (
                title,
                raw_content,
                formatted_content or raw_content,
                char_count or len(raw_content),
                lines_above_fold,
                pre_fold_chars,
                1 if is_pre_fold_safe else 0,
                archetype,
                tags_json,
            ),
        )
        draft_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return draft_id


def get_draft(draft_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve a single draft by ID."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
        d["is_pre_fold_safe"] = bool(d["is_pre_fold_safe"])
        return d
    return None


def list_drafts(limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List drafts with optional status filter."""
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute(
            "SELECT * FROM drafts WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
            (status, limit),
        )
    else:
        cursor.execute(
            "SELECT * FROM drafts ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
    rows = cursor.fetchall()
    conn.close()
    results = []
    for row in rows:
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
        d["is_pre_fold_safe"] = bool(d["is_pre_fold_safe"])
        results.append(d)
    return results


def schedule_draft(draft_id: int, scheduled_at: str, channel: str = "linkedin") -> int:
    """Schedule a draft for automatic local queueing under thread-safe write lock."""
    with _db_write_lock:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO queue_items (draft_id, scheduled_at, status, channel)
            VALUES (?, ?, 'PENDING', ?)
            """,
            (draft_id, scheduled_at, channel),
        )
        queue_id = cursor.lastrowid
        cursor.execute(
            "UPDATE drafts SET status = 'QUEUED', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (draft_id,),
        )
        conn.commit()
        conn.close()
        return queue_id


if __name__ == "__main__":
    init_db()
    seed_initial_data()


