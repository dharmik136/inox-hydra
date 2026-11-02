"""
A guided first run on the bot: /tour (phase 5, item 1).
=======================================================

/tour walks the creator through what to try, a few steps at a time, as the
checklist (docs/help/test-your-telegram-bot.md) groups them: Next replaces
a part with the next one in the same message, Stop the tour ends it, and
the last part offers From the start. Each step says what to send and what
the creator will see, in the bot's own words; a step that writes says when
no AI provider is connected, and one whose words need the words switch says
so. It is offered once after pairing (the "Paired." message carries Start
the tour) and once after an upgrade that adds commands (a notice, told once
outside quiet hours). The panel lists the steps seen working, derived from
what the studio holds, never from a press. Nothing of the creator's words
goes in it. The menu's record and the notice are kept only for the bot they
were made for: a bot removed while Telegram is still answering keeps neither.

docs/quality/cycle4/bot-phase5.md, item 1. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import json
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
from test_telegram_bot_e2e import OWNER, TOKEN, _save, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


@pytest.fixture
def touring(bot, monkeypatch):
    """The worker looks for something to tell at every turn, and the bot's clock reads midday (quiet hours aside)."""
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    midday = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(telegram_bot, "local_now", lambda: midday)
    return bot


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": "Pricing is a design decision.\n\nWrite the price page first."}
    yield fake
    fake.close()


def _parts():
    return len(telegram_bot.TOUR_PARTS)


def _tour_message(bot):
    """The newest message the bot sent that is a part of the tour, as the phone shows it now."""
    for sent in reversed(bot["fake"].sent):
        if str(sent["text"] or "").startswith("Tour, part 1 of"):
            return sent["message_id"]
    return None


def _shown(bot, message_id):
    return str(bot["fake"].message(message_id).get("text") or "")


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _started(bot):
    bot["fake"].push(OWNER, "/tour")
    assert _until(lambda: _tour_message(bot) is not None), _texts(bot)
    return _tour_message(bot)


def _write(key, value):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.close()


def _setting(key):
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _seen(bot):
    return {step["key"]: step["seen"] for step in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}


def test_tour_walks_the_parts_in_one_message_with_next_and_from_the_start(bot):
    _saved(bot)
    message = _started(bot)
    assert _shown(bot, message) == telegram_bot.tour_part_text(0)
    assert _labels(bot, message) == ["Next", "Stop the tour"]
    for part in range(1, _parts()):
        bot["fake"].press_button("Next", OWNER, message_id=message)
        assert _until(lambda: _shown(bot, message).startswith(f"Tour, part {part + 1} of {_parts()}")), _shown(bot, message)
        assert _shown(bot, message) == telegram_bot.tour_part_text(part)
    assert _labels(bot, message) == ["From the start"]
    assert "Send /tour to see it again" in _shown(bot, message)
    bot["fake"].press_button("From the start", OWNER, message_id=message)
    assert _until(lambda: _shown(bot, message) == telegram_bot.tour_part_text(0))
    assert _labels(bot, message) == ["Next", "Stop the tour"]
    # A part replaces the one before it: one message, edited, never a new one each time.
    assert len([m for m in bot["fake"].sent if str(m["text"] or "").startswith("Tour, part")]) == 1


def test_stop_the_tour_ends_it(bot):
    _saved(bot)
    message = _started(bot)
    bot["fake"].press_button("Stop the tour", OWNER, message_id=message)
    assert _until(lambda: _shown(bot, message) == telegram_bot.TOUR_STOPPED)
    assert _labels(bot, message) == []


def test_each_step_says_what_to_send_and_what_you_will_see_in_the_bots_own_words():
    every = "\n".join(telegram_bot.tour_part_text(n) for n in range(_parts()))
    for key in ("collected", "writing", "draft_ready", "added", "edited"):
        assert SAID[key] in every, key
    assert "Idea: testing the bot" in every and "/write" in every and "/remember" in every
    # Numbered across the parts, so a step can be named.
    assert "\n1. " in telegram_bot.tour_part_text(0) and "\n4. " in telegram_bot.tour_part_text(1)


def test_a_step_that_writes_says_when_no_provider_is_connected(bot):
    second = telegram_bot.tour_part_text(1)
    assert telegram_bot.TOUR_NEEDS_PROVIDER in second
    assert "Composer's Prompt tab" in telegram_bot.TOUR_NEEDS_PROVIDER
    assert telegram_bot.TOUR_NEEDS_PROVIDER not in telegram_bot.tour_part_text(0)
    fake = FakeProvider()
    fake.connect()
    try:
        assert telegram_bot.TOUR_NEEDS_PROVIDER not in telegram_bot.tour_part_text(1)
    finally:
        fake.close()


