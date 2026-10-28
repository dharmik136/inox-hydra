"""
Things to remember: their table, and everything that carries a table carries it.
===============================================================================

Phase 3 of the Telegram bot, item 3 (docs/quality/cycle4/collection-box.md).
The facts the creator tells the studio about themselves, their audience,
offers and dates live in `remembered`; what a draft was written from, and
with which of them, in `posts.made_with`. As for every new table: created by
a named migration and reaching an older database, sized in Storage,
cleared by Delete everything, exported, kept out of the diagnostics bundle,
and said in the policy and the help.

Strict Invariants:
- Zero em-dashes.
"""

import io
import json
import os
import sqlite3
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import migrations  # noqa: E402
import paths  # noqa: E402

COLUMNS = {"id", "text", "about", "in_use", "source", "origin_ref", "created_at", "updated_at", "last_used_at",
           "used_count"}


def _read(*parts):
    with io.open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path / "studio"))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db

    init_db()
    return tmp_path


def _the_migration():
    found = [m for m in migrations.MIGRATIONS if "things to remember" in m[1].lower()]
    assert len(found) == 1, "the memory migration is not in the ledger exactly once"
    return found[0]


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info([{table}])")}


def test_the_migration_is_named_for_what_it_changes():
    _version, description, payload = _the_migration()
    assert "draft" in description.lower() and callable(payload)


def test_a_fresh_database_has_the_table_and_the_drafts_note(home):
    conn = sqlite3.connect(paths.get_db_path())
    assert COLUMNS <= _columns(conn, "remembered"), COLUMNS - _columns(conn, "remembered")
    assert "made_with" in _columns(conn, "posts")
    conn.close()


def test_an_older_database_gains_them_and_a_second_run_adds_nothing(home):
    conn = sqlite3.connect(paths.get_db_path())
    version, _description, payload = _the_migration()
    conn.execute("DROP TABLE remembered")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    migrations.ensure_schema(conn, take_backup=False)
    assert COLUMNS <= _columns(conn, "remembered")
    payload(conn.cursor())
    conn.commit()
    assert "made_with" in _columns(conn, "posts")
    conn.close()


def test_storage_export_and_delete_everything_carry_it(home):
    import onboarding
    import retention
    import support

    assert retention._category_of("remembered") != "other"
    assert "remembered" in support.EXPORTABLE_TABLES
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO remembered (text, about, in_use, source, created_at, updated_at) "
                 "VALUES ('my course costs 49 dollars', 'offer', 1, 'studio', '2026-10-29', '2026-10-29')")
    conn.commit()
    conn.close()
    onboarding.forget_identity()
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute("SELECT COUNT(*) FROM remembered").fetchone()[0] == 0
    conn.close()


def test_the_diagnostics_bundle_carries_no_word_of_it(home):
    import support

    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("INSERT INTO remembered (text, about, in_use, source, created_at, updated_at) "
                 "VALUES ('launching the Zenith course in March', 'date', 1, 'studio', '2026-10-29', '2026-10-29')")
    conn.commit()
    conn.close()
    assert "Zenith" not in json.dumps(support.collect_diagnostics())


def test_the_policy_and_the_help_say_it_is_kept():
    policy = " ".join(_read("docs", "PRIVACY_POLICY.md").split())
    assert "things to remember" in policy.lower()
    keeps = " ".join(_read("docs", "help", "choose-what-the-studio-keeps.md").split())
    assert "Things to remember" in keeps
