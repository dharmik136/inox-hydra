"""
The AI surfaces as a creator sees them, driven in headless Chromium against
the built UI and an in-process studio. [F2 quality cycle]

The provider is a fake OpenAI-compatible endpoint on loopback. Service
workers are blocked in every context, so nothing the studio caches can stand
between the page and the server.
"""

import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = os.path.join(REPO_ROOT, "studio", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import uvicorn  # noqa: E402

FRONTEND = os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")
pytestmark = pytest.mark.skipif(not os.path.exists(FRONTEND), reason="the studio UI is not built")

DEADLINE = 2.0


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeProvider:
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
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", "100000")
                    self.end_headers()
                    try:
                        for _ in range(60):
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
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(scope="module")
def studio_url():
    home = tempfile.mkdtemp(prefix="inox_qc_f2_ui_")
    previous = os.environ.get("INOX_HYDRA_HOME")
    os.environ["INOX_HYDRA_HOME"] = home
    from app import app
    from database import init_db

    init_db()
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
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)
    if previous is not None:
        os.environ["INOX_HYDRA_HOME"] = previous
    else:
        os.environ.pop("INOX_HYDRA_HOME", None)
    shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        instance = p.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser, studio_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, service_workers="block")
    tab = context.new_page()
    tab.goto(studio_url, wait_until="networkidle")
    yield tab
    context.close()


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    from agno_agentos import model_gateway

    for name, module in list(sys.modules.items()):
        if name.endswith("agno_agentos.model_gateway") and module:
            monkeypatch.setattr(module, "PROVIDER_DEADLINE_SECONDS", DEADLINE, raising=False)
    monkeypatch.delenv("INOX_NO_EGRESS", raising=False)
    model_gateway.save_ai_config(
        provider="custom_openai", api_key="sk-qc-f2-fake-0000000000", model="fake",
        base_url=f"http://127.0.0.1:{fake.port}/v1",
    )
    yield fake
    model_gateway.save_ai_config(provider="local_deterministic")
    fake.mode = "ok"
    fake.close()


def _select_draft(page, text):
    page.click('button[aria-label="Composer"]')
    editor = page.locator('textarea[aria-label="Post body"]')
    editor.fill(text)
    editor.focus()
    page.keyboard.press("Control+A")
    page.wait_for_selector('button[aria-label="Re-hook this selection"]')


def test_re_hook_shows_it_is_working_ignores_repeat_presses_and_says_why_it_failed(page, provider):
    """[WRITE-12, WRITE-13]"""
    provider.mode = "trickle"
    _select_draft(page, "Pricing for small studios")

    page.click('button[aria-label="Re-hook this selection"]')
    page.wait_for_selector("text=WRITING HOOKS FROM YOUR SELECTION")
    page.click('button[aria-label="Re-hook this selection"]')
    page.click('button[aria-label="Re-hook this selection"]')

    failure = page.wait_for_selector("text=Re-Hook failed.", timeout=(DEADLINE + 8) * 1000)
    assert "did not finish answering within 2 seconds" in failure.inner_text()
    assert len(provider.requests) == 1, f"repeat presses sent {len(provider.requests)} requests"

    provider.mode = "unauthorized"
    page.click('button[aria-label="Re-hook this selection"]')
    page.wait_for_selector("text=refused the key")
    assert "Incorrect API key provided" in page.inner_text('div[role="status"]')


def test_without_a_model_re_hook_offers_labelled_fill_in_templates(page):
    """[WRITE-16]"""
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    _select_draft(page, "We moved our bakery orders to a simple form")
    page.click('button[aria-label="Re-hook this selection"]')

    page.wait_for_selector("text=THESE ARE FILL-IN TEMPLATES")
    rail = page.locator('section[aria-label="Hook archetypes"]')
    assert "Generated from selection".upper() in rail.inner_text().upper()
    cards = rail.locator("li button")
    assert cards.count() == 10
    for index in range(cards.count()):
        text = cards.nth(index).inner_text()
        assert "[" in text, f"a template card reads as finished: {text!r}"
        assert "%" not in text and "enterprise" not in text.lower(), text


def _run_command(page, text, include_draft):
    page.click('button[aria-label="Command"]')
    page.fill("#agent-command", text)
    box = page.locator('input[type="checkbox"][name="include-draft"]')
    if include_draft:
        box.check()
    page.click('button[aria-label="Run the command"]')
    page.wait_for_selector("section li pre")