def test_a_step_whose_words_need_the_words_switch_says_so(bot):
    _save(bot)
    assert telegram_bot.TOUR_NEEDS_WORDS in telegram_bot.tour_part_text(1)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    assert telegram_bot.TOUR_NEEDS_WORDS not in telegram_bot.tour_part_text(1)


def test_seen_working_is_derived_from_what_the_studio_holds_never_from_a_press(bot, provider):
    _saved(bot)
    assert not any(_seen(bot).values()), _seen(bot)
    bot["fake"].push(OWNER, "Idea: pricing is a design decision")
    assert _until(lambda: _seen(bot)["saved"]), _seen(bot)
    assert telegram_bot.TOUR_SEEN in telegram_bot.tour_part_text(0)
    # A press alone marks nothing: Next is pressed, nothing is written.
    message = _started(bot)
    bot["fake"].press_button("Next", OWNER, message_id=message)
    assert _until(lambda: _shown(bot, message).startswith("Tour, part 2"))
    assert _seen(bot)["written"] is False
    # Written up from the phone: the draft records that it was asked for there.
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: SAID["draft_ready"] in _texts(bot)), _texts(bot)
    assert _until(lambda: _seen(bot)["written"]), _seen(bot)
    conn = get_db()
    made = [json.loads(r[0]) for r in conn.execute("SELECT made_with FROM posts WHERE made_with IS NOT NULL")]
    conn.close()
    assert [m.get("via") for m in made] == ["telegram"]


def test_one_draft_from_several_counts_only_when_the_phone_asked_for_it(bot, provider):
    _saved(bot)
    for words in ("Idea: pricing one", "Idea: pricing two"):
        bot["fake"].push(OWNER, words)
    assert _until(lambda: len(bot["client"].get("/api/v1/collection").json()["items"]) == 2)
    # Combined at the desk: a draft from several items, and not the phone's.
    ids = [item["id"] for item in bot["client"].get("/api/v1/collection").json()["items"]]
    assert bot["client"].post("/api/v1/collection/write", json={"items": ids}).status_code == 200
    assert _seen(bot)["several"] is False and _seen(bot)["written"] is False
    for words in ("Idea: pricing three", "Idea: pricing four"):
        bot["fake"].push(OWNER, words)
    assert _until(lambda: len(bot["client"].get("/api/v1/collection").json()["items"]) == 2)
    bot["fake"].push(OWNER, "/write pricing")
    assert _until(lambda: _seen(bot)["several"]), _texts(bot)


def test_what_the_panel_lists_each_with_its_title(bot):
    _saved(bot)
    listed = bot["client"].get("/api/v1/ingress/settings").json()["tour"]
    assert [step["key"] for step in listed] == list(telegram_bot.TOUR_EVIDENCE)
    assert all(step["title"] and step["seen"] is False for step in listed)


def test_pairing_offers_the_tour_once_on_the_paired_message(bot):
    _saved(bot)
    paired = [m for m in bot["fake"].sent if m["text"] == SAID["paired"]]
    assert len(paired) == 1 and "Start the tour" in SAID["paired"]
    assert _labels(bot, paired[0]["message_id"]) == ["Start the tour"]
    bot["fake"].press_button("Start the tour", OWNER, message_id=paired[0]["message_id"])
    assert _until(lambda: _tour_message(bot) is not None), _texts(bot)
    assert _shown(bot, _tour_message(bot)) == telegram_bot.tour_part_text(0)
    assert _until(lambda: _shown(bot, paired[0]["message_id"]).endswith(SAID["tour_started"]))
    assert _labels(bot, paired[0]["message_id"]) == []


def _menu_of_2_13(chat):
    """The menu's record as 2.13.0 kept it once Telegram took its list: a fingerprint, the chat, when."""
    held = json.dumps({"chat": str(chat), "commands": [list(c) for c in telegram_bot.COMMANDS_2_13]}, sort_keys=True)
    import hashlib
    return {"fingerprint": hashlib.sha256(held.encode("utf-8")).hexdigest()[:24], "chat": str(chat),
            "at": "2026-10-30T12:00:00+00:00"}


def _added():
    before = {name for name, _words in telegram_bot.COMMANDS_2_13}
    return [name for name, _words in telegram_bot.BOT_COMMANDS if name not in before]


