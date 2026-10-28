"""
Making something from the collection, in a browser, and where its preferences are set.
=====================================================================================

Phase 3 of the Telegram bot, item 2. Against a studio in a throwaway home and
the fake provider on loopback (tests/ai_fake.py):

- Brand, Writing: each preference shows its default, saves, and goes back to
  the defaults; axe in both themes.
- Your collection: Make a post opens the Composer on what the provider wrote;
  the angles button says the creator's number and offers each angle to write
  up; Combine makes one draft from the items chosen; with no provider it says
  so plainly; the summary names the preferences it reads; axe in both themes.
- The Telegram panel: "The bot may send me what it writes from my
  collection" and the morning idea, off by default, with their days, hour
  and sources; axe in both themes.

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

LEVEL = "section[aria-labelledby='collection-title']"
WRITING = "section[aria-labelledby='writing-title']"


@pytest.fixture
def provider(studio):
    fake_provider = FakeProvider()
    fake_provider.connect()
    fake_provider.answer = lambda body: (
        {"angles": ["Your price page is a design brief.", "Stop letting finance name it.", "Price it like a product."]}
        if "opening lines" in str(body) else {"draft": "Pricing is a design decision.\n\nWrite the price page first."})
    yield fake_provider
    fake_provider.close()


def _collection(page, studio):
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    expect(page.locator(LEVEL)).to_be_visible()


def test_brand_writing_shows_each_default_saves_and_goes_back(page, studio):
    import writing

    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    panel = page.locator(WRITING)
    expect(panel.get_by_label("Tone")).to_have_value(writing.DEFAULTS["tone"])
    expect(panel.get_by_text("Default: about 150 words")).to_be_visible()
    expect(panel.get_by_text("Default: The language of what you wrote")).to_be_visible()
    assert _axe(page, WRITING) == []
    panel.get_by_label("Tone").fill("warm, plain and a little dry")
    panel.get_by_label("Angles").select_option("4")
    panel.get_by_role("button", name="Save", exact=True).click()
    expect(panel.get_by_text("Saved. Every writing request reads these from now on.")).to_be_visible()
    values = writing.preferences()
    assert (values["tone"], values["angles"]) == ("warm, plain and a little dry", 4)
    panel.get_by_role("button", name="Back to the defaults").click()
    expect(panel.get_by_text("Back to the defaults.", exact=True)).to_be_visible()
    assert writing.preferences() == writing.DEFAULTS
    assert _axe(page, WRITING) == []


def test_make_a_post_angles_and_combine_from_the_collection(page, studio, provider):
    import collection

    collection.add("note", "pricing is a design decision")
    collection.add("idea", "the cost of saying yes")
    _collection(page, studio)
    level = page.locator(LEVEL)
    expect(level.get_by_text("pricing is a design decision")).to_be_visible()
    expect(level.get_by_text("How Make a post, Combine and Angles write", exact=False)).to_be_visible()
    assert _axe(page, LEVEL) == []

    item = level.locator("li", has_text="pricing is a design decision")
    item.get_by_role("button", name="3 angles").click()
    expect(item.get_by_text("Stop letting finance name it.")).to_be_visible(timeout=10000)
    assert _axe(page, LEVEL) == []
    item.get_by_role("listitem").filter(has_text="Stop letting finance name it.").get_by_role(
        "button", name="Write it up").click()
    expect(page.locator("textarea").first).to_have_value("Pricing is a design decision.\n\nWrite the price page first.",
                                                       timeout=10000)
    assert "Stop letting finance name it." in provider.sent()

    collection.add("note", "a third note on pricing")
    _collection(page, studio)
    level = page.locator(LEVEL)
    for words in ("the cost of saying yes", "a third note on pricing"):
        level.get_by_label(f"Choose to combine: {words}").check()
    level.get_by_role("button", name="Combine 2 into one post").click()
    expect(page.locator("textarea").first).to_have_value("Pricing is a design decision.\n\nWrite the price page first.",
                                                       timeout=10000)
    assert "brings these notes together" in provider.sent()


def test_with_no_provider_the_collection_says_so_plainly(page, studio):
    import collection

    collection.add("note", "a thought with no provider")
    _collection(page, studio)
    level = page.locator(LEVEL)
    level.get_by_role("button", name="Make a post").click()
    expect(level.get_by_text("No AI provider is set up, so nothing was written.", exact=False)).to_be_visible()
    expect(level.get_by_role("button", name="Use as a draft")).to_be_visible()
    assert _axe(page, LEVEL) == []


def test_the_bots_switches_for_the_collection_show_their_defaults_and_save(page, studio, fake):
    import telegram_bot
    import writing

    _saved_in_the_panel(page, studio)
    words = page.get_by_role("checkbox", name="The bot may send me what it writes from my collection")
    morning = page.get_by_role("checkbox", name="Send me an idea from my collection each morning")
    expect(words).not_to_be_checked()
    expect(morning).not_to_be_checked()
    expect(page.get_by_role("combobox", name="Morning idea hour")).to_have_value("8")
    expect(page.get_by_role("combobox", name="Morning idea hour")).to_be_disabled()
    expect(page.get_by_text("the angles button says 3 angles (the default)", exact=False)).to_be_visible()
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []

    morning.click()
    expect(page.get_by_text("An idea each morning at 08:00.")).to_be_visible()
    expect(page.get_by_text("IT CARRIES YOUR WORDS, SO IT WAITS", exact=False)).to_be_visible()
    words.click()
    expect(page.get_by_text("The bot may send you what it writes from your collection.")).to_be_visible()
    page.get_by_role("checkbox", name="Sat").click()
    expect(page.get_by_text("The morning idea comes on 6 days a week.")).to_be_visible()
    page.get_by_role("checkbox", name="your posts, for the angle").click()
    expect(page.get_by_text("Angles leave your posts alone.")).to_be_visible()
    early = telegram_bot.morning()
    assert early["on"] is True and 5 in early["days"] and telegram_bot.collection_words_on()
    assert writing.preferences()["sources"] == ["collection", "asks"]
    assert _axe(page, "section:has(input[aria-label='Telegram bot token'])") == []
