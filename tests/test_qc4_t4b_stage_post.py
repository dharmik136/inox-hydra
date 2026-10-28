"""
A lead's stage history records the post a stage change came from.
=================================================================

Migration 14 created lead_stage_events promising to say "from which post"
a lead moved, and wrote no post column (sections report, defects table). A
creator moves someone along the pipeline most often straight after reading
them on a post: in Replies, under the post their comment is on, or in a
post's detail on Posts. The dossier opened from there now records that post
on the change it makes, and the history says it; a change made from the
Leads list records none, because none is known, and says nothing about one.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
UI = os.path.join(REPO_ROOT, "studio", "ui", "src")

POST = "urn:li:activity:7390000000000000501"
OTHER = "urn:li:activity:7390000000000000502"


def _read(*parts):
    with io.open(os.path.join(*parts), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_stage_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db, get_db
    init_db()
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'Freight is a data problem pretending to be a trucking problem.', "
                     "'2026-10-20T09:00:00+00:00', '2026-10-20T09:00:00+00:00', '2026-10-20T09:00:00+00:00')", (POST,))
        conn.execute("INSERT INTO leads (id, name, full_name, status, lead_status) VALUES ('lead-x', 'Asha Rao', 'Asha Rao', "
                     "'New Lead', 'NEW')")
        conn.execute("INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at) "
                     "VALUES ('lead-x', ?, 'COMMENT', 'This matches what we saw.', '2026-10-21T10:00:00+00:00')", (POST,))
    conn.close()
    from fastapi.testclient import TestClient
    import app as app_module
    yield TestClient(app_module.app)
    shutil.rmtree(home, ignore_errors=True)


def _history(client):
    answer = client.get("/api/v1/crm/leads/lead-x/timeline")
    assert answer.status_code == 200, answer.text
    return answer.json()["stage_history"]


def test_the_migration_gives_a_stage_change_its_post():
    import migrations
    entry = next((e for e in migrations.MIGRATIONS if "stage change" in e[1] and "post" in e[1]), None)
    assert entry, "no migration is named for a stage change's post"


def test_a_change_made_from_a_post_records_it_and_the_history_says_which(client):
    answer = client.put("/api/leads/lead-x/status", json={"status": "Connected", "post_urn": POST})
    assert answer.status_code == 200, answer.text
    [event] = _history(client)
    assert event["to_status"] == "Connected" and event["post_urn"] == POST
    assert event["post_excerpt"].startswith("Freight is a data problem")


def test_a_change_made_from_the_list_records_no_post(client):
    assert client.put("/api/leads/lead-x/status", json={"status": "Connected"}).status_code == 200
    [event] = _history(client)
    assert event["post_urn"] is None and event.get("post_excerpt") is None


def test_a_post_the_person_never_engaged_with_is_refused_not_recorded(client):
    answer = client.put("/api/leads/lead-x/status", json={"status": "Connected", "post_urn": OTHER})
    assert answer.status_code == 422, answer.text
    assert _history(client) == [], "a refused change moved the stage anyway"


def test_the_screens_that_open_a_lead_from_a_post_say_which_post():
    components = os.path.join(UI, "components")
    replies = _read(components, "RepliesSurface.tsx")
    assert "onOpenLead(comment.lead_id, comment.post_urn)" in replies, "Replies opens the lead without its post"
    detail = _read(components, "PostDetail.tsx")
    assert "onOpenLead(person.id, activityUrn)" in detail, "a post's detail opens the lead without the post"
    leads = _read(components, "LeadsSurface.tsx")
    assert "updateLeadStatus(lead.id, candidate, fromPost)" in leads, "the pipeline does not send the post it came from"
    assert "FROM YOUR POST" in leads, "the stage history does not say which post a change came from"
    api = _read(UI, "lib", "api.ts")
    assert "post_urn" in api.split("export async function updateLeadStatus")[1].split("\n}\n")[0]
