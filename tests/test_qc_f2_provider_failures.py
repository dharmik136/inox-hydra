"""
A configured provider that fails or stalls says so, in words, within a
deadline, and cannot starve the rest of the studio. [WRITE-12, WRITE-13]

WRITE-12: a revoked key, an account out of credit or an outage made Re-Hook
and Command return the deterministic templates as a success, under a banner
that still said SENT TO THE PROVIDER. The creator could not tell their key had
stopped working.

WRITE-13: urlopen's timeout applies to each socket read, so a provider (or a
proxy) that sent one byte every few seconds never timed out. Each Re-Hook
press held one of the server's worker threads, and about forty presses froze
every screen, Save included.

Everything runs against a fake OpenAI-compatible endpoint on loopback and a
real uvicorn server in this process. No provider is contacted.
"""

import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import uvicorn  # noqa: E402

DEADLINE = 2.0
FAKE_KEY = "sk-qc-f2-fake-0000000000"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _FakeProvider:
    """An OpenAI-compatible endpoint whose behaviour the test switches."""

    def __init__(self):
        self.mode = "ok"
        self.requests = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(body)
                if fake.mode == "unauthorized":
                    out = json.dumps({"error": {"message": "Incorrect API key provided."}}).encode()
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(out)))
                    self.end_headers()
                    self.wfile.write(out)
                    return
                if fake.mode == "trickle":
                    # Every socket read succeeds, so a per-read timeout never fires.
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    try:
                        for _ in range(120):
                            self.wfile.write(b" ")
                            self.wfile.flush()
                            time.sleep(0.5)
                    except Exception:
                        pass
                    return
                prompt = body.get("messages", [{}])[-1].get("content", "")
                if "'hook'" in prompt:
                    content = json.dumps([{"archetype": f"A{i}", "hook": f"Model hook {i}."} for i in range(10)])
                else:
                    content = "OK from the fake model."
                out = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", _free_port()), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.mode = "ok"
        self.server.shutdown()
        self.server.server_close()


def _gateways():
    return [m for name, m in sys.modules.items() if name.endswith("agno_agentos.model_gateway") and m]


@pytest.fixture(scope="module")
def studio():
    """A real server, so worker threads are what they are in production."""
    from app import app
    from security import get_or_create_token

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", get_or_create_token()
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def provider(monkeypatch):
    fake = _FakeProvider()
    from agno_agentos import model_gateway

    for gateway in _gateways():
        monkeypatch.setattr(gateway, "PROVIDER_DEADLINE_SECONDS", DEADLINE, raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    model_gateway.save_ai_config(
        provider="custom_openai", api_key=FAKE_KEY, model="fake",
        base_url=f"http://127.0.0.1:{fake.port}/v1",
    )
    yield fake
    model_gateway.save_ai_config(provider="local_deterministic")
    fake.close()


def _call(base, token, method, path, body=None, timeout=30.0):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method=method)
    request.add_header("X-Inox-Token", token)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def test_a_refused_key_is_an_error_the_creator_can_read_not_a_template(studio, provider):
    base, token = studio
    provider.mode = "unauthorized"

    status, body = _call(base, token, "POST", "/api/format/re-hook", {"text": "Pricing for small studios"})
    assert status == 502, body
    assert "refused the key" in body["detail"], body
    assert "Incorrect API key provided" in body["detail"], body

    status, body = _call(base, token, "POST", "/api/ai/command", {"command": "Rewrite this as a question"})
    assert status == 502, body
    assert "refused the key" in body["detail"], body

    # Recorded where the Prompt tab reads, so a creator who opens it later
    # learns the key stopped working.
    status, ai = _call(base, token, "GET", "/api/ai/status")
    assert status == 200
    assert ai["last_error"] and "refused the key" in ai["last_error"], ai
    assert ai["last_error_at"], ai

    # A good answer clears it.
    provider.mode = "ok"
    status, body = _call(base, token, "POST", "/api/format/re-hook", {"text": "Pricing for small studios"})
    assert status == 200 and body["hooks"][0]["hook_text"].startswith("Model hook"), body
    assert _call(base, token, "GET", "/api/ai/status")[1]["last_error"] is None


def test_a_stalled_provider_answers_within_the_deadline(studio, provider):
    base, token = studio
    provider.mode = "trickle"

    started = time.monotonic()
    status, body = _call(base, token, "POST", "/api/format/re-hook", {"text": "Pricing for small studios"}, timeout=DEADLINE + 15)
    elapsed = time.monotonic() - started

    assert status == 504, body
    assert "seconds" in body["detail"], body
    assert elapsed < DEADLINE + 4, f"re-hook took {elapsed:.1f} s against a {DEADLINE} s deadline"


def test_repeated_presses_against_a_stalled_provider_leave_the_studio_responsive(studio, provider):
    base, token = studio
    provider.mode = "trickle"

    results = []

    def press():
        try:
            results.append(_call(base, token, "POST", "/api/format/re-hook", {"text": "Pricing"}, timeout=60)[0])
        except Exception as error:  # pragma: no cover - reported below
            results.append(repr(error))

    presses = [threading.Thread(target=press, daemon=True) for _ in range(45)]
    for thread in presses:
        thread.start()
    time.sleep(0.5)

    # The screens a creator would reach for while that is happening.
    for path in ("/api/posts?status=draft", "/api/ai/status"):
        started = time.monotonic()
        status, _ = _call(base, token, "GET", path, timeout=5)
        assert status == 200, path
        assert time.monotonic() - started < 3, f"{path} was starved by provider calls"

    for thread in presses:
        thread.join(timeout=DEADLINE + 20)
    assert len(results) == 45, results
    # Every press got an answer: the few that ran hit the deadline, the rest
    # were told the provider is still busy, at once.
    assert set(results) <= {503, 504}, results
    assert results.count(503) >= 30, results
