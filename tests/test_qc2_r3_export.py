"""
Export streams its rows, and writes the same files.
==================================================

Cycle 2, batch R3 (DATA-05).

Export read every exportable table into a list of dicts before writing a byte:
1.1 GB of memory for the JSON export of three years of one creator's data and
1.5 GB for the CSV ZIP, on the laptop the creator is leaving with. It now
writes from the cursor, 500 rows at a time. The files are what they were:
these tests rebuild them the old way and compare.
"""

import csv
import io
import json
import os
import shutil
import sys
import tempfile
import tracemalloc
import zipfile
from datetime import datetime

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
sys.path.insert(0, os.path.dirname(__file__))

import qc2_r3_data  # noqa: E402

FIXED = datetime(2026, 10, 20, 12, 0, 0)


class _Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc2_r3_export_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    qc2_r3_data.build(conn)
    with conn:
        # Text a spreadsheet would run, bytes, nulls and non-ASCII.
        conn.execute("UPDATE leads SET notes = '=HYPERLINK(\"x\")' WHERE rowid % 9 = 0")
        conn.execute("UPDATE leads SET headline = '@everyone, Zoë' WHERE rowid % 10 = 0")
    conn.close()
    import support
    monkeypatch.setattr(support, "datetime", _Clock)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _old_payload():
    import support
    conn = support._connect()
    try:
        available = set(support._table_names(conn))
        return {t: [dict(r) for r in conn.execute(f"SELECT * FROM [{t}]").fetchall()]
                for t in support.EXPORTABLE_TABLES if t in available}
    finally:
        conn.close()


def test_the_json_export_is_the_file_it_always_was(home):
    import support
    path = support.export_data(os.path.join(home, "new.json"), fmt="json")
    old = json.dumps({"exported_at": FIXED.isoformat(timespec="seconds"), "app_version": support.__version__,
                      "tables": _old_payload()}, indent=2, default=str)
    with open(path, encoding="utf-8") as handle:
        assert handle.read() == old


def test_the_json_export_of_no_tables_is_valid(home, monkeypatch):
    import support
    monkeypatch.setattr(support, "EXPORTABLE_TABLES", ("no_such_table",))
    path = support.export_data(os.path.join(home, "empty.json"), fmt="json")
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    assert text == json.dumps({"exported_at": FIXED.isoformat(timespec="seconds"),
                               "app_version": support.__version__, "tables": {}}, indent=2)


def test_the_csv_export_holds_the_same_files(home):
    import support
    path = support.export_data(os.path.join(home, "new.zip"), fmt="csv")
    with zipfile.ZipFile(path) as z:
        got = {name: z.read(name).decode("utf-8") for name in z.namelist()}
    expected = {}
    for table, rows in _old_payload().items():
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: support._cell(v) for k, v in row.items()})
        expected[f"{table}.csv"] = buffer.getvalue()
    assert got == expected
    assert any(text.count("\n") > 1000 for text in got.values())


def test_export_memory_does_not_grow_with_the_data(home):
    """Peak Python memory for the export stays far under the size of what it writes."""
    import support
    from database import get_db
    conn = get_db()
    with conn:
        conn.executemany(
            "INSERT INTO lead_interactions (lead_id, interaction_type, comment_text, comment_key) "
            "VALUES ('lead-0001', 'COMMENT', ?, ?)",
            [("x" * 2000 + str(n), f"bulk-{n}") for n in range(12000)])
    conn.close()
    for fmt, name in (("json", "big.json"), ("csv", "big.zip")):
        tracemalloc.start()
        path = support.export_data(os.path.join(home, name), fmt=fmt)
        _now, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        written = os.path.getsize(path) if fmt == "json" else sum(
            info.file_size for info in zipfile.ZipFile(path).infolist())
        assert written > 24_000_000
        assert peak < 8_000_000, f"{fmt} export peaked at {peak / 1e6:.1f} MB for {written / 1e6:.0f} MB of data"
