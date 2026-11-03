"""
It connects to, in real time (phase 6, item 1).
===============================================

When something with words is saved from the phone, "Saved to your
collection." also says how many other unused items share at least the
creator's number of its meaningful words, with Write one post from these:
the item and the ones it connects to, read again at the press, as many as
"Connected items offered with one" and never more than "Most items in one
draft" in all, written through Combine. Their first lines come only with the
words switch on. Your collection shows the same groups on each item, and the
group itself. Matched on the computer; nothing leaves it but a count, and the
words only with the switch, and only to the creator's own provider on a press.

docs/quality/cycle4/bot-phase6.md, item 1. Against the fake Bot API and the
fake provider.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
COMBINE = "Write one post from these"
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _seed(*entries):
    """Items in the collection, oldest first: (words, status) or words; each a day newer than the one before."""
    import collection
    ids = []
    for n, entry in enumerate(entries):
        words, status = (entry, "new") if isinstance(entry, str) else entry
        ids.append(collection.add("note", words, status=status, source="studio")["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-{10 + n:02d}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def _answers(bot):
    return [m for m in bot["fake"].sent if str(m["text"] or "").startswith(SAID["collected"])]


def _sent(bot, words):
    """A message from the phone, and the bot's answer to it once it has come: its id and its text."""
    before = len(_answers(bot))
    bot["fake"].push(OWNER, words)
    assert _until(lambda: len(_answers(bot)) > before), _texts(bot)
    answer = _answers(bot)[-1]
    return answer["message_id"], answer["text"]


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _notices(bot):
    return [a["text"] for a in bot["fake"].answered]


def _words_on(bot):
    assert bot["client"].post("/api/v1/ingress/options", json={"collection_words": True}).status_code == 200


def _status(ids):
    conn = get_db()
    try:
        return [conn.execute("SELECT status FROM collection_items WHERE id = ?", (i,)).fetchone()[0] for i in ids]
    finally:
        conn.close()


def _made():
    conn = get_db()
    try:
        return [json.loads(r[0]) for r in conn.execute("SELECT made_with FROM posts WHERE made_with IS NOT NULL "
                                                       "ORDER BY rowid")]
    finally:
        conn.close()


def _newest_item_id():
    conn = get_db()
    try:
        return conn.execute("SELECT MAX(id) FROM collection_items").fetchone()[0]
    finally:
        conn.close()


def test_a_saved_idea_says_how_many_unused_items_it_shares_words_with_and_no_words(bot, provider):
    _saved(bot)
    _seed("the pricing page is a brief", "pricing the page for a studio", ("pricing page an old one", "used"),
          "pricing alone", "hiring loops")
    message, text = _sent(bot, "Idea: pricing page copy for founders")
    assert text == SAID["collected"] + " " + SAID["connects"].format(count=2), text
    assert "pricing" not in text and "page" not in text, "the creator's words went with the words switch off"
    assert COMBINE in _labels(bot, message)
    assert _labels(bot, message)[:2] == ["Write it up", "3 angles"]


def test_with_the_words_on_the_offered_ones_come_most_shared_first_then_newest(bot, provider):
    _saved(bot)
    _words_on(bot)
    _seed("pricing page founders one", "pricing page two", "pricing page three", "pricing page founders four",
          "pricing page five")
    message, text = _sent(bot, "Idea: pricing page for founders")
    head = SAID["collected"] + " " + SAID["connects"].format(count=5)
    assert text.startswith(head), text
    assert text[len(head):] == ("\n\n" + SAID["connects_most"].format(count=3)
                                + "\n1. pricing page founders four\n2. pricing page founders one\n3. pricing page five")


def test_with_the_words_on_and_few_enough_there_is_no_most_line(bot, provider):
    _saved(bot)
    _words_on(bot)
    _seed("pricing page founders one", "hiring loops")
    _message, text = _sent(bot, "Idea: pricing page for founders")
    assert text == (SAID["collected"] + " " + SAID["connects_one"] + "\n\n1. pricing page founders one"), text


def test_write_one_post_from_these_writes_the_item_and_what_it_connects_to(bot, provider):
    _saved(bot)
    ids = _seed("the pricing page is a brief", "pricing the page for a studio", "hiring loops")
    message, _text = _sent(bot, "Idea: pricing page copy for founders")
    item = _newest_item_id()
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["write_from"].format(count=3)]), _notices(bot)
    assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)
    sent = provider.sent()
    assert "pricing page copy for founders" in sent and "the pricing page is a brief" in sent
    assert "pricing the page for a studio" in sent and "hiring" not in sent
    assert _status(ids + [item]) == ["used", "used", "new", "used"]
    made = _made()[-1]
    assert made["via"] == "telegram" and made["connected"] is True
    assert sorted(made["items"]) == sorted([item, ids[0], ids[1]])
    assert _until(lambda: _labels(bot, message) == [])


def test_the_press_reads_the_group_again_and_says_when_nothing_is_left(bot, provider):
    _saved(bot)
    ids = _seed("the pricing page is a brief")
    message, _text = _sent(bot, "Idea: pricing page copy for founders")
    import collection
    collection.set_status(ids[0], "not_now")
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["connected_none"]]), _notices(bot)
    assert _until(lambda: COMBINE not in _labels(bot, message))
    assert "Write it up" in _labels(bot, message) and "Undo" in _labels(bot, message), "the other buttons went"
    assert _made() == []


