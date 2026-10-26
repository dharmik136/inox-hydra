"""
The daily section's tables exist, and everything that carries a table carries them.
====================================================================================

Cycle 4, track 7, batch 1 of the personalised daily ideas report. The
queue_items lesson (database.py) is that "retention, backup, export and
forget all carried it" for a table nothing read; the mirror lesson is a
table that something reads and nothing carries. So this holds, for every
new table: it is created by a named migration and reaches an older
database; the Storage panel can size it (retention.CATEGORIES); forget
identity clears what is the creator's; the data export lists it; the
diagnostics bundle redacts what is typed into it; and the policy and the
help say it is kept, and for how long, before the first row lands.

The migration is asserted by name and by what it adds, never by its
number, which the coordinator renumbers at integration.
"""

import io
import json
import os
import sqlite3
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

import migrations  # noqa: E402
import paths  # noqa: E402

CREATOR_TABLES = ("asks", "daily_view", "daily_run", "card_marks", "record_notes")
ARCHIVE_TABLE = "archive_records"
LIBRARY_TABLE = "library_entries"
NEW_TABLES = CREATOR_TABLES + (ARCHIVE_TABLE, LIBRARY_TABLE)

COLUMNS = {
    "asks": {"id", "text", "source", "field", "origin_ref", "status", "created_at", "updated_at",
             "last_used_at", "hidden_at"},
    "daily_run": {"day", "input_signature", "started_at", "finished_at", "local_ok", "local_note",
                  "carried_from", "seed", "rerolled_at", "model_status", "model_note", "model_calls",
                  "model_tokens_in", "model_tokens_out", "estimated_cost_usd", "price_date", "searches",
                  "dropped_cards", "note"},
    "daily_view": {"day", "card_id", "slot", "block", "kind", "label", "method", "payload_json",
                   "provenance_json", "status", "created_at"},
    "card_marks": {"id", "day", "card_id", "mark", "at", "draft_id"},
    "record_notes": {"month", "text", "at"},
    "archive_records": {"id", "kind", "url", "title", "name", "detail", "happened_at", "dedupe_key",
                        "source_file", "imported_at", "import_id"},
    "library_entries": {"id", "entry_id", "kind", "title", "text", "tags_json", "author", "bundle_version",
                        "signed_at", "key_id", "fetched_at"},
}


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


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info([{table}])")}


def _the_migration():
    found = [m for m in migrations.MIGRATIONS if "From your record" in m[1]]
    assert len(found) == 1, "the section's migration is not in the ledger exactly once"
    return found[0]


def test_the_migration_is_named_for_what_it_changes():
    _version, description, payload = _the_migration()
    for word in ("asks", "daily batch", "card marks", "archive", "library"):
        assert word in description, f"the migration's name does not say it adds {word}"
    assert callable(payload)
    assert _the_migration() is migrations.MIGRATIONS[-1], "a later migration follows it in this branch"


def test_a_fresh_database_has_every_table_with_its_columns(home):
    conn = sqlite3.connect(paths.get_db_path())
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for table in NEW_TABLES:
        assert table in tables, f"{table} is missing"
        assert COLUMNS[table] <= _columns(conn, table), f"{table} lacks {COLUMNS[table] - _columns(conn, table)}"
    assert {"origin_card_id", "origin_day"} <= _columns(conn, "drafts"), "a draft cannot record the card it came from"
    conn.close()


def test_an_older_database_gains_the_tables_by_the_migration(home):
    """A database the migration has not reached: its tables dropped and its version set back."""
    conn = sqlite3.connect(paths.get_db_path())
    version, _description, _payload = _the_migration()
    for table in NEW_TABLES:
        conn.execute(f"DROP TABLE {table}")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    report = migrations.ensure_schema(conn, take_backup=False)
    assert [a["version"] for a in report["applied"]] == [version]
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(NEW_TABLES) <= tables
    # Idempotent: the ALTER TABLE on drafts is guarded, so a second run adds nothing.
    migrations._migrate_record_section(conn.cursor())
    conn.close()


