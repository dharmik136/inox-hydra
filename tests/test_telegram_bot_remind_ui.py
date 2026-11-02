"""
Remind me in the studio, in a browser (phase 5, item 4).
========================================================

Drives the built interface against a studio in a throwaway home. Your
collection lists the reminders asked for on an item, each with Cancel, which
removes it; the Telegram panel's "Remind me offers" shows its default and
saves the creator's own moments. Checked with axe in both themes, once the
page has settled.

docs/quality/cycle4/bot-phase5.md, item 4.

Strict Invariants:
- Zero em-dashes.
"""

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

import phone_reminders  # noqa: E402
from database import get_db  # noqa: E402

PANEL = "section:has(input[aria-label='Telegram bot token'])"
BOX = "section[aria-labelledby='collection-title']"


def test_your_collection_lists_a_reminder_on_its_item_with_cancel(page, studio):
    import collection
    item = collection.add("idea", "pricing is a design decision")
    when = datetime.now(timezone.utc) + timedelta(days=1)
    assert phone_reminders.add(item["id"], when.isoformat(), "Tomorrow morning")["status"] == "kept"
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    box = page.locator(BOX)
    reminders = box.get_by_role("list", name="Reminders asked for on your phone")
    expect(reminders.get_by_text("(Tomorrow morning), on your phone", exact=False)).to_be_visible()
    cancel = reminders.get_by_role("button", name="Cancel the reminder", exact=False)
    expect(cancel).to_be_enabled()
    assert _axe(page, BOX) == []
    cancel.click()
    expect(box.get_by_text("Reminder cancelled: the bot will not bring it back then.")).to_be_visible()
    expect(box.get_by_role("list", name="Reminders asked for on your phone")).to_have_count(0)
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM item_reminders").fetchone()[0] == 0
    conn.close()
    assert _axe(page, BOX) == []


def test_remind_me_offers_shows_its_default_and_saves_the_creators_moments(page, studio, fake):
    _saved_in_the_panel(page, studio)
    moments = page.locator("fieldset", has=page.get_by_text("Remind me offers", exact=True))
    expect(moments.get_by_text("(The default.)")).to_be_visible()
    first = moments.locator("input[aria-label='Moment 1: its label']")
    expect(first).to_have_value("This evening")
    assert _axe(page, PANEL) == []
    first.fill("After work")
    moments.locator("input[aria-label='Moment 1: at']").fill("19:30")
    save = moments.get_by_role("button", name="Save your moments")
    expect(save).to_be_enabled()
    save.click()
    expect(page.get_by_text("Remind me offers After work (today at 19:30), Tomorrow morning (tomorrow at 09:00), "
                            "Next week (in 7 days at 09:00).")).to_be_visible()
    assert phone_reminders.moments()[0] == {"label": "After work", "days": 0, "at": "19:30"}
    expect(moments.get_by_text("(Default: This evening (today at 18:00)", exact=False)).to_be_visible()
    expect(save).to_be_disabled()
    assert _axe(page, PANEL) == []
