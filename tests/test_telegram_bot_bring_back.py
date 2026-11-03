"""
Bring back an unused idea (phase 6, item 2).
============================================

Off by default. On the days and at the hour the creator picks, between
polls, the bot brings back one unused item with words older than the
creator's age: the oldest; never one set aside, already used, or with a
reminder waiting; never the one it brought back last time, nor the one the
morning idea offered last. Its first line only with the words switch on;
otherwise only its kind and its age. Under it, Write it up, Remind me and Not
now. Told once a day it is due, held by quiet hours, kept only for the bot it
was made with; the panel says when the next one comes.

docs/quality/cycle4/bot-phase6.md, item 2. Against the fake Bot API. The
bot's clock is held at midday before the worker starts and never moved while
it runs: a setting's "since" is written on its row, as the morning idea's
tests do.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _save, _until, bot  # noqa: E402,F401
from test_telegram_bot_notifications import _settle  # noqa: E402
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
HEAD = "Back from your collection: "


@pytest.fixture
def bringing(bot, monkeypatch):
    """The worker tells at every turn, and the bot's clock reads midday today, held, before the worker starts."""
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    midday = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(telegram_bot, "local_now", lambda: midday)
    bot["now"] = midday
    return bot


def _seed(*entries):
    """Items of so many days ago: (days, words) or (days, words, status), each a note."""
    import collection
    ids = []
    for entry in entries:
        days, words = entry[0], entry[1]
        status = entry[2] if len(entry) > 2 else "new"
        ids.append(collection.add("note", words, status=status, source="studio")["id"])
        conn = get_db()
        with conn:
            conn.execute("UPDATE collection_items SET received_at = ? WHERE id = ?",
                         ((datetime.now(timezone.utc) - timedelta(days=days)).isoformat(), ids[-1]))
        conn.close()
    return ids


def _back_on(bot, **change):
    """Turned on for today at 09:00, before midday, as if saved at 06:00: the setting's since written on its row."""
    payload = {"back": True, "back_days": [bot["now"].weekday()], "back_hour": 9}
    payload.update(change)
    res = bot["client"].post("/api/v1/ingress/options", json=payload)
    assert res.status_code == 200, res.text
    conn = get_db()
    try:
        with conn:
            held = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?",
                                           (telegram_bot.BACK_KEY,)).fetchone()["value"])
            held["since"] = bot["now"].replace(hour=6).astimezone(timezone.utc).isoformat()
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps(held), telegram_bot.BACK_KEY))
    finally:
        conn.close()


def _backs(bot):
    return [m for m in bot["fake"].sent if str(m["text"] or "").startswith(HEAD)]


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _notices(bot):
    return [a["text"] for a in bot["fake"].answered]


def _status(item_id):
    conn = get_db()
    try:
        return conn.execute("SELECT status FROM collection_items WHERE id = ?", (item_id,)).fetchone()[0]
    finally:
        conn.close()


def _forget_today():
    """The next day, as far as what was told goes."""
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,))
    conn.close()


def _said_for(item_id):
    import collection
    conn = get_db()
    try:
        item = collection.get(conn, item_id)
    finally:
        conn.close()
    return telegram_bot.back_line(item)


def test_it_is_off_by_default(bringing):
    bot = bringing
    _saved(bot)
    _seed((30, "pricing is a design decision"))
    _settle(bot)
    assert _backs(bot) == []
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["back"] is False and options["back_days"] == [4] and options["back_hour"] == 16
    assert options["back_older"] == 14
    assert options["defaults"]["back"] == {"on": False, "days": [4], "hour": 16, "older": 14}


