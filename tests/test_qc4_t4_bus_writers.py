"""
Writers that met the change stream at the 2.9.0 merges.
=======================================================

Track 2's bus (studio/backend/changes.py) has every writer say what it wrote
once its write has committed, so a window reads again only then. Track 1's
branch and this one were cut before it, so two writers met it at the merge:

- record_capture's write moved into _write_capture (track 1), and the change
  track 2 put after it named the run's drift and minute from variables that
  no longer existed there, so every capture would have answered 500 after
  its row was written. The writer hands both back.
- note_own_post (track 1) records the publication and the post of an
  engagement on a post of the creator's the studio did not hold. It wrote a
  post and said nothing, so Posts and Today's cadence heard "people" alone.

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

ME = "bus-writers-creator"


def _urn(days_ago, salt):
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


@pytest.fixture
def client(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc4_t4_bus_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    init_db()
    from fastapi.testclient import TestClient
    import app as app_module
    client = TestClient(app_module.app)
    client.post("/api/v1/identity/observe", json={"vanity": ME, "self_evidence": ["owner_edit_controls"],
                                                  "display_name": "Bus Writer", "headline": "Engineer"})
    client.post("/api/v1/identity/confirm", json={"vanity": ME})
    yield client
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def said(monkeypatch):
    import changes
    heard = []
    monkeypatch.setattr(changes, "publish", lambda kind, **identifiers: heard.append((kind, identifiers)))
    return heard


def _engage(client, urn, who):
    answer = client.post("/api/v1/crm/interactions/ingest", json={
        "full_name": who.title(), "linkedin_urn": f"https://www.linkedin.com/in/{who}/",
        "headline": "Founder", "interaction_type": "COMMENT", "comment_text": "Well put.",
        "post_urn": urn, "post_author": ME})
    assert answer.status_code == 200, answer.text
    return answer.json()


def test_a_capture_still_names_its_reader_its_drift_and_its_minute(client, said):
    answer = client.post("/api/v1/bridge/capture", json={
        "extractor": "engagers", "page_kind": "own_post", "items_seen": 3, "items_kept": 1,
        "drift": ["name"], "extension_version": "2.9.0"})
    assert answer.status_code == 200, answer.text
    kind, identifiers = said[-1]
    assert kind == "capture" and identifiers["extractor"] == "engagers" and identifiers["drift"] is True
    ran = datetime.fromisoformat(identifiers["minute"] + ":00+00:00")
    assert abs((datetime.now(timezone.utc) - ran).total_seconds()) < 120, "the minute is not the run's"


def test_an_engagement_on_a_post_the_studio_did_not_hold_says_posts_then_people(client, said):
    urn = _urn(2, 7)
    assert _engage(client, urn, "first-engager")["outcome"] == "accepted"
    assert [kind for kind, _ids in said] == ["posts", "people"]


def test_an_engagement_on_a_post_the_studio_holds_says_people_alone(client, said):
    urn = _urn(2, 8)
    _engage(client, urn, "first-engager")
    said.clear()
    _engage(client, urn, "second-engager")
    assert [kind for kind, _ids in said] == ["people"]
