"""
One path in: one shape for a capture, and three answers.
========================================================

Nine ingest routes each had their own field names, their own idea of what
identifies a post, and their own idea of what to answer. The two costs a
creator paid:

  - `/api/v1/crm/interactions/ingest` declared `post_id: Optional[int]` for a
    TEXT key, so a client sending the studio's own "post-<hex12>" got a 422
    and its capture was lost outright.
  - a capture the studio declined was answered 200 {"status": "skipped"} with
    the reason in a field the extension looked at only for the word "Setup",
    so the refusal a real creator meets most, "import your posts first", fired
    no notice anywhere.

These tests hold `studio/backend/ingest_contract.py`, which is the one place
the shape and the three answers are written, and the handshake that lets the
studio say "reload the extension" once instead of failing quietly.
"""

import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import ingest_contract
import onboarding
from database import get_db

client = TestClient(app_module.app)

ME = "t3-creator-77"
URN_MINE = "urn:li:activity:" + str(int(datetime(2025, 2, 2, tzinfo=timezone.utc).timestamp() * 1000) << 22)
URN_STRANGER = "urn:li:activity:" + str(int(datetime(2025, 4, 4, tzinfo=timezone.utc).timestamp() * 1000) << 22)

TABLES = ("creator_identity", "own_posts", "bridge_heartbeats", "captures")


@pytest.fixture(autouse=True)
def clean():
    def wipe():
        conn = get_db()
        try:
            with conn:
                for table in TABLES:
                    conn.execute(f"DELETE FROM {table}")
                conn.execute("DELETE FROM lead_interactions WHERE lead_id IN "
                             "(SELECT id FROM leads WHERE name LIKE 'T3 %')")
                conn.execute("DELETE FROM leads WHERE name LIKE 'T3 %'")
        finally:
            conn.close()
        ingest_contract.forget()
    wipe()
    yield
    wipe()


def _confirm():
    assert onboarding.observe_profile({
        "vanity": ME, "display_name": "T3 Creator",
        "self_evidence": ["owner_edit_controls"],
    })["status"] == "candidate"
    onboarding.confirm_identity(ME)


def _own_post(urn=URN_MINE):
    written = onboarding.ingest_own_posts(ME, [{"activity_urn": urn, "actor": ME,
                                                "text": "A post of mine about rollout staging.",
                                                "reactions": 4}])
    assert written["written"] == 1, written


def _capture(**extra):
    body = {
        "full_name": "T3 Asha",
        "linkedin_urn": "https://www.linkedin.com/in/t3-asha-11/",
        "headline": "VP Engineering at TraceCo",
        "interaction_type": "COMMENT",
        "comment_text": "How did you stage the rollout?",
        "post_urn": URN_MINE,
    }
    body.update(extra)
    return client.post("/api/v1/crm/interactions/ingest", json=body)


# ---------------------------------------------------------------------------
# The shape: what identifies a post
# ---------------------------------------------------------------------------

def test_a_capture_carrying_the_studios_own_post_key_is_accepted():
    """
    The measured defect: posts.id is TEXT, the field was declared int, and a
    correct value cost the creator the capture.
    """
    _confirm()
    _own_post()
    answer = _capture(post_id="post-0")
    assert answer.status_code == 200, answer.text
    assert answer.json()["outcome"] == ingest_contract.ACCEPTED


def test_the_contract_reads_the_post_key_under_either_name():
    """post_key is the field; post_id is the alias an unreloaded extension sends."""
    assert ingest_contract.post_key_of({"post_key": "post-abc123"}) == "post-abc123"
    assert ingest_contract.post_key_of({"post_id": "post-abc123"}) == "post-abc123"
    assert ingest_contract.post_key_of({"post_id": 7}) == "7"
    assert ingest_contract.post_key_of({}) is None


def test_all_three_urn_namespaces_name_a_post():
    """
    A share or a document card is a post the creator wrote. One pattern reads
    all three, so none of them is silently un-analysable.
    """
    for namespace in ("activity", "share", "ugcPost"):
        assert ingest_contract.post_urn_of({"post_urn": f"urn:li:{namespace}:7123456789012345678"})
    assert ingest_contract.post_urn_of({"post_urn": "7123456789012345678"}) is None


def test_a_person_is_identified_by_a_profile_never_by_a_name():
    assert ingest_contract.person_key_of({"profile_url": "https://www.linkedin.com/in/x/"})
    assert ingest_contract.person_key_of({"linkedin_urn": "https://www.linkedin.com/in/x/"})
    assert ingest_contract.person_key_of({"full_name": "Asha Kulkarni"}) is None


# ---------------------------------------------------------------------------
# The three answers
# ---------------------------------------------------------------------------

def test_a_stored_capture_says_accepted():
    _confirm()
    _own_post()
    body = _capture().json()
    assert body["status"] == "success" and body["outcome"] == ingest_contract.ACCEPTED
    assert body["contract_version"] == ingest_contract.CONTRACT_VERSION


def test_a_strangers_post_is_nothing_new_with_a_reason_and_is_counted():
    """
    The rule working. It stays a 200 so an extension that has not been
    reloaded still counts the person as decided rather than offering them
    again every thirty seconds, and it now carries a reason code and a
    sentence, and is counted where the studio can show it.
    """
    _confirm()
    _own_post()
    body = _capture(post_urn=URN_STRANGER, post_author="another-creator").json()
    assert body["outcome"] == ingest_contract.NOTHING_NEW
    assert body["reason"] == "not_your_post"
    assert body["message"] and body["show"] is False
    counted = client.get("/api/v1/extension/captures/waiting").json()
    assert counted["refusals"]["refusals"]["not_your_post"] == 1


