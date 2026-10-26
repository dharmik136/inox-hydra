"""
What the studio says goes to the provider is what goes. [WRITE-11]

Every Re-Hook and Command request appended the voice pack: headline, roles,
skills, up to 400 characters of the About section and the openers of the most
reacted posts. The Prompt tab said only that "prompt text" leaves, and the help
said Re-Hook sends the first line of the selection and Command the instruction
only.

The route taken is disclosure: the pack is useful context, so it stays, and
/api/ai/status lists it in the creator's terms for the Prompt tab, and each
Command answer lists what went with it. The fake provider on loopback records
what actually arrived, which is what the lists are checked against.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient  # noqa: E402

NOW = "2026-10-01T10:00:00+00:00"
HEADLINE = "Founder, two person design studio"
ABOUT = "I run a small design studio in Pune with my partner."
ROLE = "Founder"
EARLIER = "Design Lead"
SKILL = "Brand identity"
OPENER = "Our studio lost its biggest client in March."


class _Recorder:
    def __init__(self):
        self.prompts = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
                prompt = body["messages"][-1]["content"]
                recorder.prompts.append(prompt)
                if "'hook'" in prompt:
                    content = json.dumps([{"archetype": f"A{i}", "hook": f"Hook {i}."} for i in range(10)])
                else:
                    content = "A reply."
                out = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def studio(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc_f2_disclosure_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    from database import init_db
    import paths

    init_db()
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(
        "INSERT OR REPLACE INTO creator_identity (id, vanity, headline, about, confirmed_at) VALUES (1, 'ex', ?, ?, ?)",
        (HEADLINE, ABOUT, NOW),
    )
    conn.execute("INSERT INTO creator_positions (ordinal, title, company, observed_at) VALUES (0, ?, 'Example Studio', ?)", (ROLE, NOW))
    conn.execute("INSERT INTO creator_positions (ordinal, title, company, observed_at) VALUES (1, ?, 'PayCo', ?)", (EARLIER, NOW))
    conn.execute("INSERT INTO creator_skills (skill, observed_at) VALUES (?, ?)", (SKILL, NOW))
    # Dated and settled: the openers are the one ranking's (results.ranking,
    # cycle 4), which ranks a post only once it is old enough to judge.
    for n, (text, reactions) in enumerate([(OPENER + "\n\nMore.", 90), ("Pricing is design.\n\nYes.", 40), ("A note.", 5)]):
        conn.execute(
            "INSERT INTO own_posts (activity_urn, text, reactions, published_at, first_seen_at, last_seen_at) "
            "VALUES (?, ?, ?, '2026-08-01T09:00:00+00:00', ?, ?)",
            (f"urn:li:activity:73811100000000000{n:02d}", text, reactions, NOW, NOW),
        )
    conn.commit()
    conn.close()

    recorder = _Recorder()
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(
        provider="custom_openai", api_key="sk-qc-f2-fake-0000000000", model="fake",
        base_url=f"http://127.0.0.1:{recorder.port}/v1",
    )
    from app import app

    yield TestClient(app), recorder
    model_gateway.save_ai_config(provider="local_deterministic")
    recorder.server.shutdown()
    shutil.rmtree(home, ignore_errors=True)


# Each disclosed item, and the material of it that must then be in the prompt.
EVIDENCE = {
    "your headline": HEADLINE,
    "your current role": ROLE,
    "your earlier roles": EARLIER,
    "the skills on your profile": SKILL,
    "the first 400 characters of your About section": ABOUT,
    "the opening lines of your 3 most-reacted posts": OPENER,
}


def test_the_status_lists_exactly_what_rides_along_with_every_request(studio):
    client, recorder = studio
    listed = client.get("/api/ai/status").json()["voice_pack_sent"]

    assert client.post("/api/format/re-hook", json={"text": "Pricing for small studios"}).status_code == 200
    prompt = recorder.prompts[-1]

    for label, material in EVIDENCE.items():
        assert label in listed, f"{label!r} is sent but not listed: {listed}"
        assert material in prompt, f"{label!r} is listed but {material!r} was not sent"
    assert any(item.startswith("how your posts are usually shaped") for item in listed), listed
    assert "Measured across 3 of their posts" in prompt


def test_each_command_answer_says_what_went_with_it(studio):
    client, recorder = studio
    body = client.post("/api/ai/command", json={"command": "Rewrite this", "context": "My draft text."}).json()

    assert body["sent"][:2] == ["your instruction", "your Composer draft"], body
    for label in EVIDENCE:
        assert label in body["sent"], body["sent"]
    assert "My draft text." in recorder.prompts[-1]

    body = client.post("/api/ai/command", json={"command": "Rewrite this"}).json()
    assert "your Composer draft" not in body["sent"], body["sent"]


def test_nothing_known_means_nothing_listed(monkeypatch):
    home = tempfile.mkdtemp(prefix="inox_qc_f2_disclosure_empty_")
    monkeypatch.setenv("INOX_HYDRA_HOME", home)
    monkeypatch.delenv("INOX_DEMO_DATA", raising=False)
    from database import init_db
    from app import app

    init_db()
    try:
        assert TestClient(app).get("/api/ai/status").json()["voice_pack_sent"] == []
    finally:
        shutil.rmtree(home, ignore_errors=True)


def test_the_prompt_tab_and_the_help_stop_saying_less_than_is_sent():
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PromptPanel.tsx"), encoding="utf-8").read()
    assert "voice_pack_sent" in panel, "the Prompt tab does not show what goes with each request"

    help_text = open(os.path.join(REPO_ROOT, "docs", "help", "connect-your-own-ai-provider.md"), encoding="utf-8").read()
    assert "Your instruction only" not in help_text
    assert "About section" in help_text and "most-reacted posts" in help_text
