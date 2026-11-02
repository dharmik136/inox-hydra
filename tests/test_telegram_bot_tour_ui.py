"""
The Telegram panel's tour list, in a browser (phase 5, item 1).
================================================================

Drives the built interface against a studio in a throwaway home, with the
fake Bot API on loopback standing in for Telegram and the worker's polling
loop never started, as the earlier panel tests do. Once a chat is paired the
panel lists the tour's steps that leave something in the studio, each NOT YET
until the profile holds what the step leaves, then SEEN WORKING; with no AI
provider it says writing needs one. Checked with axe in both themes.

docs/quality/cycle4/bot-phase5.md, item 1.

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
from test_telegram_bot_panel_ui import _saved_in_the_panel, fake  # noqa: E402,F401

import telegram_bot  # noqa: E402

PANEL = "section:has(input[aria-label='Telegram bot token'])"


def _line(page, title):
    return page.locator("li", has=page.get_by_text(title, exact=True))


def test_the_panel_lists_the_tour_steps_seen_working_from_what_the_studio_holds(page, studio, fake):
    _saved_in_the_panel(page, studio)
    heading = page.get_by_text(f"WHAT YOU HAVE TRIED FROM YOUR PHONE: 0 OF {len(telegram_bot.TOUR_EVIDENCE)} SEEN WORKING")
    expect(heading).to_be_visible()
    expect(page.get_by_text("Writing from your phone needs an AI provider", exact=False)).to_be_visible()
    saved = telegram_bot.TOUR_EVIDENCE["saved"]
    expect(_line(page, saved).get_by_text("NOT YET")).to_be_visible()
    assert _axe(page, PANEL) == []

    # Something saved from the paired chat: the studio holds it, so the step is seen working.
    import collection
    collection.add("idea", "testing the bot", source="telegram")
    page.reload(wait_until="networkidle")
    page.get_by_role("tab", name="Local security").click()
    expect(_line(page, saved).get_by_text("SEEN WORKING")).to_be_visible()
    expect(page.get_by_text(f"WHAT YOU HAVE TRIED FROM YOUR PHONE: 1 OF {len(telegram_bot.TOUR_EVIDENCE)} SEEN WORKING")).to_be_visible()
    expect(_line(page, telegram_bot.TOUR_EVIDENCE["written"]).get_by_text("NOT YET")).to_be_visible()
    assert _axe(page, PANEL) == []
