"""
Quality cycle 2026-10, batch F8 [F5a-N1]: the dev-mode internal sheet CSV
neutralises formula cells like every other export.

A title, description, selector or captured text that begins with =, +, - or @
ran as a live formula when the export was opened in a spreadsheet, because
export_csv wrote cells without support._cell.
"""

import csv
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from database import get_db, init_db  # noqa: E402
from internal_sheet import internal_sheet_manager  # noqa: E402

FORMULA = '=HYPERLINK("http://example.invalid","[TEST] click")'


@pytest.fixture(autouse=True)
def clean_issues():
    init_db()

    def wipe():
        conn = get_db()
        try:
            with conn:
                conn.execute("DELETE FROM internal_sheet_issues WHERE title LIKE '%[TEST]%'")
        finally:
            conn.close()

    wipe()
    yield
    wipe()


def test_formula_cells_are_written_as_text():
    internal_sheet_manager.create_issue(
        target_selector="@main > .x",
        title=FORMULA,
        description="+1 cmd|' /C calc'!A0",
        element_text_snippet="-2+3",
    )
    rows = list(csv.reader(io.StringIO(internal_sheet_manager.export_csv())))
    header, body = rows[0], rows[1:]
    row = next(r for r in body if FORMULA in r[header.index("Title")])
    assert row[header.index("Title")] == "'" + FORMULA
    assert row[header.index("Problem Description")].startswith("'+")
    assert row[header.index("Target Selector")].startswith("'@")
    assert row[header.index("Element Text Snippet")] == "'-2+3"


def test_plain_cells_are_unchanged():
    internal_sheet_manager.create_issue(target_selector="#editor", title="[TEST] plain", description="Plain words.")
    rows = list(csv.reader(io.StringIO(internal_sheet_manager.export_csv())))
    header = rows[0]
    row = next(r for r in rows[1:] if r[header.index("Title")] == "[TEST] plain")
    assert row[header.index("Target Selector")] == "#editor"
    assert row[header.index("Problem Description")] == "Plain words."
