"""
Schema Drift Guard: init_db() Is Frozen, Migrations Are The Only Way Forward.
=============================================================================
Enforces the rule that a message cannot enforce.

`init_db()` is the schema baseline, version 1. Every database a user already has
matches it, which is what allows the ledger to stamp them rather than rebuild
them. Adding a table or column to `init_db()` works perfectly on a developer
machine, because CREATE TABLE IF NOT EXISTS is idempotent against a database
that does not exist yet.

It does not reach anybody else. A user running v2.5.0 has a database stamped at
version 1. Ship v2.6.0 with new DDL inside `init_db()` and their database simply
never gains the column, silently, because nothing in the startup path is looking
for that difference. The application then misbehaves on data it cannot see, on a
machine nobody can reach.

So this compares the schema `init_db()` actually produces against a frozen
fingerprint, with the migration ledger emptied so that only `init_db()`'s own
DDL is measured. Legitimate schema changes go in migrations.py and do not
affect the baseline, so they do not touch this test.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
- Regenerating schema_baseline.json is almost never the correct fix.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.backend import migrations, paths  # noqa: E402

BASELINE_FILE = os.path.join(os.path.dirname(__file__), "..", "studio", "backend",
                             "schema_baseline.json")

FIX_ADVICE = """
This means init_db() no longer produces the schema recorded as version 1.

If you added a table, column or index to init_db(), move it to
studio/backend/migrations.py as a numbered entry instead:

    (2, "Describe the change", [
        "ALTER TABLE posts ADD COLUMN your_column TEXT",
    ]),

A user who already installed an earlier version has a database stamped at
version 1. DDL added to init_db() never reaches them, and nothing fails loudly
when it does not. A numbered migration does reach them.

Only regenerate studio/backend/schema_baseline.json if you are deliberately
re-baselining the product, which should be almost never.
"""


def _load_baseline():
    with open(BASELINE_FILE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def fresh_baseline_schema(monkeypatch):
    """
    Builds a database with the ledger emptied, so the result reflects only the
    DDL inside init_db() and not the effect of any shipped migration.
    """
    home = tempfile.mkdtemp(prefix="inox_baseline_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.setattr(migrations, "MIGRATIONS", [])
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", migrations.BASELINE_VERSION)

    from studio.backend import database
    database.init_db()

    conn = sqlite3.connect(paths.get_db_path())
    tables = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    schema = {t: sorted(r[1] for r in conn.execute(f"PRAGMA table_info([{t}])")) for t in tables}
    indexes = sorted(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"))
    conn.close()

    yield {"tables": schema, "indexes": indexes}
    shutil.rmtree(home, ignore_errors=True)


def test_baseline_fingerprint_exists():
    assert os.path.exists(BASELINE_FILE), (
        "studio/backend/schema_baseline.json is missing. Without it there is nothing "
        "stopping schema changes from being added to init_db() where users never see them."
    )


def test_no_tables_added_to_or_removed_from_init_db(fresh_baseline_schema):
    expected = set(_load_baseline()["tables"])
    actual = set(fresh_baseline_schema["tables"])

    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    assert not added, f"init_db() now creates tables that are not in the baseline: {added}\n{FIX_ADVICE}"
    assert not removed, (
        f"init_db() no longer creates baseline tables: {removed}\n"
        "Removing a table from the baseline breaks every existing user database.\n"
    )


def test_no_columns_added_to_init_db(fresh_baseline_schema):
    """
    The quiet one. A new column in init_db() is invisible on a fresh machine and
    absent on every existing install.
    """
    expected = _load_baseline()["tables"]
    actual = fresh_baseline_schema["tables"]

    drift = []
    for table, columns in actual.items():
        if table not in expected:
            continue
        added = sorted(set(columns) - set(expected[table]))
        removed = sorted(set(expected[table]) - set(columns))
        if added:
            drift.append(f"  {table}: added {added}")
        if removed:
            drift.append(f"  {table}: removed {removed}")

    assert not drift, "init_db() schema drifted from version 1:\n" + "\n".join(drift) + "\n" + FIX_ADVICE


def test_indexes_match_the_baseline(fresh_baseline_schema):
    expected = set(_load_baseline()["indexes"])
    actual = set(fresh_baseline_schema["indexes"])
    added = sorted(actual - expected)
    removed = sorted(expected - actual)
    assert not added, f"init_db() now creates indexes outside the baseline: {added}\n{FIX_ADVICE}"
    assert not removed, f"init_db() no longer creates baseline indexes: {removed}"


def test_baseline_records_the_version_it_describes():
    assert _load_baseline()["baseline_version"] == migrations.BASELINE_VERSION


def test_guard_actually_detects_drift(fresh_baseline_schema):
    """
    Proves the guard is not vacuous.

    A test that can never fail is worse than no test, because it reads as
    protection. This simulates the exact mistake being guarded against and
    confirms the comparison catches it.
    """
    tampered = {t: list(c) for t, c in fresh_baseline_schema["tables"].items()}
    tampered["posts"] = sorted(tampered["posts"] + ["a_column_someone_added_to_init_db"])

    expected = _load_baseline()["tables"]
    drift = []
    for table, columns in tampered.items():
        if table in expected:
            added = sorted(set(columns) - set(expected[table]))
            if added:
                drift.append(f"{table}: {added}")

    assert drift == ["posts: ['a_column_someone_added_to_init_db']"], (
        "the drift comparison failed to notice an added column, so the guard is not working"
    )
