"""
Things to remember, used in every writing request, as the creator allows.
========================================================================

Phase 3 of the Telegram bot, item 3. The creator tells the studio facts
about themselves, their audience, their offers and dates: in Brand, under
Writing, or from the phone with /remember (and /forget). They go with every
writing request (Make a post, Combine, Angles, Write it up, Command, Re-Hook
and the daily idea) as the creator chose: all of them, only the ones ticked,
or none. A draft says which were used. A figure a fact gives may appear in
a draft; a figure in nothing sent may not.

Against the fake Bot API and the fake provider, both on loopback.

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_writing import provider, studio  # noqa: E402,F401
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
COURSE = "My course for small studios costs 49 dollars"
AUDIENCE = "Founders of two person studios"


def _remember(client, text, about="you"):
    res = client.post("/api/v1/remembered", json={"text": text, "about": about})
    assert res.status_code == 200, res.text
    return res.json()["fact"]["id"]


def _facts():
    conn = get_db()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM remembered ORDER BY id")]
    finally:
        conn.close()


def _item(text):
    import collection
    return collection.add("note", text)["id"]


# ---------------------------------------------------------------------------
# The list, in the studio
# ---------------------------------------------------------------------------

def test_a_fact_is_kept_edited_set_aside_and_removed(studio):
    fact = _remember(studio, COURSE, "offer")
    listed = studio.get("/api/v1/remembered").json()
    assert [(f["text"], f["about"], f["in_use"], f["source"]) for f in listed["facts"]] == [(COURSE, "offer", True, "studio")]
    assert listed["mode"] == "all"
    assert studio.put(f"/api/v1/remembered/{fact}", json={"text": COURSE + ", or 39 early",
                                                         "in_use": False}).status_code == 200
    assert (_facts()[0]["text"], _facts()[0]["in_use"]) == (COURSE + ", or 39 early", 0)
    assert studio.delete(f"/api/v1/remembered/{fact}").status_code == 200
    assert _facts() == []
    assert studio.delete(f"/api/v1/remembered/{fact}").status_code == 404


@pytest.mark.parametrize("payload", [{"text": "   "}, {"text": "x" * 400}, {"text": "fine", "about": "gossip"}])
def test_an_empty_too_long_or_unknown_fact_is_refused(studio, payload):
    res = studio.post("/api/v1/remembered", json=payload)
    assert res.status_code in (400, 422), res.text
    assert _facts() == []


def test_the_same_fact_twice_is_kept_once(studio):
    _remember(studio, COURSE)
    _remember(studio, "  " + COURSE + " ")
    assert len(_facts()) == 1


# ---------------------------------------------------------------------------
# Every writing request reads them, as the creator chose
# ---------------------------------------------------------------------------

def test_make_a_post_carries_the_facts_and_the_draft_says_which(studio, provider):
    course, audience = _remember(studio, COURSE, "offer"), _remember(studio, AUDIENCE, "audience")
    made = studio.post("/api/v1/collection/write", json={"items": [_item("pricing is a design decision")]}).json()
    sent = provider.sent()
    assert COURSE in sent and AUDIENCE in sent
    note = json.loads(studio.get(f"/api/posts/{made['id']}").json()["post"]["made_with"])
    assert note["remembered"] == [course, audience] and note["items"]
    assert all(f["used_count"] == 1 and f["last_used_at"] for f in _facts())


def test_only_the_ticked_ones_with_chosen_and_none_with_off(studio, provider):
    course = _remember(studio, COURSE, "offer")
    _remember(studio, AUDIENCE, "audience")
    studio.put(f"/api/v1/remembered/{course}", json={"in_use": False})
    assert studio.put("/api/v1/writing/preferences", json={"memory": "chosen"}).status_code == 200
    studio.post("/api/v1/collection/write", json={"items": [_item("pricing is a design decision")]})
    sent = provider.sent()
    assert AUDIENCE in sent and COURSE not in sent, "a fact not ticked went with chosen"
    studio.put("/api/v1/writing/preferences", json={"memory": "off"})
    made = studio.post("/api/v1/collection/write", json={"items": [_item("another note")]}).json()
    sent = provider.sent()
    assert AUDIENCE not in sent and COURSE not in sent, "a fact went with memory off"
    assert json.loads(studio.get(f"/api/posts/{made['id']}").json()["post"]["made_with"])["remembered"] == []


def test_a_figure_a_fact_gives_may_appear_and_one_from_nowhere_may_not(studio, provider):
    _remember(studio, COURSE, "offer")
    provider.answer = {"draft": "Pricing is design. My course costs 49 dollars."}
    assert studio.post("/api/v1/collection/write", json={"items": [_item("pricing")]}).json()["status"] == "drafted"
    provider.answer = {"draft": "Pricing is design. It costs 59 dollars."}
    assert studio.post("/api/v1/collection/write", json={"items": [_item("pricing")]}).json()["status"] == "refused"


def test_command_and_re_hook_carry_them_and_command_says_so(studio, provider):
    _remember(studio, COURSE, "offer")
    provider.answer = "A tighter post."
    answer = studio.post("/api/ai/command", json={"command": "tighten this", "context": "my draft"}).json()
    assert COURSE in provider.sent()
    assert any("thing" in part and "remember" in part for part in answer["sent"]), answer["sent"]
    assert any(COURSE in part for part in answer["sent"]), "Command's answer does not name which went"
    provider.answer = [{"archetype": "Hard Lesson", "hook": f"Hook {n}"} for n in range(10)]
    studio.post("/api/format/re-hook", json={"text": "pricing is a design decision"})
    assert COURSE in provider.sent()


def test_the_daily_idea_carries_them(studio):
    _remember(studio, AUDIENCE, "audience")
    preview = studio.get("/api/v1/record/model/preview").json()
    assert AUDIENCE in json.dumps(preview), "the daily idea's request does not carry the things to remember"


def test_what_the_model_is_told_lists_them_and_where_they_go(studio):
    _remember(studio, COURSE, "offer")
    told = studio.get("/api/v1/composer/told").json()["remembered"]
    assert told["mode"] == "all" and told["sent"] == [COURSE]
    assert "Command" in told["sent_with"] and "Make a post" in told["sent_with"]


# ---------------------------------------------------------------------------
# From the phone: /remember and /forget
# ---------------------------------------------------------------------------

def _ask(bot, text):
    before = len(_texts(bot))
    bot["fake"].push(OWNER, text)
    assert _until(lambda: len(_texts(bot)) > before), _texts(bot)
    return _texts(bot)[-1]


def test_remember_from_the_phone_with_what_it_is_about_and_undo(bot):
    _saved(bot)
    assert _ask(bot, "/remember offer: " + COURSE) == SAID["remembered"]
    assert [(f["text"], f["about"], f["source"]) for f in _facts()] == [(COURSE, "offer", "telegram")]
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: [a["text"] for a in bot["fake"].answered] == [SAID["forgot_it"]])
    assert _facts() == []
    assert _ask(bot, "/remember " + AUDIENCE) == SAID["remembered"]
    assert _facts()[0]["about"] == "you"
    assert _ask(bot, "/remember") == SAID["empty_remember"]


def test_a_fact_too_long_from_the_phone_is_said_so(bot):
    _saved(bot)
    assert _ask(bot, "/remember " + "a very long fact " * 30) == SAID["remember_long"]
    assert bot["client"].get("/api/v1/remembered").json()["facts"] == []


def test_forget_from_the_phone_removes_one_match_and_never_guesses(bot):
    _saved(bot)
    _ask(bot, "/remember " + COURSE)
    _ask(bot, "/remember my other course is for agencies")
    assert _ask(bot, "/forget course") == SAID["forget_many"].format(count=2)
    assert len(_facts()) == 2, "/forget removed something it was not sure of"
    assert _ask(bot, "/forget small studios") == SAID["forgot"]
    assert [f["text"] for f in _facts()] == ["my other course is for agencies"]
    assert _ask(bot, "/forget zebras") == SAID["forget_none"]
    assert _ask(bot, "/forget") == SAID["empty_forget"]
    everything = " ".join(m["text"] for m in bot["fake"].sent)
    assert "agencies" not in everything and "small studios" not in everything, "the bot sent a fact's words back"
