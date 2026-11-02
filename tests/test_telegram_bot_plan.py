"""
Plan it from the phone (phase 5, item 2).
=========================================

Under "Draft ready", Plan it offers a few times; a press puts the draft in
the Queue at that time, in one conditional update, and the due reminder
brings it back then. The times are the creator's preference: the Queue's
next open slots by default, or their own times (tomorrow at 09:00 and at
18:00 by default), which are offered too when the Queue has no open slot.
A reply to the bot's message about a draft with /plan <day> <time> plans it
too; /plan alone lists the next queued posts, times always and first lines
only with the words switch on. Nothing here posts anything or reaches
LinkedIn: at the planned time the Queue's own scheduler marks the post due.

docs/quality/cycle4/bot-phase5.md, item 2. Against the fake Bot API and the
fake provider.

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

import egress  # noqa: E402
import phone_plans  # noqa: E402
import telegram_bot  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
DRAFT = "Pricing is a design decision.\n\nWrite the price page first."


@pytest.fixture
def planning(bot, monkeypatch):
    """The worker tells what is due at every turn, and the bot's clock reads midday, so quiet hours hold nothing."""
    monkeypatch.setattr(telegram_bot, "NOTIFY_EVERY_SECONDS", 0.0)
    midday = datetime.now().astimezone().replace(hour=12, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(telegram_bot, "local_now", lambda: midday)
    return bot


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _message(bot, text):
    found = [m for m in bot["fake"].sent if m["text"] == text]
    return found[-1]["message_id"] if found else None


def _shown(bot, message_id):
    return str(bot["fake"].message(message_id).get("text") or "")


def _drafted(bot, words_on=False):
    """An idea from the phone, written up there: the "Draft ready" message's id and the draft's."""
    _saved(bot)
    if words_on:
        bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    bot["fake"].push(OWNER, "Idea: pricing is a design decision")
    assert _until(lambda: SAID["collected"] in _texts(bot)), _texts(bot)
    bot["fake"].press_button("Write it up", OWNER)
    ready = SAID["draft_ready_words"] if words_on else SAID["draft_ready"]
    assert _until(lambda: any(t.startswith(ready) for t in _texts(bot))), _texts(bot)
    message = [m for m in bot["fake"].sent if str(m["text"]).startswith(ready)][-1]["message_id"]
    conn = get_db()
    post_id = conn.execute("SELECT id FROM posts WHERE made_with IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    conn.close()
    return message, post_id


def _post(post_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT status, scheduled_for, made_with FROM posts WHERE id = ?", (post_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _times_message(bot):
    found = [m for m in bot["fake"].sent if m["text"].startswith(SAID["plan_ask"])]
    return found[-1]["message_id"] if found else None


def _slots(*entries):
    """The Queue's weekly slots, replaced: (day of week, "HH:MM")."""
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM queue_slots")
        for day, at in entries:
            conn.execute("INSERT INTO queue_slots (day_of_week, time_slot, label, is_active) VALUES (?, ?, 'x', 1)",
                         (day, at))
    conn.close()


def _every_day_at(*clocks):
    _slots(*[(day, at) for day in range(7) for at in clocks])


def _ahead(hours):
    """A whole-minute clock time some hours from now, on the computer's clock, as a slot is written."""
    return (datetime.now().astimezone() + timedelta(hours=hours)).strftime("%H:%M")


def test_draft_ready_carries_plan_it_with_the_words_switch_on_or_off(bot, provider):
    message, _post_id = _drafted(bot)
    assert _labels(bot, message) == ["Plan it"]


def test_with_the_words_on_it_sits_beside_send_me_the_whole_post(bot, provider):
    message, _post_id = _drafted(bot, words_on=True)
    labels = _labels(bot, message)
    assert labels[:2] == ["Send me the whole post", "Plan it"]
    assert "Shorter" in labels


def test_plan_it_offers_the_queues_next_open_slots_by_default(bot, provider):
    _every_day_at(_ahead(3), _ahead(6))
    message, post_id = _drafted(bot)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None), _texts(bot)
    times, source = phone_plans.offered_times(post_id, datetime.now().astimezone())
    assert source == "slots" and len(times) == 3
    now = datetime.now().astimezone()
    assert _labels(bot, _times_message(bot)) == [phone_plans.said_time(t, now) for t in times]
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["plan_pick"]]), [a["text"] for a in bot["fake"].answered][-3:]
    # Plan it stays on its message, to be pressed again.
    assert _labels(bot, message) == ["Plan it"]
    assert _post(post_id)["status"] == "draft", "offering times planned something"