def test_it_brings_back_the_oldest_unused_item_older_than_the_age_once_a_day(bringing):
    bot = bringing
    _saved(bot)
    import phone_reminders
    ids = _seed((40, "used long ago", "used"), (30, "set aside", "not_now"), (25, "waiting for its reminder"),
                (20, "pricing is a design decision"), (19, "the price page is a brief"), (5, "too young"))
    assert phone_reminders.add(ids[2], (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                               "Tomorrow morning")["status"] == "kept"
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    [back] = _backs(bot)
    assert back["text"] == _said_for(ids[3]), back["text"]
    assert back["text"].startswith(HEAD + "a note you saved 20 days ago, on ")
    assert "pricing" not in back["text"], "its words went with the words switch off"
    assert _labels(bot, back["message_id"]) == ["Write it up", "Remind me", "Not now"]
    _settle(bot)
    assert len(_backs(bot)) == 1, "it was brought back twice in a day"


def test_with_the_words_on_its_first_line_comes_too(bringing):
    bot = bringing
    _saved(bot)
    assert bot["client"].post("/api/v1/ingress/options", json={"collection_words": True}).status_code == 200
    ids = _seed((20, "pricing is a design decision\nsecond line"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    assert _backs(bot)[0]["text"] == _said_for(ids[0]) + "\n\npricing is a design decision"


def test_never_the_one_it_brought_back_last_time(bringing):
    bot = bringing
    _saved(bot)
    ids = _seed((20, "the oldest"), (19, "the next"), (2, "offered by the morning idea"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    assert "the oldest" not in _backs(bot)[0]["text"] and _backs(bot)[0]["text"] == _said_for(ids[0])
    # The morning idea offers another item meanwhile: the bot's last offer is no longer the one brought back.
    import collection
    conn = get_db()
    collection.offered(conn, ids[2])
    conn.close()
    _forget_today()
    assert _until(lambda: len(_backs(bot)) == 2), _texts(bot)
    assert _backs(bot)[1]["text"] == _said_for(ids[1])
    _forget_today()
    assert _until(lambda: len(_backs(bot)) == 3), _texts(bot)
    assert _backs(bot)[2]["text"] == _said_for(ids[0])


def test_nor_the_one_the_morning_idea_offered_last(bringing):
    bot = bringing
    _saved(bot)
    ids = _seed((20, "the oldest"), (19, "the next"))
    import collection
    conn = get_db()
    collection.offered(conn, ids[0])
    conn.close()
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    assert _backs(bot)[0]["text"] == _said_for(ids[1])


def test_the_age_is_the_creators(bringing):
    bot = bringing
    _saved(bot)
    ids = _seed((10, "ten days old"))
    _back_on(bot)
    _settle(bot)
    assert _backs(bot) == [], "an item younger than the age came back"
    _forget_today()
    _back_on(bot, back_older=7)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    assert _backs(bot)[0]["text"] == _said_for(ids[0])


def test_a_day_with_nothing_to_bring_back_is_marked_told(bringing):
    bot = bringing
    _saved(bot)
    _back_on(bot)
    _settle(bot)

    def told():
        conn = get_db()
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,)).fetchone()
            return json.loads(row[0]) if row else []
        finally:
            conn.close()
    assert _until(lambda: f"back:{bot['now'].date().isoformat()}" in told()), told()
    _seed((20, "arrived late"))
    _settle(bot)
    assert _backs(bot) == [], "something came later the same day"


def test_quiet_hours_hold_it_until_they_end(bringing):
    bot = bringing
    _saved(bot)
    _seed((20, "pricing is a design decision"))
    assert bot["client"].post("/api/v1/ingress/options", json={"quiet_from": 11, "quiet_to": 13}).status_code == 200
    _back_on(bot)
    _settle(bot)
    assert _backs(bot) == []
    # Quiet hours changed, not the clock: the worker reads midday all along.
    assert bot["client"].post("/api/v1/ingress/options", json={"quiet_from": 14, "quiet_to": 15}).status_code == 200
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)


def test_not_now_sets_it_aside_and_remind_me_offers_the_moments(bringing):
    bot = bringing
    _saved(bot)
    ids = _seed((20, "pricing is a design decision"), (19, "the price page is a brief"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    first = _backs(bot)[0]["message_id"]
    bot["fake"].press_button("Not now", OWNER, message_id=first)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["set_aside"]]), _notices(bot)
    assert _status(ids[0]) == "not_now"
    _forget_today()
    assert _until(lambda: len(_backs(bot)) == 2), _texts(bot)
    second = _backs(bot)[1]["message_id"]
    bot["fake"].press_button("Remind me", OWNER, message_id=second)
    assert _until(lambda: _notices(bot)[-1:] == [SAID["remind_pick"]]), _notices(bot)
    assert _until(lambda: SAID["remind_ask"] in _texts(bot)), _texts(bot)
    assert "Remind me" in _labels(bot, second), "Remind me did not stay on its message"


def test_write_it_up_writes_it(bringing):
    bot = bringing
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": "Pricing is a design decision.\n\nWrite the price page first."}
    try:
        _saved(bot)
        ids = _seed((20, "pricing is a design decision"))
        _back_on(bot)
        assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
        bot["fake"].press_button("Write it up", OWNER, message_id=_backs(bot)[0]["message_id"])
        assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)
        assert "pricing is a design decision" in fake.sent()
        assert _status(ids[0]) == "used"
    finally:
        fake.close()


def test_a_reply_to_it_adds_to_the_item(bringing):
    bot = bringing
    _saved(bot)
    ids = _seed((20, "pricing is a design decision"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    bot["fake"].push(OWNER, "and the price page is the brief",
                     reply_to_message={"message_id": _backs(bot)[0]["message_id"], "chat": {"id": int(OWNER)}})
    assert _until(lambda: SAID["added"] in _texts(bot)), _texts(bot)
    conn = get_db()
    try:
        text = conn.execute("SELECT text FROM collection_items WHERE id = ?", (ids[0],)).fetchone()[0]
    finally:
        conn.close()
    assert text == "pricing is a design decision\n\nand the price page is the brief"


def test_the_panel_says_when_the_next_one_comes_and_wrong_values_are_refused(bringing):
    bot = bringing
    _saved(bot)
    assert bot["client"].get("/api/v1/ingress/settings").json()["back_next"] is None
    today = bot["now"].weekday()
    res = bot["client"].post("/api/v1/ingress/options", json={"back": True, "back_days": [today], "back_hour": 16,
                                                              "back_older": 30})
    assert res.status_code == 200, res.text
    expected = bot["now"].replace(hour=16).strftime("%a %d %b, %H:%M")
    assert res.json()["back_next"] == expected
    options = res.json()["options"]
    assert options["back"] is True and options["back_days"] == [today] and options["back_older"] == 30
    for wrong in ({"back_older": 5}, {"back_days": []}, {"back_days": [7]}, {"back_hour": 24}):
        assert bot["client"].post("/api/v1/ingress/options", json=wrong).status_code in (400, 422), wrong
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["back_older"] == 30 and options["back_days"] == [today] and options["back_hour"] == 16


def test_what_it_keeps_goes_with_the_bot_and_with_everything(bringing):
    bot = bringing
    _saved(bot)
    _seed((20, "pricing is a design decision"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)

    def kept():
        conn = get_db()
        try:
            return conn.execute("SELECT value FROM settings WHERE key = ?", (telegram_bot.BROUGHT_BACK_KEY,)).fetchone()
        finally:
            conn.close()
    assert _until(lambda: kept() is not None)
    assert bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""}).status_code == 200
    assert kept() is None
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, '{}', CURRENT_TIMESTAMP)",
                     (telegram_bot.BROUGHT_BACK_KEY,))
    conn.close()
    import onboarding
    conn = get_db()
    with conn:
        onboarding.forget_phone_and_export(conn)
    conn.close()
    assert kept() is None


