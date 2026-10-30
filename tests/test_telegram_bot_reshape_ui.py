"""
The rewrite buttons in a browser: where they are set, and what the Composer shows of a rewrite.
=============================================================================================

Phase 4, item 5 (docs/quality/cycle4/bot-phase4.md). Against a studio in a
throwaway home and the fake provider on loopback (tests/ai_fake.py):

- Brand, Writing: the rewrite buttons show their three defaults, each with
  what it asks for; one is changed, one removed, one added, and saved; axe in
  both themes.
- The Composer: a draft rewritten from the phone, open with no unsaved
  change, shows the new text without a reload; "What this draft was written
  from" lists the text the rewrite replaced, and Put it back in the editor
  puts it there; axe in both themes.

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

WRITING = "section[aria-labelledby='writing-title']"
LEVEL = "section[aria-labelledby='collection-title']"
MADE_WITH = "section[aria-labelledby='composer-made-with']"
FIRST = "Pricing is a design decision.\n\nWrite the price page first."
SHORTER = "Pricing is design.\n\nWrite the price first."


@pytest.fixture
def provider(studio):
    fake = FakeProvider()
    fake.connect()
    fake.answer = lambda body: {"draft": SHORTER if "REWRITE IT" in str(body) else FIRST}
    yield fake
    fake.close()


def test_brand_writing_sets_the_rewrite_buttons(page, studio):
    import writing

    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    panel = page.locator(WRITING)
    expect(panel.get_by_label("Rewrite button 1: its label")).to_have_value("Shorter")
    expect(panel.get_by_label("Rewrite button 3: what it asks for")).to_have_value(
        writing.DEFAULTS["reshapes"][2]["asks"])
    expect(panel.get_by_text("Default: Shorter (Make it about a third shorter.", exact=False)).to_be_visible()
    assert _axe(page, WRITING) == []

    panel.get_by_label("Rewrite button 1: what it asks for").fill("Make it about half as long.")
    panel.get_by_role("button", name="Remove the rewrite button Another angle").click()
    panel.get_by_role("button", name="Add a rewrite button").click()
    panel.get_by_label("Rewrite button 3: its label").fill("Plainer")
    panel.get_by_label("Rewrite button 3: what it asks for").fill("Say it in plainer words.")
    panel.get_by_role("button", name="Save", exact=True).click()
    expect(panel.get_by_text("Saved. Every writing request reads these from now on.")).to_be_visible()
    assert writing.preferences()["reshapes"] == [
        {"label": "Shorter", "asks": "Make it about half as long."},
        {"label": "New opening", "asks": writing.DEFAULTS["reshapes"][1]["asks"]},
        {"label": "Plainer", "asks": "Say it in plainer words."}]
    assert _axe(page, WRITING) == []


def test_the_composer_follows_a_rewrite_and_puts_the_earlier_text_back(page, studio, provider):
    import collection
    import writing

    collection.add("note", "pricing is a design decision")
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    page.locator(LEVEL).get_by_role("button", name="Make a post").click()
    editor = page.get_by_label("Post body")
    expect(editor).to_have_value(FIRST, timeout=10000)

    from database import get_db
    conn = get_db()
    post_id = conn.execute("SELECT post_id FROM collection_items WHERE post_id IS NOT NULL").fetchone()[0]
    conn.close()
    # Shorter, pressed on the phone: the open draft follows, since nothing in it is unsaved.
    assert writing.reshape(post_id, "Shorter")["status"] == "rewritten"
    expect(editor).to_have_value(SHORTER, timeout=10000)

    note = page.locator(MADE_WITH)
    expect(note.get_by_text("Rewritten from your phone", exact=False)).to_be_visible(timeout=10000)
    expect(note.get_by_text("before Shorter", exact=False)).to_be_visible()
    assert _axe(page, MADE_WITH) == []
    note.get_by_role("button", name="Put it back in the editor: Pricing is a design decision.").click()
    expect(editor).to_have_value(FIRST)
    expect(note.get_by_text("Put back in the editor. Save to keep it.")).to_be_visible()
    assert _axe(page, MADE_WITH) == []
