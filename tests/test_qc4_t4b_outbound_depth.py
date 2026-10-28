"""
Outbound shows what it already holds about each relationship.
==============================================================

Batch 8 of the sections report: Outbound held, per row of
outbound_engagements, when the studio first saw you engage, which reaction
you gave, the opening of their post, and which post it was, and drew none of
it; and "matched by display name" was a footnote under the table, not beside
the figure it qualifies. Now each account carries when the studio first saw
you engage with them, your last reaction's kind and the opening of the last
post of theirs you engaged with, the engaged-back figure and list say they
are matched by display name, and one account opens to its posts you engaged
with and, where its name is one captured person's, theirs on yours with the
time between, as the studio saw both.

Strict Invariants:
- Zero em-dashes.
"""

import io
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))
SURFACE = os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "OutboundSurface.tsx")
ME = "outbound-depth-creator"


def _urn(days, salt=0):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4b_outbound_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    import app as app_module
    client = TestClient(app_module.app)
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"]})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    yield client
    shutil.rmtree(home, ignore_errors=True)


def _outbound(client, items):
    answer = client.post("/api/v1/self/outbound/ingest", json={"actor": ME, "items": items})
    assert answer.status_code == 200, answer.text


def _set_seen(target, first, last=None):
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("UPDATE outbound_engagements SET first_seen_at = ?, last_seen_at = ? WHERE target_activity_urn = ?",
                     (first, last or first, target))
    conn.close()


def test_each_account_carries_first_seen_its_last_reaction_and_the_last_excerpt(client):
    old, new = _urn(30, 1), _urn(3, 2)
    _outbound(client, [
        {"target_activity_urn": old, "kind": "reaction", "reaction_kind": "insightful",
         "target_author": "Lucia Reyes", "target_excerpt": "Dispatch is a people problem first."},
        {"target_activity_urn": new, "kind": "reaction", "reaction_kind": "celebrate",
         "target_author": "Lucia Reyes", "target_excerpt": "We shipped the new routing today."},
    ])
    _set_seen(old, "2026-09-20T10:00:00+00:00")
    _set_seen(new, "2026-10-20T10:00:00+00:00")
    [author] = client.get("/api/v1/insights/outbound").json()["authors"]
    assert author["first_seen_at"] == "2026-09-20T10:00:00+00:00"
    assert author["last_reaction_kind"] == "celebrate"
    assert author["last_excerpt"] == "We shipped the new routing today."


def test_one_account_opens_to_its_posts_and_theirs_on_yours_with_the_time_between(client):
    from crm import reverse_crm
    mine = _urn(10, 3)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": mine, "actor": ME, "text": "My post about handovers.", "reactions": 5}]})
    theirs = _urn(12, 4)
    _outbound(client, [{"target_activity_urn": theirs, "kind": "comment", "my_text": "Great point.",
                        "target_author": "Arjun Mehta", "target_excerpt": "Night shifts deserve better tools."}])
    _set_seen(theirs, "2026-10-01T09:00:00+00:00")
    lead = reverse_crm.ingest_interaction("Arjun Mehta", "https://www.linkedin.com/in/arjun-mehta-depth",
                                          "Ops lead", None, "COMMENT", "Agreed.", post_urn=mine)["lead_id"]
    later = _urn(8, 6)
    client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": later, "actor": ME, "text": "A later post of mine.", "reactions": 2}]})
    reverse_crm.ingest_interaction("Arjun Mehta", "https://www.linkedin.com/in/arjun-mehta-depth",
                                   "Ops lead", None, "COMMENT", "Again.", post_urn=later)
    from database import get_db
    conn = get_db()
    with conn:
        conn.execute("UPDATE lead_interactions SET interacted_at = '2026-10-04T09:00:00+00:00' WHERE lead_id = ? "
                     "AND post_urn = ?", (lead, mine))
        conn.execute("UPDATE lead_interactions SET interacted_at = '2026-10-09T09:00:00+00:00' WHERE lead_id = ? "
                     "AND post_urn = ?", (lead, later))
    conn.close()

    detail = client.get("/api/v1/insights/outbound/author", params={"name": "Arjun Mehta"}).json()
    [target] = detail["targets"]
    assert target["target_excerpt"] == "Night shifts deserve better tools." and target["kind"] == "comment"
    newest, oldest = detail["inbound"]
    assert newest["post_excerpt"].startswith("A later post") and oldest["post_excerpt"].startswith("My post about handovers")
    assert detail["matched_by"] == "display name"
    assert detail["lags"] == [{"from": "2026-10-01T09:00:00+00:00", "to": "2026-10-04T09:00:00+00:00", "days": 3.0}]


def test_a_name_more_than_one_person_answers_to_shows_no_inbound(client):
    from crm import reverse_crm
    for slug in ("one", "two"):
        reverse_crm.ingest_interaction("Sam Lee", f"https://www.linkedin.com/in/sam-lee-{slug}", "Engineer", None,
                                       "COMMENT", "Hi.", post_urn=_urn(5, 9))
    _outbound(client, [{"target_activity_urn": _urn(4, 5), "kind": "reaction", "target_author": "Sam Lee"}])
    detail = client.get("/api/v1/insights/outbound/author", params={"name": "Sam Lee"}).json()
    assert detail["inbound"] is None and detail["named_people"] == 2


def test_the_screen_says_matched_by_display_name_beside_engaged_back_and_draws_the_new_facts():
    with io.open(SURFACE, encoding="utf-8") as handle:
        surface = handle.read()
    figure = surface.split('label={`Engaged back')[1].split("/>")[0]
    assert "matched by display name" in figure.lower(), "the engaged-back figure does not say how it was matched"
    assert 'label="Engaged back, matched by display name"' in surface
    for field in ("first_seen_at", "last_reaction_kind", "last_excerpt", "fetchOutboundAuthor"):
        assert field in surface, f"the screen does not draw {field}"
