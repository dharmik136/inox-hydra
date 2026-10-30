"""
Nothing lost silently while the computer is off (phase 4, item 2).
===================================================================

Telegram keeps a bot's incoming messages for at most 24 hours ("they will not
be kept longer than 24 hours", the Bot API's getUpdates), so anything sent
while the studio has not checked for longer may never arrive. The studio
keeps the time of its last successful check in the bot's profile, so it
survives a restart, and when it checks again more than a day later it says
so once, on the bot and in the Telegram panel: when nothing was checked, and
that anything sent before a moment 24 hours ago may not have arrived. It
never says a message was lost, and never gives a count. The bot's message
waits for quiet hours, as the notifications do; the panel shows it at once.

docs/quality/cycle4/bot-phase4.md, item 2. Driven end to end against the
fake Bot API (tests/telegram_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import ingress  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, TOKEN, _until, bot  # noqa: E402,F401
from test_telegram_bot_notifications import _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

CHECKED = getattr(telegram_bot, "CHECKED_KEY", "telegram_checked_at")
GAP = getattr(telegram_bot, "GAP_KEY", "telegram_gap")


def _setting(key):
    conn = get_db()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    finally:
        conn.close()


def _write(key, value):
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
    conn.close()


def _restart(bot, last_check):
    """The studio stopped, its last check kept at `last_check`, and started again."""
    daemon = bot["daemon"]
    daemon.stop_worker()
    if daemon._thread is not None:
        daemon._thread.join(3)
    _write(CHECKED, last_check.isoformat())
    daemon.last_ok_at = None
    daemon.is_running = False
    ingress.apply_settings(at_startup=True)
    assert daemon.is_running


def _gaps(bot):
    return [t for t in _texts(bot) if t.startswith("Your studio did not check Telegram")]


def test_the_last_successful_check_is_kept_in_the_bots_profile(bot):
    _saved(bot)
    assert _until(lambda: _setting(CHECKED) is not None), "the last check was never kept"
    kept = datetime.fromisoformat(_setting(CHECKED))
    assert abs((datetime.now(timezone.utc) - kept).total_seconds()) < 120


def test_a_check_more_than_a_day_after_the_last_is_told_once_on_the_bot_and_in_the_panel(notifying):
    bot = notifying
    _saved(bot)
    before = datetime.now(timezone.utc) - timedelta(hours=30)
    _restart(bot, before)
    assert _until(lambda: len(_gaps(bot)) == 1), _texts(bot)
    [said] = _gaps(bot)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    expected_start = before.astimezone().strftime("%a %d %b, %H:%M")
    assert expected_start in said, said
    assert "Telegram keeps a bot's messages for one day" in said
    assert since.astimezone().strftime("%a %d %b") in said
    assert "Send again whatever is missing from Your collection." in said
    # Never a claim of loss, never a count.
    assert "lost" not in said.lower() and not re.search(r"\b\d+ (message|item)s?\b", said)
    panel = bot["client"].get("/api/v1/ingress/settings").json()
    assert panel["gap"] and panel["gap"]["said"] == said
    _settle(bot)
    assert len(_gaps(bot)) == 1, "the gap was told twice"


def test_got_it_clears_the_panels_notice_and_a_restart_tells_nothing_again(notifying):
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=40))
    assert _until(lambda: len(_gaps(bot)) == 1)
    res = bot["client"].post("/api/v1/ingress/gap/seen")
    assert res.status_code == 200, res.text
    assert res.json()["gap"] is None
    _restart(bot, datetime.now(timezone.utc) - timedelta(minutes=5))
    _settle(bot)
    assert len(_gaps(bot)) == 1 and bot["client"].get("/api/v1/ingress/settings").json()["gap"] is None


def test_under_a_day_nothing_is_said(notifying):
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=23))
    _settle(bot)
    assert _gaps(bot) == []
    assert bot["client"].get("/api/v1/ingress/settings").json()["gap"] is None


def test_the_bots_message_waits_for_quiet_hours_and_the_panel_says_it_at_once(notifying, monkeypatch):
    bot = notifying
    _saved(bot)
    held = {"now": datetime.now().astimezone().replace(hour=2, minute=0, second=0, microsecond=0)}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: held["now"])
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=30))
    _settle(bot)
    assert _gaps(bot) == [], "the gap was told during quiet hours"
    assert bot["client"].get("/api/v1/ingress/settings").json()["gap"], "the panel did not say it at once"
    held["now"] = held["now"].replace(hour=7, minute=5)
    assert _until(lambda: len(_gaps(bot)) == 1)


def test_it_needs_no_notification_switch(notifying):
    bot = notifying
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert not any(options[k] for k in ("notify_due", "notify_24h", "weekly", "morning"))
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=26))
    assert _until(lambda: len(_gaps(bot)) == 1)


def test_a_new_bot_token_starts_with_no_last_check(notifying):
    bot = notifying
    _saved(bot)
    assert _until(lambda: _setting(CHECKED) is not None)
    _write(CHECKED, (datetime.now(timezone.utc) - timedelta(days=3)).isoformat())
    other = "987654321:AAFanotherkeyZZZZZZZZZZZZZZZZZZZZZZZZZ"
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": other, "chat_id": OWNER})
    assert _setting(CHECKED) is None or datetime.fromisoformat(_setting(CHECKED)) > (
        datetime.now(timezone.utc) - timedelta(hours=1)), "another bot's last check was kept for this one"
    assert _setting(GAP) is None


def test_status_says_when_the_studio_last_checked_before_the_message(notifying):
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(days=2, hours=1))
    bot["fake"].push(OWNER, "/status")
    assert _until(lambda: any(t.startswith("Your studio is running.") for t in _texts(bot)))
    [status] = [t for t in _texts(bot) if t.startswith("Your studio is running.")]
    assert "2 days ago" in status, status


def test_help_says_the_studio_must_run_at_least_once_a_day():
    assert "at least once a day" in telegram_bot.HELP
    article = open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"),
                   encoding="utf-8").read()
    assert "at least once a day" in article


def test_removing_the_bot_forgets_its_last_check_and_its_notice(notifying):
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=30))
    assert _until(lambda: _setting(GAP) is not None)
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    assert _setting(CHECKED) is None and _setting(GAP) is None


def test_a_check_still_waiting_when_the_bot_is_removed_keeps_nothing(notifying):
    """
    A check waiting on Telegram when the creator removes the bot ends after
    the rows are gone: its time is not kept for a bot that is no longer
    there. Failed once on CI (macOS), where the stop's wait let that check
    end and keep its time.
    """
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=30))
    assert _until(lambda: _setting(GAP) is not None)
    # The next check waits on the fake as a long poll waits on Telegram, so
    # one is in flight when the bot is removed.
    bot["fake"].max_wait = 1.0
    time.sleep(0.5)
    bot["client"].post("/api/v1/ingress/settings", json={"bot_token": "", "chat_id": ""})
    time.sleep(1.5)
    assert _setting(CHECKED) is None and _setting(GAP) is None


@pytest.mark.parametrize("hours", [24.5, 72])
def test_the_moment_named_is_a_day_before_this_check(notifying, hours):
    bot = notifying
    _saved(bot)
    _restart(bot, datetime.now(timezone.utc) - timedelta(hours=hours))
    assert _until(lambda: _setting(GAP) is not None)
    import json
    gap = json.loads(_setting(GAP))
    checked = datetime.fromisoformat(gap["to"])
    assert abs((checked - datetime.fromisoformat(gap["since"])).total_seconds() - 24 * 3600) < 1
    assert abs((checked - datetime.fromisoformat(gap["from"])).total_seconds() - hours * 3600) < 120
