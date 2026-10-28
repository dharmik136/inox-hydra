"""
A weekly summary, opt-in, off by default.
========================================

Once a week, at the day and hour the creator picks in the Telegram panel
(Monday 09:00 on the computer's clock unless changed), one message about the
seven days to that moment: how many posts the studio recorded as published,
how many drafts were saved from the phone, how many replies are waiting, and
when the next post is scheduled. The creator's own figures are added only if
"The bot may answer with your figures" is on, each with where and when it
was read; a figure nobody read is left out, never shown as 0. No one else's
name or words, ever, and not the creator's own words either.

Told once a week (telegram_told), so a restart does not tell it again; the
first comes at the first chosen moment after it was turned on; it waits
through quiet hours like every notification.

Driven end to end against the fake Bot API (tests/telegram_fake.py), with the
computer's clock as the bot reads it (telegram_bot.local_now) set by the test.

Strict Invariants:
- Zero em-dashes.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import _until, bot  # noqa: E402,F401
from test_telegram_bot_figures import _record, _stamp, _urn  # noqa: E402
from test_telegram_bot_notifications import _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

HEAD = "Your week, the seven days to "


@pytest.fixture
def clock(monkeypatch):
    """The computer's clock as the bot reads it, now unless a test moves it by whole days."""
    held = {"shift": timedelta(0)}
    monkeypatch.setattr(telegram_bot, "local_now", lambda: datetime.now().astimezone() + held["shift"])

    def move(days):
        held["shift"] = timedelta(days=days)
    return move


def _weekly(bot, clock, **change):
    """
    The summary turned on, for this day of the week at this hour, so that its
    moment has just passed; turned on yesterday, so the first one is now due.
    Quiet hours off, so the hour the suite runs at does not hold it.
    """
    now = datetime.now().astimezone()
    payload = {"weekly": True, "weekly_day": now.weekday(), "weekly_hour": now.hour, "quiet_hours": False}
    payload.update(change)
    clock(-1)
    res = bot["client"].post("/api/v1/ingress/options", json=payload)
    clock(0)
    assert res.status_code == 200, res.text
    return now.replace(minute=0, second=0, microsecond=0)


def _summaries(bot):
    return [t for t in _texts(bot) if t.startswith(HEAD)]


def _week_of_records():
    """
    Two posts published this week (one read, one not), one the week before;
    two drafts from the phone this week, one from the week before and one
    written in the studio; two comments waiting from someone; a post queued.
    """
    latest = _record(latest_days=2, read_hours_ago=3, waiting=2, scheduled_in_hours=26)
    unread = _urn(3, 3)
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                     "VALUES (?, 'More of my own words', ?, ?, ?)", (unread, _stamp(72), _stamp(72), _stamp(1)))
        for days, tags in ((1, '["mobile-ingress"]'), (2, '["idea", "mobile-ingress"]'),
                           (10, '["mobile-ingress"]'), (1, '["studio"]')):
            moment = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO drafts (title, raw_content, tags, status, created_at, updated_at) "
                         "VALUES ('t', 'A draft of mine', ?, 'DRAFT', ?, ?)", (tags, moment, moment))
    conn.close()
    return latest, unread


def _day(urn_days):
    return (datetime.now(timezone.utc) - timedelta(days=urn_days)).astimezone().strftime("%a %d %b")


def test_the_weekly_summary_is_off_by_default_and_says_nothing(notifying, clock):
    bot = notifying
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert (options["weekly"], options["weekly_day"], options["weekly_hour"]) == (False, 0, 9)
    _week_of_records()
    bot["client"].post("/api/v1/ingress/options", json={"quiet_hours": False})
    _settle(bot)
    assert _summaries(bot) == []


def test_the_summary_counts_the_week_and_says_the_next_post(notifying, clock):
    bot = notifying
    _saved(bot)
    _week_of_records()
    moment = _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1), _texts(bot)
    [summary] = _summaries(bot)
    lines = summary.split("\n")
    assert lines[0] == f"{HEAD}{moment.strftime('%a %d %b, %H:%M')} on your computer's clock:"
    assert "Posts published, as your studio recorded them: 2" in lines
    assert "Drafts saved from your phone: 2" in lines
    assert "Replies waiting: 2" in lines
    assert any(line.startswith("Next scheduled post: ") and line.endswith("(your computer's time).") for line in lines)
    assert "impressions" not in summary, "figures went with the figures switch off"


