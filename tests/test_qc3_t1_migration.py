"""
Migration 26: nothing the creator wrote is lost, and nothing is duplicated.
===========================================================================

The migration has to take four tables that disagreed and leave one record,
with a row written by each historical path landing in exactly one place:

  a publication the studio already had a post for      keeps that post
  a publication whose text matches one unbound post    binds to it
  a publication with nothing to match                  gets a post of its own
  a publication with no text at all                    gets a post of its own
  a draft the legacy store held alone                  gets a post
  a draft whose queue row held a slot                  keeps the slot
  a draft whose text a post already holds              is left alone
  a post written here and never published              is left alone

It is rehearsed on a copy of the three year dataset, timed, in the batch
report. Here the same proof is made row by row, so the suite keeps it.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import migrations
import post_identity

OLD = "2024-03-05T09:00:00+00:00"

# Four openings long enough to fingerprint, and distinct from each other.
BOUND = "The outage we caused ourselves by trusting a dashboard that read from the cluster it watched."
MATCHES_A_POST = "The quarter we stopped counting story points and started counting released changes."
NO_MATCH = "A post from three years ago that this studio never held a draft of, and never will."
A_DRAFT = "A draft I wrote on the train and never posted, which is still mine and should be visible."
QUEUED = "A draft that was queued for a Tuesday morning slot and went out from the queue."
PUBLISHED_DRAFT = "A draft the old queue marked published, with the time it went out beside it."
SEEDED = "A draft the demo seeder wrote, with a posts row beside it holding the very same text."
UNPUBLISHED = "A post written here that has never gone out, and must stay exactly as it is."

# The schema as it stood at version 25, reduced to the tables this migration
# reads and writes. Built by hand rather than from init_db, because init_db no
# longer creates the dead queue this migration drops.
_SCHEMA = (
    """
    CREATE TABLE posts (
        id TEXT PRIMARY KEY, content TEXT NOT NULL, media_urls TEXT, status TEXT DEFAULT 'draft',
        scheduled_for TEXT, published_at TEXT, impressions INTEGER DEFAULT 0, reactions INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0, tags TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, activity_urn TEXT, content_fingerprint TEXT,
        draft_id INTEGER
    )
    """,
    "CREATE UNIQUE INDEX idx_posts_activity_urn ON posts(activity_urn) WHERE activity_urn IS NOT NULL",
    """
    CREATE TABLE own_posts (
        activity_urn TEXT PRIMARY KEY, text TEXT, published_at TEXT, published_at_source TEXT,
        reactions INTEGER, comments INTEGER, reposts INTEGER, impressions INTEGER,
        first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, raw_content TEXT NOT NULL, formatted_content TEXT,
        char_count INTEGER DEFAULT 0, lines_above_fold INTEGER DEFAULT 0, pre_fold_chars INTEGER DEFAULT 0,
        is_pre_fold_safe INTEGER DEFAULT 1, archetype TEXT DEFAULT 'Direct', tags TEXT DEFAULT '[]',
        status TEXT DEFAULT 'DRAFT', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE queue_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, draft_id INTEGER NOT NULL, scheduled_at TIMESTAMP NOT NULL,
        published_at TIMESTAMP, status TEXT DEFAULT 'PENDING', channel TEXT DEFAULT 'linkedin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(draft_id) REFERENCES drafts(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX idx_queue_scheduled ON queue_items(scheduled_at, status)",
    """
    CREATE TABLE lead_interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL, post_urn TEXT,
        interaction_type TEXT NOT NULL, interacted_at TIMESTAMP
    )
    """,
    "CREATE TABLE post_engagement (post_urn TEXT PRIMARY KEY, people INTEGER DEFAULT 0, stale INTEGER DEFAULT 0)",
)


def _urn(n):
    return f"urn:li:activity:73900000000000000{n:02d}"


