"""
P4 Verification Suite: Schema Migrations Are Safe On A Machine You Cannot Reach.
===============================================================================
The scenario every test here models: a user installed v2.5.0 months ago, has
real work in their database, and now runs a build with a newer schema. Nobody
can log in and fix it if this goes wrong.

The failure paths matter more than the happy path. A migration that half applies
and still bumps the version leaves a database that every subsequent release will
misread, and the user has no way to diagnose that. So the rollback, refusal and
backup behaviours are all tested explicitly.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import migrations  # noqa: E402
import paths  # noqa: E402


@pytest.fixture
def temp_home(monkeypatch):
    """Every test gets its own application home, so none touch the real database."""
    d = tempfile.mkdtemp(prefix="inox_migr_")
    monkeypatch.setenv("INOX_HYDRA_HOME", d)
    # Unit tests in this file verify migration engine mechanics using synthetic
    # migrations starting from BASELINE_VERSION (e.g. 2, 3).
    # Reset MIGRATIONS to empty baseline for synthetic test isolation.
    monkeypatch.setattr(migrations, "MIGRATIONS", [])
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", migrations.BASELINE_VERSION)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _make_legacy_db(with_data=True):
    """
    Builds a database as it existed before the ledger: real tables, real rows,
    and user_version still 0.
    """
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, content TEXT)")
    conn.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, name TEXT)")
    if with_data:
        conn.execute("INSERT INTO posts (content) VALUES (?)", ("a post the user wrote",))
        conn.execute("INSERT INTO leads (name) VALUES (?)", ("a real prospect",))
    conn.commit()
    assert migrations.get_schema_version(conn) == 0
    return conn


def _use_migrations(monkeypatch, entries):
    """Installs a synthetic ledger and keeps SCHEMA_VERSION consistent with it."""
    monkeypatch.setattr(migrations, "MIGRATIONS", entries)
    highest = max([migrations.BASELINE_VERSION] + [e[0] for e in entries])
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", highest)


def test_empty_file_is_not_baselined(temp_home):
    """A database with no tables has nothing to adopt. init_db creates it first."""
    conn = sqlite3.connect(paths.get_db_path())
    report = migrations.ensure_schema(conn)
    assert report["baselined"] is False
    assert migrations.get_schema_version(conn) == 0
    conn.close()


def test_pre_ledger_database_is_stamped_not_rebuilt(temp_home):
    """
    The upgrade path for every existing user. Their schema is already correct,
    so adopting the ledger must stamp the version and leave their rows alone.
    """
    conn = _make_legacy_db()
    report = migrations.ensure_schema(conn)

    assert report["baselined"] is True
    assert migrations.get_schema_version(conn) == migrations.BASELINE_VERSION

    assert conn.execute("SELECT content FROM posts").fetchone()[0] == "a post the user wrote"
    assert conn.execute("SELECT name FROM leads").fetchone()[0] == "a real prospect"
    conn.close()


def test_running_twice_changes_nothing(temp_home):
    """Startup runs this every launch. It must be idempotent."""
    conn = _make_legacy_db()
    migrations.ensure_schema(conn)
    second = migrations.ensure_schema(conn)

    assert second["baselined"] is False
    assert second["applied"] == []
    assert migrations.get_schema_version(conn) == migrations.BASELINE_VERSION
    conn.close()


def test_migration_applies_and_bumps_version(temp_home, monkeypatch):
    """The gate: an old database file is brought forward by a real migration."""
    conn = _make_legacy_db()
    migrations.ensure_schema(conn)

    _use_migrations(monkeypatch, [
        (2, "Add dwell_seconds to posts", ["ALTER TABLE posts ADD COLUMN dwell_seconds REAL DEFAULT 0.0"]),
        (3, "Index leads by name", ["CREATE INDEX IF NOT EXISTS idx_leads_name ON leads(name)"]),
    ])

    report = migrations.ensure_schema(conn)

    assert [a["version"] for a in report["applied"]] == [2, 3]
    assert migrations.get_schema_version(conn) == 3

    cols = {r[1] for r in conn.execute("PRAGMA table_info(posts)")}
    assert "dwell_seconds" in cols
    # The user's pre-existing row survived the schema change.
    assert conn.execute("SELECT content FROM posts").fetchone()[0] == "a post the user wrote"
    conn.close()


def test_failed_migration_rolls_back_change_and_version(temp_home, monkeypatch):
    """
    The important one.

    If a migration fails, the version must NOT advance, and the partial change
    must be gone. Otherwise every future release misreads this database.
    """
    conn = _make_legacy_db()
    migrations.ensure_schema(conn)

    _use_migrations(monkeypatch, [
        (2, "Half valid migration", [
            "ALTER TABLE posts ADD COLUMN good_column TEXT",
            "ALTER TABLE table_that_does_not_exist ADD COLUMN boom TEXT",
        ]),
    ])

    with pytest.raises(RuntimeError, match="Migration 2"):
        migrations.ensure_schema(conn)

    assert migrations.get_schema_version(conn) == migrations.BASELINE_VERSION, (
        "version advanced despite a failed migration"
    )
    cols = {r[1] for r in conn.execute("PRAGMA table_info(posts)")}
    assert "good_column" not in cols, "partial migration was not rolled back"
    conn.close()


def test_backup_is_taken_before_migrating(temp_home, monkeypatch):
    """The user's undo button must exist before anything is altered."""
    conn = _make_legacy_db()
    migrations.ensure_schema(conn)
    conn.commit()

    _use_migrations(monkeypatch, [
        (2, "Add a column", ["ALTER TABLE posts ADD COLUMN extra TEXT"]),
    ])
    report = migrations.ensure_schema(conn)

    backup = report["backup_path"]
    assert backup and os.path.exists(backup), "no backup was taken before migrating"
    assert os.path.abspath(backup).startswith(os.path.abspath(paths.get_backups_dir()))

    # The backup is a real, readable database holding the pre-migration state.
    restored = sqlite3.connect(backup)
    assert restored.execute("SELECT content FROM posts").fetchone()[0] == "a post the user wrote"
    assert "extra" not in {r[1] for r in restored.execute("PRAGMA table_info(posts)")}
    restored.close()
    conn.close()


