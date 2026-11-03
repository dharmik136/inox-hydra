"""
Bring back an unused idea, in a browser (phase 6, item 2).
=========================================================

Drives the built interface against a studio in a throwaway home. The
Telegram panel's "Bring back an unused idea" is off, with its default named
beside it (Fridays at 16:00, older than 14 days); turned on, its days, hour
and age save, and the panel says when the next one comes. Checked with axe
in both themes, once the page has settled.

docs/quality/cycle4/bot-phase6.md, item 2.

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
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

PANEL = "section:has(input[aria-label='Telegram bot token'])"


def test_bring_back_shows_its_default_and_saves_its_days_hour_and_age(page, studio, fake):
    import telegram_bot
    _saved_in_the_panel(page, studio)
    # The switch's name is its label and what it means; the days' boxes say their day.
    switch = page.get_by_role("checkbox", name=re.compile(r"^Bring back an unused idea\s*On the days"))
    expect(switch).not_to_be_checked()
    expect(switch).to_be_enabled()
    hour = page.get_by_role("combobox", name="Bring back an unused idea at")
    older = page.get_by_role("combobox", name="Bring back an unused idea older than")
    expect(hour).to_have_value("16")
    expect(older).to_have_value("14")
    expect(hour).to_be_disabled()
    expect(page.get_by_text("NEXT ONE BROUGHT BACK", exact=False)).to_have_count(0)
    assert _axe(page, PANEL) == []

    switch.click()
    expect(page.get_by_text("An unused idea comes back Fridays at 16:00, for one older than 14 days.")).to_be_visible()
    expect(hour).to_be_enabled()
    expect(page.get_by_text("NEXT ONE BROUGHT BACK: ", exact=False)).to_be_visible()
    page.get_by_role("checkbox", name="Bring back an unused idea on Tuesday").click()
    expect(page.get_by_text("An unused idea comes back Tuesdays, Fridays at 16:00, for one older than 14 days.")).to_be_visible()
    hour.select_option("10")
    expect(page.get_by_text("An unused idea comes back Tuesdays, Fridays at 10:00, for one older than 14 days.")).to_be_visible()
    older.select_option("30")
    expect(page.get_by_text("An unused idea comes back Tuesdays, Fridays at 10:00, for one older than 30 days.")).to_be_visible()
    expect(page.get_by_text("(default: Fridays at 16:00, for one older than 14 days)")).to_be_visible()
    held = telegram_bot.bring_back()
    assert held["on"] is True and held["days"] == [1, 4] and held["hour"] == 10 and held["older"] == 30
    assert _axe(page, PANEL) == []
