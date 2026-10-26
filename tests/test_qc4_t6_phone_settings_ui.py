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
    monkeypatch.setattr(ingress.ingress_daemon, "start_worker", lambda: started.append(True))
    monkeypatch.setattr(ingress.ingress_daemon, "stop_worker", lambda: None)
    monkeypatch.setattr(ingress.ingress_daemon, "bot_token", "")
    monkeypatch.setattr(ingress.ingress_daemon, "authorized_chat_id", "")
    monkeypatch.setattr(ingress.ingress_daemon, "configured_from", None)
    monkeypatch.setattr(ingress.ingress_daemon, "profile_id", None)
    return started


def test_the_panel_says_what_it_holds_and_never_shows_the_token(page, studio, recorded):
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    panel = page.get_by_text("Your phone, through Telegram", exact=True)
    expect(panel).to_be_visible()
    expect(page.get_by_text("NOT YET BEEN TESTED AGAINST THE REAL TELEGRAM SERVICE", exact=False)).to_be_visible()
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
