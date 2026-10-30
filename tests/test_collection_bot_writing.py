"""
Make something out of the collection, on the bot: Write it up, angles, a morning idea.
=====================================================================================

Phase 3 of the Telegram bot, item 2 (docs/quality/cycle4/collection-box.md).
Under "Saved to your collection.": Write it up, and "<n> angles" with n the
creator's own number. A press is answered at once and the writing runs
beside the bot's loop, never in it: when it is done the bot sends a new
message. A switch, off by default, decides whether that message carries the
written words (the draft's first line, the angles) or only says it is done;
the creator's words then sit on Telegram's servers.

A morning idea, off by default: on the days and at the hour the creator
picks, held by quiet hours, and only with that switch on: one unused item,
the one offered least recently, with an angle from what worked in the
creator's own posts, and Write it up and Not today.

Against the fake Bot API (tests/telegram_fake.py) and a fake provider
(tests/ai_fake.py), both on loopback.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
import time
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
from test_telegram_bot_notifications import _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = lambda body: ({"angles": ["Your price page is a design brief.", "Stop letting finance name it.",
                                            "The cheapest page to write is the price.", "Price it like a product."]}
                                if "opening lines" in str(body) else {"draft": DRAFT})
    yield fake
    fake.close()


def _items():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM collection_items ORDER BY id")]
    finally:
        conn.close()


def _newest(bot):
    return [m for m in bot["fake"].sent if m["chat_id"] == OWNER][-1]


def _labels(bot, message=None):
    message = message or _newest(bot)
    return [b["text"] for b in bot["fake"].buttons(message["message_id"])]


def _answers(bot):
    return [a["text"] for a in bot["fake"].answered]


def _collect(bot, words="pricing is a design decision, not a finance one"):
    before = len(_texts(bot))
    bot["fake"].push(OWNER, words)
    assert _until(lambda: len(_texts(bot)) > before and _texts(bot)[-1] == SAID["collected"]), _texts(bot)
    return _newest(bot)


def _words_on(bot):
    res = bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    assert res.status_code == 200, res.text


def test_saved_to_your_collection_offers_write_it_up_angles_and_undo(bot, provider):
    _saved(bot)
    _collect(bot)
    # Phase 4: a note that fits a thing to remember carries Remember this too.
    assert _labels(bot) == ["Write it up", "3 angles", "Remember this", "Undo"]


def test_write_it_up_answers_at_once_and_says_when_the_draft_is_ready(bot, provider):
    _saved(bot)
    message = _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["writing"]]), _answers(bot)
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready"]), _texts(bot)
    assert bot["fake"].message(message["message_id"])["text"] == SAID["collected"] + "\n\n" + SAID["writing"]
    assert bot["fake"].buttons(message["message_id"]) == []
    [item] = _items()
    assert item["status"] == "used" and item["post_id"]
    everything = " ".join(m["text"] for m in bot["fake"].sent)
    assert "price page" not in everything, "the written words went to Telegram with the switch off"


def test_with_the_words_switch_on_the_answer_carries_the_first_line(bot, provider):
    _saved(bot)
    _words_on(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready_words"] + "\n\nPricing is a design decision."), _texts(bot)


def test_angles_follow_the_creators_number_and_write_up_the_one_pressed(bot, provider):
    _saved(bot)
    _words_on(bot)
    assert bot["client"].put("/api/v1/writing/preferences", json={"angles": 4}).status_code == 200
    _collect(bot)
    assert _labels(bot) == ["Write it up", "4 angles", "Remember this", "Undo"]
    bot["fake"].press_button("4 angles", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith(SAID["angles_here"])), _texts(bot)
    listed = _texts(bot)[-1]
    assert "2. Stop letting finance name it." in listed and "4. Price it like a product." in listed
    assert _labels(bot) == ["Write up 1", "Write up 2", "Write up 3", "Write up 4"]
    bot["fake"].press_button("Write up 2", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready_words"] + "\n\nPricing is a design decision.")
    assert "Stop letting finance name it." in provider.sent()


def test_with_the_words_switch_off_angles_say_only_that_they_are_ready(bot, provider):
    _saved(bot)
    _collect(bot)
    bot["fake"].press_button("3 angles", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["angles_ready"].format(count=3)), _texts(bot)
    assert "price page" not in " ".join(m["text"] for m in bot["fake"].sent)
    assert _labels(bot) == [], "angles were offered to write up without being shown"
    [item] = _items()
    assert item["angles"] and item["status"] == "new", "the studio cannot show the angles found on the bot"


def test_with_no_provider_the_press_says_so_and_writes_nothing(bot):
    _saved(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["no_provider"]]), _answers(bot)
    time.sleep(0.5)
    assert _items()[0]["status"] == "new" and _texts(bot)[-1] == SAID["collected"]


def test_a_provider_that_fails_is_said_and_nothing_changes(bot, provider):
    _saved(bot)
    provider.fail = 401
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["write_failed"]), _texts(bot)
    assert _items()[0]["status"] == "new"


def test_writing_never_holds_up_the_bot(bot, provider):
    _saved(bot)
    provider.delay = 3.0
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["writing"]])
    pressed = time.monotonic()
    bot["fake"].push(OWNER, "/status")
    assert _until(lambda: _texts(bot)[-1].startswith("Your studio is running."), timeout=2.5), (
        "a question waited on the provider")
    assert time.monotonic() - pressed < 2.5
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready"], timeout=8.0)


def test_the_words_switch_is_off_by_default(bot):
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["collection_words"] is False


# ---------------------------------------------------------------------------
# The morning idea
# ---------------------------------------------------------------------------

@pytest.fixture
def morning(notifying, monkeypatch):
    """A clock held at this weekday at 10:30, outside the default quiet hours; the best opener a question."""
    held = {"now": datetime.now().astimezone().replace(hour=10, minute=30, second=0, microsecond=0)}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: held["now"])
    import voice_pack
    monkeypatch.setattr(voice_pack, "_openers", lambda conn, limit: ["Why do we price last?"][:limit])
    return {"bot": notifying, "clock": held}


def _morning_on(bot, words=True, **change):
    now = telegram_bot.local_now()
    payload = {"morning": True, "morning_days": [now.weekday()], "morning_hour": 9}
    payload.update(change)
    if words:
        _words_on(bot)
    held, telegram_bot.local_now = telegram_bot.local_now, (lambda: now.replace(hour=6))
    try:
        res = bot["client"].post("/api/v1/ingress/options", json=payload)
    finally:
        telegram_bot.local_now = held
    assert res.status_code == 200, res.text


def _mornings(bot):
    return [t for t in _texts(bot) if t.startswith(SAID["morning"])]


def _seed(*texts, offered=None):
    import collection
    ids = [collection.add("note", text)["id"] for text in texts]
    conn = get_db()
    with conn:
        for item_id, when in (offered or {}).items():
            conn.execute("UPDATE collection_items SET offered_at = ? WHERE id = ?", (when, ids[item_id]))
    conn.close()
    return ids


def test_the_morning_idea_is_off_by_default(morning):
    bot = morning["bot"]
    _saved(bot)
    _seed("an idea waiting")
    _settle(bot)
    assert _mornings(bot) == []
    assert bot["client"].get("/api/v1/ingress/settings").json()["options"]["morning"] is False


def test_the_morning_idea_offers_the_least_recently_offered_item_with_an_angle_once_a_day(morning):
    bot = morning["bot"]
    _saved(bot)
    _seed("offered yesterday", "never offered, older", "never offered, newer",
          offered={0: "2026-10-28T08:00:00+00:00"})
    _morning_on(bot)
    assert _until(lambda: len(_mornings(bot)) == 1), _texts(bot)
    [said] = _mornings(bot)
    assert said == SAID["morning"] + "\n\nnever offered, older\n\n" + SAID["angle_question"]
    assert _labels(bot) == ["Write it up", "Not today"]
    _settle(bot)
    assert len(_mornings(bot)) == 1, "the morning idea was told twice in a day"


def test_the_morning_idea_needs_the_words_switch(morning):
    bot = morning["bot"]
    _saved(bot)
    _seed("an idea waiting")
    _morning_on(bot, words=False)
    _settle(bot)
    assert _mornings(bot) == [], "a morning idea carried words with the switch off"


def test_the_morning_idea_waits_for_quiet_hours(morning):
    bot = morning["bot"]
    _saved(bot)
    _seed("an idea waiting")
    bot["client"].post("/api/v1/ingress/options", json={"quiet_from": 10, "quiet_to": 11})
    _morning_on(bot)
    _settle(bot)
    assert _mornings(bot) == []
    morning["clock"]["now"] = morning["clock"]["now"].replace(hour=11, minute=5)
    assert _until(lambda: len(_mornings(bot)) == 1)


def test_not_today_keeps_the_item_and_write_it_up_writes_from_the_angle(morning):
    bot = morning["bot"]
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    try:
        _saved(bot)
        _seed("first idea", "second idea")
        _morning_on(bot)
        assert _until(lambda: len(_mornings(bot)) == 1)
        bot["fake"].press_button("Not today", OWNER)
        assert _until(lambda: _answers(bot) == [SAID["not_today"]])
        assert [i["status"] for i in _items()] == ["new", "new"]
        # The next day (today's told key forgotten) offers the other one, and Write it up writes from the angle.
        conn = get_db()
        with conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,))
        conn.close()
        assert _until(lambda: len(_mornings(bot)) == 2)
        assert "second idea" in _mornings(bot)[-1]
        bot["fake"].press_button("Write it up", OWNER)
        assert _until(lambda: _texts(bot)[-1].startswith(SAID["draft_ready_words"]))
        assert "open with a question" in fake.sent()
    finally:
        fake.close()


def test_the_creator_chooses_what_ideas_draw_on(morning):
    bot = morning["bot"]
    _saved(bot)
    _seed("an idea waiting")
    bot["client"].put("/api/v1/writing/preferences", json={"sources": ["collection"]})
    _morning_on(bot)
    assert _until(lambda: len(_mornings(bot)) == 1)
    assert SAID["angle_question"] not in _mornings(bot)[0], "an angle came from the posts with that source off"
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,))
    conn.close()
    bot["client"].put("/api/v1/writing/preferences", json={"sources": ["posts"]})
    _settle(bot)
    assert len(_mornings(bot)) == 1, "a morning idea came from the collection with that source off"


def test_the_morning_days_and_hour_are_the_creators(bot):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"morning_days": [5, 6], "morning_hour": 7})
    options = res.json()["options"]
    assert (options["morning"], options["morning_days"], options["morning_hour"]) == (False, [5, 6], 7)
    fresh = telegram_bot.morning()
    for wrong in ({"morning_days": [7]}, {"morning_hour": 24}, {"morning_days": []}):
        assert bot["client"].post("/api/v1/ingress/options", json=wrong).status_code in (400, 422), wrong
    assert telegram_bot.morning() == fresh, "a refused change was saved"


def test_the_defaults_a_fresh_profile_gets(bot):
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert (options["morning"], options["morning_days"], options["morning_hour"]) == (False, [0, 1, 2, 3, 4], 8)
    import writing
    assert writing.preferences()["sources"] == ["collection", "posts", "asks"]
