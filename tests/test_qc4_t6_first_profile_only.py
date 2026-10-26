"""
Decision D9: a session is synced, and a post sent, in the first profile only.
=============================================================================

LinkedIn's User Agreement, 8.2 item 1, bars using "another's account (such as
sharing log-in credentials or copying cookies)", and the studio cannot tell
whose browser a session came from. The Agency tier is five profiles on one
machine, which is the shape that clause names. So, until an official posting
route exists, a creator profile beyond the first cannot keep a LinkedIn
session and cannot send to LinkedIn, and the refusal is a sentence on the
screen that says why and what each creator can do instead.

Licence keys here are signed with a throwaway key made for the test, whose
public half is patched into PUBLIC_KEYS, as tests/test_qc_f6_profiles.py does.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import base64
import io
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

import accounts  # noqa: E402
import ed25519  # noqa: E402
import licensing  # noqa: E402
import paths  # noqa: E402

THROWAWAY_SECRET = os.urandom(32)
SECOND = "client-b"


def _agency_key():
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    return licensing.encode(payload, lambda message: ed25519.sign(THROWAWAY_SECRET, message))


@pytest.fixture
def agency(tmp_path, monkeypatch):
    """A studio with an Agency licence and a second creator profile, the second one active."""
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY_SECRET)).decode()])
    from database import init_db
    from app import app

    init_db()
    client = TestClient(app)
    assert client.post("/api/v1/licence", json={"key": _agency_key()}).status_code == 200
    assert client.post("/api/v1/accounts", json={"name": "Client B", "id": SECOND}).status_code == 200
    assert client.post("/api/v1/accounts/switch", json={"account_id": SECOND}).status_code == 200
    assert paths.get_active_profile_id() == SECOND
    return client


def _read(path):
    with io.open(os.path.join(REPO_ROOT, path), encoding="utf-8") as handle:
        return handle.read()


def _held_session():
    from database import get_db
    conn = get_db()
    try:
        return {r["key"] for r in conn.execute("SELECT key FROM settings WHERE key IN ('li_at', 'JSESSIONID')")}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Session sync
# ---------------------------------------------------------------------------

def test_a_second_profile_cannot_keep_a_session_and_is_told_why(agency):
    res = agency.post("/api/auth/cookies", json={"li_at": "AQEDnotreal", "JSESSIONID": "ajax:1", "vanity": "someone"})
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "not_first_profile"
    assert detail["message"] == licensing.FIRST_PROFILE_ONLY_REASON
    assert "own browser" in detail["message"] and "own machine" in detail["message"]
    assert _held_session() == set(), "the refused session was written anyway"


def test_the_first_profile_still_keeps_a_session(agency):
    assert agency.post("/api/v1/accounts/switch", json={"account_id": paths.DEFAULT_PROFILE_ID}).status_code == 200
    res = agency.post("/api/auth/cookies", json={"li_at": "AQEDnotreal", "JSESSIONID": "ajax:1", "vanity": "someone"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "success"
    assert _held_session() == {"li_at", "JSESSIONID"}


# ---------------------------------------------------------------------------
# Send to LinkedIn
# ---------------------------------------------------------------------------

def _seed_post(post_id="t6-second-profile-post"):
    from database import get_db
    conn = get_db()
    try:
        conn.execute("INSERT OR REPLACE INTO posts (id, content, status) VALUES (?, ?, 'draft')",
                     (post_id, "A post written in the second profile."))
        conn.commit()
    finally:
        conn.close()
    return post_id


def test_a_second_profile_is_not_ready_to_send_and_the_reason_is_a_sentence(agency):
    post_id = _seed_post()
    readiness = agency.get(f"/api/v1/posts/{post_id}/linkedin-send").json()
    assert readiness["ready"] is False
    assert readiness["code"] == "not_first_profile"
    assert readiness["reason"] == licensing.FIRST_PROFILE_ONLY_REASON


def test_a_second_profile_sending_is_refused_before_anything_else(agency, monkeypatch):
    """Even with a session faked as present, the profile rule answers first and nothing is sent."""
    import app as app_module

    monkeypatch.setattr(app_module.linkedin_client, "is_authenticated", lambda: True)
    sent = []
    monkeypatch.setattr(app_module.linkedin_client, "schedule_norm_share",
                        lambda *a, **k: sent.append(True) or {"status": "success"})
    post_id = _seed_post()
    when = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
    res = agency.post(f"/api/v1/posts/{post_id}/stage-to-linkedin",
                      json={"scheduled_at": when, "confirm": True, "confirm_account": "someone"})
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "not_first_profile"
    assert sent == [], "a second profile's post reached the client"


def test_the_client_itself_refuses_in_a_second_profile_even_in_mock_mode(agency):
    """Defence in depth: a caller that skipped readiness still cannot send from a second profile."""
    import linkedin_client as client_module

    with paths.using_profile(SECOND):
        result = client_module.LinkedInClient().schedule_norm_share("text", 1_900_000_000_000, mock=True)
    assert result["status"] == "refused"
    assert result["code"] == "not_first_profile"
    assert result["message"] == licensing.FIRST_PROFILE_ONLY_REASON
    assert "scheduled_urn" not in result


def test_the_guard_is_what_refuses(agency, monkeypatch):
    """Falsified: with the profile rule answering None, the same mock send goes through."""
    import linkedin_client as client_module

    monkeypatch.setattr(accounts, "profile_refusal", lambda feature: None)
    with paths.using_profile(SECOND):
        result = client_module.LinkedInClient().schedule_norm_share("text", 1_900_000_000_000, mock=True)
    assert result["status"] == "success" and result["mode"] == "mock"


def test_the_rule_names_the_two_features_and_nothing_else():
    assert set(licensing.FIRST_PROFILE_ONLY) == {"session_sync", "send_to_linkedin"}
    assert licensing.first_profile_only("session_sync")
    assert not licensing.first_profile_only("analytics")
    with paths.using_profile(paths.DEFAULT_PROFILE_ID):
        assert accounts.is_first_profile()
        assert accounts.profile_refusal("send_to_linkedin") is None
    with paths.using_profile(SECOND):
        assert not accounts.is_first_profile()
        assert accounts.profile_refusal("send_to_linkedin") == licensing.FIRST_PROFILE_ONLY_REASON
        assert accounts.profile_refusal("analytics") is None


# ---------------------------------------------------------------------------
# What the creator is told, in the help, the popup and the policy
# ---------------------------------------------------------------------------

SENTENCE = "own browser on that creator's own machine"


@pytest.mark.parametrize("article", [
    "docs/help/connect-your-linkedin-session.md",
    "docs/help/keep-each-creator-separate-and-enter-a-licence.md",
    "docs/help/publish-queue-or-send-to-linkedin.md",
])
def test_the_help_says_whose_browser_a_session_must_come_from(article):
    text = _read(article)
    assert SENTENCE in text, f"{article} does not say that each profile's session must come from that creator's own browser"
    assert "first" in text and "profile" in text


def test_the_policy_says_send_to_linkedin_is_for_the_first_profile_only():
    policy = _read("docs/PRIVACY_POLICY.md")
    row = next(line for line in policy.splitlines() if line.startswith("| `www.linkedin.com` |"))
    assert "first creator profile only" in row
    assert SENTENCE in row


def test_the_popup_shows_the_studios_own_sentence_when_the_session_is_refused():
    """
    The worker answered every refusal with "The studio refused the session (409)."
    A number is not a reason; the studio's detail message is read when it has one.
    """
    source = _read("studio/extension/background.js")
    handler = source[source.index('"/api/auth/cookies"'):]
    handler = handler[:handler.index("function getCookie")]
    assert "detail" in handler and "message" in handler, "the popup never reads the studio's sentence"
    assert re.search(r"response\.json\(\)", handler), "the refusal body is not read"
