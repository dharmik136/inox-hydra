"""
Plan it's preferences in the Telegram panel, in a browser (phase 5, item 2).
=============================================================================

Drives the built interface against a studio in a throwaway home, with the
fake Bot API on loopback and the worker's polling loop never started. Plan
it offers the Queue's next open slots by default, said beside it as the
default; choosing the creator's own times, changing one and saving them, and
"The bot lists at most", each save and say so. Checked with axe in both
themes, measured once the page has settled.

docs/quality/cycle4/bot-phase5.md, item 2.

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

import phone_plans  # noqa: E402

PANEL = "section:has(input[aria-label='Telegram bot token'])"


def test_plan_it_offers_shows_its_default_and_saves_the_creators_own_times(page, studio, fake):
    _saved_in_the_panel(page, studio)
    offers = page.locator("fieldset", has=page.get_by_text("Plan it offers", exact=True))
    expect(offers.get_by_text("(The default.)")).to_be_visible()
    slots = offers.get_by_role("radio", name="Your Queue's next open slots:")
    expect(slots).to_be_checked()
    expect(offers.get_by_role("combobox", name="How many of your Queue's open slots Plan it offers")).to_have_value("3")
    assert _axe(page, PANEL) == []

    offers.get_by_role("radio", name="Your own times").click()
    expect(page.get_by_text("Plan it offers tomorrow at 09:00 and tomorrow at 18:00.")).to_be_visible()
    assert phone_plans.plan_offers()["from"] == "times"
    first_day = offers.get_by_role("combobox", name="Your own time 1: which day")
    expect(first_day).to_be_enabled()
    first_day.select_option("2")
    offers.locator("input[aria-label='Your own time 1: at']").fill("07:30")
    save = offers.get_by_role("button", name="Save your times")
    expect(save).to_be_enabled()
    save.click()
    expect(page.get_by_text("Plan it offers in 2 days at 07:30 and tomorrow at 18:00.")).to_be_visible()
    assert phone_plans.plan_offers()["times"] == [{"days": 2, "at": "07:30"}, {"days": 1, "at": "18:00"}]
    expect(offers.get_by_text("(Default: your Queue's next 3 open slots; with none, tomorrow at 09:00 and tomorrow "
                              "at 18:00.)")).to_be_visible()
    expect(save).to_be_disabled()
    assert _axe(page, PANEL) == []


def test_the_bot_lists_at_most_shows_its_default_and_saves(page, studio, fake):
    _saved_in_the_panel(page, studio)
    most = page.get_by_role("combobox", name="The bot lists at most")
    expect(most).to_have_value("5")
    expect(page.get_by_text("in /plan and /recall (the default)")).to_be_visible()
    most.select_option("3")
    expect(page.get_by_text("The bot lists at most 3 in /plan and /recall.")).to_be_visible()
    expect(page.get_by_text("in /plan and /recall (default: 5)")).to_be_visible()
    assert phone_plans.list_at_most() == 3
    expect(most).to_be_enabled()
    assert _axe(page, PANEL) == []
