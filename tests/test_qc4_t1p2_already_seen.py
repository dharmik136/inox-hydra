"""
A capture the studio has just taken is answered already_seen, and a read is one request.
======================================================================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 5 to 7).
Ten tabs open on one post each sent every person on it, so the studio wrote
each engagement ten times: one row, but seen_count 10 and ten turns of the
single writer for one fact. A tab read thirty people as thirty requests.

The studio now keeps the keys of what it accepted in the last ten minutes,
by its own grain (the creator, the post, the person, how they engaged and
which comment), and answers a replay nothing_new / already_seen before the
writer. One read sends its people as one request carrying items[], each
answered on its own; the writer takes the whole read in one turn. A post's
analytics reading is keyed by its hour, as its table is.

Every name here is invented.

Strict Invariants:
- Zero em-dashes.
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

ME = "test-creator"


def _urn_days_ago(days, salt=1):
    when = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(when.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1p2_seen_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    import ingest_contract
    ingest_contract.RECENT.clear()
    from app import app
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    client = TestClient(app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    assert client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                         "display_name": "T"}).status_code == 200
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200
    urn = _urn_days_ago(2)
    assert client.post("/api/v1/self/posts/ingest", json={"author": ME, "posts": [
        {"activity_urn": urn, "actor": ME, "text": "A post of mine."}]}).status_code == 200
    client.post_urn = urn
    yield client
    ingest_contract.RECENT.clear()
    shutil.rmtree(home, ignore_errors=True)


def _person(n, post_urn, kind="COMMENT", words=None):
    return {"full_name": f"Person {n}", "linkedin_urn": f"https://www.linkedin.com/in/person-{n}-example",
            "headline": "Engineer", "interaction_type": kind, "comment_text": words if words is not None else f"Comment {n}",
            "post_urn": post_urn, "post_author": ME, "idempotency_key": f"k{n}"}


def _seen_counts(post_urn):
    from database import get_db
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT seen_count FROM lead_interactions WHERE post_urn = ? ORDER BY id",
                                            (post_urn,))]
    finally:
        conn.close()


def test_a_read_is_one_request_answered_item_by_item(studio):
    items = [_person(n, studio.post_urn) for n in range(5)]
    answer = studio.post("/api/v1/crm/interactions/ingest", json={"items": items})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["outcome"] == "accepted" and body["items_accepted"] == 5
    assert [a["idempotency_key"] for a in body["items"]] == [f"k{n}" for n in range(5)]
    assert all(a["outcome"] == "accepted" for a in body["items"])
    assert _seen_counts(studio.post_urn) == [1] * 5


def test_the_same_read_again_is_already_seen_and_counts_nobody_twice(studio):
    items = [_person(n, studio.post_urn) for n in range(5)]
    studio.post("/api/v1/crm/interactions/ingest", json={"items": items})
    again = studio.post("/api/v1/crm/interactions/ingest", json={"items": items}).json()
    assert again["outcome"] == "nothing_new" and again["items_accepted"] == 0
    assert {a["reason"] for a in again["items"]} == {"already_seen"}
    assert _seen_counts(studio.post_urn) == [1] * 5, "a replay was written as a second sighting"


def test_an_older_extensions_one_by_one_replay_is_already_seen_too(studio):
    person = _person(1, studio.post_urn)
    first = studio.post("/api/v1/crm/interactions/ingest", json=person).json()
    assert first["outcome"] == "accepted"
    second = studio.post("/api/v1/crm/interactions/ingest", json=person).json()
    assert second["outcome"] == "nothing_new" and second["reason"] == "already_seen"
    assert _seen_counts(studio.post_urn) == [1]


def test_a_new_comment_by_the_same_person_is_a_new_fact(studio):
    studio.post("/api/v1/crm/interactions/ingest", json=_person(1, studio.post_urn, words="First words"))
    answer = studio.post("/api/v1/crm/interactions/ingest", json=_person(1, studio.post_urn, words="Second words")).json()
    assert answer["outcome"] == "accepted"
    assert _seen_counts(studio.post_urn) == [1, 1]


def test_after_the_horizon_a_sighting_counts_again(studio, monkeypatch):
    import ingest_contract
    person = _person(1, studio.post_urn)
    studio.post("/api/v1/crm/interactions/ingest", json=person)
    clock = ingest_contract.time.monotonic
    monkeypatch.setattr(ingest_contract.time, "monotonic", lambda: clock() + ingest_contract.RECENT_HORIZON_SECONDS + 1)
    assert studio.post("/api/v1/crm/interactions/ingest", json=person).json()["outcome"] == "accepted"
    assert _seen_counts(studio.post_urn) == [2]


def test_a_refusal_is_not_remembered_so_asking_again_can_succeed(studio):
    stranger_post = _urn_days_ago(3, salt=9)
    person = dict(_person(1, stranger_post), post_author=None)
    first = studio.post("/api/v1/crm/interactions/ingest", json={"items": [person]}).json()
    assert first["items"][0]["outcome"] != "accepted"
    assert first["items"][0]["reason"] != "already_seen"
    second = studio.post("/api/v1/crm/interactions/ingest", json={"items": [person]}).json()
    assert second["items"][0]["reason"] != "already_seen", "a refusal was remembered as a replay"


def test_a_read_is_capped_at_three_hundred_people(studio):
    items = [_person(n, studio.post_urn) for n in range(301)]
    answer = studio.post("/api/v1/crm/interactions/ingest", json={"items": items})
    assert answer.status_code == 422 or answer.json().get("outcome") == "refused"


def test_a_posts_analytics_reading_twice_in_its_hour_is_already_seen(studio):
    reading = {"author": ME, "activity_urn": studio.post_urn, "metrics": {"impressions": 120, "reactions": 4}}
    assert studio.post("/api/v1/self/posts/analytics", json=reading).json()["status"] == "success"
    again = studio.post("/api/v1/self/posts/analytics", json=reading).json()
    assert again["outcome"] == "nothing_new" and again["reason"] == "already_seen"
