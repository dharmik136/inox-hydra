"""
Remember this, under "Saved to your collection." (phase 4, item 8).
===================================================================

For a note or an idea whose words fit a thing to remember (300 characters),
the bot's answer carries Remember this. A press keeps those words as a thing
to remember (about you, or what a prefix such as `offer:` says, as /remember
reads it), sets the item used ("Kept in your things to remember"), and the
message says so with Undo, which removes the fact and puts the item back to
new. Not offered for a forward (someone else's words), a link, or a file.

docs/quality/cycle4/bot-phase4.md, item 8. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import remembered  # noqa: E402
import telegram_bot  # noqa: E402
from test_telegram_bot_build_up import _items, _labels, _send  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved  # noqa: E402

SAID = telegram_bot.SENTENCES
REMEMBER = "Remember this"


def _answers(bot):
    return [a["text"] for a in bot["fake"].answered]


def test_a_note_carries_remember_this(bot):
    _saved(bot)
    _mid, answer = _send(bot, "I write for founders of small design studios")
    assert _labels(bot, answer) == ["Write it up", "3 angles", REMEMBER, "Undo"]


def test_a_press_keeps_it_as_a_thing_to_remember_and_the_item_is_used(bot):
    _saved(bot)
    _mid, answer = _send(bot, "I write for founders of small design studios")
    bot["fake"].press_button(REMEMBER, OWNER, message_id=answer["message_id"])
    assert _until(lambda: _answers(bot) == [SAID["remembered_item"]]), _answers(bot)
    [fact] = remembered.listing()
    assert (fact["text"], fact["about"], fact["source"]) == ("I write for founders of small design studios", "you",
                                                             "telegram")
    [item] = _items()
    assert item["status"] == "used"
    [listed] = bot["client"].get("/api/v1/collection?status=all").json()["items"]
    assert listed["became"] == {"kind": "fact", "said": "Kept in your things to remember"}
    shown = bot["fake"].message(answer["message_id"])
    assert shown["text"] == SAID["collected"] + "\n\n" + SAID["remembered_item"]
    assert _labels(bot, answer) == ["Undo"]


def test_what_it_is_about_is_read_as_remember_reads_it(bot):
    _saved(bot)
    _mid, answer = _send(bot, "Idea: offer: a workshop for small studios")
    bot["fake"].press_button(REMEMBER, OWNER, message_id=answer["message_id"])
    assert _until(lambda: len(remembered.listing()) == 1)
    [fact] = remembered.listing()
    assert (fact["text"], fact["about"]) == ("a workshop for small studios", "offer")


def test_undo_removes_the_fact_and_brings_the_item_back(bot):
    _saved(bot)
    _mid, answer = _send(bot, "I write for founders of small design studios")
    bot["fake"].press_button(REMEMBER, OWNER, message_id=answer["message_id"])
    assert _until(lambda: _labels(bot, answer) == ["Undo"])
    bot["fake"].press_button("Undo", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _answers(bot)[-1:] == [SAID["remember_undone"]]), _answers(bot)
    assert remembered.listing() == []
    [item] = _items()
    assert item["status"] == "new" and item["used_at"] is None


def test_it_is_not_offered_for_a_forward_a_link_or_words_too_long(bot):
    _saved(bot)
    _mid, forward = _send(bot, "someone else's words", forward_origin={"type": "hidden_user", "date": 1,
                                                                      "sender_user_name": "Somebody"})
    assert REMEMBER not in _labels(bot, forward)
    _mid, long_one = _send(bot, "a long note " + "about pricing " * 40)
    assert REMEMBER not in _labels(bot, long_one)
    _mid, link = _send(bot, "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000777/ worth a look")
    assert REMEMBER not in _labels(bot, link)


def test_words_already_kept_are_said_and_nothing_more_is_kept(bot):
    _saved(bot)
    remembered.add("I write for founders of small design studios", "you", "studio")
    _mid, answer = _send(bot, "I write for founders of small design studios")
    bot["fake"].press_button(REMEMBER, OWNER, message_id=answer["message_id"])
    assert _until(lambda: _answers(bot) == [SAID["remember_already"]]), _answers(bot)
    assert len(remembered.listing()) == 1 and _items()[0]["status"] == "new"
