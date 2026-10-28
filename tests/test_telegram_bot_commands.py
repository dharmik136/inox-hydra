"""
The bot's commands: /start, /help, /idea, /ask, /status, and one it does not know.
=================================================================================

/start and /help say what the bot does, how to pair and what it never sends.
/idea saves a draft tagged as an idea. /ask writes an ask in From your
record's store, an explicit act of the creator's, so it goes through the
store's own rule with the source "telegram". /status says whether the studio
and its bridge are running, with no figures. Any other command is answered
with how to see what the bot does.

Questions (/start, /help, /status) are answered even with the confirmations
turned off; what /idea and /ask did follows that switch, like every other
confirmation. A refused chat's command is refused like any message.

Driven end to end against the fake Bot API (tests/telegram_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
import sys
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, _drafts, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _asks():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT text, source, status FROM asks ORDER BY id")]
    finally:
        conn.close()


def _tags():
    conn = get_db()
    try:
        return [r[0] for r in conn.execute("SELECT tags FROM drafts WHERE tags LIKE '%mobile-ingress%' ORDER BY id")]
    finally:
        conn.close()


def _ask(bot, *texts, count=None):
    for text in texts:
        bot["fake"].push(OWNER, text)
    want = count if count is not None else len(texts)
    assert _until(lambda: len(_texts(bot)) >= want), _texts(bot)
    return _texts(bot)


@pytest.mark.parametrize("command", ["/start", "/help", "/HELP", "/help@InoxHydraBot"])
def test_start_and_help_say_what_the_bot_does_how_to_pair_and_what_it_never_sends(bot, command):
    _saved(bot)
    [answer] = _ask(bot, command)
    assert answer == telegram_bot.HELP
    for words in ("/idea", "/ask", "/status", "This is me", "never"):
        assert words in answer, words


def test_idea_saves_a_draft_tagged_as_an_idea(bot):
    _saved(bot)
    answers = _ask(bot, "/idea pricing for a two person studio", "/IDEA@InoxHydraBot hiring loops")
    assert _drafts() == ["pricing for a two person studio", "hiring loops"]
    assert all('"idea"' in tags for tags in _tags())
    assert answers == [SAID["draft"], SAID["draft"]]


def test_an_idea_keeps_a_short_link_as_part_of_the_idea(bot):
    """/idea says what the message is: its words stay a draft even with a link in them."""
    _saved(bot)
    _ask(bot, "/idea compare with https://lnkd.in/p/dXyZ4bQ7 next week")
    assert _drafts() == ["compare with https://lnkd.in/p/dXyZ4bQ7 next week"]


def test_an_empty_idea_or_ask_says_how_to_send_one(bot):
    _saved(bot)
    assert _ask(bot, "/idea", "/ask   ") == [SAID["empty_idea"], SAID["empty_ask"]]
    assert _drafts() == [] and _asks() == []


def test_ask_writes_an_ask_through_the_stores_rule(bot):
    _saved(bot)
    [answer] = _ask(bot, "/ask more on hiring loops")
    assert answer == SAID["ask"]
    assert _asks() == [{"text": "more on hiring loops", "source": "telegram", "status": "open"}]
    # The same ask twice is one ask, as in the store.
    _ask(bot, "/ask more on hiring loops", count=2)
    assert len(_asks()) == 1
    assert _drafts() == [], "an ask was saved as a draft as well"


def test_status_says_whether_the_studio_and_the_bridge_are_running_with_no_figures(bot):
    _saved(bot)
    [quiet] = _ask(bot, "/status")
    assert quiet.startswith("Your studio is running.") and "bridge" in quiet
    assert not re.search(r"\d", quiet), "the status carried a figure"
    bot["client"].post("/api/v1/bridge/heartbeat", json={"extension_version": "test"})
    _ask(bot, "/status", count=2)
    assert _texts(bot)[1] == "Your studio is running. " + SAID["bridge_connected"]


def test_a_command_it_does_not_know_says_how_to_see_what_it_does(bot):
    _saved(bot)
    assert _ask(bot, "/stats") == [SAID["unknown_command"]]
    assert _drafts() == [], "an unknown command was saved as a draft"


def test_questions_are_answered_with_the_confirmations_off_and_an_idea_is_not_confirmed(bot):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    bot["fake"].push(OWNER, "/idea quietly")
    bot["fake"].push(OWNER, "/help")
    assert _until(lambda: len(_texts(bot)) >= 1)
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _texts(bot) == [telegram_bot.HELP]
    assert _drafts() == ["quietly"]


def test_a_refused_chats_command_is_refused(bot):
    _saved(bot)
    bot["fake"].push(STRANGER, "/help")
    assert _until(lambda: len(_texts(bot, STRANGER)) == 1)
    assert _texts(bot, STRANGER) == [SAID["other_chat"]]


def test_the_store_takes_a_telegram_ask_and_the_box_still_refuses_one(bot):
    import record_store
    assert "telegram" in record_store.CREATOR_SOURCES
    res = bot["client"].post("/api/v1/record/asks", json={"text": "x", "source": "telegram"})
    assert res.status_code == 400, "the section's box can claim an ask came from the phone"


def test_the_help_lists_the_commands():
    article = open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"), encoding="utf-8").read()
    for command in ("/start", "/help", "/idea", "/ask", "/status", "/drafts"):
        assert f"`{command}" in article, command


def _phone_draft(days_ago, tags='["mobile-ingress"]', words="An idea of mine"):
    from datetime import timedelta
    moment = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO drafts (title, raw_content, tags, status, created_at, updated_at) "
                     "VALUES ('t', ?, ?, 'DRAFT', ?, ?)", (words, tags, moment, moment))
    conn.close()


def test_drafts_answers_how_many_drafts_came_from_the_phone_in_seven_days_as_a_count(bot):
    """Phase 2: a count, never a draft's words; answered whatever the confirmations switch says."""
    _saved(bot)
    for days in (0.5, 2, 6.5):
        _phone_draft(days)
    _phone_draft(8)
    _phone_draft(1, tags='["studio"]', words="Written at the desk")
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    [answer] = _ask(bot, "/drafts")
    assert answer == SAID["drafts"].format(count=3)
    assert "idea of mine" not in answer and "desk" not in answer
    assert len(_drafts()) == 4 and not any("drafts" in d for d in _drafts()), "/drafts was saved as a draft"


def test_drafts_with_none_says_none(bot):
    _saved(bot)
    [answer] = _ask(bot, "/drafts")
    assert answer == SAID["drafts_none"]


def test_a_strangers_drafts_command_is_refused(bot):
    _saved(bot)
    bot["fake"].push(STRANGER, "/drafts")
    assert _until(lambda: len(_texts(bot, STRANGER)) == 1)
    assert _texts(bot, STRANGER) == [SAID["other_chat"]]
