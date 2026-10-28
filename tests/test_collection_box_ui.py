"""
Your collection, in a browser: what the phone sent appears without a reload.
============================================================================

From your record's "Your collection" level (phase 3 of the Telegram bot)
against a studio in a throwaway home. An item is added the way the bot adds
one (collection.add, which publishes on the change stream), and the open
page shows it without a reload; the level passes axe in both themes; Not
now and Back to new move it between the status filters; Use as a draft
opens the Composer on the item's words. Nothing leaves loopback.

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

LEVEL = "section[aria-labelledby='collection-title']"


def _open(page, studio):
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    expect(page.locator(LEVEL)).to_be_visible()


def test_an_item_sent_from_the_phone_appears_without_a_reload(page, studio):
    import collection

    _open(page, studio)
    expect(page.get_by_text("Nothing yet. Send your bot a thought", exact=False)).to_be_visible()
    assert _axe(page, LEVEL) == []
    collection.add("note", "a thought sent from the phone about pricing #Pricing")
    collection.add("bookmark", "worth an answer", link="https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000777/",
                   activity_urn="urn:li:activity:7390000000000000777")
    level = page.locator(LEVEL)
    expect(level.get_by_text("a thought sent from the phone about pricing #Pricing")).to_be_visible(timeout=10000)
    expect(level.get_by_text("BOOKMARK", exact=True)).to_be_visible()
    expect(level.get_by_role("button", name="New (2)")).to_be_visible()
    assert _axe(page, LEVEL) == []


def test_not_now_back_to_new_and_use_as_a_draft(page, studio):
    import collection

    collection.add("idea", "hiring loops for a team of three")
    _open(page, studio)
    level = page.locator(LEVEL)
    # The item first: until the list is read, the status filter's own name is "Not now".
    expect(level.get_by_text("hiring loops for a team of three")).to_be_visible()
    level.get_by_role("button", name="Not now", exact=True).click()
    expect(level.get_by_text("Set aside: it is under Not now.")).to_be_visible()
    expect(level.get_by_role("button", name="Not now (1)")).to_be_visible()
    level.get_by_role("button", name="Not now (1)").click()
    level.get_by_role("button", name="Back to new", exact=True).click()
    level.get_by_role("button", name="New (1)").click()
    level.get_by_role("button", name="Use as a draft").click()
    expect(page.locator("textarea").first).to_have_value("hiring loops for a team of three", timeout=10000)
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    page.locator(LEVEL).get_by_role("button", name="Used (1)").click()
    expect(page.locator(LEVEL).get_by_text("A draft in the Composer", exact=False)).to_be_visible()
    assert _axe(page, LEVEL) == []
