"""
A lead says how they actually engaged, and where their profile is.
==================================================================

The capture path created every lead without an engagement_type, so the schema
default, 'Commented', applied to people who had only reacted. The first-message
draft reads that field: "I saw you commented on my post" was written to someone
who had liked it, which is a fabricated quote in front of a real person. The
same path stored the profile URL in linkedin_urn and left profile_url empty.

Now the label follows the strongest interaction on record (a comment outranks
a repost, which outranks a reaction), and the profile URL is where the rest of
the studio looks for it.
"""

import os
import shutil
import sqlite3
import sys
import tempfile

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))
sys.path.insert(0, BACKEND)

import paths  # noqa: E402
from crm import ReverseCRMManager  # noqa: E402

PROFILE = "https://www.linkedin.com/in/grace-hopper/"
POST = "urn:li:activity:7380000000000000001"


@pytest.fixture
def crm(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_label_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    yield ReverseCRMManager()
    shutil.rmtree(home, ignore_errors=True)


def _lead():
    conn = sqlite3.connect(paths.get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute("SELECT engagement_type, profile_url FROM leads").fetchone()
    finally:
        conn.close()


def test_a_reaction_is_not_recorded_as_a_comment(crm):
    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="LIKE", post_urn=POST)
    assert _lead()["engagement_type"] == "Liked"


def test_the_profile_url_is_stored_where_it_is_read(crm):
    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="LIKE", post_urn=POST)
    assert _lead()["profile_url"] == PROFILE


def test_a_comment_outranks_an_earlier_reaction_and_is_not_undone_by_a_later_one(crm):
    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="LIKE", post_urn=POST)
    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="COMMENT",
                           comment_text="Compilers are for people.", post_urn=POST)
    assert _lead()["engagement_type"] == "Commented"
    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="REPOST", post_urn=POST)
    assert _lead()["engagement_type"] == "Commented"


def test_the_draft_does_not_claim_a_comment_from_someone_who_reacted(crm):
    from leads import generate_dm_script

    result = crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="LIKE", post_urn=POST)
    for style in ("value_add", "resource_share", "quick_chat"):
        drafted = str(generate_dm_script(result["lead_id"], style=style)).lower()
        assert "commented on" not in drafted and "in the comments" not in drafted, (
            f"the {style} draft tells someone who reacted that they commented"
        )


def test_leads_captured_before_the_fix_are_corrected(crm):
    """Migration 17 relabels existing captured leads from their own interaction rows."""
    import migrations

    crm.ingest_interaction("Grace Hopper", PROFILE, "Rear Admiral", interaction_type="LIKE", post_urn=POST)
    conn = sqlite3.connect(paths.get_db_path())
    # As the capture path used to leave it.
    conn.execute("UPDATE leads SET engagement_type = 'Commented', profile_url = NULL")
    conn.execute(
        "INSERT INTO leads (id, name, engagement_type, linkedin_urn) VALUES ('manual-1', 'Typed In', 'Commented', NULL)"
    )
    migrations._migrate_lead_engagement_labels(conn.cursor())
    conn.commit()
    rows = dict(conn.execute("SELECT id, engagement_type FROM leads").fetchall())
    urls = [r[0] for r in conn.execute("SELECT profile_url FROM leads WHERE id != 'manual-1'")]
    conn.close()

    assert rows["manual-1"] == "Commented", "a lead entered by hand lost the label it was given"
    assert [v for k, v in rows.items() if k != "manual-1"] == ["Liked"]
    assert urls == [PROFILE]
