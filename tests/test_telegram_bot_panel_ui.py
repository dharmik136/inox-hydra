"""
The Telegram panel in a browser: the bot's switches and Send a test message.
===========================================================================

Drives the built interface against a studio in a throwaway home, with the
fake Bot API on loopback standing in for Telegram (tests/telegram_fake.py):
saving the bot sends Paired., the switches show their defaults (the
confirmations on, figures and both notifications off) and save, and Send a
test message reaches the fake and says so. The worker's polling loop is not
started here; every message the panel sends goes to the fake.

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
import telegram_bot  # noqa: E402
from telegram_fake import FakeTelegram  # noqa: E402

TOKEN = "123456789:AAFnotarealkeyZZZZZZZZZZZZZZZZZZZZZZZ"
OWNER = "487215963"


@pytest.fixture
def fake(monkeypatch):
    server = FakeTelegram(TOKEN).start()
    monkeypatch.setattr(telegram_bot, "API_BASE", server.url)
    daemon = ingress.ingress_daemon
    monkeypatch.setattr(daemon, "start_worker", lambda: setattr(daemon, "is_running", True))
    monkeypatch.setattr(daemon, "stop_worker", lambda: setattr(daemon, "is_running", False))
    for attribute, value in (("is_running", False), ("bot_token", ""), ("authorized_chat_id", ""),
                             ("configured_from", None), ("profile_id", None), ("refused_chats", {})):
        monkeypatch.setattr(daemon, attribute, value)
    daemon.outbox.clear()
    yield server
    server.stop()


def test_the_switches_show_their_defaults_save_and_the_test_message_arrives(page, studio, fake):
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    page.fill("input[aria-label='Telegram bot token']", TOKEN)
    page.fill("input[aria-label='Telegram chat id']", OWNER)
    page.get_by_role("button", name="Save and start").click()
    expect(page.get_by_text("SET, SEALED")).to_be_visible()
    assert fake.wait_for(lambda: [m["text"] for m in fake.sent] == [telegram_bot.SENTENCES["paired"]])

    confirms = page.get_by_role("checkbox", name="The bot confirms each message")
    figures = page.get_by_role("checkbox", name="The bot may answer with your figures")
    due = page.get_by_role("checkbox", name="Tell me when a queued post is due")
    day = page.get_by_role("checkbox", name="Send my latest post's figures at about 24 hours")
    expect(confirms).to_be_checked()
    for off in (figures, due, day):
        expect(off).not_to_be_checked()
    expect(page.get_by_text("Those figures then sit on Telegram's servers", exact=False)).to_be_visible()
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []

    figures.click()
    expect(page.get_by_text("The bot may answer /today with your figures.")).to_be_visible()
    expect(figures).to_be_checked()
    assert telegram_bot.figures_on()

    page.get_by_role("button", name="Send a test message").click()
    expect(page.get_by_text("Sent: Telegram took it for your chat. Check your phone.")).to_be_visible()
    assert [m["text"] for m in fake.sent][-1] == telegram_bot.SENTENCES["test"]
    assert TOKEN not in page.content()


def test_a_test_message_telegram_refuses_is_said_in_the_panel(page, studio, fake):
    fake.blocked_chats.add(OWNER)
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    page.fill("input[aria-label='Telegram bot token']", TOKEN)
    page.fill("input[aria-label='Telegram chat id']", OWNER)
    page.get_by_role("button", name="Save and start").click()
    expect(page.get_by_text("SET, SEALED")).to_be_visible()
    page.get_by_role("button", name="Send a test message").click()
    expect(page.get_by_text("the bot may be blocked in your chat", exact=False).first).to_be_visible()


def _saved_in_the_panel(page, studio):
    page.goto(studio["url"] + "/#/settings", wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    page.fill("input[aria-label='Telegram bot token']", TOKEN)
    page.fill("input[aria-label='Telegram chat id']", OWNER)
    page.get_by_role("button", name="Save and start").click()
    expect(page.get_by_text("SET, SEALED")).to_be_visible()


def test_quiet_hours_show_their_defaults_change_and_save(page, studio, fake):
    """Phase 2: Hold notifications during quiet hours, on by default from 23:00 to 07:00."""
    _saved_in_the_panel(page, studio)
    hold = page.get_by_role("checkbox", name="Hold notifications during quiet hours")
    start = page.get_by_role("combobox", name="Quiet hours start")
    end = page.get_by_role("combobox", name="Quiet hours end")
    expect(hold).to_be_checked()
    expect(start).to_have_value("23")
    expect(end).to_have_value("7")
    expect(page.get_by_text("Answers to your own messages and presses are never held", exact=False)).to_be_visible()
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []

    start.select_option("22")
    expect(page.get_by_text("Quiet hours: 22:00 to 07:00.")).to_be_visible()
    assert telegram_bot.quiet_hours() == {"on": True, "from": 22, "to": 7}
    end.select_option("22")
    expect(page.get_by_text("need a start and an end that differ", exact=False)).to_be_visible()
    assert telegram_bot.quiet_hours() == {"on": True, "from": 22, "to": 7}, "a refused change was saved"

    hold.click()
    expect(page.get_by_text("Notifications go at any hour.")).to_be_visible()
    expect(hold).not_to_be_checked()
    expect(start).to_be_disabled()
    assert telegram_bot.quiet_hours()["on"] is False
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []
