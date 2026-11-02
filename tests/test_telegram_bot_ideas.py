"""
Today's ideas on the phone: /ideas (phase 5, item 5).
=====================================================

/ideas reads today's batch of From your record, a SELECT: it never builds a
batch and never calls a model. With the words switch on, each shown card
that carries the creator's own words, numbered as "<its block>: <its
excerpt>", with its Write up button, and how many more cards carry no words
to send (a follow's title can name someone else, so it is never sent). Off:
how many ideas are ready. With no batch today, it says so and how they are
made. Write up writes a draft from that card's words through the creator's
provider, beside the loop; the draft carries the card, and the card is
marked used, as the studio's Draft from this marks it.

docs/quality/cycle4/bot-phase5.md, item 5. Against the fake Bot API and the
fake provider.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import record_daily  # noqa: E402
import telegram_bot  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
DRAFT = "Hiring is slow because the loop is slow.\n\nShorten the loop."


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = {"draft": DRAFT}
    yield fake
    fake.close()


def _card(card_id, slot, block, kind, payload, status="shown", label="typed"):
    return (card_id, slot, block, kind, label, payload, status)


def _batch(*cards, day=None):
    """Today's batch, as the daily job would have stored it: its run row, and its cards."""
    day = (day or record_daily.local_today()).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    with conn:
        conn.execute("INSERT OR REPLACE INTO daily_run (day, started_at, finished_at, local_ok, note) "
                     "VALUES (?, ?, ?, 1, 'built from your record')", (day, now, now))
        for card_id, slot, block, kind, label, payload, status in cards:
            conn.execute("INSERT INTO daily_view (day, card_id, slot, block, kind, label, method, payload_json, "
                         "provenance_json, status, created_at) VALUES (?, ?, ?, ?, ?, ?, 'a rule', ?, '{}', ?, ?)",
                         (day, card_id, slot, block, kind, label, json.dumps(payload), status, now))
    conn.close()
    return day


def _usual(item_id=None):
    """Five cards as a day can hold them: an ask, a comment of the creator's, a follow, the model's pending
    slot, and the Monday card; and, with an item, one drawn from the collection."""
    cards = [
        _card("ask:1", 3, "you_asked", "ask", {"title": "Something you asked for", "excerpt": "more on hiring loops",
                                                "draft_text": "more on hiring loops", "block_label": "You asked",
                                                "ask_id": None}),
        _card("eng:7", 4, "you_engaged_with", "comment",
              {"title": "You engaged with", "excerpt": "My comment: loops beat funnels",
               "draft_text": "My comment: loops beat funnels", "block_label": "You engaged with"}),
        _card("follow:3", 2, "you_engaged_with", "follow",
              {"title": "You follow Jordan Example", "excerpt": "", "draft_text": "", "block_label": "You engaged with"}),
        _card("abstain:model_pending", 5, "model", "model_pending",
              {"sentence": "An idea from your own AI provider arrives here the first time you open this section today.",
               "block_label": "Suggested by your model"}, status="abstained", label="abstained"),
        _card("monday:2026-W45", 0, "monday", "monday",
              {"title": "Your week", "excerpt": "3 posts published", "draft_text": "", "block_label": "This week"},
              label="measured"),
    ]
    if item_id is not None:
        cards.append(_card(f"collected:{item_id}", 1, "you_asked", "collected",
                           {"title": "Something you sent your bot", "excerpt": "pricing is a design decision",
                            "draft_text": "pricing is a design decision", "item_id": item_id,
                            "block_label": "You asked"}))
    return cards


def _answer(bot):
    found = [m for m in bot["fake"].sent if str(m["text"] or "").startswith(
        (telegram_bot.IDEAS_HEAD, "One idea is ready", "Today's ideas are not made yet", "Today's ideas have nothing"))
        or "ideas are ready in your studio" in str(m["text"] or "")]
    return found[-1] if found else None


def _labels(bot, message):
    return [b["text"] for b in bot["fake"].buttons(message["message_id"])]


def _asked(bot):
    bot["fake"].push(OWNER, "/ideas")
    assert _until(lambda: _answer(bot) is not None), _texts(bot)
    return _answer(bot)


def test_with_no_batch_today_it_says_so_and_how_ideas_are_made_and_builds_nothing(bot, provider, monkeypatch):
    def never(*_args, **_kwargs):
        raise AssertionError("the bot built a batch")
    monkeypatch.setattr(record_daily, "run_today", never)
    _saved(bot)
    answer = _asked(bot)
    assert answer["text"] == SAID["ideas_not_yet"]
    assert "first time it runs each day" in SAID["ideas_not_yet"]
    conn = get_db()
    assert conn.execute("SELECT COUNT(*) FROM daily_run").fetchone()[0] == 0
    conn.close()
    time.sleep(0.4)
    assert provider.requests == [], "the bot asked the model"


