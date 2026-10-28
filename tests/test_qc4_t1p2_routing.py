"""
A capture lands in the creator profile of the account it was read in.
=====================================================================

Cycle 4, track 1, phase 2 (the capture report's Appendix B, days 8 and 9).
Every capture went to whichever creator profile the studio had active, so
with an Agency licence and two browsers signed in to two clients' LinkedIn
accounts, one client's posts and engagers landed in the other's profile, or
were refused there and lost. The worker now names the account each capture
was read in (X-Inox-Account, the browser's signed-in LinkedIn account, which
is the creator's own), and the studio routes the capture to the profile that
has confirmed that account.

A capture for an account no profile holds is answered "held": the worker
keeps it, Health shows it, and it is sent when a profile for that account is
confirmed. It is never written into the active profile. A profile still
being set up takes what its browser reads, as before, so a new client can be
onboarded; and a capture that names no account goes to the active profile.

Every name here is invented. The licence is signed with a throwaway key.

Strict Invariants:
- Zero em-dashes.
"""

import base64
import os
import sqlite3
import sys
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "studio", "backend"))

THROWAWAY_SECRET = os.urandom(32)
ALICE, BOB, CAROL = "alice-example", "bob-example", "carol-example"


def _agency_key():
    import ed25519
    import licensing
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    return licensing.encode(payload, lambda message: ed25519.sign(THROWAWAY_SECRET, message))


def _confirm(profile_id, vanity):
    import paths
    from database import get_db
    with paths.using_profile(profile_id):
        conn = get_db()
        with conn:
            conn.execute("INSERT INTO creator_identity (id, vanity, confirmed_at) VALUES (1, ?, ?) "
                         "ON CONFLICT(id) DO UPDATE SET vanity = excluded.vanity, confirmed_at = excluded.confirmed_at",
                         (vanity, datetime.now(timezone.utc).isoformat()))
        conn.close()


@pytest.fixture
def agency(tmp_path, monkeypatch):
    import ed25519
    import licensing
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY_SECRET)).decode()])
    from database import init_db
    from app import app
    from fastapi.testclient import TestClient
    from security import TOKEN_HEADER, get_or_create_token
    import bridge_routing
    init_db()
    client = TestClient(app, base_url="http://127.0.0.1:8000", headers={TOKEN_HEADER: get_or_create_token()})
    assert client.post("/api/v1/licence", json={"key": _agency_key()}).status_code == 200
    assert client.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"}).status_code == 200
    client.post("/api/v1/accounts/switch", json={"account_id": "default"})
    _confirm("default", ALICE)
    _confirm("client-b", BOB)
    bridge_routing.forget()
    yield client
    bridge_routing.forget()


def _own_posts(profile_id):
    import paths
    with paths.using_profile(profile_id):
        db = paths.get_db_path()
    conn = sqlite3.connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT activity_urn FROM own_posts")]
    finally:
        conn.close()


def _captures(profile_id):
    import paths
    with paths.using_profile(profile_id):
        db = paths.get_db_path()
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0]
    finally:
        conn.close()


def _posts(client, vanity, urn, account=None):
    headers = {"X-Inox-Account": account} if account else {}
    return client.post("/api/v1/self/posts/ingest", headers=headers, json={
        "author": vanity, "posts": [{"activity_urn": urn, "actor": vanity, "text": "A post."}]})


URN_B = "urn:li:activity:7385000000000000101"
URN_A = "urn:li:activity:7385000000000000102"


def test_a_capture_read_in_the_second_account_lands_in_its_profile(agency):
    answer = _posts(agency, BOB, URN_B, account=BOB)
    assert answer.status_code == 200, answer.text
    assert _own_posts("client-b") == [URN_B]
    assert _own_posts("default") == [], "the second client's post landed in the active profile"


def test_a_capture_read_in_the_active_account_lands_in_the_active_profile(agency):
    assert _posts(agency, ALICE, URN_A, account=ALICE).status_code == 200
    assert _own_posts("default") == [URN_A] and _own_posts("client-b") == []


def test_a_capture_for_an_account_no_profile_holds_is_held_not_written(agency):
    answer = _posts(agency, CAROL, URN_B, account=CAROL)
    assert answer.status_code == 202, answer.text
    body = answer.json()
    assert body["outcome"] == "held" and body["account"] == CAROL
    assert _own_posts("default") == [] and _own_posts("client-b") == []


def test_a_run_of_a_reader_for_an_account_no_profile_holds_is_not_logged(agency):
    answer = agency.post("/api/v1/bridge/capture", headers={"X-Inox-Account": CAROL},
                         json={"extractor": "engagers", "items_seen": 2, "items_kept": 2})
    assert answer.status_code == 200 and answer.json()["outcome"] == "nothing_new"
    assert _captures("default") == 0 and _captures("client-b") == 0


def test_a_run_of_a_reader_is_logged_in_its_accounts_profile(agency):
    answer = agency.post("/api/v1/bridge/capture", headers={"X-Inox-Account": BOB},
                         json={"extractor": "engagers", "items_seen": 2, "items_kept": 2})
    assert answer.status_code == 200
    assert _captures("client-b") == 1 and _captures("default") == 0


def test_a_capture_that_names_no_account_goes_to_the_active_profile(agency):
    assert _posts(agency, ALICE, URN_A).status_code == 200
    assert _own_posts("default") == [URN_A]


def test_a_profile_being_set_up_takes_what_its_browser_reads(agency):
    import bridge_routing
    assert agency.post("/api/v1/accounts", json={"name": "Client C", "id": "client-c"}).status_code == 200
    assert agency.post("/api/v1/accounts/switch", json={"account_id": "client-c"}).status_code == 200
    bridge_routing.forget()
    answer = agency.post("/api/v1/identity/observe", headers={"X-Inox-Account": CAROL, "X-Inox-Profile": "client-c"},
                         json={"vanity": CAROL, "display_name": "Carol", "self_evidence": ["owner_edit_controls"]})
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "candidate"


def test_the_heartbeat_tells_the_worker_which_accounts_have_a_profile(agency):
    import hashlib
    answer = agency.post("/api/v1/bridge/heartbeat", json={"extension_version": "2.10.0", "contract_version": 1})
    told = answer.json()["profile_accounts"]
    # One-way digests: the worker recognises the account it holds captures
    # for, and no client's account name is kept in the browser.
    assert sorted(told) == sorted(hashlib.sha256(v.encode()).hexdigest() for v in (ALICE, BOB))
    assert ALICE not in answer.text and BOB not in answer.text
