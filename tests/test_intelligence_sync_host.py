"""
Intelligence sync fetches from a known host, not from wherever it is told.
==========================================================================

The scheme was pinned to https and the host was not. The cdn_url request
parameter therefore reached any https service the machine can see, including
internal ones and https://127.0.0.1:<port>, and the status code and parse
outcome came back to the caller. Fetched hook_text also lands in the database,
where /api/v1/intelligence/templates reads it back, so it was a probe and a way
to put chosen text in front of the creator.

updates.py and the AI gateway both got host rules. This one did not, which is
the only reason it survived.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))

import intelligence_sync
from intelligence_sync import ALLOWED_CDN_HOSTS, is_allowed_cdn_host, intelligence_sync_engine


@pytest.mark.parametrize("hostname", [
    "127.0.0.1",
    "localhost",
    "169.254.169.254",          # cloud metadata
    "internal.corp",
    "attacker.example",
])
def test_a_host_we_never_published_to_is_refused(hostname):
    assert is_allowed_cdn_host(hostname) is False


@pytest.mark.parametrize("hostname", ALLOWED_CDN_HOSTS)
def test_the_published_hosts_are_accepted(hostname):
    assert is_allowed_cdn_host(hostname) is True


def test_matching_is_exact_not_by_suffix():
    """
    "evil-githubusercontent.com" ends with the same characters as the real
    host, so a naive endswith check would accept it.
    """
    assert is_allowed_cdn_host("evil-githubusercontent.com") is False
    assert is_allowed_cdn_host("raw.githubusercontent.com.attacker.test") is False
    assert is_allowed_cdn_host("notgithub.com") is False


def test_matching_is_case_insensitive():
    assert is_allowed_cdn_host("RAW.GithubUserContent.COM") is True


def test_empty_and_missing_hosts_are_refused():
    assert is_allowed_cdn_host("") is False
    assert is_allowed_cdn_host(None) is False


def test_sync_refuses_a_disallowed_host_without_making_a_request(monkeypatch):
    """
    Refused before any socket is opened, so the endpoint cannot be used to
    probe whether an internal service exists.

    The watch used to be on intelligence_sync.urllib.request.urlopen. This
    module fetches with requests.get and imports only urllib.parse; urllib
    carried a .request attribute because some other module had imported it, so
    the patch attached successfully to a function nothing here calls.

    The effect was subtler than a dead test. The host rule itself was still
    covered, by the assertion on the message, so disabling the check did fail
    this test. What went unverified was the half that matters for SSRF: that no
    connection is attempted. And when the test did fail, it failed by really
    opening a socket to 127.0.0.1:9999, which is the behaviour it exists to
    forbid.

    Watching requests.get makes the no-socket claim real and stops a failing
    run from probing the machine it runs on.
    """
    calls = []

    def explode(*args, **kwargs):
        calls.append(args)
        raise AssertionError(
            "a request was made to a disallowed host: " + repr(args[:1])
        )

    monkeypatch.setattr(intelligence_sync.requests, "get", explode)

    result = intelligence_sync_engine.sync(cdn_url="https://127.0.0.1:9999/probe.json")

    assert result["status"] == "error"
    assert "host" in result["message"].lower()
    assert not calls, "the request was attempted before the host was checked"


def test_the_scheme_rule_still_applies(monkeypatch):
    """http, file and ftp were already refused and must stay refused."""
    # requests.get, for the same reason as the test above: urlopen is not the
    # door this module opens.
    monkeypatch.setattr(
        intelligence_sync.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be reached")),
    )
    for url in ("http://raw.githubusercontent.com/x.json",
                "file:///etc/passwd",
                "ftp://mirror.example.com/x.json"):
        result = intelligence_sync_engine.sync(cdn_url=url)
        assert result["status"] == "error", url


def test_a_self_hosted_mirror_stays_usable(monkeypatch):
    """
    INTELLIGENCE_CDN_URL is set by whoever owns the machine, which is a
    different level of trust from a request parameter. Blocking it would break
    a legitimate setup to close a hole that is not in that path.
    """
    monkeypatch.setattr(
        intelligence_sync, "DEFAULT_CDN_URL",
        "https://mirror.internal.example/hooks.json",
    )
    assert is_allowed_cdn_host("mirror.internal.example") is True
    assert is_allowed_cdn_host("attacker.example") is False
