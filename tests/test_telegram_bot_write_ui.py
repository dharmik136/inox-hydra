"""
Most items in one draft, in a browser (phase 4, item 9).
========================================================

Today's fixed limit of ten for Combine became a preference, read by Combine
in Your collection and by /write on the bot: Brand, Writing shows it with its
default and saves it, and the collection's summary of how it writes names it;
choosing items to combine stops at it. Axe in both themes.

docs/quality/cycle4/bot-phase4.md, item 9.

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

WRITING = "section[aria-labelledby='writing-title']"
LEVEL = "section[aria-labelledby='collection-title']"


def test_most_items_in_one_draft_shows_its_default_saves_and_bounds_combine(page, studio):
    import collection
    import writing

    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    panel = page.locator(WRITING)
    most = panel.get_by_label("Most items in one draft")
    expect(most).to_have_value("10")
    expect(panel.get_by_text("Default: 10 items")).to_be_visible()
    assert _axe(page, WRITING) == []
    most.select_option("2")
    panel.get_by_role("button", name="Save", exact=True).click()
    expect(panel.get_by_text("Saved. Every writing request reads these from now on.")).to_be_visible()
    assert writing.preferences()["combine_at_most"] == 2

    for words in ("first pricing note", "second pricing note", "third pricing note"):
        collection.add("note", words)
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    level = page.locator(LEVEL)
    level.get_by_text("How Make a post, Combine and Angles write", exact=False).click()
    expect(level.get_by_text("Most items in one draft:", exact=False)).to_be_visible()
    for words in ("first pricing note", "second pricing note"):
        level.get_by_label(f"Choose to combine: {words}").check()
    # A third would be more than the creator's most items: it is not taken.
    third = level.get_by_label("Choose to combine: third pricing note")
    third.click()
    expect(third).not_to_be_checked()
    expect(level.get_by_text("2 chosen", exact=False)).to_be_visible()
    expect(level.get_by_role("button", name="Combine 2 into one post")).to_be_visible()
    assert _axe(page, LEVEL) == []
