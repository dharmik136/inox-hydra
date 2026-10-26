"""
The studio can tell network reading "off" from "on and matching nothing".
=========================================================================

Cycle 4, track 1, items 2 and 3. Neither heartbeat carried the switch state
or the registration state, so on the owner's install `never_run` for the two
network readers could mean the switch was off, the page was never reloaded,
the browser failed to register the reader, or LinkedIn's calls no longer match
the bridge's patterns, and the studio could not say which.

Both heartbeats now carry a `network_reading` object and the page heartbeat
carries the Resource Timing coverage meter: how many LinkedIn data calls the
page made, by path and GraphQL query name, never a query string or a URN.
Setup and the side panel read one sentence from one definition.

Strict Invariants:
- Zero em-dashes.
- Nothing invented: no heartbeat has carried the state means null, not off.
"""

import json
import os
import shutil
import sys
import tempfile

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_t1_nr_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    from database import init_db
    init_db()
    yield
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture
def client(studio):
    import app as app_module
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def _beat(client, **body):
    answer = client.post("/api/v1/bridge/heartbeat", json={"extension_version": "test", **body})
    assert answer.status_code == 200, answer.text
    return answer.json()


def _bridge(client):
    return client.get("/api/v1/onboarding/state").json()["bridge"]


ON_SEEING = {"switch": True, "registered": True, "injected": True,
             "voyager_calls_seen": 12, "matched": 3, "captured": 2, "last_capture_at": "2026-10-26T10:00:00+00:00"}


def test_an_extension_that_has_not_reported_the_state_leaves_it_unmeasured(client):
    _beat(client, page_kind="feed")
    bridge = _bridge(client)
    assert bridge["network_reading"] is None, "a heartbeat with no state was turned into a state"


def test_off_is_a_sentence(client):
    _beat(client, page_kind="feed", network_reading={"switch": False})
    reading = _bridge(client)["network_reading"]
    assert reading["state"] == "off"
    assert reading["sentence"] == "Network reading is off."


def test_on_and_seeing_calls_names_the_counts(client):
    _beat(client, page_kind="feed", network_reading=ON_SEEING,
          voyager_calls={"/voyager/api/graphql voyagerFeedDashMainFeed": 9, "/voyager/api/identity/dash/profiles": 3})
    reading = _bridge(client)["network_reading"]
    assert reading["state"] == "seeing"
    assert reading["sentence"] == "Network reading is on and seeing 12 LinkedIn data calls, 3 matched."
    assert reading["voyager_calls_seen"] == 12 and reading["matched"] == 3
    assert reading["last_capture_at"] == "2026-10-26T10:00:00+00:00"


def test_on_and_matching_nothing_is_the_third_sentence(client):
    _beat(client, page_kind="feed", network_reading={**ON_SEEING, "matched": 0, "captured": 0, "last_capture_at": None})
    reading = _bridge(client)["network_reading"]
    assert reading["state"] == "matching_nothing"
    assert reading["sentence"].startswith("Network reading is on and matching nothing")
    assert "12 LinkedIn data calls" in reading["sentence"]


def test_a_page_opened_before_the_switch_is_said(client):
    _beat(client, page_kind="feed", network_reading={**ON_SEEING, "injected": False, "matched": 0, "captured": 0})
    reading = _bridge(client)["network_reading"]
    assert "reload" in reading["sentence"].lower()


def test_a_reader_the_browser_did_not_register_is_said(client):
    _beat(client, page_kind="service_worker", network_reading={"switch": True, "registered": False})
    reading = _bridge(client)["network_reading"]
    assert "register" in reading["sentence"].lower()


def test_the_worker_heartbeat_alone_does_not_invent_a_call_count(client):
    _beat(client, page_kind="service_worker", network_reading={"switch": True, "registered": True})
    reading = _bridge(client)["network_reading"]
    assert reading["voyager_calls_seen"] is None
    assert "no LinkedIn page has reported" in reading["sentence"]


