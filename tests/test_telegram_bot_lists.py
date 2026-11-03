"""
See what you have from the phone (phase 6, item 3).
===================================================

/recall alone lists the newest unused items, up to "The bot lists at
most": with the words switch on, their first lines, numbered, each with
words carrying Write up; off, how many and where to see them in the studio.
/remembered, a new command, lists the things the studio remembers for its
writing: with the words switch on, their words, numbered, each with Forget,
which removes that one; off, how many and where they are. The menu gains
/remembered, and a bot whose menu 2.14.0 registered is told once of it alone.

docs/quality/cycle4/bot-phase6.md, item 3. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import hashlib
import json
import os
import sys
from datetime import datetime

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


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": "Pricing is a design decision.\n\nWrite the price page first."}
    yield fake
    fake.close()


def _seed(*entries):
    """Items, oldest first: (kind, words) or (kind, words, status)."""
    import collection
    ids = []
    for n, entry in enumerate(entries):
        kind, words = entry[0], entry[1]
        status = entry[2] if len(entry) > 2 else "new"
        ids.append(collection.add(kind, words, status=status, source="studio")["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-{10 + n:02d}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def _facts(*entries):
    """Things to remember, oldest first: (about, words)."""
    import remembered
    return [remembered.add(words, about, "studio")["id"] for about, words in entries]


def _words_on(bot):
    assert bot["client"].post("/api/v1/ingress/options", json={"collection_words": True}).status_code == 200


def _asked(bot, command, starts):
    """A command sent, and the bot's answer that starts with `starts`, once a new one has come."""
    def found():
        return [m for m in bot["fake"].sent if str(m["text"] or "").startswith(starts)]
    before = len(found())
    bot["fake"].push(OWNER, command)
    assert _until(lambda: len(found()) > before), _texts(bot)
    return found()[-1]


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _notices(bot):
    return [a["text"] for a in bot["fake"].answered]


def test_recall_alone_with_the_words_off_says_how_many_and_where(bot):
    _saved(bot)
    _seed(("note", "pricing is a design decision"), ("idea", "hiring loops"), ("note", "an old one", "used"))
    answer = _asked(bot, "/recall", SAID["waiting"].format(count=2))
    assert answer["text"] == SAID["waiting"].format(count=2) + " " + SAID["waiting_where"]
    assert "pricing" not in answer["text"] and _labels(bot, answer["message_id"]) == []


def test_recall_alone_with_one_or_none_waiting(bot):
    _saved(bot)
    answer = _asked(bot, "/recall", SAID["waiting_none"])
    assert answer["text"] == SAID["waiting_none"]
    _seed(("note", "pricing is a design decision"))
    answer = _asked(bot, "/recall", SAID["waiting_one"])
    assert answer["text"] == SAID["waiting_one"] + " " + SAID["waiting_where_one"]


def test_recall_alone_with_the_words_on_lists_the_newest_each_with_write_up(bot, provider):
    _saved(bot)
    _words_on(bot)
    ids = _seed(("note", "the oldest note"), ("idea", "pricing is a design decision\nsecond line"),
                ("photo", ""), ("note", "hiring loops"), ("note", "an old one", "used"))
    answer = _asked(bot, "/recall", SAID["waiting"].format(count=4))
    assert answer["text"] == (SAID["waiting"].format(count=4) + "\n\n" + "1. hiring loops\n2. a photo, with no words\n"
                              "3. pricing is a design decision\n4. the oldest note")
    assert _labels(bot, answer["message_id"]) == ["Write up 1", "Write up 3", "Write up 4"]
    bot["fake"].press_button("Write up 3", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["writing"]]), _notices(bot)
    assert _until(lambda: SAID["draft_ready_words"] + "\n\nPricing is a design decision." in _texts(bot)), _texts(bot)
    assert "pricing is a design decision" in provider.sent()
    assert _labels(bot, answer["message_id"]) == ["Write up 1", "Write up 4"]
    conn = get_db()
    assert conn.execute("SELECT status FROM collection_items WHERE id = ?", (ids[1],)).fetchone()[0] == "used"
    conn.close()


def test_recall_alone_lists_at_most_the_creators_number(bot):
    _saved(bot)
    _words_on(bot)
    _seed(*[("note", f"note number {n}") for n in range(4)])
    assert bot["client"].post("/api/v1/ingress/options", json={"list_at_most": 2}).status_code == 200
    answer = _asked(bot, "/recall", SAID["waiting"].format(count=4))
    assert answer["text"] == (SAID["waiting"].format(count=4) + "\n\n" + telegram_bot.RECALL_NEWEST.format(count=2)
                              + "\n1. note number 3\n2. note number 2")


def test_recall_with_a_word_is_as_it_was(bot):
    _saved(bot)
    _seed(("note", "pricing is a design decision"), ("note", "hiring loops"))
    answer = _asked(bot, "/recall pricing", SAID["recall_one"])
    assert answer["text"] == SAID["recall_one"]


def test_remembered_with_the_words_off_says_how_many_and_where(bot):
    _saved(bot)
    answer = _asked(bot, "/remembered", SAID["remembered_none"])
    assert answer["text"] == SAID["remembered_none"]
    _facts(("you", "I write for founders of small design studios"))
    answer = _asked(bot, "/remembered", SAID["remembered_one"])
    assert answer["text"] == SAID["remembered_one"] + " " + SAID["remembered_where_one"]
    _facts(("offer", "a workshop for small studios"))
    answer = _asked(bot, "/remembered", SAID["remembered_count"].format(count=2))
    assert answer["text"] == SAID["remembered_count"].format(count=2) + " " + SAID["remembered_where"]
    assert "founders" not in answer["text"] and _labels(bot, answer["message_id"]) == []