def test_a_refusal_the_creator_can_act_on_is_a_409_that_names_the_reason():
    """
    Before setup the studio cannot tell whose post anything is. This answered
    200 "skipped" and reached nobody.
    """
    answer = _capture()
    assert answer.status_code == 409
    body = answer.json()
    assert body["outcome"] == ingest_contract.REFUSED
    assert body["reason"] == "setup_needed"
    assert body["show"] is True
    # The sentence is repeated as a plain `detail` string, which is where every
    # reader written before this contract looks.
    assert body["detail"] == body["message"]


def test_a_creator_with_no_imported_posts_is_told_to_import():
    """
    The refusal a real creator meets most. The gate said "not on one of your
    posts" to someone who had imported nothing, which is both wrong and
    unactionable.
    """
    _confirm()
    answer = _capture(post_urn=URN_STRANGER, post_author=None)
    assert answer.status_code == 409
    body = answer.json()
    assert body["reason"] == "import_posts_first"
    assert "import your posts" in body["message"].lower()


def test_import_your_posts_first_reaches_the_creator_on_the_analytics_route():
    """
    `/api/v1/self/posts/analytics` already answered 409 with the sentence, and
    own_pages.js collapsed it to null. The body now carries the reason code and
    `show`, so the extension has something to put on the page.
    """
    _confirm()
    _own_post()
    answer = client.post("/api/v1/self/posts/analytics",
                         json={"author": ME, "activity_urn": URN_STRANGER, "metrics": {"impressions": 10}})
    assert answer.status_code == 409
    body = answer.json()
    assert body["reason"] == "import_posts_first"
    assert body["show"] is True and body["detail"] == body["message"]


def test_every_reason_the_gate_can_give_is_in_the_contract():
    """
    One definition, one place: the gate's reasons live in ingest_contract and
    every one of them classifies to an outcome, so the sentence a creator reads
    and the outcome the extension acts on cannot drift apart.
    """
    _confirm()
    reasons = [
        onboarding.engagement_gate("https://www.linkedin.com/in/stranger/", URN_STRANGER, "another-creator"),
        onboarding.engagement_gate(f"https://www.linkedin.com/in/{ME}/", URN_MINE, ME),
        onboarding.engagement_gate("https://www.linkedin.com/in/stranger/", URN_STRANGER, None),
    ]
    for reason in reasons:
        verdict = ingest_contract.classify(reason)
        assert verdict is not None and verdict[0] != "refused", reason
        assert verdict[1] in (ingest_contract.NOTHING_NEW, ingest_contract.REFUSED)


# ---------------------------------------------------------------------------
# The handshake
# ---------------------------------------------------------------------------

def test_the_heartbeat_answers_which_contract_the_studio_speaks():
    answer = client.post("/api/v1/bridge/heartbeat",
                         json={"extension_version": "2.6.1", "page_kind": "feed",
                               "contract_version": ingest_contract.CONTRACT_VERSION})
    shake = answer.json()["handshake"]
    assert shake["contract_version"] == ingest_contract.CONTRACT_VERSION
    assert shake["reload_required"] is False and shake["message"] is None


def test_an_extension_that_has_not_been_reloaded_is_told_once_what_to_do():
    """
    An extension older than the contract says no contract_version at all. The
    studio knows, and answers one sentence naming the one action, instead of
    the two sides disagreeing about a field name and losing captures quietly.
    """
    answer = client.post("/api/v1/bridge/heartbeat",
                         json={"extension_version": "2.5.0", "page_kind": "feed"})
    shake = answer.json()["handshake"]
    assert shake["reload_required"] is True
    assert "Reload" in shake["message"]
    assert shake["extension_version"] == "2.5.0"
    assert shake["extension_contract_version"] is None
    # And health says the same thing, which is what the side panel reads.
    assert client.get("/api/v1/extension/health").json()["contract"]["reload_required"] is True


def test_a_capture_also_declares_the_contract_it_speaks():
    _confirm()
    _own_post()
    _capture(contract_version=ingest_contract.CONTRACT_VERSION, extension_version="2.6.1")
    assert client.get("/api/v1/extension/health").json()["contract"]["reload_required"] is False


# ---------------------------------------------------------------------------
# What is waiting, and what was refused
# ---------------------------------------------------------------------------

def test_the_studio_says_how_many_captures_are_waiting():
    """
    The extension keeps a capture it could not deliver, and nothing in the
    product could say so, so a creator had no way to learn work was waiting.
    """
    client.post("/api/v1/bridge/heartbeat",
                json={"extension_version": "2.6.1", "contract_version": 1,
                      "waiting_captures": 4, "oldest_waiting_at": "2026-10-22T09:00:00+00:00"})
    answer = client.get("/api/v1/extension/captures/waiting").json()
    assert answer["waiting"] == 4 and answer["measured"] is True
    assert "4 captures are waiting" in answer["message"]
    assert client.get("/api/v1/extension/health").json()["waiting_captures"]["waiting"] == 4


def test_a_count_nobody_has_reported_is_not_measured_rather_than_zero():
    """The honesty rule: an unmeasured number says so, it never shows a 0."""
    answer = client.get("/api/v1/extension/captures/waiting").json()
    assert answer["measured"] is False and answer["waiting"] is None
    assert "has not reported" in answer["message"]