def test_every_new_table_is_sized_by_the_storage_panel():
    import retention

    for table in NEW_TABLES:
        assert retention._category_of(table) != "other", f"{table} would be sized under 'other'"


def test_forget_identity_clears_what_is_the_creators(home):
    import onboarding

    conn = sqlite3.connect(paths.get_db_path())
    now = "2026-10-26T06:00:00+00:00"
    conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) VALUES ('hiring without a recruiter', 'ask_box', 'open', ?, ?)", (now, now))
    conn.execute("INSERT INTO daily_run (day, started_at, local_ok) VALUES ('2026-10-26', ?, 1)", (now,))
    conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, provenance_json, created_at) "
                 "VALUES ('2026-10-26', 'theme:hiring', 3, 'you_asked', 'theme', 'typed', 'rule', '{}', '{}', ?)", (now,))
    conn.execute("INSERT INTO card_marks (day, card_id, mark, at) VALUES ('2026-10-26', 'theme:hiring', 'keep', ?)", (now,))
    conn.execute("INSERT INTO record_notes (month, text, at) VALUES ('2026-10', 'they helped', ?)", (now,))
    conn.execute("INSERT INTO archive_records (kind, url, dedupe_key, source_file, imported_at) "
                 "VALUES ('saved_item', 'https://www.linkedin.com/posts/x', 'k', 'Saved_Items.csv', ?)", (now,))
    conn.commit()
    conn.close()

    onboarding.forget_identity()

    conn = sqlite3.connect(paths.get_db_path())
    for table in CREATOR_TABLES + (ARCHIVE_TABLE,):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, f"{table} survived forget"
    conn.close()


def test_the_export_carries_the_creators_rows_and_not_the_library():
    import support

    for table in CREATOR_TABLES + (ARCHIVE_TABLE,):
        assert table in support.EXPORTABLE_TABLES, f"{table} cannot be taken elsewhere"
    assert LIBRARY_TABLE not in support.EXPORTABLE_TABLES, "the company's library is not the creator's data"


def test_the_diagnostics_bundle_carries_no_ask_and_redacts_the_section_settings(home):
    import support

    conn = sqlite3.connect(paths.get_db_path())
    now = "2026-10-26T06:00:00+00:00"
    conn.execute("INSERT INTO asks (text, source, status, created_at, updated_at) "
                 "VALUES ('pricing for the Acme pitch', 'ask_box', 'open', ?, ?)", (now, now))
    conn.execute("INSERT INTO settings (key, value) VALUES ('record_cost_ceiling_usd', '0.25')")
    conn.commit()
    conn.close()
    text = json.dumps(support.collect_diagnostics())
    assert "Acme" not in text and "pricing for the" not in text, "an ask reached the diagnostics bundle"
    assert "record_cost_ceiling_usd" not in support.SAFE_SETTING_KEYS
    assert '"0.25"' not in text


def test_the_policy_says_what_is_kept_and_when_the_model_stage_runs():
    policy = _read("docs", "PRIVACY_POLICY.md")
    for phrase in (
        "the text of the asks you make of the studio and choose to keep",
        "the marks you put on the daily cards",
        "the daily batch of cards itself",
        "only for the files you ticked at import",
        "with the file it came from and the date it was imported",
        "365 by",
        "None of it is in\nthe diagnostics bundle or the access log",
        "it runs when you open From your\nrecord for the first time each day, never on a timer",
        "It never sends figures, other people's names or comments, your connections or anybody's score",
        "any phrase carrying a number, is dropped before it is shown",
    ):
        assert phrase in policy, f"the policy does not say: {phrase!r}"
    # The sentence the model stage rests on is still there, unchanged.
    assert "only at the moment you use the feature that needs it" in policy


def test_the_help_table_of_what_is_kept_has_the_rows():
    article = _read("docs", "help", "choose-what-the-studio-keeps.md")
    assert "| Your asks and the marks on your daily cards (From your record) |" in article
    assert "| The daily batches of cards (From your record) | 365 days |" in article
    assert "From your record (your asks, the daily cards, their marks and your notes)" in article