def test_remembered_with_the_words_on_lists_them_newest_first_each_with_forget(bot):
    _saved(bot)
    _words_on(bot)
    ids = _facts(("you", "I write for founders of small design studios"), ("offer", "a workshop for small studios"),
                 ("date", "My course opens on 1 March"))
    answer = _asked(bot, "/remembered", SAID["remembered_count"].format(count=3))
    assert answer["text"] == (SAID["remembered_count"].format(count=3) + "\n\n1. A date: My course opens on 1 March\n"
                              "2. An offer: a workshop for small studios\n"
                              "3. About you: I write for founders of small design studios")
    assert _labels(bot, answer["message_id"]) == ["Forget 1", "Forget 2", "Forget 3"]
    bot["fake"].press_button("Forget 2", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["forgot"]]), _notices(bot)
    assert _until(lambda: _labels(bot, answer["message_id"]) == ["Forget 1", "Forget 3"])
    import remembered
    assert [f["id"] for f in remembered.listing()] == [ids[0], ids[2]]
    remembered.remove(ids[0])
    bot["fake"].press_button("Forget 3", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["forget_gone"]]), _notices(bot)


def test_remembered_lists_at_most_the_creators_number_and_says_what_goes_with_writing(bot):
    import remembered
    _saved(bot)
    _words_on(bot)
    ids = _facts(*[("you", f"fact number {n}") for n in range(4)])
    assert bot["client"].post("/api/v1/ingress/options", json={"list_at_most": 2}).status_code == 200
    answer = _asked(bot, "/remembered", SAID["remembered_count"].format(count=4))
    assert answer["text"] == (SAID["remembered_count"].format(count=4) + "\n\n"
                              + telegram_bot.RECALL_NEWEST.format(count=2)
                              + "\n1. About you: fact number 3\n2. About you: fact number 2")
    assert bot["client"].put("/api/v1/writing/preferences", json={"memory": "chosen"}).status_code == 200
    remembered.update(ids[3], in_use=False)
    answer = _asked(bot, "/remembered", SAID["remembered_count"].format(count=4))
    assert "1. About you: fact number 3" + telegram_bot.REMEMBERED_UNTICKED + "\n" in answer["text"]
    assert "2. About you: fact number 2\n" not in answer["text"] and answer["text"].endswith("2. About you: fact number 2")
    assert bot["client"].put("/api/v1/writing/preferences", json={"memory": "off"}).status_code == 200
    answer = _asked(bot, "/remembered", SAID["remembered_count"].format(count=4))
    assert answer["text"].endswith("\n\n" + SAID["remembered_off"])


def test_remembered_is_in_the_menu_and_help_and_answered_with_the_confirmations_off(bot):
    names = [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "remembered" in names and names.index("remembered") == names.index("forget") + 1
    assert "- /remembered: " in telegram_bot.HELP
    assert dict(telegram_bot.BOT_COMMANDS)["recall"].startswith("Alone, your newest unused items")
    _saved(bot)
    assert bot["client"].post("/api/v1/ingress/options", json={"replies": False}).status_code == 200
    assert _asked(bot, "/remembered", SAID["remembered_none"])
    assert _asked(bot, "/recall", SAID["waiting_none"])


def test_the_2_14_list_is_frozen_word_for_word():
    """The fingerprint 2.14.0 kept for chat 487215963, computed from v2.14.0's own BOT_COMMANDS."""
    assert telegram_bot._fingerprint("487215963", telegram_bot.COMMANDS_2_14) == "77ad75f0f5e46498efef28f9"
    assert telegram_bot.COMMANDS_2_14 in telegram_bot.EARLIER_COMMANDS
    assert telegram_bot.COMMANDS_2_13 in telegram_bot.EARLIER_COMMANDS


@pytest.fixture
def touring(bot, monkeypatch):
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    midday = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(telegram_bot, "local_now", lambda: midday)
    return bot


def _menu_of_2_14(chat, names=True):
    """The menu's record as 2.14.0 kept it once Telegram took its list: with the names, or only the fingerprint."""
    held = json.dumps({"chat": str(chat), "commands": [list(c) for c in telegram_bot.COMMANDS_2_14]}, sort_keys=True)
    record = {"fingerprint": hashlib.sha256(held.encode("utf-8")).hexdigest()[:24], "chat": str(chat),
              "at": "2026-11-02T12:00:00+00:00"}
    if names:
        record["names"] = [name for name, _words in telegram_bot.COMMANDS_2_14]
    return record


def _write(key, value):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.close()


@pytest.mark.parametrize("names", [True, False])
def test_a_bot_whose_menu_2_14_registered_is_told_once_of_remembered_alone(touring, names):
    bot = touring
    _write(telegram_bot.MENU_KEY, json.dumps(_menu_of_2_14(OWNER, names=names)))
    _saved(bot)
    notice = telegram_bot.tour_notice_text(["remembered"])
    assert notice.startswith("Your studio was updated: your bot now also takes /remembered. Press Start the tour")
    assert _until(lambda: notice in _texts(bot)), _texts(bot)
    assert _until(lambda: [c["command"] for c in bot["fake"].menu(OWNER)] == [n for n, _w in telegram_bot.BOT_COMMANDS])


def test_the_lists_are_in_the_tour(bot):
    keys = [key for _title, steps in telegram_bot.TOUR_PARTS for key in steps]
    assert "lists" in keys
    assert "/remembered" in telegram_bot.TOUR_STEPS["lists"]["say"] and "/recall" in telegram_bot.TOUR_STEPS["lists"]["say"]
    assert "lists" not in telegram_bot.TOUR_EVIDENCE, "a list leaves nothing in the studio to be seen working"