def test_a_time_pressed_puts_the_draft_in_the_queue_at_that_time_with_undo(bot, provider):
    _every_day_at(_ahead(3))
    message, post_id = _drafted(bot)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    times_message = _times_message(bot)
    first = bot["fake"].buttons(times_message)[0]["text"]
    bot["fake"].press_button(first, OWNER, message_id=times_message)
    assert _until(lambda: _post(post_id)["status"] == "scheduled"), _post(post_id)
    held = _post(post_id)
    planned = json.loads(held["made_with"])["planned"]
    assert planned["for"] == held["scheduled_for"] and planned["from"] == "telegram"
    when = datetime.fromisoformat(held["scheduled_for"])
    assert when > datetime.now(timezone.utc)
    assert _until(lambda: _shown(bot, times_message).startswith(
        telegram_bot.PLANNED_WORDS.format(when=phone_plans.full_time(when))))
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["planned"]]), [a["text"] for a in bot["fake"].answered][-3:]
    assert _labels(bot, times_message) == ["Undo"]
    bot["fake"].press_button("Undo", OWNER, message_id=times_message)
    assert _until(lambda: _post(post_id)["status"] == "draft"), _post(post_id)
    assert _post(post_id)["scheduled_for"] is None
    assert "planned" not in json.loads(_post(post_id)["made_with"])
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["unplanned"]]), [a["text"] for a in bot["fake"].answered][-3:]
def test_undo_leaves_a_plan_moved_in_the_queue_as_it_is(bot, provider):
    _every_day_at(_ahead(3))
    message, post_id = _drafted(bot)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    times_message = _times_message(bot)
    bot["fake"].press_button(bot["fake"].buttons(times_message)[0]["text"], OWNER, message_id=times_message)
    assert _until(lambda: _post(post_id)["status"] == "scheduled")
    later = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    assert bot["client"].post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": later}).status_code == 200
    bot["fake"].press_button("Undo", OWNER, message_id=times_message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["unplan_changed"]])
    assert _post(post_id)["status"] == "scheduled"


def test_planning_never_reaches_linkedin_and_the_queue_marks_it_due_not_published(planning, provider):
    bot = planning
    _every_day_at(_ahead(3))
    message, post_id = _drafted(bot)
    linkedin = egress.stats_for("linkedin")
    before = linkedin["performed"] + linkedin["refused"]
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    times_message = _times_message(bot)
    bot["fake"].press_button(bot["fake"].buttons(times_message)[0]["text"], OWNER, message_id=times_message)
    assert _until(lambda: _post(post_id)["status"] == "scheduled")
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM settings WHERE key LIKE 'linkedin_holds:%'").fetchone()[0] == 0
    # The planned time comes: the Queue's own scheduler marks it due, and that is all.
    with conn:
        conn.execute("UPDATE posts SET scheduled_for = ? WHERE id = ?",
                     ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), post_id))
        conn.execute("UPDATE posts SET made_with = json_set(made_with, '$.planned.for', scheduled_for) WHERE id = ?",
                     (post_id,))
    conn.close()
    from scheduler import native_scheduler
    native_scheduler.check_scheduled_queue()
    assert _post(post_id)["status"] == "due"
    assert linkedin["performed"] + linkedin["refused"] == before, "planning asked for LinkedIn"
    methods = {c["method"] for c in bot["fake"].calls}
    assert methods <= {"getUpdates", "sendMessage", "answerCallbackQuery", "editMessageText",
                       "editMessageReplyMarkup", "setMyCommands", "deleteMyCommands"}, methods


def test_at_its_time_the_due_reminder_brings_it_back_even_with_the_due_switch_off(planning, provider):
    bot = planning
    _every_day_at(_ahead(3))
    message, post_id = _drafted(bot, words_on=True)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    times_message = _times_message(bot)
    bot["fake"].press_button(bot["fake"].buttons(times_message)[0]["text"], OWNER, message_id=times_message)
    assert _until(lambda: _post(post_id)["status"] == "scheduled")
    assert telegram_bot.notify_due_on() is False
    # A post queued at the desk and due too: not planned from the phone, so not told with the switch off.
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES ('desk-1', 'Desk words', 'due', ?)",
                     ((datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),))
        conn.execute("UPDATE posts SET status = 'due' WHERE id = ?", (post_id,))
    conn.close()
    assert _until(lambda: SAID["due_one"] in _texts(bot)), _texts(bot)
    told = _message(bot, SAID["due_one"])
    assert _labels(bot, told) == ["Send me the whole post", "Remind me in an hour", "Done"]
    bot["fake"].press_button("Send me the whole post", OWNER, message_id=told)
    assert _until(lambda: _texts(bot)[-1] == DRAFT), _texts(bot)
    time.sleep(1.0)
    assert _texts(bot).count(SAID["due_one"]) == 1, "told twice, or the desk's post told with the switch off"


