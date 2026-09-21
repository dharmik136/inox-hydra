"""
The Passive Observer Boundary
=============================
This studio observes LinkedIn pages the creator opened themselves. It does not
fetch on their behalf. DAY_03_IMPLEMENTATION_SPEC.md:87 states the guarantee as
"exactly 0 additional HTTP requests".

That guarantee was false. Three call sites in linkedin_client.py issued
authenticated requests using the stored session cookie:

  - GET /voyager/api/me inside sync_live_profile_and_stats
  - GET /voyager/api/me inside check_session_health
  - POST /voyager/api/contentcreation/normShares inside schedule_norm_share

The first was reachable in ordinary use without the creator doing anything.
background.js called syncActiveSessionToStudio() from inside its webRequest
listener, which POSTed to /api/auth/cookies, which called the sync. So merely
loading the creator analytics page caused the backend to make its own request.
The 15 minute alarm did the same thing on a timer.

Every outbound call now passes egress_guard(), which refuses unless
INOX_ALLOW_LINKEDIN_EGRESS is set. These tests assert the count, because a
boundary that is only described in a document is not a boundary.
"""

import importlib
import os

import pytest


@pytest.fixture
def client_module():
    import studio.backend.linkedin_client as lc
    importlib.reload(lc)
    lc.egress_stats["refused"] = 0
    lc.egress_stats["performed"] = 0
    lc.egress_stats["last_refused_endpoint"] = None
    return lc


@pytest.fixture
def no_egress(monkeypatch):
    monkeypatch.delenv("INOX_ALLOW_LINKEDIN_EGRESS", raising=False)


class ForbiddenRequest(AssertionError):
    """Raised by the stub when anything tries to leave the process."""


@pytest.fixture
def tripwire(monkeypatch):
    """
    Replace the HTTP verbs so any real outbound attempt fails loudly.

    The stub records rather than silently returning, so a test cannot pass by
    virtue of the request failing for an unrelated reason such as no network.
    """
    attempts = []

    def forbidden(method):
        def _call(url, *args, **kwargs):
            attempts.append((method, str(url)))
            raise ForbiddenRequest(f"{method} {url}")
        return _call

    import studio.backend.linkedin_client as lc
    monkeypatch.setattr(lc.requests, "get", forbidden("GET"))
    monkeypatch.setattr(lc.requests, "post", forbidden("POST"))
    monkeypatch.setattr(lc.requests, "put", forbidden("PUT"))
    return attempts


def _store_tokens(lc):
    """Give the client a session, so nothing is skipped merely for lacking one."""
    lc.linkedin_client.save_tokens("AQEDATEST_li_at_value", '"ajax:1234567890"')


def test_saving_a_session_token_contacts_nobody(client_module, no_egress, tripwire):
    """
    The regression in its original shape: POST /api/auth/cookies triggered an
    authenticated GET to LinkedIn. The extension called it on a 15 minute alarm
    and on every creator-analytics response.
    """
    from fastapi.testclient import TestClient
    import studio.backend.app as app_module

    client = TestClient(app_module.app, raise_server_exceptions=False)
    res = client.post(
        "/api/auth/cookies",
        json={"li_at": "AQEDATEST_li_at_value", "JSESSIONID": '"ajax:1234567890"'},
    )

    assert res.status_code == 200, res.text
    assert not tripwire, (
        f"Saving a token produced {len(tripwire)} outbound request(s): {tripwire}"
    )


def test_profile_sync_refuses_by_default(client_module, no_egress, tripwire):
    _store_tokens(client_module)
    result = client_module.linkedin_client.sync_live_profile_and_stats()

    assert result["status"] == "egress_refused", result
    assert not tripwire, f"An outbound request escaped the gate: {tripwire}"
    assert client_module.egress_stats["refused"] >= 1
    assert client_module.egress_stats["performed"] == 0


def test_session_health_check_refuses_by_default(client_module, no_egress, tripwire):
    _store_tokens(client_module)
    result = client_module.linkedin_client.check_session_health()

    assert result["status"] == "egress_refused", result
    assert not tripwire, f"An outbound request escaped the gate: {tripwire}"


def test_publishing_refuses_by_default(client_module, no_egress, tripwire):
    """
    A live POST to contentcreation/normShares publishes as the creator. That is
    the furthest possible thing from passive observation.
    """
    _store_tokens(client_module)
    result = client_module.linkedin_client.schedule_norm_share(
        content="A test post that must never reach LinkedIn.",
        scheduled_at_ms=1893456000000,
    )

    assert result["status"] == "egress_refused", result
    assert not tripwire, f"A publish request escaped the gate: {tripwire}"


def test_the_gate_opens_only_when_explicitly_asked(client_module, monkeypatch, tripwire):
    """
    The refusal must be a deliberate default, not an inability. If setting the
    flag changed nothing, these tests would be proving the wrong thing.
    """
    monkeypatch.setenv("INOX_ALLOW_LINKEDIN_EGRESS", "1")
    _store_tokens(client_module)

    # The method catches broadly and returns an error dict, so the tripwire's
    # exception does not propagate. What it recorded is the evidence.
    result = client_module.linkedin_client.sync_live_profile_and_stats()

    assert result.get("status") != "egress_refused", (
        "With the flag set the gate should have let the call through"
    )
    assert tripwire, "With the flag set, the call should have reached the HTTP layer"
    assert "linkedin.com" in tripwire[0][1]
    assert client_module.egress_stats["performed"] >= 1


def test_every_outbound_call_site_is_behind_the_gate():
    """
    Coverage rather than spot checks. A fourth call site added later must also
    pass through egress_guard, and this test is how that gets noticed.
    """
    import re

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(repo_root, "studio", "backend", "linkedin_client.py")
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    unguarded = []
    for i, line in enumerate(lines):
        if re.search(r"\brequests\.(get|post|put|patch|delete)\(", line):
            window = "\n".join(lines[max(0, i - 16):i])
            if "egress_guard" not in window:
                unguarded.append(f"linkedin_client.py:{i + 1}: {line.strip()[:80]}")

    assert not unguarded, (
        "These outbound calls are not preceded by an egress_guard check:\n  "
        + "\n  ".join(unguarded)
    )


def test_the_extension_does_not_trigger_a_fetch_from_an_observation():
    """
    The listener observes that a request completed. Observing must not cause a
    new request, or the observer is a participant.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    path = os.path.join(repo_root, "studio", "extension", "background.js")
    with open(path, "r", encoding="utf-8") as f:
        source = f.read()

    import re

    listener_start = source.index("chrome.webRequest.onCompleted.addListener")
    listener_body = source[listener_start:source.index("chrome.runtime.onMessage", listener_start)]
    # Comments explain why the call was removed and must not count as the call.
    listener_body = re.sub(r"/\*.*?\*/", "", listener_body, flags=re.S)
    listener_body = re.sub(r"//[^\n]*", "", listener_body)

    assert "syncActiveSessionToStudio()" not in listener_body, (
        "The webRequest listener calls syncActiveSessionToStudio(), which makes "
        "the backend issue its own authenticated request to LinkedIn. Observing "
        "a page load must not cause a fetch."
    )
