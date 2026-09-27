"""
One interaction per interaction, one lead per person.
=====================================================

Audit W4, W7 and W8, which all live in ReverseCRMManager.ingest_interaction.

W8. Every page load inserted a row, because the extension re-sends what is on
screen whenever a post is opened. "Most engaged" meant "most often reopened".

W7. A reaction was stored with the comment text "Reacted to post on LinkedIn",
and the dossier showed it as words the person wrote.

W4. Leads were matched by `linkedin_urn OR (name AND company)`, and the capture
rarely knows a company, so two people with the same display name became one
lead, and the creator could quote one to the other.
"""

import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import migrations
from crm import reverse_crm
from database import get_db

POST = "urn:li:activity:7100000000000000001"
TAG = "graintest"


@pytest.fixture(autouse=True)
def clean():
    yield
    conn = get_db()
    with conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM leads WHERE name LIKE ?", (f"%{TAG}%",))]
        for lead_id in ids:
            conn.execute("DELETE FROM lead_interactions WHERE lead_id = ?", (lead_id,))
            conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.close()


def _ingest(name, profile, **extra):
    body = dict(full_name=name, linkedin_urn=profile, headline="Engineer", interaction_type="COMMENT",
                comment_text="How did you stage the rollout?", post_urn=POST)
    body.update(extra)
    return reverse_crm.ingest_interaction(**body)


def _interactions(lead_id):
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT comment_text, seen_count FROM lead_interactions WHERE lead_id = ?", (lead_id,))]
    finally:
        conn.close()


def test_reopening_a_post_is_not_a_second_engagement():
    first = _ingest(f"Asha {TAG}", "https://www.linkedin.com/in/asha-graintest")
    for _ in range(4):
        _ingest(f"Asha {TAG}", "https://www.linkedin.com/in/asha-graintest")
    rows = _interactions(first["lead_id"])
    assert len(rows) == 1, f"five reads of one comment became {len(rows)} interactions"
    assert rows[0]["seen_count"] == 5, "the revisit signal was lost rather than kept"


def test_a_second_comment_is_a_second_interaction():
    first = _ingest(f"Asha {TAG}", "https://www.linkedin.com/in/asha-graintest")
    _ingest(f"Asha {TAG}", "https://www.linkedin.com/in/asha-graintest", comment_text="And the rollback?")
    assert len(_interactions(first["lead_id"])) == 2


def test_a_reaction_carries_no_invented_words():
    result = _ingest(f"Ben {TAG}", "https://www.linkedin.com/in/ben-graintest",
                     interaction_type="LIKE", comment_text="Reacted to post on LinkedIn")
    assert _interactions(result["lead_id"])[0]["comment_text"] is None


def test_namesakes_stay_two_people():
    one = _ingest(f"Rahul Sharma {TAG}", "https://www.linkedin.com/in/rahul-sharma-graintest-1")
    two = _ingest(f"Rahul Sharma {TAG}", "https://www.linkedin.com/in/rahul-sharma-graintest-2")
    assert one["lead_id"] != two["lead_id"]


def test_one_person_spelled_two_ways_is_one_lead():
    one = _ingest(f"Chen {TAG}", "https://www.linkedin.com/in/chen-graintest")
    two = _ingest(f"Chen {TAG}", "https://linkedin.com/in/Chen-GrainTest/?trk=feed")
    assert one["lead_id"] == two["lead_id"]


def test_an_underscore_is_not_a_wildcard():
    one = _ingest(f"Dee {TAG}", "https://www.linkedin.com/in/dee_graintest")
    two = _ingest(f"Dee {TAG}", "https://www.linkedin.com/in/deexgraintest")
    assert one["lead_id"] != two["lead_id"]


def test_the_migration_collapses_existing_reloads():
    """Run against the old shape, as an install upgrading from version 10 would."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE lead_interactions (id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id INTEGER NOT NULL, "
        "post_id INTEGER, post_urn TEXT, interaction_type TEXT NOT NULL, comment_text TEXT, "
        "suggested_dm_reply TEXT, capture_context TEXT, interacted_at TIMESTAMP)"
    )
    rows = [
        (1, POST, "COMMENT", "Nice rollout", "2026-09-01 10:00:00"),
        (1, POST, "COMMENT", "nice   rollout", "2026-09-03 10:00:00"),
        (1, POST, "COMMENT", "Nice rollout", "2026-09-05 10:00:00"),
        (1, POST, "LIKE", "Reacted to post on LinkedIn", "2026-09-01 10:00:00"),
        (2, POST, "COMMENT", "Different person", "2026-09-02 10:00:00"),
    ]
    conn.executemany(
        "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at) "
        "VALUES (?,?,?,?,?)", rows)

    migrations._migrate_interaction_grain(conn.cursor())

    kept = conn.execute(
        "SELECT lead_id, interaction_type, comment_text, seen_count, first_seen_at, last_seen_at "
        "FROM lead_interactions ORDER BY lead_id, interaction_type").fetchall()
    assert kept == [
        (1, "COMMENT", "Nice rollout", 3, "2026-09-01 10:00:00", "2026-09-05 10:00:00"),
        (1, "LIKE", None, 1, "2026-09-01 10:00:00", "2026-09-01 10:00:00"),
        (2, "COMMENT", "Different person", 1, "2026-09-02 10:00:00", "2026-09-02 10:00:00"),
    ]