def test_the_times_offered_are_the_creators_preference(bot, provider):
    described = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert described["plan"] == phone_plans.PLAN_DEFAULT
    assert described["defaults"]["plan"] == phone_plans.PLAN_DEFAULT
    mine = {"from": "times", "slots": 3, "times": [{"days": 2, "at": "07:30"}]}
    res = bot["client"].post("/api/v1/ingress/options", json={"plan": mine})
    assert res.status_code == 200 and res.json()["options"]["plan"] == mine, res.text
    message, post_id = _drafted(bot)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    expected = datetime.combine(datetime.now().astimezone().date() + timedelta(days=2),
                                datetime.min.time().replace(hour=7, minute=30)).astimezone()
    assert _labels(bot, _times_message(bot)) == [phone_plans.said_time(expected, datetime.now().astimezone())]


def test_with_no_open_slot_the_creators_own_times_are_offered_and_said(bot, provider):
    _slots()
    message, post_id = _drafted(bot)
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: _times_message(bot) is not None)
    assert SAID["plan_times_instead"] in _shown(bot, _times_message(bot))
    now = datetime.now().astimezone()
    tomorrow = now.date() + timedelta(days=1)
    expected = [datetime.combine(tomorrow, datetime.min.time().replace(hour=h)).astimezone() for h in (9, 18)]
    assert _labels(bot, _times_message(bot)) == [phone_plans.said_time(t, now) for t in expected]


def test_a_wrong_preference_is_refused_and_nothing_is_saved(bot):
    for wrong in ({"from": "times", "slots": 3, "times": []},
                  {"from": "times", "slots": 3, "times": [{"days": 20, "at": "09:00"}]},
                  {"from": "times", "slots": 3, "times": [{"days": 1, "at": "25:00"}]},
                  {"from": "slots", "slots": 9, "times": [{"days": 1, "at": "09:00"}]},
                  {"from": "later", "slots": 3, "times": [{"days": 1, "at": "09:00"}]}):
        assert bot["client"].post("/api/v1/ingress/options", json={"plan": wrong}).status_code == 400, wrong
    assert phone_plans.plan_offers() == phone_plans.PLAN_DEFAULT
    for wrong in (0, 11):
        assert bot["client"].post("/api/v1/ingress/options", json={"list_at_most": wrong}).status_code in (400, 422)
    assert phone_plans.list_at_most() == 5


def test_a_post_queued_at_the_desk_published_or_gone_is_left_as_it_is(bot, provider):
    _every_day_at(_ahead(3))
    message, post_id = _drafted(bot)
    later = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    assert bot["client"].post(f"/api/posts/{post_id}/reschedule", json={"scheduled_for": later}).status_code == 200
    bot["fake"].press_button("Plan it", OWNER, message_id=message)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["plan_queued"]])
    assert _times_message(bot) is None and _post(post_id)["scheduled_for"] == later
    # Handed to LinkedIn: never moved from the phone.
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'draft', scheduled_for = NULL WHERE id = ?", (post_id,))
        conn.execute("INSERT INTO settings (key, value) VALUES (?, 'held')", (f"linkedin_holds:{post_id}",))
    conn.close()
    assert phone_plans.plan(post_id, later)["status"] == "queued"
    conn = get_db()
    with conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (f"linkedin_holds:{post_id}",))
        conn.execute("UPDATE posts SET status = 'published', published_at = ? WHERE id = ?", (later, post_id))
    conn.close()
    assert phone_plans.plan(post_id, later)["status"] == "posted"
    assert phone_plans.plan("post_gone", later)["status"] == "gone"


def test_a_reply_with_a_day_and_a_time_plans_that_draft(planning, provider):
    bot = planning
    message, post_id = _drafted(bot)
    bot["fake"].push(OWNER, "/plan tomorrow 09:00", reply_to_message={"message_id": message, "chat": {"id": int(OWNER)},
                                                                      "text": SAID["draft_ready"]})
    tomorrow = datetime.combine(datetime.now().astimezone().date() + timedelta(days=1),
                                datetime.min.time().replace(hour=9)).astimezone()
    assert _until(lambda: _post(post_id)["status"] == "scheduled"), _texts(bot)
    assert datetime.fromisoformat(_post(post_id)["scheduled_for"]) == tomorrow
    said = telegram_bot.PLANNED_WORDS.format(when=phone_plans.full_time(tomorrow))
    assert _until(lambda: any(t.startswith(said) for t in _texts(bot))), _texts(bot)
    assert _labels(bot, [m for m in bot["fake"].sent if str(m["text"]).startswith(said)][-1]["message_id"]) == ["Undo"]