def test_with_figures_on_each_post_of_the_week_says_its_figures_and_where_and_when_they_were_read(notifying, clock):
    bot = notifying
    _saved(bot)
    _week_of_records()
    bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1), _texts(bot)
    [summary] = _summaries(bot)
    assert ("- Published " + _day(2) + ": 1,234 impressions, 56 reactions, 7 comments, read on its analytics page "
            "3 hours ago") in summary.split("\n"), summary
    assert "- Published " + _day(3) + ": no figures read yet" in summary.split("\n"), summary
    assert "reposts" not in summary, "a repost count nobody read was said"
    assert summary.count("- Published ") == 2, "a post from another week was counted"


def test_the_summary_never_carries_a_persons_name_their_words_or_the_creators_own(notifying, clock):
    bot = notifying
    _saved(bot)
    _week_of_records()
    bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1)
    [summary] = _summaries(bot)
    for private in ("Jane", "Stranger", "thoughtful", "Head of Something", "pricing", "My scheduled words",
                    "More of my own words", "A draft of mine"):
        assert private not in summary, private


def test_it_is_told_once_a_week_and_a_restart_does_not_tell_it_again(notifying, clock):
    bot = notifying
    _saved(bot)
    _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1)
    _settle(bot)
    bot["daemon"].stop_worker()
    bot["daemon"]._thread.join(3)
    bot["daemon"].start_worker()
    _settle(bot)
    assert len(_summaries(bot)) == 1, "the week's summary was told twice"
    # A week later, the next one.
    clock(7)
    assert _until(lambda: len(_summaries(bot)) == 2), _texts(bot)
    _settle(bot)
    assert len(_summaries(bot)) == 2


def test_the_first_comes_at_the_first_chosen_moment_after_it_was_turned_on(notifying, clock):
    """Turned on after this week's moment has passed, nothing comes until next week's."""
    bot = notifying
    _saved(bot)
    now = datetime.now().astimezone()
    res = bot["client"].post("/api/v1/ingress/options", json={
        "weekly": True, "weekly_day": now.weekday(), "weekly_hour": now.hour, "quiet_hours": False})
    assert res.status_code == 200
    _settle(bot)
    assert _summaries(bot) == [], "a summary went the moment it was turned on"
    assert res.json()["weekly_next"] == (now.replace(minute=0, second=0, microsecond=0) + timedelta(days=7)).strftime(
        "%a %d %b, %H:%M")
    clock(7)
    assert _until(lambda: len(_summaries(bot)) == 1), _texts(bot)


def test_the_summary_waits_through_quiet_hours(notifying, clock):
    bot = notifying
    _saved(bot)
    now = datetime.now().astimezone()
    _weekly(bot, clock, quiet_hours=True, quiet_from=now.hour, quiet_to=(now.hour + 1) % 24)
    _settle(bot)
    _settle(bot)
    assert _summaries(bot) == [], "the summary went during quiet hours"
    bot["client"].post("/api/v1/ingress/options", json={"quiet_hours": False})
    assert _until(lambda: len(_summaries(bot)) == 1), "the summary did not go when quiet hours ended"


def test_the_day_and_the_hour_are_the_creators_to_pick(bot):
    _saved(bot)
    res = bot["client"].post("/api/v1/ingress/options", json={"weekly_day": 4, "weekly_hour": 18})
    assert res.status_code == 200
    options = res.json()["options"]
    assert (options["weekly"], options["weekly_day"], options["weekly_hour"]) == (False, 4, 18)
    for wrong in ({"weekly_day": 7}, {"weekly_hour": 24}, {"weekly_day": -1}):
        assert bot["client"].post("/api/v1/ingress/options", json=wrong).status_code in (400, 422), wrong
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert (options["weekly_day"], options["weekly_hour"]) == (4, 18), "a refused change was saved"


def test_deleting_everything_forgets_that_a_week_was_told(notifying, clock):
    bot = notifying
    _saved(bot)
    _weekly(bot, clock)
    assert _until(lambda: len(_summaries(bot)) == 1)
    import onboarding
    onboarding.forget_identity()
    conn = get_db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM settings WHERE key = ?", (telegram_bot.TOLD_KEY,)).fetchone()[0] == 0
    finally:
        conn.close()


def test_the_help_the_policy_and_the_panel_say_what_the_summary_sends():
    article = " ".join(open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"),
                            encoding="utf-8").read().split())
    policy = " ".join(open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read().split())
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    for text in (article, policy, panel):
        assert "Send me a weekly summary" in text
    assert HEAD.strip() in article and "Drafts saved from your phone" in article
    assert "weekly summary" in policy and "replies are waiting (a count)" in policy
