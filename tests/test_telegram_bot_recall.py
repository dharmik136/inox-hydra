"""
Act on what /recall finds (phase 5, item 3).
============================================

With the words switch on, /recall lists the matching items' first lines,
numbered, up to "The bot lists at most", each with its Write up button, and
Write one post from these, which writes one draft from the unused items that
hold the word, newest first, up to "Most items in one draft", as /write
does. With the switch off: the count, and Write one post from these, whose
draft lands in the studio. Each button acts once; the others stay. Writing
runs beside the bot's loop, through the creator's own provider.

docs/quality/cycle4/bot-phase5.md, item 3. Against the fake Bot API and the
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
    """Items in the collection, oldest first: (words, status) or words; newest last."""
    import collection
    ids = []
    for n, entry in enumerate(entries):
        words, status = (entry, "new") if isinstance(entry, str) else entry
        ids.append(collection.add("note", words, status=status)["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-{10 + n:02d}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def _status(ids):
    conn = get_db()
    try:
        return [conn.execute("SELECT status FROM collection_items WHERE id = ?", (i,)).fetchone()[0] for i in ids]
    finally:
        conn.close()


def _answers(bot):
    return [m["message_id"] for m in bot["fake"].sent
            if str(m["text"] or "").startswith(("One item in your collection", "Nothing in your collection"))
            or " items in your collection hold that word." in str(m["text"] or "")]


def _answer(bot):
    found = _answers(bot)
    return found[-1] if found else None


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _words_on(bot):
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})


def _recalled(bot, word="pricing"):
    """/recall sent, and its answer's id, once a new one has come."""
    before = len(_answers(bot))
    bot["fake"].push(OWNER, f"/recall {word}")
    assert _until(lambda: len(_answers(bot)) > before), _texts(bot)
    return _answer(bot)


def _drafts():
    conn = get_db()
    try:
        return [json.loads(r[0]) for r in conn.execute("SELECT made_with FROM posts WHERE made_with IS NOT NULL "
                                                       "ORDER BY rowid")]
    finally:
        conn.close()


def test_with_the_words_on_it_lists_first_lines_each_with_write_up_and_one_post_from_these(bot, provider):
    _saved(bot)
    _words_on(bot)
    _seed("pricing is a design decision\nsecond line", "hiring loops", ("pricing an old idea", "used"),
          "pricing pages lie")
    message = _recalled(bot)
    text = bot["fake"].message(message)["text"]
    assert text.startswith(SAID["recall"].format(count=3))
    assert "1. pricing pages lie" in text and "2. pricing an old idea" in text and "3. pricing is a design decision" in text
    assert "second line" not in text and "hiring" not in text
    assert _labels(bot, message) == ["Write up 1", "Write up 2", "Write up 3", COMBINE]


def test_more_than_the_list_shows_says_the_newest_and_the_list_is_a_preference(bot, provider):
    _saved(bot)
    _words_on(bot)
    _seed(*[f"pricing note {n}" for n in range(7)])
    message = _recalled(bot)
    text = bot["fake"].message(message)["text"]
    assert "The newest 5:" in text and "5. pricing note 2" in text and "pricing note 1" not in text
    assert bot["client"].post("/api/v1/ingress/options", json={"list_at_most": 2}).status_code == 200
    message = _recalled(bot)
    text = bot["fake"].message(message)["text"]
    assert "The newest 2:" in text and "2. pricing note 5" in text and "pricing note 4" not in text
    assert _labels(bot, message) == ["Write up 1", "Write up 2", COMBINE]


def test_write_up_writes_that_item_and_the_other_buttons_stay(bot, provider):
    _saved(bot)
    _words_on(bot)
    ids = _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button("Write up 2", OWNER, message_id=message)
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)
    assert [a["text"] for a in bot["fake"].answered][-1] == SAID["writing"]
    assert "pricing is a design decision" in provider.sent() and "pricing pages lie" not in provider.sent()
    assert _status(ids) == ["used", "new"]
    assert _labels(bot, message) == ["Write up 1", COMBINE], "the pressed button stayed, or the others went"
    assert _drafts()[-1]["via"] == "telegram"


def test_one_post_from_these_writes_the_unused_items_that_hold_the_word(bot, provider):
    _saved(bot)
    _words_on(bot)
    ids = _seed("pricing is a design decision", ("pricing an old idea", "used"), "hiring loops", "pricing pages lie")
    message = _recalled(bot)
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["write_from"].format(count=2)])
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)
    sent = provider.sent()
    assert "pricing is a design decision" in sent and "pricing pages lie" in sent
    assert "an old idea" not in sent and "hiring" not in sent
    assert _status(ids) == ["used", "used", "new", "used"]
    assert _drafts()[-1]["items"] == [ids[3], ids[0]] and _drafts()[-1]["via"] == "telegram"
    assert COMBINE not in _labels(bot, message)


def test_with_the_words_off_the_count_and_one_post_from_these_whose_draft_lands_in_the_studio(bot, provider):
    _saved(bot)
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    assert bot["fake"].message(message)["text"] == SAID["recall"].format(count=2)
    assert _labels(bot, message) == [COMBINE]
    bot["fake"].press_button(COMBINE, OWNER, message_id=message)
    assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM posts WHERE made_with IS NOT NULL AND status = 'draft'").fetchone()[0] == 1
    conn.close()


def test_with_no_unused_item_there_is_nothing_to_write_one_post_from(bot, provider):
    _saved(bot)
    _seed(("pricing an old idea", "used"))
    message = _recalled(bot)
    assert bot["fake"].message(message)["text"] == SAID["recall_one"]
    assert _labels(bot, message) == []
    _words_on(bot)
    message = _recalled(bot)
    assert _labels(bot, message) == ["Write up 1"]


def test_with_no_provider_a_press_says_so_and_the_button_stays(bot):
    _saved(bot)
    _words_on(bot)
    _seed("pricing is a design decision")
    message = _recalled(bot)
    bot["fake"].press_button("Write up 1", OWNER, message_id=message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["no_provider"]])
    time.sleep(0.4)
    assert _labels(bot, message) == ["Write up 1", COMBINE]


def test_nothing_matching_offers_nothing(bot, provider):
    _saved(bot)
    _seed("hiring loops")
    bot["fake"].push(OWNER, "/recall pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["recall_none"]]), _texts(bot)
    message = [m for m in bot["fake"].sent if m["text"] == SAID["recall_none"]][-1]["message_id"]
    assert _labels(bot, message) == []


def test_a_button_acts_once(bot, provider):
    _saved(bot)
    _words_on(bot)
    _seed("pricing is a design decision", "pricing pages lie")
    message = _recalled(bot)
    data = next(b["callback_data"] for b in bot["fake"].buttons(message) if b["text"] == "Write up 1")
    bot["fake"].press(OWNER, data, message_id=message)
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)
    bot["fake"].press(OWNER, data, message_id=message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["button_used"]])
    assert len(_drafts()) == 1
