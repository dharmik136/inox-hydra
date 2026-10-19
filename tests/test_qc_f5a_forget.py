"""
Forgetting a lead forgets everything about them.
================================================

A creator who deletes a person, or purges them on request, believes the person
is gone. Their stage history lived in lead_stage_events, which had no foreign
key and was deleted by none of the three removal paths, so it stayed in the
database and in every export. Lead ids are a hash of the profile, so the same
person engaging again got the same id and the old history came back on the
dossier: "New Lead to Meeting Booked" beside a status of New Lead.

Each test runs in a home of its own, against the real schema.
"""

import json
import os
import sqlite3
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

PROFILE = "https://www.linkedin.com/in/asha-rao-qc"
POST = "urn:li:activity:7381000000000000001"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_forget_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db

    init_db()
    yield path


@pytest.fixture
def client(home):
    from fastapi.testclient import TestClient
    import app as app_module

    return TestClient(app_module.app)


def _capture():
    from crm import reverse_crm

    return reverse_crm.ingest_interaction(
        full_name="Asha Rao",
        linkedin_urn=PROFILE,
        headline="Founder at Crumb Co",
        interaction_type="COMMENT",
        comment_text="We lost a fifth of our flour to this last winter.",
        post_urn=POST,
    )["lead_id"]


def _rows_about(lead_id):
    from database import get_db

    conn = get_db()
    try:
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table} WHERE lead_id = ?", (lead_id,)).fetchone()[0]
            for table in ("lead_interactions", "lead_stage_events", "lead_enrichments")
        } | {"leads": conn.execute("SELECT COUNT(*) FROM leads WHERE id = ?", (lead_id,)).fetchone()[0]}
    finally:
        conn.close()


def _move_through_the_pipeline(client, lead_id):
    for stage in ("Outreach Sent", "Meeting Booked"):
        assert client.put(f"/api/leads/{lead_id}/status", json={"status": stage}).status_code == 200
    assert _rows_about(lead_id)["lead_stage_events"] == 2


@pytest.mark.parametrize("route", ["/api/leads/{id}", "/api/v1/crm/leads/{id}/purge"])
def test_every_removal_route_leaves_nothing_about_the_person(client, route):
    lead_id = _capture()
    _move_through_the_pipeline(client, lead_id)

    response = client.delete(route.format(id=lead_id))
    assert response.status_code == 200, response.text

    left = _rows_about(lead_id)
    assert left == {"lead_interactions": 0, "lead_stage_events": 0, "lead_enrichments": 0, "leads": 0}, (
        f"{route} left rows about a forgotten person behind: {left}"
    )


def test_a_person_who_engages_again_starts_with_no_history(client):
    lead_id = _capture()
    _move_through_the_pipeline(client, lead_id)
    assert client.delete(f"/api/v1/crm/leads/{lead_id}/purge").status_code == 200

    again = _capture()
    assert again == lead_id, "the premise: the same profile gives the same id"
    timeline = client.get(f"/api/v1/crm/leads/{again}/timeline").json()
    assert timeline["stage_history"] == [], (
        "a purged person's old pipeline reattached to them when they engaged again: "
        f"{timeline['stage_history']}"
    )


def test_any_delete_of_a_lead_takes_their_history_with_it(home):
    """
    The Leads screen's review removes people through a third path, and any
    future one should not have to remember the stage table either.
    """
    from database import get_db

    lead_id = _capture()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) VALUES (?, 'New Lead', 'Connected', '2026-10-01')",
            (lead_id,),
        )
        conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conn.commit()
    finally:
        conn.close()
    assert _rows_about(lead_id)["lead_stage_events"] == 0


def test_history_left_behind_by_older_versions_is_cleaned_up(home):
    """Rows orphaned before this fix are about people already forgotten."""
    import migrations
    from database import get_db

    keep = _capture()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) VALUES ('lead-gone', 'New Lead', 'Meeting Booked', '2026-09-01')"
        )
        conn.execute(
            "INSERT INTO lead_stage_events (lead_id, from_status, to_status, changed_at) VALUES (?, 'New Lead', 'Connected', '2026-09-02')",
            (keep,),
        )
        conn.commit()
        migration = next(m for m in migrations.MIGRATIONS if "forgotten" in m[1].lower())
        migrations._apply(conn.cursor(), migration[2])
        conn.commit()
        remaining = [r[0] for r in conn.execute("SELECT lead_id FROM lead_stage_events")]
    finally:
        conn.close()
    assert remaining == [keep], f"the cleanup removed the wrong rows or left an orphan: {remaining}"


def test_the_export_holds_nothing_about_a_forgotten_person(client):
    import support

    lead_id = _capture()
    _move_through_the_pipeline(client, lead_id)
    assert client.delete(f"/api/leads/{lead_id}").status_code == 200

    path = support.export_data(fmt="json")
    with open(path, encoding="utf-8") as handle:
        tables = json.load(handle)["tables"]
    mentions = {
        table: [row for row in rows if lead_id in json.dumps(row)]
        for table, rows in tables.items()
    }
    assert not any(mentions.values()), f"the export still carries the forgotten person: {mentions}"


def test_the_dossier_can_write_notes_without_moving_the_stage(client):
    """AUDIENCE-14: notes were read-only in the dossier; the route writes them alone."""
    lead_id = _capture()
    assert client.put(f"/api/leads/{lead_id}/status", json={"status": "Connected"}).status_code == 200

    response = client.patch(f"/api/leads/{lead_id}", json={"notes": "  Wants the flour sheet.  "})
    assert response.status_code == 200, response.text
    lead = client.get(f"/api/v1/crm/leads/{lead_id}/timeline").json()["lead"]
    assert lead["notes"] == "Wants the flour sheet."
    assert lead["status"] == "Connected"
    assert _rows_about(lead_id)["lead_stage_events"] == 1, "saving notes recorded a stage change"

    assert client.patch("/api/leads/lead-nobody", json={"notes": "x"}).status_code == 404
