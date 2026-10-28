"""
Decision D6, in a browser: the Telegram panel under Local security.
===================================================================

Drives the built interface against a studio in a throwaway home. Saving
starts the worker, which would ask Telegram for messages, so its start is
recorded instead of run: nothing here reaches the network.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

if not os.path.isfile(os.path.join(REPO_ROOT, "studio", "frontend_next", "index.html")):
    pytest.skip("studio/frontend_next is not built in this checkout", allow_module_level=True)

from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401

import ingress  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"


@pytest.fixture
def recorded(monkeypatch):
    started = []
    daemon = ingress.ingress_daemon
    monkeypatch.setattr(daemon, "start_worker", lambda: started.append(True) or setattr(daemon, "is_running", True))
    monkeypatch.setattr(daemon, "stop_worker", lambda: setattr(daemon, "is_running", False))
    monkeypatch.setattr(daemon, "is_running", False)
    monkeypatch.setattr(daemon, "bot_token", "")
    monkeypatch.setattr(daemon, "authorized_chat_id", "")
    monkeypatch.setattr(daemon, "configured_from", None)
    monkeypatch.setattr(daemon, "profile_id", None)
    monkeypatch.setattr(daemon, "refused_chats", {})
    return started


def test_the_panel_says_what_it_holds_and_never_shows_the_token(page, studio, recorded):
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    panel = page.get_by_text("Your phone, through Telegram", exact=True)
    expect(panel).to_be_visible()
    expect(page.get_by_text("NOT YET SEEN WORKING ON THIS COMPUTER", exact=False)).to_be_visible()
    expect(page.get_by_text("never a figure", exact=False)).to_be_visible()
    section = "section:has(input[aria-label='Telegram bot token'])"
    assert _axe(page, section) == []
    page.fill("input[aria-label='Telegram bot token']", TOKEN)
    page.fill("input[aria-label='Telegram chat id']", "555000111")
    page.get_by_role("button", name="Save and start").click()
    expect(page.get_by_text("SET, SEALED")).to_be_visible()
    assert recorded == [True]
    assert TOKEN not in page.content(), "the token is on the page after saving"
    expect(page.get_by_role("button", name="Remove the bot")).to_be_visible()


def test_this_is_me_pairs_the_chat_the_bot_refused(page, studio, recorded):
    """
    The owner's case of 2026-10-28: the chat id was not known. The token is
    saved alone, the phone's first message is refused and listed with the
    start of it, and This is me saves that chat. Telegram is not reached: the
    message is handed to the worker as a poll would hand it over.
    """
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    page.fill("input[aria-label='Telegram bot token']", TOKEN)
    page.get_by_role("button", name="Save and start").click()
    expect(page.get_by_text("NOT SET YET, PAIR BELOW")).to_be_visible()
    assert recorded == [True] and ingress.ingress_daemon.authorized_chat_id == ""
    for text in ("hello from my phone", "is this working?"):
        ingress.ingress_daemon.process_incoming_update({"update_id": 1, "message": {
            "chat": {"id": 487215963, "type": "private"}, "text": text}})
    ingress.ingress_daemon.process_incoming_update({"update_id": 2, "message": {
        "chat": {"id": 731004218, "type": "private"}, "text": "a stranger"}})
    line = "2 messages refused from chat 487215963, first: 'hello from my phone'. Is that you?"
    expect(page.get_by_text(line)).to_be_visible(timeout=10000)
    expect(page.get_by_text("1 message refused from chat 731004218, first: 'a stranger'. Is that you?")).to_be_visible()
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []
    page.locator("li", has_text="chat 487215963").get_by_role("button", name="This is me").click()
    expect(page.get_by_text("487215963", exact=True)).to_be_visible()
    expect(page.get_by_text(line)).to_have_count(0)
    assert ingress.ingress_daemon.authorized_chat_id == "487215963", "the press did not pair the chat"
    expect(page.get_by_text("1 message refused from chat 731004218", exact=False)).to_be_visible()
