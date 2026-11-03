"""
What connects, in a browser (phase 6, item 1).
==============================================

Drives the built interface against a studio in a throwaway home and the
fake provider on loopback (tests/ai_fake.py). Your collection says on each
new item what it connects to, with Open the group, which lists the item and
the ones offered with it and Combines them into one post; Brand, Writing
shows the two preferences with their defaults and saves them; the Telegram
panel's switch is on by default and saves. Checked with axe in both themes,
once the page has settled.

docs/quality/cycle4/bot-phase6.md, item 1.

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
from test_telegram_bot_panel_ui import _saved_in_the_panel, fake  # noqa: E402,F401

BOX = "section[aria-labelledby='collection-title']"
WRITING = "section[aria-labelledby='writing-title']"
PANEL = "section:has(input[aria-label='Telegram bot token'])"
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def provider(studio):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _seed(*texts):
    import collection
    from database import get_db
    ids = []
    for n, text in enumerate(texts):
        ids.append(collection.add("note", text, source="studio")["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-{10 + n:02d}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def test_your_collection_says_what_an_item_connects_to_and_combines_its_group(page, studio, provider):
    _seed("pricing page founders one", "pricing page two", "hiring loops", "pricing page founders newest")
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    box = page.locator(BOX)
    newest = box.locator("li", has_text="pricing page founders newest")
    expect(newest.get_by_text("Shares words with 2 other unused items: page, pricing, founders")).to_be_visible()
    expect(box.locator("li", has_text="hiring loops").get_by_role("button", name="Open the group",
                                                                  exact=False)).to_have_count(0)
    opener = newest.get_by_role("button", name="Open the group", exact=False)
    expect(opener).to_be_enabled()
    assert _axe(page, BOX) == []

    opener.click()
    group = box.get_by_role("group", name="The group around one item")
    expect(group.get_by_text("THE ITEM AND THE 2 OFFERED WITH IT, WHICH SHARE ITS WORDS")).to_be_visible()
    expect(box.locator("li", has_text="hiring loops")).to_have_count(0)
    expect(box.locator("li", has_text="pricing page two")).to_have_count(1)
    combine = group.get_by_role("button", name="Combine these 3 into one post")
    expect(combine).to_be_enabled()
    assert _axe(page, BOX) == []

    combine.click()
    expect(page.get_by_label("Post body")).to_have_value(DRAFT, timeout=10000)
    sent = provider.sent()
    assert "pricing page founders newest" in sent and "pricing page founders one" in sent
    assert "pricing page two" in sent and "hiring" not in sent


def test_brand_writing_sets_what_connects_and_how_many_are_offered(page, studio):
    import writing
    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    panel = page.locator(WRITING)
    shared = panel.get_by_label("Words two items share to be connected")
    offered = panel.get_by_label("Connected items offered with one")
    expect(shared).to_have_value("2")
    expect(offered).to_have_value("3")
    expect(panel.get_by_text("Default: 2 words")).to_be_visible()
    expect(panel.get_by_text("Default: 3 items")).to_be_visible()
    assert _axe(page, WRITING) == []
    shared.select_option("3")
    offered.select_option("5")
    panel.get_by_role("button", name="Save", exact=True).click()
    expect(panel.get_by_text("Saved. Every writing request reads these from now on.")).to_be_visible()
    assert writing.preferences()["connect_shared"] == 3 and writing.preferences()["connect_offer"] == 5
    assert _axe(page, WRITING) == []


def test_the_panel_says_what_something_new_connects_to_by_default_and_saves(page, studio, fake):
    import telegram_bot
    _saved_in_the_panel(page, studio)
    switch = page.get_by_role("checkbox", name="Say what something new connects to")
    expect(switch).to_be_checked()
    expect(switch).to_be_enabled()
    expect(page.get_by_text("Two items are connected when they share 2 words, and 3 items are offered with one "
                            "(the defaults), as set in Brand, under Writing.")).to_be_visible()
    assert _axe(page, PANEL) == []
    switch.click()
    expect(page.get_by_text("The bot no longer says what something new connects to.")).to_be_visible()
    expect(switch).not_to_be_checked()
    assert telegram_bot.connect_on() is False
    assert _axe(page, PANEL) == []