def test_an_upgrade_that_adds_commands_offers_the_tour_once(touring):
    bot = touring
    _write(telegram_bot.MENU_KEY, json.dumps(_menu_of_2_13(OWNER)))
    _saved(bot)
    notice = telegram_bot.tour_notice_text(_added())
    assert _until(lambda: notice in _texts(bot)), _texts(bot)
    for name in _added():
        assert f"/{name}" in notice
    sent = [m for m in bot["fake"].sent if m["text"] == notice]
    assert _labels(bot, sent[0]["message_id"]) == ["Start the tour"]
    # The menu now lists every command, and its record names them.
    assert _until(lambda: [c["command"] for c in bot["fake"].menu(OWNER)] == [n for n, _w in telegram_bot.BOT_COMMANDS])
    assert json.loads(_setting(telegram_bot.MENU_KEY))["names"] == [n for n, _w in telegram_bot.BOT_COMMANDS]
    # Told once: later turns of the loop and a restart tell nothing more.
    time.sleep(1.0)
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": TOKEN, "chat_id": OWNER})
    time.sleep(1.0)
    assert _texts(bot).count(notice) == 1


def test_the_upgrade_notice_waits_for_quiet_hours(bot, monkeypatch):
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    night = datetime.now().astimezone().replace(hour=2, minute=0, second=0, microsecond=0)
    clock = {"now": night}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: clock["now"])
    _write(telegram_bot.MENU_KEY, json.dumps(_menu_of_2_13(OWNER)))
    _saved(bot)
    assert _until(lambda: json.loads(_setting(telegram_bot.MENU_KEY) or "{}").get("names"))
    time.sleep(1.0)
    notice = telegram_bot.tour_notice_text(_added())
    assert notice not in _texts(bot)
    clock["now"] = night.replace(hour=12)
    assert _until(lambda: notice in _texts(bot)), _texts(bot)


def test_a_menu_nothing_recognises_and_a_first_pairing_offer_no_notice(touring):
    bot = touring
    _write(telegram_bot.MENU_KEY, json.dumps({"fingerprint": "0" * 24, "chat": OWNER, "at": "2026-10-01T00:00:00+00:00"}))
    _saved(bot)
    assert _until(lambda: json.loads(_setting(telegram_bot.MENU_KEY) or "{}").get("names"))
    time.sleep(1.0)
    assert _texts(bot) == [], _texts(bot)
    assert _setting(telegram_bot.TOUR_KEY) is None


def test_a_bot_removed_while_telegram_takes_its_menu_keeps_no_record_of_it(touring):
    """The worker stops before the rows go: a registration ending during the stop keeps nothing."""
    bot = touring
    _write(telegram_bot.MENU_KEY, json.dumps(_menu_of_2_13(OWNER)))
    bot["fake"].plan("setMyCommands", ("hold", 0.8))
    _saved(bot)
    assert _until(lambda: bot["fake"].calls_of("setMyCommands")), "the menu was never registered"
    assert bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""}).status_code == 200
    time.sleep(1.5)
    assert _setting(telegram_bot.MENU_KEY) is None
    assert _setting(telegram_bot.TOUR_KEY) is None


def test_a_registration_outliving_the_stop_keeps_nothing_for_a_bot_that_is_gone(touring, monkeypatch):
    """The stop gave up waiting: the record is kept only for the bot it was made with, under the check lock."""
    bot = touring
    monkeypatch.setattr(bot["daemon"], "STOP_JOIN_SECONDS", 0.1)
    _write(telegram_bot.MENU_KEY, json.dumps(_menu_of_2_13(OWNER)))
    bot["fake"].plan("setMyCommands", ("hold", 1.5))
    _saved(bot)
    assert _until(lambda: bot["fake"].calls_of("setMyCommands")), "the menu was never registered"
    assert bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""}).status_code == 200
    time.sleep(2.5)
    assert _setting(telegram_bot.MENU_KEY) is None
    assert _setting(telegram_bot.TOUR_KEY) is None


def test_the_notice_goes_with_the_bot_and_with_everything(bot):
    import onboarding
    _save(bot)
    _write(telegram_bot.TOUR_KEY, json.dumps({"chat": OWNER, "added": ["tour"], "bot": "waiting"}))
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    assert _setting(telegram_bot.TOUR_KEY) is None
    _write(telegram_bot.TOUR_KEY, json.dumps({"chat": OWNER, "added": ["tour"], "bot": "waiting"}))
    conn = get_db()
    with conn:
        onboarding.forget_phone_and_export(conn)
    conn.close()
    assert _setting(telegram_bot.TOUR_KEY) is None


def test_nothing_of_the_creators_words_is_in_the_tour(bot):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    bot["fake"].push(OWNER, "Idea: my secret pricing thought")
    assert _until(lambda: _seen(bot)["saved"])
    every = "\n".join(telegram_bot.tour_part_text(n) for n in range(_parts()))
    assert "secret pricing" not in every


def test_tour_is_in_the_menu_and_help_and_answered_with_the_confirmations_off(bot):
    assert "tour" in [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "- /tour: " in telegram_bot.HELP
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    assert _started(bot)
