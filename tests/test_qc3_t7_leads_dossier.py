"""
The dossier's engagement history, through the route the dossier reads.
======================================================================

Cycle 3, batch T7, review send-back 2. The first version of this module
called crm.reverse_crm.get_lead_timeline directly and asserted that it
annotated each interaction with post_origin and post_excerpt. That was the
wrong layer and the wrong claim: the dossier reads
GET /api/v1/crm/leads/<id>/timeline, and routers/crm.py has always annotated
there, so the field was never missing on screen. The annotation added to
crm.py has been reverted.

What is actually new, and what these hold, is the contract the dossier's
"Engagement with your posts" section stands on: the route says, for every
interaction, whether it was on a post of the creator's and what that post
opens with. The grouping itself is held by a Playwright test over the built
screen (tests/test_qc3_t7_surfaces.py), because it is drawn in the browser.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

TIMELINE = "/api/v1/crm/leads/{}/timeline"


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t7_dossier_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(home):
    from fastapi.testclient import TestClient
    import app as app_module
    return TestClient(app_module.app)


def _seed(conn, *, post_urn, post_text, lead_id, lead_name):
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
        (post_urn, post_text, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.execute("INSERT INTO leads (id, name) VALUES (?, ?)", (lead_id, lead_name))
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at) "
        "VALUES (?, ?, 'COMMENT', 'Great post', '2026-01-01T00:00:00')",
        (lead_id, post_urn),
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at) "
        "VALUES (?, ?, 'LIKE', '2026-01-02T00:00:00')",
        (lead_id, post_urn),
    )
    conn.commit()


def test_the_timeline_route_says_which_of_your_posts_each_interaction_was_on(client, home):
    """
    What the dossier's engagement history is built from. A comment and a like
    on the same post of yours both resolve to it, and the post's opening is
    carried with them so the screen does not have to ask for it again.
    """
    from database import get_db

    conn = get_db()
    _seed(
        conn,
        post_urn="urn:li:activity:7001",
        post_text="Our local-first architecture ships without a server.",
        lead_id="lead-1",
        lead_name="Ada Lovelace",
    )
    conn.close()

    answer = client.get(TIMELINE.format("lead-1"))
    assert answer.status_code == 200, answer.text
    interactions = answer.json()["interactions"]
    assert len(interactions) == 2
    for entry in interactions:
        assert entry["post_origin"] == "yours", entry
        assert entry["post_excerpt"] and "local-first architecture" in entry["post_excerpt"]


def test_the_timeline_route_does_not_guess_a_post_that_is_not_yours(client, home):
    from database import get_db

    conn = get_db()
    conn.execute("INSERT INTO leads (id, name) VALUES ('lead-2', 'Grace Hopper')")
    conn.execute(
        "INSERT INTO self_import_requests (kind, outcome, items_seen, requested_at, finished_at) "
        "VALUES ('posts', 'end_of_list', 10, '2026-01-01T00:00:00', '2026-01-01T00:00:00')"
    )
    conn.execute(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, interacted_at) "
        "VALUES ('lead-2', 'urn:li:activity:9999', 'COMMENT', '2026-01-01T00:00:00')"
    )
    conn.commit()
    conn.close()

    entry = client.get(TIMELINE.format("lead-2")).json()["interactions"][0]
    assert entry["post_origin"] == "not_yours"
    assert entry["post_excerpt"] is None


def test_the_route_annotates_once_for_one_read(client, home, monkeypatch):
    """
    annotate_interactions reads every own post's text and every posts.content
    to do its work, so running it twice for one dossier open is 8 ms of the
    19 the route takes on a three year home. The batch added a second call
    inside crm.get_lead_timeline; the review found it, and this holds the
    route to one.
    """
    from database import get_db
    import onboarding

    conn = get_db()
    _seed(
        conn,
        post_urn="urn:li:activity:7002",
        post_text="One call per read.",
        lead_id="lead-3",
        lead_name="Annie Easley",
    )
    conn.close()

    calls = []
    real = onboarding.annotate_interactions
    monkeypatch.setattr(onboarding, "annotate_interactions",
                        lambda rows: (calls.append(len(rows)), real(rows))[1])

    assert client.get(TIMELINE.format("lead-3")).status_code == 200
    assert calls == [2], f"the route annotated {len(calls)} times for one read"