@pytest.fixture
def before(tmp_path):
    """One database holding a row from every historical write path."""
    conn = sqlite3.connect(tmp_path / "studio.db")
    conn.row_factory = sqlite3.Row
    for statement in _SCHEMA:
        conn.execute(statement)

    def own(urn, text, source="urn_decode"):
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, published_at_source, "
                     "first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?, ?)",
                     (urn, text, OLD, source, OLD, OLD))

    def post(post_id, content, status="draft", urn=None, draft_id=None, created_at=OLD):
        conn.execute("INSERT INTO posts (id, content, status, activity_urn, draft_id, created_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (post_id, content, status, urn, draft_id, created_at))

    def draft(content, status="DRAFT", created_at=OLD):
        return conn.execute("INSERT INTO drafts (title, raw_content, status, created_at) VALUES (?, ?, ?, ?)",
                            (content[:20], content, status, created_at)).lastrowid

    # 1. A publication the studio already has a post for.
    own(_urn(1), BOUND)
    post("post-bound", BOUND, status="published", urn=_urn(1))
    # 2. A publication whose text matches one unbound post, marked published
    #    by the creator the way "Mark as published" does.
    own(_urn(2), MATCHES_A_POST)
    post("post-marked", MATCHES_A_POST, status="published")
    # 3. A publication with nothing in the studio to match, and its engagement.
    own(_urn(3), NO_MATCH)
    for lead in ("lead-a", "lead-b"):
        conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type) VALUES (?, ?, 'LIKE')",
                     (lead, _urn(3)))
    # 4. A publication the archive brought with no text.
    own(_urn(4), None, source="archive")
    # 5, 6, 7. The legacy drafts store, with and without a queue row.
    alone = draft(A_DRAFT)
    queued = draft(QUEUED, status="QUEUED")
    conn.execute("INSERT INTO queue_items (draft_id, scheduled_at, status) VALUES (?, '2026-11-03 09:30', 'PENDING')",
                 (queued,))
    published = draft(PUBLISHED_DRAFT, status="PUBLISHED")
    conn.execute("INSERT INTO queue_items (draft_id, scheduled_at, published_at, status) "
                 "VALUES (?, '2026-10-01 09:00', '2026-10-01 09:04', 'PUBLISHED')", (published,))
    # 8. A draft whose text a posts row already holds, as the demo seeder and
    #    the Telegram ingress both wrote them.
    seeded = draft(SEEDED)
    post("post-day02-1", SEEDED, status="scheduled")
    # 9. A post written here and never published.
    post("post-unpublished", UNPUBLISHED)
    conn.commit()
    return conn, {"alone": alone, "queued": queued, "published": published, "seeded": seeded}


def _texts(conn):
    """Every non-empty thing the creator wrote, wherever it is held."""
    found = []
    for sql in ("SELECT content FROM posts",
                "SELECT text FROM own_posts",
                "SELECT raw_content FROM drafts"):
        found.extend(r[0] for r in conn.execute(sql) if (r[0] or "").strip())
    return found


def _run(conn):
    cursor = conn.cursor()
    migrations._migrate_one_post_identity(cursor)
    conn.commit()


def test_nothing_the_creator_wrote_is_lost_and_nothing_is_duplicated(before):
    conn, _ids = before
    was = set(_texts(conn))
    counted_before = {"posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
                      "own_posts": conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0],
                      "drafts": conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]}

    _run(conn)

    now = [r[0] for r in conn.execute("SELECT content FROM posts") if (r[0] or "").strip()]
    assert was <= set(now), f"lost: {sorted(was - set(now))}"
    duplicated = {text for text in now if now.count(text) > 1}
    assert duplicated == set(), duplicated
    # Three publications and three legacy drafts needed a post; the rest had one.
    assert conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == counted_before["posts"] + 5
    assert conn.execute("SELECT COUNT(*) FROM own_posts").fetchone()[0] == counted_before["own_posts"]
    assert conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0] == counted_before["drafts"]


def test_every_publication_has_exactly_one_post(before):
    conn, _ids = before
    _run(conn)

    assert conn.execute("SELECT COUNT(*) FROM own_posts WHERE post_id IS NULL").fetchone()[0] == 0
    missing = conn.execute(
        "SELECT o.activity_urn FROM own_posts o LEFT JOIN posts p ON p.id = o.post_id WHERE p.id IS NULL"
    ).fetchall()
    assert missing == [], [r[0] for r in missing]
    shared = conn.execute(
        "SELECT post_id, COUNT(*) FROM own_posts GROUP BY post_id HAVING COUNT(*) > 1").fetchall()
    assert shared == [], [tuple(r) for r in shared]


def test_every_interaction_can_reach_its_post(before):
    conn, _ids = before
    stranded_before = conn.execute(
        "SELECT COUNT(*) FROM lead_interactions i LEFT JOIN posts p ON p.activity_urn = i.post_urn "
        "WHERE p.id IS NULL").fetchone()[0]
    assert stranded_before == 2, "the fixture does not reproduce the fault"

    _run(conn)

    stranded = conn.execute(
        "SELECT COUNT(*) FROM lead_interactions i "
        "LEFT JOIN own_posts o ON o.activity_urn = i.post_urn "
        "LEFT JOIN posts p ON p.id = o.post_id WHERE p.id IS NULL").fetchone()[0]
    assert stranded == 0
    # And by the one resolver, which is what the endpoint uses.
    for urn in [r[0] for r in conn.execute("SELECT DISTINCT post_urn FROM lead_interactions")]:
        assert post_identity.resolve(conn, urn) is not None, urn


