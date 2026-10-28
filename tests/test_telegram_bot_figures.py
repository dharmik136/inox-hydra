"""
Figures on Telegram, only when the creator allows it.
=====================================================

A switch in the Telegram panel, off by default: "The bot may answer with
your figures". Off, /today says the figures stay in the studio. On, /today
answers with the latest post's figures, each with where it was read and how
long ago, how many replies are waiting, as a count, and when the next post
is scheduled. Those figures then sit on Telegram's servers, which the panel
and the policy say. Never another person's name or comment text.

Driven end to end against the fake Bot API (tests/telegram_fake.py).

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
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

ME = "figures-creator"


def _urn(days, salt):
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return "urn:li:activity:" + str((int(moment.timestamp() * 1000) << 22) + salt)


def _stamp(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _record(latest_days=2, read_hours_ago=3, waiting=2, scheduled_in_hours=26):
    """The creator's latest post read on its analytics page, comments waiting from two people, a post queued."""
    from migrations import interaction_comment_key
    latest, older = _urn(latest_days, 1), _urn(9, 2)
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO creator_identity (id, vanity, display_name, confirmed_at) "
                     "VALUES (1, ?, 'Figures Creator', '2026-10-01T00:00:00+00:00')", (ME,))
        for urn, days in ((latest, latest_days), (older, 9)):
            conn.execute("INSERT INTO own_posts (activity_urn, text, published_at, first_seen_at, last_seen_at) "
                         "VALUES (?, ?, ?, ?, ?)", (urn, "My own words about pricing", _stamp(days * 24),
                                                    _stamp(days * 24), _stamp(1)))
        conn.execute(
            "INSERT INTO post_metric_observations (activity_urn, observed_at, observed_hour, age_hours, source, "
            "impressions, reactions, comments, reposts, precision) VALUES (?, ?, ?, ?, 'post_analytics', 1234, 56, 7, "
            "NULL, 'exact')", (latest, _stamp(read_hours_ago), "probe-hour", latest_days * 24.0 - read_hours_ago))
        for n in range(waiting):
            lead = f"lead-{n}"
            conn.execute("INSERT INTO leads (id, name, full_name, headline, lead_status) VALUES (?, ?, ?, ?, 'NEW')",
                         (lead, "Jane Stranger", "Jane Stranger", "Head of Something"))
            text = f"What a thoughtful post number {n}"
            conn.execute(
                "INSERT INTO lead_interactions (lead_id, post_urn, interaction_type, comment_text, interacted_at, "
                "comment_key, first_seen_at, last_seen_at, seen_count) VALUES (?, ?, 'COMMENT', ?, ?, ?, ?, ?, 1)",
                (lead, latest, text, _stamp(5), interaction_comment_key(text), _stamp(5), _stamp(5)))
        if scheduled_in_hours is not None:
            when = (datetime.now(timezone.utc) + timedelta(hours=scheduled_in_hours)).replace(microsecond=0)
            conn.execute("INSERT INTO posts (id, content, status, scheduled_for, created_at) "
                         "VALUES ('queued-1', 'My scheduled words', 'scheduled', ?, ?)",
                         (when.isoformat(), _stamp(1)))
    conn.close()
    return latest


def _today(bot):
    bot["fake"].push(OWNER, "/today")
    assert _until(lambda: len(_texts(bot)) >= 1), _texts(bot)
    return _texts(bot)[-1]


def test_figures_are_off_by_default_and_today_says_so(bot):
    _saved(bot)
    _record()
    assert bot["client"].get("/api/v1/ingress/settings").json()["options"]["figures"] is False
    answer = _today(bot)
    assert answer == telegram_bot.SENTENCES["figures_off"]
    assert "1,234" not in answer and "1234" not in answer


def test_with_figures_on_today_answers_with_the_latest_posts_figures_replies_and_the_next_post(bot):
    _saved(bot)
    _record()
    res = bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    assert res.status_code == 200 and res.json()["options"]["figures"] is True
    answer = _today(bot)
    assert answer.startswith("Your latest post, published 2 days ago: 1,234 impressions, 56 reactions, 7 comments,")
    assert "read on its analytics page 3 hours ago" in answer
    assert "Replies waiting: 2." in answer
    assert "Next scheduled post:" in answer and "your computer's time" in answer


def test_today_never_carries_a_persons_name_their_words_or_the_creators_text(bot):
    _saved(bot)
    _record()
    bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    answer = _today(bot)
    for private in ("Jane", "Stranger", "thoughtful", "Head of Something", "pricing", "My scheduled words"):
        assert private not in answer, private


def test_a_figure_not_read_is_left_out_never_made_zero(bot):
    _saved(bot)
    _record()
    bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    assert "reposts" not in _today(bot), "a repost count nobody read was said"


def test_with_nothing_held_today_says_so_plainly(bot):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"figures": True})
    answer = _today(bot)
    assert answer.startswith(telegram_bot.SENTENCES["no_post"])
    assert "Replies waiting: 0." in answer and telegram_bot.SENTENCES["nothing_scheduled"] in answer


def test_the_panel_and_the_policy_say_the_figures_then_sit_on_telegrams_servers():
    panel = open(os.path.join(REPO_ROOT, "studio", "ui", "src", "components", "TelegramIngressPanel.tsx"),
                 encoding="utf-8").read()
    assert "The bot may answer with your figures" in panel and "Telegram's servers" in panel
    policy = " ".join(open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read().split())
    assert "The bot may answer with your figures" in policy and "sit on Telegram's servers" in policy


@pytest.mark.parametrize("hours, said", [(0.5, "30 minutes ago"), (3, "3 hours ago"), (50, "2 days ago")])
def test_ages_are_said_in_words(hours, said):
    assert telegram_bot.ago(datetime.now(timezone.utc) - timedelta(hours=hours)) == said
