"""
The lead dossier shows where a person actually met your writing.
==================================================================

Cycle 3, batch T7. `get_lead_timeline` read lead_interactions straight off the
table and returned it: no post_origin, no post_excerpt, even though both are
computed by onboarding.annotate_interactions and the dossier (LeadsSurface.tsx)
has read them since the "ON YOUR POST: ..." line was written. The function
that would have filled them in was never called from here, so the field was
always undefined and the line never rendered on any install. One post
identity (T1) is what makes the match reliable enough to wire in now.
"""

import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def home(monkeypatch):
    path = tempfile.mkdtemp(prefix="inox_qc3_t7_dossier_")
    monkeypatch.setenv("INOX_HYDRA_HOME", path)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _seed(conn, *, post_urn, post_text, lead_id, lead_name):
    conn.execute(
        "INSERT INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?)",
        (post_urn, post_text, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )
    conn.execute(
        "INSERT INTO leads (id, name) VALUES (?, ?)",
        (lead_id, lead_name),
    )
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


def test_dossier_names_which_own_post_a_person_engaged_with(home):
    from database import get_db
    import crm

    conn = get_db()
    _seed(
        conn,
        post_urn="urn:li:activity:7001",
        post_text="Our local-first architecture ships without a server.",
        lead_id="lead-1",
        lead_name="Ada Lovelace",
    )
    conn.close()

    result = crm.reverse_crm.get_lead_timeline("lead-1")

    assert result["status"] == "success"
    interactions = result["interactions"]
    assert len(interactions) == 2
    for entry in interactions:
        assert entry["post_origin"] == "yours", (
            "a comment and a like on the creator's own post must both resolve to it, "
            f"got {entry}"
        )
        assert entry["post_excerpt"] and "local-first architecture" in entry["post_excerpt"]


def test_dossier_names_a_post_that_is_not_yours_without_guessing(home):
    from database import get_db
    import crm

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

    result = crm.reverse_crm.get_lead_timeline("lead-2")
    entry = result["interactions"][0]
    assert entry["post_origin"] == "not_yours"
    assert entry["post_excerpt"] is None
