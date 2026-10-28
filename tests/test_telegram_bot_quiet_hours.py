"""
Quiet hours: the bot's notifications wait, and go when they end.
================================================================

The opt-in notifications (a queued post due, the 24 hour figures, a reminder
asked for with Remind me in an hour, and the weekly summary) wait while quiet
hours are on, and go when they end, each still told once. Default 23:00 to
07:00 on the computer's own clock, changed in the Telegram panel, and can be
turned off. Answers to the creator's own messages, commands and button
presses are never held.

Kept separate from the poller's night pace (ingress.is_quiet_hours, 23:00 to
06:00, fixed): that changes only how often the studio asks Telegram for
messages, never what the bot holds back, and quiet hours never change it.

Driven end to end against the fake Bot API (tests/telegram_fake.py), with the
computer's clock as the bot reads it (telegram_bot.local_now) set by the test.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
from datetime import datetime

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from test_telegram_bot_e2e import OWNER, _collected, _until, bot  # noqa: E402,F401
from test_telegram_bot_figures import _record  # noqa: E402
from test_telegram_bot_notifications import _due, _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _at(hour, minute=0):
    """Today at this hour on the computer's clock."""
    return datetime.now().astimezone().replace(hour=hour, minute=minute, second=0, microsecond=0)


@pytest.fixture
def clock(monkeypatch):
    """The computer's clock as the bot reads it; a test moves it."""
    held = {"now": _at(12)}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: held["now"])

    def move(hour, minute=0):
        held["now"] = _at(hour, minute)
    return move


def _options(bot):
    return bot["client"].get("/api/v1/ingress/settings").json()["options"]


def _due_on(bot):
    _saved(bot)
    _record(latest_days=5)
    res = bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    assert res.status_code == 200, res.text


def test_quiet_hours_are_on_by_default_from_23_to_7(bot):
    _saved(bot)
    options = _options(bot)
    assert (options["quiet_hours"], options["quiet_from"], options["quiet_to"]) == (True, 23, 7)


def test_a_notification_waits_through_quiet_hours_and_goes_once_when_they_end(notifying, clock):
    bot = notifying
    clock(2)
    _due_on(bot)
    _due()
    _settle(bot)
    _settle(bot)
    assert _texts(bot) == [], "a notification went during quiet hours"
    assert bot["client"].get("/api/v1/ingress/settings").json()["quiet_now"] is True
    clock(6, 59)
    _settle(bot)
    assert _texts(bot) == []
    clock(7)
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), _texts(bot)
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]], "a notification held through the night was told twice"
    assert bot["client"].get("/api/v1/ingress/settings").json()["quiet_now"] is False


def test_answers_to_the_creators_own_messages_commands_and_presses_are_never_held(notifying, clock):
    bot = notifying
    clock(3)
    _due_on(bot)
    bot["fake"].push(OWNER, "Idea: a thought at three in the morning")
    bot["fake"].push(OWNER, "/status")
    assert _until(lambda: len(_texts(bot)) == 2), _texts(bot)
    assert _texts(bot)[0] == SAID["collected"] and _texts(bot)[1].startswith("Your studio is running.")
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["undone_item"]])
    assert _collected() == []


def test_with_quiet_hours_off_nothing_waits(notifying, clock):
    bot = notifying
    clock(2)
    _due_on(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"quiet_hours": False})
    assert res.status_code == 200 and res.json()["options"]["quiet_hours"] is False
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), _texts(bot)


def test_quiet_hours_can_be_changed(notifying, clock):
    bot = notifying
    _due_on(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"quiet_from": 22, "quiet_to": 6})
    assert res.status_code == 200, res.text
    assert (res.json()["options"]["quiet_from"], res.json()["options"]["quiet_to"]) == (22, 6)
    clock(22, 30)
    _due()
    _settle(bot)
    assert _texts(bot) == [], "a notification went inside the changed quiet hours"
    clock(6, 30)
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), "the changed quiet hours held on past their end"


def test_a_reminder_waits_for_quiet_hours_too(notifying, clock, monkeypatch):
    bot = notifying
    monkeypatch.setattr(telegram_bot, "REMIND_AFTER_SECONDS", 0.3)
    clock(22, 50)
    _due_on(bot)
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]])
    bot["fake"].press_button("Remind me in an hour", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["remind_set"]])
    clock(23, 50)
    _settle(bot)
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]], "a reminder went during quiet hours"
    clock(7, 5)
    assert _until(lambda: _texts(bot) == [SAID["due_one"], SAID["due_again_one"]]), _texts(bot)


@pytest.mark.parametrize("payload", [{"quiet_from": 5, "quiet_to": 5}, {"quiet_from": 7}])
def test_quiet_hours_need_a_start_and_an_end_that_differ(bot, payload):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/options", json=payload)
    assert res.status_code == 400 and "differ" in res.json()["detail"], res.text
    options = _options(bot)
    assert (options["quiet_from"], options["quiet_to"]) == (23, 7), "a refused change was saved"


@pytest.mark.parametrize("start, end, hour, minute, quiet", [
    (23, 7, 23, 0, True), (23, 7, 2, 0, True), (23, 7, 6, 59, True), (23, 7, 7, 0, False), (23, 7, 22, 59, False),
    (1, 5, 0, 30, False), (1, 5, 1, 0, True), (1, 5, 4, 59, True), (1, 5, 5, 0, False),
])
def test_the_window_runs_from_its_start_to_its_end_across_midnight(bot, start, end, hour, minute, quiet):
    bot["client"].post("/api/v1/ingress/options", json={"quiet_from": start, "quiet_to": end})
    assert telegram_bot.in_quiet_hours(_at(hour, minute)) is quiet


def test_the_pollers_night_pace_is_separate_from_quiet_hours(bot, monkeypatch):
    """
    The poller asks Telegram less often between 23:00 and 06:00, whatever
    quiet hours say; quiet hours hold only notifications. Turning quiet hours
    off, or moving them, never changes how often the studio asks.
    """
    import ingress
    daemon = ingress.TelegramIngressDaemon(bot_token="", authorized_chat_id="")
    night, day = _at(2), _at(12)
    for change in ({"quiet_hours": False}, {"quiet_hours": True, "quiet_from": 12, "quiet_to": 13}):
        bot["client"].post("/api/v1/ingress/options", json=change)
        assert daemon.calculate_next_poll_interval(current_time=night) == daemon.quiet_delay
        assert daemon.calculate_next_poll_interval(current_time=day) == daemon.base_delay
    assert telegram_bot.in_quiet_hours(_at(12, 30)) is True and daemon.is_quiet_hours(_at(12, 30)) is False


def test_the_help_and_the_policy_say_quiet_hours_hold_only_notifications():
    article = " ".join(open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"),
                            encoding="utf-8").read().split())
    policy = " ".join(open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read().split())
    assert "Hold notifications during quiet hours" in article and "23:00 to 07:00" in article
    assert "never held" in article and "asks Telegram less often" in article
    assert "quiet hours" in policy