def test_the_command_console_shows_the_answer_and_sends_the_draft_only_when_asked(page, provider):
    """[WRITE-25]"""
    page.click('button[aria-label="Composer"]')
    page.locator('textarea[aria-label="Post body"]').fill("Our bakery moved orders to a simple form.")

    _run_command(page, "Summarise my draft in one sentence", include_draft=True)
    entry = page.locator("section li").first
    assert entry.locator("pre").inner_text().strip() == "OK from the fake model."
    assert "{" not in entry.inner_text(), "the console printed the raw JSON"
    assert "Custom_openai (fake)" in entry.inner_text(), "the engine that answered is not named"
    assert "Our bakery moved orders to a simple form." in provider.requests[-1]["messages"][-1]["content"]

    page.locator('input[type="checkbox"][name="include-draft"]').uncheck()
    page.fill("#agent-command", "Write one line about pricing")
    page.click('button[aria-label="Run the command"]')
    page.wait_for_function("document.querySelectorAll('section li pre').length >= 2")
    assert "Our bakery" not in provider.requests[-1]["messages"][-1]["content"], "the draft was sent unasked"


def _open_prompt_tab(page):
    page.click('button[aria-label="Composer"]')
    opener = page.locator('button[aria-label="Open inspector"]')
    if opener.count() and opener.is_visible():
        opener.click()
    page.click('aside[aria-label="Inspector"] button:has-text("Prompt")')
    page.wait_for_selector("text=What a provider would receive")
    return page.locator('aside[aria-label="Inspector"]')


def test_the_prompt_tab_says_what_each_feature_sends(page):
    """[WRITE-11]"""
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    panel = _open_prompt_tab(page).inner_text()
    assert "the first line of your selection" in panel
    assert "your Composer draft when you tick the box to include it" in panel
    assert "Nothing from your profile or posts goes with them yet." in panel
    assert "PROMPT TEXT LEAVES" not in panel.upper()


def test_the_prompt_tab_lets_you_choose_the_model_and_sends_it(page):
    """[WRITE-14]"""
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    sent = []

    def capture(route):
        sent.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "status": "success", "message": "Connected.", "latency_ms": 1.0, "config": {},
        }))

    page.route("**/api/ai/configure", capture)
    panel = _open_prompt_tab(page)
    panel.locator('select[aria-label="Model provider"]').select_option("anthropic")
    model = panel.locator('input[aria-label="Model"]')
    assert model.input_value() == "claude-sonnet-5-5", "the default is not a current Claude model"
    suggestions = page.eval_on_selector_all(
        f"datalist#{model.get_attribute('list')} option", "nodes => nodes.map(n => n.value)"
    )
    assert set(suggestions) == {"claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"}, suggestions

    model.fill("claude-opus-5-5")
    panel.locator('input[aria-label="Provider API key"]').fill("sk-ant-notarealkey-000")
    panel.locator('button:has-text("Verify and save")').click()
    page.wait_for_function("() => document.body.innerText.includes('Connected.')")
    assert sent and sent[-1]["provider"] == "anthropic" and sent[-1]["model"] == "claude-opus-5-5", sent


def _open_audit_tab(page, text):
    page.click('button[aria-label="Composer"]')
    page.locator('textarea[aria-label="Post body"]').fill(text)
    opener = page.locator('button[aria-label="Open inspector"]')
    if opener.count() and opener.is_visible():
        opener.click()
    page.click('aside[aria-label="Inspector"] button:has-text("Audit")')
    return page.locator('aside[aria-label="Inspector"]')


def test_the_audit_scores_nothing_for_an_empty_draft(page):
    """[UX-23]"""
    panel = _open_audit_tab(page, "")
    page.wait_for_selector("text=NOTHING TO AUDIT YET")
    page.wait_for_timeout(1200)  # past the audit's settle delay, in case it ran
    text = panel.inner_text()
    assert "100" not in text, "an empty draft was given a perfect score"
    assert "NO DISTRIBUTION PENALTIES DETECTED" not in text
    assert "BLOCKED" not in text


def test_the_checks_read_as_advice_without_team_roles(page):
    """[UX-23]"""
    panel = _open_audit_tab(page, "Short.")
    page.wait_for_selector("text=OF 6 PASS")
    text = panel.inner_text()
    assert "BLOCKED" not in text and "WORTH A LOOK" in text, text
    for role in ("(CEO)", "(Eng Manager)", "(Designer)", "(QA)", "(CSO)", "Gate 2"):
        assert role not in text, f"{role!r} is still shown: {text}"
    assert "Content is too short" in text


def test_the_prompt_panel_never_shows_the_engine_codename():
    """[F7-N3] The Mode row read the internal 'Antigravity' engine name."""
    source = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "PromptPanel.tsx"), encoding="utf-8").read()
    assert "status.active_mode" not in source, "the panel renders the server's engine codename"
    rendered = "\n".join(line for line in source.splitlines() if not line.strip().startswith(("//", "*", "/*")))
    assert "Antigravity" not in rendered


def test_the_prompt_tab_says_plainly_that_no_model_is_set_up(page):
    """[F7-N3]"""
    from agno_agentos import model_gateway

    model_gateway.save_ai_config(provider="local_deterministic")
    panel = _open_prompt_tab(page).inner_text()
    assert "ANTIGRAVITY" not in panel.upper()
    assert "BUILT-IN TEMPLATES, NO MODEL" in panel.upper()