def test_refuses_a_database_from_a_newer_build(temp_home, monkeypatch):
    """
    Protects the user who upgrades, dislikes it, and reinstalls the old version.
    Opening their newer database with an older build would corrupt assumptions.
    """
    conn = _make_legacy_db()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION + 5:d}")
    conn.commit()

    with pytest.raises(migrations.SchemaTooNewError) as exc:
        migrations.ensure_schema(conn)
    # The message has to be actionable, because it is the only support channel.
    assert "newer version" in str(exc.value)
    assert "backup" in str(exc.value).lower()
    conn.close()


def test_refuses_a_database_older_than_minimum_supported(temp_home, monkeypatch):
    """
    A build that has dropped support for very old schemas must say so rather
    than attempt a migration path it no longer carries.

    SCHEMA_VERSION is raised alongside MIN_SUPPORTED_SCHEMA so the database
    under test is unambiguously too old. Leaving the target at 1 would make a
    version-2 database simultaneously too new, and the too-new check runs first
    because that is the more urgent diagnosis.
    """
    monkeypatch.setattr(migrations, "MIN_SUPPORTED_SCHEMA", 5)
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 10)
    conn = _make_legacy_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 2")
    conn.commit()

    with pytest.raises(migrations.SchemaTooOldError):
        migrations.ensure_schema(conn)
    conn.close()


def test_schema_version_rejects_non_integer():
    """PRAGMA cannot bind parameters, so the interpolated value must be validated."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    for bad in ("1; DROP TABLE posts", 1.5, -1, None):
        with pytest.raises(ValueError):
            migrations._set_schema_version(cursor, bad)
    conn.close()


def test_describe_reports_pending_work(temp_home, monkeypatch):
    conn = _make_legacy_db()
    migrations.ensure_schema(conn)

    _use_migrations(monkeypatch, [
        (2, "Pending change", ["ALTER TABLE posts ADD COLUMN later TEXT"]),
    ])
    status = migrations.describe(conn)

    assert status["current_version"] == migrations.BASELINE_VERSION
    assert status["target_version"] == 2
    assert status["up_to_date"] is False
    assert status["too_new"] is False
    assert [p["version"] for p in status["pending"]] == [2]
    conn.close()


def test_shipped_ledger_is_well_formed():
    """
    Guards the ledger itself: strictly ascending, starting above the baseline,
    no duplicates. A reordered or duplicated entry corrupts every database that
    has already applied part of the sequence.
    """
    versions = [v for v, _, _ in migrations.MIGRATIONS]
    assert versions == sorted(versions), "migrations are not in ascending order"
    assert len(versions) == len(set(versions)), "duplicate migration versions"
    assert all(v > migrations.BASELINE_VERSION for v in versions), (
        "a migration claims a version at or below the baseline"
    )
    assert migrations.SCHEMA_VERSION == migrations.BASELINE_VERSION + len(migrations.MIGRATIONS)


def test_migration_2_migrates_and_drops_inspirations(temp_home):
    """
    Verifies that Migration 2 migrates existing inspirations into viral_templates
    and drops the inspirations table cleanly.
    """
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("""
    CREATE TABLE inspirations (
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
    conn.execute("""
    INSERT INTO inspirations (id, topic, key_hook, content)
    VALUES ('insp-test-1', 'Contrarian', 'Test hook line', 'Test hook line\n\nBody text')
    """)
    conn.commit()

    # Apply real migration 2 callable
    from studio.backend.migrations import _migrate_inspirations
    cursor = conn.cursor()
    _migrate_inspirations(cursor)
    conn.commit()

    # Table inspirations should be dropped
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inspirations'")
    assert cursor.fetchone() is None

    # Table viral_templates should exist and contain migrated record
    cursor.execute("SELECT archetype, hook_text FROM viral_templates WHERE example_post_id = 'migrated-insp-test-1'")
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "Contrarian"
    assert row[1] == "Test hook line"
    conn.close()