def test_the_newest_page_report_supplies_the_calls_when_the_worker_beat_is_newer(client):
    _beat(client, page_kind="feed", network_reading=ON_SEEING,
          voyager_calls={"/voyager/api/graphql voyagerFeedDashMainFeed": 9})
    _beat(client, page_kind="service_worker", network_reading={"switch": True, "registered": True})
    reading = _bridge(client)["network_reading"]
    assert reading["voyager_calls_seen"] == 12 and reading["matched"] == 3
    assert reading["state"] == "seeing"


def test_the_coverage_meter_is_kept_and_answered_without_query_strings(client):
    _beat(client, page_kind="feed", network_reading=ON_SEEING,
          voyager_calls={"/voyager/api/graphql voyagerFeedDashMainFeed": 9,
                         "/voyager/api/graphql?queryId=secret.abc&variables=(urn:li:fsd_profile:ACoAA)": 1})
    health = client.get("/api/v1/extension/health").json()
    calls = health["network_reading"]["voyager_calls"]
    assert calls == {"/voyager/api/graphql voyagerFeedDashMainFeed": 9}, "a key carrying a query string was kept"
    assert health["network_reading"]["sentence"].startswith("Network reading is on")


def test_the_opt_in_readers_are_listed_only_while_the_switch_is_on(client):
    labels = [h["extractor"] for h in client.get("/api/v1/onboarding/state").json()["health"]]
    assert "voyager_feed_updates" not in labels, "listed with the switch unknown"
    _beat(client, page_kind="feed", network_reading={"switch": False})
    labels = [h["extractor"] for h in client.get("/api/v1/onboarding/state").json()["health"]]
    assert "voyager_feed_updates" not in labels, "listed with the switch off"
    _beat(client, page_kind="feed", network_reading=ON_SEEING)
    labels = [h["extractor"] for h in client.get("/api/v1/onboarding/state").json()["health"]]
    assert "voyager_feed_updates" in labels and "voyager_creator_analytics" in labels, (
        "with the switch on, the readers that have never matched are hidden, which is the one time they matter")


def test_a_bad_shape_is_ignored_rather_than_stored(client):
    _beat(client, page_kind="feed", network_reading={"switch": "yes", "voyager_calls_seen": "lots"})
    reading = _bridge(client)["network_reading"]
    assert reading is None or reading["voyager_calls_seen"] is None


def test_the_workers_registration_outlives_a_newer_page_heartbeat(client):
    """Only the worker can know the reader is registered; a page beat must not blank it."""
    _beat(client, page_kind="service_worker", network_reading={"switch": True, "registered": True})
    _beat(client, page_kind="feed", network_reading={**ON_SEEING, "registered": None})
    reading = _bridge(client)["network_reading"]
    assert reading["registered"] is True
    assert reading["state"] == "seeing"


def test_the_side_panels_list_follows_the_same_rule_as_setup(client):
    """The panel listed all five network readers as NOT SEEN YET with the switch off."""
    _beat(client, page_kind="feed", network_reading={"switch": False})
    names = [h["extractor"] for h in client.get("/api/v1/extension/health").json()["extractors"]]
    assert not [n for n in names if n.startswith("voyager_")]
    _beat(client, page_kind="feed", network_reading=ON_SEEING)
    names = [h["extractor"] for h in client.get("/api/v1/extension/health").json()["extractors"]]
    assert len([n for n in names if n.startswith("voyager_")]) == 5


def test_a_call_key_that_still_names_a_member_or_a_post_is_refused(client):
    """An extension that did not strip an identifier from a path is not trusted to have."""
    _beat(client, page_kind="feed", network_reading=ON_SEEING, voyager_calls={
        "/voyager/api/identity/profiles/plainwordvanity/profileView": 1,
        "/voyager/api/feed/updates/7385000000000000001": 1,
        "/voyager/api/identity/profiles/_id_/profileView": 2,
        "/voyager/api/graphql voyagerFeedDashMainFeed": 9})
    calls = client.get("/api/v1/extension/health").json()["network_reading"]["voyager_calls"]
    assert calls == {"/voyager/api/identity/profiles/_id_/profileView": 2,
                     "/voyager/api/graphql voyagerFeedDashMainFeed": 9}
