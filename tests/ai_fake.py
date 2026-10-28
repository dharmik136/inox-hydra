"""
A fake AI provider on loopback, for the suite.
==============================================

An OpenAI-compatible chat completions endpoint on 127.0.0.1, shared as
tests/telegram_fake.py is (its pattern is the one tests/test_qc4_t7_model_stage.py
defined for itself). The studio is pointed at it the way a creator points it
at their own endpoint (model_gateway.save_ai_config with custom_openai and a
loopback base URL), so every request goes through the model gateway and its
egress check, counted under "model", as a real provider's would. Nothing
here reaches the network.

What a test sets:

  answer        what the next answers carry: a dict or a list, sent as its
                JSON, or a string, sent as it is; or a callable taking the
                request body and returning one
  delay         seconds to wait before answering, to show what waits on it
  fail          an HTTP status to answer with instead, such as 401

What it keeps: `requests`, every body it was sent, in order.

Strict Invariants:
- Zero em-dashes.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Union

FAKE_KEY = "sk-collection-fake-000000"


class FakeProvider:
    def __init__(self):
        self.requests: List[Dict[str, Any]] = []
        self.answer: Union[Dict[str, Any], Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.delay = 0.0
        self.fail: Optional[int] = None
        self._lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                with provider._lock:
                    provider.requests.append(body)
                if provider.delay:
                    time.sleep(provider.delay)
                if provider.fail:
                    out = json.dumps({"error": {"message": "refused by the fake"}}).encode()
                    self.send_response(provider.fail)
                else:
                    answer = provider.answer(body) if callable(provider.answer) else provider.answer
                    # A plain completion answers text; a structured one, its JSON.
                    content = answer if isinstance(answer, str) else json.dumps(answer)
                    out = json.dumps({"choices": [{"message": {"content": content}}],
                                      "usage": {"prompt_tokens": 100, "completion_tokens": 50}}).encode()
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    # -- what a test reads ---------------------------------------------------

    def sent(self, index: int = -1) -> str:
        """Everything one request carried, system and user, as one text."""
        with self._lock:
            body = self.requests[index]
        return "\n".join(str(m.get("content") or "") for m in body.get("messages") or [])

    def system(self, index: int = -1) -> str:
        with self._lock:
            body = self.requests[index]
        return "\n".join(str(m.get("content") or "") for m in body.get("messages") or [] if m.get("role") == "system")

    def wait_for(self, count: int, timeout: float = 8.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.requests) >= count:
                    return True
            time.sleep(0.02)
        return False

    # -- the studio's side ---------------------------------------------------

    def connect(self) -> None:
        """The studio's provider set to this endpoint, as the Prompt tab would save it."""
        from agno_agentos import model_gateway

        model_gateway.save_ai_config(provider="custom_openai", api_key=FAKE_KEY, model="fake-writer",
                                     base_url=f"http://127.0.0.1:{self.port}/v1")

    def close(self) -> None:
        from agno_agentos import model_gateway

        try:
            model_gateway.save_ai_config(provider="local_deterministic")
        except Exception:
            pass
        self.server.shutdown()
        self.server.server_close()
