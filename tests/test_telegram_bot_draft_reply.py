"""
Reply to a draft with what to change (phase 6, item 4).
=======================================================

A plain reply to one of the bot's messages about a draft (Draft ready, a
rewrite, the times Plan it offers, a plan) is no longer filed as a note: the
bot offers Rewrite it with what you said and Keep it as a note. The first
rewrites that draft through the creator's own provider with their words as
the instruction, as a rewrite button does, keeping the replaced text for
Undo; its words come back only with the words switch on. The second keeps the
reply as a note, as before. With no provider the offer says so and the press
says it again, its buttons staying. A draft planned from the phone may be
rewritten while it is still queued at its planned time; its plan is kept.
"What a reply to a draft does" is the creator's preference.

docs/quality/cycle4/bot-phase6.md, item 4. Against the fake Bot API and the
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

import telegram_bot  # noqa: E402
import writing  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
FIRST = "Pricing is a design decision.\n\nWrite the price page first."
ASKED = "Pricing is a design decision my first client taught me.\n\nWrite the price page first."
REWRITE = "Rewrite it with what you said"
NOTE = "Keep it as a note"


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = lambda body: {"draft": ASKED if "REWRITE IT" in str(body) else FIRST}
    yield fake
    fake.close()


def _words_on(bot):
    assert bot["client"].post("/api/v1/ingress/options", json={"collection_words": True}).status_code == 200


def _drafted(bot):
    """An idea written up from the phone: the "Draft ready" message's id and the draft's post id."""
    def ready():
        return [m for m in bot["fake"].sent if str(m["text"] or "").startswith(SAID["draft_ready"])]
    before = len(ready())
    bot["fake"].push(OWNER, "Idea: pricing is a design decision")
    assert _until(lambda: any(str(m["text"] or "").startswith(SAID["collected"]) for m in bot["fake"].sent))
    saved = [m for m in bot["fake"].sent if str(m["text"] or "").startswith(SAID["collected"])][-1]
    bot["fake"].press_button("Write it up", OWNER, message_id=saved["message_id"])
    assert _until(lambda: len(ready()) > before), _texts(bot)
    conn = get_db()
    try:
        post = conn.execute("SELECT id FROM posts WHERE made_with IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()[0]
    finally:
        conn.close()
    return ready()[-1]["message_id"], post


def _reply(bot, message_id, words):
    """
    A reply on the phone to one of the bot's messages about a draft, once the
    bot has kept Telegram's id for that message (it does as Telegram answers
    the send, a moment after the phone shows it); the bot's answer to it.
    """
    assert _until(lambda: telegram_bot.post_of_message(OWNER, message_id) is not None), "the message was never kept"

    def offers():
        return [m for m in bot["fake"].sent if str(m["text"] or "") in (SAID["draft_reply_offer"],
                                                                        SAID["draft_reply_no_provider"])]
    before = len(offers())
    bot["fake"].push(OWNER, words, reply_to_message={"message_id": message_id, "chat": {"id": int(OWNER)}})
    assert _until(lambda: len(offers()) > before), _texts(bot)
    return offers()[-1]


def _labels(bot, message_id):
    return [b["text"] for b in bot["fake"].buttons(message_id)]


def _notices(bot):
    return [a["text"] for a in bot["fake"].answered]


def _post(post_id):
    conn = get_db()
    try:
        row = conn.execute("SELECT content, status, scheduled_for, made_with FROM posts WHERE id = ?",
                           (post_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _items():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM collection_items ORDER BY id")]
    finally:
        conn.close()


def test_a_reply_to_draft_ready_offers_to_rewrite_it_and_keeps_no_note(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    before = _items()
    offer = _reply(bot, ready, "make it about my first client")
    assert offer["text"] == SAID["draft_reply_offer"]
    assert "first client" not in offer["text"], "the reply's words went back out"
    assert _labels(bot, offer["message_id"]) == [REWRITE, NOTE]
    time.sleep(0.3)
    assert _items() == before, "the reply was kept as a note"


def test_rewrite_it_with_what_you_said_rewrites_the_draft_and_undo_puts_it_back(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["rewriting"]]), _notices(bot)
    assert _until(lambda: SAID["rewritten_asked"] in _texts(bot)), _texts(bot)
    sent = provider.sent()
    assert "REWRITE IT: make it about my first client" in sent and FIRST.split("\n")[0] in sent
    assert _post(post)["content"] == ASKED
    made = json.loads(_post(post)["made_with"])
    assert made["earlier"][-1]["text"] == FIRST and made["earlier"][-1]["by"] == writing.REPLY_LABEL
    answer = [m for m in bot["fake"].sent if m["text"] == SAID["rewritten_asked"]][-1]
    assert "first client" not in answer["text"]
    assert _labels(bot, answer["message_id"]) == ["Plan it", "Undo"]
    assert _labels(bot, offer["message_id"]) == []
    bot["fake"].press_button("Undo", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["reshape_undone"]]), _notices(bot)
    assert _post(post)["content"] == FIRST


def test_with_the_words_on_the_rewrite_comes_back_with_its_first_line_and_the_drafts_buttons(bot, provider):
    _saved(bot)
    _words_on(bot)
    ready, post = _drafted(bot)
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    text = telegram_bot.REWRITTEN_ASKED_WORDS + "\n\n" + ASKED.split("\n")[0]
    assert _until(lambda: text in _texts(bot)), _texts(bot)
    answer = [m for m in bot["fake"].sent if m["text"] == text][-1]
    labels = _labels(bot, answer["message_id"])
    assert labels[:2] == ["Send me the whole post", "Plan it"] and labels[-1] == "Undo"
    # A reply to the rewrite's own message is about the same draft.
    again = _reply(bot, answer["message_id"], "shorter please")
    assert _labels(bot, again["message_id"]) == [REWRITE, NOTE]


def test_keep_it_as_a_note_keeps_the_reply_as_before(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(NOTE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["collected"]]), _notices(bot)
    assert _until(lambda: any(i["text"] == "make it about my first client" for i in _items())), _items()
    note = [i for i in _items() if i["text"] == "make it about my first client"][0]
    assert note["kind"] == "note" and note["status"] == "new" and note["source"] == "telegram"
    assert _post(post)["content"] == FIRST, "the draft changed"
    assert _until(lambda: "Undo" in _labels(bot, offer["message_id"])), _labels(bot, offer["message_id"])
    assert REWRITE not in _labels(bot, offer["message_id"])


def test_with_no_provider_the_offer_says_so_and_a_press_keeps_its_buttons(bot):
    _saved(bot)
    conn = get_db()
    with conn:
        conn.execute("INSERT INTO posts (id, content, status, made_with) VALUES ('post_by_hand', ?, 'draft', ?)",
                     (FIRST, json.dumps({"items": [], "provider": "fake", "via": "telegram"})))
    conn.close()
    shown = telegram_bot.issue_buttons(OWNER, "draft", SAID["draft_ready"], rows=telegram_bot.PLAN_ONLY,
                                       post="post_by_hand")
    bot["daemon"].outbox.put(OWNER, SAID["draft_ready"], shown)
    bot["daemon"].flush_replies()
    ready = [m for m in bot["fake"].sent if m["text"] == SAID["draft_ready"]][-1]["message_id"]
    offer = _reply(bot, ready, "make it about my first client")
    assert offer["text"] == SAID["draft_reply_no_provider"]
    assert "Composer's Prompt tab" in offer["text"]
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["no_provider"]]), _notices(bot)
    time.sleep(0.4)
    assert _labels(bot, offer["message_id"]) == [REWRITE, NOTE]


def test_a_draft_planned_from_the_phone_is_rewritten_and_keeps_its_plan(bot, provider):
    import phone_plans
    _saved(bot)
    ready, post = _drafted(bot)
    when = (datetime.now(timezone.utc) + timedelta(days=2)).replace(microsecond=0).isoformat()
    assert phone_plans.plan(post, when)["status"] == "planned"
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: SAID["rewritten_asked"] in _texts(bot)), _texts(bot)
    held = _post(post)
    assert held["content"] == ASKED and held["status"] == "scheduled" and held["scheduled_for"] == when
    assert json.loads(held["made_with"])["planned"]["for"] == when
    answer = [m for m in bot["fake"].sent if m["text"] == SAID["rewritten_asked"]][-1]
    bot["fake"].press_button("Undo", OWNER, message_id=answer["message_id"])
    assert _until(lambda: _notices(bot)[-1:] == [SAID["reshape_undone"]]), _notices(bot)
    assert _post(post)["content"] == FIRST and _post(post)["status"] == "scheduled"


def test_a_post_queued_at_the_desk_or_published_is_not_rewritten(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'scheduled', scheduled_for = ? WHERE id = ?",
                     ((datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), post))
    conn.close()
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: SAID["reshape_not_draft"] in _texts(bot)), _texts(bot)
    assert _post(post)["content"] == FIRST


def test_a_draft_changed_at_the_desk_while_it_was_rewritten_is_kept(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)

    def slow(body):
        if "REWRITE IT" in str(body):
            conn = get_db()
            with conn:
                conn.execute("UPDATE posts SET content = 'Changed at the desk.' WHERE id = ?", (post,))
            conn.close()
            return {"draft": ASKED}
        return {"draft": FIRST}
    provider.answer = slow
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: SAID["reshape_changed"] in _texts(bot)), _texts(bot)
    assert _post(post)["content"] == "Changed at the desk."


def test_the_preference_keeps_a_reply_as_a_note_as_before(bot, provider):
    _saved(bot)
    options = bot["client"].get("/api/v1/ingress/settings").json()["options"]
    assert options["draft_reply"] == "rewrite" and options["defaults"]["draft_reply"] == "rewrite"
    assert bot["client"].post("/api/v1/ingress/options", json={"draft_reply": "note"}).status_code == 200
    ready, post = _drafted(bot)
    assert _until(lambda: telegram_bot.post_of_message(OWNER, ready) is not None)
    bot["fake"].push(OWNER, "make it about my first client",
                     reply_to_message={"message_id": ready, "chat": {"id": int(OWNER)}})
    assert _until(lambda: any(i["text"] == "make it about my first client" for i in _items())), _items()
    assert SAID["draft_reply_offer"] not in _texts(bot)
    assert bot["client"].post("/api/v1/ingress/options", json={"draft_reply": "maybe"}).status_code == 400
    assert bot["client"].get("/api/v1/ingress/settings").json()["options"]["draft_reply"] == "note"


def test_a_command_a_file_or_a_reply_to_something_else_is_as_before(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    bot["fake"].push(OWNER, "/plan", reply_to_message={"message_id": ready, "chat": {"id": int(OWNER)}})
    assert _until(lambda: any(t.startswith(SAID["plan_list_none"]) or t.startswith("Planned in your Queue")
                              for t in _texts(bot))), _texts(bot)
    assert SAID["draft_reply_offer"] not in _texts(bot)


def test_it_is_in_the_tour_and_the_panel_lists_a_draft_rewritten_with_a_reply(bot, provider):
    _saved(bot)
    assert any("replied" in steps for _title, steps in telegram_bot.TOUR_PARTS)

    def seen():
        return {s["key"]: s["seen"] for s in bot["client"].get("/api/v1/ingress/settings").json()["tour"]}
    assert seen()["replied"] is False
    ready, post = _drafted(bot)
    offer = _reply(bot, ready, "make it about my first client")
    bot["fake"].press_button(REWRITE, OWNER, message_id=offer["message_id"])
    assert _until(lambda: SAID["rewritten_asked"] in _texts(bot)), _texts(bot)
    assert _until(lambda: seen()["replied"]), seen()


def test_a_reply_to_the_offer_is_about_the_same_draft(bot, provider):
    _saved(bot)
    ready, post = _drafted(bot)
    first = _reply(bot, ready, "make it about my first client")
    second = _reply(bot, first["message_id"], "and keep it short")
    assert second["message_id"] != first["message_id"]
    bot["fake"].press_button(REWRITE, OWNER, message_id=second["message_id"])
    assert _until(lambda: SAID["rewritten_asked"] in _texts(bot)), _texts(bot)
    assert "REWRITE IT: and keep it short" in provider.sent()
    assert _post(post)["content"] == ASKED
