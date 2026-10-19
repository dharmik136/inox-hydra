"""
Creator Profiles: Deleting, Switching, Naming.
==============================================

An agency deletes a client's profile while work for it is still running,
switches to a profile a newer build wrote, and types short custom ids. These
hold the profile code to doing the right thing in each.

Licence keys here are signed with a throwaway key made for the test, whose
public half is patched into PUBLIC_KEYS.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import base64
import os
import sqlite3
import sys
import threading

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import accounts  # noqa: E402
import ed25519  # noqa: E402
import licensing  # noqa: E402
import migrations  # noqa: E402
import paths  # noqa: E402

THROWAWAY_SECRET = os.urandom(32)


def _agency_key():
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    return licensing.encode(payload, lambda message: ed25519.sign(THROWAWAY_SECRET, message))


@pytest.fixture
def agency(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY_SECRET)).decode()])
    from database import init_db
    from app import app

    init_db()
    client = TestClient(app)
    assert client.post("/api/v1/licence", json={"key": _agency_key()}).status_code == 200
    return client


# ---------------------------------------------------------------------------
# PLATFORM-07: work still running for a deleted profile does not bring it back
# ---------------------------------------------------------------------------

def test_work_pinned_to_a_deleted_profile_cannot_recreate_its_folder(agency, tmp_path):
    assert agency.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"}).status_code == 200
    folder = os.path.join(str(tmp_path), "profiles", "client-b")
    started, deleted, outcome = threading.Event(), threading.Event(), {}

    def long_running_work():
        # As an image generation does: pinned to the profile it was asked in.
        with paths.using_profile("client-b"):
            started.set()
            deleted.wait(5)
            try:
                with open(os.path.join(paths.get_generated_dir(), "gen_late.jpg"), "wb") as handle:
                    handle.write(b"client image")
                outcome["wrote"] = True
            except Exception as error:
                outcome["error"] = error

    worker = threading.Thread(target=long_running_work)
    worker.start()
    started.wait(5)
    gone = agency.request("DELETE", "/api/v1/accounts/client-b", json={"confirm": "Client B"})
    assert gone.status_code == 200
    deleted.set()
    worker.join(5)

    assert "wrote" not in outcome, "work for a deleted profile wrote the client's data back"
    assert isinstance(outcome.get("error"), paths.ProfileGone)
    assert not os.path.exists(folder), "the deleted profile's folder came back"
    again = agency.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"})
    assert again.status_code == 200, again.text


def test_a_deleted_profile_has_no_database_path(agency):
    agency.post("/api/v1/accounts", json={"name": "Client C", "id": "client-c"})
    with paths.using_profile("client-c"):
        assert accounts.delete_account("client-c", confirm="Client C")["status"] == "success"
        with pytest.raises(paths.ProfileGone):
            paths.get_db_path()


# ---------------------------------------------------------------------------
# PLATFORM-16: a profile a newer build wrote is refused with the reason
# ---------------------------------------------------------------------------

def test_switching_to_a_profile_from_a_newer_build_says_why(agency, tmp_path):
    agency.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"})
    db = os.path.join(str(tmp_path), "profiles", "client-b", "data", paths.DB_FILENAME)
    conn = sqlite3.connect(db)
    conn.execute(f"PRAGMA user_version = {migrations.SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    res = agency.post("/api/v1/accounts/switch", json={"account_id": "client-b"})
    assert res.status_code == 409, res.text
    assert "newer" in res.json()["detail"]
    assert agency.get("/api/v1/accounts").json()["active_account_id"] == "default"


# ---------------------------------------------------------------------------
# PLATFORM-19: a profile id must be a folder name Windows accepts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("reserved", ["con", "prn", "aux", "nul", "com1", "com9", "lpt1", "lpt9", "CON", "Aux"])
def test_a_windows_device_name_cannot_be_a_profile_id(agency, tmp_path, reserved):
    res = agency.post("/api/v1/accounts", json={"name": "Short Name", "id": reserved})
    assert res.status_code == 400, res.text
    assert "Windows" in res.json()["detail"]
    assert not os.path.exists(os.path.join(str(tmp_path), "profiles", reserved.lower()))


# ---------------------------------------------------------------------------
# WRITE-28: the switcher counts the drafts the Composer saves
# ---------------------------------------------------------------------------

def test_the_switcher_counts_composer_drafts(agency):
    assert agency.post("/api/posts", json={"content": "A draft from the Composer"}).status_code == 200
    me = next(a for a in agency.get("/api/v1/accounts").json()["accounts"] if a["id"] == "default")
    assert me["drafts_count"] == 1, "a profile with a draft was shown as having none"
    assert me["posts_count"] == 0, "the draft was counted as a post too"

    assert agency.post("/api/posts", json={"content": "Queued", "status": "scheduled",
                                           "scheduled_for": "2099-01-01T09:00:00+00:00"}).status_code == 200
    me = next(a for a in agency.get("/api/v1/accounts").json()["accounts"] if a["id"] == "default")
    assert (me["drafts_count"], me["posts_count"]) == (1, 1)


def test_ordinary_short_ids_are_still_accepted(agency):
    for pid in ("cona", "com10", "lpt", "aux-1"):
        assert agency.post("/api/v1/accounts", json={"name": pid, "id": pid}).status_code == 200, pid
