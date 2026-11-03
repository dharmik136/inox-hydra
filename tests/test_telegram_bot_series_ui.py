"""
A series from a group, in a browser (phase 6, item 5).
=====================================================

Drives the built interface against a studio in a throwaway home and the
fake provider on loopback. Your collection's group writes a series of the
creator's number of drafts and opens the first in the Composer, whose note
says which part it is; Brand, Writing shows "Drafts in a series" with its
default and saves it. Checked with axe in both themes, once the page has
settled.

docs/quality/cycle4/bot-phase6.md, item 5.

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

from ai_fake import FakeProvider  # noqa: E402
from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401
from test_telegram_bot_connected_ui import _seed  # noqa: E402

BOX = "section[aria-labelledby='collection-title']"
WRITING = "section[aria-labelledby='writing-title']"
MADE_WITH = "section[aria-labelledby='composer-made-with']"
PARTS = ["Pricing starts with the page.\n\nPart one.", "The page is a brief.\n\nPart two.",
         "Write the page first.\n\nPart three."]


@pytest.fixture
def provider(studio):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"posts": list(PARTS)}
    yield fake
    fake.close()


def test_the_group_writes_a_series_and_the_composer_says_which_part(page, studio, provider):
    _seed("pricing page founders one", "pricing page two", "pricing page founders newest")
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    box = page.locator(BOX)
    opener = box.locator("li", has_text="pricing page founders newest").get_by_role("button", name="Open the group",
                                                                                      exact=False)
    expect(opener).to_be_enabled()
    opener.click()
    group = box.get_by_role("group", name="The group around one item")
    series = group.get_by_role("button", name="Write a series of 3 from these")
    expect(series).to_be_enabled()
    assert _axe(page, BOX) == []
    series.click()
    expect(page.get_by_label("Post body")).to_have_value(PARTS[0], timeout=10000)
    note = page.locator(MADE_WITH)
    expect(note.get_by_text("part 1 of a series of 3", exact=False)).to_be_visible()
    page.wait_for_load_state("networkidle")
    assert _axe(page, MADE_WITH) == []
    assert "a series of 3 posts" in provider.sent()


def test_brand_writing_sets_how_many_drafts_a_series_is(page, studio):
    import writing
    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    panel = page.locator(WRITING)
    parts = panel.get_by_label("Drafts in a series")
    expect(parts).to_have_value("3")
    expect(panel.get_by_text("Default: 3 drafts")).to_be_visible()
    assert _axe(page, WRITING) == []
    parts.select_option("4")
    panel.get_by_role("button", name="Save", exact=True).click()
    expect(panel.get_by_text("Saved. Every writing request reads these from now on.")).to_be_visible()
    assert writing.preferences()["series_parts"] == 4