def test_a_press_on_an_item_used_since_writes_nothing(bot, provider):
    _saved(bot)
    _seed("the pricing page is a brief")
    message, _text = _sent(bot, "Idea: pricing page copy for founders")
    conn = get_db()
    with conn:
        conn.execute("UPDATE collection_items SET status = 'used' WHERE id = ?", (_newest_item_id(),))
    conn.close()
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["connected_used"]]), _notices(bot)
    assert _made() == []


def test_with_no_provider_a_press_says_so_and_every_button_stays(bot):
    _saved(bot)
    _seed("the pricing page is a brief")
    message, _text = _sent(bot, "Idea: pricing page copy for founders")
    before = _labels(bot, message)
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["no_provider"]]), _notices(bot)
    time.sleep(0.4)
    assert _labels(bot, message) == before


def test_nothing_that_connects_says_nothing_more_and_offers_nothing_more(bot, provider):
    _saved(bot)
    _seed("pricing alone", "hiring loops")
    message, text = _sent(bot, "Idea: pricing page copy")
    assert text == SAID["collected"]
    assert COMBINE not in _labels(bot, message)


def test_the_switch_is_on_by_default_and_turns_it_off(bot, provider):
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["connect"] is True and options["connect_shared"] == 2 and options["connect_offer"] == 3
    _seed("the pricing page is a brief")
    assert bot["client"].post("/api/v1/ingress/options", json={"connect": False}).status_code == 200
    message, text = _sent(bot, "Idea: pricing page copy for founders")
    assert text == SAID["collected"]
    assert COMBINE not in _labels(bot, message)


def test_how_many_words_connect_and_how_many_are_offered_are_the_creators(bot, provider):
    import writing
    _saved(bot)
    assert writing.preferences()["connect_shared"] == 2 and writing.preferences()["connect_offer"] == 3
    ids = _seed("pricing alone", "pricing page one", "pricing page two", "pricing page three")
    assert bot["client"].put("/api/v1/writing/preferences", json={"connect_shared": 1}).status_code == 200
    _message, text = _sent(bot, "Idea: pricing page copy")
    assert text == SAID["collected"] + " " + SAID["connects"].format(count=4), text
    first = _newest_item_id()
    assert bot["client"].put("/api/v1/writing/preferences", json={"connect_offer": 1}).status_code == 200
    message, _text = _sent(bot, "Idea: pricing page again")
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["write_from"].format(count=2)]), _notices(bot)
    assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)
    # Two words shared with each; the newest of those, the idea sent first here, is the one offered.
    assert sorted(_made()[-1]["items"]) == sorted([_newest_item_id(), first])
    assert _status(ids) == ["new", "new", "new", "new"]
    for field, wrong in (("connect_shared", 0), ("connect_shared", 6), ("connect_offer", 0), ("connect_offer", 10),
                         ("connect_offer", "many")):
        assert bot["client"].put("/api/v1/writing/preferences", json={field: wrong}).status_code in (400, 422), field
    assert writing.preferences()["connect_shared"] == 1 and writing.preferences()["connect_offer"] == 1


def test_never_more_than_most_items_in_one_draft(bot, provider):
    _saved(bot)
    _seed("pricing page one", "pricing page two", "pricing page three")
    assert bot["client"].put("/api/v1/writing/preferences", json={"combine_at_most": 2}).status_code == 200
    message, _text = _sent(bot, "Idea: pricing page copy")
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["write_from"].format(count=2)]), _notices(bot)


def test_your_collection_lists_what_each_item_connects_to_and_opens_the_group(bot):
    _saved(bot)
    ids = _seed("pricing page founders one", "pricing page two", ("pricing page used", "used"), "hiring loops",
                "pricing page founders newest")
    listing = bot["client"].get("/api/v1/collection").json()
    by_id = {item["id"]: item for item in listing["items"]}
    newest = by_id[ids[4]]["connected"]
    assert newest["count"] == 2 and newest["ids"] == [ids[0], ids[1]]
    assert newest["words"][:2] == ["page", "pricing"] and "founders" in newest["words"]
    assert by_id[ids[3]]["connected"] is None
    group = bot["client"].get(f"/api/v1/collection?around={ids[4]}").json()
    assert [item["id"] for item in group["items"]] == [ids[4], ids[0], ids[1]]
    used = bot["client"].get("/api/v1/collection?status=used").json()["items"]
    assert used[0]["connected"] is None, "a used item said what it connects to"


def test_it_is_in_the_tour_and_the_panel_lists_a_draft_from_what_an_idea_connects_to(bot, provider):
    _saved(bot)
    assert any("connected" in steps for _title, steps in telegram_bot.TOUR_PARTS)
    seen = {s["key"]: s["seen"] for s in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}
    assert seen["connected"] is False
    _seed("the pricing page is a brief")
    message, _text = _sent(bot, "Idea: pricing page copy for founders")
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)

    def seen_now():
        return {s["key"]: s["seen"] for s in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}
    assert _until(lambda: seen_now()["connected"]), seen_now()
