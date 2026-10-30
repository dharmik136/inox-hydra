"""
Build an idea up over the day: a reply adds to what it replies to (phase 4, item 6).
====================================================================================

Each message saved from the phone is linked to the item it made, by its chat
and message id, and so is each of the bot's answers about an item, once
Telegram says it took it. A Telegram reply from the paired chat, to one of
the creator's earlier messages or to the bot's answer about one, adds its
words to that item instead of making a new one. The bot answers with Undo,
without quoting the creator's words unless the words switch allows it. If
the item already became a draft, the words still go on the item and the bot
says the draft was not changed. A preference, on by default, switches it off.

The links live in a table of their own (migration 41, collection_messages),
which every table of the creator's passes: Storage sizes it, the export
carries it, Delete everything clears it, and the diagnostics bundle carries
no word of it.

docs/quality/cycle4/bot-phase4.md, item 6. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sqlite3
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import migrations  # noqa: E402
import paths  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
TABLE = "collection_messages"


def _items():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM collection_items ORDER BY id")]
    finally:
        conn.close()


def _send(bot, text, **message):
    """A message from the owner's phone, and the bot's answer to it; returns (its message id, the answer)."""
    before = len(_texts(bot))
    update_id = bot["fake"].push(OWNER, text, **message)
    assert _until(lambda: len(_texts(bot)) > before), _texts(bot)
    return bot["fake"].message_ids[update_id], [m for m in bot["fake"].sent if m["chat_id"] == OWNER][-1]


def _reply_to(message_id, text="the earlier words"):
    return {"reply_to_message": {"message_id": message_id, "date": int(time.time()), "text": text,
                                 "chat": {"id": int(OWNER), "type": "private"}}}


def _labels(bot, message):
    return [b["text"] for b in bot["fake"].buttons(message["message_id"])]


def test_a_reply_to_an_earlier_message_adds_its_words_to_that_item(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    _mid, answer = _send(bot, "and the price page is the brief", **_reply_to(first))
    [item] = _items()
    assert item["text"] == "pricing is a design decision\n\nand the price page is the brief"
    assert answer["text"] == SAID["added"], answer["text"]
    assert "price page" not in answer["text"], "the creator's words went back with the switch off"
    assert _labels(bot, answer) == ["Undo"]


def test_a_reply_to_the_bots_answer_about_an_item_does_the_same(bot):
    _saved(bot)
    _first, answer = _send(bot, "hiring loops are slow")
    assert _until(lambda: _linked(answer["message_id"]) is not None), "the bot's answer was never linked to its item"
    _send(bot, "because nobody owns them", **_reply_to(answer["message_id"], answer["text"]))
    [item] = _items()
    assert item["text"] == "hiring loops are slow\n\nbecause nobody owns them"


def _linked(message_id):
    conn = get_db()
    try:
        row = conn.execute(f"SELECT item_id, whose FROM {TABLE} WHERE chat_id = ? AND message_id = ?",
                           (OWNER, message_id)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def test_with_the_words_switch_on_the_answer_names_the_item(bot):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    first, _answer = _send(bot, "pricing is a design decision")
    _mid, answer = _send(bot, "more on it", **_reply_to(first))
    assert answer["text"] == SAID["added_words"] + "\n\npricing is a design decision"


def test_undo_takes_the_words_back_off(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    _mid, answer = _send(bot, "a second thought", **_reply_to(first))
    bot["fake"].press_button("Undo", OWNER, message_id=answer["message_id"])
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["added_undone"]])
    [item] = _items()
    assert item["text"] == "pricing is a design decision" and item["status"] == "new"


def test_an_item_that_became_a_draft_takes_the_words_and_the_draft_is_not_changed(bot):
    _saved(bot)
    first, _answer = _send(bot, "Draft: my whole post, as written")
    _mid, answer = _send(bot, "a line I forgot", **_reply_to(first))
    assert answer["text"] == SAID["added_draft"], answer["text"]
    [item] = _items()
    assert item["text"] == "my whole post, as written\n\na line I forgot"
    conn = get_db()
    content = conn.execute("SELECT content FROM posts WHERE id = ?", (item["post_id"],)).fetchone()[0]
    conn.close()
    assert content == "my whole post, as written", "the draft was changed"


def test_switched_off_a_reply_is_an_item_of_its_own(bot):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"replies_add": False})
    assert res.status_code == 200 and res.json()["options"]["replies_add"] is False
    first, _answer = _send(bot, "pricing is a design decision")
    _mid, answer = _send(bot, "another thought", **_reply_to(first))
    assert [i["text"] for i in _items()] == ["pricing is a design decision", "another thought"]
    assert answer["text"] == SAID["collected"]


def test_it_is_on_by_default(bot):
    _saved(bot)
    assert bot["client"].get("/api/v1/ingress/settings").json()["options"]["replies_add"] is True


def test_a_command_in_a_reply_is_a_command(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    _mid, answer = _send(bot, "/status", **_reply_to(first))
    assert answer["text"].startswith("Your studio is running.")
    assert [i["text"] for i in _items()] == ["pricing is a design decision"]


def test_a_reply_to_something_no_longer_in_the_box_makes_a_new_item(bot):
    _saved(bot)
    first, answer = _send(bot, "pricing is a design decision")
    bot["fake"].press_button("Undo", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _items() == [])
    _mid, again = _send(bot, "a fresh start", **_reply_to(first))
    assert [i["text"] for i in _items()] == ["a fresh start"] and again["text"] == SAID["collected"]


def test_a_reply_handled_twice_adds_its_words_once(bot):
    import collection
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    [item] = _items()
    for _ in range(2):
        collection.add_words(item["id"], OWNER, 999, "said once")
    assert _items()[0]["text"] == "pricing is a design decision\n\nsaid once"


def test_the_box_says_an_item_was_built_from_several_messages(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    _send(bot, "second", **_reply_to(first))
    _send(bot, "third", **_reply_to(first))
    [listed] = bot["client"].get("/api/v1/collection").json()["items"]
    assert listed["messages"] == 3


# ---------------------------------------------------------------------------
# The table, as every table of the creator's
# ---------------------------------------------------------------------------

def _the_migration():
    found = [m for m in migrations.MIGRATIONS if m[2] is getattr(migrations, "_migrate_message_links", None)]
    assert len(found) == 1, "the links' migration is not in the ledger exactly once"
    return found[0]


def test_the_migration_is_named_for_what_it_changes_and_an_older_database_gains_it(bot):
    version, description, payload = _the_migration()
    assert "message" in description.lower() and "reply" in description.lower()
    conn = sqlite3.connect(paths.get_db_path())
    conn.execute(f"DROP TABLE {TABLE}")
    conn.execute(f"PRAGMA user_version = {version - 1}")
    conn.commit()
    report = migrations.ensure_schema(conn, take_backup=False)
    assert version in [a["version"] for a in report["applied"]]
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")}
    assert {"item_id", "chat_id", "message_id", "whose", "words", "at", "edited_at"} <= columns
    payload(conn.cursor())
    conn.commit()
    assert conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0] == 0
    conn.close()


def test_storage_sizes_it_and_the_export_carries_it():
    import retention
    import support
    assert retention._category_of(TABLE) == "collection"
    assert TABLE in support.EXPORTABLE_TABLES


def test_delete_everything_clears_it_and_the_diagnostics_carry_no_word_of_it(bot):
    import onboarding
    import support
    _saved(bot)
    first, _answer = _send(bot, "the Zenith pricing pitch")
    _send(bot, "with a private aside", **_reply_to(first))
    assert "Zenith" not in json.dumps(support.collect_diagnostics())
    assert "private aside" not in json.dumps(support.collect_diagnostics())
    onboarding.forget_identity()
    conn = get_db()
    left = conn.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    conn.close()
    assert left == 0, "the links survived Delete everything"


def test_removing_an_item_removes_its_links(bot):
    import collection
    _saved(bot)
    _send(bot, "pricing is a design decision")
    [item] = _items()
    assert _until(lambda: len(_links(item["id"])) >= 1)
    collection.remove(item["id"])
    assert _links(item["id"]) == []


def _links(item_id):
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {TABLE} WHERE item_id = ?", (item_id,))]
    finally:
        conn.close()


def test_a_strangers_reply_is_refused(bot):
    _saved(bot)
    first, _answer = _send(bot, "pricing is a design decision")
    bot["fake"].push(STRANGER, "let me add to it", reply_to_message={"message_id": first, "date": 1,
                                                                      "chat": {"id": int(STRANGER)}})
    assert _until(lambda: bot["fake"].waiting() == [])
    time.sleep(0.3)
    assert [i["text"] for i in _items()] == ["pricing is a design decision"]