def test_a_bot_removed_while_it_is_told_keeps_nothing(bringing, monkeypatch):
    """The record of what it brought back is written under the worker's check lock, for the bot it was made with."""
    bot = bringing
    _saved(bot)
    _seed((20, "pricing is a design decision"))
    real = telegram_bot.notifications
    gate = {"held": False}

    def slow():
        said = real()
        if any("back" in item for item in said):
            gate["held"] = True
            time.sleep(0.8)
        return said
    monkeypatch.setattr(telegram_bot, "notifications", slow)
    _back_on(bot)
    assert _until(lambda: gate["held"])
    assert bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""}).status_code == 200
    time.sleep(1.2)
    conn = get_db()
    try:
        assert conn.execute("SELECT 1 FROM settings WHERE key = ?", (telegram_bot.BROUGHT_BACK_KEY,)).fetchone() is None
    finally:
        conn.close()


def test_it_is_in_the_tour_with_the_morning_idea_and_the_panel_lists_it_once_seen(bringing):
    bot = bringing
    _saved(bot)
    keys = [key for _title, steps in telegram_bot.TOUR_PARTS for key in steps]
    assert "back" in keys and "morning" in keys
    assert "Bring back an unused idea" in telegram_bot.TOUR_STEPS["back"]["say"]

    def seen():
        return {s["key"]: s["seen"] for s in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}
    assert seen()["back"] is False and "morning" not in seen()
    _seed((20, "pricing is a design decision"))
    _back_on(bot)
    assert _until(lambda: len(_backs(bot)) == 1), _texts(bot)
    assert _until(lambda: seen()["back"]), seen()
