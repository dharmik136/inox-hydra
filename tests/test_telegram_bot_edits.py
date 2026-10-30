"""
Edits follow (phase 4, item 7).
===============================

The poll asks for edited_message too. Editing a message in Telegram updates
the item it made while the item has not been used, live in the studio, read
as the message was (a prefix such as Idea: or a command such as /idea taken
off). Once the item has been used, the draft is kept as it is, the item takes
the edit and says so, and the bot says the draft was not changed. An edit
from any other chat is refused like a stranger's message, and an edit of a
message that made nothing changes nothing, which the bot says.

docs/quality/cycle4/bot-phase4.md, item 7. Against the fake Bot API, which
delivers an edit only to a poll that asks for one, as Telegram does.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_build_up import _items, _reply_to, _send  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _edit(bot, message_id, text, chat=OWNER, **message):
    before = len(_texts(bot))
    bot["fake"].edit(chat, message_id, text, **message)
    assert _until(lambda: len(_texts(bot)) > before or bot["fake"].waiting() == []), _texts(bot)
    assert _until(lambda: bot["fake"].waiting() == [])


def test_the_poll_asks_for_edits():
    assert "edited_message" in ingress.ALLOWED_UPDATES


def test_an_edit_updates_a_new_item_and_says_so(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a desing decision")
    _edit(bot, first, "pricing is a design decision")
    assert _until(lambda: [i["text"] for i in _items()] == ["pricing is a design decision"]), _items()
    assert _texts(bot)[-1] == SAID["edited"]
    [listed] = bot["client"].get("/api/v1/collection").json()["items"]
    assert listed["edited_at"], "the box does not say it was edited"


def test_an_edit_is_read_as_the_message_was(bot):
    _saved(bot)
    first, _answer = _send(bot, "Idea: a first try")
    second, _answer = _send(bot, "/idea another try")
    _edit(bot, first, "Idea: a better try")
    _edit(bot, second, "/idea another, better try")
    assert _until(lambda: [i["text"] for i in _items()] == ["a better try", "another, better try"]), _items()
    assert [i["kind"] for i in _items()] == ["idea", "idea"]


def test_an_edit_of_a_reply_changes_only_its_own_words(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    reply, _answer = _send(bot, "and the price pgae", **_reply_to(first))
    _edit(bot, reply, "and the price page")
    assert _until(lambda: _items()[0]["text"] == "pricing is a design decision\n\nand the price page"), _items()


def test_once_used_the_draft_is_kept_and_the_bot_says_so(bot):
    _saved(bot)
    first, _answer = _send(bot, "Draft: my post as I wrote it")
    _edit(bot, first, "Draft: my post as I meant it")
    assert _until(lambda: _texts(bot)[-1] == SAID["edited_draft"]), _texts(bot)
    [item] = _items()
    assert item["text"] == "my post as I meant it", "the edit was not recorded on the item"
    conn = get_db()
    content = conn.execute("SELECT content FROM posts WHERE id = ?", (item["post_id"],)).fetchone()[0]
    conn.close()
    assert content == "my post as I wrote it", "the draft was changed"


def test_an_edit_of_a_message_that_made_nothing_changes_nothing(bot):
    _saved(bot)
    first, _answer = _send(bot, "/status")
    _edit(bot, first, "/status now")
    assert _until(lambda: _texts(bot)[-1] == SAID["edit_nothing"]), _texts(bot)
    assert _items() == []


def test_an_edit_from_another_chat_is_refused_like_a_strangers_message(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    bot["fake"].edit(STRANGER, first, "taken over")
    assert _until(lambda: bot["fake"].waiting() == [])
    time.sleep(0.3)
    assert [i["text"] for i in _items()] == ["pricing is a design decision"]
    chats = bot["client"].get("/api/v1/ingress/settings").json()["refused_chats"]
    assert [c["chat_id"] for c in chats] == [STRANGER]


def test_a_caption_edit_updates_a_photos_words(bot):
    _saved(bot)
    bot["fake"].add_file("ph1", b"\xff\xd8photo-bytes", file_path="photos/ph1.jpg")
    first, _answer = _send(bot, None, photo=[{"file_id": "ph1", "file_unique_id": "u1", "width": 10, "height": 10,
                                              "file_size": 11}], caption="a whiteboard from tday")
    _edit(bot, first, None, caption="a whiteboard from today")
    assert _until(lambda: [i["text"] for i in _items()] == ["a whiteboard from today"]), _items()
    assert json.loads(_items()[0]["media"])["path"], "the photo went with the edit"


def test_with_the_confirmations_off_an_edit_is_still_kept_and_not_answered(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a desing decision")
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    count = len(_texts(bot))
    bot["fake"].edit(OWNER, first, "pricing is a design decision")
    assert _until(lambda: [i["text"] for i in _items()] == ["pricing is a design decision"])
    time.sleep(0.3)
    assert len(_texts(bot)) == count
