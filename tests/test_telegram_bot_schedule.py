"""
Schedule <when>: plans for real (phase 5, item 6).
==================================================

The help used to warn that `Schedule <when>: your text` "does not schedule
anything": the time was read and dropped. With Plan it's reader, a time the
bot reads as /plan reads one (a day, then a time) puts the draft in the
Queue then, answered as a plan is, with Undo, and told when due as a draft
planned from the phone is. A time it cannot read, or one already past,
keeps the draft as it always did, and the answer says so. Nothing posts and
nothing reaches LinkedIn.

docs/quality/cycle4/bot-phase5.md, item 6. Against the fake Bot API.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
from datetime import datetime, timedelta

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import phone_plans  # noqa: E402
import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES


def _drafts():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT id, content, status, scheduled_for, made_with FROM posts "
                                              "WHERE id LIKE 'post-draft-%' ORDER BY rowid")]
    finally:
        conn.close()


def _labels(bot, text_start):
    message = [m for m in bot["fake"].sent if str(m["text"]).startswith(text_start)][-1]["message_id"]
    return [b["text"] for b in bot["fake"].buttons(message)], message


def test_a_time_read_as_plan_reads_it_plans_the_draft_with_undo(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "Schedule tomorrow 09:00: pricing is a design decision")
    assert _until(lambda: _drafts() and _drafts()[-1]["status"] == "scheduled"), (_drafts(), _texts(bot))
    draft = _drafts()[-1]
    assert draft["content"] == "pricing is a design decision"
    tomorrow = datetime.combine(datetime.now().astimezone().date() + timedelta(days=1),
                                datetime.min.time().replace(hour=9)).astimezone()
    assert datetime.fromisoformat(draft["scheduled_for"]) == tomorrow
    assert json.loads(draft["made_with"])["planned"]["from"] == "telegram"
    said = SAID["draft"] + " " + telegram_bot.PLANNED_WORDS.format(when=phone_plans.full_time(tomorrow))
    assert _until(lambda: any(t.startswith(said) for t in _texts(bot))), _texts(bot)
    labels, message = _labels(bot, said)
    assert labels == ["Undo"]
    bot["fake"].press_button("Undo", OWNER, message_id=message)
    assert _until(lambda: _drafts()[-1]["status"] == "draft"), _drafts()
    assert [a["text"] for a in bot["fake"].answered][-1] == SAID["unplanned"]
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM settings WHERE key LIKE 'linkedin_holds:%'").fetchone()[0] == 0
    conn.close()


def test_a_time_not_read_keeps_the_draft_as_before_and_says_so(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "Schedule someday soon: pricing pages lie")
    assert _until(lambda: _drafts()), _texts(bot)
    assert _drafts()[-1]["status"] == "draft" and _drafts()[-1]["scheduled_for"] is None
    said = SAID["draft"] + " " + SAID["schedule_unread"]
    assert _until(lambda: said in _texts(bot)), _texts(bot)
    labels, _message = _labels(bot, said)
    assert labels == ["Undo"]


def test_a_time_already_past_keeps_the_draft_and_says_so(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "Schedule today 00:00: hiring loops")
    assert _until(lambda: _drafts()), _texts(bot)
    assert _drafts()[-1]["status"] == "draft"
    assert _until(lambda: SAID["draft"] + " " + SAID["plan_past"] in _texts(bot)), _texts(bot)


def test_a_draft_message_is_still_a_draft(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "Draft: an ordinary draft")
    assert _until(lambda: SAID["draft"] in _texts(bot)), _texts(bot)
    assert _drafts()[-1]["status"] == "draft"
