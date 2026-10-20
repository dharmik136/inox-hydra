"""
Send to LinkedIn, fixed: the author from the bridge, one guarded route, a record.
================================================================================

BE-09: the send named "urn:li:person:current_creator" as the author of every
post, because nothing ever stored the creator's member URN, so it could not
have worked for any account. BE-08: a second route, /api/v1/scheduler/native/
stage, sent any text at any time with no confirmation, no record, and a mock
"pre-staged successfully" when no session was saved.

Owner decision: fix it. The bridge learns the signed-in member's URN on their
own profile and sends it with the session; the send goes only as that account,
only after a confirmation that named it, only inside LinkedIn's scheduling
window, and every attempt is recorded with what was sent and LinkedIn's
answer.

Every request here goes to a fake LinkedIn on 127.0.0.1. Nothing reaches the
real one.
"""

import json
import os
import socket
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import app as app_module  # noqa: E402

from database import get_db  # noqa: E402

client = TestClient(app_module.app)

PREFIX = "qc2r6-send-"
VANITY = "r6-creator"
URN = "urn:li:fsd_profile:ACoAAR6CREATOR0001"


class FakeLinkedIn:
    """A stand-in for LinkedIn's normShares endpoint, on loopback only."""

    def __init__(self):
        self.requests = []
        self.reply = (201, {"value": {"urn": "urn:li:share:7100000000000000001"}})
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode("utf-8")
                fake.requests.append({"path": self.path, "body": json.loads(body), "cookie": self.headers.get("Cookie")})
                status, answer = fake.reply
                data = json.dumps(answer).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake_linkedin(monkeypatch):
    fake = FakeLinkedIn()
    monkeypatch.setenv("INOX_ALLOW_LINKEDIN_EGRESS", "1")
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    # The client the route uses. A test elsewhere reloads linkedin_client, so
    # the module's own attribute can be a different instance from app's.
    monkeypatch.setattr(app_module.linkedin_client, "base_url", f"http://127.0.0.1:{fake.port}/voyager/api")
    app_module.linkedin_client.circuit_breaker.reset()
    # Belt and braces: no name lookup and no connection except to the fake.
    real_getaddrinfo = socket.getaddrinfo

    def loopback_names_only(host, *args, **kwargs):
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a name lookup for {host} was attempted")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", loopback_names_only)
    real_connect = socket.socket.connect

    def loopback_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"a connection to {address} was attempted")
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", loopback_only)
    yield fake
    fake.close()
    app_module.linkedin_client.circuit_breaker.reset()


