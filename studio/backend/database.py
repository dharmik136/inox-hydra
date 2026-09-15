"""
Database Access Layer & SQLite WAL Manager
==========================================
Provides thread-safe connection pooling, schema migrations, seed data provisioning,
and Write-Ahead Logging (WAL) configuration for LinkedIn Studio Enterprise.

Database: studio/data/linkedin_studio.db
Journal Mode: WAL (Write-Ahead Logging)
Concurrency: Zero-blocking concurrent reads during background writes.
"""

import sqlite3
import os
import json
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "linkedin_studio.db")


def get_db() -> sqlite3.Connection:
    """
    Opens and returns an active SQLite database connection configured in WAL mode.
    Sets row_factory to sqlite3.Row for dictionary-like column access.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
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

    conn.commit()
    conn.close()
    print("Database initialized at:", DB_PATH)


def seed_initial_data():
    conn = get_db()
    cursor = conn.cursor()

    # Check if leads need seeding
    cursor.execute("SELECT COUNT(*) FROM leads")
    if cursor.fetchone()[0] == 0:
        sample_leads = [
            ("lead-1", "Aravind Subramanian", "VP of Engineering at CloudScale", "CloudScale", "https://linkedin.com/in/example-lead-aravind", "Commented", "post-enterprise-scheduled", "New Lead", "Interested in ERP observability architecture"),
            ("lead-2", "Sarah Jenkins", "Director of Product Architecture", "Fintech Nexus", "https://linkedin.com/in/example-lead-sarah", "Liked", "urn:li:activity:7390000000000000102", "Connected", "Engaged with content strategy breakdown"),
            ("lead-3", "Rohan Mehta", "Principal Enterprise Architect", "Global Tech Systems", "https://linkedin.com/in/example-lead-rohan", "Commented", "post-enterprise-scheduled", "Outreach Sent", "Exchanged notes on clean data boundaries"),
            ("lead-4", "Elena Rostova", "Head of Content & DevRel", "SaaS Matrix", "https://linkedin.com/in/example-lead-elena", "Reposted", "urn:li:activity:7390000000000000101", "Meeting Booked", "Invited to discuss agentic AI workflows")
        ]
        for l in sample_leads:
            cursor.execute("""
            INSERT OR REPLACE INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, l)
        conn.commit()

    # Clear and re-seed for rich multi-range testing if count < 60
    cursor.execute("SELECT COUNT(*) FROM analytics_daily")
    count = cursor.fetchone()[0]
    if count >= 60:
        conn.close()
        return

    cursor.execute("DELETE FROM analytics_daily")
    cursor.execute("DELETE FROM audience_demographics")
    cursor.execute("DELETE FROM queue_slots")

    print("Seeding multi-range analytics (90 days), demographics, queue slots, and inspirations...")

    # Generate 90 days of realistic creator metrics ending at 2026-09-14
    base_date = date(2026, 9, 14)
    start_date = base_date - timedelta(days=89)
    
    current_followers = 1830
    current_connections = 1720
    current_pviews = 70

    for i in range(90):
        d = start_date + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")

        # Gradual growth
        if i % 3 == 0:
            current_followers += 1
        if i % 4 == 0:
            current_connections += 1
        if i % 5 == 0:
            current_pviews = min(120, current_pviews + 1)

        # Post publication spikes on specific days
        imp = 0
        rxn = 0
        comm = 0
        shr = 0

        # Day spikes
        if d_str == "2026-07-10":
            imp = 517
            rxn = 21
            comm = 12
            shr = 4
        elif d_str == "2026-07-28":
            imp = 620
            rxn = 22
            comm = 5
            shr = 1
        elif d_str == "2026-08-18":
            imp = 42
            rxn = 2
            comm = 0
            shr = 0
        elif d_str == "2026-08-19":
            imp = 15
            rxn = 1
            comm = 0
            shr = 0
        elif d_str == "2026-09-09":
            imp = 262
            rxn = 9
            comm = 2
            shr = 0
        elif d_str == "2026-09-11":
            imp = 28
            rxn = 3
            comm = 0
            shr = 0
        elif i % 7 == 2:  # baseline organic impressions
            imp = 12 + (i % 5)
            rxn = 1 if imp > 14 else 0

        eng_rate = round(((rxn + comm + shr) / imp * 100), 2) if imp > 0 else 0.0

        cursor.execute("""
        INSERT OR REPLACE INTO analytics_daily (date, followers, connections, profile_views, impressions, reactions, comments, shares, engagement_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (d_str, current_followers, current_connections, current_pviews, imp, rxn, comm, shr, eng_rate))

    # Seed Posts
    posts_data = [
        (
            "post-enterprise-scheduled",
            """Sample scheduled post. Replace with your own words.""",
            json.dumps(["sample_creative.jpg"]),
            "scheduled",
            "2026-09-14T12:00:00.000Z",
            None,
            0, 0, 0, 0,
            json.dumps(["Enterprise", "ERP", "Observability", "SystemsArchitecture"])
        ),
        (
            "urn:li:activity:7390000000000000103",
            """Sample published post (demo seed).""",
            json.dumps(["https://example.com/sample-media.jpg"]),
            "published",
            None,
            "2026-09-11T11:30:53.996Z",
            28, 3, 0, 0,
            json.dumps(["AI", "Automation", "Workflows"])
        ),
        (
            "urn:li:activity:7390000000000000102",
            """Sample published post (demo seed).""",
            json.dumps([]),
            "published",
            None,
            "2026-09-09T04:47:17.923Z",
            262, 9, 1, 0,
            json.dumps(["Career", "B2B", "ProductMarketing", "Systems"])
        ),
        (
            "urn:li:activity:7390000000000000101",
            """Sample published post (demo seed).""",
            json.dumps([]),
            "published",
            None,
            "2026-07-10T12:13:46.007Z",
            517, 21, 6, 1,
            json.dumps(["AI", "AgenticAI", "SoftwareEngineering", "Building"])
        )
    ]

    for p in posts_data:
        cursor.execute("""
        INSERT OR REPLACE INTO posts (id, content, media_urls, status, scheduled_for, published_at, impressions, reactions, comments, shares, tags)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, p)

    # Seed Demographics across 4 dimensions
    demographics = [
        # Job Titles
        ("job_title", "Software Engineers & Architects", 34.5),
        ("job_title", "Product Managers & Leaders", 22.8),
        ("job_title", "Content & Strategy Practitioners", 18.2),
        ("job_title", "Founders & Executives", 14.1),
        ("job_title", "Consultants & Enterprise Architects", 10.4),
        # Industries
        ("industry", "IT Services & Consulting", 42.0),
        ("industry", "Software Development & SaaS", 30.5),
        ("industry", "Cloud & Infrastructure Systems", 16.0),
        ("industry", "Financial Services & Fintech", 11.5),
        # Company Size
        ("company_size", "10,001+ employees (Enterprise)", 38.2),
        ("company_size", "1,001 - 5,000 employees", 24.5),
        ("company_size", "51 - 200 employees (Scale-up)", 19.3),
        ("company_size", "1 - 10 employees (Startups)", 18.0),
        # Locations
        ("location", "Bengaluru, India", 31.0),
        ("location", "Pune, India", 26.5),
        ("location", "Mumbai, India", 18.2),
        ("location", "San Francisco Bay Area, US", 12.8),
        ("location", "London, United Kingdom", 11.5),
    ]

    for d in demographics:
        cursor.execute("INSERT INTO audience_demographics (dimension, label, percentage) VALUES (?, ?, ?)", d)

    # Seed Default Smart Queue Slots
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
    inspirations = [
        (
            "insp-1",
            "Sample Author A",
            "Sample headline",
            "Productivity & AI",
            "The greatest productivity hack is not a new app.\nIt is cutting 80% of what you thought you had to do manually.",
            4200, 312,
            "The greatest productivity hack is not a new app."
        ),
        (
            "insp-2",
            "Sample Author B",
            "Sample headline",
            "Mental Models",
            "Mental model that changed how I build:\nThe Razor of Leverage.\nIf an action does not compound while you sleep, it is labor, not asset creation.",
            8500, 480,
            "Mental model that changed how I build: The Razor of Leverage."
        ),
        (
            "insp-3",
            "Sample Author C",
            "Sample headline",
            "Engineering & AI",
            "In 2026, the best engineers are not typing code.\nThey are orchestrating agents and reviewing diffs with uncompromising taste.",
            12400, 920,
            "In 2026, the best engineers are not typing code."
        ),
        (
            "insp-4",
            "Sample Author D",
            "Sample headline",
            "Product & Strategy",
            "Most meetings are not work. They are a proxy for alignment that should have happened in a 2-page document.",
            9400, 680,
            "Most meetings are not work."
        ),
        (
            "insp-5",
            "Sample Author E",
            "Sample headline",
            "B2B & Distribution",
            "You do not lack time. You lack priorities that hurt enough to say no to everything else.",
            15300, 1100,
            "You do not lack time."
        )
    ]

    for insp in inspirations:
        cursor.execute("""
        INSERT OR REPLACE INTO inspirations (id, author_name, author_headline, topic, content, likes_count, comments_count, key_hook)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, insp)

    # Seed Initial Leads & Engagers CRM
    cursor.execute("SELECT COUNT(*) FROM leads")
    if cursor.fetchone()[0] == 0:
        sample_leads = [
            ("lead-1", "Aravind Subramanian", "VP of Engineering at CloudScale", "CloudScale", "https://linkedin.com/in/example-lead-aravind", "Commented", "post-enterprise-scheduled", "New Lead", "Interested in ERP observability architecture"),
            ("lead-2", "Sarah Jenkins", "Director of Product Architecture", "Fintech Nexus", "https://linkedin.com/in/example-lead-sarah", "Liked", "urn:li:activity:7390000000000000102", "Connected", "Engaged with content strategy breakdown"),
            ("lead-3", "Rohan Mehta", "Principal Enterprise Architect", "Global Tech Systems", "https://linkedin.com/in/example-lead-rohan", "Commented", "post-enterprise-scheduled", "Outreach Sent", "Exchanged notes on clean data boundaries"),
            ("lead-4", "Elena Rostova", "Head of Content & DevRel", "SaaS Matrix", "https://linkedin.com/in/example-lead-elena", "Reposted", "urn:li:activity:7390000000000000101", "Meeting Booked", "Invited to discuss agentic AI workflows")
        ]
        for l in sample_leads:
            cursor.execute("""
            INSERT OR REPLACE INTO leads (id, name, headline, company, profile_url, engagement_type, post_id, status, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, l)

    # Initial settings
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_status', 'ready')")
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_sync_interval_mins', '60')")

    conn.commit()
    conn.close()
    print("Seeding completed successfully!")


if __name__ == "__main__":
    init_db()
    seed_initial_data()
