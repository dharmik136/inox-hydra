"""
Quality cycle 2026-10, batch F4b: people the bridge just read.
=============================================================

AUDIENCE-16. Activity's Leads list was ordered by id, and a captured lead's id
is a hash, so "newest first" was effectively random and, in a large studio,
the people just captured were not among the 50 shown.

AUDIENCE-18. Today's "Reply to" showed the time a comment was last re-read, so
a comment first captured 13 days ago read COMMENTED, JUST NOW and jumped the
queue, and people who had only reacted were listed with nothing to reply to.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
from database import get_db

client = TestClient(app_module.app)

ME = "sample-hana"


def _ms(moment):
    return int(moment.timestamp() * 1000)


MY_POST = f"urn:li:activity:{(_ms(datetime.now(timezone.utc) - timedelta(days=20)) << 22) | 11}"


def _wipe():
    conn = get_db()
    try:
        with conn:
            conn.execute("DELETE FROM lead_interactions WHERE lead_id IN "
                         "(SELECT id FROM leads WHERE linkedin_urn LIKE '%f4b-people-probe%')")
            conn.execute("DELETE FROM leads WHERE linkedin_urn LIKE '%f4b-people-probe%'")
            for table in ("creator_identity", "own_posts"):
                conn.execute(f"DELETE FROM {table}")
    finally:
        conn.close()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _sql_time(moment):
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def _lead(lead_id, name, captured, kind="COMMENT", engagement_type=None):
    """A lead and one interaction, captured at `captured`."""
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO leads (id, name, full_name, linkedin_urn, engagement_type, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (lead_id, name, name, f"https://www.linkedin.com/in/{lead_id}-f4b-people-probe/", engagement_type,
             _sql_time(captured), _sql_time(captured)))
        conn.execute(
            "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
            "comment_key, first_seen_at, last_seen_at, seen_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (lead_id, MY_POST, kind, f"A comment from {name}." if kind == "COMMENT" else None,
             _sql_time(captured), lead_id, _sql_time(captured), _sql_time(captured)))
    conn.close()


def test_activity_lists_the_people_just_captured_first():
    now = datetime.now(timezone.utc)
    # Ids sort the opposite way to when the people were captured.
    _lead("lead-ffff-f4b", "Captured First", now - timedelta(minutes=30))
    _lead("lead-aaaa-f4b", "Captured Last", now - timedelta(minutes=1))
    _lead("lead-cccc-f4b", "Captured Between", now - timedelta(minutes=10))

    stream = client.get("/api/v1/self/activity-stream?limit=100000").json()
    names = [lead["name"] for lead in stream["recent_leads"] if lead["id"].endswith("-f4b")]
    assert names == ["Captured Last", "Captured Between", "Captured First"]


def test_activity_does_not_invent_how_someone_engaged():
    _lead("lead-dddd-f4b", "No Type", datetime.now(timezone.utc), engagement_type=None)
    conn = get_db()
    with conn:
        conn.execute("UPDATE leads SET engagement_type = NULL WHERE id = 'lead-dddd-f4b'")
    conn.close()
    stream = client.get("/api/v1/self/activity-stream?limit=100000").json()
    lead = next(l for l in stream["recent_leads"] if l["id"] == "lead-dddd-f4b")
    assert lead["engagement_type"] != "Commented"


# ---------------------------------------------------------------------------
# AUDIENCE-18
# ---------------------------------------------------------------------------

def _confirm_with_my_post():
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'Sample Hana', '2026-09-01T00:00:00+00:00')", (ME,))
        conn.execute("INSERT INTO own_posts (activity_urn, text, first_seen_at, last_seen_at) "
                     "VALUES (?, 'My post', '2026-09-01', '2026-09-01')", (MY_POST,))
    conn.close()


def _reread(lead_id):
    """Reopening the post reads the same comment again, which moves last_seen_at only."""
    conn = get_db()
    with conn:
        conn.execute("UPDATE lead_interactions SET last_seen_at = ?, seen_count = seen_count + 1 WHERE lead_id = ?",
                     (_sql_time(datetime.now(timezone.utc)), lead_id))
    conn.close()


def test_rereading_a_comment_does_not_make_it_new():
    _confirm_with_my_post()
    now = datetime.now(timezone.utc)
    _lead("lead-old-f4b", "Old Commenter", now - timedelta(days=13))
    _lead("lead-new-f4b", "New Commenter", now - timedelta(hours=2))
    _reread("lead-old-f4b")

    reply_to = client.get("/api/v1/today").json()["reply_to"]
    people = {p["lead_id"]: p for p in reply_to}
    old = people["lead-old-f4b"]
    assert old["engaged_at"].startswith((now - timedelta(days=13)).strftime("%Y-%m-%d"))
    order = [p["lead_id"] for p in reply_to]
    assert order.index("lead-new-f4b") < order.index("lead-old-f4b"), "a re-read comment jumped the queue"


def test_people_who_only_reacted_are_not_listed_to_reply_to():
    _confirm_with_my_post()
    now = datetime.now(timezone.utc)
    _lead("lead-react-f4b", "Only Reacted", now - timedelta(hours=1), kind="LIKE")
    _lead("lead-talk-f4b", "Commented", now - timedelta(hours=3))
    ids = {p["lead_id"] for p in client.get("/api/v1/today").json()["reply_to"]}
    assert "lead-talk-f4b" in ids
    assert "lead-react-f4b" not in ids
