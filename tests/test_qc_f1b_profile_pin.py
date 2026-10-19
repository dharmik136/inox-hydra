"""
A window keeps writing to the profile it shows, or is refused.
==============================================================

WRITE-01 / PLATFORM-02: the active profile is one value for the whole studio.
With two windows open, switching profile in one left the other still showing
client A while every save it made went into client B's database, reported as
SAVED. The interface now names the profile it loaded with on every request,
and the studio refuses a write that names a profile which is no longer active.
"""

import base64
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import ed25519  # noqa: E402
import licensing  # noqa: E402
from app import app  # noqa: E402
from database import get_db, init_db  # noqa: E402
import paths  # noqa: E402

TEST_SECRET = bytes(range(32))
HEADER = "X-Inox-Profile"


def _licence():
    payload = {
        "v": 1, "id": "test", "email": "buyer@example.com", "name": "", "tier": "agency", "kind": "annual",
        "profiles": 5, "issued_at": "2026-10-19", "expires_at": "2099-01-01", "updates_until": "2099-01-01",
    }
    return licensing.encode(payload, lambda message: ed25519.sign(TEST_SECRET, message))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INOX_HYDRA_HOME", str(tmp_path))
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.setattr(licensing, "PUBLIC_KEYS", [base64.b64encode(ed25519.public_key(TEST_SECRET)).decode()])
    init_db()
    client = TestClient(app)
    assert client.post("/api/v1/licence", json={"key": _licence()}).status_code == 200
    created = client.post("/api/v1/accounts", json={"name": "Client B", "id": "client-b"})
    assert created.status_code == 200, created.text
    return client


def _posts_in(profile_id):
    with paths.using_profile(profile_id):
        conn = get_db()
        try:
            return [r["content"] for r in conn.execute("SELECT content FROM posts")]
        finally:
            conn.close()


def test_every_answer_names_the_profile_that_served_it(client):
    response = client.get("/api/posts")
    assert response.headers.get(HEADER) == "default"
    client.post("/api/v1/accounts/switch", json={"account_id": "client-b"})
    assert client.get("/api/posts").headers.get(HEADER) == "client-b"


def test_a_write_from_a_window_still_showing_the_old_profile_is_refused(client):
    shown = client.get("/api/posts").headers[HEADER]
    # Another window switches.
    assert client.post("/api/v1/accounts/switch", json={"account_id": "client-b"}).status_code == 200

    response = client.post(
        "/api/posts",
        json={"content": "Confidential: My studio's launch announcement", "status": "draft"},
        headers={HEADER: shown},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "profile_changed"
    assert "Client B" in detail["message"] and "reload" in detail["message"].lower()
    assert "Confidential: My studio's launch announcement" not in _posts_in("client-b")
    assert "Confidential: My studio's launch announcement" not in _posts_in("default")


def test_a_write_from_a_window_showing_the_active_profile_goes_through(client):
    client.post("/api/v1/accounts/switch", json={"account_id": "client-b"})
    response = client.post(
        "/api/posts", json={"content": "Client B's own draft", "status": "draft"}, headers={HEADER: "client-b"}
    )
    assert response.status_code == 200
    assert "Client B's own draft" in _posts_in("client-b")


def test_a_caller_that_names_no_profile_is_unchanged(client):
    """The extension and older windows send no header; they keep working on the active profile."""
    response = client.post("/api/posts", json={"content": "From the bridge", "status": "draft"})
    assert response.status_code == 200


def test_switching_from_a_stale_window_is_allowed(client):
    client.post("/api/v1/accounts/switch", json={"account_id": "client-b"})
    response = client.post("/api/v1/accounts/switch", json={"account_id": "default"}, headers={HEADER: "client-b"})
    assert response.status_code == 200


def test_an_unauthenticated_caller_learns_nothing_about_profiles(client):
    response = client.post(
        "/api/posts",
        json={"content": "x", "status": "draft"},
        headers={HEADER: "client-b", "X-Inox-Token": "wrong"},
    )
    assert response.status_code == 401
    assert HEADER not in response.headers
