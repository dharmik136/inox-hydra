"""
Notifications, each opt-in on its own, none by default.
=======================================================

Two, each with its own switch in the Telegram panel:

  a queued post is due now           a count, never the post's words
  your latest post at about 24 hours  that reading's own figures, where it
                                       was read: counts only

Each is said once: what was told is kept in the bot's profile, so a restart
does not tell it again. Never a person's name, never a comment. The worker
checks between polls; here it is driven end to end against the fake Bot API
(tests/telegram_fake.py), with its check made immediate.

Strict Invariants:
- Zero em-dashes.
"""

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
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_figures import _record, _stamp  # noqa: E402
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


@pytest.fixture
def notifying(bot, monkeypatch):
    """
    The worker checks for something to tell at every turn of its loop, rather
    than once a minute, and the bot's clock reads midday: quiet hours (phase
    2) are on by default from 23:00 to 07:00, and would hold these
    notifications whenever the suite runs at night. A test of quiet hours
    sets the clock itself.
    """
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    midday = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(telegram_bot, "local_now", lambda: midday)
    return bot


def _due(post_id="due-1", minutes_ago=5):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for, created_at) "
                     "VALUES (?, 'My queued words', 'due', ?, ?)",
                     (post_id, _stamp(minutes_ago / 60.0), _stamp(2)))
    conn.close()


def _reading_at_24_hours(urn):
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions, reactions, comments, precision) VALUES (?, ?, 'probe-24h', 24.2, 'post_analytics', "
            "880, 31, 4, 'exact')", (urn, _stamp(23.8)))
    conn.close()


def _settle(bot, seconds=1.0):
    """A few turns of the worker's loop."""
    polls = len(bot["fake"].calls_of("getUpdates"))
    assert _until(lambda: len(bot["fake"].calls_of("getUpdates")) >= polls + 3, timeout=seconds + 5)


def test_none_is_on_by_default_and_nothing_is_said(notifying):
    bot = notifying
    _saved(bot)
    latest = _record(latest_days=1.0, read_hours_ago=1)
    _reading_at_24_hours(latest)
    _due()
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["notify_due"] is False and options["notify_24h"] is False
    _settle(bot)
    assert _texts(bot) == []


def test_a_due_post_is_said_once_as_a_count(notifying):
    bot = notifying
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), _texts(bot)
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]], "the same due post was told twice"
    _due("due-2"), _due("due-3")
    assert _until(lambda: len(_texts(bot)) == 2)
    assert _texts(bot)[1] == SAID["due_many"].format(count=2)
    assert "queued words" not in " ".join(_texts(bot))


def test_the_latest_posts_reading_at_about_24_hours_is_said_once_with_its_own_figures(notifying):
    bot = notifying
    _saved(bot)
    latest = _record(latest_days=1.1, read_hours_ago=1)
    bot["client"].post("/api/v1/ingress/options", json={"notify_24h": True})
    _reading_at_24_hours(latest)
    assert _until(lambda: len(_texts(bot)) == 1), _texts(bot)
    [told] = _texts(bot)
    assert told == ("Your latest post at about 24 hours: 880 impressions, 31 reactions, 4 comments, "
                    "read on its analytics page.")
    for private in ("Jane", "Stranger", "thoughtful", "pricing"):
        assert private not in told
    _settle(bot)
    assert len(_texts(bot)) == 1, "the 24 hour reading was told twice"


def test_each_notification_has_its_own_switch(notifying):
    bot = notifying
    _saved(bot)
    latest = _record(latest_days=1.1, read_hours_ago=1)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _reading_at_24_hours(latest)
    _due()
    assert _until(lambda: len(_texts(bot)) >= 1)
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]], "a notification that was not turned on was sent"


def test_what_was_told_is_kept_so_a_restart_does_not_tell_it_again(notifying):
    bot = notifying
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]])
    # The studio stops and starts again: the worker is started anew.
    bot["daemon"].stop_worker()
    bot["daemon"]._thread.join(3)
    bot["daemon"].start_worker()
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]]


def test_the_panel_and_the_help_name_both_switches():
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    assert "notify_due" in panel and "notify_24h" in panel
    article = " ".join(open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"),
                            encoding="utf-8").read().split())
    assert "Tell me when a queued post is due" in article and "Send my latest post's figures at about 24 hours" in article


def test_deleting_everything_forgets_what_the_bot_has_told(notifying):
    """What was told names the creator's posts, so it goes with everything else the studio holds about them."""
    bot = notifying
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]])
    import onboarding
    onboarding.forget_identity()
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,)).fetchone()[0] == 0
    finally:
        conn.close()
