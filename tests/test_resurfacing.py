"""
What was collected comes back: in the Composer, the daily cards, the week and /recall.
=====================================================================================

Phase 3 of the Telegram bot, item 3. The Composer shows "From your
collection": the unused items whose words the draft shares, matched
locally; Add to the draft marks the item used. From your record's daily
cards may draw an unused collected idea in slot 3, cited by its row like an
ask, so a removed item drops its card, and only while ideas may draw on the
collection. The weekly summary counts the ideas still unused. /recall
answers how many items match a word, and their first lines only with the
switch that lets the bot send them.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_writing import studio  # noqa: E402,F401
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_notifications import notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402
from test_telegram_bot_weekly import _summaries, _weekly, clock  # noqa: E402,F401

SAID = telegram_bot.SENTENCES


def _item(text, status="new"):
    import collection
    item = collection.add("note", text)
    if status != "new":
        collection.set_status(item["id"], status)
    return item["id"]


def _status(item_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT status, post_id FROM collection_items WHERE id = ?", (item_id,)).fetchone()
        return tuple(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# The Composer
# ---------------------------------------------------------------------------

def test_the_composer_finds_the_unused_items_its_draft_shares_words_with(studio):
    pricing = _item("pricing pages lie less when founders write them")
    _item("pricing for agencies is a different game")
    _item("hiring loops for a team of three")
    _item("pricing again but set aside", status="not_now")
    found = studio.post("/api/v1/collection/related", json={"text": "Why founders should write the pricing page"}).json()
    texts = [i["text"] for i in found["items"]]
    assert texts[0] == "pricing pages lie less when founders write them"
    assert "hiring loops for a team of three" not in texts and "pricing again but set aside" not in texts
    assert len(texts) <= 3
    assert studio.post(f"/api/v1/collection/{pricing}/used", json={"post_id": "post_composer1"}).status_code == 200
    assert _status(pricing) == ("used", "post_composer1")
    again = studio.post("/api/v1/collection/related", json={"text": "Why founders should write the pricing page"}).json()
    assert "pricing pages lie less when founders write them" not in [i["text"] for i in again["items"]]


def test_undo_in_the_composer_brings_the_item_back_as_new(studio):
    """Add to the draft, then Undo: the words came out of the draft, so the item became nothing."""
    pricing = _item("pricing pages lie less when founders write them")
    studio.post(f"/api/v1/collection/{pricing}/used", json={"post_id": "post_composer2"})
    assert _status(pricing) == ("used", "post_composer2")
    back = studio.post(f"/api/v1/collection/{pricing}/status", json={"status": "new"})
    assert back.status_code == 200, back.text
    assert _status(pricing) == ("new", None)
    assert back.json()["item"]["became"] is None
    found = studio.post("/api/v1/collection/related", json={"text": "founders write the pricing page"}).json()
    assert "pricing pages lie less when founders write them" in [i["text"] for i in found["items"]]


def test_an_empty_draft_finds_nothing(studio):
    _item("pricing pages lie less")
    assert studio.post("/api/v1/collection/related", json={"text": "   "}).json()["items"] == []


# ---------------------------------------------------------------------------
# The daily cards
# ---------------------------------------------------------------------------

def _slot_three(studio):
    import record_daily
    record_daily.run_today()
    cards = studio.get("/api/v1/record").json()["cards"]
    return next(c for c in cards if c["slot"] == 3)


def test_slot_three_may_draw_an_unused_collected_idea_cited_by_its_row(studio):
    item = _item("pricing pages lie less when founders write them")
    card = _slot_three(studio)
    assert card["kind"] == "collected" and card["status"] == "shown", card
    assert card["payload"]["draft_text"] == "pricing pages lie less when founders write them"
    assert {"table": "collection_items", "id": item} in card["provenance"]["source_rows"]
    made = studio.post("/api/v1/record/draft", json={"day": card["day"], "card_id": card["card_id"]}).json()
    assert _status(item) == ("used", made["id"]), "a draft from the card did not use the item"


def test_a_removed_item_drops_its_card(studio):
    import collection
    import record_cards
    item = _item("pricing pages lie less when founders write them")
    card = _slot_three(studio)
    collection.remove(item)
    conn = get_db()
    try:
        assert record_cards.verify(conn, {"status": "shown", "provenance": card["provenance"]})["status"] == "dropped"
    finally:
        conn.close()


def test_with_the_collection_left_out_of_ideas_no_card_draws_on_it(studio):
    _item("pricing pages lie less when founders write them")
    studio.put("/api/v1/writing/preferences", json={"sources": ["posts", "asks"]})
    assert _slot_three(studio)["kind"] != "collected"


# ---------------------------------------------------------------------------
# The weekly summary and /recall
# ---------------------------------------------------------------------------

def test_the_weekly_summary_counts_the_ideas_still_unused(notifying, clock):
    bot = notifying
    _saved(bot)
    for text in ("one idea", "two ideas", "three ideas"):
        _item(text)
    import collection
    collection.set_status(_item("set aside"), "not_now")
    _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1)
    assert "Ideas waiting in your collection, not used yet: 3" in _summaries(bot)[0].split("\n")


def _recall(bot, words):
    before = len(_texts(bot))
    bot["fake"].push(OWNER, "/recall " + words if words else "/recall")
    assert _until(lambda: len(_texts(bot)) > before), _texts(bot)
    return _texts(bot)[-1]


def test_recall_says_how_many_match_and_their_first_lines_only_with_the_switch(bot):
    _saved(bot)
    _item("pricing pages lie less when founders write them\nand more")
    _item("pricing for agencies is a different game")
    _item("hiring loops")
    assert _recall(bot, "pricing") == SAID["recall"].format(count=2)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    said = _recall(bot, "pricing")
    assert said.startswith(SAID["recall"].format(count=2))
    assert "pricing pages lie less when founders write them" in said and "and more" not in said
    assert _recall(bot, "zebras") == SAID["recall_none"]
    assert _recall(bot, "hiring").startswith(SAID["recall_one"]), "one item is not said as one"
    assert _recall(bot, "") == SAID["empty_recall"]
