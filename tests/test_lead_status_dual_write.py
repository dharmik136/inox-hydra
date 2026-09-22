"""
A lead carries two status vocabularies, and every write must set both.
======================================================================

`status` is what the CRM screen shows a person: "New Lead", "Outreach Sent",
"Connected", "Meeting Booked". `lead_status` is what every analytic reads:
NEW, ENGAGED, DM_DRAFTED, DM_SENT, CONVERTED, ARCHIVED. The CRM list filters on
the first and the funnel and conversion rate read the second.

add_lead and update_lead_status wrote both. batch_add_leads and the leads
insert inside the analytics ingest wrote only `status`, so forty commenters
captured as "Meeting Booked" showed as forty converted in the list and zero in
the funnel. Measured before the fix: list 40, funnel 0.

ARCHIVED is deliberately exempt. It has no counterpart in the human vocabulary,
so archive_inactive_leads setting only lead_status is correct rather than a
third instance of this bug.
"""

import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import leads as leads_module
from database import get_db
from leads import LEAD_STATUS_TO_PIPELINE, VALID_LEAD_STATUSES
from linkedin_client import linkedin_client

MARKER = "[DUALWRITE]"


@pytest.fixture(autouse=True)
def clean_probe_rows():
    def purge():
        conn = get_db()
        try:
            conn.execute("DELETE FROM leads WHERE name LIKE ?", (f"%{MARKER}%",))
            conn.commit()
        finally:
            conn.close()

    purge()
    yield
    purge()


def _row(name):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT status, lead_status FROM leads WHERE name = ?", (name,)
        ).fetchone()
    finally:
        conn.close()


@pytest.mark.parametrize("human", sorted(VALID_LEAD_STATUSES))
def test_batch_add_leads_writes_both_vocabularies(human):
    """
    The path that captures a whole comment section at once, which is how most
    leads actually arrive.
    """
    name = f"{MARKER} Batch {uuid.uuid4().hex[:8]}"
    leads_module.batch_add_leads([{
        "name": name,
        "headline": "VP Platform",
        "company": "Northwind",
        "profile_url": f"https://www.linkedin.com/in/{uuid.uuid4().hex[:10]}",
        "status": human,
    }])

    row = _row(name)
    assert row is not None, "the lead was not written at all"
    assert row["status"] == human
    assert row["lead_status"] == LEAD_STATUS_TO_PIPELINE[human], (
        f"status is {row['status']!r} but lead_status is {row['lead_status']!r}. "
        f"The CRM list and the funnel now disagree about this person."
    )


def test_the_analytics_ingest_writes_both_vocabularies():
    """Leads arriving with an analytics payload rather than through the CRM."""
    name = f"{MARKER} Ingest {uuid.uuid4().hex[:8]}"
    linkedin_client.ingest_analytics_payload({"leads": [{
        "name": name,
        "headline": "CTO",
        "company": "Acme",
        "profile_url": f"https://www.linkedin.com/in/{uuid.uuid4().hex[:10]}",
        "status": "Connected",
    }]})

    row = _row(name)
    assert row is not None, "the ingest wrote no lead"
    assert row["status"] == "Connected"
    assert row["lead_status"] == "ENGAGED"


def test_a_converted_batch_is_visible_to_the_funnel():
    """
    The reported shape, end to end: capture forty converted leads and ask both
    surfaces how many converted there are.
    """
    names = []
    batch = []
    for index in range(40):
        name = f"{MARKER} Converted {index} {uuid.uuid4().hex[:6]}"
        names.append(name)
        batch.append({
            "name": name,
            "headline": "VP",
            "company": "Acme",
            "profile_url": f"https://www.linkedin.com/in/{uuid.uuid4().hex[:10]}",
            "status": "Meeting Booked",
        })
    leads_module.batch_add_leads(batch)

    conn = get_db()
    try:
        listed = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'Meeting Booked' AND name LIKE ?",
            (f"%{MARKER}%",),
        ).fetchone()[0]
        funnelled = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_status = 'CONVERTED' AND name LIKE ?",
            (f"%{MARKER}%",),
        ).fetchone()[0]
    finally:
        conn.close()

    assert listed == 40
    assert funnelled == listed, (
        f"the CRM list shows {listed} converted leads and the funnel sees "
        f"{funnelled}. This is the disagreement the dual write exists to prevent."
    )


def test_every_leads_insert_names_both_columns():
    """
    Structural, so a new write path cannot reintroduce the gap. Checked across
    the modules that write to the leads table.
    """
    import re

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    offenders = []

    for relative in ("studio/backend/leads.py", "studio/backend/linkedin_client.py",
                     "studio/backend/crm.py"):
        source = open(os.path.join(repo_root, relative), encoding="utf-8").read()
        for match in re.finditer(r"INSERT(?: OR \w+)? INTO leads \(([^)]*)\)", source):
            columns = match.group(1)
            if "status" in columns and "lead_status" not in columns:
                line = source[:match.start()].count("\n") + 1
                offenders.append(f"{relative}:{line}")

    assert not offenders, (
        "these inserts write status without lead_status, so the row they "
        "create is invisible to the funnel:\n  " + "\n  ".join(offenders)
    )


def test_archived_is_exempt_because_it_has_no_human_counterpart():
    """
    Guards against over-applying the rule. ARCHIVED exists only in the machine
    vocabulary, so archive_inactive_leads writing one column is correct, and a
    future cleanup should not invent an "Archived" human status to match it.
    """
    assert "ARCHIVED" not in LEAD_STATUS_TO_PIPELINE.values()
    assert not any(v.lower() == "archived" for v in VALID_LEAD_STATUSES)
