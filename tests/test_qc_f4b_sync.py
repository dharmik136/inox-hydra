"""
Quality cycle 2026-10, batch F4b: history imports and Sync All.
==============================================================

SETUP-14. An import request older than 30 minutes is never picked up by the
extension, but Setup showed it as WAITING FOR THE PAGE TO OPEN forever.

SETUP-16. Sync All's chain lived only in server memory, so a studio restart
in the middle of an import dropped the comments and reactions steps without
a word.

SETUP-11 and SETUP-22. Sync All said "Autonomous activity sync started"
whether or not a browser opened, and the launcher's messages named Chrome as
supported, said "this PC" on a Mac, and pointed at a path Setup never showed.
"""

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module
import onboarding
from database import get_db

client = TestClient(app_module.app)

ME = "sample-frank"


def _wipe():
    conn = get_db()
    try:
        with conn:
            for table in ("creator_identity", "own_posts", "self_import_requests", "outbound_engagements",
                          "bridge_heartbeats"):
                conn.execute(f"DELETE FROM {table}")
            conn.execute("DELETE FROM settings WHERE key IN ('creator_profile', 'identity_filled_profile', "
                         "'history_sync_chain')")
    finally:
        conn.close()
    onboarding.cancel_sync_chain()


@pytest.fixture(autouse=True)
def clean():
    _wipe()
    yield
    _wipe()


def _confirm():
    client.post("/api/v1/identity/observe", json={"vanity": ME, "display_name": "Sample Frank",
                                                  "self_evidence": ["owner_edit_controls"]})
    assert client.post("/api/v1/identity/confirm", json={"vanity": ME}).status_code == 200


def _imports():
    return {i["id"]: i for i in client.get("/api/v1/onboarding/state").json()["imports"]}


def _age(request_id, minutes):
    conn = get_db()
    with conn:
        conn.execute("UPDATE self_import_requests SET requested_at = ? WHERE id = ?",
                     ((datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(), request_id))
    conn.close()


# ---------------------------------------------------------------------------
# SETUP-14
# ---------------------------------------------------------------------------

def test_a_request_the_extension_will_no_longer_take_says_it_expired():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    _age(request_id, 31)

    assert client.post("/api/v1/self/imports/pending", json={"kind": "posts"}).json()["request"] is None
    entry = _imports()[request_id]
    assert entry["outcome"] == "expired"
    assert entry["finished_at"] is not None


def test_a_recent_request_is_still_waiting():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    _age(request_id, 5)
    entry = _imports()[request_id]
    assert entry["finished_at"] is None and entry["outcome"] is None


def test_an_import_already_scrolling_is_not_expired_under_it():
    _confirm()
    request_id = client.post("/api/v1/self/imports", json={"kind": "posts"}).json()["id"]
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "started"})
    _age(request_id, 45)
    assert _imports()[request_id]["finished_at"] is None
    client.post("/api/v1/self/imports/event", json={"id": request_id, "event": "finished",
                                                    "items_seen": 30, "outcome": "end_of_list"})
    assert _imports()[request_id]["outcome"] == "end_of_list"
