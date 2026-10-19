"""
The Licence, After It Ends.
===========================

An offline licence cannot be airtight, but it must not be undone by the
computer's clock, and an ended Agency licence must not keep every extra
creator profile working. Nothing is deleted or hidden when a licence ends:
a profile beyond what the licence covers can still be backed up, exported and
deleted, only not opened for work. The default profile always works.

Every key here is signed with a throwaway key made for the test, whose public
half is patched into PUBLIC_KEYS. The vendor key is never involved.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
"""

import base64
import os
import sys
from datetime import date

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ed25519  # noqa: E402
import licensing  # noqa: E402
import paths  # noqa: E402

THROWAWAY_SECRET = os.urandom(32)


def _signed(**fields):
    payload = {"v": 1, "email": "buyer@example.com", "tier": "agency", "kind": "annual", "profiles": 5,
               "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01"}
    payload.update(fields)
    return licensing.encode(payload, lambda message: ed25519.sign(THROWAWAY_SECRET, message))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(THROWAWAY_SECRET)).decode()])
    return tmp_path


# ---------------------------------------------------------------------------
# PLATFORM-23: an earlier clock does not revive an ended licence
# ---------------------------------------------------------------------------

def test_setting_the_clock_back_does_not_revive_an_ended_licence(vault):
    key = _signed(kind="monthly", issued_at="2026-10-19", expires_at="2026-11-19", updates_until="2026-11-19")
    assert licensing.install(key, today=date(2026, 10, 19))["status"] == "success"
    assert licensing.current(today=date(2026, 11, 1))["status"] == "active"

    ended = licensing.current(today=date(2026, 11, 25))
    assert ended["status"] == "expired" and ended["profile_limit"] == 1

    back = licensing.current(today=date(2026, 11, 1))
    assert back["status"] == "expired", "setting the clock back revived the licence"
    assert back["profile_limit"] == 1 and back["tier"] == "free"
    assert back["clock_behind"] is True and "2026-11-25" in back["reason"]


def test_a_renewal_still_works_while_the_clock_is_behind(vault):
    licensing.install(_signed(expires_at="2026-11-19"), today=date(2026, 10, 19))
    licensing.current(today=date(2026, 11, 25))
    renewed = licensing.install(_signed(expires_at="2026-12-31"), today=date(2026, 11, 1))
    assert renewed["status"] == "success"
    assert licensing.current(today=date(2026, 11, 1))["status"] == "active"


@pytest.fixture
def client(vault):
    from database import init_db
    from app import app

    init_db()
    return TestClient(app)


def _profile_db(home, pid):
    return os.path.join(str(home), "profiles", pid, "data", paths.DB_FILENAME)


# ---------------------------------------------------------------------------
# PLATFORM-05: an ended licence closes the profiles beyond it, and keeps them
# ---------------------------------------------------------------------------

def test_profiles_beyond_an_ended_licence_close_but_keep_their_data(client, vault):
    import sqlite3

    assert client.post("/api/v1/licence", json={"key": _signed()}).status_code == 200
    for name, pid in (("Client B", "client-b"), ("Client C", "client-c")):
        assert client.post("/api/v1/accounts", json={"name": name, "id": pid}).status_code == 200
    assert client.post("/api/v1/accounts/switch", json={"account_id": "client-c"}).status_code == 200
    assert client.post("/api/posts", json={"content": "client c work"}).status_code == 200
    conn = sqlite3.connect(_profile_db(vault, "client-c"))
    conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES "
                 "('due-in-c', 'Due', 'scheduled', '2020-01-01T09:00:00+00:00')")
    conn.commit()
    conn.close()

    assert client.delete("/api/v1/licence").status_code == 200

    listing = client.get("/api/v1/accounts").json()
    assert listing["active_account_id"] == "default", "the open profile kept working after the licence ended"
    by_id = {a["id"]: a for a in listing["accounts"]}
    assert set(by_id) == {"default", "client-b", "client-c"}, "a profile was hidden"
    assert by_id["client-c"]["locked"] is True and by_id["default"]["locked"] is False

    refused = client.post("/api/v1/accounts/switch", json={"account_id": "client-c"})
    assert refused.status_code == 402
    detail = refused.json()["detail"]
    assert "licence" in detail.lower() and "renew" in detail.lower() and "Client C" in detail

    # Nothing in it was deleted, and nothing works in it in the background.
    from scheduler import NativeScheduler

    NativeScheduler().check_every_profile()
    conn = sqlite3.connect(_profile_db(vault, "client-c"))
    rows = dict(conn.execute("SELECT id, status FROM posts").fetchall())
    conn.close()
    assert rows.get("due-in-c") == "scheduled", "the queue of a closed profile was worked"
    assert any(status == "draft" for status in rows.values())

    # It can still be backed up and exported, and deleted.
    import support

    with paths.using_profile("client-c"):
        assert os.path.exists(support.create_backup("before_closing"))
        assert os.path.exists(support.export_data(fmt="json"))
    assert client.post("/api/v1/accounts/switch", json={"account_id": "default"}).status_code == 200

    # Renewing opens it again.
    assert client.post("/api/v1/licence", json={"key": _signed()}).status_code == 200
    assert client.post("/api/v1/accounts/switch", json={"account_id": "client-c"}).status_code == 200
    client.delete("/api/v1/licence")
    gone = client.request("DELETE", "/api/v1/accounts/client-c", json={"confirm": "Client C"})
    assert gone.status_code == 200


def test_an_ended_key_cannot_be_installed_by_setting_the_clock_back(vault):
    licensing.current(today=date(2026, 11, 25))
    result = licensing.install(_signed(expires_at="2026-11-19"), today=date(2026, 11, 1))
    assert result["status"] == "error" and "2026-11-19" in result["message"]
