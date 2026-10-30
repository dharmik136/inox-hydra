"""
/write <word or #tag>: one draft from the unused items that match (phase 4, item 9).
====================================================================================

The unused items (new, with words) that hold the word, or carry the tag,
newest first, up to the creator's "Most items in one draft", through the
existing Combine path (one item: Make a post), beside the bot's loop. Nothing
matches: said, and nothing is asked of the provider. No provider: the
existing no_provider answer. Today's fixed limit of ten (COMBINE_AT_MOST)
becomes that preference, ten by default, read by Combine in the box too.

docs/quality/cycle4/bot-phase4.md, item 9. Against the fake Bot API and the
fake provider.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
import writing  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _seed(*entries):
    """Items in the collection, oldest first: (words, status, kind) or words."""
    import collection
    ids = []
    for n, entry in enumerate(entries):
        words, status, kind = (entry, "new", "note") if isinstance(entry, str) else entry
        ids.append(collection.add(kind, words, status=status)["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         (f"2026-10-2{n}T08:00:00+00:00" if n < 10 else f"2026-10-{n}T08:00:00+00:00", ids[-1]))
        conn.close()
    return ids


def _status(ids):
    conn = get_db()
    try:
        return [conn.execute("SELECT status FROM collection_items WHERE id = ?", (i,)).fetchone()[0] for i in ids]
    finally:
        conn.close()


def test_write_makes_one_draft_from_the_unused_items_that_hold_the_word(bot, provider):
    _saved(bot)
    ids = _seed("pricing is a design decision", "hiring loops are slow", ("pricing an old idea", "used", "note"),
                ("pricing pages lie", "new", "idea"))
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: SAID["write_from"].format(count=2) in _texts(bot)), _texts(bot)
    assert _until(lambda: _texts(bot)[-1:] == [SAID["draft_ready"]]), _texts(bot)
    sent = provider.sent()
    assert "pricing is a design decision" in sent and "pricing pages lie" in sent
    assert "hiring loops" not in sent and "an old idea" not in sent
    assert _status(ids) == ["used", "new", "used", "used"]


def test_write_a_tag_takes_the_items_that_carry_it(bot, provider):
    _saved(bot)
    ids = _seed("a thought on #pricing", "pricing without the tag", "another #Pricing note")
    bot["fake"].push(OWNER, "/write #pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["draft_ready"]]), _texts(bot)
    assert SAID["write_from"].format(count=2) in _texts(bot)
    assert _status(ids) == ["used", "new", "used"]


def test_the_newest_are_taken_up_to_the_creators_most_items(bot, provider):
    _saved(bot)
    assert bot["client"].put("/api/v1/writing/preferences", json={"combine_at_most": 2}).status_code == 200
    ids = _seed("pricing one", "pricing two", "pricing three")
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["draft_ready"]]), _texts(bot)
    assert SAID["write_from"].format(count=2) in _texts(bot)
    assert _status(ids) == ["new", "used", "used"]


def test_one_match_is_made_into_a_post_alone(bot, provider):
    _saved(bot)
    ids = _seed("pricing is a design decision", "hiring loops")
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["draft_ready"]]), _texts(bot)
    assert SAID["write_from_one"] in _texts(bot)
    assert _status(ids) == ["used", "new"]


def test_nothing_matching_is_said_and_nothing_is_asked(bot, provider):
    _saved(bot)
    _seed("hiring loops are slow")
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["write_none"]]), _texts(bot)
    time.sleep(0.4)
    assert provider.requests == []


def test_with_no_provider_it_says_so(bot):
    _saved(bot)
    _seed("pricing is a design decision")
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["no_provider"]]), _texts(bot)


def test_write_with_nothing_after_it_says_how(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "/write")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["empty_write"]]), _texts(bot)


def test_it_is_answered_with_the_confirmations_off(bot, provider):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    _seed("pricing is a design decision")
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["draft_ready"]]), _texts(bot)


def test_it_is_in_the_menu_and_in_help():
    assert "write" in [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "- /write: " in telegram_bot.HELP


def test_most_items_in_one_draft_is_a_preference_ten_by_default(bot, provider):
    assert writing.preferences()["combine_at_most"] == 10
    ids = _seed(*[f"note number {n} on pricing" for n in range(11)])
    res = bot["client"].post("/api/v1/collection/write", json={"items": ids})
    assert res.status_code == 400 and "10" in res.json()["detail"], res.text
    assert bot["client"].put("/api/v1/writing/preferences", json={"combine_at_most": 12}).status_code == 200
    res = bot["client"].post("/api/v1/collection/write", json={"items": ids})
    assert res.status_code == 200 and res.json()["status"] == "drafted", res.text
    for wrong in (1, 21, "ten"):
        assert bot["client"].put("/api/v1/writing/preferences", json={"combine_at_most": wrong}).status_code in (400, 422)
    assert writing.preferences()["combine_at_most"] == 12
