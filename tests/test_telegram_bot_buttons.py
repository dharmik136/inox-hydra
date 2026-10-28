"""
Buttons on the bot's messages: Undo, Remind me in an hour, Done.
================================================================

Telegram's inline buttons, pressed on the phone and read back by the studio
as callback_query updates from getUpdates, the way it reads messages:

  under "Saved as a draft in your studio."   Undo: removes that draft, only
                                             while it is untouched in the
                                             studio
  under "A post in your queue is due now."   Remind me in an hour: told
                                             again in an hour if still due;
                                             Done: the reminder is cleared,
                                             and nothing is marked as posted

Each press is answered (answerCallbackQuery, the notice the phone shows) and
the message is edited to say what became of it, its buttons gone. A button
acts only on the studio's own records, only for the paired chat (a press from
any other chat is refused like a stranger's message), only once, and an old
or unknown button says so. A button carries an opaque id, never words from a
post or a draft. Nothing here reaches LinkedIn.

Driven end to end against the fake Bot API (tests/telegram_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, STRANGER, _drafts, _until, bot  # noqa: E402,F401
from test_telegram_bot_figures import _record  # noqa: E402
from test_telegram_bot_notifications import _due, _settle, notifying  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
# A button's data: an opaque id and the button's one letter, nothing else.
OPAQUE = re.compile(r"^[A-Za-z0-9_-]{8,40}\.[a-z]$")


def _newest(bot, text):
    """The newest message the bot sent the owner with this text, as it was sent."""
    found = [m for m in bot["fake"].sent if m["chat_id"] == OWNER and m["text"] == text]
    assert found, f"no message {text!r} was sent: {_texts(bot)}"
    return found[-1]


def _labels(bot, message):
    return [b["text"] for b in bot["fake"].buttons(message["message_id"])]


def _answers(bot):
    return [a["text"] for a in bot["fake"].answered]


def _post_row(draft_text):
    conn = get_db()
    try:
        row = conn.execute("SELECT id, content, status FROM posts WHERE draft_id = "
                           "(SELECT id FROM drafts WHERE raw_content = ?)", (draft_text,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _posts_with(words):
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM posts WHERE content LIKE ?", (f"%{words}%",)).fetchone()[0]
    finally:
        conn.close()


def _linkedin_counts():
    import egress
    row = next(c for c in egress.describe()["categories"] if c["name"] == "linkedin")
    return row["performed"], row["refused"]


def _idea(bot, words):
    bot["fake"].push(OWNER, "Idea: " + words)
    assert _until(lambda: words in _drafts()), _drafts()
    assert _until(lambda: SAID["draft"] in _texts(bot)), _texts(bot)
    return _newest(bot, SAID["draft"])


def test_a_saved_draft_has_undo_which_removes_it_and_the_message_then_says_so(bot):
    _saved(bot)
    sent = _idea(bot, "take this back")
    assert _labels(bot, sent) == ["Undo"]
    data = bot["fake"].buttons(sent["message_id"])[0]["callback_data"]
    assert OPAQUE.match(data) and len(data.encode("utf-8")) <= 64, data
    assert "take" not in data and "back" not in data
    before = _linkedin_counts()
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["undone"]]), _answers(bot)
    assert _until(lambda: bot["fake"].message(sent["message_id"])["text"] == SAID["draft"] + "\n\n" + SAID["undone"])
    assert bot["fake"].buttons(sent["message_id"]) == [], "the buttons stayed after the press"
    assert _drafts() == [] and _posts_with("take this back") == 0, "Undo left the draft in the studio"
    assert _linkedin_counts() == before


def test_undo_keeps_a_draft_changed_in_the_studio_and_says_so(bot):
    _saved(bot)
    sent = _idea(bot, "I will edit this at my desk")
    post = _post_row("I will edit this at my desk")
    res = bot["client"].put(f"/api/posts/{post['id']}", json={"content": "Edited at my desk, keep it"})
    assert res.status_code == 200, res.text
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["undo_changed"]]), _answers(bot)
    assert _post_row("I will edit this at my desk")["content"] == "Edited at my desk, keep it"
    assert _until(lambda: bot["fake"].message(sent["message_id"])["text"].endswith(SAID["undo_changed"]))
    assert bot["fake"].buttons(sent["message_id"]) == []


def test_undo_keeps_a_draft_queued_in_the_studio(bot):
    _saved(bot)
    _idea(bot, "queue this one")
    post = _post_row("queue this one")
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'scheduled', scheduled_for = '2026-11-30T09:00:00+00:00' "
                     "WHERE id = ?", (post["id"],))
    conn.close()
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["undo_changed"]]), _answers(bot)
    assert _post_row("queue this one")["status"] == "scheduled"


def test_undo_of_a_draft_already_deleted_in_the_studio_says_there_is_nothing_to_undo(bot):
    _saved(bot)
    _idea(bot, "deleted at the desk")
    post = _post_row("deleted at the desk")
    assert bot["client"].delete(f"/api/posts/{post['id']}").status_code == 200
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["undo_gone"]]), _answers(bot)


def test_each_button_works_once(bot):
    _saved(bot)
    sent = _idea(bot, "only once")
    data = bot["fake"].buttons(sent["message_id"])[0]["callback_data"]
    # Two presses of the same button, before the first is answered.
    bot["fake"].press(OWNER, data, message_id=sent["message_id"])
    bot["fake"].press(OWNER, data, message_id=sent["message_id"])
    assert _until(lambda: len(_answers(bot)) == 2), _answers(bot)
    assert _answers(bot) == [SAID["undone"], SAID["button_used"]]
    # A draft saved again with the same words is a new draft, and the old button does not reach it.
    _idea(bot, "only once")
    bot["fake"].press(OWNER, data, message_id=sent["message_id"])
    assert _until(lambda: len(_answers(bot)) == 3)
    assert _answers(bot)[2] == SAID["button_used"]
    assert _drafts() == ["only once"]


def test_an_old_or_unknown_button_says_so_in_plain_words(bot, monkeypatch):
    _saved(bot)
    monkeypatch.setattr(telegram_bot, "BUTTONS_KEPT", 1)
    first = _idea(bot, "the older one")
    bot["fake"].push(OWNER, "Idea: the newer one")
    assert _until(lambda: _texts(bot).count(SAID["draft"]) == 2)
    # The older message's button is no longer kept: it is old.
    bot["fake"].press_button("Undo", OWNER, message_id=first["message_id"])
    assert _until(lambda: _answers(bot) == [SAID["button_old"]]), _answers(bot)
    assert _until(lambda: bot["fake"].buttons(first["message_id"]) == []), "an old button was left to be pressed"
    assert bot["fake"].message(first["message_id"])["text"] == SAID["draft"], "an old button's message was rewritten"
    # Data no button of the bot's ever carried.
    for data in ("AAAAAAAAAAAA.u", "nonsense", ""):
        bot["fake"].press(OWNER, data, message_id=first["message_id"])
    assert _until(lambda: len(_answers(bot)) == 4), _answers(bot)
    assert _answers(bot)[1:] == [SAID["button_old"]] * 3
    assert sorted(_drafts()) == ["the newer one", "the older one"], "an old or unknown button removed a draft"
    newer = _newest(bot, SAID["draft"])
    assert _labels(bot, newer) == ["Undo"], "an old button took a newer message's buttons away"


def test_a_press_from_another_chat_is_refused_like_a_strangers_message(bot):
    _saved(bot)
    sent = _idea(bot, "mine alone")
    data = bot["fake"].buttons(sent["message_id"])[0]["callback_data"]
    bot["fake"].press(STRANGER, data)
    # In the paired chat's own message, a person who is not the chat.
    bot["fake"].press(OWNER, data, message_id=sent["message_id"], from_id=STRANGER)
    assert _until(lambda: bot["fake"].waiting() == [])
    assert _until(lambda: len(bot["fake"].answered) >= 1)
    _settle(bot)
    assert _drafts() == ["mine alone"], "a press from another chat removed the owner's draft"
    assert [a["text"] for a in bot["fake"].answered] == [SAID["other_chat"]], bot["fake"].answered
    assert bot["fake"].buttons(sent["message_id"]) != [], "a stranger's press took the owner's buttons away"
    chats = bot["client"].get("/api/v1/ingress/settings").json()["refused_chats"]
    assert [(c["chat_id"], c["first"]) for c in chats] == [(STRANGER, "a button press")]
    # The owner's own press still works.
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot)[-1] == SAID["undone"]), _answers(bot)


def test_a_press_the_studio_cannot_carry_out_is_answered_after_three_tries(bot, monkeypatch):
    """Retried like any update, then stepped over, and said: a press never spins for good."""
    import ingress
    _saved(bot)
    _idea(bot, "stuck for now")
    tries = []

    def failing(*args, **kwargs):
        tries.append(True)
        raise RuntimeError("the disk is full")

    monkeypatch.setattr(telegram_bot, "press", failing)
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["press_failed"]], timeout=10.0), _answers(bot)
    assert _until(lambda: bot["fake"].waiting() == []), "a press that failed blocked the queue"
    assert len(tries) == ingress.MAX_UPDATE_ATTEMPTS
    assert _drafts() == ["stuck for now"]


def test_the_poll_asks_for_button_presses_even_for_a_bot_once_set_to_messages_only(bot):
    """Telegram keeps the kinds of update a bot last asked for: set to messages only, a bot never hears a press."""
    bot["fake"].allowed_updates = ["message"]
    _saved(bot)
    _idea(bot, "pressed later")
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["undone"]]), "a press never reached the studio"
    asked = [c["params"].get("allowed_updates") for c in bot["fake"].calls_of("getUpdates")]
    assert all(a and "callback_query" in a and "message" in a for a in asked), asked


def test_a_due_post_has_remind_and_done_and_done_marks_nothing_as_posted(notifying):
    bot = notifying
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    # The confirmations are off: a press is the creator's own act, answered all the same.
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), _texts(bot)
    sent = _newest(bot, SAID["due_one"])
    assert _labels(bot, sent) == ["Remind me in an hour", "Done"]
    before = _linkedin_counts()
    bot["fake"].press_button("Done", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["done"]]), _answers(bot)
    assert _until(lambda: bot["fake"].message(sent["message_id"])["text"] == SAID["due_one"] + "\n\n" + SAID["done"])
    assert bot["fake"].buttons(sent["message_id"]) == []
    conn = get_db()
    try:
        status, published = conn.execute("SELECT status, published_at FROM posts WHERE id = 'due-1'").fetchone()
    finally:
        conn.close()
    assert (status, published) == ("due", None), "Done marked the post as posted"
    assert _linkedin_counts() == before, "a press reached for LinkedIn"
    methods = {c["method"] for c in bot["fake"].calls}
    assert methods <= {"getUpdates", "sendMessage", "answerCallbackQuery", "editMessageText",
                       "editMessageReplyMarkup"}, methods
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"]], "Done was followed by another message"


def test_remind_me_in_an_hour_tells_again_while_it_is_still_due_and_not_after(notifying, monkeypatch):
    bot = notifying
    monkeypatch.setattr(telegram_bot, "REMIND_AFTER_SECONDS", 0.6)
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]]), _texts(bot)
    first = _newest(bot, SAID["due_one"])
    bot["fake"].press_button("Remind me in an hour", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["remind_set"]]), _answers(bot)
    assert _until(lambda: bot["fake"].buttons(first["message_id"]) == [])
    assert bot["fake"].message(first["message_id"])["text"] == SAID["due_one"] + "\n\n" + SAID["remind_set"]
    # An hour later, still due: told again, with the same two buttons.
    assert _until(lambda: _texts(bot) == [SAID["due_one"], SAID["due_again_one"]]), _texts(bot)
    again = _newest(bot, SAID["due_again_one"])
    assert _labels(bot, again) == ["Remind me in an hour", "Done"]
    # Asked again, and posted at the desk before the hour is up: nothing more is said.
    bot["fake"].press_button("Remind me in an hour", OWNER, message_id=again["message_id"])
    assert _until(lambda: len(_answers(bot)) == 2)
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'published', published_at = ? WHERE id = 'due-1'",
                     ("2026-10-28T09:00:00+00:00",))
    conn.close()
    import time
    time.sleep(0.8)
    _settle(bot)
    assert _texts(bot) == [SAID["due_one"], SAID["due_again_one"]], "a post no longer due was told again"


def test_forgetting_everything_forgets_the_buttons_and_the_reminders(notifying, monkeypatch):
    bot = notifying
    monkeypatch.setattr(telegram_bot, "REMIND_AFTER_SECONDS", 3600.0)
    _saved(bot)
    _record(latest_days=5)
    bot["client"].post("/api/v1/ingress/options", json={"notify_due": True})
    _due()
    assert _until(lambda: _texts(bot) == [SAID["due_one"]])
    bot["fake"].press_button("Remind me in an hour", OWNER)
    assert _until(lambda: _answers(bot) == [SAID["remind_set"]])
    import onboarding
    onboarding.forget_identity()
    conn = get_db()
    try:
        held = conn.execute("SELECT key FROM settings WHERE key IN (?, ?)",
                            (telegram_bot.BUTTONS_KEY, telegram_bot.REMIND_KEY)).fetchall()
    finally:
        conn.close()
    assert held == []


def test_the_help_and_the_policy_name_the_buttons():
    article = " ".join(open(os.path.join(REPO_ROOT, "docs", "help", "send-a-post-idea-from-telegram.md"),
                            encoding="utf-8").read().split())
    policy = " ".join(open(os.path.join(REPO_ROOT, "docs", "PRIVACY_POLICY.md"), encoding="utf-8").read().split())
    for label in telegram_bot.BUTTON_LABELS.values():
        assert f"**{label}**" in article, label
        assert label in policy, label
    for key in ("undone", "undo_changed", "undo_gone", "remind_set", "done", "button_used", "button_old",
                "press_failed", "due_again_one"):
        assert SAID[key] in article, key
