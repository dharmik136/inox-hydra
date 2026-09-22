"""
Tests for the local API boundary.
=================================

The bug these exist for: the studio bound to 127.0.0.1 and set
allow_origins=["*"] with credentials enabled. People read loopback binding as
"only I can reach this", which is true of other machines and false of the
browser sitting in front of it. Any page the creator had open could call the
API and read the response, so their leads, drafts and settings were readable
and writable by any site they visited.

The most important test in this file is the LinkedIn one. Allowing
https://www.linkedin.com is the obvious first instinct, since that is where the
extension's content script lives. It is also the single worst origin to trust,
because trusting it means trusting every other script on that page.

Validates:
1. A hostile page origin is refused.
2. LinkedIn specifically is refused, and stays refused.
3. DNS rebinding is refused through the Host header.
4. Requests without a valid token are refused.
5. The extension origin is accepted.
6. The interface is handed its token as a SameSite=Strict cookie.
7. The token survives a restart and is not stored in the install directory.
8. Strict Zero Em-Dash invariant.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

from app import app
import security

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# conftest patches TestClient to carry a valid token and a loopback base URL,
# which is what every other test in the suite relies on. These tests are about
# what happens when a caller does not have that, so they override per request.
client = TestClient(app)

STUDIO_PATH = "/api/v1/crm/telemetry"


def token():
    return security.get_or_create_token()


# ---------------------------------------------------------------------------
# Origin
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("origin", [
    "https://evil.example",
    "http://localhost:3000",
    "https://docs.google.com",
    "null",
])
def test_a_page_the_creator_visited_cannot_read_the_studio(origin):
    """
    The actual attack. A tab open on any site issues fetch() at 127.0.0.1 and,
    before this, the browser handed it the response.
    """
    res = client.get(STUDIO_PATH, headers={"Origin": origin, security.TOKEN_HEADER: token()})
    assert res.status_code == 403


def test_linkedin_itself_is_not_trusted_with_the_local_database():
    """
    The instinct to allowlist LinkedIn is wrong, and this test exists to keep
    somebody from acting on it later.

    The extension's content script runs inside the LinkedIn page, so its calls
    used to carry this origin. Allowing it would extend trust to every script
    on linkedin.com: LinkedIn's own code, their ad and analytics vendors, and
    anything an XSS there could run. The extension routes through its service
    worker instead, which speaks from chrome-extension://.
    """
    for origin in ("https://www.linkedin.com", "https://linkedin.com"):
        res = client.get(STUDIO_PATH, headers={"Origin": origin, security.TOKEN_HEADER: token()})
        assert res.status_code == 403, f"{origin} must never be trusted with local data"

    assert security.is_allowed_origin("https://www.linkedin.com") is False


def test_the_extension_origin_is_accepted():
    res = client.get(
        STUDIO_PATH,
        headers={"Origin": "chrome-extension://" + ("a" * 32), security.TOKEN_HEADER: token()},
    )
    assert res.status_code == 200


def test_the_interface_own_origin_is_accepted():
    res = client.get(
        STUDIO_PATH,
        headers={"Origin": "http://127.0.0.1:8000", security.TOKEN_HEADER: token()},
    )
    assert res.status_code == 200


def test_a_request_with_no_origin_still_needs_a_token():
    """
    The CLI and other non browser callers send no Origin. They are not exempt,
    they are simply checked by Host and token instead.
    """
    assert security.is_allowed_origin(None) is True
    res = client.get(STUDIO_PATH, headers={security.TOKEN_HEADER: "not-the-token"})
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# DNS rebinding
# ---------------------------------------------------------------------------

def test_a_rebound_hostname_is_refused():
    """
    An attacker points evil.example at 127.0.0.1 so their page becomes same
    origin with this server, which sidesteps the origin check entirely. The
    browser still sends Host: evil.example, and that is what catches it.
    """
    res = client.get(STUDIO_PATH, headers={"Host": "evil.example", security.TOKEN_HEADER: token()})
    assert res.status_code == 403


@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1:8000", True),
    ("localhost:8000", True),
    ("127.0.0.1", True),
    ("127.0.0.53:8000", True),
    ("[::1]:8000", True),
    ("evil.example", False),
    ("evil.example:8000", False),
    ("192.168.1.10:8000", False),
    ("", False),
    (None, False),
])
def test_loopback_host_detection(host, expected):
    assert security.is_loopback_host(host) is expected


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

def test_no_token_is_refused():
    bare = TestClient(app, headers={})
    bare.headers.pop(security.TOKEN_HEADER, None)
    res = bare.get(STUDIO_PATH)
    assert res.status_code == 401


def test_a_wrong_token_is_refused():
    res = client.get(STUDIO_PATH, headers={security.TOKEN_HEADER: "sk-guessed-wrong"})
    assert res.status_code == 401


def test_writes_are_refused_too_not_only_reads():
    """A boundary that only protects GET is not a boundary."""
    res = client.post(
        "/api/v1/internal-sheet/issues",
        headers={"Origin": "https://evil.example", security.TOKEN_HEADER: token()},
        json={"target_selector": ".x", "title": "hostile", "description": "hostile"},
    )
    assert res.status_code == 403


def test_token_comparison_does_not_short_circuit():
    real = token()
    assert security.constant_time_match(real, real) is True
    assert security.constant_time_match(real[:-1], real) is False
    assert security.constant_time_match(None, real) is False
    assert security.constant_time_match("", real) is False


def test_the_token_is_stable_across_calls():
    """A token that changed per process would unpair the extension on restart."""
    assert security.get_or_create_token() == security.get_or_create_token()


def test_the_token_lives_with_user_state_not_in_the_install():
    """
    Replacing the application folder during an update must not invalidate a
    paired extension, and two installs must never share a secret.
    """
    import paths

    token_path = os.path.join(paths.get_vault_dir(), security.TOKEN_FILENAME)
    assert os.path.abspath(token_path).startswith(os.path.abspath(paths.get_app_home()))
    assert not os.path.abspath(token_path).startswith(os.path.join(REPO_ROOT, "studio"))


def test_resetting_the_token_invalidates_the_old_one():
    original = security.get_or_create_token()
    replacement = security.reset_token()
    try:
        assert replacement != original
        res = client.get(STUDIO_PATH, headers={security.TOKEN_HEADER: original})
        assert res.status_code == 401
    finally:
        # Put the suite's shared token back, since other clients hold it.
        path = os.path.join(
            __import__("paths").get_vault_dir(), security.TOKEN_FILENAME
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(original)


# ---------------------------------------------------------------------------
# Cookie delivery
# ---------------------------------------------------------------------------

def test_the_interface_is_handed_its_token_strictly():
    """
    SameSite=Strict is the part that matters. A browser will not attach this
    cookie to a request started by another site, so a hostile page cannot ride
    on the creator's session even from the same machine.
    """
    res = client.get("/")
    header = res.headers.get("set-cookie", "")
    assert security.TOKEN_COOKIE in header
    assert "samesite=strict" in header.lower()


def test_no_script_on_the_origin_can_read_the_token():
    """
    HttpOnly, so an XSS on the studio page cannot exfiltrate the token and turn
    itself into full API access.

    The extension is unaffected: chrome.cookies.get is a privileged API that
    reads HttpOnly cookies given host permission, which it holds. Making the
    cookie script readable bought nothing and cost this.
    """
    res = client.get("/")
    assert "httponly" in res.headers.get("set-cookie", "").lower()


# ---------------------------------------------------------------------------
# The extension no longer speaks from the LinkedIn origin
# ---------------------------------------------------------------------------

def test_the_content_script_makes_no_direct_calls():
    """
    Any fetch written in content.js carries the LinkedIn origin and would be
    refused. Calls must go through the service worker.
    """
    content = open(
        os.path.join(REPO_ROOT, "studio", "extension", "content.js"), encoding="utf-8"
    ).read()
    assert "fetch(\"http://127.0.0.1" not in content
    assert "fetch('http://127.0.0.1" not in content
    assert "studioApi(" in content


def test_the_worker_relay_is_not_an_open_proxy():
    """
    Anything on the LinkedIn page can message the content script, so the relay
    accepts an exact set of paths rather than whatever it is handed.
    """
    background = open(
        os.path.join(REPO_ROOT, "studio", "extension", "background.js"), encoding="utf-8"
    ).read()
    assert "RELAYABLE_PATHS" in background
    assert "path not permitted" in background
    assert "X-Inox-Token" in background


def test_the_wildcard_origin_is_gone():
    """Checked against live code only. The comment explaining the old setting
    naturally quotes it, and that mention is the documentation, not the bug."""
    backend = open(
        os.path.join(REPO_ROOT, "studio", "backend", "app.py"), encoding="utf-8"
    ).read()
    live = [l for l in backend.splitlines() if not l.lstrip().startswith("#")]
    assert not any('allow_origins=["*"]' in l for l in live)
    assert any("allow_origins=sorted(security.allowed_origins())" in l for l in live)


def test_security_module_holds_the_zero_em_dash_invariant():
    for name in ("security.py",):
        content = open(
            os.path.join(REPO_ROOT, "studio", "backend", name), encoding="utf-8"
        ).read()
        # Never typed literally, or this file would break the rule it enforces.
        assert chr(8212) not in content, f"{name} contains an em-dash"

def test_the_health_probe_answers_without_a_token():
    """
    The desktop shell has to know whether the backend is up before it can show
    a window, and it has no token at that point. This is the only route that
    answers unauthenticated, so it must stay free of anything about the user.
    """
    bare = TestClient(app, headers={})
    bare.headers.pop(security.TOKEN_HEADER, None)
    res = bare.get("/api/v1/health")
    assert res.status_code == 200

    body = res.json()
    assert body["status"] == "ok"
    # Liveness and version only. Anything else here leaks to every process on
    # the machine.
    assert set(body) == {"status", "app", "version"}


def test_the_health_exemption_does_not_widen_to_other_routes():
    """
    request_is_exempt matches on prefix, so a route that merely starts with the
    same characters must not fall through the gate with it.
    """
    assert security.request_is_exempt("/api/v1/health") is True
    assert security.request_is_exempt("/api/v1/crm/telemetry") is False
    assert security.request_is_exempt("/api/queue/cadence-health") is False
