"""
A provider key never leaves the vault in anything a person or a support
request can read: API responses, the egress ledger, log lines, exception text
or the diagnostics bundle. [WRITE-04, PLATFORM-14]

Gemini took its key in the URL (?key=...). The egress ledger stored the full
URL as last_destination, which the Local security tab fetches, and every
network failure printed the requests exception, which quotes that URL, to the
console the launcher writes to the log the diagnostics bundle tails.

Nothing here reaches the network. Name resolution is refused for every host
that is not loopback, so each provider call fails the way it does on an
offline machine, with the libraries' own exception text.
"""

import json
import os
import re
import socket
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

PLANTED = "AIzaSyNOTAREALKEY-qc-f2-0123456789abcdef"

_real_getaddrinfo = socket.getaddrinfo


def _offline_getaddrinfo(host, *args, **kwargs):
    if host in ("127.0.0.1", "localhost", "::1"):
        return _real_getaddrinfo(host, *args, **kwargs)
    raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _offline_getaddrinfo)
    for name in ("INOX_NO_EGRESS", "INOX_ALLOW_MODEL_EGRESS", "INOX_ALLOW_IMAGE_EGRESS"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
def gemini_configured():
    from app import app

    client = TestClient(app)
    res = client.post("/api/ai/settings", json={"gemini_api_key": PLANTED})
    assert res.status_code == 200, res.text
    yield client
    client.post("/api/ai/configure", json={"provider": "local_deterministic"})


def _assert_clean(label, blob):
    text = blob if isinstance(blob, str) else json.dumps(blob, default=str)
    assert PLANTED not in text, f"{label} carries the API key: {text[:400]}"
    assert PLANTED[-8:] not in text, f"{label} carries most of the API key: {text[:400]}"
    assert not re.search(r"[?&]key=[^&\s\"']+", text), f"{label} carries a key= query value: {text[:400]}"


def test_a_failing_gemini_key_appears_in_no_response_ledger_or_log(offline, gemini_configured, capfd, caplog, monkeypatch):
    import egress

    client = gemini_configured
    egress.reset_for_tests()

    seen = {}
    seen["config"] = client.get("/api/ai/config").json()
    seen["status"] = client.get("/api/ai/status").json()
    seen["re-hook"] = client.post("/api/format/re-hook", json={"text": "Pricing for small studios"}).text
    seen["command"] = client.post("/api/ai/command", json={"command": "Rewrite this as a question"}).text
    seen["configure"] = client.post(
        "/api/ai/configure", json={"provider": "gemini", "api_key": PLANTED}
    ).text

    # The old direct helper, which printed the requests exception verbatim.
    import repurposer

    seen["call_gemini_api"] = repr(repurposer.call_gemini_api("hello"))

    # Image generation with the provider block live, as on a real install.
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    started = client.post("/api/image/generate", json={"concept": "a quiet desk at dawn"}).json()
    deadline = time.time() + 30
    progress = {}
    while time.time() < deadline:
        progress = client.get(f"/api/image/progress/{started['task_id']}").json()
        if progress.get("status") in ("completed", "failed"):
            break
        time.sleep(0.2)
    seen["image"] = progress

    seen["egress"] = client.get("/api/v1/egress/status").json()

    out, err = capfd.readouterr()
    seen["stdout"] = out
    seen["stderr"] = err
    seen["log"] = "\n".join(record.getMessage() for record in caplog.records)

    # The calls were really attempted, so a clean ledger is not a quiet one.
    model = next(c for c in seen["egress"]["categories"] if c["name"] == "model")
    assert model["performed"] >= 1, seen["egress"]
    assert model["last_destination"].startswith("https://generativelanguage.googleapis.com/")

    for label, blob in seen.items():
        _assert_clean(label, blob)

    # The diagnostics bundle tails the logs folder, where the launchers send
    # the console. With that console in it, the bundle is still clean.
    import paths
    import support

    with open(os.path.join(paths.get_logs_dir(), "engine.log"), "w", encoding="utf-8") as fh:
        fh.write(out + err)
    _assert_clean("diagnostics bundle", support.collect_diagnostics())


def test_the_egress_ledger_records_where_not_what():
    """A destination is scheme, host and path. A query can hold a credential."""
    import egress

    egress.reset_for_tests()
    egress.guard("https://user:pw@example.invalid/v1/x?key=SECRET-VALUE&alt=sse#frag", category="model")
    described = json.dumps(egress.describe())
    assert "SECRET-VALUE" not in described
    assert "pw@" not in described
    assert "https://example.invalid/v1/x" in described
    egress.reset_for_tests()


def test_no_backend_url_carries_a_key_in_its_query():
    """The structural half: the key travels in a header, never in a URL."""
    offenders = []
    for base, _dirs, files in os.walk(BACKEND):
        if "__pycache__" in base:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if re.search(r"[?&]key=\{", line):
                        offenders.append(f"{os.path.relpath(path, REPO_ROOT)}:{number}")
    assert not offenders, "a key is built into a URL: " + ", ".join(offenders)


def test_the_saved_key_is_shown_as_its_last_four_at_most():
    from agno_agentos.model_gateway import AIProviderConfig

    shown = AIProviderConfig(provider="gemini", api_key=PLANTED).to_dict()["api_key_masked"]
    assert PLANTED[:4] not in shown
    assert shown.endswith(PLANTED[-4:])
    assert len(shown.replace(".", "")) <= 4
    assert AIProviderConfig(provider="openai", api_key="sk-short").to_dict()["api_key_masked"] == "set"


def test_the_redactor_removes_every_credential_shape():
    import egress

    samples = [
        f"Max retries exceeded with url: /v1beta/models/x:predict?key={PLANTED} (Caused by ...)",
        f"headers={{'x-goog-api-key': '{PLANTED}'}}",
        "Authorization: Bearer sk-proj-notarealkey-abcdefghijklmnop0123",
        "{'x-api-key': 'sk-ant-api03-notarealkey-abcdefghijklmnop'}",
        "gsk_abcdefghijklmnopqrstuvwx rejected",
    ]
    for sample in samples:
        cleaned = egress.redact(sample)
        assert PLANTED not in cleaned, cleaned
        assert "abcdefghijklmnop" not in cleaned, cleaned


def test_a_configured_key_of_any_shape_is_removed_by_value():
    """
    The patterns know the providers' formats. A custom endpoint's key can have
    any shape, so a key the gateway was given is also removed by value, raw
    and URL-encoded. [WRITE-04, review send-back]
    """
    from urllib.parse import quote, quote_plus

    import egress
    from agno_agentos.model_gateway import AIProviderConfig

    odd = "notarealkey.qcf2+Shape/9xQ=v7"
    AIProviderConfig(provider="custom_openai", api_key=odd)
    text = f"Received API Key = {odd}; encoded {quote(odd, safe='')}; form {quote_plus(odd)}"
    cleaned = egress.redact(text)
    for form in (odd, quote(odd, safe=""), quote_plus(odd)):
        assert form not in cleaned, cleaned
    assert "Shape" not in cleaned, cleaned