def test_with_the_words_off_it_says_how_many_are_ready(bot, provider):
    _saved(bot)
    _batch(*_usual())
    answer = _asked(bot)
    assert answer["text"].startswith(SAID["ideas_ready"].format(count=3))
    assert telegram_bot.IDEAS_MODEL_WAITING in answer["text"]
    assert _labels(bot, answer) == []
    assert "loops" not in answer["text"] and "Jordan" not in answer["text"]


def test_with_the_words_on_each_card_with_words_and_its_write_up(bot, provider):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    _batch(*_usual())
    answer = _asked(bot)
    text = answer["text"]
    assert text.startswith(telegram_bot.IDEAS_HEAD)
    assert "1. You asked: more on hiring loops" in text
    assert "2. You engaged with: My comment: loops beat funnels" in text
    assert telegram_bot.IDEAS_MORE_ONE in text
    assert "Jordan" not in text, "a follow's title, which names someone, was sent"
    assert "3 posts published" not in text, "the Monday card's counts went"
    assert telegram_bot.IDEAS_MODEL_WAITING in text
    assert _labels(bot, answer) == ["Write up 1", "Write up 2"]


def test_write_up_writes_a_draft_from_that_card_and_marks_it_used(bot, provider):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    day = _batch(*_usual())
    answer = _asked(bot)
    bot["fake"].press_button("Write up 1", OWNER, message_id=answer["message_id"])
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)
    assert [a["text"] for a in bot["fake"].answered][-1] == SAID["writing"]
    assert "more on hiring loops" in provider.sent() and "loops beat funnels" not in provider.sent()
    conn = get_db()
    post = conn.execute("SELECT content, origin_card_id, origin_day, made_with FROM posts WHERE origin_card_id IS NOT NULL")
    post = post.fetchone()
    marks = conn.execute("SELECT mark, post_id FROM card_marks WHERE card_id = 'ask:1'").fetchall()
    conn.close()
    assert post["content"] == DRAFT and post["origin_card_id"] == "ask:1" and post["origin_day"] == day
    made = json.loads(post["made_with"])
    assert made["card"] == "ask:1" and made["via"] == "telegram" and made["card_title"] == "Something you asked for"
    assert [m["mark"] for m in marks] == ["used"]
    ready = [m for m in bot["fake"].sent if str(m["text"]).startswith(SAID["draft_ready_words"])][-1]
    assert "Plan it" in _labels(bot, ready)
    assert _labels(bot, answer) == ["Write up 2"], "the pressed button stayed, or the other went"


def test_a_card_drawn_from_the_collection_writes_from_its_item(bot, provider):
    import collection
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    item = collection.add("idea", "pricing is a design decision")
    _batch(*_usual(item["id"]))
    answer = _asked(bot)
    assert "1. You asked: pricing is a design decision" in answer["text"]
    bot["fake"].press_button("Write up 1", OWNER, message_id=answer["message_id"])
    assert _until(lambda: any(t.startswith(SAID["draft_ready_words"]) for t in _texts(bot))), _texts(bot)
    conn = get_db()
    status = conn.execute("SELECT status, post_id FROM collection_items WHERE id = ?", (item["id"],)).fetchone()
    post = conn.execute("SELECT origin_card_id FROM posts WHERE id = ?", (status["post_id"],)).fetchone()
    conn.close()
    assert status["status"] == "used" and post["origin_card_id"] == f"collected:{item['id']}"


def test_with_no_provider_a_press_says_so(bot):
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"collection_words": True})
    _batch(*_usual())
    answer = _asked(bot)
    bot["fake"].press_button("Write up 1", OWNER, message_id=answer["message_id"])
    assert _until(lambda: [a["text"] for a in bot["fake"].answered][-1:] == [SAID["no_provider"]])


def test_a_batch_with_nothing_shown_says_what_the_studio_shows_instead(bot, provider):
    _saved(bot)
    _batch(_card("abstain:opener", 2, "working_for_you", "opener", {"sentence": "No opener is free today.",
                                                                    "block_label": "Working for you"},
                 status="abstained", label="abstained"))
    answer = _asked(bot)
    assert answer["text"].startswith(SAID["ideas_empty"])


def test_yesterdays_batch_is_not_today_s(bot, provider):
    from datetime import timedelta
    _saved(bot)
    _batch(*_usual(), day=record_daily.local_today() - timedelta(days=1))
    assert _asked(bot)["text"] == SAID["ideas_not_yet"]


def test_ideas_is_in_the_menu_help_and_the_tour_and_answered_with_the_confirmations_off(bot, provider):
    assert "ideas" in [name for name, _words in telegram_bot.BOT_COMMANDS]
    assert "- /ideas: " in telegram_bot.HELP
    assert "card" in telegram_bot.TOUR_EVIDENCE
    _saved(bot)
    bot["client"].post("/api/v1/ingress/options", json={"replies": False})
    assert _asked(bot)["text"] == SAID["ideas_not_yet"]
