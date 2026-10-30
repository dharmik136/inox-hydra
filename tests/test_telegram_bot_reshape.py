"""
Shape a draft from the phone: the creator's own rewrite buttons (phase 4, item 5).
==================================================================================

Under a draft the bot wrote (with "The bot may send me what it writes from my
collection" on), one button per rewrite the creator keeps: Shorter, New
opening and Another angle unless they change them in Brand, under Writing
(which buttons appear, and what each asks for, are preferences with visible
defaults). A press is answered at once and the rewrite runs beside the bot's
loop, through the creator's own provider, with the draft as it is now, the
notes it was written from, their things to remember and writing preferences,
and the button's own instruction. Kept only if it passes the grounding check
every draft passes. The draft changes in place, only while it is still a
draft and unchanged since the rewrite read it; the text it replaced is kept
on the draft, which the Composer lists, and the bot's answer carries Undo.

docs/quality/cycle4/bot-phase4.md, item 5. Against the fake Bot API and the
fake provider (tests/ai_fake.py).

Strict Invariants:
- Zero em-dashes.
"""

import json
import os
import sys
import time

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for folder in (os.path.join(REPO_ROOT, "studio", "backend"), os.path.dirname(__file__)):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import telegram_bot  # noqa: E402
import writing  # noqa: E402
from ai_fake import FakeProvider  # noqa: E402
from database import get_db  # noqa: E402
from test_collection_bot_writing import DRAFT, _collect, _labels, _newest, _words_on  # noqa: E402
from test_telegram_bot_e2e import OWNER, _until, bot  # noqa: E402,F401
from test_telegram_bot_replies import _saved, _texts  # noqa: E402

SAID = telegram_bot.SENTENCES
SHORTER = "Pricing is design.\n\nWrite the price first."


@pytest.fixture
def provider(bot):
    fake = FakeProvider()
    fake.connect()
    fake.answer = lambda body: {"draft": SHORTER if "REWRITE IT" in str(body) else DRAFT}
    yield fake
    fake.close()


def _post():
    conn = get_db()
    try:
        row = conn.execute("SELECT p.id, p.content, p.made_with, p.status FROM posts p JOIN collection_items c "
                           "ON c.post_id = p.id LIMIT 1").fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _drafted(bot):
    _saved(bot)
    _words_on(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith(SAID["draft_ready_words"])), _texts(bot)
    return _newest(bot)


def _answers(bot):
    return [a["text"] for a in bot["fake"].answered]


def test_a_draft_the_bot_wrote_carries_the_creators_rewrite_buttons(bot, provider):
    message = _drafted(bot)
    assert _labels(bot, message) == ["Send me the whole post", "Shorter", "New opening", "Another angle"]


def test_a_press_rewrites_the_draft_through_the_provider_and_keeps_the_earlier_text(bot, provider):
    _drafted(bot)
    before = _post()
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: SAID["rewriting"] in _answers(bot)), _answers(bot)
    assert _until(lambda: _texts(bot)[-1].startswith("Rewritten in your studio (Shorter). It begins:")), _texts(bot)
    assert _texts(bot)[-1].endswith("\n\nPricing is design.")
    sent = provider.sent()
    assert before["content"] in sent, "the provider was not sent the draft as it is"
    assert "Make it about a third shorter" in sent, "the button's own instruction was not sent"
    assert "pricing is a design decision, not a finance one" in sent, "the notes it came from were not sent"
    assert writing.preferences()["tone"] in sent, "the writing preferences were not sent"
    after = _post()
    assert after["content"] == SHORTER and after["status"] == "draft"
    earlier = json.loads(after["made_with"])["earlier"]
    assert [e["text"] for e in earlier] == [before["content"]] and earlier[0]["by"] == "Shorter"
    assert _labels(bot) == ["Send me the whole post", "Shorter", "New opening", "Another angle", "Undo"]


def test_undo_puts_the_earlier_text_back_while_the_draft_is_as_the_rewrite_left_it(bot, provider):
    _drafted(bot)
    before = _post()["content"]
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith("Rewritten in your studio"))
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: SAID["reshape_undone"] in _answers(bot)), _answers(bot)
    assert _post()["content"] == before
    assert json.loads(_post()["made_with"]).get("earlier") == []


def test_undo_keeps_a_draft_changed_at_the_desk_since(bot, provider):
    _drafted(bot)
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith("Rewritten in your studio"))
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET content = 'Changed at the desk.' WHERE id = ?", (_post()["id"],))
    conn.close()
    bot["fake"].press_button("Undo", OWNER)
    assert _until(lambda: SAID["undo_changed"] in _answers(bot)), _answers(bot)
    assert _post()["content"] == "Changed at the desk."


def test_a_draft_changed_at_the_desk_while_it_was_rewritten_is_kept(bot, provider):
    _drafted(bot)
    provider.delay = 1.5
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: SAID["rewriting"] in _answers(bot))
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET content = 'Typed at the desk meanwhile.' WHERE id = ?", (_post()["id"],))
    conn.close()
    assert _until(lambda: _texts(bot)[-1] == SAID["reshape_changed"], timeout=10), _texts(bot)
    assert _post()["content"] == "Typed at the desk meanwhile."


