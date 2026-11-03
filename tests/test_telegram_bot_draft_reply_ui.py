"""
What a reply to a draft does, in a browser (phase 6, item 4).
=============================================================

Drives the built interface against a studio in a throwaway home. The
Telegram panel's "What a reply to a draft does" offers to rewrite the draft
by default, said beside it, and saves "Keep it as a note". The Composer's
note lists a text a reply's rewrite replaced as "before your reply", with Put
it back in the editor. Checked with axe in both themes, once the page has
settled.

docs/quality/cycle4/bot-phase6.md, item 4.

Strict Invariants:
- Zero em-dashes.
"""

import json
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

PANEL = "section:has(input[aria-label='Telegram bot token'])"
MADE_WITH = "section[aria-labelledby='composer-made-with']"


def test_what_a_reply_to_a_draft_does_shows_its_default_and_saves(page, studio, fake):
    import telegram_bot
    _saved_in_the_panel(page, studio)
    group = page.get_by_role("radiogroup", name="What a reply to a draft does")
    rewrite = group.get_by_role("radio", name="Offer to rewrite the draft with it", exact=False)
    note = group.get_by_role("radio", name="Keep it as a note", exact=False)
    expect(rewrite).to_be_checked()
    expect(note).to_be_enabled()
    expect(group.get_by_text("(The default.)")).to_be_visible()
    assert _axe(page, PANEL) == []
    note.click()
    expect(page.get_by_text("A reply to a draft is kept as a note.")).to_be_visible()
    expect(note).to_be_checked()
    expect(group.get_by_text("(Default: offer to rewrite the draft with it.)")).to_be_visible()
    assert telegram_bot.draft_reply() == "note"
    assert _axe(page, PANEL) == []


def test_the_composer_lists_what_a_reply_replaced(page, studio):
    import collection
    import writing
    from database import get_db
    made = {"items": [], "provider": "fake", "model": "fake-1", "via": "telegram", "remembered": [],
            "earlier": [{"text": "The words before the reply.", "at": "2026-11-03T09:00:00+00:00",
                         "by": writing.REPLY_LABEL}]}
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, made_with) VALUES ('post_replied', ?, 'draft', ?)",
                     ("The words after the reply.", json.dumps(made)))
    conn.close()
    collection.add("note", "the note it was written from", status="used", post_id="post_replied")
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    box = page.locator("section[aria-labelledby='collection-title']")
    box.get_by_role("button", name="Used", exact=False).click()
    open_it = box.locator("li", has_text="the note it was written from").get_by_role("button", name="Open it")
    expect(open_it).to_be_enabled()
    open_it.click()
    expect(page.get_by_label("Post body")).to_have_value("The words after the reply.", timeout=10000)
    note = page.locator(MADE_WITH)
    expect(note.get_by_text("before your reply", exact=False)).to_be_visible()
    put_back = note.get_by_role("button", name="Put it back in the editor", exact=False)
    expect(put_back).to_be_enabled()
    page.wait_for_load_state("networkidle")
    assert _axe(page, MADE_WITH) == []
