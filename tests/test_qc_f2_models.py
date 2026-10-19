"""
The providers' default models are ones the provider still serves, and a
refused model is named. [WRITE-14]

Anthropic's default was claude-3-5-sonnet-20241022, retired on 2025-10-28, and
the other two ids listed were retired too, so Verify and save failed with a
bare 400 for every Claude key and the Prompt tab had no way to pick another.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agno_agentos import model_gateway  # noqa: E402

# The Claude models Anthropic currently serves. Kept here, by hand, so a
# retirement is a one-line change that this test then enforces everywhere.
CURRENT_CLAUDE = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"}


def test_anthropic_offers_only_current_models():
    anthropic = model_gateway.SUPPORTED_PROVIDERS["anthropic"]
    assert anthropic["default_model"] == "claude-sonnet-5-5"
    assert set(anthropic["supported_models"]) == CURRENT_CLAUDE


def test_every_default_is_one_of_its_own_listed_models():
    for name, meta in model_gateway.SUPPORTED_PROVIDERS.items():
        if meta["supported_models"] == ["*"]:
            continue
        assert meta["default_model"] in meta["supported_models"], name


def test_an_anthropic_key_from_the_environment_uses_the_current_default(monkeypatch):
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-notarealkey-000000")
    model_gateway.save_ai_config(provider="local_deterministic")
    config = model_gateway.get_current_ai_config()
    assert config.provider == "anthropic" and config.model == "claude-sonnet-5-5"


def test_no_retired_claude_id_is_offered_by_the_studio_or_its_help():
    for rel in (
        "studio/backend/agno_agentos/model_gateway.py",
        "studio/ui/src/components/PromptPanel.tsx",
        "docs/help/connect-your-own-ai-provider.md",
    ):
        with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as fh:
            assert "claude-3" not in fh.read(), f"{rel} still names a retired Claude model"


def test_a_refused_model_is_named(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            out = json.dumps({"type": "error", "error": {"type": "not_found_error", "message": "model: nope-1"}}).encode()
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    try:
        ok, message, _ = model_gateway.verify_ai_connection(
            "custom_openai", api_key="notarealkey", model="nope-1",
            base_url=f"http://127.0.0.1:{server.server_address[1]}/v1",
        )
    finally:
        server.shutdown()
    assert ok is False
    assert "did not find the model 'nope-1'" in message, message
