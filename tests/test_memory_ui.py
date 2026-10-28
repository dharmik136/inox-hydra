"""
Things to remember, and the collection coming back, in a browser.
================================================================

Phase 3 of the Telegram bot, item 3. Against a studio in a throwaway home,
and the fake provider on loopback (tests/ai_fake.py) where something is
written:

- Brand, Writing, Things to remember: add, edit, tick, choose which go,
  remove; a /remember from the phone appears without a reload; axe in both
  themes.
- The Composer's From your collection: the new items a draft shares words
  with, Add to the draft (used, with that draft as what it became), Undo
  (new again), and a post not saved yet marking its item used when it is
  saved; axe in both themes.
- A draft written from the collection says what it was written from, and
  which things to remember went with it.
- What the studio knows: what ideas draw on, and how many ideas the daily
  model stage asks for.

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

from database import get_db  # noqa: E402
from test_collection_writing_ui import LEVEL, WRITING, _collection, provider  # noqa: E402,F401
from test_qc4_t6_analytics_export_ui import _axe, browser, page, studio  # noqa: E402,F401

REMEMBER = "section[aria-labelledby='remember-title']"
FROM_COLLECTION = "section[aria-labelledby='composer-from-collection']"
MADE_WITH = "section[aria-labelledby='composer-made-with']"
COURSE = "a six week pricing course for small studios"
SAVED = re.compile(r"\bSAVED\b")


def _status(item_id):
    conn = get_db()
    try:
        return tuple(conn.execute("SELECT status, post_id FROM collection_items WHERE id = ?", (item_id,)).fetchone())
    finally:
        conn.close()


def _facts():
    import remembered
    return remembered.listing()


def _brand_writing(page, studio):
    page.goto(studio["url"] + "/#/brand", wait_until="networkidle")
    page.get_by_role("tab", name="Writing").click()
    expect(page.locator(REMEMBER)).to_be_visible()
    return page.locator(REMEMBER)


def test_things_to_remember_are_added_changed_chosen_and_removed(page, studio):
    import remembered
    import writing

    box = _brand_writing(page, studio)
    expect(box.get_by_text("Nothing to remember yet.", exact=False)).to_be_visible()
    expect(box.get_by_label("Which go with writing")).to_have_value("all")
    expect(box.get_by_text("Default: All of them")).to_be_visible()
    assert _axe(page, REMEMBER) == []

    box.get_by_label("A thing to remember").fill(COURSE)
    box.get_by_label("What it is about").select_option("offer")
    box.get_by_role("button", name="Remember this").click()
    expect(box.get_by_text(COURSE, exact=True)).to_be_visible()
    assert [(f["text"], f["about"], f["source"]) for f in _facts()] == [(COURSE, "offer", "studio")]

    # From the phone, without a reload.
    remembered.add("my readers are founders of design studios", "audience", "telegram")
    expect(box.get_by_text("my readers are founders of design studios", exact=True)).to_be_visible(timeout=10000)
    expect(box.get_by_text("sent from your bot", exact=False)).to_be_visible()

    box.get_by_label("Which go with writing").select_option("chosen")
    expect(box.get_by_text("Only the ticked ones go with writing now.")).to_be_visible()
    assert writing.preferences()["memory"] == "chosen"
    box.get_by_label(f"Ticked to go with writing: {COURSE[:37]}...").click()
    expect(box.get_by_label(f"Ticked to go with writing: {COURSE[:37]}...")).not_to_be_checked()
    assert [f["in_use"] for f in _facts() if f["text"] == COURSE] == [False]

    box.get_by_role("button", name=f"Edit: {COURSE[:37]}...").click()
    box.get_by_label(f"Change: {COURSE[:37]}...").fill("a six week course on pricing")
    box.get_by_role("button", name="Save", exact=True).click()
    expect(box.get_by_text("a six week course on pricing", exact=True)).to_be_visible()
    assert _axe(page, REMEMBER) == []

    box.get_by_role("button", name="Remove: a six week course on pricing").click()
    box.get_by_role("button", name="Remove for good").click()
    expect(box.get_by_text("a six week course on pricing", exact=True)).to_have_count(0)
    assert [f["text"] for f in _facts()] == ["my readers are founders of design studios"]
    assert _axe(page, REMEMBER) == []


def test_the_composer_offers_what_the_draft_shares_words_with(page, studio):
    import collection

    first = collection.add("note", "founders should write their own pricing page")["id"]
    related = collection.add("idea", "a pricing page is a design brief for founders")["id"]
    collection.add("note", "hiring loops for a team of three")
    _collection(page, studio)
    page.locator(LEVEL).locator("li", has_text="founders should write their own pricing page").get_by_role(
        "button", name="Use as a draft").click()
    editor = page.get_by_label("Post body")
    expect(editor).to_have_value("founders should write their own pricing page", timeout=10000)
    draft_id = _status(first)[1]

    panel = page.locator(FROM_COLLECTION)
    expect(panel.get_by_text("1 SHARES ITS WORDS")).to_be_visible(timeout=10000)
    panel.get_by_role("button", name="Show From your collection").click()
    expect(panel.get_by_text("a pricing page is a design brief for founders")).to_be_visible()
    expect(panel.get_by_text("hiring loops for a team of three")).to_have_count(0)
    assert _axe(page, FROM_COLLECTION) == []

    panel.get_by_role("button", name="Add to the draft: a pricing page is a design brief for founders").click()
    expect(editor).to_have_value("founders should write their own pricing page\n\na pricing page is a design brief "
                                 "for founders")
    expect(panel.get_by_text("Added at the end of your draft, and marked used in your collection.")).to_be_visible()
    for _ in range(50):
        if _status(related) == ("used", draft_id):
            break
        page.wait_for_timeout(100)
    assert _status(related) == ("used", draft_id)
    assert _axe(page, FROM_COLLECTION) == []

    panel.get_by_role("button", name="Undo: take the item back out of the draft").click()
    expect(editor).to_have_value("founders should write their own pricing page")
    for _ in range(50):
        if _status(related) == ("new", None):
            break
        page.wait_for_timeout(100)
    assert _status(related) == ("new", None)


def test_a_post_not_saved_yet_marks_its_item_used_when_it_is_saved(page, studio):
    import collection

    item = collection.add("note", "pricing pages lie less when founders write them")["id"]
    page.goto(studio["url"] + "/#/composer", wait_until="networkidle")
    editor = page.get_by_label("Post body")
    editor.fill("Why founders should write the pricing page")
    panel = page.locator(FROM_COLLECTION)
    panel.get_by_role("button", name="Show From your collection").click()
    panel.get_by_role("button", name="Add to the draft: pricing pages lie less when founders write them").click()
    expect(panel.get_by_text("It is marked used in your collection when you save the draft.")).to_be_visible()
    assert _status(item) == ("new", None)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.locator("header [role=status]").first).to_contain_text(SAVED)
    for _ in range(50):
        if _status(item)[0] == "used":
            break
        page.wait_for_timeout(100)
    status, post_id = _status(item)
    assert status == "used" and post_id and post_id.startswith("post")


def test_a_draft_written_from_the_collection_says_what_went_with_it(page, studio, provider):
    import collection
    import remembered

    remembered.add(COURSE, "offer")
    collection.add("note", "pricing is a design decision")
    _collection(page, studio)
    page.locator(LEVEL).get_by_role("button", name="Make a post").click()
    expect(page.get_by_label("Post body")).to_have_value("Pricing is a design decision.\n\nWrite the price page "
                                                         "first.", timeout=10000)
    note = page.locator(MADE_WITH)
    expect(note).to_be_visible()
    expect(note.get_by_text(COURSE, exact=True)).to_be_visible()
    expect(note.get_by_text("from one item in your collection", exact=False)).to_be_visible()
    assert COURSE in provider.sent()
    assert _axe(page, MADE_WITH) == []


def test_what_the_studio_knows_sets_what_ideas_draw_on_and_how_many(page, studio, provider):
    import writing

    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="What the studio knows").click()
    sources = page.locator("section[aria-labelledby='ideas-draw-title']")
    expect(sources).to_be_visible(timeout=10000)
    expect(sources.get_by_role("checkbox", name=re.compile("^Your asks"))).to_be_checked()
    assert _axe(page, "section[aria-labelledby='ideas-draw-title']") == []
    sources.get_by_role("checkbox", name=re.compile("^Your asks")).click()
    expect(sources.get_by_role("checkbox", name=re.compile("^Your asks"))).not_to_be_checked()
    assert writing.preferences()["sources"] == ["collection", "posts"]

    ideas = page.get_by_label("Ideas asked for each day")
    expect(ideas).to_have_value("3")
    expect(page.get_by_text("Default: 3 ideas", exact=False)).to_be_visible()
    ideas.select_option("5")
    expect(page.get_by_text("Saved. The next call asks for that many.")).to_be_visible()
    assert writing.preferences()["ideas"] == 5
    assert _axe(page, "section[aria-labelledby='record-model-title']") == []