def test_plan_with_a_time_but_no_reply_unread_or_past_says_how(planning, provider):
    bot = planning
    message, post_id = _drafted(bot)
    bot["fake"].push(OWNER, "/plan tomorrow 09:00")
    assert _until(lambda: _texts(bot)[-1] == SAID["plan_reply"]), _texts(bot)
    reply = {"message_id": message, "chat": {"id": int(OWNER)}, "text": SAID["draft_ready"]}
    bot["fake"].push(OWNER, "/plan someday soon", reply_to_message=reply)
    assert _until(lambda: _texts(bot)[-1] == SAID["plan_unread"]), _texts(bot)
    bot["fake"].push(OWNER, "/plan today 00:00", reply_to_message=reply)
    assert _until(lambda: _texts(bot)[-1] == SAID["plan_past"]), _texts(bot)
    assert _post(post_id)["status"] == "draft"


def test_read_when_reads_a_day_and_a_time_as_a_person_writes_them():
    wednesday = datetime(2026, 11, 4, 12, 0).astimezone()
    read = phone_plans.read_when
    assert read("today 18:30", wednesday) == datetime(2026, 11, 4, 18, 30).astimezone()
    assert read("tomorrow 9", wednesday) == datetime(2026, 11, 5, 9, 0).astimezone()
    assert read("fri 6pm", wednesday) == datetime(2026, 11, 6, 18, 0).astimezone()
    assert read("Friday 6 pm", wednesday) == datetime(2026, 11, 6, 18, 0).astimezone()
    assert read("wed 13:00", wednesday) == datetime(2026, 11, 4, 13, 0).astimezone()
    assert read("wed 11:00", wednesday) == datetime(2026, 11, 11, 11, 0).astimezone(), "a weekday's past time is next week"
    assert read("mon 12am", wednesday) == datetime(2026, 11, 9, 0, 0).astimezone()
    for wrong in ("tomorrow", "9:00", "someday 9", "tomorrow 25:00", "tomorrow 13pm", "tomorrow 9:75", ""):
        assert read(wrong, wednesday) is None, wrong


def test_plan_alone_lists_the_next_queued_posts_times_always_words_only_with_the_switch(planning):
    bot = planning
    _saved(bot)
    now = datetime.now(timezone.utc)
    conn = get_db()
    with conn:
        for n in range(7):
            conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES (?, ?, 'scheduled', ?)",
                         (f"q-{n}", f"Queued words {n}\nmore", (now + timedelta(days=n + 1)).isoformat()))
        conn.execute("INSERT INTO settings (key, value) VALUES ('linkedin_holds:q-0', 'held')")
        conn.execute("INSERT INTO posts (id, content, status, scheduled_for) VALUES ('d-1', 'Due words', 'due', ?)",
                     (now.isoformat(),))
    conn.close()
    bot["fake"].push(OWNER, "/plan")
    assert _until(lambda: _texts(bot) and _texts(bot)[-1].startswith("Planned in your Queue")), _texts(bot)
    listed = _texts(bot)[-1]
    lines = [line for line in listed.splitlines() if line.startswith("- ")]
    assert len(lines) == 5 and "Queued words" not in listed
    assert "LinkedIn posts it" in lines[0]
    assert phone_plans.full_time(now + timedelta(days=1)) in lines[0]
    assert "One post is due now in your Queue." in listed
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True, "list_at_most": 2})
    bot["fake"].push(OWNER, "/plan")
    assert _until(lambda: "Queued words 0" in _texts(bot)[-1]), _texts(bot)
    assert len([line for line in _texts(bot)[-1].splitlines() if line.startswith("- ")]) == 2
    assert "more" not in _texts(bot)[-1], "more than a first line went"


def test_plan_alone_with_nothing_queued_says_so(bot):
    _saved(bot)
    bot["fake"].push(OWNER, "/plan")
    assert _until(lambda: _texts(bot)[-1:] == [SAID["plan_list_none"]]), _texts(bot)


def test_plan_is_in_the_menu_help_and_the_tour(bot):
    assert "plan" in [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "- /plan: " in telegram_bot.HELP
    assert "planned" in telegram_bot.TOUR_EVIDENCE
    assert any("planned" in steps for _title, steps in telegram_bot.TOUR_PARTS)