@pytest.fixture
def creator():
    """A confirmed creator, put back as it was afterwards."""
    conn = get_db()
    before = conn.execute("SELECT * FROM creator_identity WHERE id = 1").fetchone()
    before = dict(before) if before else None
    conn.execute("DELETE FROM creator_identity WHERE id = 1")
    conn.execute(
        "INSERT INTO creator_identity (id, vanity, display_name, confirmed_at) VALUES (1, ?, 'Rae Six', ?)",
        (VANITY, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
    yield
    conn = get_db()
    conn.execute("DELETE FROM creator_identity WHERE id = 1")
    if before:
        columns = ", ".join(before)
        conn.execute(f"INSERT INTO creator_identity ({columns}) VALUES ({', '.join('?' for _ in before)})",
                     tuple(before.values()))
    conn.execute("DELETE FROM posts WHERE id LIKE ?", (PREFIX + "%",))
    conn.execute("DELETE FROM settings WHERE key LIKE ?", ("%" + PREFIX + "%",))
    conn.commit()
    conn.close()
    app_module.linkedin_client.clear_tokens()


def _sync(vanity=VANITY, member_urn=URN):
    body = {"li_at": "AQEDAR6liveshaped", "JSESSIONID": '"ajax:6060606060"', "vanity": vanity, "member_urn": member_urn}
    response = client.post("/api/auth/cookies", json=body)
    assert response.status_code == 200, response.text


def _seed(name, content="The post the creator approved, exactly."):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO posts (id, content, status) VALUES (?, ?, 'draft')", (PREFIX + name, content))
    conn.commit()
    conn.close()
    return PREFIX + name


def _row(post_id):
    conn = get_db()
    try:
        return dict(conn.execute("SELECT status, scheduled_for FROM posts WHERE id = ?", (post_id,)).fetchone())
    finally:
        conn.close()


def _when(**delta):
    return (datetime.now(timezone.utc) + timedelta(**(delta or {"hours": 6}))).replace(microsecond=0)


def _send(post_id, when=None, account=VANITY, **extra):
    when = when or _when()
    return client.post(f"/api/v1/posts/{post_id}/stage-to-linkedin", json={
        "scheduled_at": when.isoformat(), "confirm": True, "confirm_account": account, **extra,
    })


def _record(post_id):
    return client.get(f"/api/v1/posts/{post_id}/linkedin-send").json()


# ---------------------------------------------------------------------------
# The author comes from the bridge
# ---------------------------------------------------------------------------

def test_the_session_is_saved_with_the_account_and_its_member_urn(creator):
    _sync()
    readiness = client.get(f"/api/v1/posts/{PREFIX}none/linkedin-send").json()
    assert readiness["account"]["vanity"] == VANITY
    assert readiness["account"]["name"] == "Rae Six"
    assert readiness["account"]["member_urn_known"] is True
    assert readiness["code"] in (None, "egress_off")


def test_a_urn_that_is_not_a_member_urn_is_not_kept(creator):
    _sync(member_urn="urn:li:person:current_creator; DROP")
    assert app_module.linkedin_client.session_account()["member_urn"] is None


def test_the_send_names_the_member_the_bridge_learnt_as_the_author(creator, fake_linkedin):
    _sync()
    post_id = _seed("ok", "Line one.\n\nLine two, exactly as approved.")
    when = _when(hours=5)

    response = _send(post_id, when)

    assert response.status_code == 200, response.text
    assert len(fake_linkedin.requests) == 1
    sent = fake_linkedin.requests[0]
    assert sent["path"] == "/voyager/api/contentcreation/normShares"
    assert sent["body"]["author"] == URN, "the author is not the member the bridge learnt"
    assert "current_creator" not in json.dumps(sent["body"])
    assert sent["body"]["commentary"]["text"] == "Line one.\n\nLine two, exactly as approved."
    assert sent["body"]["scheduledAt"] == int(when.timestamp() * 1000)
    assert _row(post_id)["status"] == "scheduled"

    record = _record(post_id)["sends"]
    assert [entry["outcome"] for entry in record] == ["accepted"]
    assert record[0]["account"] == VANITY and record[0]["author_urn"] == URN
    assert record[0]["sent"]["commentary"]["text"] == "Line one.\n\nLine two, exactly as approved."
    assert "urn:li:share:7100000000000000001" in record[0]["linkedin_answer"]
    assert record[0]["scheduled_urn"] == "urn:li:share:7100000000000000001"


def test_linkedins_refusal_is_readable_and_recorded(creator, fake_linkedin):
    _sync()
    fake_linkedin.reply = (422, {"message": "Unpermitted fields present in REQUEST_BODY: author", "status": 422})
    post_id = _seed("refused")

    response = _send(post_id)

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "LinkedIn refused the post (HTTP 422" in detail
    assert "Unpermitted fields present in REQUEST_BODY: author" in detail
    assert "Nothing was scheduled" in detail
    assert _row(post_id)["status"] == "draft"
    record = _record(post_id)["sends"]
    assert record[-1]["outcome"] == "refused_by_linkedin"
    assert record[-1]["http_status"] == 422
    assert "Unpermitted fields" in record[-1]["linkedin_answer"]
    assert record[-1]["sent"]["author"] == URN


# ---------------------------------------------------------------------------
# Nothing is sent, and nothing claims to be, when the account is not right
# ---------------------------------------------------------------------------

def test_no_saved_session_is_refused_not_faked(creator, fake_linkedin):
    app_module.linkedin_client.clear_tokens()
    post_id = _seed("nosession")
    response = _send(post_id)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "no_session"
    assert fake_linkedin.requests == []
    assert _row(post_id)["status"] == "draft"


def test_an_unknown_member_urn_is_refused_with_what_to_do(creator, fake_linkedin):
    _sync(member_urn=None)
    post_id = _seed("nourn")
    readiness = _record(post_id)
    assert readiness["ready"] is False and readiness["code"] == "author_unknown"
    assert "Open your own LinkedIn profile" in readiness["reason"]
    response = _send(post_id)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "author_unknown"
    assert fake_linkedin.requests == []


def test_a_session_for_another_account_is_refused(creator, fake_linkedin):
    _sync(vanity="someone-else", member_urn="urn:li:fsd_profile:ACoAAOTHER00001")
    post_id = _seed("other")
    response = _send(post_id, account="someone-else")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "other_account"
    assert "linkedin.com/in/someone-else" in response.json()["detail"]["message"]
    assert fake_linkedin.requests == []


def test_a_confirmation_that_named_another_account_sends_nothing(creator, fake_linkedin):
    _sync()
    post_id = _seed("changed")
    response = _send(post_id, account="who-the-dialog-showed-before")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "account_changed"
    assert fake_linkedin.requests == []


@pytest.mark.parametrize("delta, words", [({"minutes": 4}, "less than 10 minutes"), ({"days": 100}, "three months")])
def test_a_time_linkedin_would_not_hold_is_refused_here(creator, fake_linkedin, delta, words):
    _sync()
    post_id = _seed("time")
    response = _send(post_id, _when(**delta))
    assert response.status_code == 400
    assert words in response.json()["detail"]
    assert fake_linkedin.requests == []


def test_without_confirmation_nothing_is_sent(creator, fake_linkedin):
    _sync()
    post_id = _seed("noconfirm")
    response = client.post(f"/api/v1/posts/{post_id}/stage-to-linkedin",
                           json={"scheduled_at": _when().isoformat(), "confirm_account": VANITY})
    assert response.status_code == 400
    assert fake_linkedin.requests == []


def test_the_client_never_names_a_stand_in_author(fake_linkedin):
    app_module.linkedin_client.save_tokens("AQEDAR6liveshaped", '"ajax:1"')
    try:
        result = app_module.linkedin_client.schedule_norm_share(content="A post.", scheduled_at_ms=1)
    finally:
        app_module.linkedin_client.clear_tokens()
    assert result["code"] == "author_unknown"
    assert fake_linkedin.requests == []


# ---------------------------------------------------------------------------
# BE-08: one guarded route
# ---------------------------------------------------------------------------

def test_the_unguarded_staging_route_is_gone(creator, fake_linkedin):
    _sync()
    response = client.post("/api/v1/scheduler/native/stage",
                           json={"content": "Text nobody approved", "scheduled_at_ms": 1})
    assert response.status_code in (404, 405)
    assert fake_linkedin.requests == []
    assert not hasattr(app_module, "NativeStageRequest")
