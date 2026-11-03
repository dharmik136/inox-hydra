"""
The Composer opens a draft planned from the phone, in a browser.
===============================================================

Found while writing the phase 6 PRD (docs/quality/cycle4/bot-phase6.md):
"What this draft was written from" read `made.items.length` for any post
whose record of how it was made is set. A draft saved and planned with
`Schedule tomorrow 09:00:` from the phone (phase 5, item 6) has a record
holding only its plan, and one unplanned with Undo an empty one; the
Queue's Edit text, and Your collection's Open it, opened them in the
Composer, where that read threw and took the page with it. Now the note
says only what the record holds: nothing, for a plan alone.

Against a studio in a throwaway home. Checked with axe in both themes, once
the page has settled.

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

WORDS = "A post planned by its first word"
MADE_WITH = "section[aria-labelledby='composer-made-with']"


def _scheduled_from_the_phone():
    """`Schedule tomorrow 09:00: <words>` as the bot saves it: a draft, planned for then. Its post's id."""
    import ingress
    record = ingress.ingress_daemon._store(f"Schedule tomorrow 09:00: {WORDS}", origin=None, from_telegram=True)
    assert record["planned"]["status"] == "planned", record["planned"]
    from database import get_db
    conn = get_db()
    try:
        held = conn.execute("SELECT made_with FROM posts WHERE id = ?", (f"post-draft-{record['id']}",)).fetchone()
    finally:
        conn.close()
    assert set(json.loads(held[0])) == {"planned"}, held[0]
    return f"post-draft-{record['id']}", record["planned"]["for"]


def _watched(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return errors


def test_a_draft_planned_with_schedule_opens_from_the_queue(page, studio):
    _scheduled_from_the_phone()
    errors = _watched(page)
    page.goto(studio["url"] + "/#/queue", wait_until="networkidle")
    row = page.locator("li", has_text=WORDS)
    edit = row.get_by_role("button", name="Edit text")
    expect(edit).to_be_enabled()
    edit.click()
    expect(page.get_by_label("Post body")).to_have_value(WORDS, timeout=10000)
    page.wait_for_load_state("networkidle")
    assert errors == [], errors
    # A plan alone says nothing about how the draft was written.
    expect(page.locator(MADE_WITH)).to_have_count(0)
    assert _axe(page, "main") == []


def test_a_draft_unplanned_with_undo_opens_from_your_collection(page, studio):
    import phone_plans
    post_id, planned_for = _scheduled_from_the_phone()
    assert phone_plans.unplan(post_id, planned_for) == "unplanned"
    errors = _watched(page)
    page.goto(studio["url"] + "/#/record", wait_until="networkidle")
    page.get_by_role("button", name="Your collection").click()
    box = page.locator("section[aria-labelledby='collection-title']")
    box.get_by_role("button", name="Used", exact=False).click()
    open_it = box.locator("li", has_text=WORDS).get_by_role("button", name="Open it")
    expect(open_it).to_be_enabled()
    open_it.click()
    expect(page.get_by_label("Post body")).to_have_value(WORDS, timeout=10000)
    page.wait_for_load_state("networkidle")
    assert errors == [], errors
    expect(page.locator(MADE_WITH)).to_have_count(0)
    assert _axe(page, "main") == []
