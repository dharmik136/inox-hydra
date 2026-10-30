"""
The Telegram panel's phase 4 controls, in a browser.
====================================================

Drives the built interface against a studio in a throwaway home, with the
fake Bot API on loopback standing in for Telegram (tests/telegram_fake.py),
the worker's polling loop never started, as the phase 2 panel tests do. Each
new control is checked with axe in both themes.

  item 2   the last check of Telegram, and the notice of a day the studio
           did not check, with Got it

docs/quality/cycle4/bot-phase4.md.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

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
from test_telegram_bot_panel_ui import _saved_in_the_panel, fake  # noqa: E402,F401

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402

PANEL = "section:has(input[aria-label='Telegram bot token'])"


def _write(key, value):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.close()


def test_the_notice_of_a_day_not_checked_shows_and_got_it_clears_it(page, studio, fake):
    """Item 2: the panel says it at once, in the server's own words, until Got it."""
    _saved_in_the_panel(page, studio)
    expect(page.get_by_text("Last checked Telegram")).to_be_visible()
    now = datetime.now(timezone.utc)
    _write(telegram_bot.GAP_KEY, json.dumps({
        "from": (now - timedelta(hours=40)).isoformat(), "to": now.isoformat(),
        "since": (now - timedelta(hours=24)).isoformat(), "bot": "told", "panel": "shown"}))
    page.reload(wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    said = telegram_bot.gap_shown()["said"]
    expect(page.get_by_text("A DAY THE STUDIO DID NOT CHECK TELEGRAM")).to_be_visible()
    expect(page.get_by_text(said)).to_be_visible()
    assert _axe(page, PANEL) == []

    page.get_by_role("button", name="Got it").click()
    expect(page.get_by_text("A DAY THE STUDIO DID NOT CHECK TELEGRAM")).to_have_count(0)
    assert telegram_bot.gap_shown() is None
    assert _axe(page, PANEL) == []