def test_a_queued_post_is_not_rewritten(bot, provider):
    _drafted(bot)
    conn = get_db()
    with conn:
        conn.execute("UPDATE posts SET status = 'scheduled', scheduled_for = '2026-11-02T09:00:00+00:00' WHERE id = ?",
                     (_post()["id"],))
    conn.close()
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["reshape_not_draft"]), _texts(bot)
    assert _post()["content"] == DRAFT


def test_with_no_provider_the_press_says_so_and_nothing_is_asked(bot, provider):
    _drafted(bot)
    asked = len(provider.requests)
    from agno_agentos import model_gateway
    model_gateway.save_ai_config(provider="local_deterministic")
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: SAID["no_provider"] in _answers(bot)), _answers(bot)
    time.sleep(0.5)
    assert len(provider.requests) == asked and _post()["content"] == DRAFT


def test_a_rewrite_with_a_figure_nobody_sent_is_refused_and_the_draft_kept(bot, provider):
    _drafted(bot)
    provider.answer = lambda body: {"draft": "Pricing is design. 73% of studios agree." if "REWRITE IT" in str(body)
                                    else DRAFT}
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["write_refused"]), _texts(bot)
    assert _post()["content"] == DRAFT


def test_which_buttons_appear_and_what_each_asks_are_the_creators(bot, provider):
    res = bot["client"].put("/api/v1/writing/preferences",
                            json={"reshapes": [{"label": "Plainer", "asks": "Say it in plainer words."}]})
    assert res.status_code == 200, res.text
    message = _drafted(bot)
    assert _labels(bot, message) == ["Send me the whole post", "Plainer"]
    bot["fake"].press_button("Plainer", OWNER)
    assert _until(lambda: _texts(bot)[-1].startswith("Rewritten in your studio (Plainer)."))
    assert "Say it in plainer words." in provider.sent()


def test_no_rewrite_buttons_is_a_choice_too(bot, provider):
    assert bot["client"].put("/api/v1/writing/preferences", json={"reshapes": []}).status_code == 200
    message = _drafted(bot)
    assert _labels(bot, message) == ["Send me the whole post"]


@pytest.mark.parametrize("wrong", [
    [{"label": f"B{n}", "asks": "Do it."} for n in range(7)],
    [{"label": "A label far longer than a button", "asks": "Do it."}],
    [{"label": "Shorter", "asks": ""}],
    [{"label": "Same", "asks": "One."}, {"label": "same", "asks": "Two."}],
    [{"label": "Shorter", "asks": "x" * 201}],
])
def test_a_rewrite_outside_its_limits_is_refused_and_nothing_saved(bot, wrong):
    before = writing.preferences()["reshapes"]
    res = bot["client"].put("/api/v1/writing/preferences", json={"reshapes": wrong})
    assert res.status_code == 400, res.text
    assert writing.preferences()["reshapes"] == before


def test_a_fresh_profile_gets_the_three_defaults(bot):
    labels = [b["label"] for b in writing.preferences()["reshapes"]]
    assert labels == ["Shorter", "New opening", "Another angle"]
    described = bot["client"].get("/api/v1/writing/preferences").json()
    assert described["defaults"]["reshapes"][0]["asks"].startswith("Make it about a third shorter")


def test_with_the_words_switch_off_no_rewrite_button_is_offered(bot, provider):
    _saved(bot)
    _collect(bot)
    bot["fake"].press_button("Write it up", OWNER)
    assert _until(lambda: _texts(bot)[-1] == SAID["draft_ready"])
    assert _labels(bot) == []


def test_rewriting_never_holds_up_the_bot(bot, provider):
    _drafted(bot)
    provider.delay = 3.0
    bot["fake"].press_button("Shorter", OWNER)
    assert _until(lambda: SAID["rewriting"] in _answers(bot))
    pressed = time.monotonic()
    bot["fake"].push(OWNER, "/status")
    assert _until(lambda: _texts(bot)[-1].startswith("Your studio is running."), timeout=2.5)
    assert time.monotonic() - pressed < 2.5
    assert _until(lambda: _texts(bot)[-1].startswith("Rewritten in your studio"), timeout=10)


def test_at_most_ten_earlier_texts_are_kept(bot, provider):
    _drafted(bot)
    post_id = _post()["id"]
    for n in range(12):
        conn = get_db()
        with conn:
            conn.execute("UPDATE posts SET content = ? WHERE id = ?", (f"Version {n} of the draft.", post_id))
        conn.close()
        assert writing.reshape(post_id, "Shorter")["status"] == "rewritten"
    earlier = json.loads(_post()["made_with"])["earlier"]
    assert len(earlier) == writing.EARLIER_KEPT == 10
    assert earlier[-1]["text"] == "Version 11 of the draft."