def test_a_publication_that_matched_a_post_bound_to_it_rather_than_making_another(before):
    conn, _ids = before
    _run(conn)
    row = conn.execute("SELECT activity_urn, status, content_fingerprint FROM posts WHERE id = ?",
                       ("post-marked",)).fetchone()
    assert row["activity_urn"] == _urn(2)
    assert row["status"] == "published"
    assert row["content_fingerprint"] == post_identity.content_fingerprint(MATCHES_A_POST)


def test_a_publication_with_nothing_to_match_gets_a_post_of_its_own(before):
    conn, _ids = before
    _run(conn)
    row = conn.execute("SELECT id, content, status, source FROM posts WHERE activity_urn = ?", (_urn(3),)).fetchone()
    assert row is not None
    assert row["content"] == NO_MATCH
    assert row["status"] == "published"
    assert row["source"] == "linkedin"


def test_a_publication_with_no_text_still_gets_its_post(before):
    conn, _ids = before
    _run(conn)
    row = conn.execute("SELECT content, source FROM posts WHERE activity_urn = ?", (_urn(4),)).fetchone()
    assert row is not None, "a publication from the archive with no text has no post"
    assert row["content"] == ""


def test_a_draft_the_legacy_store_held_alone_becomes_a_draft_the_creator_can_see(before):
    conn, ids = before
    _run(conn)
    row = conn.execute("SELECT content, status, source FROM posts WHERE draft_id = ?", (ids["alone"],)).fetchone()
    assert row is not None
    assert row["content"] == A_DRAFT
    assert row["status"] == "draft"
    assert row["source"] == "drafts"


def test_the_slot_the_dead_queue_held_is_carried_into_the_post(before):
    conn, ids = before
    _run(conn)
    queued = conn.execute("SELECT status, scheduled_for FROM posts WHERE draft_id = ?", (ids["queued"],)).fetchone()
    assert queued["status"] == "scheduled"
    assert queued["scheduled_for"] == "2026-11-03 09:30"
    published = conn.execute("SELECT status, published_at FROM posts WHERE draft_id = ?",
                             (ids["published"],)).fetchone()
    assert published["status"] == "published"
    assert published["published_at"] == "2026-10-01 09:04"


def test_a_draft_whose_text_a_post_already_holds_is_left_alone(before):
    conn, ids = before
    _run(conn)
    assert conn.execute("SELECT COUNT(*) FROM posts WHERE content = ?", (SEEDED,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM posts WHERE draft_id = ?", (ids["seeded"],)).fetchone()[0] == 0


def test_a_post_that_never_went_out_is_untouched(before):
    conn, _ids = before
    _run(conn)
    row = conn.execute("SELECT status, activity_urn, published_at FROM posts WHERE id = 'post-unpublished'").fetchone()
    assert row["status"] == "draft"
    assert row["activity_urn"] is None and row["published_at"] is None


def test_the_dead_queue_is_dropped(before):
    conn, _ids = before
    _run(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "queue_items" not in names
    assert "idx_queue_scheduled" not in names


def test_running_it_twice_changes_nothing(before):
    """
    Idempotent and resumable: every step is written as the work still to do,
    so a run interrupted and rolled back repeats only what it had not done.
    """
    conn, _ids = before
    _run(conn)
    snapshot = sorted(tuple(r) for r in conn.execute(
        "SELECT id, content, status, scheduled_for, published_at, activity_urn, draft_id, source FROM posts"))
    publications = sorted(tuple(r) for r in conn.execute("SELECT activity_urn, post_id FROM own_posts"))

    _run(conn)

    assert sorted(tuple(r) for r in conn.execute(
        "SELECT id, content, status, scheduled_for, published_at, activity_urn, draft_id, source FROM posts"
    )) == snapshot
    assert sorted(tuple(r) for r in conn.execute("SELECT activity_urn, post_id FROM own_posts")) == publications


def test_the_ledger_takes_a_backup_before_it_runs():
    """
    The standard pre-migration backup is the ledger's, not this migration's,
    and it must still be the thing that runs first.
    """
    import inspect

    source = inspect.getsource(migrations.ensure_schema)
    assert "backup_database(\"premigration\")" in source
    assert (26, "One identity for a post: every publication has its post, and the dead queue is gone",
            migrations._migrate_one_post_identity) in migrations.MIGRATIONS
