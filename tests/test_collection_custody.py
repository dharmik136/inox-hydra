"""
The collection's table exists, and everything that carries a table carries it.
==============================================================================

Phase 3 of the Telegram bot: everything sent to the bot lands in one table,
collection_items (docs/quality/cycle4/collection-box.md). As for every new
table (tests/test_qc4_t7_schema_and_custody.py): it is created by a named
migration and reaches an older database; what the phone sent before it
existed is recorded in it once, as used, and never brought back once
removed; the Storage panel sizes it; Delete everything clears it; the data
export lists it; the diagnostics bundle carries no word of it; and the
policy and the help say it is kept.

The migration is asserted by name and by what it adds, never by its number,
which the coordinator renumbers at integration.

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
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
sys.path.insert(0, BACKEND)

import migrations  # noqa: E402
import paths  # noqa: E402

TABLE = "collection_items"
COLUMNS = {"id", "received_at", "kind", "text", "link", "activity_urn", "desk_request_id", "tags", "topic",
           "status", "post_id", "source", "origin_ref", "updated_at", "used_at", "offered_at", "angles"}


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
    found = [m for m in migrations.MIGRATIONS if "collection" in m[1].lower()]
    assert len(found) == 1, "the collection's migration is not in the ledger exactly once"
    return found[0]


def _items(conn):
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(f"SELECT * FROM {TABLE} ORDER BY id")]


def test_the_migration_is_named_for_what_it_changes():
    _version, description, payload = _the_migration()
    for word in ("collection", "phone", "bot"):
        assert word in description.lower(), f"the migration's name does not say {word}"
    assert callable(payload)


def test_a_fresh_database_has_the_table_with_its_columns(home):
    conn = sqlite3.connect(paths.get_db_path())
    assert COLUMNS <= _columns(conn, TABLE), COLUMNS - _columns(conn, TABLE)
    assert migrations.get_schema_version(conn) == migrations.SCHEMA_VERSION
    conn.close()


def _older_with_phone_history(home):
    """
    A database the migration has not reached, holding what the phone sent
    before: a note and an idea saved as drafts (one deleted in the studio
    since), a draft written in the studio, and three requests from Telegram
    (one of the creator's posts, a short link, and someone else's post).
    """
    from database import create_draft

    note = create_draft("a thought from the phone #pricing", tags=["mobile-ingress", "pricing"])
    idea = create_draft("an idea from the phone", tags=["idea", "mobile-ingress"])
    gone = create_draft("deleted at the desk", tags=["mobile-ingress"])
    create_draft("written at the desk", tags=[])
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute("DELETE FROM posts WHERE id = ?", (f"post-draft-{gone}",))
    for urn, state, link in (("urn:li:activity:7390000000000000001", "open", None),
                             ("", "open", "https://lnkd.in/p/AbC123"),
                             ("urn:li:activity:7390000000000000777", "refused", None)):
        conn.execute("INSERT INTO desk_requests (activity_urn, asked_at, source, state, link) "
                     "VALUES (?, '2026-10-20T08:00:00+00:00', 'telegram', ?, ?)", (urn, state, link))
    version, _description, _payload = _the_migration()
    conn.execute(f"DROP TABLE {TABLE}")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    return conn, {"note": note, "idea": idea, "gone": gone}


def test_an_older_database_gains_the_table_and_what_the_phone_sent_before(home):
    conn, drafts = _older_with_phone_history(home)
    version, _description, _payload = _the_migration()
    report = migrations.ensure_schema(conn, take_backup=False)
    assert [a["version"] for a in report["applied"]] == list(range(version, migrations.SCHEMA_VERSION + 1))
    items = _items(conn)
    by_text = {i["text"]: i for i in items if i["text"]}
    assert set(by_text) == {"a thought from the phone #pricing", "an idea from the phone", "deleted at the desk"}
    assert by_text["an idea from the phone"]["kind"] == "idea"
    assert by_text["a thought from the phone #pricing"]["kind"] == "note"
    assert json.loads(by_text["a thought from the phone #pricing"]["tags"]) == ["pricing"]
    assert all(i["status"] == "used" for i in by_text.values()), "something sent before was offered as new"
    assert by_text["an idea from the phone"]["post_id"] == f"post-draft-{drafts['idea']}"
    assert by_text["deleted at the desk"]["post_id"] is None, "a draft deleted in the studio is named as what it became"
    links = sorted((i["kind"], i["link"]) for i in items if i["desk_request_id"])
    assert links == [("bookmark", "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000777/"),
                     ("link", "https://lnkd.in/p/AbC123"),
                     ("post", "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000001/")]
    assert all(i["source"] == "telegram" and i["received_at"] for i in items)
    conn.close()


def test_run_again_it_adds_nothing_and_never_brings_back_what_was_removed(home):
    conn, _drafts = _older_with_phone_history(home)
    migrations.ensure_schema(conn, take_backup=False)
    before = len(_items(conn))
    conn.execute(f"DELETE FROM {TABLE} WHERE kind = 'idea'")
    conn.commit()
    version, _description, payload = _the_migration()
    payload(conn.cursor())
    conn.commit()
    assert len(_items(conn)) == before - 1, "a second run added rows, or brought back one the creator removed"
    conn.close()


def test_the_storage_panel_sizes_it_and_the_export_carries_it():
    import retention
    import support

    assert retention._category_of(TABLE) != "other", "the collection would be sized under 'other'"
    assert TABLE in support.EXPORTABLE_TABLES, "the creator's collection cannot be taken elsewhere"


def test_delete_everything_clears_the_collection(home):
    import onboarding

    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(f"INSERT INTO {TABLE} (received_at, kind, text, status, source) "
                 "VALUES ('2026-10-29T08:00:00+00:00', 'note', 'my private plan', 'new', 'telegram')")
    conn.commit()
    conn.close()
    onboarding.forget_identity()
    conn = sqlite3.connect(paths.get_db_path())
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] == 0, "the collection survived forget"
    conn.close()


def test_the_diagnostics_bundle_carries_no_word_of_it(home):
    import support

    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(f"INSERT INTO {TABLE} (received_at, kind, text, status, source) "
                 "VALUES ('2026-10-29T08:00:00+00:00', 'note', 'pricing for the Zenith pitch', 'new', 'telegram')")
    conn.commit()
    conn.close()
    text = json.dumps(support.collect_diagnostics())
    assert "Zenith" not in text and "pricing for the" not in text, "a collected item reached the diagnostics bundle"


def test_the_policy_and_the_help_say_it_is_kept():
    policy = " ".join(_read("docs", "PRIVACY_POLICY.md").split())
    assert "your collection" in policy and "never the forward's origin" in policy
    keeps = " ".join(_read("docs", "help", "choose-what-the-studio-keeps.md").split())
    assert "Your collection" in keeps
